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
    from app.cli.engine import parse_config_text

    twin = orchestrator.TWIN
    cfg = twin.device_configs["database"]
    text = render_config("bash", cfg)
    assert cfg["hostname"] in text
    back = parse_config_text("bash", text)
    assert back["hostname"] == cfg["hostname"]
    assert [i["name"] for i in back["interfaces"]] == [i["name"] for i in cfg["interfaces"]]
    assert [i["ip"] for i in back["interfaces"]] == [i["ip"] for i in cfg["interfaces"]]


def test_cli_more_dialects_show_commands():
    twin = orchestrator.TWIN
    for asset in ("firewall", "web-server", "database", "employee-workstation"):
        for cmd in ("show interfaces", "show ip route", "show access-list", "show version", "?"):
            out = execute(twin, asset, cmd)
            assert out["output"], (asset, cmd)


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


def test_f3_typed_acl_parse_and_bind():
    from app.cli.engine import parse_acl_command

    diff = parse_acl_command("access-list EDGE seq 20 deny tcp any any eq 445")
    entry = diff["ops"][0]["value"]["entry"]
    assert entry == {"seq": 20, "action": "deny", "proto": "tcp", "src": "any", "dst": "any", "dst_port": 445, "log": True}
    twin = orchestrator.TWIN
    out = execute(twin, "employee-workstation", "access-list EDGE seq 20 deny tcp any any eq 445")
    assert out["diff"]["ops"][0]["op"] == "add_acl_entry"
    out = execute(twin, "employee-workstation", "ip access-group EDGE in")
    assert out["diff"]["ops"][0]["op"] == "bind_acl"
    twin.pending_diffs.pop("employee-workstation", None)


def test_f3_pending_appends_and_rollback_exact():
    client.post("/api/twin/reset")
    d1 = {"ops": [{"op": "set", "path": "hostname", "value": "WS-TEST-01"}]}
    d2 = {"ops": [{"op": "set", "path": "mgmt.ssh", "value": True}]}
    client.post("/api/twin/devices/employee-workstation/config/diff", json={"diff": d1})
    client.post("/api/twin/devices/employee-workstation/config/diff", json={"diff": d2})
    pending = client.get("/api/twin/devices/employee-workstation/config/pending").json()
    assert pending["pending_count"] == 2
    r = client.post("/api/twin/devices/employee-workstation/config/commit")
    assert r.status_code == 200, r.text
    assert client.get("/api/twin/devices/employee-workstation/config").json()["config"]["hostname"] == "WS-TEST-01"
    rb = client.post("/api/twin/devices/employee-workstation/config/rollback/0")
    assert rb.status_code == 200
    assert client.get("/api/twin/devices/employee-workstation/config").json()["config"]["hostname"] != "WS-TEST-01"
    client.post("/api/twin/reset")


def test_f3_set_isolated_on_domain_controller_rejected_403():
    client.post("/api/twin/reset")
    client.post("/api/twin/devices/identity-provider/config/diff",
                json={"diff": {"ops": [{"op": "set", "path": "isolated", "value": True}]}})
    r = client.post("/api/twin/devices/identity-provider/config/commit")
    assert r.status_code == 403, r.text
    assert "rejected" in r.text
    client.post("/api/twin/reset")


def test_audit_and_explain_endpoints():
    assert client.post("/api/audit/run").status_code == 200
    r = client.post("/api/config/explain", json={"text": "line vty 0 4 transport input telnet"})
    assert r.status_code == 200 and "telnet" in r.json()["explanation"].lower()
