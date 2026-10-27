import os
import sys

os.environ["SIM_STEP_DELAY_MS"] = "0"
os.environ["OFFLINE_MODE"] = "true"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.orchestration.orchestrator import run_experiment  # noqa: E402
from app.simulation.twin import DigitalTwin  # noqa: E402

client = TestClient(app)

CUSTOM_TWIN = {
    "name": "Test Lab Twin", "description": "small custom topology",
    "assets": [
        {"id": "ws-1", "name": "Lab Workstation", "asset_type": "workstation", "zone": "endpoints", "pos": [-3, 1, 2]},
        {"id": "fs-1", "name": "Lab File Server", "asset_type": "file_server", "zone": "internal", "pos": [0, 1, 3]},
        {"id": "db-1", "name": "Lab DB", "asset_type": "database", "zone": "data", "pos": [3, 1, -2]},
    ],
    "connections": [
        {"source": "ws-1", "target": "fs-1", "traversable": True, "types": ["smb"]},
        {"source": "fs-1", "target": "db-1", "traversable": True, "types": ["sql"]},
    ],
}


def test_from_dict_and_stable_seed():
    t = DigitalTwin.from_dict(CUSTOM_TWIN["assets"], CUSTOM_TWIN["connections"])
    assert t.reachable("ws-1", "db-1")
    t2 = DigitalTwin.from_dict(CUSTOM_TWIN["assets"], CUSTOM_TWIN["connections"])
    sc = {"id": "x", "source_asset": "ws-1", "target_asset": "fs-1",
          "attack_steps": [{"type": "file_modification_burst", "asset": "ws-1", "description": "burst"}]}
    assert t.apply_attack(sc, seed=42) == t2.apply_attack(sc, seed=42)
    with pytest.raises(ValueError):
        DigitalTwin.from_dict(CUSTOM_TWIN["assets"], [{"source": "ws-1", "target": "nope"}])
    with pytest.raises(ValueError):
        t.apply_attack({**sc, "attack_steps": [{"type": "run_shellcode", "asset": "ws-1", "description": "x"}]})


def test_candidates_optimality_and_red_team():
    from app.agents.red_team import enumerate_paths
    from app.simulation.candidates import evaluate_candidates

    t = DigitalTwin.from_dict(CUSTOM_TWIN["assets"], CUSTOM_TWIN["connections"])
    sc = {"id": "lab", "source_asset": "ws-1", "target_asset": "fs-1", "verification_kind": "reachability",
          "objectives": ["x"], "attack_steps": [{"type": "file_modification_burst", "asset": "ws-1", "description": "b"}]}
    base = t.clone(); t.apply_attack(sc, seed=1)
    cands = evaluate_candidates(t, base, sc, [{"action_type": "apply_patch", "asset_id": "ws-1", "params": {}}])
    by_label = {c["label"]: c for c in cands}
    assert by_label["Agent proposal"]["blocked"] is False  # patch alone does not stop spread
    assert cands[0]["blocked"] is True  # best trade-off ranked first
    # twin with two disjoint paths: red team must find the alternate after the first is cut
    assets = [{"id": n, "name": n, "asset_type": "workstation", "zone": "z", "pos": [0, 1, 0]} for n in ("a", "b", "c", "d")]
    conns = [{"source": "a", "target": "b"}, {"source": "b", "target": "d"},
             {"source": "a", "target": "c"}, {"source": "c", "target": "d"}]
    t2 = DigitalTwin.from_dict(assets, conns)
    assert len(enumerate_paths(t2, "a", "d")) == 2
    t2.apply_action("block_connection", "a", {"source": "a", "target": "b"})
    remaining = enumerate_paths(t2, "a", "d")
    assert remaining == [["a", "c", "d"]]


@pytest.mark.asyncio
async def test_concurrent_runs_isolated_twins_and_metrics():
    import asyncio as _asyncio

    from app.db import SessionLocal
    from app import models as _models

    ids = []
    for _ in range(2):
        c = client.post("/api/experiments", json={"scenario_id": "ransomware_activity", "seed": 42})
        ids.append(c.json()["id"])
    await _asyncio.gather(*(run_experiment(i) for i in ids))
    for rid in ids:
        res = client.get(f"/api/experiments/{rid}/results").json()
        assert res["run"]["state"] == "COMPLETED" and res["verification"]["outcome"] == "PASS"
        m = res["verification"]["metrics"]
        assert m["checks_total"] == 3 and m["optimal_edge_cut"] == 2 and m["optimality_gap"] == 0
        assert m["candidates"] and m["rounds"] and m["time_basis"].startswith("simulated")
        dec = res["decisions"][1]  # investigator: real telemetry evidence ids, not evt-N
        assert all(r.startswith("tele-") for r in dec["evidence_refs"]), dec
        db = SessionLocal()
        labels = {r.label for r in db.query(_models.AssetStateSnapshot).filter_by(run_id=rid).all()}
        db.close()
        assert {"baseline", "attacked", "post_remediation"} <= labels


