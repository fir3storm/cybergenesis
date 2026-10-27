"""Independent verification: replay the same attack objective. Computed, never hardcoded."""

import networkx as nx

from app.schemas import VerificationResult
from app.simulation.twin import DigitalTwin


def _min_edge_cut(baseline: DigitalTwin, scenario: dict) -> int | None:
    if scenario["verification_kind"] != "reachability":
        return None
    g = nx.Graph()
    for c in baseline.to_dict()["connections"]:
        if c["traversable"] and c["active"]:
            g.add_edge(c["source"], c["target"])
    try:
        return len(nx.minimum_edge_cut(g, scenario["source_asset"], scenario["target_asset"]))
    except Exception:  # noqa: BLE001 - no path / missing node -> optimum 0
        return 0


def _edges_removed(baseline: DigitalTwin, after: DigitalTwin) -> int:
    # traversable edges only — comparable to the minimum edge cut below
    b = {(c["source"], c["target"]) for c in baseline.to_dict()["connections"] if c["active"] and c["traversable"]}
    a = {(c["source"], c["target"]) for c in after.to_dict()["connections"] if c["active"] and c["traversable"]}
    return len(b - a)


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
    }
    passed = all(c["passed"] for c in checks)
    return VerificationResult(outcome="PASS" if passed else "FAIL", invariant=scenario["invariant"],
                              checks=checks, metrics=metrics,
                              evidence_refs=[f"check:{c['name']}" for c in checks])
