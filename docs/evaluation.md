# Evaluation

## What is measured (all computed per run, never hardcoded)
- **Attack-path reachability** before/after (BFS over traversable, active, non-isolated edges).
- **Containment success** — containment records present + objective blocked on replay.
- **Time to detect / time to contain** — monotonic timestamps across attack onset → observation → first applied defense.
- **Defense effectiveness %** — blocked predefined objectives / total objectives for the scenario.
- **Operational impact** — legitimate communication pairs reachable at baseline but disrupted after defense.

## Verified results (development machine, offline mode, seed 42)
All three scenarios run end-to-end in the automated suite (`backend/tests/test_cybergenesis.py`, 12 tests passing):
ransomware, compromised identity, and lateral movement each reach `COMPLETED` with verification **PASS** and 100% of their (single/dual) objectives blocked. Example live HTTP run: ransomware completed with effectiveness 100.0%, 2 legitimate paths disrupted by workstation isolation (honest cost, shown in the Verification Lab), workstation status `contained`.

Negative test: verification with **no defense applied returns FAIL** — the verifier catches ineffective defense rather than rubber-stamping.

Determinism: identical seed → identical telemetry and state snapshots (tested). Evidence references resolve to stored `evidence_records` rows (tested).

## Limitations
- Metrics derive from the synthetic graph model, not real network traffic; times are wall-clock orchestration times at demo step delays.
- Live Meta inference was not exercised in this environment (no API key available); the live path is covered by mocked/failure tests and the honest offline fallback. Judges with a key can enable it per README.
- Docker Compose stack is provided but was not run here (Docker not installed on the dev machine); local uvicorn+Vite operation is fully verified.
