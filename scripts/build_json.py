"""
Rebuild hermes-archive/catalogue.json and hermes-archive/analysis.json
from the SQLite database. Run after each scrape.

Analytics focus: resale market — supply, pricing, provenance, geography.
"""

import datetime
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from scraper.db import connect, all_items

OUT_DIR = Path("hermes-archive")


def _price_value(item: dict) -> float:
    return item.get("price_value") or -1.0


def load_items() -> list[dict]:
    with connect() as conn:
        return all_items(conn)


BAG_TYPES = [
    "birkin", "kelly", "constance", "lindy", "evelyne", "picotin",
    "bolide", "herbag", "garden party", "roulis", "geta", "in the loop",
    "collier", "sabot", "steeple", "arcon", "faubourg", "della cavalleria",
]


def _bag_type(name: str) -> str:
    n = (name or "").lower()
    for t in BAG_TYPES:
        if t in n:
            return t.title()
    return "Other"


def _stats(prices: list[float]) -> dict:
    if not prices:
        return {"count": 0, "min": 0, "max": 0, "median": 0, "mean": 0}
    s = sorted(prices)
    return {
        "count":  len(s),
        "min":    round(min(s)),
        "max":    round(max(s)),
        "median": round(statistics.median(s)),
        "mean":   round(statistics.mean(s)),
    }


def _band_counts(prices: list[float], edges: list[int]) -> list[int]:
    counts = [0] * (len(edges) - 1)
    for p in prices:
        for i in range(len(edges) - 1):
            if edges[i] <= p < edges[i + 1]:
                counts[i] += 1
                break
    return counts


