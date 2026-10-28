# HACKATHON SUBMISSION — CYBERGENESIS

**Project:** CYBERGENESIS — *The Autonomous Self-Defending Digital Twin*
**Creator:** Dr. Abhirup Guha · **Event:** Meta Global AI Developer Hackathon 2026

## Problem
Security tools overwhelmingly stop at detection: logs, alerts, dashboards, and human toil. Nobody proves a defense actually works before a real adversary tests it.

## Solution
An autonomous closed loop on a living 3D digital twin of an enterprise: **Observe → Reason → Propose → Validate → Act → Retest → Prove.** Six agents (Observer, Adversary Simulator, Incident Investigator, Defense Strategist, Defense Executor, Verification Scientist) run five complete scenarios — ransomware-like activity, compromised credential, lateral movement, data exfiltration, and red-vs-blue battle — end to end. A toggleable Demo Commentary panel narrates the loop for judges, and every run exports a human-readable Markdown evidence report.

## Device emulation
**200 catalog devices, 20 fully emulated flagships, and configuration is the twin.** Every cable, interface, VLAN, ACL, firewall policy, service, user and patch level compiles deterministically into the graph the attack/defense/verification loop uses — defenses *are* config changes (ConfigDiffs), and every commit is a **Verified Commit** that replays known campaigns on a clone and rejects changes that reopen a path, explaining the hop and rule. Devices open in draggable windows with faceplates, GUI config panes, a backend-authoritative CLI (IOS/Junos/FortiOS/PAN-OS/RouterOS/bash/PowerShell dialects), and OS shells (Windows 11/Server, macOS, Linux, ESXi, S7-1500 HMI) that reflect live twin state. 20 framework agents (13 Meta-powered) run on one typed framework with tool permissions and scorecards. *Emulated for simulation. Not affiliated with any vendor.*

## Innovation
- Autonomous **defense validation**, not detection: the identical attack is replayed after remediation and the outcome is computed (reachability, session denial), never asserted.
- AI proposes; a **deterministic, LLM-independent policy engine** authorises only allowlisted simulated actions.
- Honest AI: live Meta inference or clearly-labelled offline deterministic mode — fake success is treated as a test failure.

## Multi-provider Settings
Four providers are integrated behind a unified settings panel: **Meta Muse Spark**, **Command Code**, **Kilo Gateway**, and **Google AI Studio**. Each provider's credentials, model selection, and fallback behaviour are configurable at runtime, allowing judges to swap backends without code changes.

## Arena: red vs blue, self-learning (B1–B7 complete)
A second loop pits Red against Blue on the same twin: Red picks a validated attack route, Blue proposes a defense through the deterministic policy gate, and each round is replayed on a clone before anything is applied. The Arena feature set (B1–B7) is complete:
- **Adaptive rerouting**: Red automatically reroutes when Blue blocks only the selected path.
- **Atomic policy rejection**: invalid proposals are rejected as a unit — no partial application.
- **Pydantic-validated AI outputs**: every LLM response is schema-checked before entering the policy engine.
- **Full decision provenance**: agent role, evidence refs, asset IDs, action, justification, confidence, model ID, timestamp, mode (`live`/`offline`), and fallback reason recorded per round.
- **Paired evaluation runner**: `scripts/evaluate_arena.py` compares deterministic vs learned strategies on held-out twins with frozen evaluation memory; results at `/api/arena/evaluation` and in `docs/arena-evaluation.json`.
- **League table**: ranked comparison of strategies surfaced in the UI.

Honest labels: offline runs say so; a failed provider is recorded as a failure row, never as a success.

## Key features delivered
- **Proof certificates**: cryptographic evidence artifacts for every verified defense.
- **Counterfactual forks**: branch the twin to explore "what if" attack paths without mutating the main graph.
- **Mobile approval**: approve or reject defense proposals from a mobile client.
- **Custom twin designer**: drag-and-drop topology editor backed by the same deterministic compilation pipeline.
- **Attack playbook**: curated library of attack chains runnable against any twin.
- **Component library**: reusable UI building blocks for twin visualization and controls.
- **Replay player**: step-by-step playback of any incident with full provenance.
- **Cinematic mode**: camera follows the attack path node by node for judge demos.

## Meta AI usage
Meta Muse Spark (`muse-spark-1.3`, Meta Model API) performs incident investigation and defense strategy through structured, Pydantic-validated JSON with confidence, evidence references, retries, timeouts, token accounting, and prompt versioning. See `docs/meta-integration.md`.

## Architecture
FastAPI + SQLAlchemy + NetworkX deterministic twin (snapshots, seeded replay) · React/TypeScript + React Three Fiber living twin with WebSocket live events · 14-table audit/evidence store · Docker Compose. Details: `docs/architecture.md`.

## Working demonstration
One click ("Run Autonomous Defense Demo") executes the full loop in ~20 seconds; the 3-minute narrated script is in `docs/demo-script.md`. Verified on the dev machine: backend **236 passed, 1 skipped**, frontend **32 passed** across 11 test files with production build (code-split: 320 KB main / 864 KB lazy 3D chunk), Playwright end-to-end smoke test, 12 screenshots in `docs/screenshots/`.

## Benchmark
Reproducible benchmark harness: `python scripts/benchmark.py` runs **50 seeded twin/scenario pairs** across three defenders (none, offline, simulate). Full methodology and results in `docs/benchmark.md`; raw data in `scripts/benchmark_results.json`. All 5 scenarios pass verification under the offline and simulate defenders. Live Muse Spark spot-checks confirm end-to-end PASS with optimality gap 0 on reachability scenarios.

## Results
All 5 scenarios run **live with Meta Muse Spark**: verification PASS, 100% of objectives blocked (computed), honest operational-impact costs displayed (e.g., isolation disrupts legitimate paths). The first live run failed verification because the model proposed an under-specified action the policy engine rejected — the system reported FAIL rather than faking success; after publishing action contracts to the model plus a policy-feedback retry, live runs pass. A no-defense negative test also correctly returns FAIL.

## Limitations
Synthetic graph model, not real traffic; live Meta calls require an API key in backend env (offline mode is fully functional and labelled); Docker stack provided but unverified on the dev machine (no Docker installed).

## Future
SIEM/EDR connectors (Wazuh), cloud & OT/ICS twins, IaC control testing, continuous resilience scoring — behind the same policy/verification boundary.
