"""AI provider registry: Meta, Command Code, Kilo Code, Google AI Studio.

All four speak the OpenAI chat-completions wire format, so the single
client in meta_client.py serves all of them; this module owns the
catalogue (endpoints, defaults) and the runtime choices saved from the
Settings UI. Keys are stored only in the local provider_settings.json
(gitignored) or environment variables - they are never returned by any API.
"""

import json
from pathlib import Path

from app.core.config import settings

PROVIDERS: dict[str, dict] = {
    "meta": {
        "label": "Meta Muse Spark", "short": "META",
        "description": "Meta Model API (OpenAI-compatible). The original CYBERGENESIS provider.",
        "default_base_url": "https://api.meta.ai/v1", "default_model": "muse-spark-1.3",
        "model_placeholder": "muse-spark-1.3", "key_hint": "MODEL_API_KEY from the Meta developer console",
    },
    "commandcode": {
        "label": "Command Code", "short": "COMMAND CODE",
        "description": "Command Code Provider API: every top model behind one OpenAI-compatible endpoint.",
        "default_base_url": "https://api.commandcode.ai/provider/v1", "default_model": "",
        "model_placeholder": "e.g. a model id from GET /provider/v1/models", "key_hint": "COMMAND_CODE_API_KEY (cmd_...) from commandcode.ai",
    },
    "kilo": {
        "label": "Kilo Code (Kilo Gateway)", "short": "KILO",
        "description": "Kilo AI Gateway: one OpenAI-compatible endpoint routing to hundreds of models.",
        "default_base_url": "https://ai-gateway.kilo.ai/api/v1", "default_model": "",
        "model_placeholder": "e.g. provider/model id from the Kilo Gateway catalogue", "key_hint": "KILO_API_KEY from kilo.ai",
    },
    "google": {
        "label": "Google AI Studio (Gemini)", "short": "GOOGLE",
        "description": "Google AI Studio Gemini models via the OpenAI-compatibility endpoint.",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "default_model": "gemini-2.5-flash",
        "model_placeholder": "gemini-2.5-flash", "key_hint": "GOOGLE_API_KEY from Google AI Studio (aistudio.google.com)",
    },
}

_ENV_KEYS = {"meta": "model_api_key", "commandcode": "commandcode_api_key", "kilo": "kilo_api_key", "google": "google_api_key"}
_ENV_MODELS = {"meta": "meta_model", "commandcode": "commandcode_model", "kilo": "kilo_model", "google": "google_model"}
_ENV_BASES = {"meta": "model_api_base_url", "commandcode": "commandcode_base_url", "kilo": "kilo_base_url", "google": "google_base_url"}


def _store() -> Path:
    return Path(settings.provider_settings_path)


def load_saved() -> dict:
    try:
        return json.loads(_store().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing/corrupt store just means env defaults
        return {}


def save(data: dict) -> None:
    _store().write_text(json.dumps(data, indent=2), encoding="utf-8")


def resolved(provider_id: str, saved: dict | None = None) -> dict:
    """Effective config for a provider: Settings-UI store wins, then env, then defaults."""
    p = PROVIDERS[provider_id]
    saved = load_saved() if saved is None else saved
    entry = (saved.get("providers") or {}).get(provider_id) or {}
    return {
        "id": provider_id, "label": p["label"], "short": p["short"], "description": p["description"],
        "api_key": entry.get("api_key") or getattr(settings, _ENV_KEYS[provider_id]) or "",
        "model": entry.get("model") or getattr(settings, _ENV_MODELS[provider_id]) or p["default_model"],
        "base_url": (entry.get("base_url") or getattr(settings, _ENV_BASES[provider_id]) or p["default_base_url"]).rstrip("/"),
        "model_placeholder": p["model_placeholder"], "key_hint": p["key_hint"],
    }


def active_id(saved: dict | None = None) -> str:
    saved = load_saved() if saved is None else saved
    pid = saved.get("active") or settings.ai_provider or "meta"
    return pid if pid in PROVIDERS else "meta"


def public_catalogue() -> list[dict]:
    """What the Settings UI may see: everything except the keys themselves."""
    saved = load_saved()
    active = active_id(saved)
    out = []
    for pid in PROVIDERS:
        r = resolved(pid, saved)
        out.append({"id": pid, "label": r["label"], "short": r["short"], "description": r["description"],
                    "base_url": r["base_url"], "model": r["model"], "model_placeholder": r["model_placeholder"],
                    "key_hint": r["key_hint"], "configured": bool(r["api_key"]), "active": pid == active})
    return out


_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def check_base_url(provider_id: str, base_url: str) -> str:
    """The API key travels to base_url, so only the provider's own host (or the
    host pinned in the env by the operator) is accepted over https; plain http
    is allowed only for a gateway on this machine."""
    from urllib.parse import urlparse

    u = urlparse(base_url.strip())
    host = (u.hostname or "").lower()
    if not host:
        raise ValueError(f"invalid base_url: {base_url!r}")
    if host in _LOCAL_HOSTS:
        if u.scheme not in ("http", "https"):
            raise ValueError("base_url must be http(s)")
        return base_url.strip().rstrip("/")
    allowed = {urlparse(PROVIDERS[provider_id]["default_base_url"]).hostname}
    env_base = getattr(settings, _ENV_BASES[provider_id]) or ""
    if env_base:
        allowed.add(urlparse(env_base).hostname)
    if u.scheme != "https":
        raise ValueError("base_url must use https (http only for localhost)")
    if host not in allowed:
        raise ValueError(f"base_url host {host!r} is not allowed for provider {provider_id} (allowed: {', '.join(sorted(h for h in allowed if h))})")
    return base_url.strip().rstrip("/")


def activate(provider_id: str, api_key: str | None = None, model: str | None = None, base_url: str | None = None) -> dict:
    if provider_id not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider_id}")
    if base_url:
        base_url = check_base_url(provider_id, base_url)
    saved = load_saved()
    providers = saved.get("providers") or {}
    entry = dict(providers.get(provider_id) or {})
    if api_key:
        entry["api_key"] = api_key.strip()
    if model is not None:
        entry["model"] = model.strip()
    if base_url:
        entry["base_url"] = base_url.strip().rstrip("/")
    providers[provider_id] = entry
    save({"active": provider_id, "providers": providers})
    return resolved(provider_id)
