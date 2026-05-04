"""
Hermès scraper — authentic bags and accessories directly from hermes.com (DE locale).

Uses Scrapling's AsyncStealthySession (Camoufox/Firefox-based) to bypass Hermes's
Cloudflare protection. Strategy mirrors vestiaire.py and vinted.py:
  1. Warm up on the homepage to acquire CF clearance cookies
  2. Fetch category listing pages and extract product URLs
  3. Fetch each product detail page and parse structured data

Each item saved as:
    platform = "hermes.com"
    authenticity_label = "authentic"
    condition = "new"

Rich metadata (leather_type, dimensions, collection_since, etc.) is extracted from the
German-language description and saved to both SQLite and data/hermes/metadata/*.json
since the DB schema only stores standard fields.
"""

import argparse
import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from scrapling.fetchers import AsyncStealthySession
from tqdm import tqdm

from scraper.db import connect, item_exists, upsert_item

PLATFORM  = "hermes.com"
BASE_URL  = "https://www.hermes.com"
HOMEPAGE  = f"{BASE_URL}/de/de/"
META_DIR  = Path("data/hermes/metadata")

# DE/DE bag and leather-goods category pages to scrape
# URLs discovered from hermes.com/de/de/ navigation — all bags live under /lederwaren/
CATEGORIES = [
    f"{BASE_URL}/de/de/category/lederwaren/taschen-und-kleine-taschen/taschen-und-kleine-taschen-fur-damen/",
    f"{BASE_URL}/de/de/category/lederwaren/taschen-und-kleine-taschen/taschen-und-kleine-taschen-fur-herren/",
    f"{BASE_URL}/de/de/category/lederwaren/kleinlederwaren/brieftaschen/",
    f"{BASE_URL}/de/de/category/lederwaren/kleinlederwaren/",
    f"{BASE_URL}/de/de/category/lederwaren/reisen/koffer-und-reisetaschen/",
]

_DIM_RE      = re.compile(r"Abmessungen:\s*([^|\n]+)")
# Match the leather name after "aus " — e.g. "Tasche aus Epsom-Kalbsleder" → "Epsom-Kalbsleder"
_LEATHER_RE  = re.compile(
    r"aus\s+([\w\-]+(?:leder|canvas|toile|swift|clemence|epsom|togo|vache|barenia|evergrain|croco|ostrich|alligator)[\w\-]*)",
    re.IGNORECASE,
)
_SINCE_RE    = re.compile(r"In der Kollektion verwendet seit[:\s]+([^\n]+)")
_HAND_RE     = re.compile(r"Zum Tragen in der Hand", re.IGNORECASE)
_SHOULDER_RE = re.compile(r"Schulter|diagonal", re.IGNORECASE)
_HANDMADE_RE = re.compile(r"handgefertigt", re.IGNORECASE)
_SIZE_RE     = re.compile(r"\b(\d{2})\b")
_REF_RE      = re.compile(r"([A-Z][0-9]{6}[A-Z0-9]{2,})")
_IMG_RES_RE  = re.compile(r"-\d+-\d+(_g\.(?:jpg|webp|png))$")


def _hires(url: str) -> str:
    """Upscale Hermès CDN thumbnails to 800×800 (matching existing data format)."""
    return _IMG_RES_RE.sub(r"-800-800\1", url)


def _parse_description(text: str) -> dict:
    leather_m = _LEATHER_RE.search(text)
    dim_m     = _DIM_RE.search(text)
    since_m   = _SINCE_RE.search(text)
    return {
        "leather_type":     leather_m.group(1).strip() if leather_m else "",
        "dimensions":       dim_m.group(1).strip() if dim_m else "",
        "collection_since": since_m.group(1).strip() if since_m else "",
        "handmade":         bool(_HANDMADE_RE.search(text)),
        "carry_type":       "hand" if _HAND_RE.search(text) else (
                            "shoulder" if _SHOULDER_RE.search(text) else ""),
    }


