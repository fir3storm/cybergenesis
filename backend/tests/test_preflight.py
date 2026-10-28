"""Attack-path regression preflight: safe/regression/improved, clone isolation, CLI codes."""

import itertools
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.simulation.preflight import run_preflight, validate_ops
from app.simulation.twin import DigitalTwin

client = TestClient(app)

SC = [{"id": "lat", "name": "Lat", "source_asset": "web-server", "target_asset": "database",
       "verification_kind": "reachability"}]


def _twin():
    return DigitalTwin.from_dict(
        [{"id": a, "name": a, "asset_type": "workstation", "zone": "internal", "posture": 0.7,
          "pos": [0, 1, 0], "vulnerabilities": ["x"]} for a in ("web-server", "app-server", "relay", "database")],
        [{"source": "web-server", "target": "app-server"}, {"source": "app-server", "target": "database"}])


def test_safe_change_passes():
    r = run_preflight(_twin(), SC, {"ops": [{"op": "set_posture", "asset_id": "app-server", "posture": 0.9}]})
    assert r["verdict"] == "PASS"
    assert r["results"][0]["status"] == "STILL_EXPOSED"


def test_added_link_opens_new_path_fails_with_exact_path():
    r = run_preflight(_twin(), SC, {"ops": [{"op": "add_link", "src": "web-server", "dst": "relay"},
                                            {"op": "add_link", "src": "relay", "dst": "database"}]})
    assert r["verdict"] == "FAIL"
    row = r["results"][0]
    assert row["status"] == "REGRESSION"
    assert ["web-server", "relay", "database"] in row["new_paths"]


def _meshed_twin():
    """web-server -> 4 fully meshed relays -> database: well over MAX_PATHS simple paths."""
    relays = [f"r{i}" for i in range(4)]
    ids = ("web-server", "database", *relays)
    conns = [{"source": "web-server", "target": r} for r in relays]
    conns += [{"source": r, "target": "database"} for r in relays]
    conns += [{"source": a, "target": b} for i, a in enumerate(relays) for b in relays[i + 1:]]
    return DigitalTwin.from_dict(
        [{"id": a, "name": a, "asset_type": "workstation", "zone": "internal", "posture": 0.7,
          "pos": [0, 1, 0], "vulnerabilities": ["x"]} for a in ids], conns)


def test_link_removal_on_many_path_twin_is_not_a_regression():
    # Removing a link can only remove paths; old paths beyond the display cap must not count as new.
    r = run_preflight(_meshed_twin(), SC, [{"op": "remove_link", "src": "web-server", "dst": "r0"}])
    row = r["results"][0]
    assert r["verdict"] == "PASS"
    assert row["status"] == "STILL_EXPOSED" and row["new_paths"] == []


def test_new_path_on_many_path_twin_is_found_and_uses_new_edge():
    twin = _meshed_twin()
    twin_r = run_preflight(twin, SC, [{"op": "add_link", "src": "web-server", "dst": "database"}])
    row = twin_r["results"][0]
    assert twin_r["verdict"] == "FAIL" and row["status"] == "REGRESSION"
    assert ["web-server", "database"] in row["new_paths"]
    assert all(("web-server", "database") in set(itertools.pairwise(p)) for p in row["new_paths"])


def test_builtin_preflight_ignores_last_run_defenses():
    from app.orchestration import orchestrator

    # leave the live twin defended, as a finished demo run does
    orchestrator.TWIN.apply_action("quarantine_vlan", "employee-workstation", {})
    try:
        r = client.post("/api/twins/builtin/preflight",
                        json={"change": [{"op": "set_posture", "asset_id": "app-server", "posture": 0.9}],
                              "scenario_ids": ["ransomware_activity"]}).json()
        row = r["results"][0]
        assert row["baseline_reachable"] is True, "builtin must be the pristine twin, not the defended live one"
        assert row["scenario_name"] and row["scenario_name"] != row["scenario_id"]
    finally:
        client.post("/api/demo/reset")


