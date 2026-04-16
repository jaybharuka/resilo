@echo off
REM ── Resilo Agent — Windows EXE builder ──────────────────────────────────────
REM Run from the desktop_agent/ folder:  build_exe.bat
REM Output: dist\ResilioAgent.exe  (single file, no installer needed)

echo [build] Installing dependencies...
pip install pyinstaller pystray pillow psutil -q

echo [build] Packaging...
pyinstaller ^
  --onefile ^
  --windowed ^
  --name ResilioAgent ^
  --paths . ^
  --hidden-import resilo_agent ^
  resilo_gui.py

echo.
if exist dist\ResilioAgent.exe (
    echo [build] SUCCESS: dist\ResilioAgent.exe
    echo [build] Share this file with remote users.
) else (
    echo [build] FAILED — check the output above.
)
pause
