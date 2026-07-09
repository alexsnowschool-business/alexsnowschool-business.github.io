"""
Sotheby's sold-lot scraper — results-page discovery + GraphQL lot fetch.

Discovery:
  Paginate https://www.sothebys.com/en/results?locale=en to find auctions.
  Each card links to /bsp-api/quickcard?uuid=<UUID>. That UUID is the auctionId
  accepted by Sotheby's GraphQL lot API — no slug-resolution step required.

Strategy:
  1. Paginate /en/results?locale=en (p=1, 2, …) to collect auction UUIDs + URLs.
  2. Filter out non-art sales via URL slug keywords.
  3. For each UUID, paginate lots via GraphQL auction(auctionId=UUID, take=100, skip=…).
  4. Skip lots where sold=False.  For sold lots not in DB, fetch the lot HTML page
     and extract the hammer price from the __NEXT_DATA__ Apollo cache.
  5. Save to art_db.
"""

import argparse
import asyncio
import json
import re


import httpx
from tqdm import tqdm

from scraper.art_db import connect, lot_exists, upsert_lot

AUCTION_HOUSE = "Sotheby's"
BASE_URL      = "https://www.sothebys.com"
GQL_URL       = "https://customerapi.prod.sothelabs.com/graphql"
RESULTS_URL   = "https://www.sothebys.com/en/results"
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

# Lot-level filter — skip individual lots that aren't fine art
_NON_ART_BLOCKLIST = re.compile(
    r"\b(château|bordeaux|burgundy|champagne|whisky|whiskey|diamond|bracelet|necklace|"
    r"earring|brooch|pendant|ring|rolex|patek|audemars|vacheron|watch|clock|"
    r"decanter|bottle|magnum|wine|beer|cognac|port|brandy|"
    r"book|manuscript|autograph|autographed|first.edition|signed.edition|"
    r"letter|archive|folio|incunabul)\b",
    re.IGNORECASE,
)

# Auction-level blocklist — skip entire sales whose URL slug signals non-art content
_NON_ART_SALE_RE = re.compile(
    r"\b(wines?|whisky|whiskey|jewelry|jewel|jewellery|watches?|nba|sports?|comics?|"
    r"handbag|spirits|cognac|champagne|bordeaux|burgundy|tequila|automobile|napa|"
    r"macallan|cask|sneaker|collectible|numismatic|coin|medal|stamp|natural.history|"
    r"science|space|entertainment|pop.culture|streetwear|fashion|luxury.accessories|"
    r"clock|barometer|instrument|silver|real.estate|gold.box|"
    r"history.of.science|popular.culture|sports.memorabilia|sneakers|"
    r"books?|manuscripts?|autographs?|archives?|literature)\b",
    re.IGNORECASE,
)

# Auction-level allowlist — Sotheby's official art department slugs.
# A sale must match at least one keyword here (after passing the blocklist) to be scraped.
# Derived from: Contemporary Art, Impressionist & Modern Art, Old Master Paintings/Drawings,
# Prints, Photographs, Sculpture, 19th/20th C. European, African, Asian, Chinese, Japanese,
# Indian, Himalayan, Islamic, Latin American, Russian, Aboriginal, Pre-Columbian, Digital Art,
# Middle East, Southeast Asian, British/Irish, Czech, Swiss, Canadian, Dutch, Belgian,
# Italian, Spanish, German/Austrian, Orientalist, Decorative Arts, Manuscripts, Judaica, etc.
_ART_SALE_ALLOWLIST = re.compile(
    r"\b("
    r"paint(?:ing)?s?|drawings?|prints?|multiples|photographs?|photography|"
    r"sculpt(?:ure)?s?|watercolou?rs?|ceramics?|porcelain|gouache|etchings?|"
    r"old[\-_]?master|works[\-_]?on[\-_]?paper|works[\-_]?of[\-_]?art|"
    r"pre[\-_]?raphaelite|pre[\-_]?columbian|"
    r"contemporary|impressionist|surreali\w*|abstract\w*|baroque|renaissance|"
    r"african|oceanic|aboriginal|asian|chinese|japanese|korean|himalayan|"
    r"islamic|judaica|orientali\w*|latin|southeast[\-_]?asian|"
    r"russian|canadian|swiss|czech|dutch|belgian|italian|spanish|"
    r"german|austrian|british|irish|european|american|indian|"
    r"digital|decorative|modern|design|"
    r"\bart\b"
    r")",
    re.IGNORECASE,
)

