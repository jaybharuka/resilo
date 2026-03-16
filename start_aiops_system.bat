@echo off
echo 🚀 Starting AIOps Dashboard System...
echo.

REM Kill any existing processes on these ports
echo 🔄 Cleaning up existing processes...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5000') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :3000') do taskkill /f /pid %%a >nul 2>&1

echo.
echo 📡 Starting Real-Time API Server (Port 5000)...
cd /d "D:\AIOps Bot"
start "AIOps API Server" cmd /k ".\.venv\Scripts\python.exe realtime_api_server.py"

echo.
echo ⏱️ Waiting for API server to start...
timeout /t 5 /nobreak >nul

echo.
echo 🌐 Starting React Dashboard (Port 3000)...
cd /d "D:\AIOps Bot\dashboard"
start "AIOps Dashboard" cmd /k "npm start"

echo.
echo ✅ AIOps Dashboard System Started!
echo.
echo 📊 Dashboard: http://localhost:3000
echo 🔌 API Server: http://localhost:5000
echo.
echo 💡 Tips:
echo   - Real-time data updates every 2 seconds
echo   - Try the AI chat feature for system insights
echo   - Navigate using the sidebar menu
echo   - Set GEMINI_API_KEY in .env for enhanced AI responses
echo.
echo Press any key to exit setup...
pause >nul