#!/usr/bin/env bash
# Terminal 1: backend (set MODEL_API_KEY first for LIVE META AI)
# Terminal 2: frontend, then open http://localhost:5173 and click "Run Autonomous Defense Demo"
cd "$(dirname "$0")/../backend" && python -m uvicorn app.main:app --port 8000
