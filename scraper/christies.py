"""
Christie's sold-lot scraper — individual lot pages + next_lot_url chain.

Each lot page embeds window.chrComponents.lotHeader_* with structured JSON:
  estimate_low/high, price_realised, lot_assets (image URLs + dimensions),
  title_primary_txt (artist), title_secondary_txt (artwork title),
  next_lot_url / previous_lot_url for in-sale navigation.

The page accordion section contains: artist, title, medium, dimensions in plain text.

Strategy:
  1. Discover art Day Sales via the Christie's auction-results calendar API
     (api/discoverywebsite/auctioncalendar/auctionresults), filtering by name.
  2. Resolve the first lot ID for each sale from its landing page.
  3. Navigate forward through the sale using next_lot_url.
  4. Stop when next_lot_url leads outside the current sale number.
  5. Skip non-art lots (wine/jewelry/watches) via blocklist.
"""

import argparse
import asyncio
import json
import re
from datetime import date, timedelta

import httpx
from tqdm import tqdm

from scraper.art_db import connect, lot_exists, upsert_lot

AUCTION_HOUSE = "Christie's"
BASE_URL      = "https://www.christies.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

_CALENDAR_API       = f"{BASE_URL}/api/discoverywebsite/auctioncalendar/auctionresults"
_CALENDAR_COMPONENT = "e7d92272-7bcc-4dba-ae5b-28e4f3729ae8"

# Sale names that match our target departments
_TARGET_SALE_RE = re.compile(
    r"(post.war and contemporary art day sale"
    r"|impressionist and modern art day (sale|and works on paper sale))",
    re.IGNORECASE,
)

# Fallback hardcoded starts used when discovery fails
_FALLBACK_STARTS: list[tuple[str, int, str]] = [
    ("22044", 6425000, "Post-War & Contemporary Art Day Sale, NY 2023"),
    ("22658", 6470000, "Impressionist & Modern Art Day Sale, London 2024"),
    ("23740", 6549978, "Post-War & Contemporary Art Day Sale, NY 2025"),
    ("23486", 6559641, "Post-War & Contemporary Art Day Sale, NY 2025"),
    ("23488", 6560017, "Impressionist & Modern Art Day Sale, NY 2025"),
    ("24183", 6574487, "Impressionist & Modern Art Day Sale, London 2025"),
    ("24182", 6575080, "Post-War & Contemporary Art Day Sale, London 2025"),
]

# Titles containing these words are NOT art — skip them
_NON_ART_BLOCKLIST = re.compile(
    r"\b(château|bordeaux|burgundy|champagne|whisky|whiskey|diamond|bracelet|necklace|"
    r"earring|brooch|pendant|ring|rolex|patek|audemars|vacheron|watch|clock|"
    r"decanter|bottle|magnum|wine|beer|cognac|port|brandy|vintage \d{4})\b",
    re.IGNORECASE,
)

_ARTIST_YEAR_RE = re.compile(r"\s*\([\d\–\-–]+\)\s*$")
_CURRENCY_MAP   = {"USD": "USD", "GBP": "GBP", "EUR": "EUR", "HKD": "HKD", "CHF": "CHF"}
_YEAR_RE        = re.compile(r"\b(1[3-9]\d{2}|20[0-2]\d)\b")

_FX = {"USD": 1.0, "GBP": 1.27, "EUR": 1.09, "HKD": 0.128, "CHF": 1.13}


def _to_usd(amount: float, currency: str) -> float:
    return round(amount * _FX.get(currency, 1.0))


def _currency_from_txt(txt: str) -> str:
    """Extract currency code from a formatted price string like 'USD 400,000'."""
    for code in _CURRENCY_MAP:
        if txt.startswith(code):
            return code
    return "USD"


def _medium_category(medium: str | None) -> str:
    if not medium:
        return "other"
    m = medium.lower()
    # Sculpture keywords checked first — welded/cast/bronze override "ink on paper" etc.
    for keyword in ("bronze", "marble", "ceramic", "terracotta", "plaster",
                    "welded", "cast", "steel", "metal", "wire", "mobile",
                    "aluminum", "aluminium", "glass", "wood carving"):
        if keyword in m:
            return "sculpture"
    for keyword in ("photograph", "gelatin", "chromogenic", "c-print", "daguerreotype"):
        if keyword in m:
            return "photography"
    for keyword in ("etching", "lithograph", "screenprint", "woodcut",
                    "engraving", "aquatint", "mezzotint", "linocut"):
        if keyword in m:
            return "print"
    for keyword in ("gouache", "watercolor", "watercolour", "pastel",
                    "charcoal", "pencil", "crayon", "chalk", "graphite"):
        if keyword in m:
            return "works on paper"
    for keyword in ("oil", "acrylic", "tempera", "fresco", "distemper", "canvas", "linen", "panel"):
        if keyword in m:
            return "painting"
    return "other"


