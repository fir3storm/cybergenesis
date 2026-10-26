"""Opt-in live Meta integration test. Skipped unless RUN_META_INTEGRATION=1 and a key exist."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from app.integrations.meta_client import meta_client  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_META_INTEGRATION") != "1" or not meta_client.configured,
    reason="live Meta integration disabled (set RUN_META_INTEGRATION=1 + MODEL_API_KEY)",
)


@pytest.mark.asyncio
async def test_live_meta_json():
    data, usage = await meta_client.chat_json("Return ONLY JSON {\"ok\": true}", "ping")
    assert data.get("ok") is True
    assert usage["success"] is True
