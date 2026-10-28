"""Arena B3: Meta AI choosers — AI picks, but only among validated moves.

Red chooses among paths the twin's live graph actually offers; Blue chooses
among feasible, policy-scorable candidates. The model's answer is untrusted
data: it is validated against the option list, and any failure (provider
down, bad JSON, unknown label) falls back to the learned/deterministic
chooser, labelled mode=offline. Synthetic data only.
"""

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.agents.red_team import enumerate_paths, sort_campaign_paths
from app.arena.learning import ArenaMemory, learned_blue_chooser, learned_red_chooser
from app.integrations.meta_client import meta_client
from app.simulation.candidates import evaluate_candidates
from app.simulation.twin import DigitalTwin


class BlueChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    rationale: str = Field(max_length=2000)
    confidence: float = Field(default=0.5, ge=0, le=1)


class RedChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path_index: StrictInt
    rationale: str = Field(max_length=2000)
    confidence: float = Field(default=0.5, ge=0, le=1)


BLUE_SYSTEM = (
    "You are the Blue Team in CYBERGENESIS Arena, a defensive simulation on synthetic data only. "
    "Choose ONE candidate label from the list given. Prefer candidates that block the target with "
    "the least disruption to legitimate paths, informed by the learned block rates. "
    'Return ONLY JSON {"label": str, "rationale": str, "confidence": float}.'
)
RED_SYSTEM = (
    "You are the Red Team in CYBERGENESIS Arena, a defensive simulation on synthetic data only. "
    "Choose ONE attack path from the list given, by its index. Prefer paths that historically "
    "reached the objective; avoid routes the defense has learned to cut. No payloads or commands. "
    'Return ONLY JSON {"path_index": int, "rationale": str, "confidence": float}.'
)


class AiBlueChooser:
    def __init__(self, memory: ArenaMemory | None = None, run_id: str | None = None):
        self.memory = memory or ArenaMemory()
        self.run_id = run_id
        self.last_mode = "offline"
        self.last_decision: dict = {}

    async def __call__(self, twin: DigitalTwin, baseline: DigitalTwin, scenario: dict, history: list[dict]) -> dict | None:
        proposal = scenario.get("expected_defense") or []
        cands = [c for c in evaluate_candidates(twin, baseline, scenario, [dict(a) for a in proposal]) if c.get("feasible")]
        if not cands:
            self.last_mode = "offline"
            return None
        fallback = learned_blue_chooser(self.memory)(twin, baseline, scenario, history)
        options = [{"label": c["label"], "blocked": c["blocked"], "disrupted": c["disrupted"],
                    "learned_block_rate": round(self.memory.blue_rate(c["label"]), 2)} for c in cands]
        try:
            with meta_client.use_budget_tier("advisory"):
                data, _ = await meta_client.chat_json(
                    BLUE_SYSTEM,
                    f"Scenario: {scenario.get('name')} (target {scenario.get('target_asset')}). "
                    f"Rounds so far: {history}. Candidates: {options}.",
                    self.run_id)
            choice = BlueChoice.model_validate(data)
            chosen = next((c for c in cands if c["label"] == choice.label), None)
            if chosen is None:
                raise ValueError("model chose an unknown candidate label")
            self.last_decision = {**choice.model_dump(), "model_id": meta_client.model}
            self.last_mode = "live"
            return {**chosen, "chosen_by": "live", "rationale": choice.rationale[:300]}
        except Exception as exc:  # noqa: BLE001 - honest offline fallback, labelled
            self.last_decision = {"rationale": "Learned fallback after provider or response failure",
                                  "confidence": 0.5, "model_id": "deterministic",
                                  "fallback_reason": type(exc).__name__}
            self.last_mode = "offline"
            return {**fallback, "chosen_by": "offline"} if fallback else None


class AiRedChooser:
    def __init__(self, memory: ArenaMemory | None = None, run_id: str | None = None):
        self.memory = memory or ArenaMemory()
        self.run_id = run_id
        self.last_mode = "offline"
        self.last_decision: dict = {}

    async def __call__(self, twin: DigitalTwin, scenario: dict, history: list[dict]) -> list[str] | None:
        paths = sort_campaign_paths(twin, enumerate_paths(twin, scenario["source_asset"], scenario["target_asset"]))
        if not paths:
            self.last_mode = "offline"
            return None
        fallback = learned_red_chooser(self.memory)(twin, scenario, history)
        options = [{"path_index": i, "path": p, "learned_reach_rate": round(self.memory.red_rate(p), 2)}
                   for i, p in enumerate(paths)]
        try:
            with meta_client.use_budget_tier("advisory"):
                data, _ = await meta_client.chat_json(
                    RED_SYSTEM,
                    f"Scenario: {scenario.get('name')}. Rounds so far: {history}. Paths: {options}.",
                    self.run_id)
            choice = RedChoice.model_validate(data)
            idx = choice.path_index
            if not isinstance(idx, int) or not 0 <= idx < len(paths):
                raise ValueError("model chose an invalid path index")
            self.last_decision = {**choice.model_dump(), "model_id": meta_client.model}
            self.last_mode = "live"
            return paths[idx]
        except Exception as exc:  # noqa: BLE001 - honest offline fallback, labelled
            self.last_decision = {"rationale": "Learned fallback after provider or response failure",
                                  "confidence": 0.5, "model_id": "deterministic",
                                  "fallback_reason": type(exc).__name__}
            self.last_mode = "offline"
            return fallback