def build_analysis(items: list[dict]) -> dict:
    priced = [item for item in items if _price_value(item) > 0]
    prices = [_price_value(item) for item in priced]

    BRAND_ALIASES = {
        "hermes": "Hermès", "hermès": "Hermès",
        "delvaux": "Delvaux", "valextra": "Valextra",
        "loro piana": "Loro Piana", "moynat": "Moynat",
    }

    def _normalise_brand(raw: str) -> str:
        key = raw.strip().lower()
        return BRAND_ALIASES.get(key, raw.strip())

    # ── By brand ────────────────────────────────────────────────────────────
    brand_prices: dict[str, list[float]] = defaultdict(list)
    for item in priced:
        brand = _normalise_brand(item.get("brand") or "Unknown")
        brand_prices[brand].append(_price_value(item))

    brand_rows = sorted(
        [
            {
                "brand":  brand,
                "count":  len(pp),
                "median": round(statistics.median(pp)),
                "mean":   round(statistics.mean(pp)),
                "min":    round(min(pp)),
                "max":    round(max(pp)),
            }
            for brand, pp in brand_prices.items() if pp
        ],
        key=lambda r: r["count"],
        reverse=True,
    )

    # ── By model (Hermès bag type or raw model field) ────────────────────────
    model_prices: dict[str, list[float]] = defaultdict(list)
    for item in priced:
        brand = (item.get("brand") or "").lower()
        if "herm" in brand:
            model = _bag_type(item.get("name", ""))
        else:
            model = (item.get("model") or "Other").strip() or "Other"
        model_prices[model].append(_price_value(item))

    model_rows = sorted(
        [
            {
                "model":  model,
                "count":  len(pp),
                "median": round(statistics.median(pp)),
                "mean":   round(statistics.mean(pp)),
            }
            for model, pp in model_prices.items() if len(pp) >= 2
        ],
        key=lambda r: r["count"],
        reverse=True,
    )[:20]

    # ── By platform ─────────────────────────────────────────────────────────
    platform_prices: dict[str, list[float]] = defaultdict(list)
    for item in priced:
        platform_prices[item.get("platform", "unknown")].append(_price_value(item))

    platform_rows = sorted(
        [
            {
                "platform": plat,
                "count":    len(pp),
                "median":   round(statistics.median(pp)),
                "mean":     round(statistics.mean(pp)),
            }
            for plat, pp in platform_prices.items() if pp
        ],
        key=lambda r: r["count"],
        reverse=True,
    )

    # ── Geographic supply ────────────────────────────────────────────────────
    COUNTRY_CODES = {
        "FR": "France", "US": "United States", "GB": "United Kingdom",
        "DE": "Germany", "IT": "Italy", "CH": "Switzerland",
        "BE": "Belgium", "NL": "Netherlands", "ES": "Spain",
        "AT": "Austria", "JP": "Japan", "HK": "Hong Kong", "AU": "Australia",
        "CN": "China", "KR": "Korea", "CA": "Canada",
    }
    country_raw = Counter(
        item["country"] for item in items if item.get("country")
    )
    top_countries = [
        {"country": COUNTRY_CODES.get(str(k), str(k)), "count": v}
        for k, v in country_raw.most_common(12)
    ]

    # ── Price distribution ───────────────────────────────────────────────────
    band_edges  = [0, 500, 1000, 2000, 3000, 5000, 8000, 12000, 20000, 50000]
    band_labels = [f"€{band_edges[i]:,}–€{band_edges[i+1]:,}" for i in range(len(band_edges) - 1)]

    fine_edges  = list(range(0, 42001, 2000))
    fine_labels = [f"€{fine_edges[i]//1000}k" for i in range(len(fine_edges) - 1)]

    # ── Listing timeline ─────────────────────────────────────────────────────
    monthly: Counter = Counter()
    for item in items:
        la = item.get("listed_at")
        if not la:
            continue
        try:
            if isinstance(la, (int, float)) and la > 0:
                dt = datetime.datetime.fromtimestamp(la, tz=datetime.timezone.utc)
            else:
                dt = datetime.datetime.fromisoformat(str(la).replace("Z", "+00:00"))
            monthly[dt.strftime("%Y-%m")] += 1
        except Exception:
            pass
    all_months = sorted(monthly)

    # ── Metadata coverage ────────────────────────────────────────────────────
    TEXT_FIELDS = ["description", "condition", "size", "color", "listed_at", "model", "country"]
    platform_totals: dict[str, int] = defaultdict(int)
    platform_field_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for item in items:
        plat = item.get("platform", "unknown")
        platform_totals[plat] += 1
        for field in TEXT_FIELDS:
            v = item.get(field)
            if v and v != "" and v != [] and v != {}:
                platform_field_counts[plat][field] += 1

    coverage_rows = [
        {
            "platform": plat,
            "total":    total,
            "fields": {
                f: {
                    "count": platform_field_counts[plat].get(f, 0),
                    "pct":   round(platform_field_counts[plat].get(f, 0) * 100 / total) if total else 0,
                }
                for f in TEXT_FIELDS
            },
        }
        for plat, total in sorted(platform_totals.items())
    ]

    # ── Description length ───────────────────────────────────────────────────
    desc_lengths = [len(item["description"]) for item in items if item.get("description")]
    desc_stats = {
        "count":  len(desc_lengths),
        "mean":   round(statistics.mean(desc_lengths)) if desc_lengths else 0,
        "median": round(statistics.median(desc_lengths)) if desc_lengths else 0,
    }

    # ── Colour supply (top 10 colours across all brands) ─────────────────────
    color_counts: Counter = Counter()
    for item in items:
        colors = item.get("colors") or []
        if isinstance(colors, str):
            try:
                import json
                colors = json.loads(colors)
            except Exception:
                colors = [colors]
        for c in colors:
            if c:
                color_counts[str(c).strip()] += 1

    top_colors = [{"color": k, "count": v} for k, v in color_counts.most_common(12)]

    total_with_metadata = sum(
        1 for item in items if any(item.get(f) for f in TEXT_FIELDS)
    )

    return {
        "total_items":          len(items),
        "total_images":         sum(len(i.get("image_urls", [])) for i in items),
        "total_with_metadata":  total_with_metadata,
        "price_stats":          _stats(prices),
        "band_labels":          band_labels,
        "price_bands":          _band_counts(prices, band_edges),
        "fine_labels":          fine_labels,
        "fine_bands":           _band_counts(prices, fine_edges),
        "brand_rows":           brand_rows,
        "model_rows":           model_rows,
        "platform_rows":        platform_rows,
        "top_countries":        top_countries,
        "top_colors":           top_colors,
        "coverage_rows":        coverage_rows,
        "desc_stats":           desc_stats,
        "timeline": {
            "labels": all_months,
            "counts": [monthly.get(m, 0) for m in all_months],
        },
    }


if __name__ == "__main__":
    import json

    print("Loading items from DB…")
    items = load_items()
    print(f"  {len(items)} items loaded")

    print("Writing catalogue.json…")
    (OUT_DIR / "catalogue.json").write_text(json.dumps(items))

    print("Building analysis…")
    analysis = build_analysis(items)
    (OUT_DIR / "analysis.json").write_text(json.dumps(analysis))

    ps = analysis["price_stats"]
    print(f"Done — {len(items)} items · median €{ps['median']:,} · {len(analysis['brand_rows'])} brands")
