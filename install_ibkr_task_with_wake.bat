@echo off
:: Reinstalls "IBKR Daily Rebalance" with Wake-to-Run enabled.
:: Self-elevates via UAC prompt if not already running as Administrator.

:: --- Self-elevate ---------------------------------------------------------
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting Administrator privileges...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo Running as Administrator. OK.
echo Reinstalling "IBKR Daily Rebalance" with Wake-to-Run enabled...
echo.

powershell -NoProfile -Command "try { $action = New-ScheduledTaskAction -Execute 'C:\Kei\ComposerInvest\run_ibkr.bat'; $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '3:55PM'; $settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -DontStopOnIdleEnd -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) -ExecutionTimeLimit (New-TimeSpan -Minutes 15); $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest; Register-ScheduledTask -TaskName 'IBKR Daily Rebalance' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force -ErrorAction Stop | Out-Null; exit 0 } catch { Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red; exit 1 }"

set "PSEXIT=%ERRORLEVEL%"

if "%PSEXIT%"=="0" goto :success
goto :failure

:success
echo.
echo SUCCESS - task reinstalled with Wake-to-Run enabled.
echo   - Trigger:           Mon-Fri at 3:55 PM
echo   - WakeToRun:         ON
echo   - StartWhenAvailable: ON  (catches up if missed)
echo   - Restart on fail:   3 retries, 2 min apart
echo.
echo Verifying registration with schtasks...
schtasks /query /tn "IBKR Daily Rebalance" /v /fo LIST | findstr /i "TaskName Status NextRun"
echo.
echo See install_schwab_task_with_wake.bat for Windows power settings notes.
goto :end

:failure
echo.
echo FAILED - PowerShell returned exit code %PSEXIT%.
echo See the ERROR message above for details.
goto :end

:end
echo.
pause
