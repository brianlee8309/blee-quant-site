@echo off
REM ============================================================
REM  deploy_auth_fix.bat
REM  Commits the auth-flow fixes and pushes to GitHub.
REM  The current git index has 34 staged DELETIONS of essential
REM  pages (index.html, login.html, mission.html, etc.) that
REM  MUST be unstaged before committing — otherwise the live
REM  site would lose those pages.
REM ============================================================
setlocal
cd /d C:\Kei\ComposerInvest

echo.
echo === Step 1: Clear any stale git lock ===
if exist .git\index.lock del /f /q .git\index.lock

echo.
echo === Step 2: Unstage EVERYTHING (cancels the 34 dangerous deletions) ===
git reset HEAD -- .

echo.
echo === Step 3: Show files that exist but were marked for deletion ===
git status --short | findstr /R "^D " && echo  ^!^! none — good
echo.

echo === Step 4: Stage ONLY the real auth fixes ===
git add admin.html auth_guard.js user_bar.js firestore.rules firebase.json

echo.
echo === Step 5: Show what will be committed ===
git status --short
echo.
echo --- diff summary ---
git diff --cached --stat
echo.

echo === Step 6: Commit ===
git commit -m "Fix auth: case-insensitive admin email, fail-closed, session-restore race, marketer tier rank, Firestore rules"

echo.
echo === Step 7: Push to GitHub (publishes to bleeanalytics.com via GitHub Pages) ===
git push origin main

echo.
echo === Done. Hard-refresh the site (Ctrl+F5) to bypass cache. ===
pause
