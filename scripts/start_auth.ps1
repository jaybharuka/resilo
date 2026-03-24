# start_auth.ps1 — Starts the FastAPI Auth Service (port 5001)
# Requires: PostgreSQL running on localhost:5432
# Run from repo root: .\scripts\start_auth.ps1

param(
    [string]$BindAddress = "0.0.0.0",
    [int]$Port = 5001
)

Set-Location "$PSScriptRoot\.."

# Load .env if present
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
Write-Host "Starting AIOps Auth API..." -ForegroundColor Cyan
Write-Host "  URL:      http://${BindAddress}:${Port}" -ForegroundColor White
Write-Host "  Docs:     http://localhost:${Port}/auth/docs" -ForegroundColor White
Write-Host "  Database: $env:DATABASE_URL" -ForegroundColor DarkGray
Write-Host ""

uvicorn app.api.auth_api:app --host $BindAddress --port $Port --reload
