param(
  [string]$AdminEmail = "",
  [SecureString]$AdminPassword,
  [switch]$OpenRegistration,
  [switch]$AllowActions,
  [string]$AllowedOrigins = ""
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot

# Optional environment setup
if ($AdminEmail) { $env:ADMIN_EMAIL = $AdminEmail }
if ($AdminPassword) {
  $plain = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR(
    [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($AdminPassword)
  )
  $env:ADMIN_PASSWORD = $plain
}
if ($OpenRegistration) { $env:OPEN_REGISTRATION = 'true' }
if ($AllowActions) { $env:ALLOW_SYSTEM_ACTIONS = 'true' }
if ($AllowedOrigins) { $env:ALLOWED_ORIGINS = $AllowedOrigins }

# Start Flask backend in a new window
$appPaths = "$repoRoot\app;$repoRoot\app\api;$repoRoot\app\auth;$repoRoot\app\core;$repoRoot\app\monitoring;$repoRoot\app\security;$repoRoot\app\analytics;$repoRoot\app\remediation;$repoRoot\app\integrations"
$venvPy = Join-Path $repoRoot '.venv\Scripts\python.exe'
$py = if (Test-Path $venvPy) { $venvPy } else { 'python' }
$cmd = "cd `"$repoRoot`"; `$env:PYTHONPATH=`"$appPaths`"; & `"$py`" -u app\api\api_server.py"
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit","-Command","$cmd" -WorkingDirectory $repoRoot | Out-Null

# Wait for health
Write-Host "Waiting for backend health at http://127.0.0.1:5000/health ..."
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:5000/health" -TimeoutSec 2 -ErrorAction Stop
    if ($response.StatusCode -eq 200) {
      $ok = $true
      break
    }
  } catch { }
  Start-Sleep -Milliseconds 500
}
if ($ok) { Write-Host "Backend is healthy (200)." -ForegroundColor Green } else { Write-Warning "Backend did not respond in time; check the backend window for logs." }
