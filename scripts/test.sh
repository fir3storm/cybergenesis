#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../backend" && python -m pytest -q && python -m ruff check app tests
cd ../frontend && npm test && npm run build
echo "ALL GATES PASSED"
