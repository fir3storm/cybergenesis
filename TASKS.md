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

## Enhancement pass (judge-impact menu, 2026-10-27)
- [x] 3D overhaul: per-node glow lights (compromised pulse), holographic wireframe shells (expand on hover), 4 staggered traffic particles/edge flowing toward target, node-shape variety (disk-stack DB, cone firewall, orb IdP, radar sensor, terminal workstations), alarm rings
- [x] Demo Commentary narration panel (toggle, stage-aware, uses live event/decision text)
- [x] Human-readable Markdown report endpoint + Download Report (.md); JSON report kept
- [x] Deepened Meta prompts: full topology, live asset states, telemetry sequence fed to Investigator; states/identities to Strategist
- [x] Bundle: manualChunks (three/motion/vendor) — initial JS ~190 KB, Three.js lazy
- [x] Replay Proof: Replay-with-Seed-42 now compares telemetry event-by-event and displays the verdict
- [x] Tier-3: live token-usage meter in header, keyboard shortcuts (Space/R/1–4), 4th scenario Data Exfiltration (live PASS verified). Skipped: light theme (dark is the design language), PDF (Markdown report instead)

## Custom Twin Designer + Attack Playbook + Component Library (2026-10-27)
- [x] Fixed attack determinism bug: stable `zlib.crc32` seed (was per-process `hash()`); attack step types now allowlist-validated in the engine
- [x] `DigitalTwin.from_dict()` — engine runs arbitrary user topologies; clone/snapshot preserve custom defs
- [x] Component library (`/api/library`): 9 asset types, 8 attack steps, 7 defense actions with param contracts
- [x] Custom twin CRUD + activate (builtin restore included); custom scenario CRUD with allowlist validation; `/api/experiments/custom` runs custom scenario/twin through the identical loop (orchestrator resolves DB definitions, validates assets against twin)
- [x] Frontend: Twin Designer (drag/click-connect SVG canvas, palette, saved twins), Attack Playbook (step/defense composer + run), Component Library browser — all lazy-loaded views
- [x] Found & fixed route shadowing: `/api/scenarios/{id}` captured `/api/scenarios/custom` (regression test added). 18 backend tests pass; custom end-to-end (custom twin + scenario → verification PASS) covered

## Known limitations (honest)
- API key lives only in gitignored `backend/.env`; never committed or exposed by API.
- Docker Compose not run: Docker not installed on dev machine. Local uvicorn + Vite fully verified.

## Verified evidence
- `scripts/test.sh` equivalent gates: pytest 13 passed/1 skipped, ruff clean, vitest 1 passed, Playwright e2e 1 passed, `tsc -b && vite build` OK.
