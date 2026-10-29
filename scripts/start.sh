#!/usr/bin/env bash
# Run after first-time setup in DEPLOY.md. Ctrl+C stops both services.
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
python_command="python3"
if [ -x "$project_root/.venv/bin/python" ]; then python_command="$project_root/.venv/bin/python"; fi
command -v node >/dev/null || { echo 'Node 20+ is required.' >&2; exit 1; }
test -f "$project_root/frontend/node_modules/vite/bin/vite.js" || { echo 'Run npm ci in frontend first.' >&2; exit 1; }
(cd "$project_root/backend" && "$python_command" -c "import uvicorn; from app.core.config import settings; assert settings.cert_demo_key, 'Set CERT_DEMO_KEY in backend/.env (see DEPLOY.md)'")
if [ "${1:-}" = '--check' ]; then echo 'Local dependency and certificate-key checks passed.'; exit 0; fi
"$python_command" -c 'import socket; sockets=[socket.socket() for _ in range(2)]; [s.bind(("127.0.0.1",p)) for s,p in zip(sockets,(8000,5173))]' || { echo 'A service port is already in use.' >&2; exit 1; }
log_directory="$(mktemp -d "${TMPDIR:-/tmp}/cybergenesis-start.XXXXXX")"
(cd "$project_root/backend" && exec "$python_command" -m uvicorn app.main:app --port 8000) >"$log_directory/backend.log" 2>&1 &
backend_pid=$!
(cd "$project_root/frontend" && exec node node_modules/vite/bin/vite.js --strictPort) >"$log_directory/frontend.log" 2>&1 &
frontend_pid=$!
trap 'kill "$backend_pid" "$frontend_pid" 2>/dev/null || true' EXIT
trap 'exit 130' INT TERM
ready=false
for attempt in {1..45}; do
  kill -0 "$backend_pid" "$frontend_pid" 2>/dev/null || { echo "A service exited. Logs: $log_directory" >&2; exit 1; }
  if "$python_command" -c 'import urllib.request; [urllib.request.urlopen(u, timeout=1).close() for u in ("http://127.0.0.1:8000/api/health", "http://127.0.0.1:5173")]' 2>/dev/null; then ready=true; break; fi
  sleep 1
done
if [ "$ready" != true ]; then echo "Services did not become ready. Logs: $log_directory" >&2; exit 1; fi
echo "CYBERGENESIS ready: http://localhost:5173. Ctrl+C stops both services. Logs: $log_directory"
while kill -0 "$backend_pid" "$frontend_pid" 2>/dev/null; do sleep 1; done
echo "A service stopped. Logs: $log_directory" >&2
exit 1
