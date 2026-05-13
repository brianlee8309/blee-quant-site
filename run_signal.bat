@echo off
cd /d C:\Kei\ComposerInvest

:: Remove stale git lock files
if exist ".git\index.lock" del /f ".git\index.lock"
if exist ".git\HEAD.lock"  del /f ".git\HEAD.lock"

echo [1/2] Archiving current pages...
python archive_pages.py

echo.
echo [2/2] Pulling Composer allocations and generating Daily Signal pages...
python composer_pull_allocation.py

echo.
echo Pushing Daily Signal pages to GitHub Pages...
git add index2.html index_50.html index_185v2.html composer_config.json Algorithm185History.html BackLog\
git commit -m "Auto: Daily Signal update %date% %time%"
git push origin main

echo.
echo Done - index2.html / index_50.html / index_185v2.html / BackLog live on GitHub Pages.
echo Run run_forecast.bat next to generate the Market Weather Forecast.
echo.
