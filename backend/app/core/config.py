from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Why protected_namespaces=("settings_",): Pydantic v2 otherwise warns/errors
    # when a field name starts with the protected prefix ("model_" by default).
    # Guarding "settings_" keeps that check for any future settings_* field;
    # keep it until such fields are renamed.
    model_config = ConfigDict(protected_namespaces=("settings_",), env_file=".env", extra="ignore")

    model_api_base_url: str = "https://api.meta.ai/v1"
    meta_model: str = "muse-spark-1.3"
    model_api_key: str = ""
    # Active AI provider: meta | commandcode | kilo | google (Settings UI can switch at runtime)
    ai_provider: str = "meta"
    commandcode_api_key: str = ""
    commandcode_model: str = ""
    commandcode_base_url: str = "https://api.commandcode.ai/provider/v1"
    kilo_api_key: str = ""
    kilo_model: str = ""
    kilo_base_url: str = "https://ai-gateway.kilo.ai/api/v1"
    google_api_key: str = ""
    google_model: str = "gemini-2.5-flash"
    google_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    # Runtime provider choices saved from the Settings UI (keys stay on this machine)
    provider_settings_path: str = "./provider_settings.json"
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
    # Shared secret for write-capable settings endpoints; auto-seeded at startup if unset
    admin_token: str = ""


settings = Settings()
