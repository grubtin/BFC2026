import requests
import json
import base64
import os
import sys
from datetime import datetime, timezone

# ── CONFIG ────────────────────────────────────────────────────────
LEAGUE_ID    = "C4JXU0PEO03"
AUTH_URL     = "https://api.formula1.com/v2/account/subscriber/authenticate/by-password"
API_KEY      = "fCUCjWrKPu9ylJwRAv8BpGLEgiAuThx7"
DIST_CHAN    = "d861e38f-05ea-4063-8776-a7e2b6d885a4"
HISTORY_FILE = "history.json"

# 2026 F1 calendar — label rounds automatically
GP_CALENDAR = {
    1:  {"gp": "Australian GP",   "flag": "🇦🇺"},
    2:  {"gp": "Chinese GP",      "flag": "🇨🇳"},
    3:  {"gp": "Japanese GP",     "flag": "🇯🇵"},
    4:  {"gp": "Bahrain GP",      "flag": "🇧🇭"},
    5:  {"gp": "Saudi Arabian GP","flag": "🇸🇦"},
    6:  {"gp": "Miami GP",        "flag": "🇺🇸"},
    7:  {"gp": "Emilia Romagna GP","flag": "🇮🇹"},
    8:  {"gp": "Monaco GP",       "flag": "🇲🇨"},
    9:  {"gp": "Spanish GP",      "flag": "🇪🇸"},
    10: {"gp": "Canadian GP",     "flag": "🇨🇦"},
    11: {"gp": "Austrian GP",     "flag": "🇦🇹"},
    12: {"gp": "British GP",      "flag": "🇬🇧"},
    13: {"gp": "Belgian GP",      "flag": "🇧🇪"},
    14: {"gp": "Hungarian GP",    "flag": "🇭🇺"},
    15: {"gp": "Dutch GP",        "flag": "🇳🇱"},
    16: {"gp": "Italian GP",      "flag": "🇮🇹"},
    17: {"gp": "Azerbaijan GP",   "flag": "🇦🇿"},
    18: {"gp": "Singapore GP",    "flag": "🇸🇬"},
    19: {"gp": "United States GP","flag": "🇺🇸"},
    20: {"gp": "Mexico City GP",  "flag": "🇲🇽"},
    21: {"gp": "São Paulo GP",    "flag": "🇧🇷"},
    22: {"gp": "Las Vegas GP",    "flag": "🇺🇸"},
    23: {"gp": "Qatar GP",        "flag": "🇶🇦"},
    24: {"gp": "Abu Dhabi GP",    "flag": "🇦🇪"},
}

# Static player registry — maps API player names to app keys
PLAYER_REGISTRY = {
    "kevcedes": {"name": "Kevcedes",     "owner": "Kevin Liang",    "emoji": "⚡", "color": "#f4a100"},
    "grahhh":   {"name": "GRAHHH racing","owner": "Vivian Nguyen",  "emoji": "🔥", "color": "#ff4757"},
    "leclaren": {"name": "LeClaren F1",  "owner": "Selina Le Khac", "emoji": "🧡", "color": "#3a86ff"},
    "juice":    {"name": "RACING JUICE", "owner": "Justin Tran",    "emoji": "🍊", "color": "#2ec4b6"},
    "thumbi":   {"name": "Thumbi",       "owner": "Thomas George",  "emoji": "👍", "color": "#c77dff"},
}

# ── 1. AUTHENTICATE ───────────────────────────────────────────────
def get_auth_token():
    email    = os.getenv("F1_EMAIL")
    password = os.getenv("F1_PASSWORD")
    if not email or not password:
        print("ERROR: F1_EMAIL and F1_PASSWORD must be set.")
        sys.exit(1)

    print(f"Authenticating as {email}...")
    res = requests.post(AUTH_URL, json={
        "Login": email,
        "Password": password,
        "DistributionChannel": DIST_CHAN,
    }, headers={"apiKey": API_KEY}, timeout=15)

    if res.status_code != 200:
        print(f"ERROR: Auth failed — HTTP {res.status_code}")
        print(res.text[:500])
        sys.exit(1)

    token = res.json().get("data", {}).get("subscriptionToken")
    if not token:
        print("ERROR: No subscriptionToken in response.")
        print(res.text[:500])
        sys.exit(1)

    print("Auth OK.")
    return base64.b64encode(
        json.dumps({"data": {"subscriptionToken": token}}).encode()
    ).decode()

# ── 2. FETCH LEAGUE ───────────────────────────────────────────────
def fetch_league_data(cookie):
    url = f"https://fantasy-api.formula1.com/partner_games/f1/leagues/{LEAGUE_ID}"
    print(f"Fetching league {LEAGUE_ID}...")
    res = requests.get(url, headers={"X-F1-Cookie-Data": cookie}, timeout=15)

    if res.status_code != 200:
        print(f"ERROR: League fetch failed — HTTP {res.status_code}")
        print(res.text[:500])
        sys.exit(1)

    print("League data fetched OK.")
    return res.json()

