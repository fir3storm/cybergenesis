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
    assert client.post("/api/twins/from-image", json={"image_data_url": "data:image/png;base64," + "A" * 8_100_000}).status_code == 413
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


def test_benchmark_endpoint():
    b = client.get("/api/benchmark").json()
    assert "available" in b and "scope" in b


def test_library_catalog():
    lib = client.get("/api/library").json()
    assert len(lib["asset_types"]) == 9 and len(lib["attack_steps"]) == 8 and len(lib["defense_actions"]) == 7


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
