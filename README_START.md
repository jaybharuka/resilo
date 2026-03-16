# AIOps Bot — Stable Start on Windows

These scripts make starting/stopping the backend (Flask) and frontend (dashboard server) reliable on Windows.

## Quick start

1) Start both services (recommended)

- Double‑click `start_all.bat` in the repo root, or run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_all.ps1 -Port 3001 -BindHost "127.0.0.1"
```

- This will:
  - Free common ports (5000, 3001/3011)
  - Start backend in its own terminal and wait for health
  - Build the React app if needed and start the dashboard server in its own terminal
  - Open the correct URL in your browser

2) Start individually (if needed)

- Backend only:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_backend.ps1 -AllowActions -OpenRegistration -AdminEmail "admin@example.com" -AdminPassword "Admin123!"
```

- Frontend only:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_dashboard.ps1 -Port 3001 -Host "127.0.0.1" -BuildIfNeeded -KillExisting
```

3) Stop listeners (free ports)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop_all.ps1
```

## Common tips

- Prefer `http://127.0.0.1` over `http://localhost` on Windows to avoid IPv6 (::1) mismatches.
- If you need LAN access, pass `-BindHost "0.0.0.0"` to `start_all.ps1` and open `http://<your-LAN-IP>:3001`. The UI will talk to API at `http://<your-LAN-IP>:5000` automatically.
- The dashboard server can fall back to another port if the preferred one is busy. The script detects the live port and opens the right URL for you.
- If the browser shows “connection refused,” run `stop_all.ps1`, then `start_all.ps1` again to re‑establish clean listeners.

## Environment options

- Backend (Flask): `OPEN_REGISTRATION`, `ALLOW_SYSTEM_ACTIONS`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ALLOWED_ORIGINS`
- Frontend server: `PORT`, `HOST` (scripts set these for you)

## Where things run

- API: `http://127.0.0.1:5000` (by default)
- Dashboard: `http://127.0.0.1:3001` (preferred), fallback to `3011` if 3001 is taken

## Troubleshooting

- Check the two PowerShell terminals opened by the scripts for logs.
- Firewalls: allow `python.exe` (Flask) and `node.exe` (dashboard server) on Private networks.
- If `cmdlet not found` appears, ensure you’re running in PowerShell (not legacy cmd) and ExecutionPolicy allows script execution.
