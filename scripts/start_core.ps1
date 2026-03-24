# start_core.ps1 — Starts the FastAPI Core API (port 8000)
# Requires: PostgreSQL / TimescaleDB on localhost:5432
# Run from repo root: .\scripts\start_core.ps1

param(
    [string]$BindAddress = "0.0.0.0",
    [int]$Port = 8000
)

Set-Location "$PSScriptRoot\.."

if (Test-Path ".env") {
    Get-Content ".env" | Where-Object { $_ -match '^\s*[^#]' -and $_ -match '=' } | ForEach-Object {
        $parts = $_ -split '=', 2
        if ($parts.Count -eq 2) {
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim())
        }
    }
    Write-Host "Loaded .env" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "Starting AIOps Core API..." -ForegroundColor Cyan
Write-Host "  URL:      http://${BindAddress}:${Port}" -ForegroundColor White
Write-Host "  Docs:     http://localhost:${Port}/api/docs" -ForegroundColor White
Write-Host "  Database: $env:DATABASE_URL" -ForegroundColor DarkGray
Write-Host "  Anomaly:  autonomous=$env:ANOMALY_AUTONOMOUS, poll=${env:ANOMALY_POLL_INTERVAL}s" -ForegroundColor DarkGray
Write-Host ""

uvicorn app.api.core_api:app --host $BindAddress --port $Port --reload
