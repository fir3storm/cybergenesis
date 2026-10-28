# Deploying CYBERGENESIS

## Fastest judge path (local, no Docker)

```bash
# backend (terminal 1)
cd backend && cp ../.env.example .env   # set CERT_DEMO_KEY; MODEL_API_KEY optional for LIVE AI
pip install -e ".[dev]" && uvicorn app.main:app --port 8000
# frontend (terminal 2)
cd frontend && npm ci && npm run dev   # http://localhost:5173
```

Open http://localhost:5173 and click **⚖ Judge Mode** — a 5-step path (Import → Run → Policy → Proof → Preflight) with captions. With no API key the app runs fully offline and says so on the badge.

## Docker Compose

`docker-compose.yml` (repo root) builds backend + frontend. Verified by YAML/schema inspection on the dev machine; Docker itself is not installed there, so the Compose run is unverified locally — the local path above is the verified one.

## Hosted (Render blueprint)

`render.yaml` deploys the backend (offline mode, generated `CERT_DEMO_KEY`) and the static frontend. Set `VITE_API_URL` to the backend URL if it differs, and add `MODEL_API_KEY` on the backend for LIVE Meta AI. Any static host + any Python host works the same way; there is no other infrastructure (SQLite, in-process twin).
