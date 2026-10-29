# Implementation Plan

## Phase 1 — Foundation
Repo init, backend (FastAPI/SQLAlchemy/NetworkX), frontend scaffold (Vite/React/TS/Tailwind), schemas, deterministic twin engine, initial topology, base tests, both services start.

## Phase 2 — First complete experiment (ransomware-like)
Attack sim → telemetry → observer → investigator → defense proposal → policy → containment → verification → evidence. Gate: vertical slice passes end-to-end test before continuing.

## Phase 3 — Meta intelligence
MetaModelClient (structured JSON, retries, validation, usage), `/api/models/status`, honest OFFLINE fallback with visible indicator, mocked tests + opt-in live integration test.

## Phase 4 — 3D digital twin
R3F scene, status colours, animated traffic/attack path, orbit/select/inspect, WebSocket wiring, 2D fallback.

## Phase 5 — Additional scenarios
Compromised identity, lateral movement, each with independent verification.

## Phase 6 — Polish
Landing, agent collaboration view, verification lab (before/after), attack path explorer, evidence export, settings, accessibility, reduced-motion.

## Phase 7 — Delivery
Local startup scripts, README, docs (architecture/threat-model/evaluation/demo-script/meta-integration), HACKATHON_SUBMISSION.md, quality gates (pytest, vitest, tsc, ruff, build, health, full experiment, reset/replay).

## Decisions
- SQLite dev DB via SQLAlchemy (Postgres-compatible models); single global twin instance guarded by lock, snapshots in DB.
- httpx for Meta API (OpenAI-compatible `/chat/completions`), no extra SDK weight.
- Step delays configurable (`SIM_STEP_DELAY_MS`) — 350ms for demo, 0 in tests.
- Frontend: view-state navigation (Zustand), no router dependency weight.
