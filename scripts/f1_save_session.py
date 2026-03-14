"""
f1_save_session.py
──────────────────
Connects to YOUR real Chrome browser (not Playwright's Chromium) so that
Cloudflare / F1 Fantasy bot-detection sees a genuine browser fingerprint.

STEP 1 — Close all Chrome windows, then launch Chrome with remote debugging:

  "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222

  (or put the line above in a .bat file for convenience)

STEP 2 — In that Chrome window, log in to F1 Fantasy manually.
          Make sure you can see your team.

STEP 3 — Run this script.  It will connect to Chrome, extract everything it
          needs, and write scripts/f1_session.json.
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

SESSION_FILE = Path(__file__).parent / "f1_session.json"
CDP_URL       = "http://localhost:9222"


async def main():
    print("=" * 55)
    print("  F1 Fantasy — Session Setup (real Chrome via CDP)")
    print("=" * 55)
    print()
    print("Before running this script you must have:")
    print("  1. Launched Chrome with --remote-debugging-port=9222")
    print("  2. Logged into F1 Fantasy in that Chrome window")
    print()
    input("Press Enter to connect to Chrome and save the session... ")
    print()

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            print(f"❌ Could not connect to Chrome at {CDP_URL}")
            print()
            print("Make sure Chrome is running with:")
            print('  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9222')
            print()
            print(f"  Error: {e}")
            return

        print(f"✅ Connected to Chrome ({len(browser.contexts)} context(s) found)")

        # Use the first (and usually only) browser context
        if not browser.contexts:
            print("❌ No browser contexts found. Make sure Chrome is open and logged in.")
            await browser.close()
            return

        context = browser.contexts[0]

        # Find the F1 Fantasy tab, or fall back to the first available page
        page = None
        for pg in context.pages:
            if "fantasy.formula1.com" in pg.url:
                page = pg
                print(f"  Found F1 Fantasy tab: {pg.url[:60]}")
                break

        if page is None:
            if context.pages:
                page = context.pages[0]
                print(f"  ⚠️  No F1 Fantasy tab found — using: {page.url[:60]}")
                print("  Navigate to fantasy.formula1.com and log in, then re-run.")
                await browser.close()
                return
            else:
                print("❌ No open tabs found.")
                await browser.close()
                return

        # Extract full storage state (cookies + localStorage)
        print("  Extracting storage state...")
        try:
            storage = await context.storage_state()
        except Exception as e:
            print(f"❌ Failed to extract storage state: {e}")
            await browser.close()
            return

        # Extract GUID from localStorage
        guid = ""
        try:
            guid = await page.evaluate("""() => {
                const raw = localStorage.getItem('si-persistroot');
                if (!raw) return '';
                try {
                    const data = JSON.parse(raw);
                    const user = JSON.parse(data.user || '{}');
                    return user.data?.GUID || '';
                } catch { return ''; }
            }""")
        except Exception:
            pass

        # If localStorage GUID not found, try to fish it out of cookies
        if not guid:
            for cookie in storage.get("cookies", []):
                if "guid" in cookie.get("name", "").lower():
                    guid = cookie["value"]
                    print(f"  GUID found in cookie: {cookie['name']}")
                    break

        # Disconnect (don't close — we don't own this browser)
        await browser.close()

    # Persist
    storage["guid"] = guid
    SESSION_FILE.write_text(json.dumps(storage, indent=2))

    print()
    if guid:
        print(f"✅ Session saved → {SESSION_FILE}")
        print(f"   GUID: {guid[:8]}...")
    else:
        print(f"✅ Session saved → {SESSION_FILE}")
        print("⚠️  GUID not found automatically.")
        print()
        print("   To find it manually:")
        print("   1. In Chrome, press F12 → Application tab")
        print("   2. Local Storage → https://fantasy.formula1.com")
        print("   3. Find key: si-persistroot")
        print('   4. Inside that JSON, look for: data.GUID')
        print(f'   5. Add it to {SESSION_FILE} as: "guid": "<your-guid>"')

    print()
    print("You can now run run_fantasy_sync.bat normally.")


asyncio.run(main())
