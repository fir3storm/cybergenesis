import os
import sys

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.agents.eval import deception_trip
from app.agents.framework import io
from app.agents.framework.adapters import build_agent
from app.agents.framework.base import AgentContext
from app.simulation.scenarios import SCENARIOS
from app.simulation.twin import DigitalTwin


@pytest.mark.parametrize("scenario_id", sorted(SCENARIOS))
def test_f7a_decoy_on_source_is_in_live_graph_and_trips_red(scenario_id):
    scenario = SCENARIOS[scenario_id]
    twin = DigitalTwin()
    twin.apply_action("deploy_decoy", scenario["source_asset"],
                      {"kind": "honeypot_host", "name": "decoy"})

    graph = twin.live_graph()
    assert "decoy" in graph.nodes
    assert any("decoy" in (a, b) for a, b in graph.edges())
    # The anchor connection is registered for the compiler, both directions active.
    assert (scenario["source_asset"], "decoy", "low", True, ["network"]) in twin.edge_defs
    assert twin.dir_active[(scenario["source_asset"], "decoy")] is True
    assert twin.dir_active[("decoy", scenario["source_asset"])] is True
    assert any("decoy" in (c["a"]["device"], c["b"]["device"]) for c in twin.cables_list())
    assert deception_trip(twin, scenario) == 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario_id", ["lateral_movement", "red_vs_blue_battle"])
async def test_f7a_decoy_via_defense_executor_trips_red(scenario_id):
    scenario = SCENARIOS[scenario_id]
    twin = DigitalTwin()
    ctx = AgentContext(run_id="f7a-test", twin=twin, scenario=scenario, telemetry=[])
    ex = await build_agent("defense_executor").run(ctx, io.ExecuteIn(
        actions=[{"action_type": "deploy_decoy", "asset_id": scenario["source_asset"],
                  "params": {"kind": "honeypot_host", "name": "decoy"}}]))
    assert ex.output.success
    assert "decoy" in twin.live_graph().nodes
    assert deception_trip(twin, scenario) == 1.0


def test_f7a_decoy_device_config_interfaces_and_telnet_service():
    twin = DigitalTwin()
    twin.apply_action("deploy_decoy", "web-server", {"kind": "honeypot_host", "name": "decoy"})

    cfg = twin.device_configs["decoy"]
    peers = {a if b == "decoy" else b for a, b, *_ in twin.edge_defs if "decoy" in (a, b)}
    assert peers  # anchor plus 2-hop shortcut peers
    assert [i["name"] for i in cfg["interfaces"]] == [f"eth{i}" for i in range(len(peers))]
    assert {i["peer"] for i in cfg["interfaces"]} == peers
    assert all(i["enabled"] for i in cfg["interfaces"])
    assert any(s["name"] == "telnet" and s["port"] == 23 and s["enabled"] for s in cfg["services"])
    # Compiler traversal into the decoy itself can succeed (enabled service + weakness).
    assert twin.find_path("internet", "decoy") is not None


def test_f7a_no_self_loops_after_deploying_on_several_anchors():
    twin = DigitalTwin()
    anchors = ["internet", "web-server", "employee-workstation", "database", "file-server"]
    for i, anchor in enumerate(anchors, start=1):
        twin.apply_action("deploy_decoy", anchor, {"kind": "honeypot_host", "name": f"decoy-{i}"})

    graph = twin.live_graph()
    for i in range(1, len(anchors) + 1):
        assert f"decoy-{i}" in graph.nodes
    assert all(a != b for a, b in graph.edges())
    assert all(a != b for a, b in twin.graph.edges())
    assert all(s != t for s, t, *_ in twin.edge_defs)