@pytest.mark.asyncio
async def test_red_vs_blue_battle_multiple_rounds():
    c = client.post("/api/experiments", json={"scenario_id": "red_vs_blue_battle", "seed": 42})
    rid = c.json()["id"]
    await run_experiment(rid)
    res = client.get(f"/api/experiments/{rid}/results").json()
    assert res["run"]["state"] == "COMPLETED" and res["verification"]["outcome"] == "PASS", res
    rounds = res["verification"]["metrics"]["rounds"]
    assert len(rounds) >= 2, rounds  # red team must have found an alternate path at least once
    scores = [r["resilience_score"] for r in rounds]
    assert scores[-1] == 100.0 and scores == sorted(scores), rounds  # resilience climbs to 100%
    twin = client.get("/api/twin").json()
    fs = next(a for a in twin["assets"] if a["id"] == "file-server")
    assert fs["status"] in ("protected", "remediated", "healthy", "contained")


def test_one_way_outbound_block():
    t = DigitalTwin()
    assert t.reachable("database", "internet")  # exfil direction
    t.apply_action("block_connection", "web-server", {"source": "web-server", "target": "firewall", "direction": "outbound"})
    assert not t.reachable("database", "internet")  # egress cut
    assert t.reachable("internet", "web-server")  # inbound legit flow still works


@pytest.mark.asyncio
async def test_vision_and_text_to_scenario_mocked(monkeypatch):
    from app.integrations import meta_client as mc_mod
    from app import main as main_mod

    async def fake_vision(prompt, image, run_id=None):
        return ({"assets": [{"id": "ws-1", "name": "WS", "asset_type": "workstation", "zone": "endpoints", "pos": [0, 1, 0]},
                            {"id": "db-1", "name": "DB", "asset_type": "database", "zone": "data", "pos": [3, 1, 0]}],
                 "connections": [{"source": "ws-1", "target": "db-1", "traversable": True}]}, {})

    monkeypatch.setattr(mc_mod.meta_client, "chat_vision_json", fake_vision)
    r = client.post("/api/twins/from-image", json={"image_data_url": "data:image/png;base64,AAAA", "name": "Mock Diagram"})
    assert r.status_code == 201, r.text
    assert client.post("/api/twins/from-image", json={"image_data_url": "data:image/png;base64," + "A" * 4_100_000}).status_code == 413
    client.delete(f"/api/twins/custom/{r.json()['id']}")

    async def fake_chat(system, user, run_id=None):
        return ({"source_asset": "employee-workstation", "target_asset": "file-server", "severity": "high",
                 "invariant": "employee-workstation cannot reach file-server",
                 "attack_steps": [{"type": "file_modification_burst", "asset": "employee-workstation", "description": "synthetic burst"}],
                 "expected_defense": [{"action_type": "isolate_asset", "asset_id": "employee-workstation", "params": {}}]}, {})

    monkeypatch.setattr(main_mod.meta_client, "chat_json", fake_chat)
    r2 = client.post("/api/scenarios/from-text", json={"prompt_text": "what if the employee laptop is phished?", "name": "Phish What-If"})
    assert r2.status_code == 201, r2.text
    client.delete(f"/api/scenarios/custom/{r2.json()['id']}")


@pytest.mark.asyncio
async def test_human_approval_gate(monkeypatch):
    import asyncio as _asyncio

    from app.core.config import settings
    from app.orchestration import orchestrator

    monkeypatch.setattr(settings, "human_approval_enabled", True)
    monkeypatch.setattr(settings, "approval_timeout_seconds", 20)
    rid = client.post("/api/experiments", json={"scenario_id": "ransomware_activity", "seed": 42}).json()["id"]
    task = _asyncio.create_task(run_experiment(rid))
    for _ in range(100):
        await _asyncio.sleep(0.1)
        if rid in orchestrator._approvals:
            break
    assert rid in orchestrator._approvals  # isolate disrupts >=2 legit paths -> gate must fire
    assert client.post(f"/api/experiments/{rid}/approve", json={"approved": True}).status_code == 200
    await _asyncio.wait_for(task, timeout=30)
    assert client.get(f"/api/experiments/{rid}/results").json()["verification"]["outcome"] == "PASS"


