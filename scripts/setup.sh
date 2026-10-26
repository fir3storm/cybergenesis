#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
python -m venv .venv 2>/dev/null || true
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate
pip install -e "backend[dev]"
cd frontend && npm ci --no-audit --no-fund || npm install --no-audit --no-fund
echo "Setup complete. See scripts/demo.sh"
