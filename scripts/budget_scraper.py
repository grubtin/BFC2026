import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright

# ─────────────────────────────────────────────────────────────────
# f1fantasytools.com/budget-builder — "Required Points" view
#
# Before scraping we must enable display options:
#   ✅ Show points scored in previous 2 races  (checkbox 0)
#   ☐ Show expected points for analyst sims   (leave off)
#   ✅ Show required points next to simulation odds (checkbox 2)
#
# Column layout after enabling those options:
#   DR/CR | $ | R0 Pts | R1 Pts | -0.3 Pts | -0.1 Pts | +0.1 Pts | +0.3 Pts
#
# Each table:
#   index 0 → Drivers      (rows tagged DR)
#   index 1 → Constructors (rows tagged CR)
#
# Tier rows: single <td colspan=N> "Tier A (>=18.5M)" / "Tier B (<18.5M)"
# ─────────────────────────────────────────────────────────────────

SKIP_TAGS = {"-", "DR", "CR", "Pts", "xPts", "$", "R0", "R1", "R2",
             "Odds (pts)", "Odds(pts)", "xΔ$", ""}


def clean_price(raw: str) -> str:
    return raw.replace("$", "").strip()


def to_int_or_str(val: str) -> str:
    """Return value as-is — preserve ≤ signs and negatives exactly as shown."""
    return val.strip() if val else ""


async def enable_display_options(page) -> None:
    """
    Click the settings gear and ensure:
      [0] Show points scored in previous 2 races  → ON
      [1] Show expected points for analyst sims   → OFF
      [2] Show required points next to odds       → ON
    Then select "Required Points" from the dropdown.
    """
    try:
        # Click the settings gear icon
        await page.locator('[data-testid="settings-icon"], button:has(svg), .settings-btn').first.click()
        await page.wait_for_timeout(600)
    except Exception:
        # Try clicking the gear/cog SVG button near T1/T2/T3
        try:
            await page.locator('button').filter(has_text="").nth(3).click()
            await page.wait_for_timeout(400)
        except Exception:
            pass

    # Try to set checkboxes by label text
    try:
        checkboxes = await page.locator('input[type="checkbox"]').all()
        print(f"  Found {len(checkboxes)} checkboxes")
        for i, cb in enumerate(checkboxes):
            checked = await cb.is_checked()
            print(f"    cb[{i}] checked={checked}")

        # cb[0]: Show points scored in previous 2 races → must be ON
        if len(checkboxes) > 0:
            if not await checkboxes[0].is_checked():
                await checkboxes[0].click()
                await page.wait_for_timeout(300)

        # cb[1]: Show expected points for analyst sims → must be OFF
        if len(checkboxes) > 1:
            if await checkboxes[1].is_checked():
                await checkboxes[1].click()
                await page.wait_for_timeout(300)

        # cb[2]: Show required points next to simulation odds → must be ON
        if len(checkboxes) > 2:
            if not await checkboxes[2].is_checked():
                await checkboxes[2].click()
                await page.wait_for_timeout(300)

    except Exception as e:
        print(f"  ⚠️  Checkbox setup: {e}")

    # Select "Required Points" from the mode dropdown
    try:
        sel = page.locator('select, [role="combobox"]').first
        await sel.select_option(label="Required Points")
        await page.wait_for_timeout(500)
        print("  ✅  Set mode to 'Required Points'")
    except Exception as e:
        print(f"  ⚠️  Dropdown: {e}")

    await page.wait_for_timeout(800)


