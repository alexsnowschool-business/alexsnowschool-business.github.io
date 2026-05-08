"""
Hermès scraper — authentic bags and accessories directly from hermes.com (DE locale).

Hermes category pages are server-side rendered and accessible via Googlebot UA + plain
httpx — no browser needed. Product detail pages return 403 (Cloudflare), but every
field we need (name, price, color, product ref) is already in the category listing HTML.

Each item saved as:
    platform = "hermes.com"
    authenticity_label = "authentic"
    condition = "new"
"""

import argparse
import asyncio
import re
from datetime import datetime, timezone

import httpx
from scrapling.parser import Adaptor
from tqdm import tqdm

from scraper.db import connect, item_exists, upsert_item

PLATFORM = "hermes.com"
BASE_URL = "https://www.hermes.com"

CATEGORIES = [
    f"{BASE_URL}/de/de/category/lederwaren/taschen-und-kleine-taschen/taschen-und-kleine-taschen-fur-damen/",
    f"{BASE_URL}/de/de/category/lederwaren/taschen-und-kleine-taschen/taschen-und-kleine-taschen-fur-herren/",
    f"{BASE_URL}/de/de/category/lederwaren/kleinlederwaren/brieftaschen/",
    f"{BASE_URL}/de/de/category/lederwaren/kleinlederwaren/",
    f"{BASE_URL}/de/de/category/lederwaren/reisen/koffer-und-reisetaschen/",
]

# Googlebot UA is allowed — Hermes serves SSR HTML to crawlers
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "de-DE,de;q=0.9",
}

_REF_RE       = re.compile(r"-([A-Z][0-9]{6}[A-Z0-9]{2,})/?$")
_SIZE_RE      = re.compile(r"\b(\d{2})\b")
_DE_PRICE_RE  = re.compile(r"([\d.,]+)\s*€")


def _normalize_price(raw: str) -> str | None:
    """
    Convert German price string to €X,XXX format that db._price_value handles.
    German: dot = thousands separator, comma = decimal → "4.500 €" → "€4,500"
    """
    m = _DE_PRICE_RE.search(raw)
    if not m:
        return raw.strip() or None
    num = m.group(1).strip()
    if "," in num:
        # e.g. "4.500,50" → 4500.50
        num = num.replace(".", "").replace(",", ".")
    elif re.search(r"\.\d{3}$", num):
        # e.g. "4.500" → 4500 (dot is thousands separator)
        num = num.replace(".", "")
    try:
        value = float(num)
        if value == int(value):
            return f"€{int(value):,}"
        return f"€{value:,.2f}"
    except ValueError:
        return raw.strip() or None


def _parse_category_page(html: str, page_url: str) -> list[dict]:
    page = Adaptor(html, url=page_url)
    products = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for block in page.css("div.product-item-meta"):
        link = block.css("a.product-item-name")
        if not link:
            continue
        link = link[0]

        href = link.attrib.get("href", "")
        if not href:
            continue

        full_url = BASE_URL + href if not href.startswith("http") else href
        slug = full_url.rstrip("/").rsplit("/", 1)[-1]

        # title format: "Product Name, Color" or just "Product Name"
        title = link.attrib.get("title", "")
        if "," in title:
            name, color = title.split(",", 1)
            name  = name.strip()
            color = color.strip()
        else:
            name  = title.strip()
            color = ""

        if not name:
            name = link.css("span.product-title::text").get("").strip()
        if not name:
            continue

        # Price: strip the "Preis" sr-only label, keep the number + €
        price_parts = [
            t.strip() for t in block.css("span.price::text").getall()
            if t.strip() and t.strip().lower() != "preis"
        ]
        price = _normalize_price(" ".join(price_parts)) if price_parts else None

        ref_m  = _REF_RE.search(slug)
        size_m = _SIZE_RE.search(name)

        products.append({
            "id":                 slug,
            "platform":           PLATFORM,
            "name":               name,
            "brand":              "Hermes",
            "model":              name,
            "price":              price,
            "color":              color,
            "description":        "",
            "condition":          "new",
            "size":               size_m.group(1) if size_m else "",
            "listed_at":          now,
            "source_url":         full_url,
            "authenticity_label": "authentic",
            "image_urls":         [],
            "local_images":       [],
            "product_ref":        ref_m.group(1) if ref_m else "",
        })

    return products


async def _fetch_category(client: httpx.AsyncClient, url: str) -> list[dict]:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return _parse_category_page(resp.text, url)
    except Exception as e:
        print(f"  Warning: could not fetch {url}: {e}")
        return []


async def scrape(max_products: int = 20, categories: list[str] | None = None) -> None:
    if categories is None:
        categories = CATEGORIES

    conn  = connect()
    saved = 0

    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=True,
        headers=_HEADERS,
    ) as client:
        with tqdm(total=max_products, desc="Products") as pbar:
            for cat_url in categories:
                if saved >= max_products:
                    break

                tqdm.write(f"\nFetching: {cat_url}")
                products = await _fetch_category(client, cat_url)
                tqdm.write(f"  → {len(products)} products found")

                for product in products:
                    if saved >= max_products:
                        break
                    if item_exists(conn, product["id"], PLATFORM):
                        continue
                    upsert_item(conn, product)
                    saved += 1
                    pbar.update(1)
                    tqdm.write(f"  saved: {product['name']} — {product.get('price')}")

                await asyncio.sleep(1.0)

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
