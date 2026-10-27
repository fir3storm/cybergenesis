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
