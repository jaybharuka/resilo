@echo off
title AIOps API Server
echo 🚀 Starting AIOps API Server...
cd /d "D:\AIOps Bot"
echo 📍 Current directory: %CD%

echo 🔧 Starting Python Flask API server on port 5000...
"D:\AIOps Bot\.venv\Scripts\python.exe" simple_api_server.py

echo.
echo ❌ API Server stopped. Press any key to restart...
pause
goto :eof