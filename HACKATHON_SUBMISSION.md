# HACKATHON SUBMISSION — CYBERGENESIS

**Project:** CYBERGENESIS — *The Autonomous Self-Defending Digital Twin*
**Creator:** Dr. Abhirup Guha · **Event:** Meta Global AI Developer Hackathon 2026

## Problem
Security tools overwhelmingly stop at detection: logs, alerts, dashboards, and human toil. Nobody proves a defense actually works before a real adversary tests it.

## Solution
An autonomous closed loop on a living 3D digital twin of an enterprise: **Observe → Reason → Propose → Validate → Act → Retest → Prove.** Six agents (Observer, Adversary Simulator, Incident Investigator, Defense Strategist, Defense Executor, Verification Scientist) run three complete incidents — ransomware-like activity, compromised credential, lateral movement — end to end.

## Innovation
- Autonomous **defense validation**, not detection: the identical attack is replayed after remediation and the outcome is computed (reachability, session denial), never asserted.
- AI proposes; a **deterministic, LLM-independent policy engine** authorises only allowlisted simulated actions.
- Honest AI: live Meta inference or clearly-labelled offline deterministic mode — fake success is treated as a test failure.

## Meta AI usage
Meta Muse Spark (`muse-spark-1.3`, Meta Model API) performs incident investigation and defense strategy through structured, Pydantic-validated JSON with confidence, evidence references, retries, timeouts, token accounting, and prompt versioning. See `docs/meta-integration.md`.

## Architecture
FastAPI + SQLAlchemy + NetworkX deterministic twin (10 assets, snapshots, seeded replay) · React/TypeScript + React Three Fiber living twin with WebSocket live events · 14-table audit/evidence store · Docker Compose. Details: `docs/architecture.md`.

## Working demonstration
One click ("Run Autonomous Defense Demo") executes the full loop in ~20 seconds; the 3-minute narrated script is in `docs/demo-script.md`. Verified on the dev machine: backend 12/12 tests, frontend tests + production build, live HTTP experiment COMPLETED with verification PASS, full UI click-through with zero console errors (screenshots in `docs/screenshots/`).

## Results
All 3 scenarios: verification PASS, 100% of objectives blocked (computed), with honest operational-impact costs displayed (e.g., isolation disrupts 2 legitimate paths). A no-defense negative test correctly returns FAIL.

## Limitations
Synthetic graph model, not real traffic; live Meta calls require a judge-provided API key (offline mode is fully functional and labelled); Docker stack provided but unverified on the dev machine (no Docker installed).

## Future
SIEM/EDR connectors (Wazuh), cloud & OT/ICS twins, IaC control testing, continuous resilience scoring — behind the same policy/verification boundary.
