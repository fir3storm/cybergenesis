"""Arena B4: match service — play, learn, persist.

Loads the persistent score memory, plays one match with the requested
strategy mode, records the outcome into the memory (self-learning across
matches), stores the match row, and returns everything the spectate UI
needs. Modes: ai (Meta picks among validated moves, learned fallback),
learned (score memory only), deterministic (B1 defaults).
"""

from app import models
from app.arena.ai import AiBlueChooser, AiRedChooser
from app.arena.engine import deterministic_blue, deterministic_red, play_match_async
from app.arena.learning import ArenaMemory, learned_blue_chooser, learned_red_chooser
from app.core.config import settings
from app.simulation.scenarios import SCENARIOS
from app.simulation.twin import DigitalTwin


class ArenaError(ValueError):
    pass


def _resolve(db, scenario_id: str, custom_twin_id: str | None) -> tuple[dict, DigitalTwin]:
    if scenario_id in SCENARIOS:
        scenario = SCENARIOS[scenario_id]
    else:
        row = db.get(models.CustomScenarioDefinition, scenario_id)
        if not row:
            raise ArenaError(f"unknown scenario: {scenario_id}")
        scenario = {**row.definition, "id": row.id, "name": row.name}
    if custom_twin_id:
        trow = db.get(models.CustomTwinDefinition, custom_twin_id)
        if not trow:
            raise ArenaError(f"unknown custom twin: {custom_twin_id}")
        return scenario, DigitalTwin.from_dict(trow.assets, trow.connections)
    return scenario, DigitalTwin()


def _choosers(mode: str, memory: ArenaMemory):
    if mode == "ai":
        return AiRedChooser(memory), AiBlueChooser(memory)
    if mode == "learned":
        return learned_red_chooser(memory), learned_blue_chooser(memory)
    if mode == "deterministic":
        return deterministic_red, deterministic_blue
    raise ArenaError(f"unknown arena mode: {mode} (use ai | learned | deterministic)")


async def play_and_store(db, scenario_id: str, mode: str = "ai", max_rounds: int | None = None,
                         seed: int = 42, custom_twin_id: str | None = None) -> dict:
    scenario, twin = _resolve(db, scenario_id, custom_twin_id)
    memory = ArenaMemory.load(settings.arena_memory_path)
    red, blue = _choosers(mode, memory)
    result = await play_match_async(scenario, twin=twin, max_rounds=max_rounds, seed=seed,
                                    red_chooser=red, blue_chooser=blue)
    memory.record_match(result)
    memory.save(settings.arena_memory_path)
    row = models.ArenaMatch(scenario_id=scenario_id, winner=result["winner"], reason=result["reason"],
                            mode=mode, rounds_played=result["rounds_played"], payload=result)
    db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "created_at": row.created_at.isoformat() if row.created_at else None,
            "mode": mode, **result, "memory": memory.summary()}


def build_arena_certificate(db, match_id: str) -> dict:
    """B6 winner proof: signed, self-contained arena certificate (verify_cert.py checks it offline)."""
    import hashlib
    import hmac
    import json

    from app.verification.certificate import DEMO_KEY

    row = db.get(models.ArenaMatch, match_id)
    if not row:
        raise ArenaError("arena match not found")
    scenario, _twin = _resolve(db, row.scenario_id, None)
    p = row.payload or {}
    cert: dict = {
        "kind": "arena_match",
        "version": 1,
        "match_id": row.id,
        "scenario": {"id": row.scenario_id, "source": scenario.get("source_asset"), "target": scenario.get("target_asset"),
                     "verification_kind": scenario.get("verification_kind"), "identity": scenario.get("identity")},
        "mode": row.mode,
        "winner": row.winner,
        "reason": row.reason,
        "rounds_played": row.rounds_played,
        "rounds": p.get("rounds", []),
        "target_reachable_final": p.get("target_reachable_final"),
        "total_disrupted": p.get("total_disrupted"),
        "final_twin": p.get("final_twin"),
    }
    canonical = json.dumps({k: cert[k] for k in sorted(cert)}, sort_keys=True, default=str)
    cert["signature"] = hmac.new(DEMO_KEY.encode(), canonical.encode(), hashlib.sha256).hexdigest()
    return cert


def league(db) -> dict:
    rows = db.query(models.ArenaMatch).all()
    table: dict[str, dict] = {}
    for r in rows:
        t = table.setdefault(r.scenario_id, {"scenario_id": r.scenario_id, "matches": 0, "red_wins": 0, "blue_wins": 0})
        t["matches"] += 1
        t["red_wins" if r.winner == "red" else "blue_wins"] += 1
    return {"matches": len(rows),
            "red_wins": sum(1 for r in rows if r.winner == "red"),
            "blue_wins": sum(1 for r in rows if r.winner == "blue"),
            "by_scenario": sorted(table.values(), key=lambda t: t["scenario_id"])}