async def _first_lot_from_landing(client: httpx.AsyncClient, landing_url: str) -> int | None:
    """Fetch a sale landing page and return the lowest embedded lot ID."""
    try:
        r = await client.get(landing_url, timeout=20)
        ids = re.findall(r"/en/lot/lot-(\d+)", r.text)
        return min(int(i) for i in ids) if ids else None
    except Exception:
        return None


async def discover_day_sales(
    client: httpx.AsyncClient,
    lookback_months: int = 18,
) -> list[tuple[str, int, str]]:
    """Query the Christie's results calendar API and return sale_starts tuples
    for all closed Post-War & Contemporary / Impressionist & Modern Day Sales
    within the last `lookback_months` months.

    Returns list of (sale_number, first_lot_id, sale_name) sorted oldest-first.
    """
    today      = date.today()
    cal_headers = {**_HEADERS, "Accept": "application/json, */*",
                   "Referer": f"{BASE_URL}/en/results"}
    found: dict[str, tuple[str, int, str]] = {}  # keyed by sale_number

    months_to_check = []
    for delta in range(lookback_months + 1):
        d = today - timedelta(days=delta * 30)
        months_to_check.append((d.year, d.month))
    # Deduplicate while preserving order
    seen: set = set()
    unique_months = []
    for ym in months_to_check:
        if ym not in seen:
            seen.add(ym)
            unique_months.append(ym)

    for year, month in unique_months:
        try:
            r = await client.get(
                _CALENDAR_API,
                params={"language": "en", "month": str(month),
                        "year": str(year), "component": _CALENDAR_COMPONENT},
                headers=cal_headers,
                timeout=15,
            )
            if r.status_code != 200:
                continue
            data = r.json()
        except Exception:
            continue

        for ev in data.get("events", []):
            title = ev.get("title_txt", "")
            if not _TARGET_SALE_RE.search(title):
                continue
            # Only closed (results available) sales
            if "CLOSED" not in ev.get("subtitle_txt", ""):
                continue

            sub = ev.get("subtitle_txt", "")
            sale_num_m = re.search(r"\b(\d{5})\b", sub)
            if not sale_num_m:
                continue
            sale_num = sale_num_m.group(1)
            if sale_num in found:
                continue

            landing = ev.get("landing_url", "")
            if not landing:
                continue

            first_lot = await _first_lot_from_landing(client, landing)
            if not first_lot:
                continue

            location = ev.get("location_txt", "")
            label    = f"{title.strip()}, {location} {year}"
            found[sale_num] = (sale_num, first_lot, label)
            tqdm.write(f"  discovered sale {sale_num}: {label} (first lot {first_lot})")
            await asyncio.sleep(0.3)

    # Return sorted by first_lot_id (chronological)
    return sorted(found.values(), key=lambda t: t[1])


def _extract_navigation(body: str) -> tuple[str | None, str | None]:
    """Always extract (next_url, sale_number) from a lot page, even for skipped lots."""
    next_url = None
    sale_num = None

    m = re.search(r"chrComponents\.lotHeader_\w+\s*=\s*(\{.*?\})\s*;", body, re.DOTALL)
    if m:
        try:
            header = json.loads(m.group(1))
            lots = header.get("data", {}).get("lots", [])
            if lots:
                next_url = lots[0].get("next_lot_url")
        except json.JSONDecodeError:
            pass

    sale_m = re.search(r"AnalyticsDataLayer\.sale\s*=\s*(\{[^;]+\})", body)
    if sale_m:
        try:
            sale_num = json.loads(sale_m.group(1)).get("number")
        except json.JSONDecodeError:
            pass

    return next_url, sale_num


