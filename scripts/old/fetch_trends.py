#!/usr/bin/env python3
"""
Fetch trending topics, drill into TikTok, and generate quote/content ideas.

Pipeline:
  1. Google Trends RSS   → what's spiking right now
  2. pytrends            → broad category ranking (last 24h)
  3. Scraptik/TikTok     → hashtag reach for each top trending topic
  4. LLM (OpenRouter)    → quote + content ideas per topic

Usage:
    python scripts/fetch_trends.py
    python scripts/fetch_trends.py --geo US --top 5
    python scripts/fetch_trends.py --json
"""

import argparse
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import httpx
import requests
from dotenv import load_dotenv
from pytrends.request import TrendReq

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

_RAPIDAPI_KEY  = os.getenv("RAPIDAPI_KEY")
_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
_SCRAPTIK_HOST = "scraptik.p.rapidapi.com"
_RSS_NS = "https://trends.google.com/trending/rss"

BROAD_CATEGORIES = [
    ["AI", "sports", "music", "film", "health"],
    ["politics", "fashion", "crypto", "economy", "climate"],
    ["art", "gaming", "travel", "food", "science"],
]


def fetch_google_trending_rss(geo: str = "US") -> list[dict]:
    """Pull today's trending searches from Google Trends RSS (no keyword needed)."""
    try:
        r = requests.get(
            "https://trends.google.com/trending/rss",
            params={"geo": geo or "US"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        r.raise_for_status()
        root = ET.fromstring(r.content)
        results = []
        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            traffic = item.findtext(f"{{{_RSS_NS}}}approx_traffic", "")
            news = item.find(f"{{{_RSS_NS}}}news_item")
            source  = news.findtext(f"{{{_RSS_NS}}}news_item_source", "") if news is not None else ""
            snippet = news.findtext(f"{{{_RSS_NS}}}news_item_snippet", "") if news is not None else ""
            results.append({"title": title, "traffic": traffic, "source": source, "snippet": snippet})
        return results
    except Exception as e:
        print(f"[warn] Google RSS failed: {e}", file=sys.stderr)
        return []


def fetch_category_interest(geo: str = "US") -> list[dict]:
    """Rank broad topic categories by search interest (last 24h)."""
    pt = TrendReq(hl="en-US", tz=0)
    all_results = []
    for chunk in BROAD_CATEGORIES:
        try:
            pt.build_payload(chunk, timeframe="now 1-d", geo=geo)
            df = pt.interest_over_time()
            if df.empty:
                continue
            avg = df[chunk].mean()
            for k, v in avg.items():
                all_results.append({"category": k, "interest": round(float(v), 1)})
            time.sleep(2)
        except Exception as e:
            print(f"[warn] interest fetch failed for {chunk}: {e}", file=sys.stderr)
            time.sleep(5)
    all_results.sort(key=lambda x: x["interest"], reverse=True)
    return all_results


def fetch_tiktok_hashtags(keyword: str, count: int = 10) -> list[dict]:
    """Return top TikTok hashtags for a keyword, sorted by view count."""
    if not _RAPIDAPI_KEY:
        return []
    try:
        r = requests.get(
            f"https://{_SCRAPTIK_HOST}/search-hashtags",
            headers={
                "x-rapidapi-key": _RAPIDAPI_KEY,
                "x-rapidapi-host": _SCRAPTIK_HOST,
                "Content-Type": "application/json",
            },
            params={"keyword": keyword, "count": count, "cursor": 0, "compact": 0},
            timeout=15,
        )
        r.raise_for_status()
        results = []
        for c in r.json().get("challenge_list", []):
            info = c.get("challenge_info", {})
            results.append({
                "hashtag": info.get("cha_name", ""),
                "view_count": info.get("view_count", 0),
                "post_count": info.get("use_count", 0),
            })
        results.sort(key=lambda x: x["view_count"], reverse=True)
        return results[:5]
    except Exception as e:
        print(f"[warn] TikTok fetch failed for '{keyword}': {e}", file=sys.stderr)
        return []


def generate_quote_ideas(topic: str, snippet: str, hashtags: list[dict]) -> list[dict]:
    """Use LLM to generate quote/caption ideas for a trending topic."""
    if not _OPENROUTER_KEY:
        print("[warn] OPENROUTER_API_KEY not set — skipping LLM", file=sys.stderr)
        return []

    top_tags = " ".join(f"#{h['hashtag']}" for h in hashtags[:3])

    prompt = f"""You are a social media content strategist. A topic is trending right now.

Topic: {topic}
Context: {snippet or "No context available."}
Top TikTok hashtags: {top_tags or "none found"}

Generate 3 short, punchy content ideas (quote cards, captions, or hooks) that:
- Ride the trend without being newsy or political
- Work as standalone Instagram/TikTok captions or quote card text
- Are 1-2 sentences max, editorial tone, thought-provoking
- Can be paired with visual art or design content

Return ONLY a JSON array of objects, each with:
  "idea": the caption/quote text (max 40 words)
  "angle": one-word content angle (e.g. "motivation", "contrast", "irony", "beauty")
  "hashtags": 3-5 relevant hashtags as a string

No markdown, no explanation. Raw JSON array only."""

    try:
        r = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {_OPENROUTER_KEY}",
                "HTTP-Referer": "https://github.com/alexsnowschool-business",
                "X-Title": "trend-content-bot",
            },
            json={
                "model": _OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 500,
                "temperature": 0.7,
            },
            timeout=30,
        )
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"[warn] LLM idea generation failed: {e}", file=sys.stderr)
        return []


