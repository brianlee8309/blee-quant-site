@echo off
title BLEE Quant Pro Trader — Windows Installer
color 0B

echo.
echo  ==========================================
echo   BLEE Quant Pro Trader — Windows Install
echo  ==========================================
echo.

:: Check Python 3.11+
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found.
    echo  Please install Python 3.11 or later from https://python.org/downloads
    echo  Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

:: Show Python version
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  Found: %%v

:: Navigate to src folder
cd /d "%~dp0..\src"
if errorlevel 1 (
    echo  [ERROR] Could not find src folder. Run install.bat from the windows\ folder.
    pause
    exit /b 1
)

echo.
echo  Installing Python packages...
echo  (This may take 1-2 minutes on first run)
echo.

pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo  [ERROR] Package installation failed.
    echo  Try running as Administrator, or check your internet connection.
    pause
    exit /b 1
)

:: Copy .env.example if .env doesn't exist
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo.
        echo  Created .env from template. Edit src\.env with your Schwab credentials.
    )
)

echo.
echo  ==========================================
echo   Installation complete!
echo  ==========================================
echo.
echo  Next steps:
echo   1. Edit src\.env with your Schwab API credentials
echo   2. Run: windows\auth_schwab.bat  (one-time Schwab login)
echo   3. Run: windows\run.bat  (start the trading app)
echo.
echo  Or run create_shortcut.bat to add a desktop shortcut.
echo.
pause
