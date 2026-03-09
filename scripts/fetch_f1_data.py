import requests
import json
import base64
import os

# 1. AUTHENTICATION (Postman: "Login By Password")
def get_auth_token():
    auth_url = "https://api.formula1.com/v2/account/subscriber/authenticate/by-password"
    payload = {
        "Login": os.getenv("F1_EMAIL"),
        "Password": os.getenv("F1_PASSWORD"),
        "DistributionChannel": "d861e38f-05ea-4063-8776-a7e2b6d885a4"
    }
    headers = {"apiKey": "fCUCjWrKPu9ylJwRAv8BpGLEgiAuThx7"} # Default F1 API Key
    
    response = requests.post(auth_url, json=payload, headers=headers)
    token = response.json()['data']['subscriptionToken']
    
    # Generate X-F1-Cookie-Data (Base64 encoded JSON)
    cookie_json = json.dumps({"data": {"subscriptionToken": token}})
    encoded_cookie = base64.b64encode(cookie_json.encode()).decode()
    return encoded_cookie

# 2. FETCH LEAGUE (Postman: "Authenticated -> Leagues")
def fetch_league_data(cookie):
    league_id = "YOUR_LEAGUE_ID" # Get this from your browser URL when viewing your league
    url = f"https://fantasy-api.formula1.com/partner_games/f1/leagues/{league_id}"
    headers = {"X-F1-Cookie-Data": cookie}
    
    response = requests.get(url, headers=headers)
    return response.json()

# 3. SAVE TO FILE
if __name__ == "__main__":
    cookie = get_auth_token()
    data = fetch_league_data(cookie)
    
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=4)
