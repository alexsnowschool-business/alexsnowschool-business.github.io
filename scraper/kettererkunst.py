"""
Ketterer Kunst sold-lot scraper — plain HTTP, no JS rendering needed.

Discovery:
  Paginate https://www.kettererkunst.com/result.php?seite=N&shw=1&auswahl=vk&gebiet=9
  ("auswahl=vk" = "verkauft" / sold; "gebiet=9" = the Modern & Contemporary Art
  department, identified from an Evening Sale lot during scoping — Ketterer
  also runs Post-War/Contemporary, rare books, and other departments under
  different `gebiet` values not yet catalogued here).

  Each listing page embeds 30 lots as `/still/kunst/pic570/{anummer}/{obnr}.jpg`
  image paths, which double as the (auction_number, object_number) key needed
  to build the English detail-page URL — no extra discovery hop required.

Detail page:
  https://www.kettererkunst.com/details-e.php?obnr={obnr}&anummer={anummer}
  Ships fully server-rendered English HTML (no client JS needed) with artist,
  title, year, medium, estimate, sold price (EUR + USD, EUR already given —
  no FX table needed), and a free-text lot description block containing
  dimensions and a "PROVENANCE:" section.

Caveat: Ketterer's "Sold" price includes buyer's premium ("incl. surcharge"),
unlike Christie's price_realised / Sotheby's bidAsk which are pre-premium
hammer prices. Stored in `hammer_price` for schema consistency, but it is not
an apples-to-apples hammer price against the other two houses.
"""

import argparse
import asyncio
import html
import re
from datetime import datetime

import httpx
from tqdm import tqdm

from scraper.art_db import connect, lot_exists, upsert_lot

AUCTION_HOUSE = "Ketterer Kunst"
BASE_URL      = "https://www.kettererkunst.com"
RESULTS_URL   = f"{BASE_URL}/result.php"
DETAIL_URL    = f"{BASE_URL}/details-e.php"
GEBIET        = "9"  # Modern & Contemporary Art department

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

_NON_ART_BLOCKLIST = re.compile(
    r"\b(château|bordeaux|burgundy|champagne|whisky|whiskey|diamond|bracelet|necklace|"
    r"earring|brooch|pendant|ring|rolex|patek|audemars|vacheron|watch|clock|"
    r"decanter|bottle|magnum|wine|beer|cognac|port|brandy)\b",
    re.IGNORECASE,
)

_LOT_IMG_RE      = re.compile(r"/still/kunst/pic570/(\d+)/(\d+)\.jpg")
_SALE_BANNER_RE  = re.compile(
    r"Sale:\s*<b>(\d+)\s*/\s*([^,<]+),</b>\s*([^<]+?)\s+in\s+([^<]+?)\s*</a>"
    r".*?Lot\s+(\d+)",
    re.DOTALL,
)
_ARTIST_RE       = re.compile(r"text-transform:uppercase;'>([^<]+)</span>")
_TITLE_YEAR_RE   = re.compile(r"<i>([^<]+)</i>,\s*(\d{4})\.")
_MEDIUM_RE       = re.compile(
    r"</i>,\s*\d{4}\.\s*</div>\s*<div style='margin-top:15px;'>\s*([^<]+?)\s*</div>"
)
_ESTIMATE_RE     = re.compile(
    r"Estimate:</b></div>\s*&euro;\s*([\d,]+)\s*/\s*\$\s*([\d,]+)"
)
_SOLD_RE         = re.compile(
    r"Sold:</b></div>\s*&euro;\s*([\d,]+)\s*/\s*\$\s*([\d,]+)"
)
_DESC_BLOCK_RE   = re.compile(
    r"class='block_beschreibung_sub beschreibung'>(.*?)</div>", re.DOTALL
)
_DIMENSIONS_RE   = re.compile(r"[\d.,]+\s*x\s*[\d.,]+\s*cm(?:\s*\([^)]*\))?", re.IGNORECASE)
_PROVENANCE_RE   = re.compile(
    r"PROVENANCE:\s*(.*?)(?:<br\s*/?>\s*){2}[A-Z]{4,}:|PROVENANCE:\s*(.*?)$",
    re.DOTALL,
)
_DATE_RE         = re.compile(r"([A-Za-z]+)\s+(\d{1,2})\.\s+(\d{4})")


