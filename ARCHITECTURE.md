# CYBERGENESIS — Architecture

**Tagline:** The Autonomous Self-Defending Digital Twin
**Owner:** Dr. Abhirup Guha · **Event:** Meta Global AI Developer Hackathon 2026
**Primary AI:** Meta Muse Spark (`muse-spark-1.3`) via Meta Model API (OpenAI-compatible)

## Closed loop (the differentiator)
`Observe → Reason → Propose → Validate (policy) → Act → Retest → Prove`

## Layers
1. **Digital Twin** — NetworkX graph of 10 synthetic assets (internet, firewall, web/app/db, IdP, workstations, file server, sensor) with zone, posture, state, vulnerabilities. Baseline / active / post-remediation snapshots, seeded reset.
2. **Telemetry Generator** — deterministic synthetic events (auth, network, process, file, authz-failure, config, detection, containment). All synthetic, clearly labelled.
3. **Adversarial Simulation** — typed, predefined scenario actions only (3 scenarios). No exploits, no scanning, no real targets.
4. **AI Reasoning** — Meta Muse Spark via `MetaModelClient`: async, structured JSON validated by Pydantic, retries/timeout, token accounting, prompt versioning. Falls back to explicitly-labelled OFFLINE deterministic mode — never presented as live inference.
5. **Policy & Control** — deterministic, LLM-independent allowlist engine (action types, assets, preconditions). AI proposes; policy decides.
6. **Defensive Execution** — allowlisted actions mutate twin state only; every transition recorded.
7. **Verification** — independent replay of the same attack objective against modified twin; PASS/FAIL/INCONCLUSIVE computed from reachability/session/state invariants, never hardcoded.
8. **Visualization** — React + React Three Fiber living 3D twin, WebSocket live events, 2D fallback.
9. **Audit & Evidence** — append-only events, decisions, policy evals, executions, verifications, model usage in SQLite (PostgreSQL-compatible SQLAlchemy models).

## Agents (orchestrated, explicit state machine)
Observer (deterministic) · Adversary Simulator (typed plans) · Incident Investigator (Meta) · Defense Strategist (Meta) · Defense Executor (policy+engine) · Verification Scientist (deterministic replay).
States: IDLE → SCENARIO_SELECTED → ATTACK_SIMULATING → TELEMETRY_COLLECTED → INVESTIGATING → DEFENSE_PROPOSED → POLICY_VALIDATING → DEFENSE_APPLYING → VERIFYING → COMPLETED | FAILED. Cancellation, retry limits, timeouts supported.

## Trust boundaries
- Runtime agents have **no shell**, no network egress except Meta API client, no real-target capability.
- LLM output is parsed as data, validated against schemas and policy; never executed as code/commands.
- Secrets only from environment; never logged or returned by API.

## Stack
Frontend: React+TS+Vite+Tailwind+R3F/Three/Drei+Zustand+TanStack Query+Lucide. Backend: FastAPI+Pydantic+SQLAlchemy+NetworkX+asyncio+WebSockets. Tests: Pytest, Vitest, Playwright (smoke), Ruff, TS strict. Deploy: local Python/Node services, optional Render blueprint.
