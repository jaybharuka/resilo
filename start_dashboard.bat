@echo off
echo 🚀 Starting AIOps Dashboard System
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH
    echo Please install Python 3.8+ and try again
    pause
    exit /b 1
)

REM Check if Node.js is available
node --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Node.js is not installed or not in PATH
    echo Please install Node.js 16+ and try again
    pause
    exit /b 1
)

echo ✅ Python and Node.js are available
echo.

REM Install Python dependencies
echo 📦 Installing Python dependencies...
pip install flask flask-cors psutil transformers torch --quiet
if errorlevel 1 (
    echo ⚠️ Some Python packages may have failed to install
    echo The system will still work with reduced functionality
)

echo.

REM Install Node.js dependencies
echo 📦 Installing React dependencies...
cd dashboard
call npm install --silent
if errorlevel 1 (
    echo ❌ Failed to install React dependencies
    pause
    exit /b 1
)

cd ..

echo.
echo 🎯 Starting servers...
echo.

REM Start API server in background
echo 🔌 Starting API Server (Port 5000)...
start "AIOps API Server" python api_server.py

REM Wait a moment for API server to start
timeout /t 3 /nobreak >nul

REM Start React development server
echo 🌐 Starting React Dashboard (Port 3000)...
cd dashboard
start "AIOps Dashboard" npm start

cd ..

echo.
echo 🎉 AIOps Dashboard is starting up!
echo.
echo 📊 Dashboard:     http://localhost:3000
echo 🔌 API Server:    http://localhost:5000
echo 📋 API Health:    http://localhost:5000/api/health
echo.
echo ⚡ The dashboard should open in your browser automatically
echo 📱 If not, navigate to http://localhost:3000
echo.
echo Press any key to open the dashboard manually...
pause >nul

REM Open dashboard in default browser
start http://localhost:3000

echo.
echo 🔄 Servers are running in separate windows
echo 🛑 Close this window or press Ctrl+C to stop monitoring
echo.

REM Keep this window open to show status
:loop
timeout /t 30 /nobreak >nul
echo ⏰ %date% %time% - System monitoring active...
goto loop