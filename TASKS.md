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
- [x] UX: cinematic mode, replay player + timeline scrubber over stored snapshots, 1—/2—/4— speed (server step-delay param)

## F8d-finish — Proof certificate in the UI (2026-10-28)
- [x] `api.getCertificate(runId)`; ProofCard in Experiment Console, Verification Lab + Evidence (PASS only, `certificate-<runId>.json`, signature/hash-chain short, campaigns replayed, verify-locally hint); README "Proof-carrying defense"; Playwright asserts the downloaded file's signature + `unreachable_proof`; backend `test_f8d` valid/tampered

## F8e — Counterfactual time machine (2026-10-28)
- [x] `POST /api/experiments/{id}/fork {at_event, choose_candidate}` restores the attacked snapshot, re-applies the alternative candidate through the same policy engine + verifier as a new recorded run (original unchanged, deterministic); fork payload carries both twins, both timelines and metric deltas (disruption, risk, rounds, verdict); Compare view renders two timelines + two twins side by side with a Δ column; backend + Playwright tests cover different-candidate outcome

## F8f — Approve from your phone (2026-10-28)
- [x] Approval card shows a QR code (LAN URL, auto-detected or `PUBLIC_BASE_URL`) for `/m/approve/{run_id}?t=<one-time token>`; the phone page lists actions + impact with Approve/Reject through the same gate, audited as `approval_mobile` ("approved via mobile"); reused, UI-decided and expired tokens all return 403 (token dies with the approval window); tests: backend single-use/expiry/UI-decision + Playwright phone flow + QR unit tests

## Arena (red vs blue, self-learning) — design locked 2026-10-28
Win: red reaches target OR blue survives max_rounds. Learning: hybrid (AI picks among validated moves, deterministic score memory biases later rounds). Scope: any twin+scenario, live spectate.
- [x] B1 core engine (`app/arena/engine.py`): round loop (validated red path → policy-gated blue candidate → replay check), injected strategies, deterministic defaults, caller twin never mutated; 6 tests (blue holds, red breaks/no-defense, survival, identity, determinism)
- [x] B2 learning memory (`app/arena/learning.py`): persistent JSON score memory, learned red/blue choosers (blocking first, then learned rate, then disruption); 5 tests
- [x] B3 Meta AI choosers (`app/arena/ai.py` + async engine): AI picks only among validated paths/candidates, unknown picks and provider failures fall back labelled offline; 3 mocked tests
- [x] B4 API + persistence: `POST/GET /api/arena/matches`, `GET /api/arena/memory|league`, `ArenaMatch` rows, memory saved across matches; 3 tests
- [x] B5 spectate UI (`views/arena.tsx`): scenario/strategy/rounds controls, league scoreboard, spectate replay of rounds, final twin, learned-memory and past-match panels
- [x] B6 winner proof: `GET /api/arena/matches/{id}/certificate` (HMAC, winner + final twin), `verify_cert.py` recomputes the objective; tamper → INVALID; deterministic replay test
- [x] B7 league table (UI + API), Playwright arena test (play → spectate → winner proof file), README Arena section

## Multi-provider Settings (2026-10-28)
- [x] Four AI providers behind the one OpenAI-compatible client: Meta Muse Spark, Command Code (`api.commandcode.ai/provider/v1`), Kilo Gateway (`ai-gateway.kilo.ai/api/v1`), Google AI Studio (`generativelanguage.googleapis.com/v1beta/openai`); Settings UI activates any provider at runtime (key + model + base URL), keys stored locally only and never returned by an API; env vars remain a fallback; header badge names the live provider; 4 backend tests + live UI probe

## Working-tree hardening (2026-10-28)
- [x] Scenario-driven `apply_attack` extras (`spread`, `mark_target_suspicious`, `proc_name`, `process_asset_types`) moved out of hardcoded `scenario["id"]` branches into JSON — a new scenario is authored purely in JSON, `twin.py` needs no edit; `_asset_type_of()` helper added
- [x] Identity pivot in `policies/engine.py` keyed on asset_type (`IDENTITY_SCOPE_TYPES = {"identity","workstation"}`), so generated/custom twins (ids like `db-main`) qualify — not just hardcoded names
- [x] Arena `learned_blue_chooser` ranking documented: blockers first, then learned block rate, then disruption, then invasiveness
- [x] `test_catalog.py` rewritten to the real contract (200 total, category counts, 20 flagships, `BY_ID` completeness, `BUILTIN_DEVICE_MAP` resolution, `query_catalog` paging/filtering) — fixed the 3 failing assertions that assumed object accessors on the dict-shaped API response
- [x] Full backend suite: **174 passed, 1 skipped** (was 3 failed)

