import os
import sys

os.environ["SIM_STEP_DELAY_MS"] = "0"
os.environ["OFFLINE_MODE"] = "true"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orchestration.orchestrator import run_experiment
from app.simulation.candidates import evaluate_candidates
from app.simulation.scenarios import SCENARIOS
from app.simulation.twin import DigitalTwin

client = TestClient(app)


# ---------- 1. legitimate traffic ignores the attacker vulnerability gate ----------

def test_patching_intermediate_changes_attacker_but_not_legitimate_reachability():
    twin = DigitalTwin()
    baseline = twin.clone()
    assert twin.find_path("internet", "database") is not None
    assert twin.legitimate_reachable("internet", "web-server")

    twin.apply_action("apply_patch", "web-server")

    # Attacker reachability changes: web-server is a pivot on the only
    # internet -> database path, and a patched pivot fails the hop gate —
    # even a direct attacker probe of the patched target is gated.
    assert twin.find_path("internet", "database") is None
    assert twin.find_path("internet", "web-server") is None
    # Legitimate traffic does not need a vulnerability: no pair disrupted.
    assert twin.legitimate_reachable("internet", "web-server")
    assert twin.legitimate_disrupted(baseline) == 0

    # …but legitimate checks still honour real link blocks.
    twin.apply_action("block_connection", "internet",
                      {"source": "internet", "target": "firewall", "direction": "egress"})
    assert not twin.legitimate_reachable("internet", "web-server")
    assert twin.legitimate_disrupted(baseline) >= 1


# ---------- 2. surgical candidates ----------

def _actions(cands):
    return [a for c in cands for a in c["actions"]]


def test_candidates_emit_min_cut_surgical_options_and_rank_blocking_first():
    twin = DigitalTwin()
    baseline = twin.clone()
    sc = SCENARIOS["ransomware_activity"]
    twin.apply_attack(sc, seed=42)
    cut = sorted(nx.minimum_edge_cut(twin.live_graph(sc["target_asset"]),
                                      sc["source_asset"], sc["target_asset"]))
    assert cut, "test twin must have a min cut"
    twin.device_configs["file-server"]["mgmt"]["telnet"] = True
    cands = evaluate_candidates(twin, baseline, sc,
                                [{"action_type": "apply_patch", "asset_id": "employee-workstation", "params": {}}])
    actions = _actions(cands)
    # block_connection on EACH min-cut edge, egress at the sender and
    # ingress at the receiver
    for u, v in cut:
        assert any(a["action_type"] == "block_connection" and a["asset_id"] == u
                   and a["params"] == {"source": u, "target": v, "direction": "egress"} for a in actions), (u, v)
        assert any(a["action_type"] == "block_connection" and a["asset_id"] == v
                   and a["params"] == {"source": v, "target": u, "direction": "ingress"} for a in actions), (u, v)
    labels = [c["label"] for c in cands]
    assert any("min-cut" in lbl and "egress" in lbl for lbl in labels)
    assert any("min-cut" in lbl and "ingress" in lbl for lbl in labels)
    # quarantine on the source; harden_mgmt where the path has a mgmt weakness
    assert any(a["action_type"] == "quarantine_vlan" and a["asset_id"] == sc["source_asset"] for a in actions)
    assert any(a["action_type"] == "harden_mgmt" and a["asset_id"] == "file-server" for a in actions)
    # ranking: a blocking surgical option ahead of the non-blocking patch proposal
    agent_idx = next(i for i, c in enumerate(cands) if c["label"] == "Agent proposal")
    assert cands[agent_idx]["blocked"] is False
    blocking_surgical = [i for i, c in enumerate(cands)
                         if c["blocked"] and c["origin"] == "simulated"]
    assert blocking_surgical and min(blocking_surgical) < agent_idx
    assert cands[0]["blocked"] is True
    # invasiveness is recorded and the sort honours it among equals
    assert all("invasiveness" in c for c in cands)


def test_candidates_quarantine_compromised_intermediate_and_harden_snmp():
    twin = DigitalTwin()
    baseline = twin.clone()
    sc = SCENARIOS["lateral_movement"]
    twin.apply_attack(sc, seed=42)
    twin.set_state("app-server", "status", "compromised")
    twin.device_configs["app-server"]["mgmt"]["snmp_community"] = "public"
    cands = evaluate_candidates(twin, baseline, sc,
                                [{"action_type": "apply_patch", "asset_id": "web-server", "params": {}}])
    actions = _actions(cands)
    assert any(a["action_type"] == "quarantine_vlan" and a["asset_id"] == "web-server" for a in actions)
    assert any(a["action_type"] == "quarantine_vlan" and a["asset_id"] == "app-server" for a in actions)
    assert any(a["action_type"] == "harden_mgmt" and a["asset_id"] == "app-server" for a in actions)


# ---------- 3. battle max_rounds single source of truth ----------

def test_battle_scenario_declares_max_rounds_5_and_api_exposes_it():
    assert SCENARIOS["red_vs_blue_battle"]["max_rounds"] == 5
    listed = {s["id"]: s for s in client.get("/api/scenarios").json()}
    assert listed["red_vs_blue_battle"]["max_rounds"] == 5


