"""
Sotheby's sold-lot scraper — GraphQL pagination + per-lot page fetch.

Sotheby's public GraphQL API (customerapi.prod.sothelabs.com/graphql) returns lots with
artist, title, estimates, and sold=True/False — but deliberately hides the hammer price
behind a ResultHidden type for completed auctions.

The hammer price IS embedded in each lot's __NEXT_DATA__ Apollo cache under
BidState.bidAsk, which is the final ask at closing (equivalent to hammer price for
closed sold lots).

Strategy:
  1. Resolve each sale slug to an auctionId via the GraphQL auctionBySlug query.
  2. Paginate through lots using auction(auctionId, take=100, skip=0/100/...).
  3. For lots where sold=True: fetch the lot's HTML page and extract bidAsk
     from the Apollo cache embedded in __NEXT_DATA__.
  4. Save completed lots to art_db.

SALE_STARTS format: (sale_slug, sale_name_hint)
  slug is the path segment after /en/buy/auction/ on sothebys.com
  e.g. "2025/contemporary-day-auction"
  Browse past sales: https://www.sothebys.com/en/series/the-new-york-sales
"""

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone

import httpx
from tqdm import tqdm

from scraper.art_db import connect, lot_exists, upsert_lot

AUCTION_HOUSE = "Sotheby's"
BASE_URL      = "https://www.sothebys.com"
GQL_URL       = "https://customerapi.prod.sothelabs.com/graphql"
PAGE_SIZE     = 100

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

_GQL_HEADERS = {**_HEADERS, "Content-Type": "application/json", "Accept": "application/json"}

# (sale_slug, sale_name_hint)
# These are PAST completed sales with sold lots confirmed.
# Browse and add more at: https://www.sothebys.com/en/series/the-new-york-sales
SALE_STARTS: list[tuple[str, str]] = [
    ("2025/contemporary-evening-auction",           "Contemporary Evening Auction, NY May 2025"),
    ("2025/contemporary-day-auction",               "Contemporary Day Auction, NY May 2025"),
    ("2025/modern-evening-auction",                 "Modern Evening Auction, NY May 2025"),
    ("2025/modern-day-auction",                     "Modern Day Auction, NY May 2025"),
    ("2024/contemporary-evening-auction",           "Contemporary Evening Auction, NY Nov 2024"),
    ("2024/contemporary-day-auction",               "Contemporary Day Auction, NY April 2024"),
    ("2024/modern-evening-auction",                 "Modern Evening Auction, NY April 2024"),
    ("2024/modern-day-auction",                     "Modern Day Auction, NY April 2024"),
    ("2024/impressionist-modern-art-day-auction",   "Impressionist & Modern Art Day, NY 2024"),
    ("2024/impressionist-modern-art-evening-sale",  "Impressionist & Modern Art Evening, NY 2024"),
    ("2023/contemporary-evening-auction",           "Contemporary Evening Auction, NY Nov 2023"),
    ("2023/contemporary-day-auction",               "Contemporary Day Auction, NY 2023"),
    ("2023/modern-evening-auction",                 "Modern Evening Auction, NY 2023"),
    ("2023/modern-day-auction",                     "Modern Day Auction, NY 2023"),
    ("2023/impressionist-modern-art-day-auction",   "Impressionist & Modern Art Day, NY 2023"),
    ("2023/impressionist-modern-art-evening-sale",  "Impressionist & Modern Art Evening, NY 2023"),
]

_NON_ART_BLOCKLIST = re.compile(
    r"\b(château|bordeaux|burgundy|champagne|whisky|whiskey|diamond|bracelet|necklace|"
    r"earring|brooch|pendant|ring|rolex|patek|audemars|vacheron|watch|clock|"
    r"decanter|bottle|magnum|wine|beer|cognac|port|brandy)\b",
    re.IGNORECASE,
)

_FX      = {"USD": 1.0, "GBP": 1.27, "EUR": 1.09, "HKD": 0.128, "CHF": 1.13}
_YEAR_RE = re.compile(r"\b(1[3-9]\d{2}|20[0-2]\d)\b")

_LOT_LIST_QUERY = """
query AuctionLots($auctionId: String!, $take: Int!, $skip: Int!) {
  auction(auctionId: $auctionId, take: $take, skip: $skip) {
    lots {
      lotId
      lotNr
      sold
      creatorsDisplayTitle
      title
      url
      estimates { low high }
    }
  }
}
"""

_AUCTION_BY_SLUG_QUERY = """
query AuctionBySlug($name: String!, $year: String!) {
  auctionBySlug(slug: { name: $name, year: $year }, take: 0) {
    auctionId
    title
  }
}
"""


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


def _infer_currency(sale_slug: str) -> str:
    slug = sale_slug.lower()
    if "london" in slug or re.search(r"\bl\d{4,}\b", slug):
        return "GBP"
    if "hong-kong" in slug or "/hk" in slug:
        return "HKD"
    if "paris" in slug:
        return "EUR"
    return "USD"