def _parse_product_page(page, url: str) -> dict | None:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    ref_m = _REF_RE.search(slug)
    product_ref = ref_m.group(1) if ref_m else ""

    # Prefer JSON-LD structured data — survives layout/class-name changes
    name = description = price_str = availability = None
    img_urls: list[str] = []

    for script_text in page.css('script[type="application/ld+json"]::text').getall():
        try:
            data = json.loads(script_text)
            if isinstance(data, list):
                data = next((d for d in data if d.get("@type") == "Product"), None)
            if not data or data.get("@type") != "Product":
                continue
            name = data.get("name", "")
            description = data.get("description", "")
            offers = data.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if price_val := offers.get("price"):
                currency = offers.get("priceCurrency", "EUR")
                try:
                    price_str = (
                        f"€{float(price_val):,.0f}"
                        if currency == "EUR"
                        else f"{currency} {float(price_val):,.0f}"
                    )
                except (ValueError, TypeError):
                    price_str = str(price_val)
            avail_url = offers.get("availability", "")
            availability = "in_stock" if "InStock" in avail_url else "out_of_stock"
            for img in data.get("image", []):
                if isinstance(img, str):
                    img_urls.append(_hires(img))
                elif isinstance(img, dict):
                    if u := img.get("url") or img.get("contentUrl"):
                        img_urls.append(_hires(u))
            break
        except (json.JSONDecodeError, AttributeError, StopIteration):
            continue

    # CSS fallbacks — Scrapling adaptive selectors auto-recover if class names change
    if not name:
        name = (
            page.css('h1::text').get() or
            page.css('[class*="product-name"]::text').get() or
            page.css('[class*="title"]::text').get() or
            ""
        ).strip()

    if not price_str:
        raw = (
            page.css('[class*="price"]::text').get() or
            page.css('[data-id*="price"]::text').get() or
            ""
        ).strip()
        price_str = raw or None

    if not description:
        description = (page.css('[class*="description"]::text').get() or "").strip()

    if not img_urls:
        img_urls = [
            _hires(src) for src in (
                page.css('img[src*="assets.hermes.com"]::attr(src)').getall() +
                page.css('img[data-src*="assets.hermes.com"]::attr(data-src)').getall()
            ) if src
        ]

    if not name:
        return None

    parsed = _parse_description(description or "")
    size_m = _SIZE_RE.search(name)

    return {
        "id":                 slug,
        "sku":                slug,
        "name":               name,
        "brand":              "Hermes",
        "model":              name,
        "price":              price_str,
        "description":        description or "",
        "listed_at":          datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_url":         url,
        "platform":           PLATFORM,
        "authenticity_label": "authentic",
        "condition":          "new",
        "availability":       availability or "in_stock",
        "product_ref":        product_ref,
        "bag_size":           size_m.group(1) if size_m else "",
        "image_urls":         img_urls,
        "local_images":       [],
        **parsed,
    }


async def _collect_product_urls(session: AsyncStealthySession, category_url: str) -> list[str]:
    try:
        page = await session.fetch(category_url)
    except Exception as e:
        print(f"  Warning: could not fetch {category_url}: {e}")
        return []

    hrefs = page.css('a[href*="/product/"]::attr(href)').getall()
    urls = set()
    for href in hrefs:
        full = href if href.startswith("http") else BASE_URL + href
        urls.add(full.split("?")[0].rstrip("/") + "/")
    return list(urls)


async def scrape(max_products: int = 200, categories: list[str] | None = None) -> None:
    if categories is None:
        categories = CATEGORIES
    META_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    saved = 0

    # AsyncStealthySession uses Camoufox (Firefox-based) with advanced fingerprint
    # spoofing. solve_cloudflare=True handles Cloudflare Turnstile/interstitial
    # challenges that hermes.com serves to automated browsers.
    async with AsyncStealthySession(
        headless=True,
        network_idle=True,
        solve_cloudflare=True,
    ) as session:

        # Warm up on the homepage first — acquires CF clearance cookies before
        # hitting category pages, same strategy as vestiaire.py and vinted.py.
        print(f"Loading homepage to acquire CF clearance… ({HOMEPAGE})")
        try:
            await session.fetch(HOMEPAGE)
        except Exception as e:
            print(f"  Warning: homepage warm-up failed: {e}")
        await asyncio.sleep(4)

        # Phase 1: collect product URLs from each category page
        print("\nDiscovering product URLs…")
        all_urls: list[str] = []
        for cat_url in categories:
            print(f"  {cat_url}")
            urls = await _collect_product_urls(session, cat_url)
            all_urls.extend(urls)
            print(f"    → {len(urls)} product links found")
            await asyncio.sleep(2)

        unique_urls = list(dict.fromkeys(all_urls))
        print(f"\n{len(unique_urls)} unique products found — scraping details…\n")

        # Phase 2: fetch and parse each product page
        with tqdm(total=min(max_products, len(unique_urls)), desc="Products") as pbar:
            for url in unique_urls:
                if saved >= max_products:
                    break

                slug = url.rstrip("/").rsplit("/", 1)[-1]
                if item_exists(conn, slug, PLATFORM):
                    pbar.update(1)
                    continue

                try:
                    page = await session.fetch(url)
                    product = _parse_product_page(page, url)
                except Exception as e:
                    tqdm.write(f"  error {slug}: {e}")
                    await asyncio.sleep(1)
                    continue

                if not product:
                    tqdm.write(f"  parse failed: {slug}")
                    continue

                upsert_item(conn, product)

                # Save rich JSON — leather_type, dimensions, etc. are not in DB schema
                json_path = META_DIR / f"{slug}.json"
                json_path.write_text(json.dumps(product, indent=2, ensure_ascii=False))

                saved += 1
                pbar.update(1)
                tqdm.write(f"  saved: {product['name']} — {product.get('price')}")
                await asyncio.sleep(1.5)

    conn.close()
    print(f"\nDone — {saved} new Hermès products saved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape authentic Hermès products from hermes.com/de/de/"
    )
    parser.add_argument("--max-products", type=int, default=200)
    parser.add_argument("--categories", nargs="+", default=None,
                        help="Override default category URLs")
    args = parser.parse_args()
    asyncio.run(scrape(max_products=args.max_products, categories=args.categories))
