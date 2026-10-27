from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = ConfigDict(protected_namespaces=("settings_",), env_file=".env", extra="ignore")

    model_api_base_url: str = "https://api.meta.ai/v1"
    meta_model: str = "muse-spark-1.3"
    model_api_key: str = ""
    database_url: str = "sqlite:///./cybergenesis.db"
    sim_step_delay_ms: int = 350
    model_timeout_seconds: float = 30.0
    model_max_retries: int = 2
    offline_mode: bool = False
    human_approval_enabled: bool = False
    approval_timeout_seconds: int = 120
    auto_approve: bool = False
    max_tokens_per_run: int = 20000
    run_timeout_s: float = 180
    # base URL phones on the LAN use for mobile approval; empty = auto-detect LAN IP:8000
    public_base_url: str = ""
    # Arena self-learning memory (B2/B4): JSON score memory across matches
    arena_memory_path: str = "./arena_memory.json"


settings = Settings()
