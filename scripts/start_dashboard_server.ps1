# Serve the React build using the included Node/Express server
param(
  [int]$Port = 3001,
  [string]$BindHost = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
Set-Location -Path "d:\AIOps Bot\dashboard"
$env:PORT = "$Port"
$env:HOST = "$BindHost"

Write-Host ("Serving dashboard build at http://{0}:{1}" -f $BindHost, $Port) -ForegroundColor Cyan
# Start minimized
Start-Process -FilePath "node" -ArgumentList "server.js" -WorkingDirectory (Get-Location).Path -WindowStyle Minimized