def _best_image_from_cache(cache: dict) -> str | None:
    """Extract the best image URL from the lot's Apollo cache entry."""
    lot_key = next((k for k in cache if k.startswith("LotV2:")), None)
    if not lot_key:
        return None
    lot = cache[lot_key]
    # Images are stored under a parametrised key
    for key, val in lot.items():
        if "media" in key.lower() and isinstance(val, dict):
            images = val.get("images") or []
            for img in images:
                renditions = img.get("renditions") or []
                for size in ("Large", "Medium", "ExtraLarge", "Small"):
                    for r in renditions:
                        if r.get("imageSize") == size and r.get("url"):
                            return r["url"]
    return None


def _extract_lot_data_from_cache(cache: dict) -> dict:
    """Extract hammer price and image from the Apollo cache of a lot page."""
    result = {"hammer": None, "image": None, "medium": None, "provenance": None, "year": None}

    # BidState.bidAsk = hammer price for closed sold lots
    bid_key = next((k for k in cache if k.startswith("BidState:")), None)
    if bid_key:
        bid = cache[bid_key]
        if bid.get("isClosed") and bid.get("reserveMet"):
            bid_ask = bid.get("bidAsk")
            if bid_ask:
                try:
                    result["hammer"] = float(bid_ask)
                except (TypeError, ValueError):
                    pass

    # Image from LotV2 media
    result["image"] = _best_image_from_cache(cache)

    # Medium + provenance from LotV2 description/lotConcise
    lot_key = next((k for k in cache if k.startswith("LotV2:")), None)
    if lot_key:
        lot = cache[lot_key]
        desc = lot.get("description") or ""
        lot_concise = lot.get("lotConcise") or ""
        provenance = lot.get("provenance") or ""

        # Strip HTML
        desc_text = re.sub(r"<[^>]+>", " ", desc)
        result["provenance"] = re.sub(r"<[^>]+>", " ", provenance).strip()[:400] or None

        # Extract year from description
        y = _YEAR_RE.search(desc_text)
        if y:
            result["year"] = y.group(1)

        # Use lotConcise as a clean medium+dimensions source
        if lot_concise:
            # lotConcise format: "Artist, Title, year, medium, dimensions"
            # Take the part after the title (usually 3rd+ comma)
            parts = lot_concise.split(",")
            if len(parts) >= 3:
                result["medium"] = ", ".join(p.strip() for p in parts[2:4]).strip() or None

    return result


async def _resolve_auction_id(client: httpx.AsyncClient, sale_slug: str) -> str | None:
    """Resolve a sale slug (e.g. '2025/contemporary-day-auction') to an auctionId UUID."""
    parts = sale_slug.split("/", 1)
    if len(parts) != 2:
        return None
    year, name = parts

    try:
        r = await client.post(
            GQL_URL,
            json={"query": _AUCTION_BY_SLUG_QUERY, "variables": {"name": name, "year": year}},
            headers=_GQL_HEADERS,
            timeout=15,
        )
        return r.json().get("data", {}).get("auctionBySlug", {}).get("auctionId")
    except Exception as e:
        tqdm.write(f"  auctionBySlug error for {sale_slug}: {e}")
        return None


async def _fetch_lots_page(
    client: httpx.AsyncClient, auction_id: str, skip: int
) -> list[dict]:
    try:
        r = await client.post(
            GQL_URL,
            json={"query": _LOT_LIST_QUERY, "variables": {"auctionId": auction_id, "take": PAGE_SIZE, "skip": skip}},
            headers=_GQL_HEADERS,
            timeout=20,
        )
        return r.json().get("data", {}).get("auction", {}).get("lots") or []
    except Exception as e:
        tqdm.write(f"  GraphQL error (skip={skip}): {e}")
        return []