# Regexes for results-page HTML parsing
_UUID_RE    = re.compile(
    r'quickcard\?uuid=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
)
_AUC_URL_RE = re.compile(r'/en/buy/auction/(\d{4})/([a-z0-9][a-z0-9-]+)')

_FX      = {"USD": 1.0, "GBP": 1.27, "EUR": 1.09, "HKD": 0.128, "CHF": 1.13}
_YEAR_RE = re.compile(r"\b(1[3-9]\d{2}|20[0-2]\d)\b")
_ORDINAL_RE = re.compile(r"(\d)(St|Nd|Rd|Th)\b")


def _sale_name_from_slug(slug: str) -> str:
    """slug.replace('-', ' ').title() mangles ordinals ('19th' -> '19Th') — fix them back."""
    return _ORDINAL_RE.sub(lambda m: m.group(1) + m.group(2).lower(), slug.replace("-", " ").title())

_AUCTION_BY_SLUG_QUERY = """
query AuctionBySlug($name: String!, $year: String!) {
  auctionBySlug(slug: { name: $name, year: $year }, take: 0) {
    auctionId
    title
  }
}
"""

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
      closedAt
      endDate
      estimates { low high }
    }
  }
}
"""


def _to_usd(amount: float, currency: str) -> float:
    return round(amount * _FX.get(currency, 1.0))


def _medium_category(medium: str | None) -> str:
    if not medium:
        return "other"
    m = medium.lower()
    for kw in ("bronze", "marble", "ceramic", "terracotta", "plaster",
                "welded", "cast", "steel", "metal", "wire", "mobile",
                "aluminum", "aluminium", "glass", "wood carving"):
        if kw in m:
            return "sculpture"
    for kw in ("photograph", "gelatin", "chromogenic", "c-print", "daguerreotype"):
        if kw in m:
            return "photography"
    for kw in ("etching", "lithograph", "screenprint", "woodcut",
                "engraving", "aquatint", "mezzotint", "linocut"):
        if kw in m:
            return "print"
    for kw in ("gouache", "watercolor", "watercolour", "pastel",
                "charcoal", "pencil", "crayon", "chalk", "graphite"):
        if kw in m:
            return "works on paper"
    for kw in ("oil", "acrylic", "tempera", "fresco", "distemper", "canvas", "linen", "panel"):
        if kw in m:
            return "painting"
    return "other"


def _infer_currency(auction_url: str) -> str:
    u = auction_url.lower()
    if "london" in u or "-l" in u:
        return "GBP"
    if "hong-kong" in u or "/hk" in u:
        return "HKD"
    if "paris" in u:
        return "EUR"
    return "USD"


def _best_image_from_cache(cache: dict) -> str | None:
    lot_key = next((k for k in cache if k.startswith("LotV2:")), None)
    if not lot_key:
        return None
    lot = cache[lot_key]
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


_ISO_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _parse_iso_date(value: str | None) -> str | None:
    """Return YYYY-MM-DD from an ISO timestamp, or None."""
    if not value:
        return None
    m = _ISO_DATE_RE.search(str(value))
    return m.group(1) if m else None


def _extract_lot_data_from_cache(cache: dict) -> dict:
    result = {"hammer": None, "image": None, "medium": None, "provenance": None,
              "year": None, "closed_at": None}

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
        # closedAt / endDate live on BidState in the Apollo cache
        result["closed_at"] = _parse_iso_date(
            bid.get("closedAt") or bid.get("endDate") or bid.get("closeDate")
        )

    result["image"] = _best_image_from_cache(cache)

    lot_key = next((k for k in cache if k.startswith("LotV2:")), None)
    if lot_key:
        lot = cache[lot_key]
        desc       = lot.get("description") or ""
        lot_concise = lot.get("lotConcise") or ""
        provenance = lot.get("provenance") or ""

        desc_text = re.sub(r"<[^>]+>", " ", desc)
        result["provenance"] = re.sub(r"<[^>]+>", " ", provenance).strip()[:400] or None

        y = _YEAR_RE.search(desc_text)
        if y:
            result["year"] = y.group(1)

        if lot_concise:
            parts = lot_concise.split(",")
            if len(parts) >= 3:
                result["medium"] = ", ".join(p.strip() for p in parts[2:4]).strip() or None

    return result


async def _resolve_auction_id(client: httpx.AsyncClient, year: str, slug: str) -> str | None:
    """Resolve year + slug to the GraphQL auctionId UUID."""
    try:
        r = await client.post(
            GQL_URL,
            json={"query": _AUCTION_BY_SLUG_QUERY, "variables": {"name": slug, "year": year}},
            headers=_GQL_HEADERS,
            timeout=15,
        )
        return (r.json().get("data", {}).get("auctionBySlug") or {}).get("auctionId")
    except Exception as e:
        tqdm.write(f"  auctionBySlug error for {year}/{slug}: {e}")
        return None


async def _discover_auctions(
    client: httpx.AsyncClient,
    max_pages: int,
) -> list[tuple[str, str, str]]:
    """
    Paginate /en/results and return [(year, slug, auction_url)] for art auctions.
    Filters out non-art sales using URL slug keywords.
    The caller uses year+slug to resolve the GraphQL auctionId via auctionBySlug.
    """
    seen: set[str] = set()
    result: list[tuple[str, str, str]] = []

    for page in range(1, max_pages + 1):
        tqdm.write(f"\nDiscovering: results page {page}/{max_pages}")
        try:
            r = await client.get(
                RESULTS_URL,
                params={"locale": "en", "p": str(page)},
                timeout=25,
            )
        except Exception as e:
            tqdm.write(f"  error fetching results page {page}: {e}")
            break

        html = r.text

        for m in _UUID_RE.finditer(html):
            # Extract auction URL from the ±800-char context window around each quickcard link
            ctx_start = max(0, m.start() - 800)
            ctx_end   = min(len(html), m.end() + 200)
            ctx       = html[ctx_start:ctx_end]

            url_m = _AUC_URL_RE.search(ctx)
            if not url_m:
                continue  # no /en/buy/auction/ link → not a standard auction

            year, slug = url_m.group(1), url_m.group(2)
            key = f"{year}/{slug}"
            if key in seen:
                continue

            if _NON_ART_SALE_RE.search(slug):
                tqdm.write(f"  skip non-art: {slug}")
                continue

            if not _ART_SALE_ALLOWLIST.search(slug):
                tqdm.write(f"  skip unknown category: {slug}")
                continue

            seen.add(key)
            auction_url = f"/en/buy/auction/{year}/{slug}"
            result.append((year, slug, auction_url))
            tqdm.write(f"  + {key}")

        await asyncio.sleep(0.4)

    tqdm.write(f"\nDiscovered {len(result)} art auction(s) across {max_pages} results page(s)")
    return result


async def _fetch_lots_page(
    client: httpx.AsyncClient, auction_id: str, skip: int
) -> list[dict]:
    try:
        r = await client.post(
            GQL_URL,
            json={
                "query": _LOT_LIST_QUERY,
                "variables": {"auctionId": auction_id, "take": PAGE_SIZE, "skip": skip},
            },
            headers=_GQL_HEADERS,
            timeout=20,
        )
        return r.json().get("data", {}).get("auction", {}).get("lots") or []
    except Exception as e:
        tqdm.write(f"  GraphQL error (skip={skip}): {e}")
        return []


async def _fetch_lot_details(client: httpx.AsyncClient, lot_url: str) -> dict:
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


def _parse_lot(raw: dict, details: dict, sale_name: str, currency: str, year: str | None = None) -> dict | None:
    artist = (raw.get("creatorsDisplayTitle") or "").strip() or None
    title  = (raw.get("title") or "").strip()

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

    # Prefer exact lot-close date; fall back to auction year from URL slug.
    # Sources in priority order: GQL closedAt/endDate fields, Apollo BidState.
    sale_date = (
        _parse_iso_date(raw.get("closedAt") or raw.get("endDate"))
        or details.get("closed_at")
        or year
    )

    lot_url = raw.get("url") or ""
    if lot_url and not lot_url.startswith("http"):
        lot_url = BASE_URL + lot_url

    return {
        "id":              raw["lotId"],
        "auction_house":   AUCTION_HOUSE,
        "artist":          artist,
        "title":           title or artist,
        "medium":          details.get("medium"),
        "medium_category": _medium_category(details.get("medium")),
        "dimensions":      None,
        "year_created":    details.get("year"),
        "lot_number":      str(raw.get("lotNr") or ""),
        "sale_name":       sale_name,
        "sale_date":       sale_date,
        "estimate_low":    float(est_lo) if est_lo else None,
        "estimate_high":   float(est_hi) if est_hi else None,
        "hammer_price":    hammer,
        "currency":        currency,
        "hammer_usd":      _to_usd(hammer, currency) if hammer else None,
        "provenance":      details.get("provenance"),
        "description":     f"{artist} — {title}" if title else artist,
        "image_urls":      [details["image"]] if details.get("image") else [],
        "source_url":      lot_url,
    }


async def _scrape_sale(
    client: httpx.AsyncClient,
    conn,
    year: str,
    slug: str,
    auction_url: str,
    sale_name: str,
    max_lots: int,
    pbar,
    saved_ref: list[int],
    skipped_ref: list[int],
) -> None:
    tqdm.write(f"\nResolving: {year}/{slug}")
    auction_id = await _resolve_auction_id(client, year, slug)
    if not auction_id:
        tqdm.write("  could not resolve auctionId — skipping")
        return

    tqdm.write(f"  auctionId: {auction_id}")
    currency = _infer_currency(auction_url)
    skip = 0
    first_page_ids: set[str] = set()

    MAX_CONSECUTIVE_NO_PRICE = 15
    MAX_CONSECUTIVE_EXISTING = 50
    consecutive_no_price = 0
    consecutive_existing = 0

    while saved_ref[0] < max_lots:
        lots_raw = await _fetch_lots_page(client, auction_id, skip)
        if not lots_raw:
            break

        page_ids = {r.get("lotId") for r in lots_raw if r.get("lotId")}
        if skip == 0:
            first_page_ids = page_ids
        elif page_ids == first_page_ids:
            tqdm.write("  API repeated first page — stopping")
            break

        for raw in lots_raw:
            if saved_ref[0] >= max_lots:
                return

            if not raw.get("sold"):
                continue

            lot_id = raw.get("lotId") or ""
            if lot_exists(conn, lot_id, AUCTION_HOUSE):
                skipped_ref[0] += 1
                consecutive_existing += 1
                pbar.set_postfix(saved=saved_ref[0], existing=skipped_ref[0])
                if consecutive_existing >= MAX_CONSECUTIVE_EXISTING:
                    tqdm.write(f"  {MAX_CONSECUTIVE_EXISTING} consecutive existing lots — sale done")
                    return
                continue

            lot_url = raw.get("url") or ""
            if not lot_url:
                tqdm.write(f"  skipped: lot {raw.get('lotNr')} — no URL")
                continue

            details = await _fetch_lot_details(client, lot_url)
            if not details.get("hammer"):
                consecutive_no_price += 1
                pbar.set_postfix(saved=saved_ref[0], existing=skipped_ref[0], no_price=consecutive_no_price)
                tqdm.write(f"  no price: lot {raw.get('lotNr')} ({consecutive_no_price}/{MAX_CONSECUTIVE_NO_PRICE})")
                if consecutive_no_price >= MAX_CONSECUTIVE_NO_PRICE:
                    tqdm.write(f"  {MAX_CONSECUTIVE_NO_PRICE} consecutive no-price lots — next sale")
                    return
                await asyncio.sleep(0.3)
                continue

            consecutive_no_price = 0
            consecutive_existing = 0

            lot = _parse_lot(raw, details, sale_name, currency, year)
            if not lot:
                tqdm.write(f"  skipped: lot {raw.get('lotNr')} — filtered")
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


async def scrape(max_lots: int = 50, max_pages: int = 10) -> None:
    conn        = connect()
    saved_ref   = [0]
    skipped_ref = [0]

    async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
        auctions = await _discover_auctions(client, max_pages=max_pages)

        with tqdm(total=max_lots, desc="Lots") as pbar:
            for year, slug, auction_url in auctions:
                if saved_ref[0] >= max_lots:
                    break
                sale_name = _sale_name_from_slug(slug)
                await _scrape_sale(
                    client, conn, year, slug, auction_url, sale_name,
                    max_lots, pbar, saved_ref, skipped_ref,
                )

    conn.close()
    print(f"\nDone — {saved_ref[0]} new Sotheby's lots saved ({skipped_ref[0]} already in DB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape sold art lots from Sotheby's via results-page discovery"
    )
    parser.add_argument(
        "--max-lots",  type=int, default=50,
        help="Stop after saving this many new lots (default: 50)",
    )
    parser.add_argument(
        "--max-pages", type=int, default=10,
        help="Results pages to paginate for auction discovery (default: 10, ≈140 auctions)",
    )
    args = parser.parse_args()
    asyncio.run(scrape(max_lots=args.max_lots, max_pages=args.max_pages))
