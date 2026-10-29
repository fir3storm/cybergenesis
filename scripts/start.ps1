# Run after first-time setup in DEPLOY.md. Ctrl+C stops both services.
param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$pythonCommand = if (Test-Path "$projectRoot/.venv/Scripts/python.exe") { "$projectRoot/.venv/Scripts/python.exe" } else { (Get-Command python).Source }
$nodeCommand = (Get-Command node).Source
$viteScript = "$projectRoot/frontend/node_modules/vite/bin/vite.js"
if (-not (Test-Path $viteScript)) { throw 'Frontend dependencies missing: run npm ci in frontend.' }
Push-Location "$projectRoot/backend"
try {
    & $pythonCommand -c "import uvicorn; from app.core.config import settings; assert settings.cert_demo_key, 'Set CERT_DEMO_KEY in backend/.env (see DEPLOY.md)'"
    if ($LASTEXITCODE -ne 0) { throw 'Backend preflight failed: install backend dependencies and configure backend/.env.' }
} finally { Pop-Location }
if ($CheckOnly) { Write-Host 'Local dependency and certificate-key checks passed.'; exit 0 }
foreach ($port in @(8000, 5173)) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
    try { $listener.Start() } catch { throw "Port $port is in use. Stop that service or start manually." } finally { $listener.Stop() }
}
$logDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("cybergenesis-start-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $logDirectory | Out-Null
$backendProcess = $null
$frontendProcess = $null
try {
    $backendProcess = Start-Process -FilePath $pythonCommand -ArgumentList '-m uvicorn app.main:app --port 8000' -WorkingDirectory "$projectRoot/backend" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logDirectory/backend.log" -RedirectStandardError "$logDirectory/backend-error.log"
    $frontendProcess = Start-Process -FilePath $nodeCommand -ArgumentList "`"$viteScript`" --strictPort" -WorkingDirectory "$projectRoot/frontend" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$logDirectory/frontend.log" -RedirectStandardError "$logDirectory/frontend-error.log"
    $ready = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        if ($backendProcess.HasExited -or $frontendProcess.HasExited) { throw "A service exited. Logs: $logDirectory" }
        try {
            $backendHealth = Invoke-WebRequest 'http://127.0.0.1:8000/api/health' -UseBasicParsing -TimeoutSec 1
            $frontendHealth = Invoke-WebRequest 'http://127.0.0.1:5173' -UseBasicParsing -TimeoutSec 1
            if ($backendHealth.StatusCode -eq 200 -and $frontendHealth.StatusCode -eq 200) { $ready = $true; break }
        } catch { }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw "Services did not become ready. Logs: $logDirectory" }
    Write-Host "CYBERGENESIS ready: http://localhost:5173. Ctrl+C stops both services. Logs: $logDirectory"
    Start-Process 'http://localhost:5173'
    while (-not $backendProcess.HasExited -and -not $frontendProcess.HasExited) { Start-Sleep -Seconds 1 }
    throw "A service stopped. Logs: $logDirectory"
} finally {
    foreach ($process in @($backendProcess, $frontendProcess)) {
        if ($null -ne $process -and -not $process.HasExited) { Stop-Process -Id $process.Id -ErrorAction SilentlyContinue }
    }
}
