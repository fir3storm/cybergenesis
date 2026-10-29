# HACKATHON SUBMISSION — CYBERGENESIS

**Project:** CYBERGENESIS — *The Autonomous Self-Defending Digital Twin*
**Creator:** Dr. Abhirup Guha · **Event:** Meta Global AI Developer Hackathon 2026

## Problem
Security tools overwhelmingly stop at detection: logs, alerts, dashboards, and human toil. Teams need repeatable evidence that a proposed defense blocks the modeled attack before they apply it.

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

## Arena: red vs blue, score-memory learning (B1–B7 complete)
A second loop pits Red against Blue on the same twin: Red picks a validated attack route, Blue proposes a defense through the deterministic policy gate, and each round is replayed on a clone before anything is applied. The Arena feature set (B1–B7) is complete:
- **Adaptive rerouting**: Red automatically reroutes when Blue blocks only the selected path.
- **Atomic policy rejection**: invalid proposals are rejected as a unit — no partial application.
- **Pydantic-validated AI outputs**: every LLM response is schema-checked before entering the policy engine.
- **Full decision provenance**: agent role, evidence refs, asset IDs, action, justification, confidence, model ID, timestamp, mode (`live`/`offline`), and fallback reason recorded per round.
- **Paired evaluation runner**: `scripts/evaluate_arena.py` compares distinct baselines and score-memory strategies on held-out twins, with optional live Meta calls and explicit cold-start labels; results at `/api/arena/evaluation` and in `docs/arena-evaluation.json`.
- **League table**: recorded Red/Blue wins by scenario surfaced in the UI.

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
FastAPI + SQLAlchemy + NetworkX deterministic twin (snapshots, seeded replay) · React/TypeScript + React Three Fiber living twin with WebSocket live events · 14-table audit/evidence store · local Python/Node launchers, optional Render blueprint. Details: `docs/architecture.md`.

## Working demonstration
One click ("Run Autonomous Defense Demo") executes the full loop; live latency depends on provider calls and approval waits. Judge Mode captions explain each stage. The 3-minute presentation outline is in `docs/demo-script.md`, with screenshots and a recording available under `docs/`. Fresh automated validation results are recorded in `TASKS.md`; these are distinct from historical browser and live-provider checks.

## Benchmark
Reproducible benchmark harness: `python scripts/benchmark.py` runs **50 seeded twin/scenario pairs** across three defenders (none, offline, simulate). Full methodology and results in `docs/benchmark.md`; raw data in `scripts/benchmark_results.json`. All 5 scenarios pass verification under the offline and simulate defenders. Historical live Muse Spark spot-checks are described separately in `docs/evaluation.md`; the offline benchmark does not establish Meta superiority or learning improvement.

## Results
The offline automated suite exercises all five builtin scenarios. The historical live record in `docs/evaluation.md` describes three scenarios with Meta Muse Spark: ransomware, compromised identity and lateral movement. It reports PASS after action-contract feedback was added; the first live ransomware attempt reported FAIL when policy rejected an underspecified action. A no-defense negative test also correctly returns FAIL. This submission does not claim a fresh five-scenario live evaluation or live held-out superiority without a corresponding saved report.

## Limitations
Synthetic graph model, not real traffic; live Meta calls require an API key in backend env (offline mode is fully functional and labelled). Arena 'learning' is deterministic outcome-count score memory, not model training; held-out results in docs/holdout-benchmark.md show the deterministic min-cut removing fewer edges than candidate search - the LLM's value is contextual reasoning, not graph arithmetic. Local + Render deploy paths: DEPLOY.md.

## Future
SIEM/EDR connectors (Wazuh), cloud & OT/ICS twins, IaC control testing, continuous resilience scoring — behind the same policy/verification boundary.
