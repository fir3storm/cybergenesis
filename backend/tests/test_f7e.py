import os
import sys

os.environ["OFFLINE_MODE"] = "true"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.orchestration import orchestrator  # noqa: E402
from app.simulation.scenarios import SCENARIOS  # noqa: E402

client = TestClient(app)


def test_scenario_process_per_compromised_windows_asset():
    twin = orchestrator.TWIN
    twin.reset()
    twin.apply_attack(SCENARIOS["ransomware_activity"], seed=42)
    procs = twin.processes.get("employee-workstation", [])
    assert any(p["name"] == "synthetic-locker.exe" and p["suspicious"] for p in procs)
    twin.apply_action("kill_process", "employee-workstation", {})
    assert not any(p["suspicious"] for p in twin.processes.get("employee-workstation", []))
    twin.reset()


def test_bind_unknown_interface_422_and_finalize_all_pending():
    client.post("/api/twin/reset")
    r = client.post("/api/twin/devices/employee-workstation/config/diff",
                    json={"diff": {"ops": [{"op": "bind_acl", "value": {"name": "X", "direction": "in", "interface": "eth99"}}]}})
    assert r.status_code == 422
    d = {"ops": [{"op": "set", "path": "hostname", "value": "WS-F7E"}]}
    client.post("/api/twin/devices/employee-workstation/config/diff", json={"diff": d})
    client.post("/api/twin/devices/employee-workstation/config/diff", json={"diff": d})
    assert client.post("/api/twin/devices/employee-workstation/config/commit").status_code == 200
    from app.db import SessionLocal
    from app import models

    db = SessionLocal()
    pending = db.query(models.ConfigCommit).filter_by(device_id="employee-workstation", status="pending").count()
    db.close()
    assert pending == 0
    client.post("/api/twin/reset")
