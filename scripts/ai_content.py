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

import asyncio
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

_HASHTAGS_IG = "#thehammerprice #artmarket #auctionresults"
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

    artist    = lot.get("artist", "Unknown")
    title     = lot.get("title", "Untitled")
    house     = lot.get("auction_house", "the auction house")
    hammer    = lot.get("hammer_fmt", "unknown")
    est       = lot.get("estimate_fmt", "unknown")
    pct       = lot.get("pct_above", 0)
    angle = random.choice(_ANGLES).format(estimate=est, hammer=hammer)

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
- Do NOT repeat the estimate or hammer price — the video already shows the numbers
- Do NOT include hashtags

--- INSTAGRAM ---
Format (4 short paragraphs, each 1–2 lines):
1. Hook: one punchy line using the angle — lead with the insight, not the price.
2. The work: one sentence naming {artist} and "{title}" with context about why this result matters.
3. Art history: one sentence about {artist} — who they are, what movement or period they belong to, why their work is significant. specific, not generic.
4. The so-what: one sentence zooming out — what this tells us about the market.

--- TIKTOK ---
Format (2 lines max):
1. Same hook line as Instagram.
2. One follow-up line — the so-what.
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


def generate_hook_answer(lot: dict, question: str) -> str | None:
    """
    Generate a 2–3 sentence art-history explanation for the reel hook answer.
    Specific to the artist and work — replaces hardcoded _HOOK_TEMPLATES answers.
    Returns plain lowercase text or None if API unavailable.
    """
    if not OPENROUTER_KEY:
        return None

    artist = lot.get("artist", "Unknown")
    title  = lot.get("title", "Untitled")
    house  = lot.get("auction_house", "the auction house")
    hammer = lot.get("hammer_fmt", "unknown")
    est    = lot.get("estimate_fmt", "unknown")
    pct    = lot.get("pct_above", 0)

    prompt = f"""You write punchy on-screen text for art auction reels. 1–2 short sentences, all lowercase.

Auction result:
- Artist: {artist}
- Work: "{title}"
- House: {house}
- Estimate: {est} → Hammer: {hammer} ({pct:.0f}% above estimate)
- Hook question on screen: "{question}"

Answer that question in the voice of an auction house narrator — talk about the catalogue, the room, the estimate, the gap. Make it feel like insider commentary: why did the room bid this high? what did the specialists miss? Keep it tight, specific to this lot.

Rules: all lowercase. no fluff. 1–2 sentences only, under 25 words total.

Reply with only the answer text, nothing else."""

    raw = _call([{"role": "user", "content": prompt}], max_tokens=60)
    return raw.strip() if raw else None


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

    return blurb + f"\n\ndata source: {house} "


# ── Text-to-speech ─────────────────────────────────────────────────────────────

TTS_VOICE = "en-GB-RyanNeural"   # deep British male — fits auction house tone


async def _tts_with_timing_async(text: str, output_path: str, voice: str) -> list[dict]:
    """Stream TTS, write MP3, and collect word-boundary events."""
    import edge_tts
    word_timings = []
    communicate = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    with open(output_path, "wb") as f:
        async for event in communicate.stream():
            if event["type"] == "audio":
                f.write(event["data"])
            elif event["type"] == "WordBoundary":
                word_timings.append({
                    "word":  event["text"],
                    "start": event["offset"] / 10_000_000,   # 100-ns → seconds
                })
    return word_timings


def generate_voiceover(text: str, output_path: str, voice: str = TTS_VOICE) -> tuple[bool, list[dict]]:
    """
    Synthesise text to MP3 via Edge-TTS (free, no API key).
    Returns (success, word_timings) where word_timings = [{"word": str, "start": float_secs}, ...].
    """
    try:
        timings = asyncio.run(_tts_with_timing_async(text, output_path, voice))
        return True, timings
    except Exception as e:
        print(f"  ⚠ TTS error: {e}")
        return False, []
