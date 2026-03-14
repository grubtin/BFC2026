@echo off
chcp 65001 >nul
set F1_FANTASY_LEAGUE_ID=C4JXU0PEO03

echo.
echo ============================================
echo  Baby Formula Championship - F1 Fantasy Sync
echo ============================================
echo.

cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from python.org
    pause
    exit /b 1
)

python -c "import httpx" >nul 2>&1
if errorlevel 1 (
    echo Installing httpx...
    pip install httpx
)

python scripts/f1_fantasy_sync.py

if errorlevel 1 (
    echo.
    echo SYNC FAILED - see error above.
    echo.
    echo If you see a 401 error, your cookies have expired.
    echo.
    echo How to refresh cookies:
    echo   1. Open Chrome - fantasy.formula1.com
    echo   2. F12 - Network tab - filter: getusergamedaysv1
    echo   3. Reload the page
    echo   4. Right-click request - Copy - Copy as cURL (bash)
    echo   5. Extract the -b '...' value
    echo   6. Paste into scripts\f1_session.json as raw_cookies
    echo.
    pause
    exit /b 1
)

echo.
echo Pushing to GitHub...
git add f1_teams.json
git commit -m "data: sync f1 fantasy [skip ci]"
git push

if errorlevel 1 (
    echo WARNING: Git push failed - data file updated locally.
) else (
    echo SUCCESS: f1_teams.json synced and pushed.
)

echo.
pause
