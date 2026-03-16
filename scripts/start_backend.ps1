param(
  [string]$AdminEmail = "",
  [string]$AdminPassword = "",
  [switch]$OpenRegistration,
  [switch]$AllowActions,
  [string]$AllowedOrigins = ""
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot

# Optional environment setup
if ($AdminEmail) { $env:ADMIN_EMAIL = $AdminEmail }
if ($AdminPassword) { $env:ADMIN_PASSWORD = $AdminPassword }
if ($OpenRegistration) { $env:OPEN_REGISTRATION = 'true' }
if ($AllowActions) { $env:ALLOW_SYSTEM_ACTIONS = 'true' }
if ($AllowedOrigins) { $env:ALLOWED_ORIGINS = $AllowedOrigins }

# Start in a new window so it stays up
$cmd = "cd `"$repoRoot`"; python -u .\aiops_chatbot_backend.py"
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit","-Command","$cmd" -WorkingDirectory $repoRoot | Out-Null

# Wait for health
Write-Host "Waiting for backend health at http://127.0.0.1:5000/health ..."
$ok = $false
for ($i=0; $i -lt 30; $i++) {
  try { $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:5000/health" -TimeoutSec 2; if ($r.StatusCode -eq 200) { $ok = $true; break } } catch {}
  Start-Sleep -Milliseconds 500
}
if ($ok) { Write-Host "Backend is healthy (200)." -ForegroundColor Green } else { Write-Warning "Backend did not respond in time; check the backend window for logs." }
# Start Flask backend with optional admin bootstrap and CORS for localhost
param(
    [string]$AdminEmail = "admin@example.com",
    [string]$AdminPassword = "Admin123!",
    [switch]$AllowActions = $true
)

$ErrorActionPreference = 'Stop'
Write-Host "Starting backend in d:\AIOps Bot" -ForegroundColor Cyan
Set-Location -Path "d:\AIOps Bot"

# Environment variables
$env:ADMIN_EMAIL = $AdminEmail
$env:ADMIN_PASSWORD = $AdminPassword
$env:ALLOW_SYSTEM_ACTIONS = if ($AllowActions.IsPresent) { 'true' } else { 'false' }
$env:ALLOWED_ORIGINS = 'http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001'

# Start backend unbuffered, redirecting output to a rotating log
$log = Join-Path (Get-Location) 'backend-5000.out.log'
Write-Host "Logging to $log" -ForegroundColor DarkGray

# Use Start-Process to avoid quoting issues
Start-Process -FilePath "python" -ArgumentList "-u","aiops_chatbot_backend.py" -WorkingDirectory (Get-Location).Path -WindowStyle Minimized

Write-Host "Backend launch attempted. If it doesn't start, open $log for details." -ForegroundColor Green
