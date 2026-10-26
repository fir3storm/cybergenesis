#!/usr/bin/env bash
# One-command demo: starts backend (:8000) + frontend (:5173).
# Set MODEL_API_KEY first for LIVE META AI; otherwise labelled OFFLINE mode.
set -e
cd "$(dirname "$0")/.."
(cd backend && python -m uvicorn app.main:app --port 8000) &
BACK=$!
(cd frontend && npm run dev) &
FRONT=$!
trap 'kill $BACK $FRONT 2>/dev/null' EXIT
echo "CYBERGENESIS: http://localhost:5173 — click 'Run Autonomous Defense Demo'"
wait
