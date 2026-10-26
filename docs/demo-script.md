# 3-Minute Demo Script

**0:00–0:20 — The Living Twin.** Land on Welcome. "This is CYBERGENESIS: a living digital twin of an enterprise — gateway, firewall, web, app, database, identity, workstations, file server, sensor — glowing in real time. Cyan healthy, amber exposed. Everything you will see is synthetic and isolated."

**0:20–0:40 — Choose the incident.** Click **Run Autonomous Defense Demo** (ransomware-like activity, seeded & reproducible). "We introduce a controlled, synthetic incident. No real malware — typed simulation events only."

**0:40–1:00 — Attack.** Watch the employee workstation turn red, file server suspicious, red attack path pulse. Point at the event timeline: high-volume synthetic file modifications spreading. "The Observer agent detects the anomaly from telemetry — deterministically, from real twin state."

**1:00–1:30 — Meta reasons.** Workflow reaches INVESTIGATING / DEFENSE_PROPOSED. Note the badge: LIVE META AI if a key is configured, otherwise honestly labelled OFFLINE SIMULATION. Open **Agents**: the Investigator's evidence-grounded hypothesis (confirmed vs speculation, confidence), then the Strategist's proposal: isolate the workstation — the least disruptive effective action.

**1:30–2:00 — Policy + action.** Timeline shows POLICY: the deterministic policy engine — independent of the AI — approves only allowlisted actions. The Executor isolates the workstation; a containment ring appears in 3D. "The AI proposes. Deterministic policy decides. Only simulated state changes."

**2:00–2:30 — Prove it.** VERIFICATION: PASS. Open **Verification Lab**: before, the workstation reached the file server; after, unreachable. Effectiveness computed at 100%, time-to-detect/contain measured, and the honest cost: 2 legitimate paths disrupted. "Same attack, replayed against the modified twin. Not a claim — a retest."

**2:30–3:00 — Close.** Open **Evidence** for the append-only audit trail. "CYBERGENESIS does not merely detect cyberattacks. It tests defenses and verifies resilience." Repeat instantly with Reset for the credential and lateral-movement scenarios.

## Demo checklist
- [ ] Backend on :8000 (`/api/health` ok), frontend on :5173
- [ ] Badge mode confirmed (LIVE if key set, else OFFLINE — say which)
- [ ] Reset twin before starting; seed 42
- [ ] Screenshots in `docs/screenshots/` as backup
- [ ] Fallback: everything above works fully offline
