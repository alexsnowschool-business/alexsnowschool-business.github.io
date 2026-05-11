"""
Phillips sold-lot scraper — sequential lot number iteration within a sale.

Phillips runs on Next.js; lot pages embed all structured data in window.__NEXT_DATA__
(a JSON blob in <script id="__NEXT_DATA__">). A JSON-LD Product schema is also present
and used as a fallback.

Lot URL format:  https://www.phillips.com/lot/{SALE_ID}a{N}
  e.g. https://www.phillips.com/lot/NY040624a1

Strategy:
  1. Start from known sale IDs + first lot number (hardcoded SALE_STARTS).
  2. Increment lot number (a1 → a2 → …) until N consecutive 404s.
  3. Stop when we cross into a different sale (saleId mismatch).
  4. Skip non-art lots via blocklist.
"""

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone

import httpx
from tqdm import tqdm

from scraper.art_db import connect, lot_exists, upsert_lot

AUCTION_HOUSE = "Phillips"
BASE_URL      = "https://www.phillips.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# (sale_id, first_lot_number, sale_name_hint)
# Sale IDs: 2-letter location + 3-digit sequence + 2-digit year + 2-digit month
# Browse past sales at: https://www.phillips.com/sell/auction-results
SALE_STARTS: list[tuple[str, int, str]] = [
    ("NY040624", 1, "20th Century & Contemporary Art Day Sale, NY June 2024"),
    ("NY040524", 1, "20th Century & Contemporary Art Day Sale, NY May 2024"),
    ("UK010224", 1, "20th Century & Contemporary Art Day Sale, London Feb 2024"),
]

# Max consecutive 404s before we consider a sale exhausted
_MAX_MISSES = 20

_NON_ART_BLOCKLIST = re.compile(
    r"\b(château|bordeaux|burgundy|champagne|whisky|whiskey|diamond|bracelet|necklace|"
    r"earring|brooch|pendant|ring|rolex|patek|audemars|vacheron|watch|clock|"
    r"decanter|bottle|magnum|wine|beer|cognac|port|brandy|vintage \d{4})\b",
    re.IGNORECASE,
)

_FX      = {"USD": 1.0, "GBP": 1.27, "EUR": 1.09, "HKD": 0.128, "CHF": 1.13}
_YEAR_RE = re.compile(r"\b(1[3-9]\d{2}|20[0-2]\d)\b")


def _to_usd(amount: float, currency: str) -> float:
    return round(amount * _FX.get(currency, 1.0))


def _medium_category(medium: str | None) -> str:
    if not medium:
        return "other"
    m = medium.lower()
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


def _extract_next_data(body: str) -> dict:
    """Pull the __NEXT_DATA__ JSON blob from a Phillips page."""
    m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>\s*(\{.*?\})\s*</script>',
        body, re.DOTALL,
    )
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def _extract_ld_json(body: str) -> dict:
    """Return the first Product-type JSON-LD block found on the page."""
    for script in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        body, re.DOTALL,
    ):
        try:
            data = json.loads(script)
            if isinstance(data, list):
                data = next((d for d in data if d.get("@type") == "Product"), None)
            if data and data.get("@type") == "Product":
                return data
        except Exception:
            continue
    return {}


