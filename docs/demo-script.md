# 3-Minute Demo Script

The whole pitch in one arc: **import an unseen network → AI defends, policy disposes → proof you can check yourself → a change that would reopen the path gets blocked in preflight.**

**0:00–0:30 — Import the unseen network.** Open Twin Designer. Paste the sample running-configs (or drop a whiteboard photo) and import. "This network was not in the training data or the demo script — CYBERGENESIS compiles it into a living twin: cables, VLANs, ACLs, services, weaknesses. Configuration *is* the twin."

**0:30–1:10 — Attack and reasoning.** Run the demo. The workstation turns red, the attack path pulses. Open Agents: the Incident Investigator's hypothesis cites telemetry IDs (`tele-…`) as confirmed vs speculation; the Defense Strategist proposes a defense from the graph alone — it was never told the answer. Note the LIVE / OFFLINE badge and say which mode you are in.

**1:10–1:40 — Policy disposes.** A proposed action is rejected by the deterministic policy engine (show the rejection reason), the revised action is approved and applied. "The AI proposes. Deterministic policy — no LLM — decides. Only allowlisted simulated actions can touch the twin."

**1:40–2:20 — Prove it, don't trust it.** Verification: PASS. Open the Proof card: **OPTIMAL** badge — cut size equals the Menger lower bound, with the edge-disjoint witness paths listed. Download the certificate, then in a terminal:

```powershell
python scripts/verify_cert.py certificate-<runId>.json --pubkey <public_key_hex>
# BASELINE: graph re-derived from embedded baseline twin matches optimality proof
# OPTIMALITY: OPTIMAL (cut 1 = lower bound 1, 1 edge-disjoint witness paths)
# VALID … [Ed25519 verified]
```

"The checker re-derives the attack graph from the embedded baseline twin, replays the cut, and verifies the signature — no server, no LLM, no shared secret. Flip one byte and it fails."

**2:20–3:00 — Block the regression before merge.** In the Designer, open **Preflight a change**: add the link `relay → database` and run. FAIL banner with the exact new path. "The same check runs in GitHub Actions on any PR touching `network/**` (`scripts/preflight.py`, exit 1). A defense that was proven optimal yesterday cannot silently rot tomorrow." Close: "CYBERGENESIS does not merely detect cyberattacks. It tests defenses, proves them optimal, and blocks the change that would break them."

## Demo checklist
- [ ] Backend on :8000 (`/api/health` ok), frontend on :5173
- [ ] Badge mode confirmed (LIVE if key set, else OFFLINE — say which)
- [ ] Reset twin before starting; seed 42
- [ ] Terminal ready with a freshly downloaded certificate + pubkey
- [ ] Screenshots in `docs/screenshots/` as backup; `docs/demo.webm` as full fallback
- [ ] Fallback: everything above works fully offline
