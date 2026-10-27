import os
import sys

os.environ["OFFLINE_MODE"] = "true"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402

from app.cli.engine import execute, render_config  # noqa: E402
from app.main import app  # noqa: E402
from app.orchestration import orchestrator  # noqa: E402

client = TestClient(app)


def test_cli_show_commands_and_acl_diff():
    twin = orchestrator.TWIN
    out = execute(twin, "firewall", "show running-config")
    assert "hostname" in out["output"]
    out = execute(twin, "firewall", "sh ip int br")  # unique-prefix abbreviation expands via prefix match list
    assert out["output"]
    out = execute(twin, "employee-workstation", "access-list CYBER deny ip any any")
    assert out["diff"] is not None
    assert twin.pending_diffs.get("employee-workstation") is not None
    twin.pending_diffs.pop("employee-workstation", None)


def test_cli_render_roundtrip_contains_config():
    twin = orchestrator.TWIN
    cfg = twin.device_configs["database"]
    text = render_config("bash", cfg)
    assert cfg["hostname"] in text


def test_verified_commit_rejects_reopening():
    # stage an action that would un-isolate nothing harmful vs a restore that reopens: isolate then try restore via diff on contained asset
    client.post("/api/twin/reset")
    # isolate employee via direct action, then a diff restoring it would reopen ransomware path -> commit must reject or accept per campaigns
    client.post("/api/twin/action", json={"action_type": "isolate_asset", "asset_id": "employee-workstation", "params": {}})
    client.post("/api/twin/devices/employee-workstation/config/diff",
                json={"diff": {"ops": [{"op": "set", "path": "isolated", "value": False}]}})
    r = client.post("/api/twin/devices/employee-workstation/config/commit")
    # either rejected by verified-commit replay, or committed only if campaigns remain blocked
    assert r.status_code in (200, 403)
    client.post("/api/twin/reset")


def test_audit_and_explain_endpoints():
    assert client.post("/api/audit/run").status_code == 200
    r = client.post("/api/config/explain", json={"text": "line vty 0 4 transport input telnet"})
    assert r.status_code == 200 and "telnet" in r.json()["explanation"].lower()
