@echo off
title BLEE Quant Pro Trader

:: Navigate to src folder (relative to this script's location)
cd /d "%~dp0..\src"
if errorlevel 1 (
    echo [ERROR] Could not find src folder.
    pause
    exit /b 1
)

:: Check for .env file
if not exist ".env" (
    echo [ERROR] .env file not found in src\
    echo Run install.bat first, then edit src\.env with your credentials.
    pause
    exit /b 1
)

:: Check for Schwab token
if not exist "schwab_token.enc" (
    echo.
    echo [WARNING] No Schwab token found.
    echo Run auth_schwab.bat first to authenticate with Schwab.
    echo.
    echo Starting anyway — you can configure settings in the app.
    echo.
    timeout /t 3 >nul
)

echo Starting BLEE Quant Pro Trader...
echo Open http://127.0.0.1:5060 in your browser.
echo Press Ctrl+C to stop.
echo.

python trader_client.py

if errorlevel 1 (
    echo.
    echo [ERROR] App exited with an error. Check the output above.
    pause
)
