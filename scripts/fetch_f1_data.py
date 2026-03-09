import requests
import json
import base64
import os
import sys

# ── CONFIG ────────────────────────────────────────────────────────
LEAGUE_ID = "C4JXU0PEO03"
AUTH_URL   = "https://api.formula1.com/v2/account/subscriber/authenticate/by-password"
API_KEY    = "fCUCjWrKPu9ylJwRAv8BpGLEgiAuThx7"
DIST_CHAN  = "d861e38f-05ea-4063-8776-a7e2b6d885a4"

# ── 1. AUTHENTICATE ───────────────────────────────────────────────
def get_auth_token():
    email    = os.getenv("F1_EMAIL")
    password = os.getenv("F1_PASSWORD")

    if not email or not password:
        print("ERROR: F1_EMAIL and F1_PASSWORD environment variables must be set.")
        sys.exit(1)

    payload = {
        "Login": email,
        "Password": password,
        "DistributionChannel": DIST_CHAN,
    }
    headers = {"apiKey": API_KEY}

    print(f"Authenticating as {email}...")
    response = requests.post(AUTH_URL, json=payload, headers=headers, timeout=15)

    if response.status_code != 200:
        print(f"ERROR: Auth failed — HTTP {response.status_code}")
        print(response.text[:500])
        sys.exit(1)

    body = response.json()
    token = body.get("data", {}).get("subscriptionToken")
    if not token:
        print("ERROR: No subscriptionToken in response:")
        print(json.dumps(body, indent=2)[:500])
        sys.exit(1)

    print("Auth OK.")
    cookie_json    = json.dumps({"data": {"subscriptionToken": token}})
    encoded_cookie = base64.b64encode(cookie_json.encode()).decode()
    return encoded_cookie

# ── 2. FETCH LEAGUE ───────────────────────────────────────────────
def fetch_league_data(cookie):
    url     = f"https://fantasy-api.formula1.com/partner_games/f1/leagues/{LEAGUE_ID}"
    headers = {"X-F1-Cookie-Data": cookie}

    print(f"Fetching league {LEAGUE_ID}...")
    response = requests.get(url, headers=headers, timeout=15)

    if response.status_code != 200:
        print(f"ERROR: League fetch failed — HTTP {response.status_code}")
        print(response.text[:500])
        sys.exit(1)

    data = response.json()
    print("League data fetched OK.")
    return data

# ── 3. SAVE ───────────────────────────────────────────────────────
if __name__ == "__main__":
    cookie = get_auth_token()
    data   = fetch_league_data(cookie)

    with open("data.json", "w") as f:
        json.dump(data, f, indent=4)

    print("data.json written successfully.")
