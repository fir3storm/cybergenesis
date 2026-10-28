"""CISO board briefing: deterministic fact sheet, control mapping, honest AI fallback."""

import os
import sys

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orchestration.orchestrator import run_experiment
from app.simulation.twin import ALLOWED_ACTIONS
from app.verification import briefing as br

client = TestClient(app)


def test_every_allowed_action_has_a_control_mapping():
    assert set(br.CONTROL_MAP) == set(ALLOWED_ACTIONS)
    for csf, _cis in br.CONTROL_MAP.values():
        assert all(c in br.CSF_TITLES for c in csf)


def test_compliance_tags_only_count_successful_actions():
    tags = br.compliance_tags([{"action_type": "enforce_mfa", "asset_id": "idp", "success": True},
                               {"action_type": "apply_patch", "asset_id": "web", "success": False}])
    ids = {t["id"] for t in tags}
    assert "PR.AA-03" in ids and "ID.IM-02" in ids
    assert "PR.PS-02" not in ids  # the failed patch is not evidence


def test_failed_run_is_reported_as_not_stopped():
    facts = {"scenario": "Ransomware", "target": "file-server", "outcome": "FAIL", "run_state": "COMPLETED",
             "risk_before_pct": 58.0, "risk_after_pct": 58.0, "risk_after_ci95": None, "actions": [],
             "users_affected": 0, "legit_paths_disrupted": 0, "policy_rejections": []}
    n = br.deterministic_narrative(facts)
    assert "NOT stopped" in n["headline"] and n["mode"] == "offline"
    assert any("did not close" in a for a in n["board_asks"])


@pytest.mark.asyncio
async def test_briefing_endpoint_and_offline_narration_label():
    rid = client.post("/api/experiments", json={"scenario_id": "ransomware_activity", "seed": 42}).json()["id"]
    await run_experiment(rid)
    b = client.get(f"/api/experiments/{rid}/briefing").json()
    assert b["facts"]["run_id"] == rid and b["facts"]["outcome"] in ("PASS", "FAIL")
    assert b["narrative"]["mode"] == "offline" and b["compliance"]
    # narrate=true under OFFLINE_MODE must fall back honestly, never pretend to be live
    n = client.get(f"/api/experiments/{rid}/briefing?narrate=true").json()["narrative"]
    assert n["mode"] == "offline" and n["fallback_reason"]
    md = client.get(f"/api/experiments/{rid}/briefing/markdown").text
    assert md.startswith("# Board briefing") and "NIST CSF 2.0" in md and "not an audit opinion" in md
    assert client.get("/api/experiments/missing/briefing").status_code == 404


@pytest.mark.asyncio
async def test_live_narrative_is_schema_checked(monkeypatch):
    from app.integrations.meta_client import meta_client

    async def fake(system, user, run_id=None, tier=None):
        return {"headline": "x" * 500, "summary": "s"}, {}
    monkeypatch.setattr(meta_client, "chat_json", fake)
    facts = {"scenario": "S", "target": "t", "outcome": "PASS", "run_state": "COMPLETED", "risk_before_pct": 1,
             "risk_after_pct": 0, "risk_after_ci95": None, "actions": ["a"], "users_affected": 0,
             "legit_paths_disrupted": 0, "policy_rejections": []}
    n = await br.ai_narrative(facts, "r1")
    assert n["mode"] == "offline" and "schema" in n["fallback_reason"]

    async def good(system, user, run_id=None, tier=None):
        return {"headline": "Stopped.", "summary": "All good.", "board_asks": ["Re-run quarterly"]}, {}
    monkeypatch.setattr(meta_client, "chat_json", good)
    n = await br.ai_narrative(facts, "r2")
    assert n["mode"] == "live" and n["headline"] == "Stopped."