def _clean(html_fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", html_fragment)).strip()


def _parse_num(txt: str) -> float | None:
    try:
        return float(txt.replace(",", ""))
    except (ValueError, AttributeError):
        return None


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


def _parse_sale_date(date_txt: str) -> str | None:
    m = _DATE_RE.search(date_txt)
    if not m:
        return None
    month, day, year = m.groups()
    try:
        return datetime.strptime(f"{month} {day} {year}", "%B %d %Y").strftime("%Y-%m-%d")
    except ValueError:
        return year


async def _discover_lot_keys(client: httpx.AsyncClient, max_pages: int) -> list[tuple[str, str]]:
    """Paginate the results listing and return [(anummer, obnr)] newest-first."""
    keys: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for page in range(1, max_pages + 1):
        try:
            r = await client.get(
                RESULTS_URL,
                params={"seite": str(page), "shw": "1", "auswahl": "vk", "gebiet": GEBIET},
                timeout=20,
            )
            r.raise_for_status()
        except Exception as e:
            tqdm.write(f"  results page {page} fetch error: {e}")
            break

        page_keys = _LOT_IMG_RE.findall(r.text)  # already (anummer, obnr) per regex group order
        new_keys = [k for k in page_keys if k not in seen]
        if not page_keys:
            tqdm.write(f"  results page {page} empty — stopping discovery")
            break

        seen.update(page_keys)
        keys.extend(new_keys)
        tqdm.write(f"  results page {page}: {len(page_keys)} lots ({len(new_keys)} new)")
        await asyncio.sleep(0.3)

    return keys


def _parse_lot_detail(body: str, anummer: str, obnr: str) -> dict | None:
    artist_m = _ARTIST_RE.search(body)
    title_m  = _TITLE_YEAR_RE.search(body)
    if not artist_m or not title_m:
        return None

    artist = html.unescape(artist_m.group(1).strip())
    title, year_created = html.unescape(title_m.group(1).strip()), title_m.group(2)

    if _NON_ART_BLOCKLIST.search(artist) or _NON_ART_BLOCKLIST.search(title):
        return None

    banner_m  = _SALE_BANNER_RE.search(body)
    sale_name = f"{banner_m.group(2).strip()}, {banner_m.group(4).strip()}" if banner_m else None
    sale_date = _parse_sale_date(banner_m.group(3)) if banner_m else None
    lot_number = banner_m.group(5) if banner_m else None

    medium_m = _MEDIUM_RE.search(body)
    medium   = html.unescape(medium_m.group(1).strip()) if medium_m else None

    est_m  = _ESTIMATE_RE.search(body)
    sold_m = _SOLD_RE.search(body)
    # Ketterer publishes a single estimate figure, not a low/high range.
    est_low   = _parse_num(est_m.group(1)) if est_m else None
    est_high  = est_low
    hammer    = _parse_num(sold_m.group(1)) if sold_m else None
    hammer_usd = _parse_num(sold_m.group(2)) if sold_m else None

    desc_m      = _DESC_BLOCK_RE.search(body)
    dimensions  = None
    provenance  = None
    if desc_m:
        desc_html = desc_m.group(1)
        dim_m = _DIMENSIONS_RE.search(_clean(desc_html))
        dimensions = dim_m.group(0) if dim_m else None
        prov_m = _PROVENANCE_RE.search(desc_html)
        if prov_m:
            raw_prov = prov_m.group(1) or prov_m.group(2) or ""
            provenance = _clean(raw_prov)[:400] or None

    return {
        "id":              obnr,
        "auction_house":   AUCTION_HOUSE,
        "artist":          artist,
        "title":           title,
        "medium":          medium,
        "medium_category": _medium_category(medium),
        "dimensions":      dimensions,
        "year_created":    year_created,
        "lot_number":      lot_number,
        "sale_name":       sale_name,
        "sale_date":       sale_date,
        "estimate_low":    est_low,
        "estimate_high":   est_high,
        "hammer_price":    hammer,
        "currency":        "EUR",
        "hammer_usd":      hammer_usd,
        "provenance":      provenance,
        "description":     f"{artist} — {title}" if title else artist,
        "image_urls":      [f"{BASE_URL}/still/kunst/pic570/{anummer}/{obnr}.jpg"],
        "source_url":      f"{DETAIL_URL}?obnr={obnr}&anummer={anummer}",
    }


async def _scrape_lot(
    client: httpx.AsyncClient, conn, anummer: str, obnr: str,
) -> dict | None:
    try:
        r = await client.get(DETAIL_URL, params={"obnr": obnr, "anummer": anummer}, timeout=20)
        r.raise_for_status()
    except Exception as e:
        tqdm.write(f"  detail fetch error obnr={obnr}: {e}")
        return None
    return _parse_lot_detail(r.text, anummer, obnr)


async def scrape(max_lots: int = 100, max_pages: int = 20) -> None:
    conn = connect()
    saved = 0
    consecutive_existing = 0
    MAX_CONSECUTIVE_EXISTING = 60

    async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True) as client:
        keys = await _discover_lot_keys(client, max_pages)
        tqdm.write(f"\nDiscovered {len(keys)} candidate lots — fetching details")

        with tqdm(total=min(max_lots, len(keys)), desc="Lots") as pbar:
            for anummer, obnr in keys:
                if saved >= max_lots:
                    break

                if lot_exists(conn, obnr, AUCTION_HOUSE):
                    consecutive_existing += 1
                    if consecutive_existing >= MAX_CONSECUTIVE_EXISTING:
                        tqdm.write(f"  {MAX_CONSECUTIVE_EXISTING} consecutive existing lots — stopping")
                        break
                    continue

                lot = await _scrape_lot(client, conn, anummer, obnr)
                if not lot:
                    tqdm.write(f"  skipped: obnr={obnr} — filtered or unparsable")
                    await asyncio.sleep(0.3)
                    continue

                consecutive_existing = 0
                upsert_lot(conn, lot)
                saved += 1
                pbar.update(1)
                price = f"€{lot['hammer_price']:,.0f}" if lot.get("hammer_price") else "—"
                tqdm.write(f"  saved: {lot['artist']} — {(lot['title'] or '')[:40]} ({price})")
                await asyncio.sleep(0.5)

    conn.close()
    print(f"\nDone — {saved} new Ketterer Kunst lots saved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape sold art lots from Ketterer Kunst")
    parser.add_argument("--max-lots",  type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=20,
                         help="Results pages to paginate for lot discovery (default: 20, ~600 lots)")
    args = parser.parse_args()
    asyncio.run(scrape(max_lots=args.max_lots, max_pages=args.max_pages))
