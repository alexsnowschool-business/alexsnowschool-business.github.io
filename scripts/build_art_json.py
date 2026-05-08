"""
Rebuild art-archive/catalogue.json and art-archive/analysis.json from data/art.db.
Run after each scrape:  uv run python scripts/build_art_json.py
"""

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from scraper.art_db import connect, all_lots

OUT_DIR = Path("art-archive")


def _band_counts(values: list[float], edges: list[float]) -> list[int]:
    counts = [0] * (len(edges) - 1)
    for v in values:
        for i in range(len(edges) - 1):
            if edges[i] <= v < edges[i + 1]:
                counts[i] += 1
                break
    return counts


def build_analysis(lots: list[dict]) -> dict:
    hammer_prices: list[float] = []
    by_house: dict[str, list[float]]    = defaultdict(list)
    by_medium: dict[str, list[float]]   = defaultdict(list)
    by_perf: dict[str, int]             = defaultdict(int)
    by_year: dict[str, list[float]]     = defaultdict(list)
    artist_totals: dict[str, float]     = defaultdict(float)
    artist_counts: dict[str, int]       = defaultdict(int)
    above_below: list[dict]             = []

    for lot in lots:
        h = lot.get("hammer_usd") or lot.get("hammer_price") or 0
        if h <= 0:
            continue

        hammer_prices.append(h)
        house  = lot.get("auction_house") or "Unknown"
        medium = lot.get("medium_category") or "other"
        perf   = lot.get("sale_performance") or "unknown"
        artist = lot.get("artist") or "Unknown"

        by_house[house].append(h)
        by_medium[medium].append(h)
        by_perf[perf] += 1

        year = (lot.get("sale_date") or "")[:4]
        if year.isdigit():
            by_year[year].append(h)

        artist_totals[artist] += h
        artist_counts[artist] += 1

        low  = lot.get("estimate_low")
        high = lot.get("estimate_high")
        if low and high and h > 0:
            ratio = h / ((low + high) / 2)
            above_below.append({
                "id":      lot["id"],
                "artist":  artist,
                "title":   (lot.get("title") or "")[:50],
                "hammer":  round(h),
                "est_mid": round((low + high) / 2),
                "ratio":   round(ratio, 2),
                "perf":    perf,
                "house":   house,
                "img":     (lot.get("image_urls") or [""])[0],
                "url":     lot.get("source_url") or "",
            })

    def _stats(prices: list[float]) -> dict:
        if not prices:
            return {"count": 0, "min": 0, "max": 0, "median": 0, "mean": 0}
        return {
            "count":  len(prices),
            "min":    round(min(prices)),
            "max":    round(max(prices)),
            "median": round(statistics.median(prices)),
            "mean":   round(statistics.mean(prices)),
        }

    # Price tier edges (USD)
    tier_edges  = [0, 10_000, 100_000, 500_000, 1_000_000, 5_000_000, 50_000_000]
    tier_labels = ["<$10k", "$10k–100k", "$100k–500k", "$500k–1M", "$1M–5M", "$5M+"]

    # Top artists by total hammer value
    top_artists = sorted(artist_totals.items(), key=lambda x: x[1], reverse=True)[:20]
    top_artist_rows = [
        {
            "artist": a,
            "total":  round(v),
            "count":  artist_counts[a],
            "avg":    round(v / artist_counts[a]),
        }
        for a, v in top_artists
    ]

    # Performance breakdown by house
    house_perf: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for lot in lots:
        if lot.get("hammer_usd") and lot.get("hammer_usd", 0) > 0:
            house_perf[lot.get("auction_house") or "Unknown"][
                lot.get("sale_performance") or "unknown"
            ] += 1

    house_perf_rows = [
        {
            "house": h,
            "above": counts.get("above", 0),
            "within": counts.get("within", 0),
            "below":  counts.get("below", 0),
        }
        for h, counts in house_perf.items()
    ]

    # Sale year timeline
    all_years = sorted(by_year.keys())
    year_timeline = {
        "labels":  all_years,
        "medians": [round(statistics.median(by_year[y])) if by_year[y] else 0 for y in all_years],
        "counts":  [len(by_year[y]) for y in all_years],
    }

    # Notable lots (top outperformers relative to estimate)
    above_below.sort(key=lambda x: x["ratio"], reverse=True)

    medium_summary = {
        cat: _stats(prices)
        for cat, prices in by_medium.items() if prices
    }

    return {
        "total_lots":      len(lots),
        "total_with_price": len(hammer_prices),
        "total_images":    sum(len(lot.get("image_urls") or []) for lot in lots),
        "overall":         _stats(hammer_prices),
        "by_house":        {h: _stats(p) for h, p in by_house.items()},
        "by_medium":       medium_summary,
        "sale_performance": dict(by_perf),
        "tier_labels":     tier_labels,
        "tier_bands":      _band_counts(hammer_prices, tier_edges),
        "top_artists":     top_artist_rows,
        "house_perf_rows": house_perf_rows,
        "year_timeline":   year_timeline,
        "top_outperformers": above_below[:12],
    }


if __name__ == "__main__":
    print("Loading art lots from DB…")
    with connect() as conn:
        lots = all_lots(conn)
    print(f"  {len(lots)} lots loaded")

    OUT_DIR.mkdir(exist_ok=True)

    print("Writing catalogue.json…")
    (OUT_DIR / "catalogue.json").write_text(json.dumps(lots))

    print("Building analysis…")
    analysis = build_analysis(lots)
    (OUT_DIR / "analysis.json").write_text(json.dumps(analysis))

    priced = analysis["total_with_price"]
    print(f"Done — {len(lots)} lots ({priced} with hammer price)")
