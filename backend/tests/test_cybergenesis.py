import os
import sys

os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.orchestration.orchestrator import run_experiment  # noqa: E402
from app.policies.engine import evaluate  # noqa: E402
from app.schemas import IncidentHypothesis  # noqa: E402
from app.simulation.scenarios import SCENARIOS  # noqa: E402
from app.simulation.twin import DigitalTwin  # noqa: E402
from pydantic import ValidationError  # noqa: E402

client = TestClient(app)


def test_scenarios_load():
    assert set(SCENARIOS) == {"ransomware_activity", "compromised_identity", "lateral_movement", "data_exfiltration"}
    for s in SCENARIOS.values():
        assert s["expected_defense"] and s["invariant"] and s["attack_steps"]


def test_topology_consistent():
    t = DigitalTwin()
    d = t.to_dict()
    assert len(d["assets"]) == 10 and len(d["connections"]) == 14
    assert t.reachable("internet", "database")  # via fw/web/app
    assert t.find_path("web-server", "database") == ["web-server", "app-server", "database"]


def test_attack_updates_state_and_observer():
    from app.agents.agents import observe
    t = DigitalTwin()
    ev = t.apply_attack(SCENARIOS["ransomware_activity"], seed=42)
    assert t.status["employee-workstation"] == "compromised"
    obs = observe(ev)
    assert obs.anomalous and obs.anomaly_type == "high_volume_file_modification"


def test_schema_rejects_malformed():
    with pytest.raises(ValidationError):
        IncidentHypothesis(hypothesis="x", confidence=5)


def test_policy_rejects_unsupported_and_core_isolation():
    t = DigitalTwin()
    assert not evaluate("run_shell", "employee-workstation", {}, t).approved
    assert not evaluate("isolate_asset", "database", {}, t).approved
    assert not evaluate("block_connection", "app-server", {"source": "app-server", "target": "internet"}, t).approved
    assert evaluate("isolate_asset", "employee-workstation", {}, t).approved


def test_isolation_changes_reachability_and_reset():
    t = DigitalTwin()
    assert t.reachable("employee-workstation", "file-server")
    t.apply_action("isolate_asset", "employee-workstation")
    assert not t.reachable("employee-workstation", "file-server")
    t.reset()
    assert t.reachable("employee-workstation", "file-server")
    assert t.status["employee-workstation"] == "healthy"


def test_deterministic_replay_same_seed():
    a, b = DigitalTwin(), DigitalTwin()
    ea = a.apply_attack(SCENARIOS["ransomware_activity"], seed=7)
    eb = b.apply_attack(SCENARIOS["ransomware_activity"], seed=7)
    assert ea == eb and a.snapshot()["status"] == b.snapshot()["status"]


def test_verification_catches_failed_defense():
    from app.verification.verifier import verify
    import time
    base = DigitalTwin()
    attacked = DigitalTwin(); attacked.apply_attack(SCENARIOS["ransomware_activity"], seed=42)
    baseline_result = attacked.attempt_attack_objective(SCENARIOS["ransomware_activity"])
    # no defense applied -> verification must FAIL
    res = verify(SCENARIOS["ransomware_activity"], base, attacked, baseline_result, time.monotonic(), time.monotonic(), None)
    assert res.outcome == "FAIL"


@pytest.mark.asyncio
async def test_full_experiment_all_scenarios():
    from app.db import SessionLocal
    from app import models
    for sid in SCENARIOS:
        c = client.post("/api/experiments", json={"scenario_id": sid, "seed": 42})
        assert c.status_code == 201, c.text
        rid = c.json()["id"]
        await run_experiment(rid)
        r = client.get(f"/api/experiments/{rid}/results")
        data = r.json()
        assert data["run"]["state"] == "COMPLETED", data
        assert data["verification"]["outcome"] == "PASS", data
        assert data["verification"]["metrics"]["defense_effectiveness_pct"] == 100.0
        ev = client.get(f"/api/experiments/{rid}/evidence").json()
        assert len(ev) >= 3
        # evidence refs point to stored rows
        db = SessionLocal()
        assert db.query(models.EvidenceRecord).filter_by(run_id=rid).count() == len(ev)
        db.close()


def test_provider_unavailable_is_honest():
    r = client.get("/api/models/status").json()
    assert "mode" in r and r["api_key_exposed"] is False
    if not r["configured"]:
        assert r["mode"] == "offline"


def test_api_validation_and_health():
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.post("/api/experiments", json={"scenario_id": "nope"}).status_code == 422
    assert client.get("/api/experiments/does-not-exist").status_code == 404
    assert client.get("/api/twin").status_code == 200


@pytest.mark.asyncio
async def test_live_proposal_retries_with_policy_feedback(monkeypatch):
    """Regression: live model first proposed block_connection without params (rejected),
    then corrected after policy feedback. Verified live on 2026-10-26."""
    from app.agents import agents
    from app.schemas import IncidentHypothesis

    calls = {"n": 0}

    async def fake_chat(system, user, run_id=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"actions": [{"action_type": "block_connection", "asset_id": "employee-workstation", "params": {}}],
                    "justification": "block it", "confidence": 0.5}, {}
        assert "REJECTED by policy" in user
        return {"actions": [{"action_type": "isolate_asset", "asset_id": "employee-workstation", "params": {}}],
                "justification": "isolate source", "confidence": 0.9}, {}

    monkeypatch.setattr(agents.meta_client, "chat_json", fake_chat)
    hyp = IncidentHypothesis(hypothesis="synthetic ransomware", affected_assets=["employee-workstation"], confidence=0.8)
    p = await agents.propose_defense(SCENARIOS["ransomware_activity"], hyp, "test-run", twin=DigitalTwin())
    assert calls["n"] == 2 and p.mode == "live"
    assert p.actions[0].action_type == "isolate_asset"


@pytest.mark.asyncio
async def test_markdown_report_and_usage():
    c = client.post("/api/experiments", json={"scenario_id": "data_exfiltration", "seed": 42})
    rid = c.json()["id"]
    await run_experiment(rid)
    md = client.get(f"/api/experiments/{rid}/report/markdown")
    assert md.status_code == 200 and "text/markdown" in md.headers["content-type"]
    assert "# CYBERGENESIS Experiment Report" in md.text and "Data Exfiltration" in md.text
    assert "Outcome: PASS" in md.text and "APPROVED" in md.text
    res = client.get(f"/api/experiments/{rid}/results").json()
    assert "usage" in res and res["usage"]["calls"] >= 0  # 0 in offline tests, >0 live


def test_manual_action_policy_gate():
    client.post("/api/twin/reset")
    bad = client.post("/api/twin/action", json={"action_type": "run_shell", "asset_id": "employee-workstation", "params": {}})
    assert bad.status_code == 403
    ok = client.post("/api/twin/action", json={"action_type": "isolate_asset", "asset_id": "employee-workstation", "params": {}})
    assert ok.status_code == 200
    client.post("/api/twin/reset")
