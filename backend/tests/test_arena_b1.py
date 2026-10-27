"""Arena B1: match engine win rules, policy gate, twin isolation."""

import os
import sys

os.environ["OFFLINE_MODE"] = "true"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.arena.engine import play_match  # noqa: E402
from app.simulation.scenarios import SCENARIOS  # noqa: E402
from app.simulation.twin import DigitalTwin  # noqa: E402


def _no_defense(twin, baseline, scenario, history):
    return None


def _weak_defense(twin, baseline, scenario, history):
    return {"label": "Do almost nothing", "actions": [{"action_type": "apply_patch", "asset_id": scenario["source_asset"], "params": {}}],
            "disrupted": 0, "feasible": True}


def test_blue_wins_when_defense_cuts_the_only_path():
    r = play_match(SCENARIOS["red_vs_blue_battle"])
    assert r["winner"] == "blue"
    assert r["target_reachable_final"] is False
    assert r["rounds_played"] >= 1
    assert r["rounds"][0]["target_reachable_after"] is False
    assert r["rounds"][0]["red_path"][-1] == "file-server"


def test_red_wins_when_blue_does_not_defend():
    r = play_match(SCENARIOS["ransomware_activity"], blue_chooser=_no_defense)
    assert r["winner"] == "red"
    assert r["rounds_played"] == 1
    assert r["target_reachable_final"] is True


def test_red_wins_when_blue_defense_fails_to_block():
    r = play_match(SCENARIOS["red_vs_blue_battle"], blue_chooser=_weak_defense)
    assert r["winner"] == "red"
    assert "did not block" in r["reason"]


def test_blue_survives_max_rounds():
    r = play_match(SCENARIOS["red_vs_blue_battle"], max_rounds=1)
    assert r["winner"] == "blue"
    assert r["rounds_played"] == 1
    assert "survived" in r["reason"] or "no validated path" in r["reason"]


def test_match_is_deterministic_and_twin_unchanged():
    twin = DigitalTwin()
    before = twin.config_hash()
    a = play_match(SCENARIOS["lateral_movement"], twin=twin)
    b = play_match(SCENARIOS["lateral_movement"], twin=twin)
    assert twin.config_hash() == before
    assert a["winner"] == b["winner"] and a["rounds"] == b["rounds"]


def test_identity_scenario_plays_a_round():
    r = play_match(SCENARIOS["compromised_identity"])
    assert r["winner"] in ("red", "blue")
    assert r["rounds_played"] >= 1
