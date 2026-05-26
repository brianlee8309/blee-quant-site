@echo off
cd /d C:\Kei\ComposerInvest

:: Remove stale git lock files
if exist ".git\index.lock" del /f ".git\index.lock"
if exist ".git\HEAD.lock"  del /f ".git\HEAD.lock"

echo IBKR Auto-Trader starting at %date% %time%
echo Symphony: qjmHJ3IR19kmaAlbgkNj (BLEE-187 SGOV Bond 20%% Yield and Min Dual Reversal)
echo.
echo NOTE: run_signal.bat must have already run at 3:51 PM to update index2.html
echo NOTE: TWS must be open and logged in to account U25734106
echo.

echo Running IBKR Auto-Trader...
python ibkr_trader.py >> ibkr_trade_run.log 2>&1

echo.
echo Done - check ibkr_trade_log.csv for trade records.
echo Log written to: C:\Kei\ComposerInvest\ibkr_trade_run.log
echo.
