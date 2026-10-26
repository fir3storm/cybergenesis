# CYBERGENESIS — The Autonomous Self-Defending Digital Twin

**Created by Dr. Abhirup Guha · Meta Global AI Developer Hackathon 2026 · Powered by Meta Muse Spark**

CYBERGENESIS does not merely detect cyberattacks. It tests defenses and verifies resilience.

A closed-loop autonomous cybersecurity digital twin: AI agents observe a synthetic enterprise, a controlled adversary introduces incidents, Meta Muse Spark investigates and proposes defenses, a deterministic policy engine approves only allowlisted actions, the twin applies them, and an independent Verification Scientist replays the identical attack to prove — with computed before/after evidence — whether it now fails.

![Welcome — LIVE META AI](docs/screenshots/01-welcome.png)
![Living Twin](docs/screenshots/02-living-twin.png)
![Verification Lab](docs/screenshots/05-verification-lab.png)

## Quick start (local, no Docker required)

Backend (Python 3.12+):
```powershell
cd backend
pip install -e .   # or use an existing env with fastapi/uvicorn/sqlalchemy/networkx/httpx
python -m uvicorn app.main:app --port 8000
```

Frontend (Node 20+):
```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173
```

Open http://localhost:5173 → **Run Autonomous Defense Demo**.

## Meta AI (live mode)

Without a key the app runs in clearly-labelled **OFFLINE SIMULATION** mode (deterministic, evidence-derived — never presented as Meta inference). For live inference:

```powershell
$env:MODEL_API_KEY = "<your key>"   # backend env only, never committed or displayed
$env:META_MODEL = "muse-spark-1.3"
```
Restart the backend; the header badge switches to **LIVE META AI** and `/api/models/status` reports provider reachability.

## Docker

Docker was not available on the development machine, so the Compose stack is provided but locally unverified:
```bash
cp .env.example .env   # fill MODEL_API_KEY if desired
docker compose up --build
```

## Tests

```powershell
cd backend;  python -m pytest -q;  python -m ruff check app tests
cd frontend; npm test; npm run build
```
13 backend tests cover all 3 scenarios end-to-end (verification PASS), policy rejection, determinism, failed-defense detection, live-proposal policy-feedback retry (mocked), and honest provider failure. Test runs force `OFFLINE_MODE=true` for hermetic results. Frontend: Vitest + a Playwright smoke test (`npm run test:e2e`, Edge, requires servers running). Live Meta was verified on 2026-10-27: all 3 scenarios PASS with real Muse Spark decisions (see `docs/evaluation.md`).

## The four scenarios
1. **Ransomware-like activity** — synthetic file-modification burst → isolate workstation → replay proves file server unreachable.
2. **Compromised credential** — suspicious admin session → revoke session + rotate synthetic credential → replayed access denied.
3. **Lateral movement** — graph attack path web→app→database → segmentation at the choke point → replay proves database unreachable.
4. **Data exfiltration** — synthetic bulk staging database→app→web→internet → egress segmentation at the DMZ → replay proves database cannot reach the internet.

Extras: toggleable **Demo Commentary** narration panel, human-readable Markdown report (`/api/experiments/{id}/report/markdown`, Download Report .md), live Meta token meter in the header, Replay-with-Seed-42 telemetry-identity proof, keyboard shortcuts (Space/R/1–4).

All data is synthetic. No real targets, scanning, exploitation, or credential harvesting — see `docs/threat-model.md`.

## Docs
`docs/architecture.md` · `docs/meta-integration.md` · `docs/evaluation.md` · `docs/demo-script.md` · `docs/threat-model.md` · `HACKATHON_SUBMISSION.md`
