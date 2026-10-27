from pydantic import BaseModel, Field


class AgentObservation(BaseModel):
    agent: str = "observer"
    anomalous: bool
    asset_ids: list[str] = []
    event_ids: list[str] = []
    anomaly_type: str = ""
    summary: str
    confidence: float = Field(ge=0, le=1)


class IncidentHypothesis(BaseModel):
    agent: str = "incident_investigator"
    hypothesis: str
    affected_assets: list[str] = []
    threat_level: str = "medium"
    confirmed: list[str] = []
    speculation: list[str] = []
    evidence_refs: list[str] = []
    claim_evidence: list[dict] = []  # [{claim, evidence_refs:[tele-...]}] per-claim citations
    confirmed_items: list[dict] = []  # spec shape: [{"claim": str, "evidence_ids": [tele-...]}]
    citation_warnings: list[str] = []
    confidence: float = Field(ge=0, le=1, default=0.5)
    model: str = "deterministic"
    mode: str = "offline"
    fallback_reason: str | None = None


class AttackScenarioPlan(BaseModel):
    agent: str = "adversary_simulator"
    scenario_id: str
    steps: list[dict] = []
    seed: int = 42


class DefenseAction(BaseModel):
    action_type: str
    asset_id: str
    params: dict = {}


class DefenseProposal(BaseModel):
    agent: str = "defense_strategist"
    actions: list[DefenseAction] = []
    justification: str
    expected_effectiveness: str = ""
    operational_impact: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)
    model: str = "deterministic"
    mode: str = "offline"
    evidence_refs: list[str] = []
    fallback_reason: str | None = None


class PolicyDecision(BaseModel):
    agent: str = "defense_executor"
    action_type: str
    asset_id: str
    approved: bool
    reasons: list[str] = []
    requires_human_approval: bool = False


class DefenseExecutionResult(BaseModel):
    agent: str = "defense_executor"
    action_type: str
    asset_id: str
    success: bool
    transition: dict = {}
    message: str = ""


class VerificationCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class VerificationResult(BaseModel):
    agent: str = "verification_scientist"
    outcome: str  # PASS | FAIL | INCONCLUSIVE
    invariant: str
    checks: list[VerificationCheck] = []
    metrics: dict = {}
    evidence_refs: list[str] = []


class CreateExperiment(BaseModel):
    scenario_id: str
    seed: int = 42


class TwinActionRequest(BaseModel):
    action_type: str
    asset_id: str
    params: dict = {}


class CustomTwinAsset(BaseModel):
    id: str
    name: str
    asset_type: str
    zone: str
    posture: float = 0.7
    pos: list[float] = [0, 1, 0]
    vulnerabilities: list[str] = []
    device_id: str | None = None


class CustomTwinConnection(BaseModel):
    source: str
    target: str
    trust: str = "medium"
    traversable: bool = True
    types: list[str] = ["network"]


class CreateCustomTwin(BaseModel):
    name: str
    description: str = ""
    assets: list[CustomTwinAsset] = []
    connections: list[CustomTwinConnection] = []


class CustomTwinResponse(BaseModel):
    id: str
    name: str
    description: str
    assets: list[dict]
    connections: list[dict]
    created_at: str


class AttackStep(BaseModel):
    type: str
    asset: str
    description: str


class CreateCustomScenario(BaseModel):
    name: str
    description: str = ""
    source_asset: str
    target_asset: str
    severity: str = "medium"
    invariant: str = ""
    objectives: list[str] = []
    verification_kind: str = "reachability"
    identity: str | None = None
    max_rounds: int | None = Field(default=None, ge=1, description="total campaign rounds including round 1")
    attack_steps: list[AttackStep] = []
    expected_defense: list[dict] = []


class CustomScenarioResponse(BaseModel):
    id: str
    name: str
    description: str
    definition: dict
    created_at: str


class CampaignStep(BaseModel):
    type: str
    asset: str
    description: str = ""


class CampaignPlan(BaseModel):
    agent: str = "adversary_simulator"
    foothold: str
    pivot_identity: str | None = None
    objective: str
    steps: list[CampaignStep] = []
    rationale: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)
    mode: str = "offline"
    path: list[str] = []


class CreateCustomExperiment(BaseModel):
    """Run an experiment with a custom scenario and/or custom twin (either may be builtin)."""

    custom_scenario_id: str | None = None
    scenario_id: str | None = None  # builtin scenario id, used when custom_scenario_id is null
    custom_twin_id: str | None = None
    seed: int = 42
