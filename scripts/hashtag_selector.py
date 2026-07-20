#!/usr/bin/env python3
"""
Smart hashtag selector: 3 for Instagram, 5 for TikTok.

Keeps 1-2 evergreen anchor tags per content type, then fills remaining
slots with the highest-reach trending tags for the given topic.

Usage:
    python scripts/hashtag_selector.py --type art --topic "contemporary art"
    python scripts/hashtag_selector.py --type quote --topic "motivation"
    python scripts/hashtag_selector.py --type artist --topic "Salvador Dali"
"""

import argparse
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

_RAPIDAPI_KEY  = os.getenv("RAPIDAPI_KEY")
_SCRAPTIK_HOST = "scraptik.p.rapidapi.com"

IG_LIMIT = 3
TT_LIMIT = 5

# Anchors: always included, highest-priority slots.
# Keep to 1-2 per platform so trending tags still get real estate.
_ANCHORS: dict[str, dict[str, list[str]]] = {
    "art": {
        "ig": ["#thehammerprice"],
        "tt": ["#thehammerprice", "#artmarket"],
    },
    "artist": {
        "ig": ["#thehammerprice"],
        "tt": ["#thehammerprice", "#arthistory"],
    },
    "quote": {
        "ig": ["#lifequotes"],
        "tt": ["#lifequotes", "#mindset"],
    },
}

_FALLBACKS: dict[str, dict[str, list[str]]] = {
    "art": {
        "ig": ["#fineart", "#auctionresults"],
        "tt": ["#fineart", "#auctionresults", "#artoftheday"],
    },
    "artist": {
        "ig": ["#artlovers", "#arthistory"],
        "tt": ["#artlovers", "#fineart", "#artoftheday"],
    },
    "quote": {
        "ig": ["#motivation", "#quotes"],
        "tt": ["#motivation", "#quotes", "#inspiration"],
    },
}


def _fetch_tiktok_hashtags(keyword: str, count: int = 20) -> list[dict]:
    """Return TikTok hashtags for a keyword, sorted by view_count descending."""
    if not _RAPIDAPI_KEY:
        return []
    try:
        r = requests.get(
            f"https://{_SCRAPTIK_HOST}/search-hashtags",
            headers={
                "x-rapidapi-key": _RAPIDAPI_KEY,
                "x-rapidapi-host": _SCRAPTIK_HOST,
            },
            params={"keyword": keyword, "count": count, "cursor": 0, "compact": 0},
            timeout=15,
        )
        r.raise_for_status()
        results = []
        for c in r.json().get("challenge_list", []):
            info = c.get("challenge_info", {})
            name = info.get("cha_name", "").strip()
            if name:
                results.append({
                    "tag": f"#{name}",
                    "view_count": info.get("view_count", 0),
                })
        results.sort(key=lambda x: x["view_count"], reverse=True)
        return results
    except Exception as e:
        print(f"[warn] TikTok hashtag fetch failed for '{keyword}': {e}", file=sys.stderr)
        return []


def _normalise(tag: str) -> str:
    return tag.lower().lstrip("#")


def select_hashtags(
    content_type: str,
    topic: str | None = None,
) -> dict[str, str]:
    """
    Return {"instagram": "...", "tiktok": "..."} with space-separated hashtags.

    content_type: "art" | "artist" | "quote"
    topic: keyword passed to TikTok search (falls back to content_type if None)
    """
    ctype = content_type if content_type in _ANCHORS else "art"
    search_keyword = topic or ctype

    ig_anchors = list(_ANCHORS[ctype]["ig"])
    tt_anchors = list(_ANCHORS[ctype]["tt"])

    ig_seen  = {_normalise(t) for t in ig_anchors}
    tt_seen  = {_normalise(t) for t in tt_anchors}

    ig_slots = IG_LIMIT - len(ig_anchors)
    tt_slots = TT_LIMIT - len(tt_anchors)

    trending = _fetch_tiktok_hashtags(search_keyword, count=20)

    ig_extra: list[str] = []
    tt_extra: list[str] = []

    for item in trending:
        tag  = item["tag"]
        norm = _normalise(tag)
        if len(ig_extra) < ig_slots and norm not in ig_seen:
            ig_extra.append(tag)
            ig_seen.add(norm)
        if len(tt_extra) < tt_slots and norm not in tt_seen:
            tt_extra.append(tag)
            tt_seen.add(norm)
        if len(ig_extra) >= ig_slots and len(tt_extra) >= tt_slots:
            break

    # Fill any remaining slots from fallbacks if trending came up short
    if len(ig_extra) < ig_slots or len(tt_extra) < tt_slots:
        for tag in _FALLBACKS[ctype]["ig"]:
            norm = _normalise(tag)
            if len(ig_extra) < ig_slots and norm not in ig_seen:
                ig_extra.append(tag)
                ig_seen.add(norm)

        for tag in _FALLBACKS[ctype]["tt"]:
            norm = _normalise(tag)
            if len(tt_extra) < tt_slots and norm not in tt_seen:
                tt_extra.append(tag)
                tt_seen.add(norm)

    ig_tags = ig_anchors + ig_extra
    tt_tags = tt_anchors + tt_extra

    return {
        "instagram": " ".join(ig_tags[:IG_LIMIT]),
        "tiktok":    " ".join(tt_tags[:TT_LIMIT]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Smart hashtag selector")
    parser.add_argument("--type",  default="art",
                        choices=list(_ANCHORS.keys()),
                        help="Content type")
    parser.add_argument("--topic", default=None,
                        help="Topic keyword for TikTok search")
    args = parser.parse_args()

    tags = select_hashtags(args.type, args.topic)
    print(f"Instagram ({IG_LIMIT}): {tags['instagram']}")
    print(f"TikTok    ({TT_LIMIT}): {tags['tiktok']}")


if __name__ == "__main__":
    main()
