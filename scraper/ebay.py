"""
eBay scraper — counterfeit Hermès bags.

Uses the eBay Finding API — authenticates with App ID only, no OAuth needed.

Auth: EBAY_APP_ID env var (GitHub Actions) or .env file (local).
      Never expires. No token management required.

Counterfeit signal: genuine Hermès Kelly/Birkin cost $5,000+ even secondhand.
Any eBay listing under $400 claiming to be Hermès is almost certainly fake.

Each item is saved as:
  data/ebay/metadata/eb_<item_id>.json  ← authenticity_label = "counterfeit"
"""

import argparse
import asyncio
import json
import os
import random
import re
from pathlib import Path

import httpx
from tqdm import tqdm

FINDING_API   = "https://svcs.ebay.com/services/search/FindingService/v1"
MAX_PRICE_USD = 400
SEARCH_QUERIES = ["hermes kelly bag", "hermes birkin bag"]

META_DIR = Path("data/ebay/metadata")
META_DIR.mkdir(parents=True, exist_ok=True)


def _load_app_id() -> str:
    app_id = os.environ.get("EBAY_APP_ID", "")
    if not app_id:
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("EBAY_APP_ID="):
                    app_id = line.split("=", 1)[1].strip()
    if not app_id:
        raise RuntimeError("EBAY_APP_ID not found. Add it to .env or set as environment variable.")
    return app_id


def _fullres(url: str) -> str:
    """Upscale eBay CDN thumbnail to 1600px."""
    url = url.replace("thumbs/images/", "images/")
    return re.sub(r"s-l\d+", "s-l1600", url)


def _search(app_id: str, query: str, page: int, per_page: int = 100) -> dict:
    params = {
        "OPERATION-NAME":              "findItemsByKeywords",
        "SERVICE-VERSION":             "1.0.0",
        "SECURITY-APPNAME":            app_id,
        "RESPONSE-DATA-FORMAT":        "JSON",
        "keywords":                    query,
        "paginationInput.entriesPerPage": per_page,
        "paginationInput.pageNumber":  page,
        "itemFilter(0).name":          "MaxPrice",
        "itemFilter(0).value":         MAX_PRICE_USD,
        "itemFilter(0).paramName":     "Currency",
        "itemFilter(0).paramValue":    "USD",
        "outputSelector":              "PictureURLLarge",
        "sortOrder":                   "StartTimeNewest",
    }
    with httpx.Client(timeout=20) as c:
        resp = c.get(FINDING_API, params=params)
        if not resp.is_success:
            print(f"  eBay API {resp.status_code}: {resp.text[:300]}")
        resp.raise_for_status()
        return resp.json()


def _val(field) -> str:
    """Unwrap eBay Finding API's nested single-element arrays."""
    if isinstance(field, list):
        return _val(field[0]) if field else ""
    if isinstance(field, dict):
        return field.get("__value__", field.get("value", ""))
    return str(field) if field is not None else ""


async def scrape(max_products: int = 500, queries: list[str] | None = None) -> None:
    app_id = _load_app_id()
    if queries is None:
        queries = SEARCH_QUERIES

    saved = 0
    with tqdm(total=max_products, desc="Products") as pbar:
        for query in queries:
            if saved >= max_products:
                break

            print(f"\n  Searching eBay: '{query}' (max ${MAX_PRICE_USD})")
            page = 1

            while saved < max_products:
                try:
                    data = _search(app_id, query, page)
                except httpx.HTTPStatusError as e:
                    tqdm.write(f"  API error (page {page}): {e}")
                    break

                response = data.get("findItemsByKeywordsResponse", [{}])[0]
                search_result = response.get("searchResult", [{}])[0]
                items = search_result.get("item", [])
                pagination = response.get("paginationOutput", [{}])[0]
                total_pages = int(_val(pagination.get("totalPages", [1])))

                if not items:
                    tqdm.write(f"  No more items for '{query}'")
                    break

                for item in items:
                    if saved >= max_products:
                        break

                    item_id = _val(item.get("itemId", ""))
                    if not item_id:
                        continue

                    meta_path = META_DIR / f"eb_{item_id}.json"
                    if meta_path.exists():
                        pbar.update(1)
                        continue

                    gallery = _val(item.get("galleryURL", ""))
                    large   = _val(item.get("pictureURLLarge", ""))
                    raw_url = large or gallery
                    if not raw_url:
                        continue
                    img_urls = [_fullres(raw_url)]

                    price_raw = item.get("sellingStatus", [{}])[0].get("currentPrice", [{}])[0]
                    try:
                        price_str = f"${float(_val(price_raw)):,.0f}"
                    except (ValueError, TypeError):
                        price_str = _val(price_raw)

                    condition = _val(item.get("condition", [{}])[0].get("conditionDisplayName", ""))
                    country   = _val(item.get("country", ""))
                    listed_at = _val(item.get("listingInfo", [{}])[0].get("startTime", ""))
                    source_url = _val(item.get("viewItemURL", ""))
                    title      = _val(item.get("title", ""))

                    product = {
                        "id":                 item_id,
                        "name":               title,
                        "brand":              "Hermès",
                        "price":              price_str,
                        "description":        "",
                        "condition":          condition,
                        "country":            country,
                        "listed_at":          listed_at,
                        "source_url":         source_url,
                        "platform":           "ebay.com",
                        "authenticity_label": "counterfeit",
                        "search_query":       query,
                        "image_urls":         img_urls,
                        "local_images":       [],
                    }
                    meta_path.write_text(json.dumps(product, indent=2))
                    saved += 1
                    pbar.update(1)
                    tqdm.write(f"  saved: {title[:60]} — {price_str}")

                    await asyncio.sleep(random.uniform(0.1, 0.3))

                if page >= total_pages:
                    break
                page += 1
                await asyncio.sleep(random.uniform(0.5, 1.0))

    print(f"\nDone — {saved} new products saved to {META_DIR}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape counterfeit Hermès bags from eBay")
    parser.add_argument("--queries", nargs="+", default=SEARCH_QUERIES)
    parser.add_argument("--max-products", type=int, default=500)
    args = parser.parse_args()
    asyncio.run(scrape(max_products=args.max_products, queries=args.queries))
