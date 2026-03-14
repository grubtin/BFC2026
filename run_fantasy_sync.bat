@echo off
REM Run this from your home PC after each race weekend
REM It fetches F1 Fantasy data and pushes to GitHub automatically

set F1_FANTASY_EMAIL=your_email@example.com
set F1_FANTASY_PASSWORD=your_password
set F1_FANTASY_LEAGUE_ID=your_league_id

echo Running F1 Fantasy Sync from local machine...
cd /d "%~dp0"
python scripts/f1_fantasy_sync.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Pushing to GitHub...
    git add f1_fantasy.json f1_teams.json
    git commit -m "chore: update f1 fantasy data [skip ci]"
    git push
    echo Done!
) else (
    echo Sync failed - check error above
)
pause
