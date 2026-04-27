# Resilo Desktop Agent

Lightweight background agent that collects real system metrics from a user's PC or laptop and sends them to the Resilo backend every few seconds.

## Metrics collected

| Metric | Source |
|--------|--------|
| CPU % | `psutil.cpu_percent` |
| Memory % | `psutil.virtual_memory` |
| Disk % | `psutil.disk_usage` (C:\ on Windows, / elsewhere) |
| Network I/O | `psutil.net_io_counters` |
| Process count | `psutil.pids` |
| Uptime | `psutil.boot_time` |
| Temperature | `psutil.sensors_temperatures` (Linux/Mac only) |
| Load average | `psutil.getloadavg` (Linux/Mac only) |

All payloads are sent to the existing `/ingest/heartbeat` endpoint on the FastAPI Core service.

## Run (development)

```bash
# First run — interactive setup wizard
python desktop_agent/main.py
```

Config is stored at `~/.resilo/desktop_agent.json`. Edit it directly to change settings without re-running the wizard.

## Configuration keys

| Key | Description |
|-----|-------------|
| `backend_url` | Resilo Core API URL (default: `http://localhost:8000`) |
| `org_id` | Organisation ID |
| `agent_key` | Agent API key (from Resilo dashboard) |
| `label` | Human-readable agent name |
| `device_id` | UUID assigned on first run (do not change) |
| `consented` | Set `true` after consent is given |
| `autostart` | Auto-register with OS login mechanism |
| `interval` | Seconds between heartbeats (min 2, default 5) |

## Package as executable (PyInstaller)

```bash
pip install pyinstaller psutil
pyinstaller --onefile desktop_agent/main.py --name resilo-agent
```

Produces `dist/resilo-agent.exe` (Windows) or `dist/resilo-agent` (Mac/Linux).

## Auto-start behaviour

When `autostart: true`:

| OS | Mechanism |
|----|-----------|
| Windows | `.bat` file in `%APPDATA%\...\Startup` |
| macOS | LaunchAgent plist (`~/Library/LaunchAgents/`) |
| Linux | systemd user service (`~/.config/systemd/user/`) |

## Offline resilience

The sender buffers up to 50 failed payloads in memory and attempts to flush them before the next heartbeat. On persistent failure it retries with 2 s → 4 s → 8 s backoff.