async def _fetch_lot_details(client: httpx.AsyncClient, lot_url: str) -> dict:
    """Fetch the lot HTML page and extract hammer + image from Apollo cache."""
    full_url = BASE_URL + lot_url if lot_url.startswith("/") else lot_url
    try:
        r = await client.get(full_url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        tqdm.write(f"  page fetch error {lot_url}: {e}")
        return {}

    m = re.search(
        r'id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        r.text, re.DOTALL,
    )
    if not m:
        return {}
    try:
        cache = json.loads(m.group(1)).get("props", {}).get("pageProps", {}).get("apolloCache", {})
        return _extract_lot_data_from_cache(cache)
    except Exception:
        return {}


def _parse_lot(raw: dict, details: dict, sale_name: str, currency: str) -> dict | None:
    artist = (raw.get("creatorsDisplayTitle") or "").strip() or None
    title  = (raw.get("title") or "").strip()

    # For HK/bilingual sales, artist is embedded in title as "Artist (Chinese) | Title"
    if not artist and " | " in title:
        artist, title = title.split(" | ", 1)
        artist = re.sub(r"\s+[一-鿿].*", "", artist).strip() or artist.strip()

    if not artist and not title:
        return None

    if _NON_ART_BLOCKLIST.search(artist or "") or _NON_ART_BLOCKLIST.search(title or ""):
        return None

    est    = raw.get("estimates") or {}
    est_lo = est.get("low")
    est_hi = est.get("high")
    hammer = details.get("hammer")

    lot_url = raw.get("url") or ""
    if lot_url and not lot_url.startswith("http"):
        lot_url = BASE_URL + lot_url

    image = details.get("image")
    medium = details.get("medium")

    return {
        "id":              raw["lotId"],
        "auction_house":   AUCTION_HOUSE,
        "artist":          artist,
        "title":           title or artist,
        "medium":          medium,
        "medium_category": _medium_category(medium),
        "dimensions":      None,
        "year_created":    details.get("year"),
        "lot_number":      str(raw.get("lotNr") or ""),
        "sale_name":       sale_name,
        "sale_date":       None,
        "estimate_low":    float(est_lo) if est_lo else None,
        "estimate_high":   float(est_hi) if est_hi else None,
        "hammer_price":    hammer,
        "currency":        currency,
        "hammer_usd":      _to_usd(hammer, currency) if hammer else None,
        "provenance":      details.get("provenance"),
        "description":     f"{artist} — {title}" if title else artist,
        "image_urls":      [image] if image else [],
        "source_url":      lot_url,
    }


async def _scrape_sale(
    client: httpx.AsyncClient,
    conn,
    sale_slug: str,
    sale_name: str,
    max_lots: int,
    pbar,
    saved_ref: list[int],
    skipped_ref: list[int],
) -> None:
    tqdm.write(f"\nResolving: {sale_slug}")
    auction_id = await _resolve_auction_id(client, sale_slug)
    if not auction_id:
        tqdm.write("  could not resolve auctionId — skipping")
        return

    tqdm.write(f"  auctionId: {auction_id}")
    currency = _infer_currency(sale_slug)
    skip = 0

    while saved_ref[0] < max_lots:
        lots_raw = await _fetch_lots_page(client, auction_id, skip)
        if not lots_raw:
            break

        for raw in lots_raw:
            if saved_ref[0] >= max_lots:
                return

            lot_id = raw.get("lotId") or ""
            if not raw.get("sold"):
                continue
            if lot_exists(conn, lot_id, AUCTION_HOUSE):
                skipped_ref[0] += 1
                pbar.set_postfix(saved=saved_ref[0], existing=skipped_ref[0])
                continue

            lot_url = raw.get("url") or ""
            if not lot_url:
                tqdm.write(f"  skipped: lot {raw.get('lotNr')} — no URL")
                continue

            # Fetch lot page to get hammer price from Apollo cache
            details = await _fetch_lot_details(client, lot_url)
            if not details.get("hammer"):
                tqdm.write(f"  skipped: lot {raw.get('lotNr')} — no hammer price in Apollo cache")
                await asyncio.sleep(0.3)
                continue

            lot = _parse_lot(raw, details, sale_name, currency)
            if not lot:
                tqdm.write(f"  skipped: lot {raw.get('lotNr')} — filtered out")
                continue

            upsert_lot(conn, lot)
            saved_ref[0] += 1
            pbar.update(1)
            pbar.set_postfix(saved=saved_ref[0], existing=skipped_ref[0])
            price = f"${lot['hammer_usd']:,.0f}" if lot.get("hammer_usd") else "—"
            tqdm.write(f"  saved: {lot['artist']} — {(lot['title'] or '')[:40]} ({price})")
            await asyncio.sleep(0.5)

        if len(lots_raw) < PAGE_SIZE:
            break
        skip += PAGE_SIZE
        await asyncio.sleep(0.3)


async def scrape(max_lots: int = 300, sale_starts: list[tuple] | None = None) -> None:
    if sale_starts is None:
        sale_starts = SALE_STARTS

    conn         = connect()
    saved_ref    = [0]
    skipped_ref  = [0]

    async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
        with tqdm(total=max_lots, desc="Lots") as pbar:
            for sale_slug, sale_name in sale_starts:
                if saved_ref[0] >= max_lots:
                    break
                await _scrape_sale(
                    client, conn, sale_slug, sale_name,
                    max_lots, pbar, saved_ref, skipped_ref,
                )

    conn.close()
    print(f"\nDone — {saved_ref[0]} new Sotheby's art lots saved ({skipped_ref[0]} already in DB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape sold art lots from Sotheby's (GraphQL + per-lot page fetch)"
    )
    parser.add_argument("--max-lots", type=int, default=300)
    args = parser.parse_args()
    asyncio.run(scrape(max_lots=args.max_lots))
