"""Arena B2: learned choosers improve from recorded match outcomes."""

import os
import sys

os.environ["OFFLINE_MODE"] = "true"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.arena.engine import play_match
from app.arena.learning import ArenaMemory, learned_blue_chooser, learned_red_chooser
from app.simulation.scenarios import SCENARIOS
from app.simulation.twin import DigitalTwin


def test_memory_records_round_outcomes():
    mem = ArenaMemory()
    mem.record_match(play_match(SCENARIOS["red_vs_blue_battle"]))
    assert mem.data["matches"] == 1
    assert mem.data["blue"] and next(iter(mem.data["blue"].values()))["blocks"] == 1
    assert mem.data["red"] and next(iter(mem.data["red"].values()))["reaches"] == 0


def test_learned_blue_repeats_what_blocked():
    mem = ArenaMemory()
    mem.record_match(play_match(SCENARIOS["red_vs_blue_battle"]))
    r = play_match(SCENARIOS["red_vs_blue_battle"], blue_chooser=learned_blue_chooser(mem))
    assert r["winner"] == "blue"
    assert mem.blue_rate(r["rounds"][0]["blue_candidate"]) > 0.5


def test_learned_red_avoids_a_path_that_never_reached():
    mem = ArenaMemory({"blue": {}, "red": {"internet > firewall > web-server > app-server > file-server": {"plays": 4, "reaches": 0}}, "matches": 4})
    twin = DigitalTwin()
    twin.apply_attack(SCENARIOS["red_vs_blue_battle"])
    path = learned_red_chooser(mem)(twin, SCENARIOS["red_vs_blue_battle"], [])
    # an unexplored validated path (prior 0.5) beats the 1/6 learned-dead path, if one exists;
    # otherwise the chooser still returns the only validated path
    assert path is not None
    if len(path) and " > ".join(path) in mem.data["red"]:
        assert mem.red_rate(path) >= 0.5


def test_memory_persists_to_disk(tmp_path):
    mem = ArenaMemory()
    mem.record_match(play_match(SCENARIOS["ransomware_activity"]))
    p = tmp_path / "arena_memory.json"
    mem.save(p)
    loaded = ArenaMemory.load(p)
    assert loaded.data == mem.data
    assert ArenaMemory.load(tmp_path / "missing.json").data["matches"] == 0


def test_learned_blue_prefers_blocking_over_perfect_history_nonblocking():
    """Gap 10 regression: a blocking candidate beats a non-blocking one even
    when the non-blocking label has a perfect learned rate and every blocking
    label has a terrible one. In learned_blue_chooser's ascending min() key,
    blocked=True -> (not blocked) is False (0), which sorts first, so the
    blocking preference is the primary key and learned rate only breaks
    ties within a blocked class."""
    from app.simulation.candidates import evaluate_candidates

    scenario = SCENARIOS["ransomware_activity"]
    twin = DigitalTwin()
    baseline = twin.clone()
    twin.apply_attack(scenario, seed=42)
    proposal = [dict(a) for a in (scenario.get("expected_defense") or [])]
    cands = [c for c in evaluate_candidates(twin, baseline, scenario, proposal) if c.get("feasible")]
    blocking = [c for c in cands if c.get("blocked")]
    nonblocking = [c for c in cands if not c.get("blocked")]
    assert blocking and nonblocking  # precondition: both classes exist here

    blue: dict = {}
    for c in nonblocking:  # perfect history: always blocked, zero disruption
        blue[c["label"]] = {"plays": 20, "blocks": 20, "disrupted": 0}
    for c in blocking:  # worst history: never blocked, heavy disruption
        blue[c["label"]] = {"plays": 20, "blocks": 0, "disrupted": 200}
    mem = ArenaMemory({"blue": blue, "red": {}, "matches": 20})
    assert mem.blue_rate(nonblocking[0]["label"]) > mem.blue_rate(blocking[0]["label"])

    twin2 = DigitalTwin()
    baseline2 = twin2.clone()
    twin2.apply_attack(scenario, seed=42)
    choice = learned_blue_chooser(mem)(twin2, baseline2, scenario, [])
    assert choice is not None
    assert choice.get("blocked") is True


def test_learning_accumulates_across_matches():
    mem = ArenaMemory()
    for _ in range(3):
        mem.record_match(play_match(SCENARIOS["lateral_movement"], blue_chooser=learned_blue_chooser(mem),
                                    red_chooser=learned_red_chooser(mem)))
    assert mem.data["matches"] == 3
    assert mem.summary()["blue_learned"] >= 1
