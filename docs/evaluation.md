# Evaluation

## What is measured (all computed per run, never hardcoded)
- **Attack-path reachability** before/after (BFS over traversable, active, non-isolated edges).
- **Containment success** — containment records present + objective blocked on replay.
- **Time to detect / time to contain** — monotonic timestamps across attack onset → observation → first applied defense.
- **Defense effectiveness %** — blocked predefined objectives / total objectives for the scenario.
- **Operational impact** — legitimate communication pairs reachable at baseline but disrupted after defense.

## Verified results (development machine, seed 42)
All three scenarios run end-to-end in the automated suite (`backend/tests/test_cybergenesis.py`, 13 tests passing, hermetically offline):
ransomware, compromised identity, and lateral movement each reach `COMPLETED` with verification **PASS** and 100% of their objectives blocked.

**Live Meta verification (2026-10-27, real Muse Spark via Meta Model API):** provider status `mode=live` (HTTP 200), and all three scenarios completed live with verification **PASS** — Investigator and Strategist decisions stored with `model=muse-spark-1.3, mode=live`. The first live ransomware run honestly **FAILED** verification: the model proposed `block_connection` without the required source/target params, policy rejected it, nothing executed. Fixed by publishing exact action-parameter contracts + topology/attack-path context to the Strategist and adding one bounded retry carrying deterministic policy feedback (regression-tested with a mocked provider). The corrected live run proposed `isolate_asset(employee-workstation)`, policy approved, workstation `contained`, verification PASS, 2 legitimate paths disrupted (honest cost, shown in the Verification Lab).

Negative test: verification with **no defense applied returns FAIL** — the verifier catches ineffective defense rather than rubber-stamping.

Determinism: identical seed → identical telemetry and state snapshots (tested). Evidence references resolve to stored `evidence_records` rows (tested).

## Limitations
- Metrics derive from the synthetic graph model, not real network traffic; times are wall-clock orchestration times at demo step delays.
- Live Meta inference verified 2026-10-27 with a project key (kept in gitignored `backend/.env`, never committed). Without a key the app runs in labelled offline mode.
- Docker Compose stack is provided but was not run here (Docker not installed on the dev machine); local uvicorn+Vite operation is fully verified, including a Playwright (Edge) end-to-end smoke test and a headless screenshot pipeline (`frontend/scripts/screenshots.mjs`).
