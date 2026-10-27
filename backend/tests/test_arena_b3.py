"""Arena B3: AI choosers only pick validated options; failures fall back offline."""

import os
import sys

os.environ["OFFLINE_MODE"] = "true"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.arena import ai as arena_ai
from app.arena.engine import play_match_async
from app.integrations.meta_client import ProviderUnavailable
from app.simulation.scenarios import SCENARIOS


class _Ctx:
    def __enter__(self): return self
    def __exit__(self, *a): return False


@pytest.mark.asyncio
async def test_ai_blue_rejects_unknown_label_and_falls_back(monkeypatch):
    async def bad_chat(system, user, run_id=None):
        return {"label": "rm -rf everything", "rationale": "untrusted"}, {}
    monkeypatch.setattr(arena_ai.meta_client, "chat_json", bad_chat)
    monkeypatch.setattr(arena_ai.meta_client, "use_budget_tier", lambda tier: _Ctx())
    r = await play_match_async(SCENARIOS["red_vs_blue_battle"], blue_chooser=arena_ai.AiBlueChooser())
    assert r["rounds"][0]["blue_chosen_by"] == "offline"  # invalid AI pick never applied
    assert r["winner"] == "blue"  # deterministic fallback still holds


@pytest.mark.asyncio
async def test_ai_provider_down_falls_back_offline(monkeypatch):
    async def down_chat(system, user, run_id=None):
        raise ProviderUnavailable("down")
    monkeypatch.setattr(arena_ai.meta_client, "chat_json", down_chat)
    monkeypatch.setattr(arena_ai.meta_client, "use_budget_tier", lambda tier: _Ctx())
    chooser = arena_ai.AiRedChooser()
    r = await play_match_async(SCENARIOS["ransomware_activity"], red_chooser=chooser)
    assert chooser.last_mode == "offline"
    assert r["rounds"][0]["red_chosen_by"] == "offline"
    assert r["winner"] in ("red", "blue")


@pytest.mark.asyncio
async def test_ai_valid_pick_is_used_and_labelled_live(monkeypatch):
    async def good_chat(system, user, run_id=None):
        if "Blue Team" in system:
            # pick whichever feasible label the prompt offered (parse first label)
            import re
            m = re.search(r"'label': '([^']+)'", user) or re.search(r'"label": "([^"]+)"', user)
            return {"label": m.group(1) if m else "?", "rationale": "least disruption"}, {}
        return {"path_index": 0, "rationale": "shortest"}, {}
    monkeypatch.setattr(arena_ai.meta_client, "chat_json", good_chat)
    monkeypatch.setattr(arena_ai.meta_client, "use_budget_tier", lambda tier: _Ctx())
    r = await play_match_async(SCENARIOS["red_vs_blue_battle"],
                               red_chooser=arena_ai.AiRedChooser(), blue_chooser=arena_ai.AiBlueChooser())
    assert r["rounds"][0]["blue_chosen_by"] == "live"
    assert r["rounds"][0]["red_chosen_by"] == "live"
