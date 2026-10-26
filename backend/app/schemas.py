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
    confidence: float = Field(ge=0, le=1, default=0.5)
    model: str = "deterministic"
    mode: str = "offline"


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
