@echo off
cd /d C:\Kei\ComposerInvest

echo BLEE Alert Sender starting at %date% %time%
echo Sending daily allocation alerts to subscribers...
echo.

python alert_sender.py >> alert_sender_run.log 2>&1

echo.
echo Done - check alert_sender.log for results.
echo.