# ── 3. RESOLVE PLAYER KEY ─────────────────────────────────────────
def resolve_player_key(api_name):
    n = (api_name or "").lower().strip()
    for key, info in PLAYER_REGISTRY.items():
        if (key in n
                or n in info["name"].lower()
                or info["owner"].split()[0].lower() in n
                or n in info["owner"].lower()):
            return key
    return None

# ── 4. LOAD / INIT history.json ───────────────────────────────────
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    return {
        "_meta": {
            "league_id": LEAGUE_ID,
            "league_name": "Baby Formula Championship",
            "season": 2026,
            "last_updated": None,
            "rounds_completed": 0,
        },
        "rounds": [],
        "players": {k: {"id": k, **v} for k, v in PLAYER_REGISTRY.items()},
    }

# ── 5. PARSE API → round snapshot ────────────────────────────────
def parse_round(api_data, history):
    raw = api_data.get("data", {})

    # Detect game week from API or infer
    game_week = raw.get("game_week") or raw.get("current_game_week")
    if not game_week:
        existing = [r["round"] for r in history["rounds"]]
        game_week = max(existing) + 1 if existing else 1
    game_week = int(game_week)

    cal   = GP_CALENDAR.get(game_week, {"gp": f"Round {game_week}", "flag": "🏁"})
    key   = f"R{game_week:02d}"
    label = f"{key} · {cal['gp']} {cal['flag']}"
    print(f"Round: {key} — {cal['gp']}")

    standings_raw = raw.get("standings", [])

    # ── Standings ──
    standings = []
    for entry in standings_raw:
        pkey = resolve_player_key(entry.get("player_name", ""))
        if not pkey:
            print(f"  WARNING: unmatched player '{entry.get('player_name')}' — skipping")
            continue
        tv = entry.get("team_value", 0)
        standings.append({
            "player_key":  pkey,
            "player_name": PLAYER_REGISTRY[pkey]["name"],
            "owner":       PLAYER_REGISTRY[pkey]["owner"],
            "points":      entry.get("total_points", 0),
            "race_points": entry.get("last_race_points", entry.get("race_points", 0)),
            "team_value":  round(tv / 1e6, 1) if tv > 1000 else tv,
        })
    standings.sort(key=lambda x: x["points"], reverse=True)

    # ── Drivers & constructors from picks ──
    drivers_map = {}
    ctors_map   = {}

    for entry in standings_raw:
        for pick in entry.get("picks", []):
            fname = pick.get("first_name", "")
            lname = pick.get("last_name", "")
            full  = f"{fname} {lname}".strip()
            short = f"{fname[0]}. {lname}" if fname else lname
            fp    = pick.get("fantasy_price", 0)
            price = round(fp / 1e6, 1) if fp > 1000 else fp
            pts   = pick.get("total_season_score", pick.get("race_score", 0))
            sel   = round(pick.get("selection_percentage_game_week", 0), 1)
            team  = pick.get("team_name", "")

            if pick.get("is_constructor"):
                nm = lname or full
                if nm not in ctors_map or price > ctors_map[nm]["price"]:
                    ctors_map[nm] = {"name": nm, "price": price, "pts": pts, "delta": 0.0, "sel": sel}
            else:
                if full not in drivers_map or price > drivers_map[full]["price"]:
                    drivers_map[full] = {"name": short, "full": full, "team": team,
                                         "price": price, "pts": pts, "delta": 0.0, "sel": sel}

    # ── Price deltas vs previous round ──
    prev = history["rounds"][-1] if history["rounds"] else None
    if prev:
        pd = {d["full"]: d["price"] for d in prev.get("drivers", [])}
        for d in drivers_map.values():
            if d["full"] in pd:
                d["delta"] = round(d["price"] - pd[d["full"]], 1)
        pc = {c["name"]: c["price"] for c in prev.get("constructors", [])}
        for c in ctors_map.values():
            if c["name"] in pc:
                c["delta"] = round(c["price"] - pc[c["name"]], 1)

    return {
        "round":        game_week,
        "key":          key,
        "label":        label,
        "flag":         cal["flag"],
        "gp":           cal["gp"],
        "date":         datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "standings":    standings,
        "drivers":      sorted(drivers_map.values(), key=lambda x: x["pts"], reverse=True),
        "constructors": sorted(ctors_map.values(),   key=lambda x: x["pts"], reverse=True),
    }

# ── 6. UPSERT ROUND ───────────────────────────────────────────────
def upsert_round(history, rd):
    others = [r for r in history["rounds"] if r["round"] != rd["round"]]
    others.append(rd)
    others.sort(key=lambda r: r["round"])
    history["rounds"] = others
    history["_meta"]["rounds_completed"] = len(others)
    history["_meta"]["last_updated"]     = datetime.now(timezone.utc).isoformat()
    return history

# ── 7. MAIN ───────────────────────────────────────────────────────
if __name__ == "__main__":
    cookie   = get_auth_token()
    api_data = fetch_league_data(cookie)
    history  = load_history()
    rd       = parse_round(api_data, history)
    history  = upsert_round(history, rd)

    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

    print(f"history.json updated — {len(history['rounds'])} round(s) stored.")
    print(f"Latest: {rd['label']}")
