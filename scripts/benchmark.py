"""CYBERGENESIS benchmark: 50 seeded random twin+scenario pairs.

Compares three defenders on identical attacked twins:
  - none        (no defense — control)
  - offline     (deterministic scenario-policy strategist, the labelled fallback)
  - simulate    (simulate-before-acting candidate search, as used after an AI proposal)
Metrics per pair: verification PASS, defense effectiveness %, optimality gap, legit paths disrupted.
Live Muse Spark is spot-checked separately on the 4 builtin scenarios (docs/evaluation.md);
running 50 live calls is intentionally opt-in (--live not implemented for cost control).

Usage: python scripts/benchmark.py [--n 50] [--seed 7]
Writes benchmark_results.json and prints a Markdown table.
"""

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.policies.engine import evaluate  # noqa: E402
from app.simulation.candidates import evaluate_candidates  # noqa: E402
from app.simulation.twin import DigitalTwin  # noqa: E402
from app.verification.verifier import verify  # noqa: E402

TEMPLATES = [
    (["ws", "fs", "db"], [("ws", "fs"), ("fs", "db")], "ws", "fs"),
    (["web", "app", "db"], [("web", "app"), ("app", "db")], "web", "db"),
    (["web", "app", "db", "fs"], [("web", "app"), ("app", "db"), ("app", "fs")], "web", "db"),
    (["ws", "fs", "db", "app"], [("ws", "fs"), ("fs", "db"), ("ws", "app"), ("app", "db")], "ws", "db"),
    (["gw", "web", "app", "db"], [("gw", "web"), ("web", "app"), ("app", "db"), ("web", "db")], "gw", "db"),
]


def make_pair(rng: random.Random, idx: int):
    assets_tpl, edges_tpl, src, tgt = TEMPLATES[idx % len(TEMPLATES)]
    extra = rng.choice([[], ["sensor"], ["idp"], ["ws2"]])
    names = list(dict.fromkeys(assets_tpl + extra))
    assets = [{"id": n, "name": n, "asset_type": "workstation", "zone": "bench", "pos": [0, 1, 0]} for n in names]
    conns = [{"source": s, "target": t, "traversable": True} for s, t in edges_tpl]
    if "sensor" in extra:
        conns.append({"source": "sensor", "target": assets_tpl[0], "traversable": False})
    if "ws2" in extra:
        conns.append({"source": "ws2", "target": rng.choice(assets_tpl), "traversable": True})
    # seeded random shortcut edges (create alternate paths the red team would find)
    pool = [(a, b) for a in names for b in names if a < b and (a, b) not in edges_tpl and (b, a) not in edges_tpl
            and "sensor" not in (a, b)]
    for s, t in rng.sample(pool, k=min(len(pool), rng.randint(0, 2))):
        conns.append({"source": s, "target": t, "traversable": True})
    scenario = {"id": f"bench-{idx}", "source_asset": src, "target_asset": tgt, "verification_kind": "reachability",
                "objectives": ["reach_target"], "invariant": f"{src} cannot reach {tgt}",
                "attack_steps": [{"type": "network_connection", "asset": src, "description": "bench attack"}],
                "expected_defense": [{"action_type": "isolate_asset", "asset_id": src, "params": {}}]}
    return assets, conns, scenario


def run_defense(twin: DigitalTwin, scenario: dict, actions: list[dict]) -> None:
    for a in actions:
        if evaluate(a["action_type"], a["asset_id"], a.get("params", {}), twin).approved:
            try:
                twin.apply_action(a["action_type"], a["asset_id"], a.get("params", {}))
            except ValueError:
                pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    rows = []
    for i in range(args.n):
        assets, conns, scenario = make_pair(rng, i)
        base = DigitalTwin.from_dict(assets, conns)
        attacked_probe = base.clone(); attacked_probe.apply_attack(scenario, seed=args.seed)
        baseline_result = attacked_probe.attempt_attack_objective(scenario)
        entry = {"pair": i, "source": scenario["source_asset"], "target": scenario["target_asset"], "assets": len(assets)}
        for name, actions in (("none", []),
                              ("offline", scenario["expected_defense"]),
                              ("simulate", None)):
            twin = base.clone(); twin.apply_attack(scenario, seed=args.seed)
            if name == "simulate":
                cands = evaluate_candidates(twin, base, scenario, scenario["expected_defense"])
                best = cands[0] if cands else {"actions": []}
                actions = best["actions"] if best.get("blocked") else []
            run_defense(twin, scenario, actions or [])
            res = verify(scenario, base, twin, baseline_result, 0.0, 0.4, 0.8)
            entry[name] = {"pass": res.outcome == "PASS", "effectiveness": res.metrics["defense_effectiveness_pct"],
                           "gap": res.metrics["optimality_gap"], "disrupted": res.metrics["operational_impact_disrupted_legit_paths"]}
        rows.append(entry)

    def agg(key: str) -> str:
        vals = [r[key] for r in rows]
        passes = sum(v["pass"] for v in vals)
        eff = sum(v["effectiveness"] for v in vals) / len(vals)
        gaps = [v["gap"] for v in vals if v["gap"] is not None]
        dis = sum(v["disrupted"] for v in vals) / len(vals)
        gap_s = "— (no defense)" if key == "none" else f"{sum(gaps) / max(len(gaps), 1):.2f}"
        return f"| {key} | {passes}/{len(vals)} ({100 * passes / len(vals):.0f}%) | {eff:.1f}% | {gap_s} | {dis:.2f} |"

    print(f"# CYBERGENESIS benchmark — {args.n} seeded pairs (seed {args.seed})\n")
    print("| Defender | Verification PASS | Mean effectiveness | Mean optimality gap | Mean legit paths disrupted |")
    print("|---|---|---|---|---|")
    for k in ("none", "offline", "simulate"):
        print(agg(k))
    out = Path(__file__).with_name("benchmark_results.json")
    out.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
