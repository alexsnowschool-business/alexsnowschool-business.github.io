#!/usr/bin/env python3
"""
AI content generator for @thehammerprice — uses OpenRouter free models.

Generates:
  - Instagram caption (hook + data + hashtags)
  - TikTok caption (tight, hook-led)
  - Art history first comment (painter + painting context)

Usage:
    from scripts.ai_content import generate_captions, generate_art_history

Requires OPENROUTER_API_KEY in .env or environment.
Falls back gracefully (returns None) if key is missing or API fails.
"""

import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

OPENROUTER_KEY  = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL  = "https://openrouter.ai/api/v1/chat/completions"

# Model options:
#   free:  "meta-llama/llama-3.1-8b-instruct:free"  (no cost)
#          "google/gemma-2-9b-it:free"
#   paid:  "anthropic/claude-haiku-4-5"              (Claude via OpenRouter)
#          "anthropic/claude-sonnet-4-5"
MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")

_HASHTAGS_IG = (
    "#thehammerprice #artmarket #auctionresults #artcollecting #contemporaryart "
    "#artinvestment #auctionhouse #fineart #artworld #reels #explore"
)
_HASHTAGS_TT = (
    "#thehammerprice #artmarket #auctionresults #fyp #foryou #foryoupage "
    "#contemporaryart #artcollecting"
)


def _call(messages: list[dict], max_tokens: int = 400) -> str | None:
    if not OPENROUTER_KEY:
        return None
    try:
        r = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "HTTP-Referer": "https://github.com/alexsnowschool-business",
                "X-Title": "thehammerprice-reel-bot",
            },
            json={
                "model": MODEL,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.85,
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  ⚠ OpenRouter error: {e}")
        return None


def generate_captions(lot: dict) -> dict | None:
    """
    Returns {"instagram": str, "tiktok": str} or None if API unavailable.

    lot keys used: artist, title, auction_house, hammer_usd (formatted),
                   estimate_low, estimate_high, pct_above
    """
    if not OPENROUTER_KEY:
        return None

    artist  = lot.get("artist", "Unknown")
    title   = lot.get("title", "Untitled")
    house   = lot.get("auction_house", "the auction house")
    hammer  = lot.get("hammer_fmt", "unknown")
    est     = lot.get("estimate_fmt", "unknown")
    pct     = lot.get("pct_above", 0)

    prompt = f"""You write social media captions for @thehammerprice — a data-driven art market account that exposes auction price patterns.

Lot details:
- Artist: {artist}
- Title: "{title}"
- Auction house: {house}
- Estimate: {est}
- Hammer price: {hammer}
- % above low estimate: {pct:.0f}%

Write TWO captions. Tone: plain, specific, data-first. No fluff. Lowercase throughout.

--- INSTAGRAM ---
3–5 lines. Start with a one-line hook comparing estimate vs hammer price (no label, just the contrast). Second paragraph: one sentence about the artist or work. Third: one insight about what this result means for the market. End with one engagement question. Do NOT include hashtags — I'll add them separately.

--- TIKTOK ---
2–3 lines max. Hook line first (estimate vs hammer). One follow-up insight. No question needed. Do NOT include hashtags.

Reply with exactly the two sections labelled --- INSTAGRAM --- and --- TIKTOK --- and nothing else."""

    raw = _call([{"role": "user", "content": prompt}], max_tokens=500)
    if not raw:
        return None

    ig_m = re.search(r"--- INSTAGRAM ---\s*(.*?)(?=--- TIKTOK ---|$)", raw, re.DOTALL)
    tt_m = re.search(r"--- TIKTOK ---\s*(.*?)$", raw, re.DOTALL)

    ig = (ig_m.group(1).strip() + f"\n\n{_HASHTAGS_IG}") if ig_m else None
    tt = (tt_m.group(1).strip() + f"\n\n{_HASHTAGS_TT}") if tt_m else None

    if not ig or not tt:
        return None

    return {"instagram": ig, "tiktok": tt}


def generate_art_history(lot: dict) -> str | None:
    """
    Returns a 3–4 sentence art history blurb for Instagram first comment, or None.
    Covers both the painter's career and the specific work's significance.
    """
    if not OPENROUTER_KEY:
        return None

    artist = lot.get("artist", "Unknown")
    title  = lot.get("title", "Untitled")
    house  = lot.get("auction_house", "the auction house")
    hammer = lot.get("hammer_fmt", "unknown")

    prompt = f"""Write a short art history comment (3–4 sentences, ~120 words max) for an Instagram post about this auction result:

- Artist: {artist}
- Work: "{title}"
- Sold at: {house} for {hammer}

Cover: who the artist is, when they were active, what movement or style they belong to, and why this specific work or period matters. Be specific — name a movement, a decade, a key influence or context. Tone: editorial, informed, not academic. Lowercase. No hashtags. No emojis except one 🎨 at the very start.

Reply with only the comment text, nothing else."""

    raw = _call([{"role": "user", "content": prompt}], max_tokens=200)
    if not raw:
        return None

    blurb = raw.strip()
    if not blurb.startswith("🎨"):
        blurb = "🎨 " + blurb

    return blurb + "\n\n📖 ai-generated art history"