def _fmt_views(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    return f"{n:,}"


def main():
    parser = argparse.ArgumentParser(description="Trending topics → TikTok drill → quote ideas")
    parser.add_argument("--geo", default="US", help="Country code (US, GB, AU, CA)")
    parser.add_argument("--top", type=int, default=5, help="How many trending topics to drill into")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    geo = args.geo.upper()

    print(f"[trends] fetching — geo={geo}", file=sys.stderr)
    google_trending   = fetch_google_trending_rss(geo)
    print(f"[trends] ranking categories…", file=sys.stderr)
    category_interest = fetch_category_interest(geo)

    enriched = []
    for topic in google_trending[:args.top]:
        print(f"[tiktok] drilling '{topic['title']}'…", file=sys.stderr)
        hashtags = fetch_tiktok_hashtags(topic["title"])
        print(f"[llm]    generating ideas for '{topic['title']}'…", file=sys.stderr)
        ideas = generate_quote_ideas(topic["title"], topic.get("snippet", ""), hashtags)
        enriched.append({**topic, "tiktok_hashtags": hashtags, "content_ideas": ideas})
        time.sleep(1)

    result = {
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "geo": geo,
        "trending_with_ideas": enriched,
        "category_interest_24h": category_interest,
    }

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    print(f"\n{'='*60}")
    print(f"  TRENDING NOW + CONTENT IDEAS — {geo} — {result['fetched_at'][:10]}")
    print(f"{'='*60}\n")

    for i, topic in enumerate(enriched, 1):
        print(f"{'─'*60}")
        print(f"  {i}. {topic['title'].upper()}  ({topic['traffic']} searches)")
        if topic["snippet"]:
            print(f"     {topic['snippet'][:100]}…")

        if topic["tiktok_hashtags"]:
            tags = "  ".join(
                f"#{h['hashtag']} ({_fmt_views(h['view_count'])})"
                for h in topic["tiktok_hashtags"][:3]
            )
            print(f"\n     TikTok: {tags}")

        if topic["content_ideas"]:
            print(f"\n     Content ideas:")
            for idea in topic["content_ideas"]:
                print(f"       [{idea.get('angle','').upper()}]")
                print(f"       \"{idea.get('idea','')}\"")
                print(f"       {idea.get('hashtags','')}")
                print()
        else:
            print()

    print(f"\n{'─'*60}")
    print(f"CATEGORY INTEREST — last 24h:")
    for item in category_interest:
        bar = "█" * int(item["interest"] / 4)
        print(f"  {item['category']:<12} {bar:<20} {item['interest']}")


if __name__ == "__main__":
    main()
