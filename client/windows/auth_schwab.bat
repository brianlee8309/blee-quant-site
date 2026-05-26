@echo off
title BLEE Quant Pro — Schwab Authentication

cd /d "%~dp0..\src"
if errorlevel 1 (
    echo [ERROR] Could not find src folder.
    pause
    exit /b 1
)

echo.
echo  ==========================================
echo   Schwab Weekly Re-Authentication
echo  ==========================================
echo.
echo  Your browser will open shortly.
echo  Click "Sign in with Schwab" and complete the 2-factor login.
echo  After success, close the browser tab and press Ctrl+C here.
echo.
echo  NOTE: Your browser will show a security warning about the
echo  self-signed certificate. Click Advanced then Proceed.
echo  This is expected and safe — it's a local-only connection.
echo.

python auth_server.py

pause
