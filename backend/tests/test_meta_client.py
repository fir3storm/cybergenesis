"""Direct unit tests for app.integrations.meta_client (retry, budget, usage).

No provider is contacted: httpx.AsyncClient is monkeypatched, so these run
hermetic and fast.
"""

import os
import sys

os.environ["OFFLINE_MODE"] = "true"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio

import httpx
import pytest

from app.core import config as _cfg
from app.integrations import meta_client


def _live_client(monkeypatch):
    """A client that looks configured (fake key/model, offline_mode off)."""
    mc = meta_client.MetaModelClient()
    mc.apply_provider({"id": "test", "label": "Test", "base_url": "http://localhost:9999",
                       "model": "fake-model", "api_key": "fake-key"})
    monkeypatch.setattr(_cfg.settings, "offline_mode", False)
    return mc


def _patch_async_client(monkeypatch, responses):
    """Replace httpx.AsyncClient.post/get with one that serves canned responses."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        idx = calls["n"]
        calls["n"] += 1
        if idx >= len(responses):
            return httpx.Response(500, text="exhausted")
        status, payload = responses[idx]
        return httpx.Response(status_code=status, json=payload)

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            self._transport = httpx.MockTransport(handler)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, **kw):
            req = httpx.Request("POST", url)
            return self._transport.handle_request(req)

        async def get(self, url, **kw):
            req = httpx.Request("GET", url)
            return self._transport.handle_request(req)

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    return calls


def test_chat_json_retries_on_500_then_succeeds(monkeypatch):
    mc = _live_client(monkeypatch)
    calls = _patch_async_client(monkeypatch, [
        (500, {"error": "server error"}),
        (200, {"choices": [{"message": {"content": '{"answer": "ok"}'}}],
               "usage": {"prompt_tokens": 5, "completion_tokens": 3}}),
    ])
    data, usage = asyncio.run(mc.chat_json("sys", "user", "run-1"))
    assert data == {"answer": "ok"}
    assert usage["prompt_tokens"] == 5
    assert calls["n"] == 2  # one retry


def test_chat_json_raises_provider_unavailable_after_retries(monkeypatch):
    mc = _live_client(monkeypatch)
    _patch_async_client(monkeypatch, [(500, {"error": "x"})] * 10)
    with pytest.raises(meta_client.ProviderUnavailable):
        asyncio.run(mc.chat_json("sys", "user", "run-2"))


def test_budget_tier_split_and_exhaustion():
    mc = meta_client.MetaModelClient()
    # backbone tier gets the full per-run budget; advisory gets 40%.
    assert mc.budget_limit("backbone") == 20000
    assert mc.budget_limit("advisory") == 8000
    assert mc.tier_for_agent("incident_investigator") == "backbone"
    assert mc.tier_for_agent("red_team_critic") == "backbone"
    assert mc.tier_for_agent("defense_strategist") == "backbone"
    assert mc.tier_for_agent("config_engineer") == "advisory"
    assert mc.tier_for_agent("unknown") == "advisory"
    # nothing recorded yet -> not exhausted
    assert not mc.budget_exhausted(None, "advisory")
    # record enough advisory tokens to exhaust the advisory tier
    asyncio.run(mc._record({"run_id": None, "prompt_tokens": 8000, "completion_tokens": 0,
                            "latency_ms": 0, "success": True, "error": None}))
    assert mc.budget_exhausted(None, "advisory")
    # but the backbone tier still has its full budget
    assert not mc.budget_exhausted(None, "backbone")


def test_usage_snapshot_clear_is_atomic():
    mc = meta_client.MetaModelClient()
    asyncio.run(mc._record({"run_id": "r-1", "prompt_tokens": 1, "completion_tokens": 2,
                            "latency_ms": 0, "success": True, "error": None}))
    rows = mc.usage_snapshot("r-1")
    assert len(rows) == 1
    assert mc.tokens_used("r-1") == 3
    cleared = mc.usage_snapshot("r-1", clear=True)
    assert len(cleared) == 1
    assert mc.usage_snapshot("r-1") == []  # popped


def test_concurrent_calls_respect_semaphore():
    """The 4-call semaphore bounds how many httpx calls can be in flight."""
    mc = meta_client.MetaModelClient()
    assert mc._semaphore._value == 4


def test_offline_mode_labelled_honestly(monkeypatch):
    monkeypatch.setattr(_cfg.settings, "offline_mode", True)
    monkeypatch.setattr(_cfg.settings, "model_api_key", "")
    mc = meta_client.MetaModelClient()
    h = asyncio.run(mc.health())
    assert h["configured"] is False
    assert h["mode"] == "offline"
    assert "OFFLINE_MODE explicitly enabled" in h["detail"]


def test_provider_failure_recorded_not_faked(monkeypatch):
    """A failed call records a failure row — fake success is a test failure."""
    mc = _live_client(monkeypatch)
    _patch_async_client(monkeypatch, [(500, {"error": "x"})] * 10)
    with pytest.raises(meta_client.ProviderUnavailable):
        asyncio.run(mc.chat_json("sys", "user", "run-3"))
    rows = mc.usage_snapshot("run-3")
    assert rows and rows[0]["success"] is False and rows[0]["error"]


def test_budget_exhausted_raises_provider_unavailable(monkeypatch):
    """When the advisory budget is spent, the next call fails loudly offline."""
    mc = _live_client(monkeypatch)
    asyncio.run(mc._record({"run_id": "r-4", "prompt_tokens": 8000, "completion_tokens": 0,
                            "latency_ms": 0, "success": True, "error": None}))
    with pytest.raises(meta_client.ProviderUnavailable):
        asyncio.run(mc.chat_json("sys", "user", "r-4"))