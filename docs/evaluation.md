# Evaluation

## What is measured (all computed per run, never hardcoded)
- **Attack-path reachability** before/after (BFS over traversable, active, non-isolated edges).
- **Containment success** — containment records present + objective blocked on replay.
- **Time to detect / time to contain** — monotonic timestamps across attack onset → observation → first applied defense.
- **Defense effectiveness %** — blocked predefined objectives / total objectives for the scenario.
- **Operational impact** — legitimate communication pairs reachable at baseline but disrupted after defense.

## Verified results (development machine, seed 42)
All five builtin scenarios are covered by the offline automated suite. See `TASKS.md` for the latest test commands and counts. Offline replay results must not be described as live Meta evidence.

**Historical development record (2026-10-27, reported live Muse Spark via Meta Model API; not rerun in the current readiness pass):** provider status `mode=live` (HTTP 200), and all three scenarios completed live with verification **PASS** — Investigator and Strategist decisions stored with `model=muse-spark-1.3, mode=live`. The first live ransomware run honestly **FAILED** verification: the model proposed `block_connection` without the required source/target params, policy rejected it, nothing executed. Fixed by publishing exact action-parameter contracts + topology/attack-path context to the Strategist and adding one bounded retry carrying deterministic policy feedback (regression-tested with a mocked provider). The corrected live run proposed `isolate_asset(employee-workstation)`, policy approved, workstation `contained`, verification PASS, 2 legitimate paths disrupted (honest cost, shown in the Verification Lab).

Negative test: verification with **no defense applied returns FAIL** — the verifier catches ineffective defense rather than rubber-stamping.

Determinism: identical seed → identical telemetry and state snapshots (tested). Evidence references resolve to stored `evidence_records` rows (tested).

## Frontier pass (2026-10-27, second review round)
- Red team now plans campaigns on the twin's actual directed graph (same arcs as `find_path`), pivots to new footholds/targets (incl. stolen-identity via admin workstation) when the original objective is closed, and every hop is policy-validated. Rounds are fully recorded (candidates, final choice, critic, executions, decisions, rejections).
- Simulation no longer overrides the AI: candidates are sent back to Muse Spark, which makes the final choice; each run reports whether the AI agreed with the simulation optimum.
- One-way (outbound-only) connection blocking makes exfiltration defense an egress control; inbound legitimate flow keeps working (unit-tested).
- Post-PASS statuses: target = `protected`, traversed assets = `cleared` (attack evidence stays visible).
- Monte Carlo breach probability (1,000 seeded replays, posture+vulnerability-weighted) and disrupted-user estimates accompany the binary verdict.
- Human approval gate (off by default; enabled in the local demo env): defenses disrupting ≥2 legitimate paths wait for an operator decision in the UI; rejection/timeout honestly fails verification.

## Limitations
- Metrics derive from the synthetic graph model, not real network traffic; times are wall-clock orchestration times at demo step delays.
- Live Meta inference verified 2026-10-27 with a project key (kept in gitignored `backend/.env`, never committed). Without a key the app runs in labelled offline mode.
- Local Python/Node startup is the primary deployment path. Historical browser checks used Playwright (Edge); current automated verification is recorded in `TASKS.md`. Hosting and live-provider checks are separate from offline tests.

## Reproducing live evidence

Run the explicitly enabled live integration test from `backend` with a configured Meta key and `OFFLINE_MODE=false`. It makes real provider calls; the normal suite remains hermetic. A JSON ping proves provider connectivity only, not scenario completion.

For paired held-out results run `python scripts/evaluate_arena.py --live` with the backend configuration available. Preserve the generated report, including failures, mode, latency and token usage. The default report is offline and does not prove live-model advantage. Arena edge-cut optimality and business-path disruption are different measures and must be reported separately.
