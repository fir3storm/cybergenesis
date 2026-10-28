"""Bring-your-own-network import: running-configs, CSV inventory, JSON -> custom twin."""

import os
import sys

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.simulation.importers import ImportError_, parse_csv_inventory, parse_running_configs
from app.simulation.twin import DigitalTwin

client = TestClient(app)

CONFIGS = """hostname edge-fw
interface Gi0/0
 description uplink to core-rtr
 ip address 10.0.0.1 255.255.255.252
line vty 0 4
 transport input telnet
access-list OUTSIDE permit ip any any
hostname core-rtr
interface Gi0/1
 ip address 10.0.0.2/30
interface Gi0/2
 ip address 10.1.0.1/24
snmp-server community public RO
hostname db-01
interface eth0
 ip address 10.1.0.20/24
username dba role admin mfa off
"""

CSV = """id,name,asset_type,zone,posture,vulnerabilities,connects_to
internet,Internet,gateway,external,0.4,exposed_surface,web
web,Web Server,web_server,dmz,0.6,exposed_service,db
db,Database,database,data,0.9,,
"""


def test_running_configs_infer_devices_links_and_weaknesses():
    data = parse_running_configs(CONFIGS, "cisco_ios")
    by_id = {a["id"]: a for a in data["assets"]}
    assert set(by_id) == {"edge-fw", "core-rtr", "db-01"}
    assert by_id["edge-fw"]["asset_type"] == "firewall"
    assert by_id["db-01"]["asset_type"] == "database"
    assert {"telnet_enabled", "permissive_default_rule"} <= set(by_id["edge-fw"]["vulnerabilities"])
    assert "default_snmp_community" in by_id["core-rtr"]["vulnerabilities"]
    assert "no_mfa_admin" in by_id["db-01"]["vulnerabilities"]
    twin = DigitalTwin.from_dict(data["assets"], data["connections"])
    # shared /30 links fw<->rtr, shared /24 links rtr<->db: a real attack path exists
    assert nx.has_path(twin.graph, "edge-fw", "db-01")
    assert not any(c["source"] == "edge-fw" and c["target"] == "db-01" for c in data["connections"])


def test_running_configs_reject_empty_and_garbage():
    with pytest.raises(ImportError_):
        parse_running_configs("   ", "cisco_ios")
    with pytest.raises(ImportError_):
        parse_running_configs("this is not a config", "cisco_ios")


def test_csv_inventory_builds_directed_topology():
    data = parse_csv_inventory(CSV)
    assert [a["id"] for a in data["assets"]] == ["internet", "web", "db"]
    assert {(c["source"], c["target"]) for c in data["connections"]} == {("internet", "web"), ("web", "db")}
    assert len({tuple(a["pos"]) for a in data["assets"]}) == 3  # laid out, not stacked at the origin


@pytest.mark.parametrize("bad, msg", [
    ("name\nx", "'id' column"),
    ("id,asset_type\na,toaster", "unknown asset_type"),
    ("id,posture\na,high", "posture"),
    ("id,connects_to\na,ghost", "unknown asset id"),
])
def test_csv_inventory_errors_are_specific(bad, msg):
    with pytest.raises(ImportError_, match=msg):
        parse_csv_inventory(bad)


def test_import_endpoint_saves_config_twin_with_summary():
    r = client.post("/api/twins/import", json={"text_config": CONFIGS, "dialect": "cisco_ios", "name": "Lab configs"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["summary"]["assets"] == 3 and body["summary"]["links"] == 4
    assert "telnet_enabled" in body["summary"]["weaknesses"]
    listed = {t["id"] for t in client.get("/api/twins/custom").json()}
    assert body["id"] in listed


def test_import_endpoint_csv_and_json():
    r = client.post("/api/twins/import", json={"csv_inventory": CSV})
    assert r.status_code == 201, r.text
    assert r.json()["summary"]["links"] == 2
    j = client.post("/api/twins/import", json={"json_twin": {"assets": r.json()["assets"], "connections": r.json()["connections"]}})
    assert j.status_code == 201, j.text


@pytest.mark.parametrize("payload", [
    {},
    {"csv_inventory": CSV, "text_config": CONFIGS},
    {"csv_inventory": "id,asset_type\na,toaster"},
    {"json_twin": {"assets": [{"id": "a"}]}},
    {"json_twin": {"assets": [{"id": "a", "name": "a", "asset_type": "gateway", "zone": "z"}],
                   "connections": [{"source": "a", "target": "missing"}]}},
])
def test_import_endpoint_bad_input_is_422_not_500(payload):
    assert client.post("/api/twins/import", json=payload).status_code == 422
