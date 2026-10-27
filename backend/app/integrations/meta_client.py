"""Meta Model API client (OpenAI-compatible). Never fabricates success."""

import json
import time

import httpx

from app.core.config import settings

PROMPT_VERSION = "cybergenesis-v2"


class ProviderUnavailable(Exception):
    pass


class MetaModelClient:
    def __init__(self) -> None:
        self.base = settings.model_api_base_url.rstrip("/")
        self.model = settings.meta_model
        self.key = settings.model_api_key
        self.usage: list[dict] = []

    @property
    def configured(self) -> bool:
        return bool(self.key) and not settings.offline_mode

    async def health(self) -> dict:
        if not self.key:
            return {"configured": False, "reachable": False, "model": self.model,
                    "mode": "offline", "detail": "MODEL_API_KEY not set — offline simulation mode"}
        if settings.offline_mode:
            return {"configured": True, "reachable": False, "model": self.model,
                    "mode": "offline", "detail": "OFFLINE_MODE explicitly enabled"}
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"{self.base}/models", headers={"Authorization": f"Bearer {self.key}"})
            ok = r.status_code < 500
            return {"configured": True, "reachable": ok, "model": self.model,
                    "mode": "live" if ok else "offline",
                    "detail": f"provider responded HTTP {r.status_code}"}
        except Exception as e:  # noqa: BLE001 - surfaced honestly to UI
            return {"configured": True, "reachable": False, "model": self.model,
                    "mode": "offline", "detail": f"provider unreachable: {type(e).__name__}"}

    async def chat_json(self, system: str, user: str, run_id: str | None = None) -> tuple[dict, dict]:
        """Returns (parsed_json, usage_dict). Raises ProviderUnavailable on any failure."""
        if not self.configured:
            raise ProviderUnavailable("Meta Model API not configured (no key or offline mode)")
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        body = {"model": self.model, "temperature": 0.2, "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        last_err = ""
        for attempt in range(settings.model_max_retries + 1):
            started = time.time()
            try:
                async with httpx.AsyncClient(timeout=settings.model_timeout_seconds) as c:
                    r = await c.post(f"{self.base}/chat/completions", headers=headers, json=body)
                latency = int((time.time() - started) * 1000)
                if r.status_code >= 400:
                    last_err = f"HTTP {r.status_code}"
                    continue
                data = r.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {}) or {}
                parsed = _extract_json(content)
                rec = {"model": self.model, "prompt_version": PROMPT_VERSION,
                       "prompt_tokens": usage.get("prompt_tokens", 0),
                       "completion_tokens": usage.get("completion_tokens", 0),
                       "latency_ms": latency, "success": True, "run_id": run_id}
                self.usage.append(rec)
                return parsed, rec
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
        rec = {"model": self.model, "prompt_version": PROMPT_VERSION, "prompt_tokens": 0,
               "completion_tokens": 0, "latency_ms": 0, "success": False, "error": last_err, "run_id": run_id}
        self.usage.append(rec)
        raise ProviderUnavailable(last_err)


    async def chat_vision_json(self, prompt: str, image_data_url: str, run_id: str | None = None) -> tuple[dict, dict]:
        """Multimodal: send an image + prompt, expect a JSON object back."""
        if not self.configured:
            raise ProviderUnavailable("Meta Model API not configured (no key or offline mode)")
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        body = {"model": self.model, "temperature": 0.1, "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ]}]}
        started = time.time()
        try:
            async with httpx.AsyncClient(timeout=max(settings.model_timeout_seconds, 60)) as c:
                r = await c.post(f"{self.base}/chat/completions", headers=headers, json=body)
            if r.status_code >= 400:
                raise ProviderUnavailable(f"vision call HTTP {r.status_code}")
            data = r.json()
            usage = data.get("usage", {}) or {}
            parsed = _extract_json(data["choices"][0]["message"]["content"])
            rec = {"model": self.model, "prompt_version": PROMPT_VERSION + "-vision",
                   "prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0),
                   "latency_ms": int((time.time() - started) * 1000), "success": True, "run_id": run_id}
            self.usage.append(rec)
            return parsed, rec
        except ProviderUnavailable:
            raise
        except Exception as e:  # noqa: BLE001
            raise ProviderUnavailable(f"vision call failed: {type(e).__name__}: {e}") from e


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text.lower().startswith("json") else text
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object in model response")
    return json.loads(text[start:end + 1])


meta_client = MetaModelClient()
