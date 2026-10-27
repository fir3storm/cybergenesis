# Benchmark — 50 seeded twin/scenario pairs

Reproduce: `python scripts/benchmark.py` (raw data: `scripts/benchmark_results.json`).
Pairs are generated from 5 topology templates with seeded random shortcut edges and extra nodes (source must reach target pre-defense). Three defenders run on identical attacked twins: **none** (control), **offline** (deterministic scenario-policy strategist — the labelled fallback), **simulate** (simulate-before-acting candidate search used after an AI proposal).

| Defender | Verification PASS | Mean effectiveness | Mean optimality gap | Mean legit paths disrupted |
|---|---|---|---|---|
| none | 0/50 (0%) | 0.0% | — (no defense) | 0.00 |
| offline | 50/50 (100%) | 100.0% | 0.16 | 0.00 |
| simulate | 50/50 (100%) | 100.0% | 0.16 | 0.00 |

Optimality gap = transversable edges removed by the defense − NetworkX `minimum_edge_cut` between source and target. A non-zero mean gap is honest: isolating a source removes all of its edges, which can exceed the minimum cut when shortcut edges exist — the candidate simulator surfaces this trade-off explicitly in the UI.

**Live Muse Spark spot-check (2026-10-27):** all 4 builtin scenarios run live end-to-end (Investigator + Strategist, no per-scenario instructions in the prompt) — verification PASS, optimality gap 0 on every reachability scenario, candidate tables and red-team rounds recorded per run. Running all 50 pairs live is intentionally not the default (cost); the benchmark harness is offline and hermetic.

Limitations: template topologies are small (3–5 assets); effectiveness is the fraction of independent invariant checks passed; times in product metrics use the simulated telemetry timeline, not wall-clock.
