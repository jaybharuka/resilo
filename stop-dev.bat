@echo off
echo Stopping all Resilo dev processes...
taskkill /F /IM python.exe  >nul 2>&1
taskkill /F /IM pythonw.exe >nul 2>&1
taskkill /F /IM node.exe    >nul 2>&1
echo Done.
