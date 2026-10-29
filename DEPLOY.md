# Deploying CYBERGENESIS

## Local setup

Requires Python 3.12+ and Node 20+. From the repository root, on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e "./backend[dev]"
if (-not (Test-Path backend/.env)) { Copy-Item .env.example backend/.env }
python -c "from pathlib import Path; import secrets; p=Path('backend/.env'); s=p.read_text(); p.write_text(s.replace('CERT_DEMO_KEY=\n', 'CERT_DEMO_KEY='+secrets.token_hex(32)+'\n'))"
cd frontend
npm ci
cd ..
.\scripts\start.ps1 -CheckOnly
.\scripts\start.ps1
```

On macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e './backend[dev]'
test -f backend/.env || cp .env.example backend/.env
python -c "from pathlib import Path; import secrets; p=Path('backend/.env'); s=p.read_text(); p.write_text(s.replace('CERT_DEMO_KEY=\n', 'CERT_DEMO_KEY='+secrets.token_hex(32)+'\n'))"
(cd frontend && npm ci)
bash scripts/start.sh --check
bash scripts/start.sh
```

The key-generation command fills only a blank `CERT_DEMO_KEY`, preserving an existing key. Keep `backend/.env` private. Launchers check dependencies and the key, refuse occupied ports and wait for HTTP readiness. Keep the terminal open; Ctrl+C stops its services. The temporary service-log directory is printed for diagnosis. Windows opens the browser when ready; on Unix open the displayed URL.

For manual startup after setup, use two terminals with the virtual environment active:

```bash
# terminal 1, from repository root
cd backend
python -m uvicorn app.main:app --port 8000
# terminal 2, from repository root
cd frontend
npm run dev -- --strictPort
```

Open http://localhost:5173 and click **Judge Mode** for captions through Attack, Observe, Reason, Propose, Guardrails, Act, Verify and Prove. Without an API key the app uses labelled offline simulation.

## Live Meta and operator access

Set `MODEL_API_KEY` in `backend/.env` and `OFFLINE_MODE=false` for live Meta inference. `AI_PROVIDER=meta` selects Meta by default; a saved Settings selection can override it. Confirm the provider and mode before recording. Provider failure remains visible and may result in labelled fallback.

The local UI retrieves an automatically generated operator token through the loopback-only bootstrap. If you set `ADMIN_TOKEN` yourself, enter it in Settings. The token authorizes mutations and approval access; the phone approval link uses its own single-use token. Never put the operator token in a `VITE_*` variable or frontend bundle.

For a phone on the same trusted Wi-Fi, manual backend startup needs `--host 0.0.0.0` and a reachable `PUBLIC_BASE_URL`, for example `http://192.168.1.20:8000`. Only expose the backend when the operator gate is configured. The default launcher binds locally.

## Optional hosted setup (Render)

`render.yaml` provides a Python backend and static frontend blueprint. Configure values for the actual deployment URLs:

- Backend `CORS_ORIGINS`: JSON list of frontend origins, for example `["https://cybergenesis-frontend.onrender.com"]`.
- Frontend `VITE_API_URL`: HTTPS backend URL; rebuild after changing it.
- Backend `ADMIN_TOKEN`: private operator credential. Authorized judges enter it in Settings; shared hosting is not an anonymous interactive sandbox.
- Backend `CERT_DEMO_KEY`: generated signing secret; preserve it across deployments.
- Backend `OFFLINE_MODE=false`: no key still means offline; adding `MODEL_API_KEY` enables live Meta calls.
- Backend `PUBLIC_BASE_URL`: HTTPS backend URL for phone approval links.

Persist SQLite, provider settings, Arena memory and the Ed25519 key on durable storage if records must survive redeploys. Run one backend worker: the active twin and approval queue are process-local. The blueprint is configuration, not evidence of an exercised hosted instance. Verify health, operator access, a complete scenario and proof download on deployed URLs before sharing them.
