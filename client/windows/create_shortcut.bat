@echo off
title Create Desktop Shortcut — BLEE Quant Pro Trader

:: Get the absolute path to run.bat
set SCRIPT_DIR=%~dp0
set RUN_BAT=%SCRIPT_DIR%run.bat

:: Get desktop path
set DESKTOP=%USERPROFILE%\Desktop
set SHORTCUT=%DESKTOP%\BLEE Quant Pro Trader.lnk

echo Creating desktop shortcut...

:: Use PowerShell to create the shortcut
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$sc = $ws.CreateShortcut('%SHORTCUT%');" ^
  "$sc.TargetPath = '%RUN_BAT%';" ^
  "$sc.WorkingDirectory = '%SCRIPT_DIR%';" ^
  "$sc.WindowStyle = 1;" ^
  "$sc.Description = 'BLEE Quant Pro Trader';" ^
  "$sc.Save()" 2>nul

if exist "%SHORTCUT%" (
    echo.
    echo  Shortcut created on your Desktop:
    echo  "BLEE Quant Pro Trader"
    echo.
    echo  Double-click it to launch the trading app.
) else (
    echo.
    echo  [ERROR] Could not create shortcut automatically.
    echo  You can create it manually:
    echo   1. Right-click your Desktop
    echo   2. New ^> Shortcut
    echo   3. Target: %RUN_BAT%
)

echo.
pause
