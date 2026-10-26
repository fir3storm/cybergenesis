"""Independent verification: replay the same attack objective on a clone. Computed, never hardcoded."""

import time

from app.schemas import VerificationResult
from app.simulation.twin import DigitalTwin


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
    total_objectives = max(len(scenario.get("objectives", [1])), 1)
    blocked = total_objectives if after_result["objective_blocked"] else 0
    metrics = {
        "baseline_reachable_or_granted": not baseline_result["objective_blocked"],
        "after_reachable_or_granted": not after_result["objective_blocked"],
        "baseline_path": baseline_result.get("path"),
        "after_path": after_result.get("path"),
        "defense_effectiveness_pct": round(100.0 * blocked / total_objectives, 1),
        "operational_impact_disrupted_legit_paths": disrupted,
        "time_to_detect_s": round(t_detected - t_attack_start, 3),
        "time_to_contain_s": round(t_contained - t_detected, 3) if t_contained else None,
        "verified_at_monotonic": time.monotonic(),
    }
    passed = all(c["passed"] for c in checks)
    outcome = "PASS" if passed else "FAIL"
    return VerificationResult(outcome=outcome, invariant=scenario["invariant"], checks=checks,
                              metrics=metrics, evidence_refs=[f"check:{c['name']}" for c in checks])
