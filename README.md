# CYBERGENESIS

### The Autonomous Self-Defending Digital Twin

[![CI](https://github.com/fir3storm/cybergenesis/actions/workflows/ci.yml/badge.svg)](https://github.com/fir3storm/cybergenesis/actions/workflows/ci.yml)

> **Built for the Meta Global AI Developer Hackathon 2026**
> Created by **Dr. Abhirup Guha** · Powered by **Meta Muse Spark**
>
> *CYBERGENESIS does not merely detect cyberattacks. It tests defenses — and proves resilience.*

![CYBERGENESIS battle loop](docs/battle.gif)

---

## The problem: security teams drown in alerts, but starve for proof

Modern defenders face a structural problem, not a tooling problem:

- **Attacks move at machine speed; defense moves at ticket speed.** Ransomware and lateral movement unfold in minutes, while detection, triage, approval, and remediation still pass through dashboards, queues, and change windows measured in hours.
- **Alerts are abundant; evidence is scarce.** SOCs are flooded with detections, yet most tools stop at *"something looks wrong."* They rarely answer the questions that matter: *What exactly happens next? Will this fix actually stop it? What legitimate work will the fix break?*
- **You cannot rehearse on production.** Teams cannot safely test whether a segmentation rule, credential rotation, or isolation would stop a real attack path — so untested defenses fail for the first time during a real incident.
- **Automation is hard to trust.** Letting an AI change firewall rules or isolate machines feels reckless, so automation stalls at recommendations a human must still verify by hand. The result: skilled analysts burn out on repetitive triage while mean-time-to-contain stays stubbornly high.
- **Attackers adapt; static playbooks don't.** A defense that blocks one route teaches the adversary to find another. Fixed runbooks cannot keep up with an opponent who learns.

**CYBERGENESIS solves this by giving defenders a safe place to fight, learn, and prove.** On a synthetic digital twin, autonomous agents attack and defend continuously: the AI proposes, a deterministic policy engine disposes, an independent verifier replays the attack and produces *proof* — not claims — that the defense works, at what operational cost. Defenses are rehearsed, measured, and certified before they ever touch a real network, and outcome scores are retained for subsequent matches. Learning improvement must be measured separately.

## What is CYBERGENESIS?

CYBERGENESIS is a closed-loop, autonomous cybersecurity digital twin. AI agents watch over a **synthetic** enterprise network. A controlled red team introduces incidents. Meta Muse Spark investigates the telemetry, works out a defense from the live network graph — no per-scenario instructions, it reasons it out — and proposes countermeasures. A deterministic policy engine (independent of the LLM) approves only allowlisted actions. The twin applies them. Then an independent Verification Scientist replays the identical attack to **prove, with computed before/after evidence, whether it now fails**.

Everything is synthetic. No real targets, no scanning, no exploitation, no credential harvesting. See the [threat model](docs/threat-model.md).

## Built during the Hackathon (Oct 26 – Nov 4, 2026)

Everything in this repository was built during the Meta Global AI Developer Hackathon. The git history is the evidence: the first commit is dated **Oct 26, 2026, 13:00 ET**, one hour after the 12:00 ET kickoff, and every commit since falls inside the event window (`git log --reverse --format='%ad %s' --date=iso`). No code predates the event.

Built in the Hackathon (the 3-minute video shows the twin, loop, guardrails, proof, vision import and Arena):

- **The twin and the closed loop**: synthetic enterprise twin compiled from device configs, attack simulation, Observer → Investigator → Strategist → Policy → Executor → Verifier.
- **Meta AI integration**: Muse Spark agents with Pydantic-validated JSON, evidence citations, token budgets, retries, honest offline fallback, a real-call health check; multimodal photo-to-twin import; Muse Spark Open via Baseten.
- **Guardrails**: deterministic policy engine, allowlisted typed actions, human approval (in the UI or by phone QR).
- **Proof**: independent replay verification, Ed25519-signed certificates verifiable offline, Menger min-cut optimality proofs, board briefing with NIST CSF / CIS control evidence.
- **Arena**: live red-vs-blue matches with score memory, held-out strategy evaluation, signed winner proofs.
- **Preflight**: attack-path regression check (API, CLI, GitHub Action) that blocks a change reopening an attack path.

## Agentic by design

CYBERGENESIS is a multi-agent system that completes a security task end to end without scripted answers:

- **Autonomy**: one click runs observe → investigate → propose → rehearse → validate → apply → verify → prove. No step is hard-coded per scenario; the Strategist derives the defense from the live attack graph.
- **Decisions**: Muse Spark weighs evidence and business impact, picks among simulated candidates, and in the Arena plays both attacker and defender. Each decision stores role, evidence refs, confidence, model ID, timestamp and live/offline mode.
- **Coordination**: specialist agents hand off through a typed blackboard; the policy engine, human approval and the independent verifier are checkpoints, not afterthoughts.
- **Safety**: agents get no shell, filesystem or network access; only allowlisted, typed actions can touch the twin.

## Why Meta AI is essential

Muse Spark plays **both sides**:

- **Blue team** — investigates evidence-cited telemetry and proposes defenses from the live graph. Historical live spot-checks cover three scenarios; see the evidence scope in [Evaluation](docs/evaluation.md).
- **Red team** — in the Arena and battle rounds, it chooses among policy-validated attack paths and adapts while the twin hardens itself.
- **Vision** — its multimodal capability turns a whiteboard photo into a working digital twin (Twin Designer → "Try sample"), schema-validated before it becomes a twin.
- **Board briefing** — drafts a plain-language CISO summary restricted to verified facts.
- **Open weights** — Meta's **Muse Spark Open** is wired in as a provider through Baseten (`meta-models/muse-spark-open-1026`), selectable in Settings; it needs a Baseten key and was not used in the demo video.

The demo video runs **Muse Spark 1.3** live (accessed through the Command Code gateway); the direct Meta Model API is the default provider when a funded key is set.

With no API key, the app says so honestly and runs a clearly labelled deterministic simulation instead. Meta AI is the difference between a scripted demo and an adaptive adversary. Provider failure is always reported — fake success is treated as a test failure.

![Welcome — LIVE META AI](docs/screenshots/01-welcome.png)
![Living Twin](docs/screenshots/02-living-twin.png)
![Verification Lab](docs/screenshots/05-verification-lab.png)

---

## The Arena — red vs blue, self-learning until someone wins

The newest battleground. Pick any twin and scenario, choose a strategy, and spectate:

- **Red wins** by reaching the protected target after a defense. **Blue wins** by leaving Red no validated path, or by surviving every round.
- Each round: Red picks a validated attack path → Blue picks a candidate defense through the same policy gate → the replay check decides the round.
- **The AI picks, the scores learn.** Muse Spark chooses only among validated moves (an invalid pick is rejected, never applied), and a deterministic score memory — persisted across matches — records what blocked and what reached, biasing both sides in the next match.
- Every match is stored, a league table tracks Red/Blue wins per scenario, and the winner receives a **signed winner-proof certificate**, verifiable offline.

Strategy modes: **AI + learning** · **Learning only** · **Deterministic**.

## Proof-carrying defense

When a run's verdict is **PASS**, CYBERGENESIS hands you a proof instead of asking for trust: a self-contained certificate (event hash chain, campaigns replayed, per-campaign unreachable-proof with the blocking rule for every frontier arc, embedded final twin) signed with **Ed25519**. Anyone can verify it offline with only the public key: no shared secret, no LLM, no database.

```powershell
# public key: GET /api/certificates/public-key (also embedded in the certificate)
python scripts/verify_cert.py certificate-<runId>.json --pubkey <public_key_hex>
# VALID ... [Ed25519 verified] — or INVALID, with the exact reason
```

`--pubkey` pins the signer, so a certificate re-signed with someone else's key is rejected. The signing key is generated on first use at `CERT_SIGNING_KEY_PATH` (default `./cert_signing_key.pem`, gitignored); delete it to rotate.

A FAIL run gets no proof button. There is nothing to certify.

**`CERT_DEMO_KEY` is still required** for the legacy HMAC signature that certificates (and Arena winner certificates) also carry; the backend refuses to start without it. Generate one with `python -c "import secrets; print(secrets.token_hex(32))"` and put it in `backend/.env`. `verify_cert.py` checks the HMAC too when `CERT_DEMO_KEY` is set in its environment; changing the key invalidates older HMACs (`HMAC signature mismatch`), so re-download certificates after rotating.

## Proof-carrying defenses

By Menger's theorem, the maximum number of edge-disjoint attacker paths from source to target equals the size of a minimum edge cut, so publishing that many disjoint witness paths proves no defense can succeed by cutting fewer edges. Every certificate now carries an `optimality_proof` (signed by both Ed25519 and the legacy HMAC): the baseline attack graph and its SHA-256, the witness paths, the defense's relevant removed edges, and a verdict — `OPTIMAL` when the cut equals the lower bound, `SUBOPTIMAL` with the exact gap, `NOT_A_CUT` when a path survives, or `NO_PATH_AT_BASELINE`. A third party can check the whole proof from the certificate alone — no twin, no database, no LLM.

```powershell
python scripts/verify_cert.py certificate-<runId>.json --pubkey <public_key_hex>
# OPTIMALITY: OPTIMAL (cut 1 = lower bound 1, 1 edge-disjoint witness paths)
```

## Attack-path regression preflight

Before merging a network change, replay it against every saved scenario on a clone of the twin (the stored twin is never mutated). If the change opens any new source-to-target path, preflight **FAILs** with that exact path. Change ops are typed and allowlisted (`add_link`, `remove_link`, `add_vulnerability`, `remove_vulnerability`, `set_posture`, `add_asset`), or derived by diffing pasted running-configs / CSV against the current twin.

- API: `POST /api/twins/{twin_id}/preflight` with `{change, scenario_ids?}` → `{verdict, results, change_ops, twin_sha256_before, generated_at}` (persists nothing).
- CLI: `python scripts/preflight.py --offline --twin examples/preflight/twin.json --change examples/preflight/regression-change.json --scenarios examples/preflight/scenarios.json` — exit 0 PASS, 1 FAIL, 2 error. Online mode: `--api http://localhost:8000 --twin <id> --change change.json`.
- GitHub Actions: `.github/workflows/attack-path-preflight.yml` runs the offline CLI on pull requests touching `network/**` against `network/twin.json` + `network/change.json` and fails the job on regression.
- UI: **Preflight a change** panel in the Twin Designer (paste ops or configs, PASS/FAIL banner, per-scenario rows, regression path listed).
## Board briefing and control evidence

Every finished run has a one-page **board briefing**: headline, business impact (risk before/after with its 95% CI, users affected, legitimate paths disrupted), decisions requested, and the full decision trail. **Draft with AI** asks the active provider to rephrase the verified facts in plain language. The output is schema-checked and labelled *AI-drafted*, and if the provider is unavailable it falls back to the deterministic text with the reason. **Read aloud** and **.md** export are built in (`GET /api/experiments/{id}/briefing`, `/briefing/markdown`).

Each executed defense is tagged with the **NIST CSF 2.0** subcategories and **CIS Controls v8** it evidences (for example `enforce_mfa` → PR.AA-03 and CIS 6). Every verified run also evidences ID.IM-02, improvements identified from security tests. This mapping is indicative evidence from a simulation, not an audit opinion.

## Judge Mode

**⚖ Judge Mode** on the welcome screen runs the ransomware demo end to end with a caption bar: Attack → Observe → Reason → Propose + simulate → Guardrails → Act → Verify → Prove. Each stage is explained in one plain sentence as it happens, and a FAIL is captioned as a FAIL.

## Counterfactual time machine

Finished a run and wondered *"what if Blue had chosen differently?"* Fork the run at its decision point with an alternative candidate. The fork replays through the same policy gate and verifier as a brand-new recorded run — **the original is never changed** — and the Compare view shows both timelines and both twins side by side, with metric deltas for disruption, risk, rounds, and verdict.

## Approve from your phone

Some defenses disrupt legitimate paths, so they wait for a human. The approval card shows a **QR code**: scan it on the same Wi-Fi and your phone gets the action list, the impact, and Approve/Reject buttons. The link carries a one-time token that dies with the approval — reused, expired, or already-decided tokens all return **403** — and the decision joins the same audit trail, recorded as *approved via mobile*.

---

## Benchmark

50 seeded attacker/defender pairs (`python scripts/benchmark.py`, details in [docs/benchmark.md](docs/benchmark.md) and the in-app Benchmark page):

| Defender | Verification PASS | Mean effectiveness | Mean optimality gap | Mean legit paths disrupted |
|---|---|---|---|---|
| none | 0/50 (0%) | 0.0% | — (no defense) | 0.00 |
| offline | 50/50 (100%) | 100.0% | 0.16 | 0.00 |
| simulate | 50/50 (100%) | 100.0% | 0.16 | 0.00 |

## The scenarios

1. **Ransomware-like activity** — synthetic file-modification burst → isolate the workstation → replay proves the file server unreachable.
2. **Compromised credential** — suspicious admin session → revoke session + rotate the synthetic credential → replayed access denied.
3. **Lateral movement** — graph attack path web → app → database → segmentation at the choke point → replay proves the database unreachable.
4. **Data exfiltration** — synthetic bulk staging database → app → web → internet → egress segmentation at the DMZ → replay proves the database cannot reach the internet.
5. **Red vs Blue Battle** — the adaptive adversary retries over multiple rounds while the twin hardens; the seed of the Arena.

## Design your own

- **Twin Designer** — build a custom topology from the component palette (drag assets, click two to connect, save, activate), or photograph a whiteboard and let Muse Spark vision generate the twin.
- **Import your network** — paste one or more running-configs (Cisco IOS, JunOS, FortiOS, PAN-OS, RouterOS) or a CSV inventory. Links are inferred from shared subnets and interface descriptions; weaknesses the config itself shows (telnet, default SNMP community, permit-any ACLs, users without MFA) become vulnerabilities. The result is a saved twin, ready to attack and defend (`POST /api/twins/import`). Pitch: *before you push a firewall change, prove it doesn't open a path to your crown jewels.*
- **Attack Playbook** — compose a custom scenario from the allowlisted step/defense libraries and run it through the identical loop.
- **Component Library** — browse every asset type, attack step, and defense action the policy engine accepts (`GET /api/library`).

Extras: Demo Commentary narration, human-readable Markdown reports, a live Meta token meter, Replay-with-Seed-42 telemetry-identity proof, keyboard shortcuts (Space / R / 1–4), and a full 3D living twin with a 2D accessibility fallback.

---

## Quick start (local)

Requires Python 3.12+ and Node 20+. From the repository root, prepare the backend once:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e "./backend[dev]"
if (-not (Test-Path backend/.env)) { Copy-Item .env.example backend/.env }
python -c "from pathlib import Path; import secrets; p=Path('backend/.env'); s=p.read_text(); p.write_text(s.replace('CERT_DEMO_KEY=\n', 'CERT_DEMO_KEY='+secrets.token_hex(32)+'\n'))"
```

Set `MODEL_API_KEY` in `backend/.env` for live Meta inference, or leave it empty for labelled offline mode. Install the frontend dependencies once:

```powershell
cd frontend
npm ci
cd ..
.\scripts\start.ps1
```

The launcher checks dependencies and the signing key, waits for both services to respond, then opens <http://localhost:5173>. Use `-CheckOnly` to validate setup without launching. Unix setup and manual two-terminal startup are in [DEPLOY.md](DEPLOY.md).

Open **Run Autonomous Defense Demo**, or **Judge Mode** for narrated stages.

### AI providers (live mode)

CYBERGENESIS was built on **Meta Muse Spark**, and it now speaks to five providers — all through the same OpenAI-compatible chat API, so every agent works with any of them. Switch live in **Settings → AI provider** (no restart): paste a key, pick a model, activate. Keys are stored on this machine only and are never displayed or returned by any API.

| Provider | Default endpoint | Key |
|---|---|---|
| Meta Muse Spark | `https://api.meta.ai/v1` | `MODEL_API_KEY` |
| Command Code | `https://api.commandcode.ai/provider/v1` | `COMMANDCODE_API_KEY` |
| Kilo Code (Kilo Gateway) | `https://ai-gateway.kilo.ai/api/v1` | `KILO_API_KEY` |
| Google AI Studio (Gemini) | `https://generativelanguage.googleapis.com/v1beta/openai` | `GOOGLE_API_KEY` |
| Baseten (Meta open-weight Muse Spark Open) | `https://inference.baseten.co/v1` | `BASETEN_API_KEY` |

Without a key, the app runs in clearly labelled **OFFLINE SIMULATION** mode (deterministic, evidence-derived — never presented as AI inference). Provider failure is reported honestly, never faked. Environment variables work too (see `.env.example`); Settings choices override them at runtime:

```powershell
$env:MODEL_API_KEY = "<your key>"   # backend env only, never committed or displayed
$env:META_MODEL = "muse-spark-1.3"
```

Restart the backend; the header badge switches to **LIVE … AI** for the active provider and `/api/models/status` reports reachability.

## Tests

```powershell
cd backend;  python -m pytest -q;  python -m ruff check app tests
cd frontend; npm test; npm run build; npm run test:e2e   # Playwright, requires servers running
```

The automated suites cover scenario replay, policy rejection, malformed model responses, certificate tampering and signer pinning, imports, briefing fallback, access controls, counterfactual forks, mobile approval and Arena outcomes. Frontend coverage includes Vitest and Playwright flows. Current verification counts and commands are recorded in [TASKS.md](TASKS.md).

Normal tests run offline. The explicitly enabled Meta integration check and historical live evidence are documented in [Evaluation](docs/evaluation.md); offline results do not establish live-model performance.

## Documentation

[Architecture](docs/architecture.md) · [Meta integration](docs/meta-integration.md) · [Evaluation](docs/evaluation.md) · [Demo script](docs/demo-script.md) · [Threat model](docs/threat-model.md) · [Hackathon submission](HACKATHON_SUBMISSION.md)

---

*Built with Meta Muse Spark for the Meta Global AI Developer Hackathon 2026. All data is synthetic; the twin defends only itself.*
