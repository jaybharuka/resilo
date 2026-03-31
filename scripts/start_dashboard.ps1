param(
  [int]$Port = 3001,
  [string]$BindAddress = "127.0.0.1",
  [switch]$BuildIfNeeded,
  [switch]$KillExisting
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$dashDir = Join-Path $repoRoot 'dashboard'
Set-Location $dashDir

function Test-Port([int]$p) {
  try { Get-NetTCPConnection -LocalPort $p -ErrorAction Stop | Out-Null; return $true } catch { return $false }
}

if ($KillExisting) {
  foreach ($p in @($Port, 3001, 3000)) {
    try {
      $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
      foreach ($conn in $conns) {
        if ($conn.OwningProcess) {
          try { Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue } catch {}
        }
      }
    } catch {}
  }
}

if ($BuildIfNeeded -or -not (Test-Path (Join-Path $dashDir 'node_modules'))) {
  Write-Host "Installing React dependencies..."
  if (-not (Test-Path (Join-Path $dashDir 'node_modules'))) { npm ci }
}

# Start the interactive dev server using start-all (nodemon + webpack-dev-server)
$envCmd = "cd `"$dashDir`"; `$env:HOST='$BindAddress'; npm run start-all"
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoExit","-Command","$envCmd" -WorkingDirectory $dashDir | Out-Null

# Probe primary and fallback ports
$urls = @("http://127.0.0.1:$Port/", "http://127.0.0.1:3000/", "http://127.0.0.1:3001/", "http://127.0.0.1:3011/")
$okUrl = $null
Write-Host "Waiting for dashboard server..."
for ($i=0; $i -lt 30; $i++) {
  foreach ($u in $urls) {
    try { $r = Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { $okUrl = $u; break } } catch {}
  }
  if ($okUrl) { break }
  Start-Sleep -Milliseconds 500
}
if ($okUrl) {
  Write-Host "Dashboard is up at $okUrl" -ForegroundColor Green
  try { Start-Process $okUrl | Out-Null } catch {}
} else {
  Write-Warning "Dashboard did not respond in time; check the dashboard window for logs."
}
