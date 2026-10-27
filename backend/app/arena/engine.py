"""Arena B1: red-vs-blue match engine on the synthetic twin.

A match is a sequence of rounds on one cloned twin:
  1. Red picks a validated attack path (live graph only, typed steps).
  2. Blue picks a candidate defense; every action goes through the same
     deterministic policy engine as the main loop, then is applied.
  3. The verifier's replay check decides the round: if the objective is
     still reachable/granted after the defense, Red reached the target
     and wins. If no red path remains, or max_rounds are survived with
     the target blocked, Blue wins.

Strategies are injected callables, so B2 (learned scores) and B3 (Meta AI
choices) can replace the deterministic defaults without touching the
engine. Synthetic data only; no payloads, no shell, no network.
"""

from app.agents.red_team import enumerate_paths, sort_campaign_paths
from app.policies.engine import evaluate
from app.simulation.candidates import evaluate_candidates
from app.simulation.twin import DigitalTwin


def deterministic_red(twin: DigitalTwin, scenario: dict, history: list[dict]) -> list[str] | None:
    """Weakness-ranked shortest validated path from source to target."""
    paths = sort_campaign_paths(twin, enumerate_paths(twin, scenario["source_asset"], scenario["target_asset"]))
    return paths[0] if paths else None


def deterministic_blue(twin: DigitalTwin, baseline: DigitalTwin, scenario: dict, history: list[dict]) -> dict | None:
    """Best-ranked feasible candidate (blocked, then least disruption)."""
    proposal = scenario.get("expected_defense") or []
    cands = evaluate_candidates(twin, baseline, scenario, [dict(a) for a in proposal])
    feasible = [c for c in cands if c.get("feasible")]
    return feasible[0] if feasible else None


def _objective(twin: DigitalTwin, scenario: dict) -> dict:
    return twin.attempt_attack_objective(scenario)


def _red_reached(twin: DigitalTwin, scenario: dict) -> bool:
    obj = _objective(twin, scenario)
    if scenario.get("verification_kind") == "reachability":
        return bool(obj.get("reachable"))
    return bool(obj.get("access_granted"))


async def _maybe_await(value):
    import inspect

    return await value if inspect.isawaitable(value) else value


async def play_match_async(scenario: dict, twin: DigitalTwin | None = None, max_rounds: int | None = None, seed: int = 42,
                           red_chooser=deterministic_red, blue_chooser=deterministic_blue) -> dict:
    """Async match: choosers may be sync or async (e.g. Meta AI choosers)."""
    arena_twin = (twin or DigitalTwin()).clone()
    baseline = arena_twin.clone()
    arena_twin.apply_attack(scenario, seed=seed)
    limit = max_rounds if max_rounds is not None else int(scenario.get("max_rounds") or 5)
    rounds: list[dict] = []
    winner: str | None = None
    reason = ""

    for n in range(1, limit + 1):
        if not _red_reached(arena_twin, scenario):
            winner = "blue"
            reason = ("blue defense held: red has no validated path left" if rounds
                      else "target already unreachable: red has no validated path")
            break
        red_path = None
        if scenario.get("verification_kind") == "reachability":
            red_path = await _maybe_await(red_chooser(arena_twin, scenario, rounds))
            if red_path is None:
                winner, reason = "blue", "red found no validated path to the target"
                break
        cand = await _maybe_await(blue_chooser(arena_twin.clone(), baseline, scenario, rounds))
        applied: list[dict] = []
        rejected: list[str] = []
        disrupted = None
        if cand is not None:
            disrupted = cand.get("disrupted")
            for a in cand.get("actions", []):
                d = evaluate(a["action_type"], a["asset_id"], a.get("params", {}), arena_twin)
                if not d.approved:
                    rejected.append(f"{a['action_type']}: {'; '.join(d.reasons)}")
                    continue
                try:
                    arena_twin.apply_action(a["action_type"], a["asset_id"], a.get("params", {}))
                    applied.append(a)
                except ValueError as e:
                    rejected.append(f"{a['action_type']}: {e}")
        reached_after = _red_reached(arena_twin, scenario)
        rounds.append({
            "round": n,
            "red_path": red_path,
            "red_reached_before": True,
            "blue_candidate": (cand or {}).get("label"),
            "blue_chosen_by": (cand or {}).get("chosen_by"),
            "red_chosen_by": getattr(red_chooser, "last_mode", None),
            "blue_actions": applied,
            "policy_rejections": rejected,
            "disrupted": disrupted,
            "target_reachable_after": reached_after,
            "winner_so_far": "red" if reached_after else "blue",
        })
        if reached_after:
            winner, reason = "red", f"defense in round {n} did not block the objective: red reached the target"
            break
    if winner is None:
        if _red_reached(arena_twin, scenario):
            winner, reason = "red", "target still reachable when rounds ran out"
        else:
            winner, reason = "blue", f"blue survived {limit} round(s) with the target blocked"

    return {
        "winner": winner,
        "reason": reason,
        "scenario_id": scenario.get("id"),
        "max_rounds": limit,
        "rounds_played": len(rounds),
        "rounds": rounds,
        "target_reachable_final": _red_reached(arena_twin, scenario),
        "total_disrupted": sum(r["disrupted"] or 0 for r in rounds),
        "final_twin": arena_twin.to_dict(),
    }


def play_match(scenario: dict, twin: DigitalTwin | None = None, max_rounds: int | None = None, seed: int = 42,
               red_chooser=deterministic_red, blue_chooser=deterministic_blue) -> dict:
    """Sync match with sync choosers. The caller's twin is never mutated."""
    import asyncio

    return asyncio.run(play_match_async(scenario, twin=twin, max_rounds=max_rounds, seed=seed,
                                        red_chooser=red_chooser, blue_chooser=blue_chooser))
