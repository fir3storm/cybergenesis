"""MetaModelClient logic with mocked transport: hermetic, no network, no real key."""

import os
import sys

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

import app.integrations.meta_client as mc
from app.core.config import settings
from app.integrations.meta_client import MetaModelClient, ProviderUnavailable, _extract_json


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Isolate from any developer provider_settings.json / stored real keys.
    monkeypatch.setattr(settings, "provider_settings_path", str(tmp_path / "provider_settings.json"))
    monkeypatch.setattr(settings, "offline_mode", False)
    monkeypatch.setattr(settings, "max_tokens_per_run", 1000)
    monkeypatch.setattr(settings, "model_max_retries", 2)
    c = MetaModelClient()
    c.base = "https://example.test/v1"
    c.model = "test-model"
    c.key = "test-key"
    return c


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _ok(content='{"ok": true}', prompt_tokens=11, completion_tokens=7):
    return FakeResponse(200, {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    })


def _install_transport(monkeypatch, outcomes):
    """Fake httpx.AsyncClient: replays outcomes in order, repeating the last one."""
    state = {"calls": []}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers=None, json=None):
            state["calls"].append({"url": url, "headers": headers, "body": json})
            outcome = outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(mc.httpx, "AsyncClient", FakeClient)
    return state


@pytest.mark.asyncio
async def test_chat_json_success_parses_json_and_records_usage(client, monkeypatch):
    state = _install_transport(monkeypatch, [_ok('{"answer": 42}', prompt_tokens=11, completion_tokens=7)])

    parsed, rec = await client.chat_json("sys", "user", run_id="run-ok")

    assert parsed == {"answer": 42}
    assert rec["success"] is True
    assert rec["prompt_tokens"] == 11 and rec["completion_tokens"] == 7
    assert rec["model"] == "test-model" and rec["run_id"] == "run-ok"
    assert client.tokens_used("run-ok") == 18
    snapshot = client.usage_snapshot("run-ok")
    assert len(snapshot) == 1 and snapshot[0] == rec
    assert len(state["calls"]) == 1
    call = state["calls"][0]
    assert call["url"] == "https://example.test/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {client.key}"
    assert call["body"]["model"] == "test-model"


@pytest.mark.asyncio
async def test_chat_json_http500_then_success_retries(client, monkeypatch):
    state = _install_transport(monkeypatch, [FakeResponse(500, {}), _ok('{"recovered": true}', 5, 3)])

    parsed, rec = await client.chat_json("sys", "user", run_id="run-retry")

    assert parsed == {"recovered": True}
    assert rec["success"] is True
    assert len(state["calls"]) == 2
    assert client.tokens_used("run-retry") == 8
    # Only the successful attempt is recorded as a success row.
    assert [r["success"] for r in client.usage_snapshot("run-retry")] == [True]


@pytest.mark.asyncio
async def test_chat_json_persistent_failure_raises_after_retries(client, monkeypatch):
    state = _install_transport(monkeypatch, [FakeResponse(500, {})])

    with pytest.raises(ProviderUnavailable) as excinfo:
        await client.chat_json("sys", "user", run_id="run-dead")

    assert "HTTP 500" in str(excinfo.value)
    # model_max_retries=2 (patched in fixture) -> 1 initial + 2 retries.
    assert len(state["calls"]) == settings.model_max_retries + 1 == 3
    rows = client.usage_snapshot("run-dead")
    assert len(rows) == 1
    assert rows[0]["success"] is False and rows[0]["error"] == "HTTP 500"
    assert rows[0]["prompt_tokens"] == 0 and rows[0]["completion_tokens"] == 0
    assert client.tokens_used("run-dead") == 0


@pytest.mark.asyncio
async def test_chat_json_persistent_transport_error_raises_after_retries(client, monkeypatch):
    state = _install_transport(monkeypatch, [RuntimeError("boom")])

    with pytest.raises(ProviderUnavailable) as excinfo:
        await client.chat_json("sys", "user", run_id="run-boom")

    assert "RuntimeError: boom" in str(excinfo.value)
    assert len(state["calls"]) == 3


@pytest.mark.asyncio
async def test_record_usage_snapshot_and_tokens_used(client):
    await client._record({"run_id": "r1", "prompt_tokens": 10, "completion_tokens": 5, "success": True})
    await client._record({"run_id": "r1", "prompt_tokens": 1, "completion_tokens": 2, "success": True})
    await client._record({"run_id": "r2", "prompt_tokens": 100, "completion_tokens": 0, "success": True})
    await client._record({"prompt_tokens": 4, "completion_tokens": 6, "success": True})  # no run_id -> _global

    assert client.tokens_used("r1") == 18
    assert client.tokens_used("r2") == 100
    assert client.tokens_used(None) == 10
    assert client.tokens_used("missing-run") == 0

    snapshot = client.usage_snapshot("r1")
    assert len(snapshot) == 2
    cleared = client.usage_snapshot("r1", clear=True)
    assert cleared == snapshot
    assert client.usage_snapshot("r1") == []
    assert client.tokens_used("r1") == 0
    # Clearing one run leaves the others untouched.
    assert client.tokens_used("r2") == 100


