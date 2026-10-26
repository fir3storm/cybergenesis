# TASKS

## Completed
- [x] Workspace inspection (Python 3.12.10, Node 24; Docker absent — Compose provided, unverified locally)
- [x] ARCHITECTURE.md / IMPLEMENTATION_PLAN.md / AGENTS.md / TASKS.md
- [x] Phase 1: backend foundation (NetworkX twin, 14-table SQLAlchemy DB, FastAPI API + WebSocket) — 12 pytest passing, ruff clean
- [x] Phase 2: ransomware vertical slice end-to-end (attack → observer → investigate → propose → policy → isolate → verify PASS)
- [x] Phase 3: MetaModelClient (structured JSON, retries, usage, /api/models/status), honest OFFLINE fallback, opt-in live test (skipped without key)
- [x] Phase 4: frontend + R3F 3D twin + 2D fallback + WebSocket live updates; build + vitest passing; browser click-through verified, 0 console errors
- [x] Phase 5: compromised identity + lateral movement scenarios — all 3 verify PASS in tests; no-defense negative test verifies FAIL
- [x] Phase 6: all 8 screens (Welcome, Twin, Experiment, Agents, Attack Path, Verification Lab, Evidence, Settings), screenshots in docs/screenshots/
- [x] Phase 7: Docker Compose/Dockerfiles, README, docs (architecture/meta/evaluation/demo-script/threat-model), HACKATHON_SUBMISSION.md, scripts

## Known limitations (honest)
- Live Meta inference not exercised: no API key in this environment. Set MODEL_API_KEY, restart backend, badge flips to LIVE META AI.
- Docker Compose not run: Docker not installed on dev machine. Local uvicorn + Vite fully verified.
- Playwright suite not added; browser E2E was verified manually via automated browser click-through instead.

## Verified evidence
- Live HTTP run: ransomware experiment COMPLETED, verification PASS, effectiveness 100%, workstation contained, 2 legit paths disrupted.
- `scripts/test.sh` equivalent gates: pytest 12 passed/1 skipped, ruff clean, vitest 1 passed, `tsc -b && vite build` OK.
