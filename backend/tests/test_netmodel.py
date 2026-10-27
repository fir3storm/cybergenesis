import os
import sys

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
os.environ["HUMAN_APPROVAL_ENABLED"] = "false"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.netmodel.compiler import compile_twin, content_hash  # noqa: E402
from app.netmodel.config import Acl, AclEntry, DeviceConfig, FwPolicy, Interface, Service  # noqa: E402
from app.orchestration.orchestrator import run_experiment  # noqa: E402
from app.simulation.scenarios import SCENARIOS  # noqa: E402

client = TestClient(app)


def cfg(host, ifaces, **kw):
    return DeviceConfig(hostname=host, interfaces=[Interface(name=n, peer=p, ip=ip) for n, p, ip in ifaces], **kw)


def base():
    a = cfg("A", [("eth0", "fw", "10.0.0.1")], services=[Service(name="https", port=443)])
    fw = cfg("FW", [("eth0", "a", "10.0.0.2"), ("eth1", "b", "10.0.1.2")])
    b = cfg("B", [("eth0", "fw", "10.0.1.3")], services=[Service(name="https", port=443)], weaknesses=["rdp_exposed"])
    cables = [{"a": {"device": "a", "port": "eth0"}, "b": {"device": "fw", "port": "eth0"}},
              {"a": {"device": "fw", "port": "eth1"}, "b": {"device": "b", "port": "eth0"}}]
    return {"a": a, "fw": fw, "b": b}, cables, {"a": "endpoint", "fw": "firewall", "b": "server"}


def test_deny_acl_removes_path():
    configs, cables, cats = base()
    assert compile_twin(configs, cables, cats).explain("a", "b")["reachable"]
    configs["a"].acls = [Acl(name="OUT", entries=[AclEntry(action="deny", dst="any")])]
    configs["a"].interfaces[0].acl_out = "OUT"
    assert not compile_twin(configs, cables, cats).explain("a", "b")["reachable"]


def test_interface_shutdown_removes_link():
    configs, cables, cats = base()
    configs["fw"].interfaces[1].enabled = False
    assert not compile_twin(configs, cables, cats).explain("a", "b")["reachable"]


def test_firewall_policy_opens_exact_service():
    configs, cables, cats = base()
    configs["fw"].fw_policies = [FwPolicy(id=1, name="deny-all", action="deny", service="any")]
    assert not compile_twin(configs, cables, cats).explain("a", "b")["reachable"]
    configs["fw"].fw_policies = [FwPolicy(id=1, name="allow-https", action="allow", service="https"),
                                 FwPolicy(id=2, name="deny-all", action="deny", service="any")]
    assert compile_twin(configs, cables, cats).explain("a", "b")["reachable"]


def test_host_firewall_blocks_service():
    configs, cables, cats = base()
    configs["b"].host_firewall.rules = [{"action": "deny", "port": 443, "src": "any"}]
    assert not compile_twin(configs, cables, cats).explain("a", "b")["reachable"]


def test_patch_removes_weakness_traversal_and_session_allows():
    configs, cables, cats = base()
    configs["b"].weaknesses = []
    assert not compile_twin(configs, cables, cats).explain("a", "b")["reachable"]
    from app.netmodel.config import Session, User

    configs["b"].users = [User(name="admin-01", sessions=[Session(id="s1", active=True, compromised=True)])]
    assert compile_twin(configs, cables, cats).explain("a", "b")["reachable"]


def test_f1_ingress_acl_removes_and_restores_scenario_path():
    from app.simulation.twin import DigitalTwin

    t = DigitalTwin()
    assert t.find_path("employee-workstation", "file-server") is not None
    cfg = t.device_configs["file-server"]
    direct = next(i for i in cfg["interfaces"] if i.get("peer") == "employee-workstation")
    direct["acl_in"] = "IN1"
    cfg["acls"] = [{"name": "IN1", "entries": [
        {"seq": 10, "action": "deny", "proto": "ip", "src": "any", "dst": "any", "dst_port": None, "log": True}]}]
    path = t.find_path("employee-workstation", "file-server")
    assert path != ["employee-workstation", "file-server"], "ingress ACL must remove the direct scenario path"
    for i in cfg["interfaces"]:  # bind on every ingress interface of the target: no reroute remains
        i["acl_in"] = "IN1"
    assert t.find_path("employee-workstation", "file-server") is None
    for i in cfg["interfaces"]:
        i["acl_in"] = None
    cfg["acls"] = []
    assert t.find_path("employee-workstation", "file-server") is not None, "removing the ACL must restore the path"


def test_determinism_hash():
    configs, cables, _ = base()
    assert content_hash(configs, cables) == content_hash(configs, cables)


@pytest.mark.asyncio
async def test_all_scenarios_still_pass_and_config_api():
    for sid in SCENARIOS:
        rid = client.post("/api/experiments", json={"scenario_id": sid, "seed": 42}).json()["id"]
        await run_experiment(rid)
        res = client.get(f"/api/experiments/{rid}/results").json()
        assert res["verification"]["outcome"] == "PASS", (sid, res)
    client.post("/api/twins/builtin/activate")
    cfg_r = client.get("/api/twin/devices/employee-workstation/config")
    assert cfg_r.status_code == 200 and cfg_r.json()["config"]["hostname"]
    ex = client.get("/api/twin/compile/explain", params={"src": "internet", "dst": "database"})
    assert ex.status_code == 200 and "hops" in ex.json()
    twin = client.get("/api/twin").json()
    assert "devices" in twin and len(twin["devices"]) == 10
