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

## Failure handling
Provider timeout/rate-limit/malformed JSON → retries then `ProviderUnavailable` → labelled offline fallback or FAILED state; policy rejection → action skipped and recorded; WebSocket drop → polling fallback + stored-event replay on reconnect; WebGL failure → ErrorBoundary 2D twin; cancellation → run marked FAILED (cancelled), baseline restorable via Reset.
