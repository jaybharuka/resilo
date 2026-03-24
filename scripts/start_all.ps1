param(
  [int]$Port = 3001,
  [string]$BindHost = "127.0.0.1",
  [switch]$OpenRegistration,
  [switch]$AllowActions,
  [string]$AdminEmail = "",
  [securestring]$AdminPassword
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# Free common ports (optional best-effort)
function Stop-PortListener([int]$p) {
  try {
    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) { if ($c.OwningProcess) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue } }
  } catch {}
}
Stop-PortListener 5000
Stop-PortListener $Port
Stop-PortListener 3001
Stop-PortListener 3011

# Start backend (new terminal)
$backendArgs = @{
  OpenRegistration = $OpenRegistration
  AllowActions     = $AllowActions
  AdminEmail       = $AdminEmail
}
if ($AdminPassword) { $backendArgs['AdminPassword'] = $AdminPassword }
& (Join-Path $here 'start_backend.ps1') @backendArgs

# Start dashboard (new terminal)
& (Join-Path $here 'start_dashboard.ps1') -Port $Port -BindAddress $BindHost -BuildIfNeeded -KillExisting

Write-Host "All services started (or attempted)." -ForegroundColor Green
