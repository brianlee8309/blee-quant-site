@echo off
cd /d C:\Kei\ComposerInvest

:: Remove stale git lock files
if exist ".git\index.lock" del /f ".git\index.lock"
if exist ".git\HEAD.lock"  del /f ".git\HEAD.lock"

echo ============================================================
echo  PHASE 1 — Archive + Daily Signal  (fast, ~30 sec)
echo ============================================================
call run_signal.bat

echo.
echo ============================================================
echo  PHASE 2 — Market Weather Forecast  (up to 3 min)
echo ============================================================
call run_forecast.bat

echo.
echo All done! Press any key to close.
pause
