param(
    [int]$Port = 5000,
    [string]$ScriptPath = "D:\AIOps Bot\aiops_chatbot_backend.py",
    [string]$WorkingDir = "D:\AIOps Bot"
)

Write-Host "[INFO] Attempting to stop any existing backend on port $Port"

try {
    $pids = @()
    try {
        $pids = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    } catch {}

    if (-not $pids -or $pids.Count -eq 0) {
        try {
            $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'aiops_chatbot_backend.py' -and $_.CommandLine -match ("--port {0}" -f $Port) }
            if ($procs) {
                $pids = $procs | Select-Object -ExpandProperty ProcessId
            }
        } catch {}
    }

    foreach ($pid in $pids) {
        try {
            Stop-Process -Id $pid -Force -ErrorAction Stop
            Write-Host "[OK] Stopped PID $pid on port $Port"
        } catch {}
    }
} catch {}

# As an extra safety, terminate any stray backend processes regardless of port
try {
    $strays = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'aiops_chatbot_backend.py' }
    foreach ($p in $strays) {
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "[OK] Stopped stray backend PID $($p.ProcessId)"
        } catch {}
    }
} catch {}

Start-Sleep -Seconds 1

Write-Host "[INFO] Starting backend with updated code..."
$python = "python"
$arguments = @($ScriptPath, "--port", "$Port", "--allow-actions")
Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $WorkingDir -WindowStyle Hidden

# Wait for health
$ok = $false
for ($i = 0; $i -lt 12; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:{0}/health" -f $Port) -TimeoutSec 4
        if ($resp.StatusCode -eq 200) { $ok = $true; break }
    } catch {}
}

if (-not $ok) {
    Write-Error "[ERROR] Backend failed to start on port $Port"
    exit 1
}

Write-Host "[OK] Backend healthy on port $Port. Verifying endpoints..."
try {
    $owner = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess
    if ($owner) {
        $procInfo = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $owner)
        if ($procInfo) {
            Write-Host ("[INFO] Port {0} owned by PID {1}: {2}" -f $Port, $owner, $procInfo.CommandLine)
        }
    }
} catch {}
try {
    $devices = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:{0}/devices" -f $Port) -TimeoutSec 10
    $stats = Invoke-WebRequest -UseBasicParsing -Uri ("http://127.0.0.1:{0}/company-stats" -f $Port) -TimeoutSec 10
    Write-Host "\n/devices:"; $devices.Content
    Write-Host "\n/company-stats:"; $stats.Content
} catch {
    Write-Error "[ERROR] Verification failed: $_"
    exit 1
}

Write-Host "[DONE] Restart and verification complete."
