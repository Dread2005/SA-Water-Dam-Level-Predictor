"""
src/scrapers/dws_scraper.py

Scrapes weekly dam storage data from the DWS WRMS report page.
The page is JS-rendered: it uses an ASP.NET dropdown to filter by province,
so we drive it with Playwright instead of requests.

Usage:
    python -m src.scrapers.dws_scraper               # scrape all provinces
    python -m src.scrapers.dws_scraper --province "Western Cape"

Setup (once):
    pip install playwright
    playwright install chromium
"""

import argparse
import asyncio
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from playwright.async_api import async_playwright, Page, TimeoutError as PWTimeout

# Allow running as `python -m src.scrapers.dws_scraper` from repo root
sys.path.insert(0, str(Path(__file__).parents[2]))
from config import DAM_LEVELS_DIR, DWS_BASE_URL, DWS_PROVINCES, LOGS_DIR

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOGS_DIR / "dws_scraper.log"),
    ],
)
log = logging.getLogger("dws_scraper")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _clean_pct(raw: str) -> float | None:
    """'  81.2 %  '  →  81.2.  Returns None if unparseable."""
    cleaned = re.sub(r"[^\d.]", "", raw)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _clean_volume(raw: str) -> float | None:
    """'1 234.5'  →  1234.5  (millions m³).  Returns None if unparseable."""
    cleaned = raw.replace("\xa0", "").replace(" ", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


# ── Core scrape logic ──────────────────────────────────────────────────────────

async def _select_province(page: Page, province_value: str) -> None:
    """
    Select a province in the DWS dropdown and wait for the table to reload.
    The dropdown id may change — inspect the live page if this breaks.
    """
    # NOTE: Inspect the page with DevTools to confirm the selector.
    #       Common patterns on DWS: 'select[name*="Province"]' or '#ctl00_...'
    dropdown_selector = "select[id*='Province'], select[name*='Province']"
    await page.wait_for_selector(dropdown_selector, timeout=15_000)
    await page.select_option(dropdown_selector, value=province_value)

    # Wait for the table to re-render after the AJAX call
    await page.wait_for_load_state("networkidle", timeout=20_000)


async def _extract_table(page: Page, province_name: str) -> list[dict]:
    """
    Parse the dam-level HTML table currently rendered on the page.
    Returns a list of row dicts.

    Column names are normalised here; adjust if the live table headers differ.
    """
    # Grab all <table> elements and find the one with dam data
    tables = await page.query_selector_all("table")

    for table in tables:
        html = await table.inner_html()
        # Quick heuristic: the dam table contains "%" in its cells
        if "%" not in html:
            continue

        try:
            # pandas can parse the HTML string directly
            dfs = pd.read_html(f"<table>{html}</table>")
            if not dfs:
                continue
            df = dfs[0]
        except Exception:
            continue

        # Normalise column names — DWS table headers can be multi-line
        df.columns = [str(c).strip().replace("\n", " ") for c in df.columns]

        # Drop fully-empty rows (totals/spacers)
        df = df.dropna(how="all")

        # --- Map to a stable schema ---
        # Adjust these mappings after inspecting actual column headers.
        col_map = _infer_column_map(df.columns.tolist())
        if col_map is None:
            continue  # not the dam data table

        rows = []
        scrape_date = datetime.today().strftime("%Y-%m-%d")

        for _, row in df.iterrows():
            dam_name = str(row.get(col_map["name"], "")).strip()
            if not dam_name or dam_name.lower() in ("nan", "total", ""):
                continue

            rows.append({
                "scrape_date":    scrape_date,
                "province":       province_name,
                "dam_name":       dam_name,
                "river":          str(row.get(col_map.get("river", ""), "")).strip(),
                "capacity_mm3":   _clean_volume(str(row.get(col_map.get("capacity", ""), ""))),
                "current_mm3":    _clean_volume(str(row.get(col_map.get("current", ""), ""))),
                "storage_pct":    _clean_pct(str(row.get(col_map.get("storage_pct", ""), ""))),
                "last_year_pct":  _clean_pct(str(row.get(col_map.get("last_year", ""), ""))),
            })

        if rows:
            log.info("  ✓ %d dams found for %s", len(rows), province_name)
            return rows

    log.warning("  ✗ No parseable dam table found for %s — inspect selectors", province_name)
    return []


def _infer_column_map(columns: list[str]) -> dict | None:
    """
    Heuristically maps raw column names to our stable schema keys.
    Returns None if this doesn't look like the dam data table.

    IMPORTANT: Run the scraper once in debug mode and print `df.columns`
    to verify these patterns match the live page.
    """
    col_lower = [c.lower() for c in columns]

    def find(patterns: list[str]) -> str | None:
        for pat in patterns:
            for i, c in enumerate(col_lower):
                if pat in c:
                    return columns[i]
        return None

    name_col = find(["dam name", "dam", "reservoir", "name"])
    pct_col  = find(["% full", "storage %", "% capacity", "percent"])

    # If we can't identify the dam name or storage %, skip this table
    if not name_col or not pct_col:
        return None

    return {
        "name":        name_col,
        "river":       find(["river", "watercourse"]) or "",
        "capacity":    find(["capacity", "full supply"]) or "",
        "current":     find(["current", "volume", "storage (m"]) or "",
        "storage_pct": pct_col,
        "last_year":   find(["last year", "previous year", "py %"]) or "",
    }


# ── Main scrape orchestration ──────────────────────────────────────────────────

async def scrape_provinces(provinces: dict[str, str]) -> pd.DataFrame:
    """Scrape one or more provinces and return a combined DataFrame."""
    all_rows: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        log.info("Navigating to DWS WRMS: %s", DWS_BASE_URL)
        await page.goto(DWS_BASE_URL, wait_until="networkidle", timeout=30_000)

        for name, value in provinces.items():
            log.info("Scraping province: %s (value=%s)", name, value)
            try:
                await _select_province(page, value)
                rows = await _extract_table(page, name)
                all_rows.extend(rows)
            except PWTimeout:
                log.error("  Timeout on %s — skipping", name)
            except Exception as exc:
                log.exception("  Unexpected error on %s: %s", name, exc)

        await browser.close()

    if not all_rows:
        log.warning("No data scraped — returning empty DataFrame")
        return pd.DataFrame()

    return pd.DataFrame(all_rows)


def save(df: pd.DataFrame) -> Path:
    """Append today's scrape to the master parquet file (date-partitioned)."""
    if df.empty:
        log.warning("Nothing to save.")
        return Path()

    date_str = datetime.today().strftime("%Y%m%d")
    out_path = DAM_LEVELS_DIR / f"dws_dam_levels_{date_str}.csv"
    df.to_csv(out_path, index=False)
    log.info("Saved %d rows → %s", len(df), out_path)

    # Also maintain a single master file for easy loading
    master = DAM_LEVELS_DIR / "dam_levels_master.parquet"
    if master.exists():
        existing = pd.read_parquet(master)
        # Avoid duplicating today's scrape if run twice
        combined = pd.concat([existing, df]).drop_duplicates(
            subset=["scrape_date", "province", "dam_name"]
        )
    else:
        combined = df

    combined.to_parquet(master, index=False)
    log.info("Master parquet updated: %d total rows", len(combined))
    return out_path


# ── CLI entry point ────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape DWS weekly dam storage levels")
    p.add_argument(
        "--province",
        default=None,
        help="Single province name (must match config.DWS_PROVINCES). "
             "Omit to scrape all provinces.",
    )
    p.add_argument(
        "--debug",
        action="store_true",
        help="Print raw column headers to help calibrate _infer_column_map.",
    )
    return p.parse_args()


async def main() -> None:
    args = parse_args()

    if args.province:
        if args.province not in DWS_PROVINCES:
            log.error(
                "Unknown province '%s'. Valid options: %s",
                args.province,
                list(DWS_PROVINCES),
            )
            sys.exit(1)
        target = {args.province: DWS_PROVINCES[args.province]}
    else:
        target = DWS_PROVINCES

    df = await scrape_provinces(target)

    if args.debug and not df.empty:
        print("\n=== DEBUG: First 5 rows ===")
        print(df.head().to_string())
        print("\nDtypes:", df.dtypes.to_dict())

    save(df)


if __name__ == "__main__":
    asyncio.run(main())
