from pydantic import BaseModel, Field


class TextIn(BaseModel):
    text: str = ""


class TelemetryIn(BaseModel):
    telemetry: list[dict] = []


class ScenarioIn(BaseModel):
    scenario: dict = {}
    seed: int = 42


class InvestigateIn(BaseModel):
    scenario: dict = {}
    telemetry: list[dict] = []


class ProposeIn(BaseModel):
    scenario: dict = {}
    hypothesis: dict = {}
    past_examples: list[str] = []
    extra_context: str = ""


class ExecuteIn(BaseModel):
    actions: list[dict] = []


class VerifyIn(BaseModel):
    scenario: dict = {}
    baseline_result: dict = {}


class CampaignIn(BaseModel):
    source_asset: str = ""
    target_asset: str = ""


class CriticIn(BaseModel):
    defense_label: str = ""
    alternate_paths: list[list[str]] = []


class GenericOut(BaseModel):
    summary: str = ""
    confidence: float = Field(ge=0, le=1, default=0.5)
    evidence_refs: list[str] = []


class PlanStep(BaseModel):
    step: int
    agents: list[str] = []
    parallel: bool = False
    why: str = ""


class CommanderPlan(BaseModel):
    plan: list[PlanStep] = []
    stop_condition: str = "no valid red campaign remains"
    confidence: float = Field(ge=0, le=1, default=0.7)
    evidence_refs: list[str] = []


class IntelOut(BaseModel):
    techniques: list[dict] = []
    predicted_next: dict = {}
    hardening_proposals: list[dict] = []
    summary: str = ""
    confidence: float = Field(ge=0, le=1, default=0.7)
    evidence_refs: list[str] = []


class IdentityOut(BaseModel):
    privilege_paths: list[dict] = []
    mfa_gaps: list[str] = []
    proposals: list[dict] = []
    summary: str = ""
    confidence: float = Field(ge=0, le=1, default=0.8)
    evidence_refs: list[str] = []


class DialectOut(BaseModel):
    device_id: str = ""
    dialect: str = ""
    config_text: str = ""
    parsed_actions: list[dict] = []
    summary: str = ""
    confidence: float = Field(ge=0, le=1, default=0.8)
    evidence_refs: list[str] = []


class SurfaceOut(BaseModel):
    exposure: list[dict] = []
    choke_points: list[dict] = []
    crown_jewels: list[str] = []
    summary: str = ""
    confidence: float = Field(ge=0, le=1, default=0.85)
    evidence_refs: list[str] = []


class FindingsOut(BaseModel):
    findings: list[dict] = []
    summary: str = ""
    confidence: float = Field(ge=0, le=1, default=0.85)
    evidence_refs: list[str] = []


class ImpactOut(BaseModel):
    users_affected: int = 0
    disrupted_paths: int = 0
    requires_human_approval: bool = False
    explanation: str = ""
    confidence: float = Field(ge=0, le=1, default=0.85)
    evidence_refs: list[str] = []


class ReportOut(BaseModel):
    report_markdown: str = ""
    removed_claims: list[str] = []
    citation_validity_rate: float = 1.0
    summary: str = ""
    confidence: float = Field(ge=0, le=1, default=0.8)
    evidence_refs: list[str] = []
