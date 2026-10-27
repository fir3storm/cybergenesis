"""F8e counterfactual fork + F8f one-time mobile approval."""

import asyncio
import os
import sys

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orchestration import orchestrator
from app.orchestration.orchestrator import run_experiment

client = TestClient(app)


async def _finished_run(scenario_id: str = "ransomware_activity") -> str:
    rid = client.post("/api/experiments", json={"scenario_id": scenario_id, "seed": 42}).json()["id"]
    await run_experiment(rid)
    return rid


@pytest.mark.asyncio
async def test_fork_with_alternative_candidate_is_recorded_and_original_unchanged():
    rid = await _finished_run()
    before = client.get(f"/api/experiments/{rid}/results").json()
    cands = before["run"]["metrics"]["candidates"]
    assert len(cands) >= 2
    chosen_label = before["run"]["metrics"].get("ai_final_choice", {}).get("chosen_label")
    alt = next(i for i, c in enumerate(cands) if c["label"] != chosen_label)

    r = client.post(f"/api/experiments/{rid}/fork", json={"choose_candidate": alt})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parent_run_id"] == rid and body["candidate"] == cands[alt]["label"]
    assert body["fork"]["outcome"] in ("PASS", "FAIL")
    assert set(body["delta"]) >= {"verdict_changed"}

    fork = client.get(f"/api/experiments/{body['fork_id']}/results").json()
    assert fork["run"]["state"] == "COMPLETED"
    assert fork["verification"]["metrics"]["forked_from"] == rid
    assert fork["verification"]["metrics"]["counterfactual_candidate"] == cands[alt]["label"]
    types = [e["event_type"] for e in client.get(f"/api/experiments/{body['fork_id']}/events").json()]
    assert types[0] == "fork" and "verification" in types
    # a different candidate gives a different, recorded outcome
    assert body["fork"]["actions"] != body["original"]["actions"] or body["fork"] != body["original"]
    assert body["original_twin"] and body["fork_twin"]
    assert body["original_twin"] != body["fork_twin"] or body["fork"]["actions"] != body["original"]["actions"]
    assert body["original_timeline"] and body["fork_timeline"][0]["event_type"] == "fork"
    assert "rounds" in body["delta"] or "disrupted" in body["delta"]

    after = client.get(f"/api/experiments/{rid}/results").json()
    assert after["verification"] == before["verification"]
    assert after["executions"] == before["executions"]

    again = client.post(f"/api/experiments/{rid}/fork", json={"choose_candidate": alt}).json()
    assert again["fork"] == body["fork"]  # deterministic, no LLM


@pytest.mark.asyncio
async def test_fork_rejects_bad_candidate_and_unknown_run():
    rid = await _finished_run()
    assert client.post(f"/api/experiments/{rid}/fork", json={"choose_candidate": 99}).status_code == 422
    assert client.post(f"/api/experiments/{rid}/fork", json={"choose_candidate": "nope"}).status_code == 422
    assert client.post("/api/experiments/missing/fork", json={"choose_candidate": 0}).status_code == 404


async def _run_to_approval(monkeypatch) -> tuple[str, asyncio.Task]:
    from app.core.config import settings

    monkeypatch.setattr(settings, "human_approval_enabled", True)
    monkeypatch.setattr(settings, "auto_approve", False)
    monkeypatch.setattr(settings, "approval_timeout_seconds", 20)
    rid = client.post("/api/experiments", json={"scenario_id": "ransomware_activity", "seed": 42}).json()["id"]
    task = asyncio.create_task(run_experiment(rid))
    for _ in range(100):
        await asyncio.sleep(0.1)
        if orchestrator.pending_approval(rid):
            break
    assert orchestrator.pending_approval(rid)
    return rid, task


@pytest.mark.asyncio
async def test_mobile_approval_token_is_single_use(monkeypatch):
    rid, task = await _run_to_approval(monkeypatch)
    info = client.get(f"/api/experiments/{rid}/approval").json()
    assert info["pending"] and "/m/approve/" in info["mobile_url"]
    token = info["mobile_url"].split("t=")[1]

    page = client.get(f"/m/approve/{rid}?t={token}")
    assert page.status_code == 200 and "Approve defense" in page.text

    assert client.post(f"/api/m/approve/{rid}", json={"t": "wrong", "approved": True}).status_code == 403
    assert client.post(f"/api/m/approve/{rid}", json={"t": token, "approved": True}).status_code == 200
    assert client.post(f"/api/m/approve/{rid}", json={"t": token, "approved": True}).status_code == 403  # reused
    await asyncio.wait_for(task, timeout=30)
    types = [e["event_type"] for e in client.get(f"/api/experiments/{rid}/events").json()]
    assert "approval_mobile" in types
    assert client.get(f"/api/experiments/{rid}/approval").json() == {"pending": False}


@pytest.mark.asyncio
async def test_mobile_expired_token_gets_403(monkeypatch):
    rid, task = await _run_to_approval(monkeypatch)
    try:
        token = client.get(f"/api/experiments/{rid}/approval").json()["mobile_url"].split("t=")[1]
        # expire the approval window: the token dies with it
        orchestrator._approvals[rid]["expires_at"] = 0
        assert client.get(f"/api/experiments/{rid}/approval").json() == {"pending": False}
        assert client.get(f"/m/approve/{rid}?t={token}").status_code == 403
        assert client.get(f"/m/approve/{rid}?t=wrong").status_code == 403
        assert client.post(f"/api/m/approve/{rid}", json={"t": token, "approved": True}).status_code == 403
    finally:
        # unblock the waiter so the run finishes (auto-deny path)
        orchestrator.resolve_approval(rid, False)
        await asyncio.wait_for(task, timeout=30)


@pytest.mark.asyncio
async def test_mobile_token_dead_after_ui_decision(monkeypatch):
    rid, task = await _run_to_approval(monkeypatch)
    token = client.get(f"/api/experiments/{rid}/approval").json()["mobile_url"].split("t=")[1]
    assert client.post(f"/api/experiments/{rid}/deny").status_code == 200
    await asyncio.wait_for(task, timeout=30)
    assert client.post(f"/api/m/approve/{rid}", json={"t": token, "approved": True}).status_code == 403
