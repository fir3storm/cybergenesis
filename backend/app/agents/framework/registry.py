from pydantic import BaseModel, Field

from app.agents.framework import io
from app.agents.framework.spec import AgentSpec
from app.schemas import (AgentObservation, AttackScenarioPlan, CampaignPlan, DefenseProposal,
                         DefenseExecutionResult, IncidentHypothesis, VerificationResult)
from app.simulation.twin import ALLOWED_ACTIONS


class _TextIn(BaseModel):
    text: str = ""


class _TwinImageIn(BaseModel):
    image_data_url: str = ""


class _GenericOut(BaseModel):
    summary: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)
    evidence_refs: list[str] = []


READ_TOOLS = ["get_twin_summary", "get_asset", "list_telemetry", "explain_path", "get_device_config",
              "list_findings", "get_mitre", "search_memory"]

SPECS: list[AgentSpec] = [
    AgentSpec(id="observer", name="Observer", team="blue", engine="deterministic",
              description="Deterministic telemetry anomaly detection", input_model=io.TelemetryIn, output_model=AgentObservation,
              tools=["list_telemetry"], prompt_file="observer.md"),
    AgentSpec(id="adversary_simulator", name="Adversary Simulator", team="red", engine="deterministic",
              description="Executes validated campaigns only", input_model=io.ScenarioIn, output_model=AttackScenarioPlan,
              tools=[], prompt_file="adversary_simulator.md"),
    AgentSpec(id="incident_investigator", name="Incident Investigator", team="blue", engine="meta",
              description="Evidence-grounded incident reasoning", input_model=io.InvestigateIn, output_model=IncidentHypothesis,
              tools=READ_TOOLS, prompt_file="incident_investigator.md"),
    AgentSpec(id="defense_strategist", name="Defense Strategist", team="blue", engine="meta",
              description="Countermeasure proposals + simulated final choice", input_model=io.ProposeIn, output_model=DefenseProposal,
              tools=READ_TOOLS + ["simulate_on_clone"], can_propose_actions=sorted(ALLOWED_ACTIONS),
              prompt_file="defense_strategist.md"),
    AgentSpec(id="defense_executor", name="Defense Executor", team="blue", engine="deterministic",
              description="Policy gate + the ONLY twin mutator", input_model=io.ExecuteIn, output_model=DefenseExecutionResult,
              tools=["get_twin_summary"], prompt_file="defense_executor.md"),
    AgentSpec(id="verification_scientist", name="Verification Scientist", team="assurance", engine="deterministic",
              description="Independent replay verification", input_model=io.VerifyIn, output_model=VerificationResult,
              tools=["explain_path"], prompt_file="verification_scientist.md"),
    AgentSpec(id="red_team_planner", name="Red Team Planner", team="red", engine="meta",
              description="Campaign planner over the validated graph", input_model=io.CampaignIn, output_model=CampaignPlan,
              tools=READ_TOOLS, prompt_file="red_team_planner.md"),
    AgentSpec(id="red_team_critic", name="Red Team Critic", team="red", engine="meta",
              description="Finds bypasses in chosen defenses", input_model=io.CriticIn, output_model=_GenericOut,
              tools=["explain_path"], prompt_file="red_team_critic.md"),
    AgentSpec(id="scenario_author", name="Scenario Author", team="red", engine="meta",
              description="Text-to-scenario (validated)", input_model=io.TextIn, output_model=_GenericOut,
              tools=["get_twin_summary"], prompt_file="scenario_author.md"),
    AgentSpec(id="twin_architect", name="Twin Architect", team="command", engine="meta",
              description="Image-to-twin (multimodal, validated)", input_model=io.TextIn, output_model=_GenericOut,
              tools=["get_twin_summary"], prompt_file="twin_architect.md"),
]

REGISTRY: dict[str, AgentSpec] = {s.id: s for s in SPECS}


def get_spec(agent_id: str) -> AgentSpec | None:
    return REGISTRY.get(agent_id)


def all_specs() -> list[AgentSpec]:
    return list(REGISTRY.values())
