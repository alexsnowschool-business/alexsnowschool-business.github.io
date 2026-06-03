"""
Vestiaire Collective scraper — authenticated pre-owned Hermès bags.

Vestiaire authenticates every item before listing, making all listings
a valid authentic source. The site uses Cloudflare, so we:
  1. Load the homepage with Playwright to obtain CF clearance cookies
  2. Call the internal search API via page.evaluate() (browser's TLS stack)

Each item is saved as:
  data/vestiaire/metadata/vc_<id>.json  ← authenticity_label = "authentic"
"""

import argparse
import asyncio
import json
import random
import re
import uuid
from datetime import datetime, timezone

from playwright.async_api import async_playwright
from tqdm import tqdm

from scraper.db import connect, item_exists, upsert_item

BASE_URL = "https://us.vestiairecollective.com"
IMAGE_BASE = "https://images.vestiairecollective.com/images/resized/w=2000,q=90,f=auto,"
SEARCH_API = "https://search.vestiairecollective.com/v1/product/search"
MAX_IMAGES_PER_PRODUCT = 10
PLATFORM = "vestiairecollective.com"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _build_payload(offset: int, limit: int, query: str = "hermes bag") -> dict:
    return {
        "pagination": {"offset": offset, "limit": limit},
        "fields": [
            "name", "description", "brand", "model", "country", "price",
            "link", "sold", "pictures", "colors", "universeId", "createdAt",
        ],
        "facets": {"fields": ["brand"], "stats": ["price"]},
        "q": query,
        "sortBy": "relevance",
        "filters": {},
        "locale": {"country": "US", "currency": "USD", "language": "en", "sizeType": "US"},
        "options": {
            "innerFeedContext": "genericPLP",
            "disableHierarchicalParentFiltering": True,
            "enableGuidedSearch": True,
        },
        "recentlyViewedProductIDs": [],
        "mySizes": None,
    }


def _product_id(link: str) -> str | None:
    m = re.search(r"-(\d+)\.shtml$", link)
    return m.group(1) if m else None


def _candidate_image_urls(link: str) -> list[str]:
    stem = re.sub(r"\.shtml$", "", link.rsplit("/", 1)[-1])
    return [
        f"{IMAGE_BASE}/produit/{stem}-{i}_1.jpg"
        for i in range(1, MAX_IMAGES_PER_PRODUCT + 1)
    ]


async def scrape(max_products: int = 200, query: str = "hermes bag") -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            viewport={"width": 1280, "height": 900},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        print(f"Loading Vestiaire Collective (obtaining CF clearance)... query='{query}'")
        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(4)

        conn  = connect()
        saved = 0
        offset = 0
        limit = 60

        with tqdm(total=max_products, desc="Products") as pbar:
            while saved < max_products:
                payload = _build_payload(offset, limit, query)
                payload_json = json.dumps(payload)

                result = None
                for attempt in range(3):
                    result = await page.evaluate(f"""
                        async () => {{
                            try {{
                                const resp = await fetch('{SEARCH_API}', {{
                                    method: 'POST',
                                    headers: {{
                                        'accept': 'application/json',
                                        'content-type': 'application/json',
                                        'x-usecase': 'plpStandard',
                                        'x-deviceid': '{uuid.uuid4()}',
                                        'x-search-query-id': '{uuid.uuid4()}',
                                        'x-search-session-id': '{uuid.uuid4()}',
                                        'x-userid': '',
                                    }},
                                    body: JSON.stringify({payload_json})
                                }});
                                if (!resp.ok) {{
                                    return {{ __error: resp.status, __body: (await resp.text()).slice(0, 300) }};
                                }}
                                return await resp.json();
                            }} catch (e) {{
                                return {{ __error: e.message }};
                            }}
                        }}
                    """)
                    if "__error" not in result:
                        break
                    print(f"  attempt {attempt + 1} failed: {result['__error']} {result.get('__body', '')} — retrying in 10s...")
                    await asyncio.sleep(10)

                if "__error" in result:
                    print(f"All fetch attempts failed, stopping.")
                    break

                items = result.get("items", [])
                if not items:
                    print("No more items returned.")
                    break

                total_hits = result.get("paginationStats", {}).get("totalHits", 0)

                for item in items:
                    if saved >= max_products:
                        break

                    link = item.get("link", "")
                    product_id = _product_id(link)
                    if not product_id:
                        continue

                    if item_exists(conn, product_id, PLATFORM):
                        pbar.update(1)
                        continue

                    candidate_urls = _candidate_image_urls(link)

                    price_cents = item.get("price", {}).get("cents")
                    price_str = f"${price_cents / 100:,.0f}" if price_cents else None

                    model = item.get("model") or {}
                    raw_colors = item.get("colors") or []
                    if isinstance(raw_colors, dict):
                        raw_colors = raw_colors.get("all") or []
                    colors = [
                        c.get("name") if isinstance(c, dict) else str(c)
                        for c in raw_colors
                        if (c.get("name") if isinstance(c, dict) else c)
                    ]

                    listed_at_raw = item.get("createdAt") or ""
                    if isinstance(listed_at_raw, (int, float)) and listed_at_raw > 0:
                        listed_at = datetime.fromtimestamp(listed_at_raw, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    else:
                        listed_at = str(listed_at_raw) if listed_at_raw else ""

                    product = {
                        "id": product_id,
                        "name": item.get("name"),
                        "brand": item.get("brand", {}).get("name") if isinstance(item.get("brand"), dict) else item.get("brand"),
                        "model": model.get("name") if isinstance(model, dict) else (str(model) if model else ""),
                        "price": price_str,
                        "colors": colors,
                        "country": item.get("country", {}).get("name") if isinstance(item.get("country"), dict) else item.get("country"),
                        "description": item.get("description") or "",
                        "listed_at": listed_at,
                        "source_url": BASE_URL + link,
                        "platform": PLATFORM,
                        "authenticity_label": "authentic",
                        "image_urls": candidate_urls,
                        "local_images": [],
                    }
                    upsert_item(conn, product)
                    saved += 1
                    pbar.update(1)
                    tqdm.write(f"  saved: {product['name']} — {price_str}")

                    await asyncio.sleep(random.uniform(0.2, 0.6))

                offset += limit
                if offset >= total_hits:
                    break

                await asyncio.sleep(random.uniform(1.0, 2.0))

        conn.close()
        await browser.close()
        print(f"\nDone — saved {saved} products to DB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape authentic Hermès bags from Vestiaire Collective")
    parser.add_argument("--query", default="hermes bag")
    parser.add_argument("--max-products", type=int, default=200)
    args = parser.parse_args()
    asyncio.run(scrape(max_products=args.max_products, query=args.query))
