@echo off
cd /d C:\Kei\ComposerInvest

:: Remove stale git lock file if it exists (prevents git errors after crashes)
if exist ".git\index.lock" (
    echo Removing stale git lock file...
    del /f ".git\index.lock"
)

echo Archiving current pages before overwrite...
python archive_pages.py

echo.
echo Running Composer allocation pull...
python composer_pull_allocation.py

echo.
echo Running market temperature report...
python market_report.py

echo.
echo Done! Press any key to close.
pause
