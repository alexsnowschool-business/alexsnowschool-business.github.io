"""
Rebuild hermes-archive/catalogue.json and hermes-archive/analysis.json
from the SQLite database. Run after each scrape.
"""

import datetime
import re
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


def _band_counts(prices: list[float], edges: list[int]) -> list[int]:
    counts = [0] * (len(edges) - 1)
    for p in prices:
        for i in range(len(edges) - 1):
            if edges[i] <= p < edges[i + 1]:
                counts[i] += 1
                break
    return counts


def build_analysis(items: list[dict]) -> dict:
    auth_prices: list[float] = []
    fake_prices: list[float] = []
    by_source: dict[str, list[float]] = defaultdict(list)
    type_auth: dict[str, list[float]] = defaultdict(list)
    type_fake: dict[str, list[float]] = defaultdict(list)
    arbitrage: list[dict] = []

    for item in items:
        v = _price_value(item)
        if v <= 0:
            continue
        label    = item.get("authenticity_label", "")
        platform = item.get("platform", "unknown")
        bag      = _bag_type(item.get("name", ""))
        by_source[platform].append(v)
        if label == "authentic":
            auth_prices.append(v)
            type_auth[bag].append(v)
        else:
            fake_prices.append(v)
            type_fake[bag].append(v)
            if v >= 200:
                imgs = item.get("image_urls") or []
                arbitrage.append({
                    "name":      item.get("name", "—"),
                    "price":     item.get("price", "—"),
                    "price_val": v,
                    "platform":  platform,
                    "url":       item.get("source_url", ""),
                    "img":       imgs[0] if imgs else "",
                })

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

    coarse_edges = [0, 100, 250, 500, 1000, 2500, 5000, 10000, 20000, 50000]
    band_labels  = [f"€{coarse_edges[i]:,}–{coarse_edges[i+1]:,}" for i in range(len(coarse_edges) - 1)]

    all_types = sorted(set(list(type_auth.keys()) + list(type_fake.keys())))
    type_rows = []
    for t in all_types:
        a, f = type_auth.get(t, []), type_fake.get(t, [])
        if not a and not f:
            continue
        type_rows.append({
            "type":       t,
            "auth_count": len(a),
            "auth_avg":   round(statistics.mean(a)) if a else 0,
            "fake_count": len(f),
            "fake_avg":   round(statistics.mean(f)) if f else 0,
            "spread":     round(statistics.mean(a) - statistics.mean(f)) if a and f else None,
        })
    type_rows.sort(key=lambda r: r["auth_avg"], reverse=True)

    source_summary = {
        src: {
            "count":  len(prices),
            "median": round(statistics.median(prices)),
            "mean":   round(statistics.mean(prices)),
        }
        for src, prices in by_source.items() if prices
    }

    arbitrage.sort(key=lambda x: x["price_val"], reverse=True)

    total_auth_c = sum(len(v) for v in type_auth.values())
    total_fake_c = sum(len(v) for v in type_fake.values())
    concentration = []
    for t in all_types:
        a_c, f_c = len(type_auth.get(t, [])), len(type_fake.get(t, []))
        if a_c + f_c < 2:
            continue
        concentration.append({
            "type":       t,
            "auth_pct":   round(a_c / total_auth_c * 100, 1) if total_auth_c else 0,
            "fake_pct":   round(f_c / total_fake_c * 100, 1) if total_fake_c else 0,
            "auth_count": a_c,
            "fake_count": f_c,
        })
    concentration.sort(key=lambda x: x["fake_pct"], reverse=True)

    compression_rows = []
    for t in all_types:
        a, f = type_auth.get(t, []), type_fake.get(t, [])
        if not a or not f:
            continue
        compression_rows.append({
            "type":     t,
            "ratio":    round(statistics.mean(a) / statistics.mean(f), 1),
            "auth_avg": round(statistics.mean(a)),
            "fake_avg": round(statistics.mean(f)),
        })
    compression_rows.sort(key=lambda x: x["ratio"], reverse=True)

    auth_fine_edges = list(range(0, 42001, 2000))
    auth_fine_labels = [f"€{auth_fine_edges[i]//1000}k" for i in range(len(auth_fine_edges) - 1)]
    psych_edges  = list(range(0, 526, 25))
    psych_labels = [f"€{psych_edges[i]}" for i in range(len(psych_edges) - 1)]

    top2_fake_pct  = sum(c["fake_pct"] for c in concentration[:2])
    top2_auth_pct  = sum(c["auth_pct"] for c in concentration[:2])
    top_compression = compression_rows[0] if compression_rows else {"type": "—", "ratio": 0}

    fake_by_platform: dict[str, list[float]] = defaultdict(list)
    for item in items:
        if item.get("authenticity_label") != "counterfeit":
            continue
        plat = item.get("platform", "unknown")
        v = _price_value(item)
        if v > 0:
            fake_by_platform[plat].append(v)

    fake_platform_stats = {
        plat: {
            "count":  len(prices),
            "median": round(statistics.median(prices)),
            "mean":   round(statistics.mean(prices)),
            "min":    round(min(prices)),
            "max":    round(max(prices)),
        }
        for plat, prices in fake_by_platform.items() if prices
    }

    ebay_conditions = Counter(
        item.get("condition", "")
        for item in items
        if item.get("platform") == "ebay.com" and item.get("condition")
    )
    ebay_countries = Counter(
        item.get("country", "")
        for item in items
        if item.get("platform") == "ebay.com" and item.get("country")
    )
    ebay_total = sum(1 for item in items if item.get("platform") == "ebay.com")

    TEXT_FIELDS = ["description", "condition", "size", "color", "listed_at", "model", "colors", "country"]
    COUNTRY_CODES = {
        "FR": "France", "US": "United States", "GB": "United Kingdom",
        "DE": "Germany", "IT": "Italy", "CH": "Switzerland",
        "BE": "Belgium", "NL": "Netherlands", "ES": "Spain",
        "AT": "Austria", "JP": "Japan", "HK": "Hong Kong", "AU": "Australia",
    }

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

    model_counts = Counter(
        item["model"] for item in items
        if item.get("model") and item.get("authenticity_label") == "authentic"
    )
    country_raw = Counter(
        item["country"] for item in items
        if item.get("country") and item.get("authenticity_label") == "authentic"
    )
    condition_counts = Counter(
        item["condition"] for item in items
        if item.get("condition") and item.get("authenticity_label") == "counterfeit"
    )

    def _desc_stats(label: str) -> dict:
        lengths = [
            len(item["description"]) for item in items
            if item.get("description") and item.get("authenticity_label") == label
        ]
        if not lengths:
            return {"count": 0, "mean": 0, "median": 0}
        return {
            "count":  len(lengths),
            "mean":   round(statistics.mean(lengths)),
            "median": round(statistics.median(lengths)),
        }

    monthly_auth: Counter = Counter()
    monthly_fake: Counter = Counter()
    for item in items:
        la = item.get("listed_at")
        if not la:
            continue
        try:
            if isinstance(la, (int, float)) and la > 0:
                dt = datetime.datetime.fromtimestamp(la, tz=datetime.timezone.utc)
            else:
                dt = datetime.datetime.fromisoformat(str(la).replace("Z", "+00:00"))
            key = dt.strftime("%Y-%m")
            if item.get("authenticity_label") == "authentic":
                monthly_auth[key] += 1
            else:
                monthly_fake[key] += 1
        except Exception:
            pass

    all_months = sorted(set(list(monthly_auth) + list(monthly_fake)))
    total_with_metadata = sum(1 for item in items if any(item.get(f) for f in TEXT_FIELDS))

    return {
        "auth":            _stats(auth_prices),
        "fake":            _stats(fake_prices),
        "band_labels":     band_labels,
        "auth_bands":      _band_counts(auth_prices, coarse_edges),
        "fake_bands":      _band_counts(fake_prices, coarse_edges),
        "type_rows":       type_rows,
        "source_summary":  source_summary,
        "arbitrage":       arbitrage[:20],
        "total_items":     len(items),
        "total_images":    sum(len(i.get("image_urls", [])) for i in items),
        "concentration":   concentration[:12],
        "compression_rows": compression_rows,
        "auth_fine_labels": auth_fine_labels,
        "auth_fine_bands":  _band_counts(auth_prices, auth_fine_edges),
        "psych_labels":    psych_labels,
        "psych_bands":     _band_counts(fake_prices, psych_edges),
        "img_kb_auth":     0,
        "img_kb_fake":     0,
        "img_count_auth":  0,
        "img_count_fake":  0,
        "top2_fake_pct":   top2_fake_pct,
        "top2_auth_pct":   top2_auth_pct,
        "top_compression": top_compression,
        "fake_platform_stats":   fake_platform_stats,
        "top_ebay_conditions":   [{"condition": k, "count": v} for k, v in ebay_conditions.most_common(10)],
        "top_ebay_countries":    [{"country": k, "count": v} for k, v in ebay_countries.most_common(10)],
        "ebay_total":      ebay_total,
        "ebay_stats":      fake_platform_stats.get("ebay.com", {}),
        "vinted_stats":    fake_platform_stats.get("vinted.de", {}),
        "coverage_rows":   coverage_rows,
        "top_models":      [{"model": m, "count": c} for m, c in model_counts.most_common(12)],
        "top_countries":   [{"country": COUNTRY_CODES.get(str(k), str(k)), "count": v} for k, v in country_raw.most_common(10)],
        "top_conditions":  [{"condition": k, "count": v} for k, v in condition_counts.most_common(8)],
        "desc_auth":       _desc_stats("authentic"),
        "desc_fake":       _desc_stats("counterfeit"),
        "timeline": {
            "labels": all_months,
            "auth":   [monthly_auth.get(m, 0) for m in all_months],
            "fake":   [monthly_fake.get(m, 0) for m in all_months],
        },
        "total_with_metadata": total_with_metadata,
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

    auth = analysis["auth"]["count"]
    fake = analysis["fake"]["count"]
    print(f"Done — {len(items)} items ({auth} authentic, {fake} counterfeit)")
