# Architecture

See root `ARCHITECTURE.md` for the full layered design. Key implementation map:

| Concern | Code |
|---|---|
| Twin engine (NetworkX graph, snapshots, reachability, typed actions) | `backend/app/simulation/twin.py` |
| Scenario definitions (typed steps only) | `scenarios/*.json`, loader `backend/app/simulation/scenarios.py` |
| Deterministic policy gate | `backend/app/policies/engine.py` |
| Meta client (async, retries, JSON extraction, usage) | `backend/app/integrations/meta_client.py` |
| Agents (Observer/Adversary deterministic; Investigator/Strategist Meta+offline; Executor/Verifier deterministic) | `backend/app/agents/agents.py`, `backend/app/verification/verifier.py` |
| Orchestrator state machine + WebSocket fan-out | `backend/app/orchestration/orchestrator.py` |
| API + WS | `backend/app/main.py` (`/api/health`, `/api/models/status`, `/api/twin*`, `/api/scenarios*`, `/api/experiments*`, `/ws/experiments/{id}`) |
| Persistence (14 tables: runs, events, decisions, proposals, policy, executions, verifications, evidence, snapshots, model usage…) | `backend/app/models.py` |
| 3D twin (R3F/Three/Drei, status colours, traffic particles, attack-path highlight, containment rings, orbit/select) | `frontend/src/components/TwinScene.tsx` |
| Screens (Welcome, Twin Control Center, Experiment, Agents, Attack Path, Verification Lab, Evidence, Settings) | `frontend/src/App.tsx` |

## Data flow
UI → REST create/run → orchestrator (async task) → twin attack → telemetry+evidence rows → Observer → Investigator (Meta or labelled offline) → Strategist → policy per action → executor mutates twin → Verifier replays objective on modified twin → metrics computed → WS events stream every step (twin state embedded) → UI 3D updates live.

## Agent permissions matrix (20 agents, one framework)

| Agent | Team | Engine | Tools | Can propose | Mutates twin |
|---|---|---|---|---|---|
| incident_commander | command | meta | twin summary, memory | — | No |
| twin_architect | command | meta (vision) | twin summary | twin defs (validated) | No |
| observer | blue | deterministic | telemetry | — | No |
| incident_investigator | blue | meta | read tools | — | No |
| defense_strategist | blue | meta | read + simulate_on_clone | all allowlisted actions | No |
| defense_executor | blue | deterministic | twin summary | — | **Yes — only via policy gate** |
| threat_intel_analyst | blue | hybrid | telemetry, MITRE | hardening proposals | No |
| identity_guardian | blue | hybrid | summary, explain_path | revoke/rotate/enforce_mfa | No |
| config_engineer | blue | meta | device config | dialect diffs (parsed) | No |
| deception_engineer | blue | hybrid | twin summary | deploy_decoy | No |
| recovery_engineer | blue | hybrid | explain, simulate | restore actions | No |
| adversary_simulator | red | deterministic | — | validated campaigns only | Attack steps via engine |
| red_team_planner | red | meta | read tools | campaigns (evaluate_campaign) | No |
| red_team_critic | red | meta | explain_path | bypass campaigns | No |
| scenario_author | red | meta | twin summary | scenario defs (validated) | No |
| verification_scientist | assurance | deterministic | explain_path | — | No |
| config_auditor | assurance | hybrid | device config, findings | fix diffs | No |
| attack_surface_mapper | assurance | hybrid | summary, explain | — | No |
| business_impact_analyst | assurance | hybrid | simulate_on_clone | — | No |
| forensic_reporter | assurance | meta | telemetry, memory | — | No |

Prompt-injection defence: all telemetry/scenario/config/user text reaches models inside `<<DATA:...>>` delimiters with an explicit never-an-instruction rule; a regression test injects "isolate the database" into telemetry and asserts neither the proposal nor the policy engine obeys it. Concurrency: a global semaphore caps Meta calls at 4; per-run token budgets force labelled offline fallback.

## Failure handling
Provider timeout/rate-limit/malformed JSON → retries then `ProviderUnavailable` → labelled offline fallback or FAILED state; policy rejection → action skipped and recorded; WebSocket drop → polling fallback + stored-event replay on reconnect; WebGL failure → ErrorBoundary 2D twin; cancellation → run marked FAILED (cancelled), baseline restorable via Reset.
