#!/usr/bin/env bash
# CYBERGENESIS one-command start. Set MODEL_API_KEY first for LIVE META AI.
set -e
cd "$(dirname "$0")/.."
(cd backend && python -m uvicorn app.main:app --port 8000) &
(cd frontend && npm run dev) &
sleep 5
echo "CYBERGENESIS: http://localhost:5173 (backend http://localhost:8000/api/health)"
wait