def _parse_lot_page(body: str, lot_id: str) -> dict | None:
    """Parse a Christie's lot page HTML. Returns None if not a valid art lot."""

    # ── 1. lotHeader JSON ───────────────────────────────────────────────────
    m = re.search(r"chrComponents\.lotHeader_\w+\s*=\s*(\{.*?\})\s*;", body, re.DOTALL)
    if not m:
        return None
    try:
        header = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

    lots = header.get("data", {}).get("lots", [])
    if not lots:
        return None
    lot = lots[0]

    title_artist = lot.get("title_primary_txt", "").strip()
    title_work   = lot.get("title_secondary_txt", "").strip()

    # Non-art blocklist check
    if _NON_ART_BLOCKLIST.search(title_artist) or _NON_ART_BLOCKLIST.search(title_work):
        return None

    # ── 2. Sale metadata ────────────────────────────────────────────────────
    sale_m = re.search(r"AnalyticsDataLayer\.sale\s*=\s*(\{[^;]+\})", body)
    sale   = json.loads(sale_m.group(1)) if sale_m else {}

    # ── 3. Accordion: medium + dimensions ──────────────────────────────────
    # Accordion order: [artist, title, (optional inscription/signature), medium, dimensions, ...]
    accordion_m = re.search(
        r"class=[\"']chr-lot-section__accordion--text[\"'][^>]*>(.*?)</div>",
        body, re.DOTALL | re.IGNORECASE,
    )
    medium       = None
    dimensions   = None
    year_created = None
    _DIM_RE  = re.compile(r"\d[\d\s/½¼¾×xX.]+(?:cm|in\.?|inches?)", re.IGNORECASE)
    _MED_KEYWORDS = re.compile(
        r"\b(oil|acrylic|watercolor|watercolour|gouache|tempera|pastel|charcoal|"
        r"pencil|crayon|ink|bronze|marble|ceramic|terracotta|plaster|etching|"
        r"lithograph|screenprint|woodcut|engraving|photograph|gelatin|chromogenic|"
        r"silkscreen|canvas|paper|board|panel|linen|steel|metal|wire|wood|aluminum|"
        r"glass|mobile|welded|cast|painted)\b",
        re.IGNORECASE,
    )
    _SIG_RE  = re.compile(r"^(signed|inscribed|incised|stamped|dated|numbered|titled)", re.IGNORECASE)

    if accordion_m:
        lines = [
            re.sub(r"<[^>]+>", "", l).strip()
            for l in accordion_m.group(1).split("\n")
            if re.sub(r"<[^>]+>", "", l).strip()
        ]
        # Skip lines 0 (artist) and 1 (title), scan rest for medium / dimensions
        for line in lines[2:8]:
            if not dimensions and _DIM_RE.search(line) and len(line) < 120:
                dimensions = line
            elif not medium and _MED_KEYWORDS.search(line) and not _SIG_RE.match(line):
                medium = line
            if not year_created:
                y = _YEAR_RE.search(line)
                if y:
                    year_created = y.group(1)

    # ── 4. Sale name ────────────────────────────────────────────────────────
    sale_name_m = re.search(
        r"class=[\"'][^\"']*medium[^\"']*[\"'][^>]*>\s*([^<]{8,80})\s*<",
        body, re.IGNORECASE,
    )
    sale_name = (
        re.sub(r"<[^>]+>", "", sale_name_m.group(1)).strip()
        if sale_name_m else None
    )

    # ── 5. Provenance ───────────────────────────────────────────────────────
    prov_m = re.search(
        r"class=[\"'][^\"']*description[^\"']*[\"'][^>]*>(.*?)</div>",
        body, re.DOTALL | re.IGNORECASE,
    )
    provenance = (
        re.sub(r"<[^>]+>", "", prov_m.group(1)).strip()[:400]
        if prov_m else None
    )

    # ── 6. Prices + currency ────────────────────────────────────────────────
    estimate_txt = lot.get("estimate_txt", "")
    currency     = _currency_from_txt(estimate_txt)
    est_low      = lot.get("estimate_low")
    est_high     = lot.get("estimate_high")
    hammer       = lot.get("price_realised")

    # ── 7. Images ───────────────────────────────────────────────────────────
    images = [
        a["image_url"] for a in lot.get("lot_assets", [])
        if a.get("image_url")
    ]

    # ── 8. Clean artist name ────────────────────────────────────────────────
    artist = _ARTIST_YEAR_RE.sub("", title_artist).strip() or None

    # ── 9. Sale date (best effort from HTML) ────────────────────────────────
    date_m = re.search(r'"sale_date"\s*:\s*"(\d{4}-\d{2}-\d{2})', body)
    sale_date = date_m.group(1) if date_m else None

    return {
        "id":              lot_id,
        "auction_house":   AUCTION_HOUSE,
        "artist":          artist,
        "title":           title_work or title_artist,
        "medium":          medium,
        "medium_category": _medium_category(medium),
        "dimensions":      dimensions,
        "year_created":    year_created,
        "lot_number":      lot.get("lot_id_txt", ""),
        "sale_name":       sale_name,
        "sale_date":       sale_date,
        "estimate_low":    float(est_low) if est_low else None,
        "estimate_high":   float(est_high) if est_high else None,
        "hammer_price":    float(hammer) if hammer else None,
        "currency":        currency,
        "hammer_usd":      _to_usd(float(hammer), currency) if hammer else None,
        "provenance":      provenance,
        "description":     f"{title_artist} — {title_work}" if title_work else title_artist,
        "image_urls":      images,
        "source_url":      lot.get("url") or f"{BASE_URL}/en/lot/lot-{lot_id}",
    }


