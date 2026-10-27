import os
import sys

os.environ["SIM_STEP_DELAY_MS"] = "0"
os.environ["OFFLINE_MODE"] = "true"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orchestration import orchestrator
from app.orchestration.orchestrator import run_experiment

client = TestClient(app)


def test_tests_use_isolated_database_url():
    from app.core.config import settings

    assert "cybergenesis-test.db" in settings.database_url
    assert not settings.database_url.rstrip("/").endswith("./cybergenesis.db")


@pytest.mark.asyncio
async def test_operator_rejection_completes_with_verification_fail(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "human_approval_enabled", True)
    monkeypatch.setattr(settings, "auto_approve", False)
    monkeypatch.setattr(settings, "approval_timeout_seconds", 20)
    rid = client.post("/api/experiments", json={"scenario_id": "ransomware_activity", "seed": 42}).json()["id"]
    task = asyncio.create_task(run_experiment(rid))
    for _ in range(100):
        await asyncio.sleep(0.1)
        if rid in orchestrator._approvals:
            break
    assert rid in orchestrator._approvals
    assert client.post(f"/api/experiments/{rid}/deny").status_code == 200
    await asyncio.wait_for(task, timeout=30)
    res = client.get(f"/api/experiments/{rid}/results").json()
    assert res["run"]["state"] == "COMPLETED", res
    assert res["run"]["error"] is None
    assert res["verification"]["outcome"] == "FAIL", res
    metrics = res["verification"]["metrics"]
    assert metrics["time_to_contain_s"] is None
    assert "defense rejected by operator" in metrics["failure_reason"]
    types = [e["event_type"] for e in client.get(f"/api/experiments/{rid}/events").json()]
    assert "defense_rejected" in types and "verification" in types


@pytest.mark.asyncio
async def test_run_timeout_watchdog_fails_run_honestly(monkeypatch):
    from app.agents import agents
    from app.core.config import settings

    async def hang_final_choice(candidates, scenario, run_id):
        await asyncio.sleep(30)
        raise AssertionError("watchdog should have cancelled before this returns")

    monkeypatch.setattr(agents, "final_choice", hang_final_choice)
    monkeypatch.setattr(settings, "run_timeout_s", 5)
    rid = client.post("/api/experiments", json={"scenario_id": "ransomware_activity", "seed": 42}).json()["id"]
    await asyncio.wait_for(run_experiment(rid), timeout=20)
    res = client.get(f"/api/experiments/{rid}/results").json()
    assert res["run"]["state"] == "FAILED", res
    assert res["run"]["error"] == "run_timeout"
    types = [e["event_type"] for e in client.get(f"/api/experiments/{rid}/events").json()]
    assert "run_timeout" in types


def test_startup_sweep_marks_stale_run_failed():
    from app import models
    from app.db import SessionLocal

    db = SessionLocal()
    stale = models.SimulationRun(scenario_id="ransomware_activity", seed=42, state="VERIFYING")
    db.add(stale); db.commit(); db.refresh(stale)
    stale_id = stale.id
    db.close()
    with TestClient(app):
        pass  # entering the client runs the lifespan startup sweep
    db = SessionLocal()
    row = db.get(models.SimulationRun, stale_id)
    db.close()
    assert row.state == "FAILED"
    assert row.error == "ABORTED: backend restarted"
    assert row.ended_at is not None


@pytest.mark.asyncio
async def test_run_mode_mixed_when_decisions_have_mixed_modes(monkeypatch):
    from app.agents import agents
    from app.core.config import settings
    from app.integrations.meta_client import meta_client

    async def fake_chat(system, user, run_id=None):
        if "Incident Investigator" in system:
            return ({"hypothesis": "live investigator hypothesis", "affected_assets": ["employee-workstation"],
                     "threat_level": "high", "confirmed": [], "speculation": [], "confidence": 0.9}, {})
        raise RuntimeError("mock provider unavailable for this agent")

    monkeypatch.setattr(settings, "offline_mode", False)
    monkeypatch.setattr(meta_client, "key", "test-key")
    monkeypatch.setattr(agents.meta_client, "chat_json", fake_chat)
    rid = client.post("/api/experiments", json={"scenario_id": "ransomware_activity", "seed": 42}).json()["id"]
    await run_experiment(rid)
    res = client.get(f"/api/experiments/{rid}/results").json()
    assert res["run"]["state"] == "COMPLETED", res
    modes = {d["agent"]: d["mode"] for d in res["decisions"]}
    assert modes["incident_investigator"] == "live", modes
    assert "offline" in modes.values(), modes
    assert res["run"]["mode"] == "mixed", res["run"]


@pytest.mark.asyncio
async def test_advisory_budget_exhausted_while_backbone_still_works(monkeypatch):
    from app.agents.framework import io as fw_io
    from app.agents.framework.adapters import build_agent
    from app.agents.framework.base import AgentContext
    from app.core.config import settings
    from app.integrations import meta_client as mc_mod
    from app.integrations.meta_client import ProviderUnavailable, meta_client
    from app.simulation.twin import DigitalTwin

    run_id = "f8a-budget-run"
    captured = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": '{"ok": true}'}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, headers=None, json=None):
            captured["body"] = json
            return _Resp()

    monkeypatch.setattr(settings, "max_tokens_per_run", 100)
    monkeypatch.setattr(settings, "offline_mode", False)
    monkeypatch.setattr(meta_client, "key", "test-key")
    monkeypatch.setattr(mc_mod.httpx, "AsyncClient", _FakeClient)
    meta_client._usage[run_id] = [{"prompt_tokens": 50, "completion_tokens": 0}]
    try:
        assert meta_client.budget_limit("advisory") == 40
        assert meta_client.budget_limit("backbone") == 100
        # advisory (default tier) is capped at 40% so the backbone reserve survives
        with pytest.raises(ProviderUnavailable, match="token budget") as excinfo:
            await meta_client.chat_json("sys", "user", run_id=run_id)
        assert "tier=advisory" in str(excinfo.value)
        # backbone may spend past the advisory cap, up to the full budget
        data, _rec = await meta_client.chat_json("sys", "user", run_id=run_id, tier="backbone")
        assert data == {"ok": True}
        assert captured["body"]["max_tokens"] <= 900
        # an advisory framework agent falls back offline with the budget reason
        result = await build_agent("incident_commander").run(
            AgentContext(run_id=run_id, twin=DigitalTwin(), scenario={}), fw_io.TextIn(text="ransomware"))
        assert result.mode == "offline"
        assert "token budget" in (result.fallback_reason or "") and "tier=advisory" in (result.fallback_reason or "")
    finally:
        meta_client._usage.pop(run_id, None)


def test_demo_reset_returns_builtin_twin_and_clears_approvals():
    client.post("/api/twin/action", json={"action_type": "isolate_asset", "asset_id": "employee-workstation", "params": {}})
    orchestrator._approvals["demo-dummy"] = {"event": asyncio.Event(), "approved": None}
    r = client.post("/api/demo/reset")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reset"] is True and body["cleared_approvals"] >= 1
    assert len(body["twin"]["assets"]) == 10
    assert "demo-dummy" not in orchestrator._approvals
    assert len(client.get("/api/twin").json()["assets"]) == 10
