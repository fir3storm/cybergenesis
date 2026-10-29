"""Exercise the opt-in integration setup without making provider requests."""

import pytest
import test_meta_live_integration as live

from app.core.config import settings
from app.integrations import providers
from app.integrations.meta_client import meta_client


def _client(monkeypatch):
    factory = getattr(live, "_configured_meta_client", None)
    assert callable(factory), "live test needs an isolated explicit-Meta setup"
    return factory(monkeypatch)


def test_live_setup_enables_only_its_own_scope_and_selects_meta(monkeypatch):
    monkeypatch.setattr(settings, "model_api_key", "fake-meta-key")
    monkeypatch.setattr(settings, "meta_model", "meta-test-model")
    monkeypatch.setattr(settings, "model_api_base_url", "https://api.meta.ai/v1")
    monkeypatch.setattr(providers, "load_saved", lambda: {
        "active": "google", "providers": {"google": {"api_key": "fake-google-key"}},
    })
    original = (meta_client.provider_id, meta_client.key, meta_client.model)
    assert settings.offline_mode is True
    with monkeypatch.context() as scope:
        client = _client(scope)
        assert client is not meta_client
        assert client.configured is True
        assert (client.provider_id, client.key, client.model) == ("meta", "fake-meta-key", "meta-test-model")
    assert settings.offline_mode is True
    assert (meta_client.provider_id, meta_client.key, meta_client.model) == original


def test_explicit_live_request_without_credentials_fails_instead_of_skipping(monkeypatch):
    monkeypatch.setattr(settings, "model_api_key", "")
    monkeypatch.setattr(providers, "load_saved", lambda: {
        "active": "meta", "providers": {"meta": {"api_key": "saved-key-must-not-be-used"}},
    })
    with pytest.raises(pytest.fail.Exception, match="MODEL_API_KEY"):
        _client(monkeypatch)


@pytest.mark.asyncio
async def test_live_integration_uses_real_client_with_mock_transport(monkeypatch):
    import httpx

    import app.integrations.meta_client as client_module

    monkeypatch.setattr(settings, "model_api_key", "fake-meta-key")
    monkeypatch.setattr(settings, "meta_model", "meta-test-model")
    monkeypatch.setattr(settings, "model_api_base_url", "https://api.meta.ai/v1")
    seen = []
    real_async_client = httpx.AsyncClient

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": '{"ok":true}'}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        })

    monkeypatch.setattr(client_module.httpx, "AsyncClient", lambda **kw: real_async_client(
        transport=httpx.MockTransport(respond), **kw))
    client = _client(monkeypatch)
    await live.test_live_meta_json(client)
    assert len(seen) == 1
    assert str(seen[0].url) == "https://api.meta.ai/v1/chat/completions"
    assert seen[0].headers["authorization"] == "Bearer fake-meta-key"