async def _fetch_lot(
    client: httpx.AsyncClient, url: str
) -> tuple[dict | None, str | None, str | None]:
    """Fetch a lot page and return (parsed_lot_or_None, next_url, sale_number).

    next_url and sale_number are always extracted so navigation can continue
    even when the lot itself is skipped (non-art, parse fail, etc.).
    """
    lot_id = url.rstrip("/").rsplit("-", 1)[-1]
    try:
        r = await client.get(url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        tqdm.write(f"  fetch error {url}: {e}")
        return None, None, None

    # Always extract navigation before deciding to skip
    next_url, sale_num = _extract_navigation(r.text)

    lot = _parse_lot_page(r.text, lot_id)
    if lot:
        lot.pop("_next_url", None)
        lot.pop("_sale_number", None)

    return lot, next_url, sale_num


async def _scrape_sale(
    client: httpx.AsyncClient,
    conn,
    start_url: str,
    expected_sale: str,
    max_lots: int,
    pbar,
    saved_ref: list[int],
) -> str | None:
    """Chain through a sale via next_lot_url. Returns the last next_url seen."""
    url = start_url
    consecutive_skips = 0

    while url and saved_ref[0] < max_lots:
        lot_id = url.rstrip("/").rsplit("-", 1)[-1]

        lot, next_url, sale_num = await _fetch_lot(client, url)

        # Stop if we've crossed into a different sale
        if sale_num and expected_sale and sale_num != expected_sale:
            tqdm.write(f"  Sale changed: {expected_sale} → {sale_num}. Stopping.")
            return None

        # Already in DB — advance URL but count toward consecutive-existing limit
        if lot_exists(conn, lot_id, AUCTION_HOUSE):
            consecutive_skips += 1
            if consecutive_skips > 30:
                tqdm.write("  30 consecutive existing lots — sale likely fully scraped")
                return None
        elif lot:
            upsert_lot(conn, lot)
            saved_ref[0] += 1
            pbar.update(1)
            artist = lot.get("artist") or "Unknown"
            title  = (lot.get("title") or "")[:40]
            price  = (
                f"${lot['hammer_usd']:,.0f}" if lot.get("hammer_usd") else
                (f"{lot['hammer_price']:,.0f}" if lot.get("hammer_price") else "—")
            )
            tqdm.write(f"  saved: {artist} — {title} ({price})")
            consecutive_skips = 0
        else:
            consecutive_skips += 1
            tqdm.write(f"  skipped: lot {lot_id}")

        url = next_url  # always advance, even on existing/skipped lots
        await asyncio.sleep(0.5)

    return None


async def scrape(
    max_lots: int = 300,
    sale_starts: list[tuple] | None = None,
    lookback_months: int = 18,
) -> None:
    conn      = connect()
    saved_ref = [0]

    async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
        if sale_starts is None:
            tqdm.write("Discovering art Day Sales from christies.com/en/results ...")
            sale_starts = await discover_day_sales(client, lookback_months)
            if not sale_starts:
                tqdm.write("Discovery returned no sales — falling back to hardcoded list")
                sale_starts = _FALLBACK_STARTS

        with tqdm(total=max_lots, desc="Lots") as pbar:
            for sale_number, first_lot_id, sale_hint in sale_starts:
                if saved_ref[0] >= max_lots:
                    break

                tqdm.write(f"\nScraping sale {sale_number}: {sale_hint}")
                start_url = f"{BASE_URL}/en/lot/lot-{first_lot_id}"
                await _scrape_sale(
                    client, conn, start_url, sale_number,
                    max_lots, pbar, saved_ref,
                )

    conn.close()
    print(f"\nDone — {saved_ref[0]} Christie's art lots saved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape sold art lots from Christie's")
    parser.add_argument("--max-lots", type=int, default=50)
    parser.add_argument("--lookback-months", type=int, default=18,
                        help="How many months back to search for sales (default: 18)")
    args = parser.parse_args()
    asyncio.run(scrape(max_lots=args.max_lots, lookback_months=args.lookback_months))
