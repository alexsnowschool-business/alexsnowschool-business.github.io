"""
eBay scraper — counterfeit Hermès bags.

Uses the eBay Browse API (no Playwright needed — clean REST API).

Auth: Bearer token via EBAY_APP_TOKEN env var (GitHub Actions) or .env file (local).
      The workflow auto-refreshes the token using EBAY_APP_ID + EBAY_CERT_ID.
      Locally: generate a token from developer.ebay.com and put it in .env.

Counterfeit signal: genuine Hermès Kelly/Birkin cost $5,000+ even secondhand.
Any eBay listing under $400 claiming to be Hermès is almost certainly fake.

Each item is saved as:
  data/ebay/metadata/eb_<item_id>.json  ← authenticity_label = "counterfeit"
"""

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
from pathlib import Path

import httpx
from tqdm import tqdm

BROWSE_API     = "https://api.ebay.com/buy/browse/v1/item_summary/search"
MAX_PRICE_USD  = 400
SEARCH_QUERIES = ["hermes kelly bag", "hermes birkin bag"]
MARKETPLACE    = "EBAY_US"

META_DIR = Path("data/ebay/metadata")
META_DIR.mkdir(parents=True, exist_ok=True)


def _load_token() -> str:
    # Environment variable first — set by GitHub Actions workflow
    token = os.environ.get("EBAY_APP_TOKEN")
    if token:
        return token
    # Fall back to .env file for local development
    env_file = Path(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("EBAY_APP_TOKEN="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(
        "EBAY_APP_TOKEN not found.\n"
        "Local: add EBAY_APP_TOKEN=Bearer <token> to .env\n"
        "CI: add EBAY_APP_ID + EBAY_CERT_ID as GitHub secrets (workflow auto-refreshes)."
    )


def _fullres(url: str) -> str:
    """Upscale eBay CDN thumbnail to 1600px."""
    return re.sub(r"s-l\d+", "s-l1600", url)


def _search(token: str, query: str, offset: int, limit: int = 50) -> dict:
    with httpx.Client(timeout=20) as c:
        resp = c.get(
            BROWSE_API,
            params={
                "q": query,
                "limit": limit,
                "offset": offset,
                "filter": f"price:[0..{MAX_PRICE_USD}],priceCurrency:USD",
            },
            headers={"Authorization": token, "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE},
        )
        if not resp.is_success:
            print(f"  eBay API {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        return resp.json()


async def scrape(max_products: int = 500, queries: list[str] | None = None) -> None:
    """Metadata-only scrape — saves JSON sidecars, no image downloads."""
    token = _load_token()
    if queries is None:
        queries = SEARCH_QUERIES

    saved = 0
    with tqdm(total=max_products, desc="Products") as pbar:
        for query in queries:
            if saved >= max_products:
                break

            print(f"\n  Searching eBay: '{query}' (max ${MAX_PRICE_USD})")
            offset = 0
            limit  = 50

            while saved < max_products:
                try:
                    data = _search(token, query, offset, limit)
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 401:
                        print("  Token expired or invalid — check EBAY_APP_TOKEN.")
                        return
                    tqdm.write(f"  API error (offset {offset}): {e}")
                    break

                items = data.get("itemSummaries", [])
                total = data.get("total", 0)

                if not items:
                    tqdm.write(f"  No more items for '{query}'")
                    break

                for item in items:
                    if saved >= max_products:
                        break

                    item_id = item.get("itemId", "").replace("|", "-")
                    if not item_id:
                        continue

                    meta_path = META_DIR / f"eb_{item_id}.json"
                    if meta_path.exists():
                        pbar.update(1)
                        continue

                    raw_imgs = []
                    if item.get("image"):
                        raw_imgs.append(item["image"]["imageUrl"])
                    for img in item.get("additionalImages") or []:
                        raw_imgs.append(img["imageUrl"])
                    img_urls = [_fullres(u) for u in raw_imgs if u]

                    if not img_urls:
                        continue

                    price     = item.get("price", {})
                    price_val = price.get("value", "")
                    price_cur = price.get("currency", "USD")
                    try:
                        price_str = f"${float(price_val):,.0f}" if price_cur == "USD" else f"{price_cur} {float(price_val):,.0f}"
                    except (ValueError, TypeError):
                        price_str = price_val

                    loc      = item.get("itemLocation", {})
                    listed_at = item.get("itemCreationDate") or item.get("itemOriginDate") or ""

                    product = {
                        "id":                 item_id,
                        "name":               item.get("title", ""),
                        "brand":              "Hermès",
                        "price":              price_str,
                        "description":        "",
                        "condition":          item.get("condition", ""),
                        "country":            loc.get("country", ""),
                        "listed_at":          listed_at,
                        "source_url":         item.get("itemWebUrl", ""),
                        "platform":           "ebay.com",
                        "authenticity_label": "counterfeit",
                        "search_query":       query,
                        "image_urls":         img_urls,
                        "local_images":       [],
                    }
                    meta_path.write_text(json.dumps(product, indent=2))
                    saved += 1
                    pbar.update(1)
                    tqdm.write(f"  saved: {product['name'][:60]} — {price_str}")

                    await asyncio.sleep(random.uniform(0.1, 0.4))

                offset += limit
                if offset >= total:
                    break
                await asyncio.sleep(random.uniform(0.5, 1.0))

    print(f"\nDone — {saved} new products saved to {META_DIR}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape counterfeit Hermès bags from eBay")
    parser.add_argument("--queries", nargs="+", default=SEARCH_QUERIES)
    parser.add_argument("--max-products", type=int, default=500)
    args = parser.parse_args()
    asyncio.run(scrape(max_products=args.max_products, queries=args.queries))
