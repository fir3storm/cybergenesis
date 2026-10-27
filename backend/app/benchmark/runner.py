"""Benchmark runner: generated pairs x {none, offline, simulate} defenders."""

import random

from app.benchmark.generator import generate_pair
from app.policies.engine import evaluate
from app.simulation.candidates import evaluate_candidates
from app.simulation.twin import DigitalTwin
from app.verification.verifier import verify


def run_benchmark(n: int, seed: int, progress=None) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    for i in range(n):
        assets, conns, scenario = generate_pair(rng, i)
        base = DigitalTwin.from_dict(assets, conns)
        probe = base.clone(); probe.apply_attack(scenario, seed=seed)
        baseline_result = probe.attempt_attack_objective(scenario)
        entry: dict = {"pair": i, "source": scenario["source_asset"], "target": scenario["target_asset"], "assets": len(assets)}
        for name in ("none", "offline", "simulate"):
            twin = base.clone(); twin.apply_attack(scenario, seed=seed)
            if name == "offline":
                actions = scenario["expected_defense"]
            elif name == "simulate":
                cands = evaluate_candidates(twin, base, scenario, scenario["expected_defense"])
                best = cands[0] if cands else {"actions": [], "blocked": False}
                actions = best["actions"] if best.get("blocked") else []
            else:
                actions = []
            for a in actions:
                if evaluate(a["action_type"], a["asset_id"], a.get("params", {}), twin).approved:
                    try:
                        twin.apply_action(a["action_type"], a["asset_id"], a.get("params", {}))
                    except ValueError:
                        pass
            res = verify(scenario, base, twin, baseline_result, 0.0, 0.4, 0.8)
            entry[name] = {"pass": res.outcome == "PASS", "effectiveness": res.metrics["defense_effectiveness_pct"],
                           "gap": res.metrics["optimality_gap"], "disrupted": res.metrics["operational_impact_disrupted_legit_paths"],
                           "risk_after": res.metrics["risk_after_pct"]}
        rows.append(entry)
        if progress:
            progress(i + 1, n, entry)
    return rows


def summarize(rows: list[dict]) -> dict:
    out = {}
    for key in ("none", "offline", "simulate"):
        vals = [r[key] for r in rows]
        if not vals:
            continue
        gaps = [v["gap"] for v in vals if v["gap"] is not None]
        out[key] = {"pass_rate_pct": round(100 * sum(v["pass"] for v in vals) / len(vals), 1),
                    "mean_effectiveness_pct": round(sum(v["effectiveness"] for v in vals) / len(vals), 1),
                    "mean_optimality_gap": round(sum(gaps) / max(1, len(gaps)), 2),
                    "mean_disrupted": round(sum(v["disrupted"] for v in vals) / len(vals), 2),
                    "mean_risk_after_pct": round(sum(v["risk_after"] or 0 for v in vals) / len(vals), 1)}
    return out
