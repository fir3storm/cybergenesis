"""Policy engine: type-based sets are the single source of truth (gap 1).

The builtin twin's decisions must be unchanged after removing the old
asset-ID sets, and custom twins with renamed ids must get the same
protection purely from asset_type.
"""

import os
import sys

os.environ["OFFLINE_MODE"] = "true"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.policies import engine
from app.policies.engine import evaluate
from app.simulation.twin import ASSETS, EDGES, DigitalTwin

ACTIONS = ["isolate_asset", "apply_patch", "disable_service", "quarantine_vlan",
           "restore_snapshot", "revoke_session", "rotate_credential", "enforce_mfa", "kill_process"]

# Decisions captured from the pre-refactor (dual ID+type) engine.
BUILTIN_EXPECTED = {
    "internet": [False] * 9,
    "firewall": [False] * 9,
    "web-server": [True, True, True, True, True, False, False, False, False],
    "app-server": [True, True, True, True, True, False, False, False, False],
    "database": [False] * 9,
    "identity-provider": [False, False, False, False, False, True, True, True, False],
    "admin-workstation": [True, True, False, True, True, True, True, True, False],
    "employee-workstation": [True, True, False, True, True, True, True, True, False],
    "file-server": [True, True, False, True, True, False, False, False, False],
    "security-sensor": [False] * 9,
}


def test_no_id_based_sets_remain():
    for name in ("NEVER_ISOLATE", "PATCHABLE", "SERVICE_DISABLEABLE", "QUARANTINABLE"):
        assert not hasattr(engine, name), f"id-based set {name} must stay removed"


def test_builtin_decisions_unchanged():
    for asset in ASSETS:
        row = [evaluate(a, asset["id"], {}, DigitalTwin()).approved for a in ACTIONS]
        assert row == BUILTIN_EXPECTED[asset["id"]], asset["id"]


def _renamed_twin() -> DigitalTwin:
    import copy

    defs = [dict(d, id=f"x-{d['id']}") for d in copy.deepcopy(ASSETS)]
    edges = [(f"x-{s}", f"x-{t}", tr, trav, ty) for s, t, tr, trav, ty in EDGES]
    return DigitalTwin(defs, edges)


def test_custom_twin_protected_by_type_not_id():
    twin = _renamed_twin()
    assert not evaluate("isolate_asset", "x-database", {}, twin).approved
    assert not evaluate("isolate_asset", "x-internet", {}, twin).approved
    assert not evaluate("quarantine_vlan", "x-database", {}, twin).approved
    assert not evaluate("restore_snapshot", "x-firewall", {}, twin).approved
    assert evaluate("apply_patch", "x-web-server", {}, twin).approved
    assert not evaluate("apply_patch", "x-database", {}, twin).approved
    assert evaluate("disable_service", "x-web-server", {}, twin).approved
    assert not evaluate("disable_service", "x-file-server", {}, twin).approved
    assert evaluate("revoke_session", "x-identity-provider", {}, twin).approved


def test_type_wins_over_builtin_looking_id():
    # An asset that reuses a builtin id but has a core type is protected by type.
    defs = [{"id": "web-server", "name": "db in disguise", "asset_type": "database",
             "zone": "data", "posture": 0.85, "pos": [0, 1, 0], "vulnerabilities": []}]
    twin = DigitalTwin(defs, [])
    assert not evaluate("isolate_asset", "web-server", {}, twin).approved
    assert not evaluate("apply_patch", "web-server", {}, twin).approved