@pytest.mark.asyncio
async def test_phase1_campaign_validation_and_round2_after_pass():
    from app import models
    from app.db import SessionLocal
    from app.policies.engine import evaluate_campaign
    from app.simulation.twin import DigitalTwin as _DT

    t = _DT()
    bad = {"foothold": "internet", "objective": "database", "pivot_identity": None,
           "steps": [{"type": "run_shellcode", "asset": "web-server", "description": "x"},
                     {"type": "network_connection", "asset": "database", "description": "hop"}]}
    assert evaluate_campaign(bad, t)["approved"] is False  # bad type + nonexistent hop
    good = {"foothold": "internet", "objective": "database", "pivot_identity": None,
            "steps": [{"type": "network_connection", "asset": a, "description": "traverse"}
                      for a in ["internet", "firewall", "web-server", "app-server", "database"]]}
    assert evaluate_campaign(good, t)["approved"] is True

    # spec test: after round-1 PASS on ransomware, round 2 still produces a validated campaign
    rid = client.post("/api/experiments", json={"scenario_id": "ransomware_activity", "seed": 42}).json()["id"]
    await run_experiment(rid)
    res = client.get(f"/api/experiments/{rid}/results").json()
    assert res["verification"]["outcome"] == "PASS"
    db = SessionLocal()
    red_decisions = db.query(models.AgentDecision).filter_by(run_id=rid, agent="adversary_simulator").all()
    execs = db.query(models.DefenseExecution).filter_by(run_id=rid).all()
    db.close()
    assert red_decisions, "round 2+ must persist a red campaign decision even after a round-1 PASS"
    assert execs, "every round must persist defense executions"
    rounds = res["verification"]["metrics"]["rounds"]
    assert all("foothold" in r and "objective" in r for r in rounds)


@pytest.mark.asyncio
async def test_phase2_ai_final_choice_and_metrics(monkeypatch):
    from app.agents import agents

    calls = {"n": 0}

    async def fake_final(candidates, scenario, run_id):
        calls["n"] += 1
        # deliberately pick a non-optimal candidate when one exists; system must execute the AI's pick
        pick = candidates[-1] if len(candidates) > 1 else candidates[0]
        return {"chosen_label": pick["label"], "justification": "test double pick", "confidence": 0.66,
                "candidate": pick, "mode": "live", "ai_matched_optimum": pick is candidates[0],
                "candidates_considered": len(candidates)}

    monkeypatch.setattr(agents, "final_choice", fake_final)
    rid = client.post("/api/experiments", json={"scenario_id": "lateral_movement", "seed": 42}).json()["id"]
    await run_experiment(rid)
    res = client.get(f"/api/experiments/{rid}/results").json()
    assert calls["n"] >= 1
    m = res["verification"]["metrics"]
    assert "ai_matched_optimum" in m and "candidates_considered" in m and m["candidates_considered"] >= 2
    assert res["run"]["state"] == "COMPLETED"  # honest outcome either way; choice was the AI's


@pytest.mark.asyncio
async def test_phase2_critic_debate_revision(monkeypatch):
    from app.agents import agents

    async def fake_critic(scenario, label, alt_paths, run_id):
        if alt_paths:
            path = alt_paths[0]
            return {"bypass": path, "mode": "live", "assessment": "segment leaves an alternate route",
                    "suggested_campaign": {"foothold": path[0], "pivot_identity": None, "objective": path[-1],
                                           "steps": [{"type": "network_connection", "asset": a, "description": "bypass"} for a in path],
                                           "rationale": "critic", "confidence": 0.7, "mode": "live", "path": path}}
        return {"bypass": None, "suggested_campaign": None, "mode": "live", "assessment": "no bypass"}

    monkeypatch.setattr(agents, "criticize_defense", fake_critic)
    rid = client.post("/api/experiments", json={"scenario_id": "red_vs_blue_battle", "seed": 42}).json()["id"]
    await run_experiment(rid)
    evs = client.get(f"/api/experiments/{rid}/events").json()
    types = [e["event_type"] for e in evs]
    assert "debate" in types or "red_critic" in types  # critic exchange is on the record
    res = client.get(f"/api/experiments/{rid}/results").json()
    assert res["run"]["state"] == "COMPLETED"


