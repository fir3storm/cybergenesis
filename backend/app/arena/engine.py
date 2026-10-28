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

from datetime import UTC, datetime
from itertools import pairwise

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


def simulate_blue(twin: DigitalTwin, baseline: DigitalTwin, scenario: dict, history: list[dict]) -> dict | None:
    """Simulation-best: pick the top-ranked candidate from the full evaluated
    candidate list (not just the agent proposal). This is the "simulate
    before acting" strategy used as the offline benchmark."""
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
    initial_twin = arena_twin.to_dict()
    limit = max_rounds if max_rounds is not None else int(scenario.get("max_rounds") or 5)
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("max_rounds must be an integer between 1 and 10")
    rounds: list[dict] = []
    decisions: list[dict] = []
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
            red_path = await _maybe_await(red_chooser(arena_twin.clone(), scenario, rounds))
            if red_path is None:
                winner, reason = "blue", "red found no validated path to the target"
                break
            if red_path not in enumerate_paths(arena_twin, scenario["source_asset"], scenario["target_asset"]):
                raise ValueError("red route is not a validated path")
        round_scenario = {**scenario, "arena_red_path": red_path}
        cand = await _maybe_await(blue_chooser(arena_twin.clone(), baseline.clone(), round_scenario, rounds))
        applied: list[dict] = []
        rejected: list[str] = []
        disrupted = None
        trial = arena_twin.clone()
        if cand is not None:
            disrupted = cand.get("disrupted")
            for a in cand.get("actions", []):
                d = evaluate(a["action_type"], a["asset_id"], a.get("params", {}), trial)
                if not d.approved:
                    rejected.append(f"{a['action_type']}: {'; '.join(d.reasons)}")
                    continue
                try:
                    trial.apply_action(a["action_type"], a["asset_id"], a.get("params", {}))
                    applied.append(a)
                except ValueError as e:
                    rejected.append(f"{a['action_type']}: {e}")
        if not rejected:
            arena_twin = trial
        else:
            applied = []  # A proposal is atomic: no partial defense survives rejection.
        disrupted = arena_twin.legitimate_disrupted(baseline)
        reached_after = _red_reached(arena_twin, scenario)
        selected_survives = reached_after
        if red_path:
            graph = arena_twin.live_graph(scenario["target_asset"])
            selected_survives = reached_after and all(graph.has_edge(a, b) for a, b in pairwise(red_path))
        evidence_ref = f"arena-round-{n}"
        for role, chooser, action, assets in (
            ("adversary_simulator", red_chooser, {"path": red_path}, red_path or [scenario["source_asset"]]),
            ("defense_strategist", blue_chooser, {"actions": (cand or {}).get("actions", [])},
             [a["asset_id"] for a in (cand or {}).get("actions", [])]),
        ):
            provenance = getattr(chooser, "last_decision", {})
            decisions.append({"agent_role": role, "evidence_refs": [evidence_ref], "asset_ids": assets,
                              "action": action, "justification": provenance.get("rationale", "Deterministic validated strategy"),
                              "confidence": provenance.get("confidence", 1.0),
                              "model_id": provenance.get("model_id", "deterministic"),
                              "timestamp": datetime.now(UTC).isoformat(),
                              "mode": getattr(chooser, "last_mode", "offline"),
                              "fallback_reason": provenance.get("fallback_reason")})
        rounds.append({
            "round": n,
            "evidence_ref": evidence_ref,
            "twin_after": arena_twin.to_dict(),
            "selected_path_blocked": not selected_survives,
            "red_path": red_path,
            "red_reached_before": True,
            "blue_candidate": (cand or {}).get("label"),
            "blue_chosen_by": (cand or {}).get("chosen_by"),
            "red_chosen_by": getattr(red_chooser, "last_mode", None),
            "blue_actions": applied,
            "policy_rejections": rejected,
            "disrupted": disrupted,
            "target_reachable_after": reached_after,
            "winner_so_far": "red" if selected_survives else ("adapting" if reached_after else "blue"),
        })
        if selected_survives:
            winner, reason = "red", f"defense in round {n} did not block the objective: red reached the target"
            break
    if winner is None:
        if _red_reached(arena_twin, scenario):
            winner, reason = "red", "target still reachable when rounds ran out"
        else:
            winner, reason = "blue", f"blue survived {limit} round(s) with the target blocked"

    return {
        "initial_twin": initial_twin,
        "decisions": decisions,
        "winner": winner,
        "reason": reason,
        "scenario_id": scenario.get("id"),
        "max_rounds": limit,
        "rounds_played": len(rounds),
        "rounds": rounds,
        "target_reachable_final": _red_reached(arena_twin, scenario),
        "total_disrupted": arena_twin.legitimate_disrupted(baseline),
        "final_twin": arena_twin.to_dict(),
    }


def play_match(scenario: dict, twin: DigitalTwin | None = None, max_rounds: int | None = None, seed: int = 42,
               red_chooser=deterministic_red, blue_chooser=deterministic_blue) -> dict:
    """Sync match with sync choosers. The caller's twin is never mutated."""
    import asyncio

    return asyncio.run(play_match_async(scenario, twin=twin, max_rounds=max_rounds, seed=seed,
                                        red_chooser=red_chooser, blue_chooser=blue_chooser))
