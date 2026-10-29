"""Multi-provider Settings: catalogue, activation, key secrecy, wire routing."""

import os
import sys

os.environ["OFFLINE_MODE"] = "true"
os.environ["SIM_STEP_DELAY_MS"] = "0"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.integrations import providers
from app.integrations.meta_client import meta_client
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "provider_settings_path", str(tmp_path / "provider_settings.json"))
    monkeypatch.setattr(settings, "offline_mode", True)
    yield
    meta_client.apply_provider(providers.resolved("meta"))


def test_catalogue_lists_four_providers_without_keys():
    body = client.get("/api/settings/providers").json()
    ids = {p["id"] for p in body["providers"]}
    assert ids == {"meta", "commandcode", "kilo", "google"}
    assert body["api_keys_exposed"] is False
    for p in body["providers"]:
        assert "api_key" not in p and p["base_url"].startswith("https://")


def test_activate_google_switches_client_and_persists():
    r = client.post("/api/settings/provider", json={"provider": "google", "api_key": "test-google-key", "model": "gemini-2.5-flash"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] == "google" and body["api_key_exposed"] is False
    assert "test-google-key" not in r.text
    # The client is now pointed at Google with a key+model saved. `configured`
    # reports whether a *live* call would go out — false under OFFLINE_MODE
    # (hermetic tests) even though the key and model are stored.
    assert meta_client.provider_id == "google" and meta_client.model == "gemini-2.5-flash"
    assert meta_client.key == "test-google-key"
    assert meta_client.base == "https://generativelanguage.googleapis.com/v1beta/openai"

    status = client.get("/api/models/status").json()
    assert status["provider"] == "google" and status["api_key_exposed"] is False

    # a later catalogue read still shows it active, key never returned
    cat = {p["id"]: p for p in client.get("/api/settings/providers").json()["providers"]}
    assert cat["google"]["active"] is True and cat["google"]["configured"] is True


def test_activate_unknown_provider_422_and_empty_key_keeps_stored():
    assert client.post("/api/settings/provider", json={"provider": "magic"}).status_code == 422
    client.post("/api/settings/provider", json={"provider": "kilo", "api_key": "kilo-key-1", "model": "some/model"})
    r = client.post("/api/settings/provider", json={"provider": "kilo", "api_key": "", "model": "other/model"})
    # stored key kept, model updated — the response flags the saved state, not
    # whether a live call would actually go out (that is OFFLINE_MODE's job)
    assert r.json()["configured"] is False  # OFFLINE_MODE in this test session
    assert meta_client.key == "kilo-key-1" and meta_client.model == "other/model"


def test_base_url_must_be_provider_host_or_localhost():
    bad = client.post("/api/settings/provider", json={"provider": "meta", "base_url": "https://evil.example.com/v1"})
    assert bad.status_code == 422 and "not allowed" in bad.text
    plain = client.post("/api/settings/provider", json={"provider": "meta", "base_url": "http://api.meta.ai/v1"})
    assert plain.status_code == 422
    ok = client.post("/api/settings/provider", json={"provider": "meta", "base_url": "https://api.meta.ai/v1/"})
    assert ok.status_code == 200 and ok.json()["base_url"] == "https://api.meta.ai/v1"
    local = client.post("/api/settings/provider", json={"provider": "kilo", "base_url": "http://localhost:4000/v1"})
    assert local.status_code == 200


def test_generated_admin_token_only_handed_to_loopback(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    monkeypatch.setattr(settings, "admin_token", "generated-test-token")
    monkeypatch.setattr(app.state, "generated_admin_token", "generated-test-token", raising=False)
    # TestClient's peer is "testclient", i.e. not this machine's loopback
    assert "admin_token" not in client.get("/api/settings/providers").json()
    assert client.post("/api/settings/provider", json={"provider": "meta"}).status_code == 403
    import app.main as main_mod
    monkeypatch.setattr(main_mod, "_is_loopback", lambda request: True)
    assert client.get("/api/settings/providers").json()["admin_token"] == "generated-test-token"
    monkeypatch.setattr(settings, "admin_token", "")


@pytest.mark.asyncio
async def test_chat_json_routes_to_active_provider(monkeypatch):
    client.post("/api/settings/provider", json={"provider": "commandcode", "api_key": "cmd_test", "model": "test-model"})
    monkeypatch.setattr(settings, "offline_mode", False)
    seen = {}

    class FakeResp:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": "{\"ok\": true}"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None):
            seen.update(url=url, headers=headers, body=json)
            return FakeResp()

    import app.integrations.meta_client as mc
    monkeypatch.setattr(mc.httpx, "AsyncClient", FakeClient)
    data, rec = await meta_client.chat_json("sys", "user", run_id="provider-test")
    assert data == {"ok": True} and rec["success"] is True
    assert seen["url"] == "https://api.commandcode.ai/provider/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer cmd_test"
    assert seen["body"]["model"] == "test-model"
