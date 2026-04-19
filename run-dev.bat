@echo off
setlocal enabledelayedexpansion

REM ─── Resilo dev launcher ──────────────────────────────────────────────────
REM Loads .env.dev, kills stale processes, starts 3 services,
REM health-checks each one before continuing.
REM
REM  FastAPI Auth   → http://localhost:5001  (health: /auth/health)
REM  FastAPI Core   → http://localhost:8000  (health: /health/live)
REM  React dev      → http://localhost:3000  (PORT locked)
REM ──────────────────────────────────────────────────────────────────────────

echo.
echo ╔══════════════════════════════════════════╗
echo ║         Resilo Dev Environment           ║
echo ╚══════════════════════════════════════════╝

REM ── Load .env.dev ──────────────────────────────────────────────────────────
if not exist "%~dp0.env.dev" (
    echo [WARN] .env.dev not found — using defaults
) else (
    echo [env]  Loading .env.dev...
    for /f "usebackq tokens=1,* delims==" %%A in ("%~dp0.env.dev") do (
        set "line=%%A"
        if not "!line:~0,1!"=="#" if not "!line!"=="" (
            set "%%A=%%B"
        )
    )
)

REM ── Kill stale processes ───────────────────────────────────────────────────
echo [1/4] Killing stale Python and Node processes...
taskkill /F /IM python.exe  >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1
taskkill /F /IM node.exe    >nul 2>&1

REM Free ports explicitly (belt-and-suspenders)
for %%P in (5001 8000 3000) do (
    for /f "tokens=5" %%i in ('netstat -ano 2^>nul ^| findstr ":%%P " ^| findstr LISTENING') do (
        taskkill /F /PID %%i >nul 2>&1
    )
)
timeout /t 2 /nobreak >nul

REM ── FastAPI Auth ───────────────────────────────────────────────────────────
echo [2/4] Starting Auth API on :5001...
start "Auth API :5001" cmd /k ".venv\Scripts\uvicorn.exe app.api.auth_api:app --host 127.0.0.1 --port 5001 --reload"

set attempts=0
:wait_auth
timeout /t 2 /nobreak >nul
curl -sf http://localhost:5001/auth/health >nul 2>&1
if %errorlevel%==0 (
    echo        Auth API  ✓  ready
    goto :auth_ok
)
set /a attempts+=1
if %attempts% lss 15 (
    echo        Auth API  …  waiting ^(%attempts%/15^)
    goto :wait_auth
)
echo.
echo [FATAL] Auth API failed to start. Check the "Auth API :5001" window for errors.
echo         Fix the issue then run-dev.bat again.
echo.
pause
exit /b 1
:auth_ok

REM ── FastAPI Core ───────────────────────────────────────────────────────────
echo [3/4] Starting Core API on :8000...
start "Core API :8000" cmd /k ".venv\Scripts\uvicorn.exe app.api.core_api:app --host 127.0.0.1 --port 8000 --reload"

set attempts=0
:wait_core
timeout /t 2 /nobreak >nul
REM /health/ready checks DB connectivity — if this passes, the DB is up
curl -sf http://localhost:8000/health >nul 2>&1
if %errorlevel%==0 (
    echo        Core API  ✓  ready ^(DB connected^)
    goto :core_ok
)
set /a attempts+=1
if %attempts% lss 15 (
    echo        Core API  …  waiting ^(%attempts%/15^)
    goto :wait_core
)
echo.
echo [FATAL] Core API + DB did not become ready after 30s.
echo         Check the "Core API :8000" window — likely a DB connection failure.
echo         Verify PostgreSQL is running: pg_ctl status -D your_data_dir
echo.
pause
exit /b 1
:core_ok

REM ── React dev server (port locked) ───────────────────────────────────────────────────
echo [4/4] Starting React dev server on :3000...
start "React :3000" cmd /k "cd /d %~dp0dashboard && set PORT=3000 && npx craco start"

echo.
echo ──────────────────────────────────────────────────────
echo  All services started.
echo.
echo  Open:   http://localhost:3000
echo  Admin:  Set ADMIN_DEFAULT_PASSWORD in .env
echo.
echo  IMPORTANT: use http://localhost:3000 — never 127.0.0.1
echo  React will be available in ~30s (CRA compile time)
echo ──────────────────────────────────────────────────────
echo  run stop-dev.bat to kill everything cleanly
echo.