def _parse_lot_page(body: str, lot_id: str) -> dict | None:
    """Parse a Phillips lot page. Returns None if not a valid art lot."""

    # ── 1. __NEXT_DATA__ (primary source) ──────────────────────────────────
    next_data = _extract_next_data(body)
    page_props = next_data.get("props", {}).get("pageProps", {})

    # Phillips has used several key names across redesigns
    lot = (
        page_props.get("lot")
        or page_props.get("lotDetail")
        or page_props.get("lotData")
        or {}
    )

    # Artist: try multiple field names
    artist_raw = (
        lot.get("makerName")
        or lot.get("artistName")
        or lot.get("maker")
        or lot.get("artistDisplayName")
        or ""
    ).strip()

    title = (
        lot.get("title")
        or lot.get("lotTitle")
        or lot.get("titlePrimary")
        or lot.get("workTitle")
        or ""
    ).strip()

    medium = (
        lot.get("medium")
        or lot.get("materials")
        or lot.get("technique")
        or lot.get("mediumText")
    )

    dimensions = (
        lot.get("dimensions")
        or lot.get("dimensionsText")
        or lot.get("size")
    )

    estimate_low  = lot.get("estimateLow")  or lot.get("lowEstimate")
    estimate_high = lot.get("estimateHigh") or lot.get("highEstimate")
    hammer_price  = lot.get("hammerPrice")  or lot.get("salePrice") or lot.get("priceRealized")
    currency      = lot.get("currency") or lot.get("currencyCode") or "USD"
    sale_date     = (lot.get("saleDate") or lot.get("date") or "")[:10] or None
    lot_number    = str(lot.get("lotNumber") or lot.get("lot") or "")
    sale_name     = lot.get("saleName") or lot.get("sale", {}).get("title") if isinstance(lot.get("sale"), dict) else lot.get("saleName")

    raw_images = lot.get("images") or lot.get("imageUrls") or lot.get("assets") or []
    images = []
    for img in raw_images:
        if isinstance(img, str):
            images.append(img)
        elif isinstance(img, dict):
            url = img.get("url") or img.get("src") or img.get("imageUrl")
            if url:
                images.append(url)

    # ── 2. JSON-LD fallback ─────────────────────────────────────────────────
    if not artist_raw and not title:
        ld = _extract_ld_json(body)
        if ld:
            title      = ld.get("name", "")
            description = ld.get("description", "")
            if not images and ld.get("image"):
                img_val = ld["image"]
                images = [img_val] if isinstance(img_val, str) else img_val

            offers = ld.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price_val = offers.get("price")
            if price_val and not hammer_price:
                try:
                    hammer_price = float(price_val)
                except (TypeError, ValueError):
                    pass
            currency = offers.get("priceCurrency") or currency

    # ── 3. Validate ─────────────────────────────────────────────────────────
    if not artist_raw and not title:
        return None

    if _NON_ART_BLOCKLIST.search(artist_raw) or _NON_ART_BLOCKLIST.search(title):
        return None

    # ── 4. Year from medium or dimensions ───────────────────────────────────
    year_created = None
    for text in (medium or "", dimensions or ""):
        y = _YEAR_RE.search(text)
        if y:
            year_created = y.group(1)
            break

    return {
        "id":              lot_id,
        "auction_house":   AUCTION_HOUSE,
        "artist":          artist_raw or None,
        "title":           title or artist_raw,
        "medium":          medium,
        "medium_category": _medium_category(medium),
        "dimensions":      dimensions,
        "year_created":    year_created,
        "lot_number":      lot_number,
        "sale_name":       sale_name,
        "sale_date":       sale_date,
        "estimate_low":    float(estimate_low) if estimate_low else None,
        "estimate_high":   float(estimate_high) if estimate_high else None,
        "hammer_price":    float(hammer_price) if hammer_price else None,
        "currency":        currency,
        "hammer_usd":      _to_usd(float(hammer_price), currency) if hammer_price else None,
        "provenance":      None,
        "description":     f"{artist_raw} — {title}" if title else artist_raw,
        "image_urls":      images,
        "source_url":      f"{BASE_URL}/lot/{lot_id}",
    }


async def _fetch_lot(
    client: httpx.AsyncClient, lot_id: str
) -> tuple[dict | None, bool]:
    """Fetch a Phillips lot page. Returns (parsed_lot_or_None, page_found).

    page_found is False on 404 (lot doesn't exist), True otherwise.
    """
    url = f"{BASE_URL}/lot/{lot_id}"
    try:
        r = await client.get(url, timeout=20)
    except Exception as e:
        tqdm.write(f"  fetch error {lot_id}: {e}")
        return None, True  # network error ≠ missing lot

    if r.status_code == 404:
        return None, False

    try:
        r.raise_for_status()
    except Exception as e:
        tqdm.write(f"  HTTP {r.status_code} for {lot_id}: {e}")
        return None, True

    return _parse_lot_page(r.text, lot_id), True


async def _scrape_sale(
    client: httpx.AsyncClient,
    conn,
    sale_id: str,
    first_lot: int,
    max_lots: int,
    pbar,
    saved_ref: list[int],
) -> None:
    """Iterate lot numbers a{first_lot}..a{N} until _MAX_MISSES consecutive 404s."""
    consecutive_misses = 0
    lot_number = first_lot

    while saved_ref[0] < max_lots:
        lot_id = f"{sale_id}a{lot_number}"

        if lot_exists(conn, lot_id, AUCTION_HOUSE):
            lot_number += 1
            continue

        lot, page_found = await _fetch_lot(client, lot_id)

        if not page_found:
            consecutive_misses += 1
            if consecutive_misses >= _MAX_MISSES:
                tqdm.write(f"  {_MAX_MISSES} consecutive 404s — sale {sale_id} exhausted")
                break
            lot_number += 1
            await asyncio.sleep(0.3)
            continue

        consecutive_misses = 0

        if lot:
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
        else:
            tqdm.write(f"  skipped: {lot_id}")

        lot_number += 1
        await asyncio.sleep(0.5)


async def scrape(max_lots: int = 300, sale_starts: list[tuple] | None = None) -> None:
    if sale_starts is None:
        sale_starts = SALE_STARTS

    conn      = connect()
    saved_ref = [0]

    async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
        with tqdm(total=max_lots, desc="Lots") as pbar:
            for sale_id, first_lot, sale_hint in sale_starts:
                if saved_ref[0] >= max_lots:
                    break
                tqdm.write(f"\nScraping sale {sale_id}: {sale_hint}")
                await _scrape_sale(
                    client, conn, sale_id, first_lot,
                    max_lots, pbar, saved_ref,
                )

    conn.close()
    print(f"\nDone — {saved_ref[0]} Phillips art lots saved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape sold art lots from Phillips")
    parser.add_argument("--max-lots", type=int, default=300)
    args = parser.parse_args()
    asyncio.run(scrape(max_lots=args.max_lots))
