import os
import sys

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.agents.framework import io  # noqa: E402
from app.agents.framework.adapters import AGENT_CLASSES, build_agent  # noqa: E402
from app.agents.framework.base import AgentContext, AgentResult  # noqa: E402
from app.agents.framework.registry import REGISTRY  # noqa: E402
from app.db import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.orchestration.orchestrator import run_experiment  # noqa: E402
from app.schemas import (AgentObservation, AttackScenarioPlan, DefenseExecutionResult,  # noqa: E402
                         VerificationResult)
from app.simulation.scenarios import SCENARIOS  # noqa: E402
from app.simulation.twin import DigitalTwin  # noqa: E402

client = TestClient(app)
init_db()

SCENARIO = SCENARIOS["ransomware_activity"]
TELEMETRY = [
    {"id": "tele-a2-0", "event_type": "file_modification_burst", "asset_id": "employee-workstation",
     "message": "synthetic file burst"},
    {"id": "tele-a2-1", "event_type": "network_connection", "asset_id": "employee-workstation",
     "message": "synthetic connection to file server"},
]


def _ctx(twin=None, baseline_twin=None, run_id="a2-test"):
    return AgentContext(run_id=run_id, twin=twin or DigitalTwin(), scenario=SCENARIO,
                        telemetry=list(TELEMETRY), baseline_twin=baseline_twin)


def test_all_ten_registry_agents_buildable():
    assert len(REGISTRY) == 10
    assert set(REGISTRY) == set(AGENT_CLASSES)
    for agent_id in sorted(REGISTRY):
        agent = build_agent(agent_id)
        assert agent.spec.id == agent_id
        assert agent.spec is REGISTRY[agent_id] or agent.spec.id == REGISTRY[agent_id].id
    with pytest.raises(KeyError):
        build_agent("no_such_agent")


@pytest.mark.asyncio
async def test_observer_offline_deterministic_and_valid():
    results = []
    for _ in range(2):
        r = await build_agent("observer").run(_ctx(), io.TelemetryIn(telemetry=list(TELEMETRY)))
        assert isinstance(r, AgentResult)
        assert r.agent_id == "observer" and r.mode == "offline"
        assert isinstance(r.output, AgentObservation)
        AgentObservation.model_validate(r.output.model_dump())
        results.append(r.output.model_dump())
    assert results[0] == results[1]
    assert results[0]["anomalous"] is True
    assert results[0]["anomaly_type"] == "high_volume_file_modification"


@pytest.mark.asyncio
async def test_adversary_offline_deterministic_and_valid():
    results = []
    for _ in range(2):
        r = await build_agent("adversary_simulator").run(_ctx(), io.ScenarioIn(scenario=SCENARIO, seed=42))
        assert isinstance(r, AgentResult)
        assert r.agent_id == "adversary_simulator" and r.mode == "offline"
        assert isinstance(r.output, AttackScenarioPlan)
        AttackScenarioPlan.model_validate(r.output.model_dump())
        results.append(r.output.model_dump())
    assert results[0] == results[1]
    assert results[0]["scenario_id"] == "ransomware_activity"
    assert results[0]["steps"] == SCENARIO["attack_steps"]
    assert results[0]["seed"] == 42


@pytest.mark.asyncio
async def test_verification_offline_deterministic_and_valid():
    results = []
    for _ in range(2):
        twin = DigitalTwin()
        ctx = _ctx(twin=twin, baseline_twin=DigitalTwin())
        r = await build_agent("verification_scientist").run(ctx, io.VerifyIn(scenario=SCENARIO, baseline_result={"objective_blocked": False}))
        assert isinstance(r, AgentResult)
        assert r.agent_id == "verification_scientist" and r.mode == "offline"
        assert isinstance(r.output, VerificationResult)
        VerificationResult.model_validate(r.output.model_dump())
        results.append(r.output.model_dump())
    assert results[0] == results[1]
    # no defense applied, so the replay must honestly FAIL
    assert results[0]["outcome"] == "FAIL"
    assert results[0]["checks"]


@pytest.mark.asyncio
async def test_defense_executor_refuses_policy_rejected_without_mutating_twin():
    twin = DigitalTwin()
    before = twin.snapshot()
    r = await build_agent("defense_executor").run(
        _ctx(twin=twin), io.ExecuteIn(actions=[{"action_type": "isolate_asset", "asset_id": "database", "params": {}}]))
    assert isinstance(r, AgentResult)
    assert r.agent_id == "defense_executor" and r.mode == "offline"
    assert isinstance(r.output, DefenseExecutionResult)
    DefenseExecutionResult.model_validate(r.output.model_dump())
    assert r.output.success is False
    assert "policy rejected" in r.output.message
    assert twin.snapshot() == before


@pytest.mark.asyncio
async def test_defense_executor_offline_deterministic_on_rejected_action():
    outputs = []
    for _ in range(2):
        twin = DigitalTwin()
        r = await build_agent("defense_executor").run(
            _ctx(twin=twin), io.ExecuteIn(actions=[{"action_type": "isolate_asset", "asset_id": "database", "params": {}}]))
        outputs.append(r.output.model_dump())
    assert outputs[0] == outputs[1]


@pytest.mark.asyncio
async def test_incident_investigator_offline_carries_mode_and_fallback_reason():
    r = await build_agent("incident_investigator").run(_ctx(), io.InvestigateIn(scenario=SCENARIO, telemetry=list(TELEMETRY)))
    assert isinstance(r, AgentResult)
    assert r.agent_id == "incident_investigator"
    assert r.mode == "offline" and r.fallback_reason
    assert r.output.mode == "offline" and r.output.fallback_reason
    assert r.output.evidence_refs == ["tele-a2-0", "tele-a2-1"]


@pytest.mark.asyncio
async def test_orchestrated_run_messages_persisted_via_endpoint():
    created = client.post("/api/experiments", json={"scenario_id": "ransomware_activity", "seed": 42})
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]
    await run_experiment(run_id)
    results = client.get(f"/api/experiments/{run_id}/results").json()
    assert results["run"]["state"] == "COMPLETED", results

    messages = client.get(f"/api/experiments/{run_id}/messages").json()
    assert messages, "expected blackboard messages to be persisted for the run"
    seqs = [m["seq"] for m in messages]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs) and seqs[0] == 1
    assert all(m["id"] for m in messages) and len({m["id"] for m in messages}) == len(messages)

    pairs = {(m["from_agent"], m["kind"]) for m in messages}
    assert ("observer", "observation") in pairs
    assert ("incident_investigator", "hypothesis") in pairs
    assert ("defense_strategist", "proposal") in pairs
    assert ("defense_strategist", "final_choice") in pairs
    assert ("defense_executor", "decision") in pairs
    assert ("verification_scientist", "report") in pairs
    assert ("adversary_simulator", "campaign") in pairs
