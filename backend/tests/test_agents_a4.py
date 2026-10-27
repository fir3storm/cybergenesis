import asyncio
import os
import sys

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient

from app.agents.eval import run_eval
from app.main import app

client = TestClient(app)


def test_eval_scorecards_small():
    result = asyncio.run(run_eval(3, 7, "offline"))
    assert result["n"] == 3
    for aid in ("incident_investigator", "defense_strategist", "red_team_planner", "config_auditor",
                "identity_guardian", "deception_engineer", "config_engineer", "forensic_reporter"):
        assert aid in result["agents"], aid
    assert 0 <= result["agents"]["incident_investigator"]["precision"] <= 1
    assert len(result["calibration"]["incident_investigator"]) == 5


def test_eval_endpoints():
    r = client.post("/api/agents/eval/run", json={"n": 2, "seed": 7, "mode": "offline"})
    assert r.status_code == 202
    rid = r.json()["run_id"]
    import time

    for _ in range(120):
        st = client.get(f"/api/agents/eval/run/{rid}").json()
        if st["state"] in ("COMPLETED", "FAILED"):
            break
        time.sleep(0.5)
    assert st["state"] == "COMPLETED"
    latest = client.get("/api/agents/eval/latest").json()
    assert latest["available"] and latest["result"]["n"] == 2
