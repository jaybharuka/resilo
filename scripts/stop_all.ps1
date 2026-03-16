param(
  [int[]]$Ports = @(5000,3001,3011)
)

$ErrorActionPreference = 'Continue'
foreach ($p in $Ports) {
  try {
    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) { if ($c.OwningProcess) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue; Write-Host "Stopped PID $($c.OwningProcess) on port $p" } }
  } catch {}
}
Write-Host "Stop complete."
