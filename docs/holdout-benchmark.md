# Held-out topology benchmark

Reproduce: `python scripts/holdout_benchmark.py --n 24 --seed 7` (raw data: `docs/holdout-benchmark.json`).

24 seeded layered random graphs, generated for this benchmark and distinct from the builtin twin and the 5 benchmark templates. Every case is reachable before defense. A defense counts as blocking when the target is unreachable in the twin's live graph.

| Defender | Blocked | Mean edges removed | Mean legit paths disrupted |
|---|---|---|---|
| none (control) | 0/24 | 0.0 | 0.0 |
| deterministic (min-cut egress) | 24/24 | 3.12 | 0.0 |
| simulate (candidate search) | 24/24 | 6.25 | 0.0 |

## What this proves — and what it does not

The deterministic minimum-cut is the strongest *pure graph* defender here, removing the fewest edges. Simulate-before-acting also blocks every case but pays more edges (its ranking prefers low-disruption candidate classes such as isolation, which remove many arcs). Neither result is hidden.

The LLM's contribution is therefore not beating min-cut arithmetic — no honest claim of that is made. Meta Muse Spark contributes contextual investigation (evidence-cited hypotheses), defense selection among trade-offs the graph cannot see (operational impact, identity compromise, management-plane weakness), red-team path choice, whiteboard-to-twin vision, and the board narrative. Live spot-checks are in `docs/evaluation.md`; running all held-out pairs live is opt-in because of API cost.
