"""Opt-in real Meta request; the ordinary suite stays hermetically offline.

Run from backend with RUN_META_INTEGRATION=1 and MODEL_API_KEY configured.
An explicitly requested check fails, rather than skips, if credentials are absent.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.core.config import settings
from app.integrations.meta_client import MetaModelClient
from app.integrations.providers import resolved

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_META_INTEGRATION") != "1",
    reason="live Meta integration disabled (set RUN_META_INTEGRATION=1 + MODEL_API_KEY)",
)


def _configured_meta_client(monkeypatch) -> MetaModelClient:
    # Never use whichever provider happened to be selected in the demo UI.
    # Empty saved settings explicitly select Meta's environment/.env config.
    config = resolved("meta", saved={})
    if not config["api_key"] or not config["model"]:
        pytest.fail("Live Meta check requested: configure MODEL_API_KEY and META_MODEL", pytrace=False)
    monkeypatch.setattr(settings, "offline_mode", False)
    client = MetaModelClient()
    client.apply_provider(config)
    return client


@pytest.fixture
def live_meta_client(monkeypatch):
    # monkeypatch restores offline_mode at teardown; no other test goes live.
    return _configured_meta_client(monkeypatch)


@pytest.mark.asyncio
async def test_live_meta_json(live_meta_client):
    data, usage = await live_meta_client.chat_json("Return ONLY JSON {\"ok\": true}", "ping")
    assert data.get("ok") is True
    assert usage["success"] is True
