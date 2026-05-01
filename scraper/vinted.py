"""
Vinted scraper — counterfeit Hermès bags.

Vinted has light bot protection (Cloudflare). Strategy:
  1. Load the catalog search page with Playwright to acquire CF clearance cookies
  2. Call the internal catalog API via page.evaluate() (browser's TLS stack)

Labelling rationale: genuine Hermès Kelly/Birkin bags cost €5,800+ even
second-hand (authenticated resale). Any Vinted listing under €500 claiming
to be Hermès is counterfeit. We filter server-side with price_to=500.

Domain: vinted.de — far more European listings than vinted.com (770 vs 6).

Each item is saved as:
  data/vinted/metadata/vt_<id>.json  ← authenticity_label = "counterfeit"
"""

import argparse
import asyncio
import json
import random
from pathlib import Path

from playwright.async_api import async_playwright
from tqdm import tqdm

BASE_URL = "https://www.vinted.de"
SEARCH_QUERIES = ["hermes kelly", "hermes birkin"]
MAX_PRICE_EUR = 500

META_DIR = Path("data/vinted/metadata")
META_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _build_search_url(query: str, page: int, per_page: int = 96) -> str:
    params = (
        f"search_text={query.replace(' ', '+')}"
        f"&per_page={per_page}"
        f"&page={page}"
        f"&price_to={MAX_PRICE_EUR}"
        f"&order=newest_first"
    )
    return f"{BASE_URL}/api/v2/catalog/items?{params}"


async def _fetch_page(api_url: str, page) -> dict:
    result = await page.evaluate(f"""
        async () => {{
            const resp = await fetch('{api_url}', {{
                headers: {{
                    'accept': 'application/json',
                    'x-requested-with': 'XMLHttpRequest',
                }}
            }});
            if (!resp.ok) return {{}};
            return await resp.json();
        }}
    """)
    return result or {}


def _parse_price(item: dict) -> str | None:
    price = item.get("price", {})
    amount = price.get("amount")
    currency = price.get("currency_code", "EUR")
    if not amount:
        return None
    try:
        value = float(amount)
        if value == int(value):
            return f"€{int(value):,}" if currency == "EUR" else f"{currency}{int(value):,}"
        return f"€{value:,.2f}" if currency == "EUR" else f"{currency}{value:,.2f}"
    except ValueError:
        return str(amount)


async def scrape(max_products: int = 500, queries: list[str] | None = None) -> None:
    if queries is None:
        queries = SEARCH_QUERIES
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
            locale="de-DE",
            viewport={"width": 1280, "height": 900},
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        browser_page = await context.new_page()

        seed_query = queries[0].replace(" ", "+")
        print(f"Loading Vinted catalog (obtaining CF clearance)... queries={queries}")
        await browser_page.goto(
            f"{BASE_URL}/catalog?search_text={seed_query}",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        await asyncio.sleep(4)

        saved = 0

        with tqdm(total=max_products, desc="Products") as pbar:
            for query in queries:
                if saved >= max_products:
                    break

                api_page = 1
                print(f"\n  Searching: '{query}' (max price €{MAX_PRICE_EUR})")

                while saved < max_products:
                    api_url = _build_search_url(query, api_page)
                    data = await _fetch_page(api_url, browser_page)

                    items = data.get("items", [])
                    if not items:
                        tqdm.write(f"  No more items for '{query}'")
                        break

                    pagination = data.get("pagination", {})
                    total_pages = pagination.get("total_pages", 1)

                    for item in items:
                        if saved >= max_products:
                            break

                        item_id = str(item.get("id", ""))
                        if not item_id:
                            continue

                        meta_path = META_DIR / f"vt_{item_id}.json"
                        if meta_path.exists():
                            pbar.update(1)
                            continue

                        photos = item.get("photos", [])
                        img_urls = [
                            photo["full_size_url"]
                            for photo in photos
                            if photo.get("full_size_url")
                        ]
                        if not img_urls:
                            continue

                        price_str = _parse_price(item)
                        item_path = item.get("path") or f"/items/{item_id}"

                        product = {
                            "id": item_id,
                            "name": item.get("title"),
                            "brand": item.get("brand_title") or "Hermès",
                            "price": price_str,
                            "description": item.get("description") or "",
                            "condition": item.get("status") or "",
                            "size": item.get("size_title") or "",
                            "color": item.get("colour1") or "",
                            "listed_at": item.get("created_at_ts") or "",
                            "source_url": BASE_URL + item_path,
                            "platform": "vinted.de",
                            "authenticity_label": "counterfeit",
                            "search_query": query,
                            "image_urls": img_urls,
                            "local_images": [],
                        }
                        meta_path.write_text(json.dumps(product, indent=2))
                        saved += 1
                        pbar.update(1)
                        tqdm.write(f"  saved: {product['name']} — {price_str}")

                        await asyncio.sleep(random.uniform(0.5, 1.2))

                    if api_page >= total_pages:
                        break
                    api_page += 1
                    await asyncio.sleep(random.uniform(1.0, 2.5))

        await browser.close()
        print(f"\nDone — saved {saved} counterfeit products to {META_DIR}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape counterfeit Hermès bags from Vinted")
    parser.add_argument("--queries", nargs="+", default=SEARCH_QUERIES)
    parser.add_argument("--max-products", type=int, default=500)
    args = parser.parse_args()
    asyncio.run(scrape(max_products=args.max_products, queries=args.queries))
