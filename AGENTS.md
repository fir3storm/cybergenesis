# AGENTS.md — CYBERGENESIS agent contract

Six runtime agents coordinated by `backend/app/orchestration/orchestrator.py`. Agents are roles, not all LLM calls: deterministic where reliability matters, Meta Muse Spark where reasoning matters.

| Agent | Type | Input | Output schema | May mutate twin? |
|---|---|---|---|---|
| Observer | deterministic | telemetry events | `AgentObservation` | No |
| Adversary Simulator | deterministic, typed plans | scenario def | `AttackScenarioPlan` | Only via simulation engine typed actions |
| Incident Investigator | Meta Muse Spark (offline fallback labelled) | observation + evidence | `IncidentHypothesis` | No |
| Defense Strategist | Meta Muse Spark (offline fallback labelled) | hypothesis | `DefenseProposal` | No |
| Defense Executor | deterministic | proposal + `PolicyDecision` | `DefenseExecutionResult` | Yes — allowlisted actions only |
| Verification Scientist | deterministic replay | scenario + modified twin | `VerificationResult` | No (replay on clone) |

## Hard rules
- No agent gets shell, filesystem write, or arbitrary network access. The only egress is `MetaModelClient`.
- LLM output is untrusted data: Pydantic-validated, then policy-checked. Never executed.
- Adversary uses predefined typed actions from scenario JSON only. No payload generation.
- Every decision stores: agent role, evidence refs, asset IDs, action, justification, confidence, model ID, timestamp, mode (`live`/`offline`).
- Provider failure ⇒ run marked with honest error / offline label. Fake success is a test failure.
- Policy engine (`backend/app/policies/engine.py`) is deterministic and independent of the LLM.

## Dev agents (build-time)
This project was built iteratively: implement → run pytest/tsc/build → fix → update TASKS.md. Never claim a feature works unless tested.