def test_phase3_egress_ingress_and_vuln_gating():
    t = DigitalTwin()
    assert t.reachable("database", "internet")
    t.apply_action("block_connection", "web-server", {"source": "web-server", "target": "firewall", "direction": "egress"})
    assert not t.reachable("database", "internet")
    assert t.reachable("internet", "web-server")
    # patching the only vulnerable intermediate removes the hop: vulnerabilities matter
    t2 = DigitalTwin.from_dict(
        [{"id": "a", "name": "a", "asset_type": "workstation", "zone": "z", "pos": [0, 1, 0], "vulnerabilities": []},
         {"id": "mid", "name": "mid", "asset_type": "app_server", "zone": "z", "pos": [1, 1, 0], "vulnerabilities": ["cve-x"]},
         {"id": "b", "name": "b", "asset_type": "database", "zone": "z", "pos": [2, 1, 0], "vulnerabilities": []}],
        [{"source": "a", "target": "mid", "traversable": True}, {"source": "mid", "target": "b", "traversable": True}])
    assert t2.reachable("a", "b")
    t2.apply_action("apply_patch", "mid")
    assert not t2.reachable("a", "b"), "patched intermediate must no longer be traversable"


def test_phase3_probabilistic_deterministic_and_healing_metrics():
    from app.verification.verifier import _breach_probability

    sc = {"id": "x", "source_asset": "internet", "target_asset": "database", "verification_kind": "reachability"}
    t = DigitalTwin()
    r1 = _breach_probability(t, sc)
    r2 = _breach_probability(t, sc)
    assert r1 == r2 and r1 is not None and 0 <= r1[0] <= 100 and r1[1][0] <= r1[0] <= r1[1][1]


@pytest.mark.asyncio
async def test_phase3_run_metrics_present():
    rid = client.post("/api/experiments", json={"scenario_id": "data_exfiltration", "seed": 42}).json()["id"]
    await run_experiment(rid)
    m = client.get(f"/api/experiments/{rid}/results").json()["verification"]["metrics"]
    assert m["risk_before_pct"] is not None and m["risk_after_pct"] == 0.0
    assert "disrupted_before_healing" in m and "users_affected" in m
    assert "nodes_compromised_before_containment" in m


@pytest.mark.asyncio
async def test_phase4_learning_calibration_and_token_budget(monkeypatch):
    from app.core.config import settings
    from app.integrations.meta_client import ProviderUnavailable, meta_client

    assert client.get("/api/learning/curve").json()["runs"] >= 0
    cal = client.get("/api/benchmark/calibration").json()
    assert len(cal["buckets"]) == 5
    # token budget: exhaust it, next live call must refuse with the budget reason
    monkeypatch.setattr(settings, "max_tokens_per_run", 0)
    monkeypatch.setattr(meta_client, "key", "test-key")
    monkeypatch.setattr(settings, "offline_mode", False)
    with pytest.raises(ProviderUnavailable, match="token budget"):
        await meta_client.chat_json("sys", "user", run_id="budget-test")


@pytest.mark.asyncio
async def test_phase4_confirmed_items_citations_validated(monkeypatch):
    from app.agents import agents
    from app.schemas import AgentObservation

    async def fake_chat(system, user, run_id=None):
        return ({"hypothesis": "phish leads to burst", "affected_assets": ["employee-workstation"],
                 "confirmed": [{"claim": "burst observed", "evidence_ids": ["tele-ransomware_activity-42-1", "tele-INVENTED-9"]}],
                 "speculation": [], "confidence": 0.9}, {})

    monkeypatch.setattr(agents.meta_client, "chat_json", fake_chat)
    obs = AgentObservation(anomalous=True, asset_ids=["employee-workstation"],
                           event_ids=["tele-ransomware_activity-42-0", "tele-ransomware_activity-42-1"],
                           anomaly_type="x", summary="s", confidence=0.9)
    from app.simulation.scenarios import SCENARIOS

    h = await agents.investigate(SCENARIOS["ransomware_activity"], obs, "r1")
    assert h.confirmed_items and h.confirmed_items[0]["evidence_ids"] == ["tele-ransomware_activity-42-1"]
    assert h.citation_warnings  # invented id was caught and moved out of confirmed citations


