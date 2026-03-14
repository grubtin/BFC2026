#!/bin/bash
# Run this from your home Mac/Linux after each race weekend

export F1_FANTASY_EMAIL="your_email@example.com"
export F1_FANTASY_PASSWORD="your_password"
export F1_FANTASY_LEAGUE_ID="your_league_id"

echo "Running F1 Fantasy Sync from local machine..."
cd "$(dirname "$0")"
python scripts/f1_fantasy_sync.py

if [ $? -eq 0 ]; then
    echo ""
    echo "Pushing to GitHub..."
    git add f1_fantasy.json f1_teams.json
    git commit -m "chore: update f1 fantasy data [skip ci]"
    git push
    echo "Done!"
else
    echo "Sync failed - check error above"
fi