def test_trim_plan_to_max_rounds_is_deterministic():
    from app.agents.framework.io import CommanderPlan, PlanStep
    from app.agents.framework.new_agents import trim_plan_to_max_rounds

    plan = CommanderPlan(plan=[PlanStep(step=i + 1, agents=["observer"]) for i in range(5)])
    trimmed, reason = trim_plan_to_max_rounds(plan, 2)
    assert len(trimmed.plan) == 2 and reason is not None and "max_rounds=2" in reason
    unchanged, reason2 = trim_plan_to_max_rounds(plan, 5)
    assert len(unchanged.plan) == 5 and reason2 is None
    unchanged2, reason3 = trim_plan_to_max_rounds(plan, None)
    assert len(unchanged2.plan) == 5 and reason3 is None


@pytest.mark.asyncio
async def test_scenario_with_max_rounds_2_never_exceeds_2_rounds():
    sc = client.post("/api/scenarios/custom", json={
        "name": "Battle max2 (F8b)", "description": "battle capped at 2 rounds",
        "source_asset": "internet", "target_asset": "file-server", "severity": "critical",
        "invariant": "No path from the internet to the file server remains",
        "objectives": ["reach_file_server"], "verification_kind": "reachability",
        "identity": None, "max_rounds": 2,
        "attack_steps": SCENARIOS["red_vs_blue_battle"]["attack_steps"],
        "expected_defense": SCENARIOS["red_vs_blue_battle"]["expected_defense"],
    })
    assert sc.status_code == 201, sc.text
    rid = client.post("/api/experiments/custom",
                      json={"custom_scenario_id": sc.json()["id"], "seed": 42}).json()["id"]
    await run_experiment(rid)
    res = client.get(f"/api/experiments/{rid}/results").json()
    assert res["run"]["state"] == "COMPLETED", res
    rounds = res["verification"]["metrics"]["rounds"]
    assert rounds and len(rounds) <= 2 and max(r["round"] for r in rounds) <= 2
    assert res["verification"]["metrics"]["max_rounds"] == 2
    # the commander plan was deterministically trimmed to the same budget
    events = client.get(f"/api/experiments/{rid}/events").json()
    assert any(e["event_type"] == "commander_plan_trimmed" for e in events), [e["event_type"] for e in events]


# ---------- 4. commander optional steps: DAG timing, authoring skip, decisions ----------

@pytest.mark.asyncio
async def test_optional_steps_skip_authoring_agents_and_persist_decisions(monkeypatch):
    from types import SimpleNamespace

    from app.agents.framework import adapters
    from app.agents.framework.io import CommanderPlan, PlanStep

    plan = CommanderPlan(plan=[
        PlanStep(step=1, agents=["observer"], why="backbone"),
        PlanStep(step=2, agents=["scenario_author", "config_auditor"], parallel=False, why="optional"),
        PlanStep(step=3, agents=["twin_architect"], why="authoring only"),
        PlanStep(step=4, agents=["incident_investigator"], why="backbone"),
    ], confidence=0.9)

    class _FakeCommander:
        async def run(self, ctx, inp):
            return SimpleNamespace(output=plan, mode="offline", model="deterministic-offline",
                                   fallback_reason=None, confidence=0.9)

    orig_build = adapters.build_agent

    def _fake_build(agent_id):
        return _FakeCommander() if agent_id == "incident_commander" else orig_build(agent_id)

    monkeypatch.setattr(adapters, "build_agent", _fake_build)
    rid = client.post("/api/experiments", json={"scenario_id": "ransomware_activity", "seed": 42}).json()["id"]
    await run_experiment(rid)
    events = client.get(f"/api/experiments/{rid}/events").json()
    skipped = [e for e in events if e["event_type"] == "plan_step_skipped"]
    assert {e["payload"]["agent"] for e in skipped} == {"scenario_author", "twin_architect"}, skipped
    assert all("authoring" in e["payload"]["reason"] for e in skipped)
    finished = [e for e in events if e["event_type"] == "plan_step_finished"
                and e["payload"].get("agent") == "config_auditor"]
    assert finished, [e["event_type"] for e in events]
    assert isinstance(finished[0]["payload"]["duration_ms"], int)
    assert finished[0]["payload"]["duration_ms"] >= 0
    assert finished[0]["payload"]["started_at"] and finished[0]["payload"]["finished_at"]
    started = [e for e in events if e["event_type"] == "plan_step_started"
               and e["payload"].get("agent") == "config_auditor"]
    assert started and started[0]["payload"]["started_at"]
    # no started/finished events for the skipped authoring agents
    assert not [e for e in events if e["event_type"] in ("plan_step_started", "plan_step_finished")
                and e["payload"].get("agent") in ("scenario_author", "twin_architect")]
    res = client.get(f"/api/experiments/{rid}/results").json()
    auditor = [d for d in res["decisions"] if d["agent"] == "config_auditor"]
    assert auditor and auditor[0]["data"].get("plan_step") == 2, res["decisions"]


# ---------- 5c. internet is never "remediated" ----------

def test_internet_never_displays_remediated():
    twin = DigitalTwin()
    twin.set_state("internet", "status", "remediated")
    assert twin.status["internet"] != "remediated"
    assert twin.status["internet"] == "exposed"
    twin.apply_action("apply_patch", "internet")
    assert twin.status["internet"] != "remediated"
    twin.apply_action("block_connection", "internet",
                      {"source": "internet", "target": "firewall", "direction": "egress"})
    assert twin.status["internet"] != "remediated"
    # other statuses remain available to the gateway
    twin.set_state("internet", "status", "contained")
    assert twin.status["internet"] == "contained"
