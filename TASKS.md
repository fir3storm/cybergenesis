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

## Post-review hardening (competition readiness pass, 2026-10-27)
- [x] Pydantic v2 ConfigDict (no protected-namespace warnings), FastAPI lifespan handler
- [x] Frontend code-split: main bundle 1.18 MB → 320 KB, 3D scene lazy chunk; production multi-stage nginx Dockerfile; package-lock committed
- [x] 3D accessibility: keyboard orbit/select (arrows/Enter/Esc), prefers-reduced-motion pauses animation, 2D text fallback
- [x] 3D label declutter: compact status pills (expand on hover/select), staggered front/back label placement, wider topology layout
- [x] Scenario icons, agent Raw Decision JSON, Replay-with-Seed-42, prominent LIVE/OFFLINE badge + Download Report on Welcome
- [x] Playwright smoke test (`frontend/e2e/smoke.e2e.ts`, Edge channel) — passes; headless screenshot pipeline (`frontend/scripts/screenshots.mjs`) produced 6 screenshots
- [x] LIVE Meta verified: provider HTTP 200; all 3 scenarios COMPLETED + verification PASS with muse-spark-1.3 decisions. First live run honestly FAILED (model under-specified block_connection → policy rejection); fixed via action contracts in Strategist prompt + bounded policy-feedback retry (mocked regression test added). Tests forced OFFLINE_MODE for hermetic CI.

## Known limitations (honest)
- API key lives only in gitignored `backend/.env`; never committed or exposed by API.
- Docker Compose not run: Docker not installed on dev machine. Local uvicorn + Vite fully verified.

## Verified evidence
- `scripts/test.sh` equivalent gates: pytest 13 passed/1 skipped, ruff clean, vitest 1 passed, Playwright e2e 1 passed, `tsc -b && vite build` OK.