def test_removing_only_link_is_improved():
    # web -> app -> db is the only route; cutting app->db must read IMPROVED, not PASS-by-default
    r = run_preflight(_twin(), SC, {"ops": [{"op": "remove_link", "src": "app-server", "dst": "database"}]})
    row = r["results"][0]
    assert row["baseline_reachable"] is True and row["after_reachable"] is False
    assert row["status"] == "IMPROVED" and r["verdict"] == "PASS"


def test_stored_twin_unchanged_after_preflight():
    twin = _twin()
    before_hash = twin.config_hash()
    before = json.dumps(twin.to_dict(), sort_keys=True, default=str)
    run_preflight(twin, SC, {"ops": [{"op": "add_link", "src": "web-server", "dst": "database"}]})
    assert twin.config_hash() == before_hash
    assert json.dumps(twin.to_dict(), sort_keys=True, default=str) == before


def test_unknown_op_rejected_unit_and_api():
    with pytest.raises(ValueError):
        validate_ops([{"op": "nuke_everything"}])
    # create a custom twin then preflight it via the API
    twin_body = {"name": "PF Twin", "description": "",
                 "assets": [{"id": "web-server", "name": "Web", "asset_type": "web_server", "zone": "dmz", "posture": 0.6, "pos": [0, 1, 0], "vulnerabilities": ["exposed_service"]},
                            {"id": "database", "name": "DB", "asset_type": "database", "zone": "data", "posture": 0.9, "pos": [1, 1, 0], "vulnerabilities": []}],
                 "connections": [{"source": "web-server", "target": "database", "trust": "medium", "traversable": True, "types": ["network"]}]}
    created = client.post("/api/twins/custom", json=twin_body)
    assert created.status_code == 201, created.text
    tid = created.json()["id"]
    bad = client.post(f"/api/twins/{tid}/preflight", json={"change": {"ops": [{"op": "nuke_everything"}]}})
    assert bad.status_code == 422
    good = client.post(f"/api/twins/{tid}/preflight",
                       json={"change": {"ops": [{"op": "set_posture", "asset_id": "database", "posture": 0.95}]},
                             "scenario_ids": ["lateral_movement"]})
    assert good.status_code == 200, good.text
    assert good.json()["verdict"] in ("PASS", "FAIL")
    assert "twin_sha256_before" in good.json() and "generated_at" in good.json()
    missing = client.post("/api/twins/nope/preflight", json={"change": {"ops": []}})
    assert missing.status_code == 404


def test_configs_change_derives_ops():
    twin = _twin()
    r = run_preflight(twin, SC, {"configs": "hostname web-server\ninterface Gi0/0\n ip address 10.0.0.1/24\n", "dialect": "cisco_ios"})
    assert "change_ops" in r  # derived ops are shown (may be empty for a no-op import)
    assert isinstance(r["change_ops"], list)


def test_cli_offline_exit_codes(tmp_path):
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    twin_file = os.path.join(root, "examples", "preflight", "twin.json")
    scen_file = os.path.join(root, "examples", "preflight", "scenarios.json")
    safe = os.path.join(root, "examples", "preflight", "safe-change.json")
    bad = os.path.join(root, "examples", "preflight", "regression-change.json")
    script = os.path.join(root, "scripts", "preflight.py")
    r0 = subprocess.run([sys.executable, script, "--offline", "--twin", twin_file,
                         "--change", safe, "--scenarios", scen_file], capture_output=True, text=True, cwd=root, check=False)
    assert r0.returncode == 0, r0.stdout + r0.stderr
    r1 = subprocess.run([sys.executable, script, "--offline", "--twin", twin_file,
                         "--change", bad, "--scenarios", scen_file], capture_output=True, text=True, cwd=root, check=False)
    assert r1.returncode == 1, r1.stdout + r1.stderr
    assert "web-server -> relay -> database" in r1.stdout
    r2 = subprocess.run([sys.executable, script, "--offline", "--twin", str(tmp_path / "missing.json"),
                         "--change", safe], capture_output=True, text=True, cwd=root, check=False)
    assert r2.returncode == 2
