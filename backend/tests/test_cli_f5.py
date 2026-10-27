import os
import sys

os.environ["OFFLINE_MODE"] = "true"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app.cli.engine import complete, execute  # noqa: E402
from app.main import app  # noqa: E402
from app.orchestration import orchestrator  # noqa: E402

client = TestClient(app)


def test_modes_and_interface_shutdown():
    twin = orchestrator.TWIN
    client.post("/api/twin/reset")
    out = execute(twin, "employee-workstation", "configure terminal")
    assert out["mode"] == "config"
    out = execute(twin, "employee-workstation", "interface eth0")
    assert out["mode"] == "interface" and out["interface"] == "eth0"
    out = execute(twin, "employee-workstation", "shutdown")
    assert out["diff"]["ops"][0]["path"] == "interfaces.eth0.enabled"
    twin.pending_diffs.pop("employee-workstation", None)
    out = execute(twin, "employee-workstation", "end")
    assert out["mode"] == "exec"


def test_context_help_completion_and_errors():
    twin = orchestrator.TWIN
    assert "show" in execute(twin, "firewall", "?")["output"]
    comps = complete(twin, "firewall", "show")
    assert any("configuration" in c for c in comps)
    out = execute(twin, "firewall", "bogus-command-xyz")
    assert out["output"]  # vendor-style error marker, dialect-specific


def test_os_endpoint_and_kill_removes_process():
    client.post("/api/twin/reset")
    twin = orchestrator.TWIN
    from app.simulation.scenarios import SCENARIOS

    twin.apply_attack(SCENARIOS["ransomware_activity"], seed=42)
    st = client.get("/api/twin/devices/employee-workstation/os")
    assert st.status_code == 200
    body = st.json()
    assert any(p["suspicious"] for p in body["processes"])
    assert any(f.endswith(".locked") for f in body["files"])
    r = client.post("/api/twin/action", json={"action_type": "kill_process", "asset_id": "employee-workstation", "params": {}})
    assert r.status_code == 200
    body2 = client.get("/api/twin/devices/employee-workstation/os").json()
    assert not any(p["suspicious"] for p in body2["processes"])
    client.post("/api/twin/reset")
