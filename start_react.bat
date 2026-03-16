@echo off
echo 🌐 Starting AIOps React Dashboard...
cd /d "D:\AIOps Bot\dashboard"
echo 📍 Current directory: %CD%
echo 📦 Checking package.json...
if exist package.json (
    echo ✅ package.json found
    echo 🚀 Starting React development server...
    npm start
) else (
    echo ❌ package.json not found in %CD%
    pause
)