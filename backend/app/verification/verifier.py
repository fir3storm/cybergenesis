"""Independent verification: replay the same attack objective. Computed, never hardcoded."""

import networkx as nx

from app.schemas import VerificationResult
from app.simulation.twin import DigitalTwin


def _min_edge_cut(baseline: DigitalTwin, scenario: dict) -> int | None:
    if scenario["verification_kind"] != "reachability":
        return None
    g = baseline.live_graph(scenario["target_asset"])  # directed, vulnerability-gated — same semantics as find_path
    try:
        return len(nx.minimum_edge_cut(g, scenario["source_asset"], scenario["target_asset"]))
    except Exception:  # noqa: BLE001 - no path / missing node -> optimum 0
        return 0


def _edges_removed(baseline: DigitalTwin, after: DigitalTwin) -> int:
    # connections (undirected pairs) fully or partially cut — comparable to the minimum edge cut.
    # A one-way outbound block counts as one connection cut, same as the undirected optimum counts it.
    b = {(c["source"], c["target"]): int(c.get("dir_forward_active", c["active"])) + int(c.get("dir_reverse_active", c["active"]))
         for c in baseline.to_dict()["connections"] if c["traversable"]}
    a = {(c["source"], c["target"]): int(c.get("dir_forward_active", c["active"])) + int(c.get("dir_reverse_active", c["active"]))
         for c in after.to_dict()["connections"] if c["traversable"]}
    return sum(1 for k in b if a.get(k, 0) < b[k])


def _breach_probability(twin: DigitalTwin, scenario: dict, trials: int = 1000, seed: int = 42) -> tuple[float, list[float]] | None:
    """Monte Carlo (deterministic per seed): arc exploit_probability =
    clamp(0.15 + 0.6*(1 - target_posture) + 0.15*len(target_vulns), 0, 0.95).
    Returns (risk_pct, [ci95_low, ci95_high])."""
    import math
    import random

    if scenario["verification_kind"] != "reachability":
        return None
    src, tgt = scenario["source_asset"], scenario["target_asset"]
    postures = {a["id"]: a for a in twin.to_dict()["assets"]}
    rng = random.Random(seed)
    hits = 0
    isolated = set(twin.assets_status_isolated())
    # same compiled graph the reachability checks use, so quarantine / ACL
    # defenses that block the path also lower the risk estimate
    live = twin.live_graph(tgt)
    arcs: dict[str, list[tuple[str, float]]] = {}
    for node in twin.graph.nodes:
        lst = []
        for nxt in twin.graph.successors(node):
            if nxt in isolated or not twin.dir_active.get((node, nxt), False) or not live.has_edge(node, nxt):
                continue
            if not twin.graph[node][nxt].get("traversable", False) or not twin.hop_allowed(nxt, tgt):
                continue
            dest = postures[nxt]
            lst.append((nxt, max(0.0, min(0.95, 0.15 + 0.6 * (1 - dest["posture"]) + 0.15 * len(dest["vulnerabilities"])))))
        arcs[node] = lst
    for _ in range(trials):
        seen = {src}; stack = [src]
        while stack:
            node = stack.pop()
            if node == tgt:
                break
            for nxt, p in arcs.get(node, []):
                if nxt not in seen and rng.random() < p:
                    seen.add(nxt); stack.append(nxt)
        if tgt in seen:
            hits += 1
    risk = hits / trials
    margin = 1.96 * math.sqrt(risk * (1 - risk) / trials) if 0 < risk < 1 else 0.0
    return round(100.0 * risk, 1), [round(100.0 * max(0.0, risk - margin), 1), round(100.0 * min(1.0, risk + margin), 1)]


def disrupted_users(after: DigitalTwin, baseline: DigitalTwin) -> int:
    from app.simulation.twin import LEGITIMATE_PAIRS

    total = 0
    for s, t, users in LEGITIMATE_PAIRS:
        # legitimate traffic ignores the attacker vulnerability gate (see
        # DigitalTwin.legitimate_reachable): patching a hop is not disruption
        if s in after.graph and baseline.legitimate_reachable(s, t) and not after.legitimate_reachable(s, t):
            total += users
    return total


def verify(scenario: dict, baseline: DigitalTwin, after: DigitalTwin,
           baseline_result: dict, t_attack_start: float, t_detected: float, t_contained: float | None) -> VerificationResult:
    after_result = after.attempt_attack_objective(scenario)
    checks = []
    if scenario["verification_kind"] == "reachability":
        checks.append({"name": "attack_objective_blocked", "passed": bool(after_result["objective_blocked"]),
                       "detail": f"path after defense: {after_result['path']}"})
        checks.append({"name": "target_unreachable", "passed": not after.reachable(scenario["source_asset"], scenario["target_asset"]),
                       "detail": f"{scenario['source_asset']} -> {scenario['target_asset']} reachable={after.reachable(scenario['source_asset'], scenario['target_asset'])}"})
    else:
        checks.append({"name": "unauthorized_access_denied", "passed": bool(after_result["objective_blocked"]),
                       "detail": f"replayed access granted={after_result['access_granted']}, session_active={after_result['session_active']}, credential_version={after_result['credential_version']}"})
        checks.append({"name": "compromised_session_inactive", "passed": not after_result["session_active"],
                       "detail": f"session_active={after_result['session_active']}"})
    checks.append({"name": "containment_recorded", "passed": len(after.containment) > 0,
                   "detail": f"containment={after.containment}"})
    disrupted = after.legitimate_disrupted(baseline)
    _bp = _breach_probability(baseline, scenario)
    _ap = _breach_probability(after, scenario)
    passed_checks = sum(1 for c in checks if c["passed"])
    optimum = _min_edge_cut(baseline, scenario)
    removed = _edges_removed(baseline, after)
    metrics = {
        "baseline_reachable_or_granted": not baseline_result["objective_blocked"],
        "after_reachable_or_granted": not after_result["objective_blocked"],
        "baseline_path": baseline_result.get("path"),
        "after_path": after_result.get("path"),
        # granular: fraction of independent invariant checks passed (partial defenses score partially)
        "defense_effectiveness_pct": round(100.0 * passed_checks / len(checks), 1),
        "checks_passed": passed_checks,
        "checks_total": len(checks),
        "primary_objective_blocked": bool(after_result["objective_blocked"]),
        "operational_impact_disrupted_legit_paths": disrupted,
        "optimal_edge_cut": optimum,
        "defense_edges_removed": removed,
        "optimality_gap": (removed - optimum) if optimum is not None else None,
        "time_to_detect_s": round(t_detected - t_attack_start, 3),
        "time_to_contain_s": round(t_contained - t_detected, 3) if t_contained else None,
        "time_basis": "simulated telemetry timeline (event offsets), not wall-clock demo delays",
        "baseline_breach_probability_pct": _bp[0] if _bp else None,
        "after_breach_probability_pct": _ap[0] if _ap else None,
        "risk_before_pct": _bp[0] if _bp else None,
        "risk_after_pct": _ap[0] if _ap else None,
        "risk_after_ci95": _ap[1] if _ap else None,
        "users_affected": disrupted_users(after, baseline),
        "disrupted_users_estimate": disrupted_users(after, baseline),
    }
    passed = all(c["passed"] for c in checks)
    return VerificationResult(outcome="PASS" if passed else "FAIL", invariant=scenario["invariant"],
                              checks=checks, metrics=metrics,
                              evidence_refs=[f"check:{c['name']}" for c in checks])
