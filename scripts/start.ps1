# CYBERGENESIS one-command start (Windows)
# Usage: powershell -ExecutionPolicy Bypass -File scripts/start.ps1
# Set $env:MODEL_API_KEY before running for LIVE META AI; otherwise labelled OFFLINE mode.
$root = Split-Path $PSScriptRoot -Parent
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; python -m uvicorn app.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev"
Start-Sleep 6
Start-Process "http://localhost:5173"
Write-Host "CYBERGENESIS: http://localhost:5173 (backend http://localhost:8000/api/health)"
