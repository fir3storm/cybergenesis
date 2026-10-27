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

## Visual modernization + distinct views (2026-10-27)
- [x] Living Twin and Experiment are now different screens (was the same layout): Twin = inspection (assets/topology/context, no run controls); Experiment Console = scenario cards, stage stepper, commentary, agent decisions, outcome
- [x] Bloom post-processing (EffectComposer + Bloom + Vignette), smooth 0.5s status colour lerp, containment-ring expand animation, label glow shadows, shader-based traveling energy wave on attack edges, per-asset-type Lucide icons
- [x] UI: Space Grotesk/Inter/JetBrains Mono, CSS palette variables, glassmorphism panels, skeleton loaders for the 3D canvas
- [x] Agents are clickable (mouse + keyboard) with an inspector: responsibilities, input/output contract, event/decision activity
- [x] Commentary shows demo-clock timestamps per stage

## Credibility + frontier pass (2026-10-27)
- [x] Removed per-scenario defense prescriptions from prompts — model gets action contracts + graph only. Live re-verified: all 4 scenarios PASS, optimality gap 0
- [x] Real evidence citations: telemetry IDs `tele-<scenario>-<seed>-<n>` end-to-end (observer → investigator → stored evidence)
- [x] Granular effectiveness (fraction of invariant checks), simulated-timeline times, NetworkX min-edge-cut optimality gap per run
- [x] Per-run twins (concurrent runs isolated, tested); display twin syncs on finish only
- [x] Partial approvals no longer accepted (all actions must pass policy); run mode is live/mixed/offline across both AI agents; fallback reasons emitted as `provider_fallback` events and carried in decisions
- [x] Structured output (`response_format: json_object`) + Pydantic validation; directed graph (DiGraph) reachability
- [x] Post-PASS status cleanup — file server no longer sits at SUSPICIOUS after a pass
- [x] Simulate-before-acting: candidate defenses replayed on clones, ranked by blocked→disruption, shown side-by-side; simulation can overrule a non-blocking proposal (recorded)
- [x] AI red team rounds (max 3): NetworkX path enumeration, Muse Spark chooses among validated paths only, loop re-defends; resilience curve in Verification Lab
- [x] Whiteboard → twin via Muse Spark vision (`POST /api/twins/from-image` + Designer upload). Live-tested: all 10 assets/types correctly read from a twin screenshot
- [x] Benchmark: 50 seeded pairs, `scripts/benchmark.py` + `docs/benchmark.md` (none 0%, offline/simulate 100%, mean gap 0.16)
- [x] UX: cinematic mode, replay player + timeline scrubber over stored snapshots, 1×/2×/4× speed (server step-delay param)

## Known limitations (honest)
- API key lives only in gitignored `backend/.env`; never committed or exposed by API.
- Docker Compose not run: Docker not installed on dev machine. Local uvicorn + Vite fully verified.

## Verified evidence
- `scripts/test.sh` equivalent gates: pytest 13 passed/1 skipped, ruff clean, vitest 1 passed, Playwright e2e 1 passed, `tsc -b && vite build` OK.
