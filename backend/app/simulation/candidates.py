"""Simulate-before-acting: replay candidate defenses on cloned twins and score the trade-off."""

from app.policies.engine import evaluate
from app.simulation.twin import DigitalTwin


def _score(clone: DigitalTwin, baseline: DigitalTwin, scenario: dict, actions: list[dict], label: str, origin: str,
           original_path: list[str] | None = None) -> dict:
    applied = []
    for a in actions:
        d = evaluate(a["action_type"], a["asset_id"], a.get("params", {}), clone)
        if not d.approved:
            return {"label": label, "origin": origin, "actions": actions, "feasible": False,
                    "blocked": False, "disrupted": None, "detail": f"policy rejected: {'; '.join(d.reasons)}"}
        try:
            clone.apply_action(a["action_type"], a["asset_id"], a.get("params", {}))
            applied.append(a["action_type"])
        except ValueError as e:
            return {"label": label, "origin": origin, "actions": actions, "feasible": False,
                    "blocked": False, "disrupted": None, "detail": str(e)}
    result = clone.attempt_attack_objective(scenario)
    disrupted = clone.legitimate_disrupted(baseline)
    new_path = clone.find_path(scenario["source_asset"], scenario["target_asset"])
    return {"label": label, "origin": origin, "actions": actions, "feasible": True,
            "blocked": bool(result["objective_blocked"]),
            "path_blocked": bool(original_path) and new_path != original_path,
            "disrupted": disrupted,
            "detail": f"applied {applied}; objective_blocked={result['objective_blocked']}"}


def evaluate_candidates(attacked: DigitalTwin, baseline: DigitalTwin, scenario: dict,
                        proposal_actions: list[dict]) -> list[dict]:
    """Candidates: the agent proposal + mechanically distinct alternatives from the live graph."""
    src, tgt = scenario["source_asset"], scenario["target_asset"]
    path = attacked.find_path(src, tgt) or []
    candidates: list[tuple[str, str, list[dict]]] = [("Agent proposal", "ai", proposal_actions)]
    if scenario["verification_kind"] == "reachability":
        candidates.append((f"Isolate source ({src})", "simulated",
                           [{"action_type": "isolate_asset", "asset_id": src, "params": {}}]))
        for i in range(len(path) - 1):
            s, t = path[i], path[i + 1]
            candidates.append((f"Segment {s} → {t}", "simulated",
                               [{"action_type": "block_connection", "asset_id": s, "params": {"source": s, "target": t}}]))
        if path:
            candidates.append((f"Patch source ({src}) only", "simulated",
                               [{"action_type": "apply_patch", "asset_id": src, "params": {}}]))
    else:
        ident = scenario.get("identity") or "admin-01"
        candidates.append(("Revoke session only", "simulated",
                           [{"action_type": "revoke_session", "asset_id": "identity-provider", "params": {"identity": ident}}]))
        candidates.append(("Rotate credential only", "simulated",
                           [{"action_type": "rotate_credential", "asset_id": "identity-provider", "params": {"identity": ident}}]))
    seen: set[str] = set()
    results = []
    for label, origin, actions in candidates:
        sig = str(sorted(str(a) for a in actions))
        if sig in seen:
            continue
        seen.add(sig)
        results.append(_score(attacked.clone(), baseline, scenario, [dict(a) for a in actions], label, origin, original_path=path))
    # best trade-off first: blocked, then least disruption; agent proposal wins ties (it reasoned about context)
    results.sort(key=lambda r: (not r["blocked"], r["disrupted"] if r["disrupted"] is not None else 99,
                                0 if r["origin"] == "ai" else 1))
    return results