def test_budget_limits_advisory_is_40_percent_backbone_is_100_percent(client):
    # Fixture pins max_tokens_per_run=1000.
    assert settings.max_tokens_per_run == 1000
    assert client.budget_limit("advisory") == 400
    assert client.budget_limit("backbone") == 1000
    assert mc.ADVISORY_BUDGET_FRACTION == 0.4
    # Default ambient tier is advisory.
    assert client.current_budget_tier() == "advisory"
    assert client.budget_limit() == 400
    with client.use_budget_tier("backbone"):
        assert client.budget_limit() == 1000
    assert client.budget_limit() == 400


def test_tier_for_agent_and_unknown_tier_rejected(client):
    assert MetaModelClient.tier_for_agent("incident_investigator") == "backbone"
    assert MetaModelClient.tier_for_agent("defense_strategist") == "backbone"
    assert MetaModelClient.tier_for_agent("red_team_critic") == "backbone"
    assert MetaModelClient.tier_for_agent("observer") == "advisory"
    with pytest.raises(ValueError), client.use_budget_tier("bogus"):
        pass


@pytest.mark.asyncio
async def test_check_budget_raises_when_exceeded_per_tier(client):
    await client._record({"run_id": "budgeted", "prompt_tokens": 399, "completion_tokens": 0, "success": True})
    client._check_budget("budgeted", tier="advisory")  # 399 < 400: ok
    client._check_budget("budgeted", tier="backbone")
    assert client.budget_exhausted("budgeted", tier="advisory") is False

    await client._record({"run_id": "budgeted", "prompt_tokens": 1, "completion_tokens": 0, "success": True})
    assert client.tokens_used("budgeted") == 400
    with pytest.raises(ProviderUnavailable):
        client._check_budget("budgeted", tier="advisory")
    assert client.budget_exhausted("budgeted", tier="advisory") is True
    # Same usage is still within the full backbone budget.
    client._check_budget("budgeted", tier="backbone")
    assert client.budget_exhausted("budgeted", tier="backbone") is False

    await client._record({"run_id": "budgeted", "prompt_tokens": 600, "completion_tokens": 0, "success": True})
    with pytest.raises(ProviderUnavailable):
        client._check_budget("budgeted", tier="backbone")


@pytest.mark.asyncio
async def test_chat_json_refuses_when_budget_already_exceeded(client, monkeypatch):
    state = _install_transport(monkeypatch, [_ok()])
    await client._record({"run_id": "full", "prompt_tokens": 400, "completion_tokens": 0, "success": True})

    with pytest.raises(ProviderUnavailable):
        await client.chat_json("sys", "user", run_id="full")  # advisory default: 400 >= 400

    assert state["calls"] == []  # budget check fires before any transport call
    # Backbone tier may still spend up to the full budget.
    parsed, _rec = await client.chat_json("sys", "user", run_id="full", tier="backbone")
    assert parsed == {"ok": True}
    assert len(state["calls"]) == 1


def test_configured_requires_key_model_and_not_offline(client, monkeypatch):
    assert client.configured is True

    monkeypatch.setattr(settings, "offline_mode", True)
    assert client.configured is False
    monkeypatch.setattr(settings, "offline_mode", False)
    assert client.configured is True

    client.key = ""
    assert client.configured is False
    client.key = "test-key"
    client.model = ""
    assert client.configured is False


@pytest.mark.asyncio
async def test_chat_json_not_configured_raises_without_transport(client, monkeypatch):
    state = _install_transport(monkeypatch, [_ok()])
    monkeypatch.setattr(settings, "offline_mode", True)

    with pytest.raises(ProviderUnavailable):
        await client.chat_json("sys", "user", run_id="offline-run")

    assert state["calls"] == []


def test_extract_json_handles_fenced_json():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('```json {"a": 1} ```') == {"a": 1}
    assert _extract_json('```\n{"b": 2}\n```') == {"b": 2}


def test_extract_json_handles_plain_and_wrapped_json():
    assert _extract_json('{"c": 3}') == {"c": 3}
    assert _extract_json('  {"d": 4}  ') == {"d": 4}
    assert _extract_json('Here is the result: {"e": 5} done') == {"e": 5}


def test_extract_json_raises_without_json_object():
    with pytest.raises(ValueError):
        _extract_json("no json here")
    with pytest.raises(ValueError):
        _extract_json("")
