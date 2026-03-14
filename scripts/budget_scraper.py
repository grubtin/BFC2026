import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright

# ─────────────────────────────────────────────────────────────────
# f1fantasytools.com/budget-builder table structure:
#
# Each table (Drivers / Constructors) has:
#   <thead>
#     row 0: group headers
#     row 1: col headers  (DR/CR | $ | Pts | Pts | xPts | Odds(pts)×4 | xΔ$)
#   <tbody>
#     Tier A header row   (single <td colspan=N>  "Tier A (>=18.5M)")
#     data rows           (10 cells each)
#     Tier B header row   (single <td colspan=N>  "Tier B (<18.5M)")
#     data rows           (10 cells each)
#
# Data row columns (0-indexed):
#   0  Tag      e.g. "RUS"
#   1  Price    e.g. "27.7"
#   2  R0 Pts   season total  (may be "-")
#   3  R1 Pts   last race     (may be "-")
#   4  R2 xPts  expected      e.g. "43.3"
#   5  -0.3     e.g. "10% (≤-6)"
#   6  -0.1     e.g. "1% (-5)"
#   7  +0.1     e.g. "2% (11)"
#   8  +0.3     e.g. "87% (28)"
#   9  xΔ$      e.g. "+0.23"
# ─────────────────────────────────────────────────────────────────

SKIP_TAGS = {"-", "DR", "CR", "Pts", "xPts", "$", "R0", "R1", "R2",
             "Odds (pts)", "Odds(pts)", "xΔ$", ""}


def parse_pct(raw: str) -> int | None:
    """Extract leading integer % from '87% (≤28)' → 87"""
    if not raw:
        return None
    m = re.match(r"(\d+)%", raw.strip())
    return int(m.group(1)) if m else None


def clean_price(raw: str) -> str:
    return raw.replace("$", "").strip()


async def scrape_table(table) -> list[dict]:
    """
    Scrape one <table> and return list of driver/constructor dicts.
    Iterates ALL rows (thead + tbody) so nothing is missed.
    """
    entries            = []
    current_tier       = None
    current_tier_label = None
    col_pos            = None   # field -> column index, detected from sub-header row

    all_rows = await table.locator("tr").all()

    for row in all_rows:
        cells = await row.locator("td, th").all()
        texts = [(await c.inner_text()).strip() for c in cells]
        if not texts:
            continue

        # ── Tier header row (single spanning cell) ──────────────
        if len(texts) == 1:
            m = re.search(r"Tier\s+([AB])", texts[0], re.IGNORECASE)
            if m:
                current_tier       = m.group(1).upper()
                current_tier_label = texts[0].strip()
            continue

        # ── Column label row: detect col positions ───────────────
        if texts[0] in ("DR", "CR") or (len(texts) > 1 and texts[1] == "$"):
            col_pos = {}
            for i, t in enumerate(texts):
                tl = t.lower()
                if t in ("DR", "CR"):                      col_pos["name"]      = i
                elif t == "$":                              col_pos["price"]     = i
                elif tl in ("pts", "r0"):                  col_pos.setdefault("pts", i)
                elif "r1" in tl and "pts" in tl:           col_pos["pts_r1"]    = i
                elif "xpts" in tl or tl == "r2 xpts":      col_pos["xpts"]      = i
                elif "-0.3" in t or "−0.3" in t:           col_pos["odds_m03"]  = i
                elif "-0.1" in t or "−0.1" in t:           col_pos["odds_m01"]  = i
                elif "+0.1" in t:                           col_pos["odds_p01"]  = i
                elif "+0.3" in t:                           col_pos["odds_p03"]  = i
                elif "xδ" in tl or "xΔ" in t or tl == "r2": col_pos["r2_change"] = i
            print(f"    col_pos: {col_pos}")
            continue

        # ── Skip rows with fewer than 6 cells ───────────────────
        if len(texts) < 6:
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

        odds_m03 = get("odds_m03", 5)
        odds_m01 = get("odds_m01", 6)
        odds_p01 = get("odds_p01", 7)
        odds_p03 = get("odds_p03", 8)

        entries.append({
            "name":         tag,
            "tier":         current_tier,
            "tier_label":   current_tier_label,
            "price":        clean_price(get("price",     1)),
            "pts":          get("pts",       2),
            "pts_r1":       get("pts_r1",    3),
            "xpts":         get("xpts",      4),
            "odds_m03":     odds_m03,
            "odds_m01":     odds_m01,
            "odds_p01":     odds_p01,
            "odds_p03":     odds_p03,
            "odds_m03_pct": parse_pct(odds_m03),
            "odds_m01_pct": parse_pct(odds_m01),
            "odds_p01_pct": parse_pct(odds_p01),
            "odds_p03_pct": parse_pct(odds_p03),
            "r2_change":    get("r2_change", 9),
        })

    return entries


async def run_scraper():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()

        data_output = {
            "last_updated":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_url":       "https://f1fantasytools.com/budget-builder",
            "simulation_label": "",
            "drivers":          [],
            "constructors":     [],
        }

        try:
            print("Fetching Budget Builder …")
            await page.goto(
                "https://f1fantasytools.com/budget-builder",
                wait_until="networkidle",
                timeout=60_000,
            )
            await page.wait_for_selector("table", timeout=30_000)

            # Grab simulation label
            try:
                sim_label = await page.evaluate(
                    "() => { const s = document.querySelector('select'); "
                    "return s ? s.options[s.selectedIndex].text.trim() : ''; }"
                )
                data_output["simulation_label"] = sim_label or ""
            except Exception as e:
                print(f"  ⚠️  sim label: {e}")

            tables = await page.locator("table").all()
            print(f"  Found {len(tables)} table(s) on page")

            if len(tables) < 2:
                print("  ⚠️  Expected ≥2 tables. Dumping page text snippet:")
                txt = await page.inner_text("body")
                print(txt[:3000])
                raise RuntimeError(f"Only {len(tables)} table(s) found")

            # Drivers
            print("  Scraping drivers …")
            data_output["drivers"] = await scrape_table(tables[0])
            d_count = len(data_output["drivers"])
            print(f"  ✅  Drivers: {d_count} rows")

            if d_count == 0:
                print("  ⚠️  No drivers found — raw rows dump:")
                for i, row in enumerate((await tables[0].locator("tr").all())[:10]):
                    cells = await row.locator("td, th").all()
                    txts  = [(await c.inner_text()).strip() for c in cells]
                    print(f"     row {i} ({len(txts)} cells): {txts}")

            # Constructors
            print("  Scraping constructors …")
            data_output["constructors"] = await scrape_table(tables[1])
            c_count = len(data_output["constructors"])
            print(f"  ✅  Constructors: {c_count} rows")

        except Exception as e:
            print(f"Scraper error: {e}")
            import traceback; traceback.print_exc()
        finally:
            await browser.close()

        with open("f1_budget_data.json", "w", encoding="utf-8") as f:
            json.dump(data_output, f, indent=4, ensure_ascii=False)
        print("✅  f1_budget_data.json written.")


if __name__ == "__main__":
    asyncio.run(run_scraper())