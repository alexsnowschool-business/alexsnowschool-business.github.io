"""
Artprice upcoming (futures) auction lots scraper — Playwright-based.

Artprice uses JavaScript-based bot detection, so this scraper uses Playwright
to render pages with real JS execution (Chromium, headless).

The /sales/futures page publicly lists AUCTION HIGHLIGHTS — upcoming sales from
major houses with full lot details (artist, title, medium, dimensions, estimates).
No subscription is required for this data.

Strategy:
  1. Navigate /sales/futures with Playwright and extract highlighted sale redir links.
  2. Follow each redir to get the canonical sale URL (sale_id + slug).
  3. Call ?facets=1&format=json&id={sale_id} to get totalPages.
  4. Paginate through ?p=N, parsing lot blocks from the server-rendered HTML.
  5. Store upcoming lots in art_db (no hammer_price — sale hasn't occurred yet).

Lot identity: artprice lot ID extracted from id="lot-{id}" HTML attribute,
combined with auction_house="Artprice" as the DB primary key.
"""

import argparse
import asyncio
import html as html_lib
import re

from tqdm import tqdm
from playwright.async_api import async_playwright

from scraper.art_db import connect, lot_exists, upsert_lot

AUCTION_HOUSE = "Artprice"
BASE_URL      = "https://www.artprice.com"
FUTURES_URL   = f"{BASE_URL}/sales/futures"
PAGE_SIZE     = 30  # lots per page (observed)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)

_MONTH_MAP = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

_NON_ART_BLOCKLIST = re.compile(
    r"\b(château|bordeaux|burgundy|champagne|whisky|whiskey|diamond|bracelet|necklace|"
    r"earring|brooch|pendant|ring|rolex|patek|audemars|vacheron|watch|clock|"
    r"decanter|bottle|magnum|wine|beer|cognac|port|brandy)\b",
    re.IGNORECASE,
)
_YEAR_IN_TITLE_RE = re.compile(r"\(c?\.?\s*(1[3-9]\d{2}|20[0-2]\d)\s*\)\s*$")
_DATE_RE          = re.compile(
    r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})",
    re.IGNORECASE,
)


def _detect_currency(text: str) -> str:
    if "HK$" in text:
        return "HKD"
    if "€" in text:
        return "EUR"
    if "£" in text:
        return "GBP"
    if "¥" in text:
        return "JPY"
    return "USD"


def _parse_amount(text: str) -> float | None:
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _parse_date(text: str) -> str | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    day, month, year = m.groups()
    return f"{year}-{_MONTH_MAP[month.lower()]}-{int(day):02d}"


def _medium_category(medium: str | None) -> str:
    if not medium:
        return "other"
    m = medium.lower()
    for kw in ("bronze", "marble", "ceramic", "terracotta", "plaster", "welded",
               "cast", "steel", "metal", "wire", "mobile", "aluminum", "aluminium",
               "glass", "wood carving", "sculpture"):
        if kw in m:
            return "sculpture"
    for kw in ("photograph", "gelatin", "chromogenic", "c-print", "daguerreotype"):
        if kw in m:
            return "photography"
    for kw in ("etching", "lithograph", "screenprint", "woodcut",
               "engraving", "aquatint", "mezzotint", "linocut"):
        if kw in m:
            return "print"
    for kw in ("gouache", "watercolor", "watercolour", "pastel", "charcoal",
               "pencil", "crayon", "chalk", "graphite", "ink", "felt pen",
               "decollage", "collage"):
        if kw in m:
            return "works on paper"
    for kw in ("oil", "acrylic", "tempera", "fresco", "distemper",
               "canvas", "linen", "panel"):
        if kw in m:
            return "painting"
    return "other"