async def scrape_table(table, label: str) -> list[dict]:
    """
    Scrape one <table> (drivers or constructors).
    Returns list of dicts. Iterates ALL rows (thead + tbody).
    """
    entries            = []
    current_tier       = None
    current_tier_label = None
    col_pos            = None

    all_rows = await table.locator("tr").all()
    print(f"  [{label}] {len(all_rows)} rows total")

    for row in all_rows:
        cells = await row.locator("td, th").all()
        texts = [(await c.inner_text()).strip() for c in cells]
        if not texts:
            continue

        # ── Tier header (single spanning cell) ──────────────────
        if len(texts) == 1:
            m = re.search(r"Tier\s+([AB])", texts[0], re.IGNORECASE)
            if m:
                current_tier       = m.group(1).upper()
                current_tier_label = texts[0].strip()
                print(f"  [{label}] Tier: {current_tier_label}")
            continue

        # ── Column label row ─────────────────────────────────────
        if texts[0] in ("DR", "CR") or (len(texts) > 1 and texts[1] == "$"):
            col_pos = {}
            for i, t in enumerate(texts):
                tl = t.lower()
                if t in ("DR", "CR"):                       col_pos["name"]      = i
                elif t == "$":                               col_pos["price"]     = i
                elif tl in ("pts", "r0") and "name" in col_pos and "price" in col_pos:
                    col_pos.setdefault("pts_r0", i)
                elif "pts" in tl and "name" in col_pos and "price" in col_pos:
                    if "pts_r0" not in col_pos:              col_pos["pts_r0"]    = i
                    elif "pts_r1" not in col_pos:            col_pos["pts_r1"]    = i
                    elif "pts_m03" not in col_pos:           col_pos["pts_m03"]   = i
                    elif "pts_m01" not in col_pos:           col_pos["pts_m01"]   = i
                    elif "pts_p01" not in col_pos:           col_pos["pts_p01"]   = i
                    elif "pts_p03" not in col_pos:           col_pos["pts_p03"]   = i
            print(f"  [{label}] col_pos: {col_pos}")
            continue

        # Skip rows with fewer than 4 cells
        if len(texts) < 4:
            continue

        # ── Data row ─────────────────────────────────────────────
        def get(key, fallback_idx, default=""):
            if col_pos and key in col_pos:
                i = col_pos[key]
                return texts[i] if i < len(texts) else default
            return texts[fallback_idx] if fallback_idx < len(texts) else default

        tag = get("name", 0)
        if not tag or tag in SKIP_TAGS:
            continue

        entries.append({
            "name":       tag,
            "tier":       current_tier,
            "tier_label": current_tier_label,
            "price":      clean_price(get("price",   1)),
            "pts_r0":     to_int_or_str(get("pts_r0",  2)),   # R0 season total
            "pts_r1":     to_int_or_str(get("pts_r1",  3)),   # R1 last race
            "pts_m03":    to_int_or_str(get("pts_m03", 4)),   # required for -0.3
            "pts_m01":    to_int_or_str(get("pts_m01", 5)),   # required for -0.1
            "pts_p01":    to_int_or_str(get("pts_p01", 6)),   # required for +0.1
            "pts_p03":    to_int_or_str(get("pts_p03", 7)),   # required for +0.3
        })

    print(f"  [{label}] scraped {len(entries)} entries")
    return entries


async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()

        data_output = {
            "last_updated":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_url":    "https://f1fantasytools.com/budget-builder",
            "view":          "required_points",
            "drivers":       [],
            "constructors":  [],
        }

        try:
            print("Loading Budget Builder …")
            await page.goto(
                "https://f1fantasytools.com/budget-builder",
                wait_until="networkidle",
                timeout=60_000,
            )
            await page.wait_for_selector("table", timeout=30_000)
            print("  Page loaded ✅")

            # Enable correct display options
            await enable_display_options(page)

            # Wait for table to re-render
            await page.wait_for_selector("table", timeout=15_000)
            await page.wait_for_timeout(1000)

            tables = await page.locator("table").all()
            print(f"  Found {len(tables)} table(s)")

            if len(tables) < 2:
                print("  ⚠️  Dumping body text for diagnosis:")
                print((await page.inner_text("body"))[:3000])
                raise RuntimeError(f"Expected ≥2 tables, found {len(tables)}")

            # Dump first few raw rows for each table to confirm structure
            for ti in range(min(2, len(tables))):
                label = "Drivers" if ti == 0 else "Constructors"
                print(f"\n  === Raw rows preview: {label} ===")
                rows = await tables[ti].locator("tr").all()
                for i, row in enumerate(rows[:6]):
                    cells = await row.locator("td, th").all()
                    txts  = [(await c.inner_text()).strip() for c in cells]
                    print(f"    row {i}: {txts}")

            data_output["drivers"]      = await scrape_table(tables[0], "Drivers")
            data_output["constructors"] = await scrape_table(tables[1], "Constructors")

            print(f"\n  ✅  Drivers: {len(data_output['drivers'])} rows")
            print(f"  ✅  Constructors: {len(data_output['constructors'])} rows")

        except Exception as e:
            print(f"Scraper error: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()

        with open("f1_budget_data.json", "w", encoding="utf-8") as f:
            json.dump(data_output, f, indent=4, ensure_ascii=False)
        print("\n✅  f1_budget_data.json written.")


if __name__ == "__main__":
    asyncio.run(run_scraper())
