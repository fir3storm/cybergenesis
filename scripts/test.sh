#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../backend" && python -m pytest -q && python -m ruff check app tests
cd ../frontend && npm test && npm run build
echo "ALL GATES PASSED (e2e: npm run test:e2e, requires servers running + Playwright browsers)"
