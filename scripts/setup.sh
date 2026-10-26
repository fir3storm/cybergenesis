#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
pip install fastapi "uvicorn>=0.32" "pydantic>=2.10" pydantic-settings "sqlalchemy>=2.0" "networkx>=3.3" "httpx>=0.28" pytest pytest-asyncio ruff
cd frontend && npm install
echo "Setup complete. Backend: cd backend && python -m uvicorn app.main:app --port 8000 | Frontend: cd frontend && npm run dev"
