"""
f1_fantasy_sync.py
──────────────────
Pulls data from the F1 Fantasy API and writes:

  f1_fantasy.json  — driver / constructor prices & points
  f1_teams.json    — Baby Formula Championship league team picks

AUTH:
  Reads scripts/f1_session.json — update this file weekly with fresh cookies.
  See run_fantasy_sync.bat for instructions on how to get the values.

REQUIRES:
  pip install httpx
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

import httpx

BASE         = "https://fantasy.formula1.com"
SESSION_FILE = Path(__file__).parent / "f1_session.json"
LEAGUE_ID    = os.environ.get("F1_FANTASY_LEAGUE_ID", "")

PLAYER_MAP = {
    # "232016281": "kevcedes",
    # "191134213": "grahhh",
    # "178339760": "leclaren",
    # "178336081": "juice",
    # "178798446": "thumbi",
}


def load_session() -> tuple[str, str]:
    """Returns (guid, raw_cookie_string). Supports both new and old session formats."""
    if not SESSION_FILE.exists():
        print("❌ scripts/f1_session.json not found.")
        print()
        print("Create it with this content:")
        print('  {')
        print('    "guid": "your-guid-here",')
        print('    "raw_cookies": "your-cookie-string-here"')
        print('  }')
        print()
        print("See run_fantasy_sync.bat for instructions.")
        sys.exit(1)

    session     = json.loads(SESSION_FILE.read_text())
    guid        = session.get("guid", "")
    raw_cookies = session.get("raw_cookies", "")

    # Old Playwright format fallback: rebuild cookie string from cookies list
    if not raw_cookies and "cookies" in session:
        raw_cookies = "; ".join(f"{c['name']}={c['value']}" for c in session["cookies"])

    if not guid:
        print("❌ 'guid' missing from f1_session.json.")
        print("   Your GUID is: 62ff616e-135e-11f1-bcc9-110b22c295d5")
        sys.exit(1)

    if not raw_cookies:
        print("❌ 'raw_cookies' missing from f1_session.json.")
        print("   See run_fantasy_sync.bat for instructions.")
        sys.exit(1)

    return guid, raw_cookies


def build_headers(raw_cookies: str) -> dict:
    return {
        "accept":             "application/json, text/plain, */*",
        "accept-language":    "en-US,en;q=0.9",
        "referer":            "https://fantasy.formula1.com/en/",
        "user-agent":         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "sec-ch-ua":          '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile":   "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest":     "empty",
        "sec-fetch-mode":     "cors",
        "sec-fetch-site":     "same-origin",
        "cookie":             raw_cookies,
    }


async def fetch(client: httpx.AsyncClient, url: str) -> dict:
    try:
        resp = await client.get(url)
    except Exception as e:
        print(f"  ⚠️  Request failed: {e}")
        return {}

    if resp.status_code == 401:
        print()
        print("  ❌ 401 — Cookies have expired.")
        print()
        print("  Open Chrome → fantasy.formula1.com → F12 → Network tab")
        print("  Filter: getusergamedaysv1 → Refresh page")
        print("  Right-click request → Copy → Copy as cURL (bash)")
        print("  Extract the cookie string (between -b ' and ')")
        print("  Paste it as 'raw_cookies' in scripts/f1_session.json")
        sys.exit(1)

    if resp.status_code != 200:
        print(f"  ⚠️  {resp.status_code} → {url[:80]}")
        return {}

    try:
        return resp.json()
    except Exception:
        return {}


async def sync():
    guid, raw_cookies = load_session()
    print(f"  Session loaded (GUID: {guid[:8]}...)")

    ts      = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    headers = build_headers(raw_cookies)

    async with httpx.AsyncClient(headers=headers, timeout=30, follow_redirects=True) as client:

        # 1. Schedule
        print("  Fetching schedule...")
        sched    = await fetch(client, f"{BASE}/feeds/v2/schedule/raceday_en.json")
        fixtures = sched.get("Data", {}).get("fixtures", [])
        matchdays = {}
        for fx in fixtures:
            mdid = fx.get("MatchdayId") or fx.get("GamedayId")
            if not mdid:
                continue
            mdid = int(mdid)
            if mdid not in matchdays:
                matchdays[mdid] = {
                    "round":    mdid,
                    "gp":       fx.get("Venue", fx.get("RaceName", f"R{mdid}")),
                    "date":     fx.get("GameDate", "")[:10],
                    "finished": int(fx.get("GDIsLocked", 0)) == 1,
                }
        print(f"  Matchdays: {len(matchdays)}")

        # 2. Players
        print("  Fetching players...")
        players_raw = await fetch(client, f"{BASE}/feeds/drivers/2_en.json")
        all_players = players_raw.get("Data", {}).get("Value", [])
        drivers_all, constrs_all, player_lookup = [], [], {}
        constructor_ids = set()

        for pl in all_players:
            pid   = str(pl.get("PlayerId", ""))
            skill = pl.get("Skill", 1)
            entry = {
                "id":             pid,
                "short_name":     pl.get("DriverTLA", pl.get("DisplayName", "")),
                "full_name":      pl.get("FUllName", ""),
                "team":           pl.get("TeamName", "") or pl.get("FUllName", ""),
                "team_tag":       pl.get("DriverTLA", ""),
                "price":          float(pl.get("Value", 0)),
                "total_points":   float(pl.get("OverallPpints", 0) or 0),
                "points_this_gw": float(pl.get("GamedayPoints", 0) or 0),
            }
            player_lookup[pid] = entry
            if skill == 2:
                constrs_all.append(entry)
                constructor_ids.add(pid)
            else:
                drivers_all.append(entry)

        print(f"  Players: {len(drivers_all)} drivers, {len(constrs_all)} constructors")

        with open("f1_fantasy.json", "w", encoding="utf-8") as f:
            json.dump({
                "last_updated": ts,
                "overall": {"drivers": drivers_all, "constructors": constrs_all},
                "gameweeks": [],
            }, f, indent=2, ensure_ascii=False)
        print("✅ f1_fantasy.json written")

        if not LEAGUE_ID:
            print("⚠️  F1_FANTASY_LEAGUE_ID not set — skipping league sync.")
            return

        # 3. User gamedays
        print("  Fetching user gamedays...")
        gd_raw  = await fetch(client, f"{BASE}/services/user/gameplay/{guid}/getusergamedaysv1/1")
        gd_list = gd_raw.get("Data", {}).get("Value", [])
        if not gd_list:
            print("  ❌ Empty response — cookies may be expired.")
            sys.exit(1)

        completed_mds = {int(k) for k, v in gd_list[0].get("mddetails", {}).items() if v.get("mds") == 3}

        # 4. League standings
        print("  Fetching league standings...")
        league_raw    = await fetch(client, f"{BASE}/services/user/leagues/{LEAGUE_ID}/leaguedetails/1/1/100/1")
        league_val    = league_raw.get("Data", {}).get("Value", {})
        league_name   = league_val.get("leagueName", "Baby Formula Championship") if isinstance(league_val, dict) else "Baby Formula Championship"
        standings_raw = league_val.get("leagueStandings", []) if isinstance(league_val, dict) else (league_val if isinstance(league_val, list) else [])

        teams_output = {
            "last_updated": ts,
            "league_id":    LEAGUE_ID,
            "league_name":  league_name,
            "players":      [],
            "rounds":       [],
        }

        for entry in standings_raw:
            uid    = str(entry.get("socialId") or entry.get("userId") or entry.get("teamId", ""))
            our_id = PLAYER_MAP.get(uid, uid)
            teams_output["players"].append({
                "id":         our_id,
                "name":       unquote(entry.get("teamName") or entry.get("name") or our_id),
                "emoji":      "👤",
                "f1_user_id": uid,
                "guid":       entry.get("guid", ""),
            })

        if teams_output["players"]:
            print()
            print("  League players (add IDs to PLAYER_MAP at top of this file if needed):")
            for p in teams_output["players"]:
                print(f"    \"{p['f1_user_id']}\": \"{p['id']}\",  # {p['name']}")
            print()

        # 5. Per-matchday picks
        for mdid in sorted(matchdays.keys()):
            finished     = mdid in completed_mds
            round_record = {"round": mdid, "gp": matchdays[mdid]["gp"], "confirmed": finished, "teams": []}

            for player in teams_output["players"]:
                p_guid = player.get("guid", "")
                if not p_guid:
                    round_record["teams"].append({"player_id": player["id"], "picks": []})
                    continue

                picks_raw  = await fetch(client, f"{BASE}/services/user/gameplay/{p_guid}/getteam/1/{mdid}/1/1")
                team_data  = picks_raw.get("Data", {}).get("Value", {})
                user_teams = team_data.get("userTeam", [])
                team       = user_teams[0] if user_teams else {}
                raw_picks  = team.get("playerid", [])

                pick_list = [{
                    "id":         str(pk.get("id", "")),
                    "short_name": player_lookup.get(str(pk.get("id", "")), {}).get("short_name", ""),
                    "full_name":  player_lookup.get(str(pk.get("id", "")), {}).get("full_name", ""),
                    "team":       player_lookup.get(str(pk.get("id", "")), {}).get("team", ""),
                    "team_tag":   player_lookup.get(str(pk.get("id", "")), {}).get("team_tag", ""),
                    "type":       "constructor" if str(pk.get("id", "")) in constructor_ids else "driver",
                    "is_star":    bool(pk.get("iscaptain") or pk.get("ismgcaptain")),
                    "price":      player_lookup.get(str(pk.get("id", "")), {}).get("price", 0),
                    "points":     None,
                } for pk in raw_picks]

                round_record["teams"].append({
                    "player_id":        player["id"],
                    "total_points":     float(team.get("ovpoints") or 0) if finished else None,
                    "team_value":       float(team.get("teamval", 0)),
                    "budget_remaining": float(team.get("teambal", 0)),
                    "picks":            pick_list,
                })

            teams_output["rounds"].append(round_record)

        with open("f1_teams.json", "w", encoding="utf-8") as f:
            json.dump(teams_output, f, indent=2, ensure_ascii=False)
        print(f"✅ f1_teams.json — {len(teams_output['players'])} players, {len(teams_output['rounds'])} rounds")


def main():
    print("F1 Fantasy Sync")
    print()
    asyncio.run(sync())


if __name__ == "__main__":
    main()