def _strip_tags(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


def _parse_lot_block(block: str, sale_name: str, sale_date: str | None) -> dict | None:
    """Parse a single lot anchor block. Returns None if lot should be skipped."""
    # Lot ID from id="lot-{id}"
    id_m = re.search(r'id="lot-(\d+)"', block)
    if not id_m:
        return None
    lot_id = id_m.group(1)

    # Source URL — /artist/{artist_id}/{slug}/{medium}/{lot_id}/{title}
    url_m = re.search(r'href="(/artist/[^"?]+)', block)
    source_url = BASE_URL + url_m.group(1) if url_m else f"{BASE_URL}/lot/{lot_id}"

    # Title (may include year suffix like "Sans titre (1988)")
    title_m = re.search(r'class="lot-title"[^>]*>(.*?)</div>', block, re.DOTALL)
    raw_title = _strip_tags(title_m.group(1)) if title_m else ""
    year_m = _YEAR_IN_TITLE_RE.search(raw_title)
    year = year_m.group(1) if year_m else None
    title = _YEAR_IN_TITLE_RE.sub("", raw_title).strip() or raw_title

    # Artist
    artist_m = re.search(r'class="lot-artist"[^>]*>(.*?)</div>', block, re.DOTALL)
    artist = _strip_tags(artist_m.group(1)) if artist_m else None

    if not artist and not title:
        return None

    if _NON_ART_BLOCKLIST.search(artist or "") or _NON_ART_BLOCKLIST.search(title or ""):
        return None

    # Medium
    med_m = re.search(r'class="technique"[^>]*>(.*?)</div>', block, re.DOTALL)
    medium = _strip_tags(med_m.group(1)) if med_m else None

    # Dimensions
    size_m = re.search(r'class="size"[^>]*>.*?<span>(.*?)</span>', block, re.DOTALL)
    dimensions = _strip_tags(size_m.group(1)) if size_m else None

    # Estimates — "Estimate: <span class="strong"><span>€ 3,500</span> - <span>€ 4,500</span></span>"
    est_spans = re.findall(
        r'class="estimation".*?<span[^>]*>([^<]+)</span>.*?<span[^>]*>([^<]+)</span>',
        block, re.DOTALL,
    )
    est_lo = est_hi = None
    currency = "EUR"
    if est_spans:
        lo_txt, hi_txt = est_spans[0]
        currency = _detect_currency(lo_txt)
        est_lo = _parse_amount(lo_txt)
        est_hi = _parse_amount(hi_txt)

    # Sale date from first .lot-auctioneer span
    date_m = re.search(r'class="lot-auctioneer"[^>]*>.*?<span[^>]*>([^<]+)</span>', block, re.DOTALL)
    lot_date = _parse_date(date_m.group(1)) if date_m else sale_date

    # Image URL
    img_m = re.search(r'src="(https://imgprivate2\.artprice\.com/lots/[^"]+)"', block)
    images = [img_m.group(1)] if img_m else []

    return {
        "id":              lot_id,
        "auction_house":   AUCTION_HOUSE,
        "artist":          artist,
        "title":           title or raw_title or artist,
        "medium":          medium,
        "medium_category": _medium_category(medium),
        "dimensions":      dimensions,
        "year_created":    year,
        "lot_number":      lot_id,
        "sale_name":       sale_name,
        "sale_date":       lot_date or sale_date,
        "estimate_low":    est_lo,
        "estimate_high":   est_hi,
        "hammer_price":    None,
        "currency":        currency,
        "hammer_usd":      None,
        "provenance":      None,
        "description":     f"{artist} — {title}" if artist and title else (artist or title),
        "image_urls":      images,
        "source_url":      source_url,
    }


def _parse_lots_from_html(html: str, sale_name: str, sale_date: str | None) -> list[dict]:
    """Extract all lot records from a sale page's rendered HTML."""
    lots = []
    # Split on anchor opens — each lot is wrapped in <a id="lot-{id}" ...>
    blocks = re.split(r'(?=<a\s+id="lot-\d+)', html)
    for block in blocks:
        lot = _parse_lot_block(block, sale_name, sale_date)
        if lot:
            lots.append(lot)
    return lots


async def _get_total_pages(page, sale_id: str, sale_url: str) -> int:
    """Call the JSON facets API to retrieve total page count."""
    facets_url = f"{sale_url}?facets=1&format=json&id={sale_id}"
    total_pages = [1]

    async def _capture(resp):
        if "format=json" in resp.url and "sale" in resp.url:
            try:
                data = await resp.json()
                tp = data.get("totalPages")
                if tp:
                    total_pages[0] = int(tp)
            except Exception:
                pass

    page.on("response", _capture)
    await page.goto(sale_url, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(2000)
    page.remove_listener("response", _capture)
    return total_pages[0]


async def _navigate_and_get_html(page, url: str) -> str:
    """Navigate to url and return rendered page HTML after Angular/React hydration."""
    await page.goto(url, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(2000)
    return await page.content()


async def _get_sale_metadata(html: str) -> tuple[str, str | None]:
    """Extract sale name and date from the sale page HTML."""
    h1_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.DOTALL | re.IGNORECASE)
    sale_name = html_lib.unescape(_strip_tags(h1_m.group(1))) if h1_m else "Unknown Sale"

    sale_date = _parse_date(html)
    return sale_name, sale_date


async def _scrape_sale(
    page,
    conn,
    sale_id: str,
    sale_url: str,
    max_lots: int,
    pbar,
    saved_ref: list[int],
    skipped_ref: list[int],
) -> None:
    tqdm.write(f"\n  Sale {sale_id}: {sale_url}")

    # Get total pages and sale metadata from first page
    total_pages = await _get_total_pages(page, sale_id, sale_url)
    html = await page.content()
    sale_name, sale_date = await _get_sale_metadata(html)

    tqdm.write(f"  '{sale_name}' — {total_pages} pages, date: {sale_date}")

    MAX_CONSECUTIVE_EXISTING = 30

    for page_num in range(1, total_pages + 1):
        if saved_ref[0] >= max_lots:
            return

        if page_num > 1:
            page_url = f"{sale_url}?p={page_num}"
            html = await _navigate_and_get_html(page, page_url)

        lots = _parse_lots_from_html(html, sale_name, sale_date)
        if not lots:
            tqdm.write(f"  Page {page_num}: no lots parsed — stopping sale")
            break

        consecutive_existing = 0
        for lot in lots:
            if saved_ref[0] >= max_lots:
                return

            if lot_exists(conn, lot["id"], AUCTION_HOUSE):
                skipped_ref[0] += 1
                consecutive_existing += 1
                pbar.set_postfix(saved=saved_ref[0], existing=skipped_ref[0])
                if consecutive_existing >= MAX_CONSECUTIVE_EXISTING:
                    tqdm.write(f"  {MAX_CONSECUTIVE_EXISTING} consecutive existing lots — sale fully scraped")
                    return
                continue

            consecutive_existing = 0
            upsert_lot(conn, lot)
            saved_ref[0] += 1
            pbar.update(1)
            pbar.set_postfix(saved=saved_ref[0], existing=skipped_ref[0])

            est = ""
            if lot.get("estimate_low") and lot.get("estimate_high"):
                sym = {"EUR": "€", "GBP": "£", "USD": "$", "HKD": "HK$"}.get(lot["currency"], "")
                est = f"{sym}{lot['estimate_low']:,.0f}–{lot['estimate_high']:,.0f}"
            tqdm.write(
                f"  saved: {lot['artist']} — {(lot['title'] or '')[:40]} ({est})"
            )

        await asyncio.sleep(0.5)


async def _get_futures_sale_links(page) -> list[str]:
    """Navigate /sales/futures and return all highlighted redir URLs."""
    await page.goto(FUTURES_URL, wait_until="networkidle", timeout=40000)
    await page.wait_for_timeout(3000)

    html = await page.content()
    # Links are HTML-encoded: /redir?ia=50904&amp;f=future_sales
    redir_ids = re.findall(r'/redir\?ia=(\d+)&(?:amp;)?f=future_sales', html)
    seen = set()
    unique_ids = []
    for rid in redir_ids:
        if rid not in seen:
            seen.add(rid)
            unique_ids.append(rid)

    tqdm.write(f"Found {len(unique_ids)} highlighted upcoming sales")
    return unique_ids


async def _resolve_sale_url(page, redir_id: str) -> tuple[str, str] | None:
    """Follow /redir?ia={id}&f=future_sales to get (sale_id, canonical_sale_url)."""
    redir_url = f"{BASE_URL}/redir?ia={redir_id}&f=future_sales"
    await page.goto(redir_url, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(4000)

    final_url = page.url
    # Expected: https://www.artprice.com/sale/{sale_id}/{slug}
    m = re.search(r"/sale/(\d+)/", final_url)
    if not m:
        tqdm.write(f"  Could not resolve sale ID from {final_url}")
        return None

    sale_id = m.group(1)
    # Canonical URL without query params
    canonical = re.sub(r"\?.*", "", final_url)
    return sale_id, canonical


async def scrape(max_lots: int = 100) -> None:
    conn = connect()
    saved_ref  = [0]
    skipped_ref = [0]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=_UA,
            locale="en-US",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        with tqdm(total=max_lots, desc="Artprice lots") as pbar:
            redir_ids = await _get_futures_sale_links(page)

            for redir_id in redir_ids:
                if saved_ref[0] >= max_lots:
                    break

                result = await _resolve_sale_url(page, redir_id)
                if not result:
                    continue

                sale_id, sale_url = result
                await _scrape_sale(
                    page, conn, sale_id, sale_url,
                    max_lots, pbar, saved_ref, skipped_ref,
                )

        await browser.close()

    conn.close()
    print(f"\nDone — {saved_ref[0]} new Artprice lots saved ({skipped_ref[0]} already in DB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape upcoming art lots from Artprice futures page"
    )
    parser.add_argument("--max-lots", type=int, default=100)
    args = parser.parse_args()
    asyncio.run(scrape(max_lots=args.max_lots))
