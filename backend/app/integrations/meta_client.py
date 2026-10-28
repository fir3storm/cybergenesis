"""Meta Model API client (OpenAI-compatible). Never fabricates success."""

import asyncio
import hashlib
import json
import time
from contextlib import contextmanager
from contextvars import ContextVar

import httpx

from app.core.config import settings

PROMPT_VERSION = "cybergenesis-v4"

# Per-run budget split: backbone agents may spend the full per-run budget;
# advisory agents may spend only the non-reserved 40%, so the 60% backbone
# reserve can never be drained by them. The per-call output cap is
# settings.model_max_tokens_per_call.
ADVISORY_BUDGET_FRACTION = 0.4
BACKBONE_AGENT_IDS = frozenset({"incident_investigator", "defense_strategist", "red_team_critic"})

_budget_tier: ContextVar[str] = ContextVar("cybergenesis_budget_tier", default="advisory")


class ProviderUnavailable(Exception):
    pass


MAX_RETRY_WAIT_S = 20.0
HEALTH_CACHE_S = 600.0


def _retry_wait(r: httpx.Response, attempt: int) -> float | None:
    """Seconds to wait before retrying an HTTP error, or None to stop now.

    Only rate limits (429) and transient overload (5xx) are worth retrying, and
    only after a pause: instant retries on a 429 burn quota and fail again
    (plus Command Code's intermittent region 403, which is routing, not auth). A
    provider-suggested wait longer than MAX_RETRY_WAIT_S (e.g. a daily free-tier
    cap) is not worth blocking a run for, so it fails fast to the labelled
    offline fallback. Other 4xx (bad model, bad key) never succeed on retry.
    """
    import re

    if r.status_code == 403 and "model_region_unavailable" in r.text:
        # Command Code refuses a share of Muse Spark calls by region routing,
        # uncharged; the same request usually succeeds on the next attempt.
        return 1.0
    if r.status_code != 429 and r.status_code < 500:
        return None
    hint = r.headers.get("retry-after")
    if not hint:
        m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", r.text)
        if m:
            hint = str(int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3)))
    try:
        wait = float(hint) if hint else 2.0 * (2 ** attempt)
    except ValueError:
        wait = 2.0 * (2 ** attempt)
    return wait if wait <= MAX_RETRY_WAIT_S else None