## Competition readiness pass (2026-10-28)
- [x] **Arena reroute loop**: `engine.py` replays Blue's candidate on a clone, applies atomically only if every action passes policy (no partial defense), and Red reroutes when only the *selected* route is blocked — matches end on route-survival or round-budget-exhaustion, not on bare reachability. `selected_path_blocked` + `winner_so_far: red|adapting|blue` per round; `max_rounds` validated 1..10 at the API boundary
- [x] **Decision provenance**: every round emits `decisions[]` (adversary_simulator + defense_strategist) with agent_role, evidence_refs, asset_ids, action, justification, confidence, model_id, timestamp, mode, fallback_reason; `ai.py` carries typed `BlueChoice`/`RedChoice` Pydantic schemas (`extra="forbid"`) and records `last_decision`/`last_mode` on both choosers
- [x] **Held-out evaluation**: `app/arena/evaluation.py` — paired deterministic vs learned on generated held-out twins, training memory frozen and re-asserted unchanged, per-case wins/disruption/latency/tokens/fallbacks; `scripts/evaluate_arena.py` writes `docs/arena-evaluation.json`; `/api/arena/evaluation` + Arena UI panel surface it. Honest: no claim of AI superiority from deterministic evidence
- [x] **Context isolation**: `ArenaMemory.for_context(scenario_id, custom_twin_id)` — scenario-scoped scores, legacy global scores do not leak into unseen scenarios, persistent across matches
- [x] **Tests**: 15 new arena tests (`test_arena_adaptive`, `test_arena_evaluation`, `test_arena_context`, `test_arena_b3` additions) — reroute, residual-exposure-at-budget, invalid-route rejection, round limits, atomic rejected proposal + audit; frontend `arena.test.tsx` (training count, stop-after-match, failure stops session)
- [x] Full gates: backend **189 passed / 1 skipped**, frontend 28 passed, `tsc -b` clean, ruff clean, evaluation report generated

## Known limitations (honest)
- API key lives only in gitignored `backend/.env`; never committed or exposed by API.
- Docker removed 2026-10-29 per submitter request. Local uvicorn + Vite verified; Render blueprint unexercised.

## Verified evidence
- `scripts/test.sh` equivalent gates: pytest 13 passed/1 skipped, ruff clean, vitest 1 passed, Playwright e2e 1 passed, `tsc -b && vite build` OK.

### Arena training enhancement — 2026-10-28
- Added bounded sequential self-play sessions (3/5/10/20 battles), stop-after-match control, outcome history and replay selection.
- Scoped strategy memory by scenario and custom twin; preserved aggregate historical reporting and existing chooser ranking.
- Exposed current-scenario experience and clarified that learning updates outcome scores, not model weights. Sessions run while the arena is mounted; persisted completed matches remain available afterward.
- Verified: 23 arena backend tests; 28 frontend tests including training completion, stop and failure handling; TypeScript and production build passed (existing large-chunk warning).

## Submission-readiness pass - 2026-10-29
- [x] Removed Docker entirely: docker-compose.yml, backend/Dockerfile, frontend/Dockerfile, frontend/nginx.conf deleted; docs now use local launchers (scripts/start.ps1 / start.sh) + optional Render blueprint.
- [x] CORS origins configurable via CORS_ORIGINS; hosted frontend origin allowlisted in render.yaml.
- [x] Operator gate: mutations, approval-token disclosure and narrate=true require ADMIN_TOKEN (loopback bootstrap for local UI; Settings entry for shared hosting); CLI websocket requires token; mobile approval stays single-use capability.
- [x] Arena evaluation fixed: optimality gap now compares removed directed edges vs directed minimum edge cut (business disruption reported separately); strategies are distinct (min_cut / simulate / learned / optional ai); identical-strategy benchmark removed.
- [x] Live Meta test opt-in fixed: explicit RUN_META_INTEGRATION setup overrides offline for that fixture only; no-key run reports honestly (one accidental ping returned HTTP 402 - no live success claimed).
- [x] Submission claims reconciled: live evidence is 3 scenarios (docs/evaluation.md), not 5; no deterministic-vs-learned superiority claim.
- [x] Verified: backend 264 passed / 1 skipped, ruff clean, frontend 35 passed, tsc clean, production build OK, scripts/start.ps1 -CheckOnly OK.
- [ ] Still open: exercise hosted Render instance end-to-end; record docs/demo.webm fallback; re-run Playwright e2e.


## Clean-slate for demo video - 2026-10-29
- [x] Moved accumulated runtime data to D:\Ajanta-backup-20261029\ (backend DB 134MB + 134MB bak: 1,143 runs/65,360 events/8,978 decisions/6 custom twins/7 custom scenarios; stray frontend DB; arena_memory.json with 1 learned match).
- [x] Fresh boot verified: DB reseeds only the 5 built-in scenarios + auto-created local operator user; 0 runs/events/decisions/custom content; /api/experiments=[].
- [x] Kept by choice: backend/.env (CERT_DEMO_KEY), provider_settings.json (provider keys), cert_signing_key.pem (certificate signer identity). Built-in twin + 5 scenarios are code-defined and remain - demo depends on them.
- [ ] Before recording: use a fresh browser profile/incognito (clears localStorage operator token), re-run scripts/start.ps1 -CheckOnly.

## Demo video - 2026-10-29
- [x] Live run-through: Muse Spark 1.3 via fresh Command Code key (mode=live, HTTP 200 at /api/models/status); direct Meta key returns HTTP 402, old CommandCode key 401 - disclosed to user. First API run honestly FAILed (approval timeout, auto-deny); UI run with operator approval: verification PASS 100%.
- [x] Recorded Playwright/Edge take on pristine DB; docs/demo-final.mp4 = 180.000s video+audio, 1440x810, TTS en-US-GuyNeural, problem statement (0:00) then twin/run/policy/verify/proof/arena/close. Script: docs/demo-final-script.md.
- [ ] Watch docs/demo-final.mp4 fully before submitting; rotate the Command Code key pasted in chat after the submission.
