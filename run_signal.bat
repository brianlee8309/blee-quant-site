@echo off
cd /d C:\Kei\ComposerInvest

:: Remove stale git lock files
if exist ".git\index.lock" del /f ".git\index.lock"
if exist ".git\HEAD.lock"  del /f ".git\HEAD.lock"

echo [1/4] Archiving current pages...
python archive_pages.py

echo.
echo [2/4] Pulling Composer allocations and generating Daily Signal pages...
python composer_pull_allocation.py

echo.
echo [3/4] Refreshing 1yr/3yr performance stats on Algorithm185History.html...
python update_performance.py

echo.
echo [4/4] Refreshing per-row signal accuracy on Algorithm185History.html...
python update_accuracy.py

echo.
echo Pushing Daily Signal pages to GitHub Pages...
git add index.html index2.html index_50.html index_185v2.html composer_config.json Algorithm185History.html performance1.html marketDailySummary.html subscribe.html i18n.js analytics.js perf_chart.js performance_data.json BackLog\
git commit -m "Auto: Daily Signal update %date% %time%"
git push origin main

echo.
echo Done - index2.html / index_50.html / index_185v2.html / BackLog live on GitHub Pages.
echo Run run_forecast.bat next to generate the Market Weather Forecast.
echo.
