@echo off
cd /d C:\Kei\ComposerInvest

:: Remove stale git lock files
if exist ".git\index.lock" del /f ".git\index.lock"
if exist ".git\HEAD.lock"  del /f ".git\HEAD.lock"

echo Generating Market Weather Forecast (marketDailySummary.html)...
echo Hard cap: 3 minutes. Script will self-terminate if exceeded.
python market_report.py

echo.
echo Pushing marketDailySummary.html to GitHub Pages...
git add marketDailySummary.html BackLog\
git commit -m "Auto: Market Weather Forecast update %date% %time%"
git push origin main

echo.
echo Done - marketDailySummary.html updated and live on GitHub Pages.
echo.
