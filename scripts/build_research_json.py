"""
Rebuild art-research/research.json from data/art.db.

Merges live auction statistics with curated biographical profiles stored
in the artist_profiles table of art.db.
Artists without a profile entry appear with dataset stats only.

Run after each scrape:  uv run python scripts/build_research_json.py
"""

import json
import re
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

from scraper.art_db import connect, all_lots, all_artist_profiles

OUT_PATH = Path("art-research/research.json")

_STRIP_DATES = re.compile(
    r"\s*\("
    r"(?:b\.\s*\d{4}|B\.\s*\d{4}|\d{4}\s*[-–]\s*(?:\d{4}|present)|\d{4})"
    r"\)\s*$",
    re.IGNORECASE,
)


def _normalize(name: str) -> str:
    """Uppercase artist name, strip trailing date parentheticals."""
    return _STRIP_DATES.sub("", name).upper().strip()


def _fmt_usd(v: float) -> str:
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}k"
    return f"${v:.0f}"


def build_research(lots: list[dict], profiles: dict) -> dict:
    artist_lots: dict[str, list[dict]] = defaultdict(list)
    for lot in lots:
        artist = lot.get("artist")
        if artist:
            artist_lots[_normalize(artist)].append(lot)

    hero_hammers = [l["hammer_usd"] for l in lots if l.get("hammer_usd")]
    above = sum(1 for l in lots if l.get("sale_performance") == "above")
    total_perf = sum(1 for l in lots if l.get("sale_performance") in ("above", "within", "below"))
    sources = sorted({l["auction_house"] for l in lots if l.get("auction_house")})

    ratios = []
    for l in lots:
        lo, hi = l.get("estimate_low"), l.get("estimate_high")
        h = l.get("hammer_usd")
        if lo and hi and h:
            ratios.append(h / ((lo + hi) / 2))

    stats = {
        "total_lots":      len(lots),
        "total_artists":   len(artist_lots),
        "median_hammer_usd": round(statistics.median(hero_hammers)) if hero_hammers else 0,
        "pct_above_estimate": round(100 * above / total_perf, 1) if total_perf else 0,
        "max_ratio":       round(max(ratios), 1) if ratios else 0,
        "sources":         sources,
        "generated_at":    date.today().isoformat(),
    }

    artist_rows = []

    # Build a dict: normalized_name -> profile entry (may be None)
    all_norm_names = set(artist_lots.keys())
    # Also include all profile names (so curated artists without DB lots still appear)
    # but we only emit artists that appear in the DB
    for norm_name, a_lots in artist_lots.items():
        profile = profiles.get(norm_name) or {}

        hammers = [l["hammer_usd"] for l in a_lots if l.get("hammer_usd")]
        total = sum(hammers)
        avg   = total / len(hammers) if hammers else 0

        ratios_a = []
        for l in a_lots:
            lo, hi = l.get("estimate_low"), l.get("estimate_high")
            h = l.get("hammer_usd")
            if lo and hi and h:
                ratios_a.append((h / ((lo + hi) / 2), l))
        top_ratio_lot = max(ratios_a, key=lambda x: x[0])[1] if ratios_a else None

        # Best lot by hammer
        top_lot = max(a_lots, key=lambda l: l.get("hammer_usd") or 0) if a_lots else None

        dataset = {
            "lot_count":    len(a_lots),
            "total_usd":    round(total),
            "avg_usd":      round(avg),
            "total_label":  _fmt_usd(total),
            "avg_label":    _fmt_usd(avg),
        }
        if top_lot:
            dataset["top_lot"] = {
                "title":      (top_lot.get("title") or "")[:60],
                "hammer_usd": round(top_lot.get("hammer_usd") or 0),
                "sale_name":  top_lot.get("sale_name") or "",
            }
        if top_ratio_lot:
            dataset["top_ratio_lot"] = {
                "title":  (top_ratio_lot.get("title") or "")[:60],
                "ratio":  round(ratios_a[0][0] if len(ratios_a) == 1 else max(r for r, _ in ratios_a), 2),
            }

        row = {
            "norm_name":    norm_name,
            "display_name": profile.get("display_name") or norm_name.title(),
            "dates":        profile.get("dates") or "",
            "nationality":  profile.get("nationality") or "",
            "movement":     profile.get("movement") or "",
            "movement_id":  profile.get("movement_id") or "contemporary",
            "bio":          profile.get("bio") or "",
            "famous_works":       profile.get("famous_works") or [],
            "lesser_known_works": profile.get("lesser_known_works") or [],
            "dataset": dataset,
        }
        artist_rows.append(row)

    # Sort: profiled artists with highest total first, then unprofiled
    artist_rows.sort(key=lambda r: (
        0 if r["bio"] else 1,
        -(r["dataset"]["total_usd"])
    ))

    return {"stats": stats, "artists": artist_rows}


if __name__ == "__main__":
    print("Loading data from DB…")
    with connect() as conn:
        lots     = all_lots(conn)
        profiles = all_artist_profiles(conn)
    print(f"  {len(lots)} lots, {len(profiles)} artist profiles")

    OUT_PATH.parent.mkdir(exist_ok=True)

    print("Building research.json…")
    research = build_research(lots, profiles)
    OUT_PATH.write_text(json.dumps(research, ensure_ascii=False, indent=2))

    n_profiled = sum(1 for a in research["artists"] if a["bio"])
    print(f"Done — {len(research['artists'])} artists ({n_profiled} with full profiles)")
    print(f"  Stats: {research['stats']['total_lots']} lots, "
          f"median ${research['stats']['median_hammer_usd']:,}, "
          f"{research['stats']['pct_above_estimate']}% above estimate")