@pytest.mark.asyncio
async def test_phase5_hallucinated_asset_rejected_and_benchmark_run(monkeypatch):
    import asyncio as _asyncio

    from app import main as main_mod

    async def fake_chat(system, user, run_id=None):
        return ({"source_asset": "ghost-server", "target_asset": "file-server", "severity": "high",
                 "invariant": "x", "attack_steps": [{"type": "network_connection", "asset": "ghost-server", "description": "x"}],
                 "expected_defense": []}, {})

    monkeypatch.setattr(main_mod.meta_client, "chat_json", fake_chat)
    r = client.post("/api/scenarios/from-text", json={"prompt": "what if a ghost attacks?"})
    assert r.status_code == 422  # hallucinated asset id must not be saved

    br = client.post("/api/benchmark/run", json={"n": 3, "seed": 7, "mode": "offline"})
    assert br.status_code == 202
    rid = br.json()["run_id"]
    for _ in range(300):
        st = client.get(f"/api/benchmark/run/{rid}").json()
        if st["state"] in ("COMPLETED", "FAILED"):
            break
        await _asyncio.sleep(0.5)
    assert st["state"] == "COMPLETED" and len(st["rows"]) == 3
    assert client.get(f"/api/benchmark/run/{rid}/export?format=csv").status_code == 200


def test_benchmark_endpoint():
    b = client.get("/api/benchmark").json()
    assert "available" in b and "scope" in b


def test_library_catalog():
    lib = client.get("/api/library").json()
    assert len(lib["asset_types"]) == 9 and len(lib["attack_steps"]) == 8 and len(lib["defense_actions"]) == 11


def test_custom_twin_crud_and_validation():
    r = client.post("/api/twins/custom", json=CUSTOM_TWIN)
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    assert client.get(f"/api/twins/custom/{tid}").json()["name"] == "Test Lab Twin"
    bad = client.post("/api/twins/custom", json={**CUSTOM_TWIN, "assets": [
        {"id": "a", "name": "A", "asset_type": "teleporter", "zone": "x"}]})
    assert bad.status_code == 422
    act = client.post(f"/api/twins/custom/{tid}/activate")
    assert act.status_code == 200 and len(act.json()["twin"]["assets"]) == 3
    client.post("/api/twins/builtin/activate")
    assert client.delete(f"/api/twins/custom/{tid}").status_code == 200
    assert client.get(f"/api/twins/custom/{tid}").status_code == 404


@pytest.mark.asyncio
async def test_custom_scenario_experiment_end_to_end():
    tid = client.post("/api/twins/custom", json=CUSTOM_TWIN).json()["id"]
    sc = client.post("/api/scenarios/custom", json={
        "name": "Lab Ransomware", "source_asset": "ws-1", "target_asset": "fs-1", "severity": "critical",
        "invariant": "ws-1 cannot reach fs-1", "verification_kind": "reachability",
        "attack_steps": [{"type": "file_modification_burst", "asset": "ws-1", "description": "Synthetic burst on lab workstation"}],
        "expected_defense": [{"action_type": "isolate_asset", "asset_id": "ws-1", "params": {}}]})
    assert sc.status_code == 201, sc.text
    sid = sc.json()["id"]
    listed = client.get("/api/scenarios/custom")  # must not be shadowed by /api/scenarios/{id}
    assert listed.status_code == 200 and any(r["id"] == sid for r in listed.json())
    assert client.get(f"/api/scenarios/custom/{sid}").json()["name"] == "Lab Ransomware"
    bad = client.post("/api/scenarios/custom", json={
        "name": "Bad", "source_asset": "ws-1", "target_asset": "fs-1",
        "attack_steps": [{"type": "detonate_payload", "asset": "ws-1", "description": "x"}], "expected_defense": []})
    assert bad.status_code == 422  # step type not in allowlist
    exp = client.post("/api/experiments/custom", json={"custom_twin_id": tid, "custom_scenario_id": sid, "seed": 42})
    assert exp.status_code == 201, exp.text
    rid = exp.json()["id"]
    await run_experiment(rid)
    res = client.get(f"/api/experiments/{rid}/results").json()
    assert res["run"]["state"] == "COMPLETED", res
    assert res["verification"]["outcome"] == "PASS", res
    client.post("/api/twins/builtin/activate")
    client.delete(f"/api/scenarios/custom/{sid}")
    client.delete(f"/api/twins/custom/{tid}")