class MetaModelClient:
    """One OpenAI-compatible client serving every registered AI provider.

    The active provider (Meta / Command Code / Kilo / Google AI Studio) is
    chosen at runtime from the Settings UI; switching providers simply
    re-points base URL, model and key. All call sites keep using this client.
    """

    def __init__(self) -> None:
        self._health_cache: dict[tuple, tuple[float, dict]] = {}
        self.base = settings.model_api_base_url.rstrip("/")
        self.model = settings.meta_model
        self.key = settings.model_api_key
        self.provider_id = "meta"
        self.provider_label = "Meta Muse Spark"
        try:
            from app.integrations.providers import active_id, resolved

            self.apply_provider(resolved(active_id()))
        except Exception:  # noqa: BLE001 - registry failure must not break offline mode
            self.provider_id = "meta"

    def apply_provider(self, cfg: dict) -> None:
        self.provider_id = cfg["id"]
        self.provider_label = cfg["label"]
        self.base = cfg["base_url"].rstrip("/")
        self.model = cfg["model"]
        self.key = cfg["api_key"]
        self._usage: dict[str, list[dict]] = {}
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(4)  # max 4 concurrent Meta calls across all agents/runs

    async def _record(self, rec: dict) -> None:
        async with self._lock:
            self._usage.setdefault(rec.get("run_id") or "_global", []).append(rec)

    def usage_snapshot(self, run_id: str | None, clear: bool = False) -> list[dict]:
        """Sync snapshot for the orchestrator's persistence step (dict pop is atomic)."""
        key = run_id or "_global"
        rows = list(self._usage.get(key, []))
        if clear:
            self._usage.pop(key, None)
        return rows

    def tokens_used(self, run_id: str | None) -> int:
        return sum(u["prompt_tokens"] + u["completion_tokens"] for u in self._usage.get(run_id or "_global", []))

    def budget_limit(self, tier: str | None = None) -> int:
        tier = tier or _budget_tier.get()
        if tier == "backbone":
            return int(settings.max_tokens_per_run)
        return int(settings.max_tokens_per_run * ADVISORY_BUDGET_FRACTION)

    def current_budget_tier(self) -> str:
        return _budget_tier.get()

    @contextmanager
    def use_budget_tier(self, tier: str):
        if tier not in ("backbone", "advisory"):
            raise ValueError(f"unknown budget tier '{tier}'")
        token = _budget_tier.set(tier)
        try:
            yield self
        finally:
            _budget_tier.reset(token)

    @staticmethod
    def tier_for_agent(agent_id: str) -> str:
        return "backbone" if agent_id in BACKBONE_AGENT_IDS else "advisory"

    def budget_exhausted(self, run_id: str | None, tier: str | None = None) -> bool:
        return self.tokens_used(run_id) >= self.budget_limit(tier)

    def _check_budget(self, run_id: str | None, tier: str | None = None) -> None:
        tier = tier or _budget_tier.get()
        used = self.tokens_used(run_id)
        limit = self.budget_limit(tier)
        if used >= limit:
            raise ProviderUnavailable(
                f"token budget exceeded for run (tier={tier}, used {used} >= limit {limit} "
                f"of max_tokens_per_run={settings.max_tokens_per_run}); falling back offline")

    @property
    def configured(self) -> bool:
        return bool(self.key and self.model) and not settings.offline_mode

    async def health(self) -> dict:
        # Must agree with the `configured` property: offline mode means the
        # client will never call a live provider, so it is not configured.
        if not self.key or settings.offline_mode:
            return {"configured": False, "reachable": False, "model": self.model, "provider": self.provider_id,
                    "provider_label": self.provider_label,
                    "mode": "offline",
                    "detail": ("OFFLINE_MODE explicitly enabled"
                               if settings.offline_mode else
                               f"no API key for {self.provider_label} — offline simulation mode (set one in Settings)")}
        # Listing /models proves only that the key is accepted: a wrong model
        # name or an exhausted quota still lists fine. So one tiny real chat
        # request decides "live", cached per provider/model/key so page loads
        # do not spend quota.
        cache_key = (self.base, self.model, hashlib.sha256(self.key.encode()).hexdigest()[:12])
        cached = self._health_cache.get(cache_key)
        if cached and time.time() - cached[0] < HEALTH_CACHE_S:
            return cached[1]
        headers = {"Authorization": f"Bearer {self.key}"}
        body = {"model": self.model, "max_tokens": 16, "messages": [{"role": "user", "content": "Reply with: ok"}]}
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                for _ in range(2):  # one retry for Command Code's intermittent region 403
                    r = await c.post(f"{self.base}/chat/completions", headers=headers, json=body)
                    if not (r.status_code == 403 and "model_region_unavailable" in r.text):
                        break
            ok = r.status_code < 400
            reason = {401: "key rejected", 403: "access denied", 404: "model not found",
                      429: "rate limit or quota exhausted"}.get(r.status_code, "")
            result = {"configured": True, "reachable": r.status_code < 500, "model": self.model,
                      "mode": "live" if ok else "offline",
                      "detail": (f"model answered (HTTP {r.status_code})" if ok else
                                 f"model {self.model} unusable: HTTP {r.status_code}{' — ' + reason if reason else ''}")}
        except Exception as e:  # noqa: BLE001 - surfaced honestly to UI
            return {"configured": True, "reachable": False, "model": self.model,
                    "mode": "offline", "detail": f"provider unreachable: {type(e).__name__}"}
        self._health_cache[cache_key] = (time.time(), result)
        return result

    async def chat_json(self, system: str, user: str, run_id: str | None = None,
                        tier: str | None = None) -> tuple[dict, dict]:
        """Returns (parsed_json, usage_dict). Raises ProviderUnavailable on any failure.

        ``tier`` is "backbone" (full per-run budget) or "advisory" (only the
        non-reserved 40%); when omitted, the ambient ``use_budget_tier``
        context applies, defaulting to advisory.
        """
        if not self.configured:
            raise ProviderUnavailable(f"AI provider not configured ({self.provider_label}: no key/model or offline mode)")
        self._check_budget(run_id, tier)
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        body = {"model": self.model, "temperature": 0.2, "response_format": {"type": "json_object"},
                "max_tokens": settings.model_max_tokens_per_call,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        last_err = ""
        for attempt in range(settings.model_max_retries + 1):
            started = time.time()
            try:
                async with self._semaphore, httpx.AsyncClient(timeout=settings.model_timeout_seconds) as c:
                    r = await c.post(f"{self.base}/chat/completions", headers=headers, json=body)
                latency = int((time.time() - started) * 1000)
                if r.status_code >= 400:
                    last_err = f"HTTP {r.status_code}"
                    wait = _retry_wait(r, attempt)
                    if wait is None or attempt == settings.model_max_retries:
                        break
                    await asyncio.sleep(wait)
                    continue
                data = r.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {}) or {}
                parsed = _extract_json(content)
                rec = {"model": self.model, "prompt_version": PROMPT_VERSION,
                       "prompt_hash": hashlib.sha256((PROMPT_VERSION + system).encode()).hexdigest()[:12],
                       "prompt_tokens": usage.get("prompt_tokens", 0),
                       "completion_tokens": usage.get("completion_tokens", 0),
                       "latency_ms": latency, "success": True, "run_id": run_id}
                await self._record(rec)
                return parsed, rec
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
        rec = {"model": self.model, "prompt_version": PROMPT_VERSION,
               "prompt_hash": hashlib.sha256((PROMPT_VERSION + system).encode()).hexdigest()[:12],
               "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 0, "success": False, "error": last_err, "run_id": run_id}
        await self._record(rec)
        raise ProviderUnavailable(last_err)


    async def chat_vision_json(self, prompt: str, image_data_url: str, run_id: str | None = None,
                               tier: str | None = None) -> tuple[dict, dict]:
        """Multimodal: send an image + prompt, expect a JSON object back."""
        if not self.configured:
            raise ProviderUnavailable(f"AI provider not configured ({self.provider_label}: no key/model or offline mode)")
        self._check_budget(run_id, tier)
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        body = {"model": self.model, "temperature": 0.1, "response_format": {"type": "json_object"},
                "max_tokens": settings.model_max_tokens_per_call,
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
                   "prompt_hash": hashlib.sha256((PROMPT_VERSION + prompt).encode()).hexdigest()[:12],
                   "prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0),
                   "latency_ms": int((time.time() - started) * 1000), "success": True, "run_id": run_id}
            await self._record(rec)
            return parsed, rec
        except ProviderUnavailable:
            raise
        except Exception as e:
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

