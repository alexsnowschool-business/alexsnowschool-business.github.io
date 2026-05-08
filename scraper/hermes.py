"""
Hermès scraper — authentic bags and accessories directly from hermes.com (DE locale).

Hermes category pages are server-side rendered and accessible via Googlebot UA + plain
httpx — no browser needed. Product detail pages return 403 (Cloudflare), but every
field we need (name, price, color, product ref) is already in the category listing HTML.

Each item saved as:
    platform = "hermes.com"
    authenticity_label = "authentic"
    condition = "new"

Image URLs are constructed from the slug and verified with a HEAD request before saving.
Not every color variant has a CDN photo — unverified URLs are dropped rather than saved
as broken links.
"""

import argparse
import asyncio
import json
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

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "de-DE,de;q=0.9",
}

_CDN_BASE    = "https://assets.hermes.com/is/image/hermesproduct"
_REF_RE      = re.compile(r"-([A-Z][0-9]{6}[A-Z0-9]{2,})/?$")
_SLUG_CDN_RE = re.compile(r"-([A-Z])([A-Z0-9]+)$")
_SIZE_RE     = re.compile(r"\b(\d{2})\b")
_DE_PRICE_RE = re.compile(r"([\d.,]+)\s*€")


def _candidate_image_url(slug: str) -> str:
    """Construct the Hermes CDN front-image URL from a slug (unverified)."""
    cdn_name = _SLUG_CDN_RE.sub(r"--\2", slug)
    return f"{_CDN_BASE}/{cdn_name}-front-wm-1-0-0-800-800_g.jpg"


async def _image_exists(client: httpx.AsyncClient, url: str) -> bool:
    """Return True only if the CDN URL resolves to a real image (HTTP 200)."""
    try:
        r = await client.head(url, timeout=8)
        return r.status_code == 200
    except Exception:
        return False


def _normalize_price(raw: str) -> str | None:
    m = _DE_PRICE_RE.search(raw)
    if not m:
        return raw.strip() or None
    num = m.group(1).strip()
    if "," in num:
        num = num.replace(".", "").replace(",", ".")
    elif re.search(r"\.\d{3}$", num):
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
            # image_urls filled in by _verify_and_attach_images after batch HEAD checks
            "image_urls":         [],
            "local_images":       [],
            "product_ref":        ref_m.group(1) if ref_m else "",
            "_candidate_img":     _candidate_image_url(slug),
        })

    return products


async def _verify_and_attach_images(
    client: httpx.AsyncClient, products: list[dict]
) -> None:
    """
    Batch-verify CDN image URLs and attach only the ones that return HTTP 200.
    Runs all HEAD requests concurrently so it adds minimal latency.
    """
    slugs = [p["id"] for p in products]
    urls  = [p.pop("_candidate_img") for p in products]
    results = await asyncio.gather(*[_image_exists(client, u) for u in urls])
    for product, url, ok in zip(products, urls, results):
        product["image_urls"] = [url] if ok else []


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
                tqdm.write(f"  → {len(products)} products found, verifying images…")

                # Batch-verify CDN images before saving — skips broken URLs
                await _verify_and_attach_images(client, products)
                verified = sum(1 for p in products if p["image_urls"])
                tqdm.write(f"  → {verified}/{len(products)} have verified images")

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


async def fix_images() -> None:
    """
    Re-probe every existing hermes item's image URL and clear ones that return non-200.
    Run this once to repair items saved before URL verification was added.
    """
    conn = connect()
    rows = conn.execute(
        "SELECT id, image_urls FROM items WHERE platform = ? AND image_urls != '[]'",
        (PLATFORM,),
    ).fetchall()

    slugs_and_urls = [
        (row["id"], json.loads(row["image_urls"])[0])
        for row in rows
        if json.loads(row["image_urls"])
    ]
    print(f"Probing {len(slugs_and_urls)} existing image URLs…")

    async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
        results = await asyncio.gather(
            *[_image_exists(client, url) for _, url in slugs_and_urls]
        )

    cleared = 0
    for (slug, _), ok in zip(slugs_and_urls, results):
        if not ok:
            conn.execute(
                "UPDATE items SET image_urls = '[]' WHERE id = ? AND platform = ?",
                (slug, PLATFORM),
            )
            cleared += 1

    conn.commit()
    conn.close()
    print(f"Cleared broken image URLs for {cleared}/{len(slugs_and_urls)} items")


def backfill_images_sync() -> None:
    """Construct and backfill image URLs for items that have none (no verification)."""
    conn = connect()
    rows = conn.execute(
        "SELECT id FROM items WHERE platform = ? AND image_urls = '[]'", (PLATFORM,)
    ).fetchall()
    updated = 0
    for row in rows:
        url = _candidate_image_url(row["id"])
        conn.execute(
            "UPDATE items SET image_urls = ? WHERE id = ? AND platform = ?",
            (json.dumps([url]), row["id"], PLATFORM),
        )
        updated += 1
    conn.commit()
    conn.close()
    print(f"Backfilled candidate image_urls for {updated} items (unverified)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape authentic Hermès products from hermes.com/de/de/"
    )
    parser.add_argument("--max-products", type=int, default=200)
    parser.add_argument("--categories", nargs="+", default=None)
    parser.add_argument("--fix-images", action="store_true",
                        help="Re-probe existing image URLs and clear broken ones")
    parser.add_argument("--backfill-images", action="store_true",
                        help="Construct image URLs for items with none (no verification)")
    args = parser.parse_args()

    if args.fix_images:
        asyncio.run(fix_images())
    elif args.backfill_images:
        backfill_images_sync()
    else:
        asyncio.run(scrape(max_products=args.max_products, categories=args.categories))
