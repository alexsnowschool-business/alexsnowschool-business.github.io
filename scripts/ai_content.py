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


_ANGLES = [
    "data pattern — use the stat: 51% of lots at the major houses sell above estimate. connect this result to the broader pattern.",
    "collector psychology — why did someone pay this much? nobody goes to auction to pay fair value. they go to win.",
    "market timing — what shifted before the sale? the estimate is set months early. by auction day the market had already moved.",
    "catalogue vs room — the specialist wrote one number, the room bid another. the gap between them is the real story.",
    "price discovery — use the actual numbers ({estimate} → {hammer}). the estimate is a floor, not a forecast.",
]


def generate_captions(lot: dict) -> dict | None:
    """Returns {instagram, tiktok} captions or None if API unavailable."""
    import random
    if not OPENROUTER_KEY:
        return None

    artist  = lot.get("artist", "Unknown")
    title   = lot.get("title", "Untitled")
    house   = lot.get("auction_house", "the auction house")
    hammer  = lot.get("hammer_fmt", "unknown")
    est     = lot.get("estimate_fmt", "unknown")
    pct     = lot.get("pct_above", 0)
    angle   = random.choice(_ANGLES).format(estimate=est, hammer=hammer)

    prompt = f"""You write captions for @thehammerprice — an art market account. Short, plain, lowercase. No emojis except where shown.

Lot:
- Artist: {artist}
- Work: "{title}"
- House: {house}
- Estimate: {est}  →  Hammer: {hammer}  ({pct:.0f}% above estimate)

Angle to use: {angle}

Rules:
- All lowercase
- No fluff, no adjectives like "stunning" or "incredible"
- Specific and data-driven
- Do NOT include hashtags

--- INSTAGRAM ---
Format (4 short paragraphs, each 1–2 lines):
1. Hook: one line — estimate vs hammer price as a contrast. no label.
2. The work: one sentence naming {artist} and "{title}", what the % means.
3. The insight: one sentence using the angle above.
4. Question: one short engagement question for the comments.

--- TIKTOK ---
Format (3 lines max):
1. Same hook line as Instagram.
2. One follow-up line using the angle.
3. "📍 {house}"

Reply with only the two sections and their labels. Nothing else."""

    raw = _call([{"role": "user", "content": prompt}], max_tokens=400)
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
