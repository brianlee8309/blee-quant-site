@echo off
cd /d C:\Kei\ComposerInvest

:: Remove stale git lock files
if exist ".git\index.lock" del /f ".git\index.lock"
if exist ".git\HEAD.lock"  del /f ".git\HEAD.lock"

echo [Morning Preview] %date% %time%
echo Running morning_preview.py...

python morning_preview.py

echo Done.
