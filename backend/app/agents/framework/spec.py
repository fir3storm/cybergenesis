import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.integrations.meta_client import PROMPT_VERSION

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


class AgentSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    name: str
    team: str  # command|blue|red|assurance
    engine: str  # meta|deterministic|hybrid
    description: str = ""
    duties: list[str] = []
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    tools: list[str] = []
    can_propose_actions: list[str] = []
    timeout_s: float = 30.0
    max_tokens: int = 4000
    max_tool_steps: int = 4
    prompt_file: str = ""

    @property
    def prompt_version(self) -> str:
        return PROMPT_VERSION

    @property
    def prompt_hash(self) -> str:
        p = PROMPTS_DIR / self.prompt_file if self.prompt_file else None
        text = p.read_text(encoding="utf-8") if p and p.exists() else self.id
        return hashlib.sha256((PROMPT_VERSION + text).encode()).hexdigest()[:12]

    def system_prompt(self) -> str:
        p = PROMPTS_DIR / self.prompt_file if self.prompt_file else None
        return p.read_text(encoding="utf-8") if p and p.exists() else f"You are {self.name} in CYBERGENESIS."
