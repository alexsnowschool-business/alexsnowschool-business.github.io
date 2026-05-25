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
_HASHTAGS_LN = "#artmarket #auctionresults #artcollecting #contemporaryart"


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

    ln = generate_linkedin_caption(lot)

    return {"instagram": ig, "tiktok": tt, "linkedin": ln or ""}


def generate_linkedin_caption(lot: dict) -> str | None:
    """Returns a LinkedIn caption or None if API unavailable."""
    if not OPENROUTER_KEY:
        return None

    artist = lot.get("artist", "Unknown")
    title  = lot.get("title", "Untitled")
    house  = lot.get("auction_house", "the auction house")
    hammer = lot.get("hammer_fmt", "unknown")
    est    = lot.get("estimate_fmt", "unknown")
    pct    = lot.get("pct_above", 0)

    prompt = f"""You write posts for @thehammerprice — an art market account on LinkedIn. Professional but conversational. No emojis except one at the start.

Lot:
- Artist: {artist}
- Work: "{title}"
- House: {house}
- Estimate: {est}  →  Hammer: {hammer}  ({pct:.0f}% above estimate)

Write a LinkedIn post (3–4 short paragraphs):
1. Opening hook — one punchy sentence, lead with the insight (what the gap between estimate and hammer reveals).
2. Context — one sentence about {artist} and why this result matters to collectors or the market.
3. The market signal — one sentence: what does a result like this tell us about demand, pricing, or where the market is going?
4. Closing line — a question or observation that invites professional discussion.

Rules:
- All lowercase except proper nouns
- No fluff adjectives
- Do NOT repeat the full estimate/hammer — reference the gap or the % instead
- Keep it under 200 words
- End with exactly: {_HASHTAGS_LN}

Reply with only the post text, nothing else."""

    raw = _call([{"role": "user", "content": prompt}], max_tokens=350)
    return raw.strip() if raw else None


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


# ── Substack content ───────────────────────────────────────────────────────────

def _lot_context(lot: dict) -> str:
    """Shared lot summary block reused across Substack prompts."""
    hammer   = f"${lot.get('hammer_usd', 0):,.0f}"
    est_low  = f"${lot.get('estimate_low', 0):,.0f}"
    est_high = f"${lot.get('estimate_high') or lot.get('estimate_low', 0):,.0f}"
    pct      = lot.get("pct_above", 0)
    return (
        f"Artist: {lot.get('artist', 'Unknown')}\n"
        f"Work: \"{lot.get('title', 'Untitled')}\"\n"
        f"Auction house: {lot.get('auction_house', 'unknown')}\n"
        f"Sale: {lot.get('sale_name', '')}, {lot.get('sale_date', '')}\n"
        f"Estimate: {est_low}–{est_high}\n"
        f"Hammer: {hammer} ({pct:.0f}% above low estimate)"
    )


def generate_substack_title(lot: dict) -> str | None:
    """Generate an editorial headline + subtitle for the Substack post."""
    if not OPENROUTER_KEY:
        return None

    prompt = f"""You write editorial headlines for a Substack called The Hammer Price — art market analysis for collectors and curious readers.

Auction result:
{_lot_context(lot)}

Write:
1. TITLE: one punchy headline (~8 words). Not clickbait. Factual but intriguing. Can use a colon. Should name the artist or work.
2. SUBTITLE: one sentence (~20 words). Sets up the question this post will answer — what does this result tell us about the market, the artist, or the collector?

Rules: sentence case (not title case). No quotes around the title. No emojis.

Reply with only:
TITLE: <title>
SUBTITLE: <subtitle>"""

    raw = _call([{"role": "user", "content": prompt}], max_tokens=120)
    return raw.strip() if raw else None


def generate_substack_price_commentary(lot: dict) -> str | None:
    """
    Generate a 250-word price commentary section: estimate vs hammer, what the gap signals,
    market context for this artist.
    """
    if not OPENROUTER_KEY:
        return None

    prompt = f"""You write art market analysis for The Hammer Price, a Substack for informed collectors. Voice: editorial, precise, no hype. Like a sharp auction house specialist talking off the record.

Auction result:
{_lot_context(lot)}

Write the PRICE COMMENTARY section (~250 words). Cover:
1. The estimate vs the hammer — what the specialists thought going in, and what the room decided.
2. What the percentage gap means in this market context — is this surprising? Routine? Historically significant?
3. What drives collectors to push past estimate for this kind of work — demand signal, scarcity, timing?
4. End with one sentence that frames what this result reveals about where the market is right now.

Rules:
- Prose paragraphs only — no bullet points, no headers within the section.
- Specific and data-grounded — reference the actual numbers.
- No fluff adjectives ("stunning", "remarkable"). Say what things mean, not how impressive they are.
- Write in present tense where appropriate.

Reply with only the section text."""

    raw = _call([{"role": "user", "content": prompt}], max_tokens=600)
    return raw.strip() if raw else None


def generate_substack_work_analysis(lot: dict) -> str | None:
    """
    Generate a 200-word analysis of the specific artwork — medium, period, visual/conceptual
    significance, why this piece rather than another by the same hand.
    """
    if not OPENROUTER_KEY:
        return None

    prompt = f"""You write art market analysis for The Hammer Price, a Substack for informed collectors. Voice: editorial, precise, knowledgeable.

Auction result:
{_lot_context(lot)}

Write THE WORK section (~200 words). Cover:
1. What this specific piece is — medium, likely period or date range, scale if known, subject or visual character.
2. What distinguishes it within this artist's output — is this a signature subject? An atypical experiment? A peak-period work?
3. Any provenance or exhibition context if known — if you don't know specifics, note what collectors typically look for in a work like this.
4. Why the room wanted this piece in particular — not just the artist, but this object.

Rules:
- Prose paragraphs only.
- Be specific about the work, not generic about the artist.
- If you're uncertain about a detail, reason from what's probable — don't invent provenance dates or exhibition names.

Reply with only the section text."""

    raw = _call([{"role": "user", "content": prompt}], max_tokens=500)
    return raw.strip() if raw else None


def generate_substack_art_history(lot: dict) -> str | None:
    """
    Generate a 280-word art history analysis: artist biography, movement, market trajectory,
    why this result matters in the arc of their career and market.
    """
    if not OPENROUTER_KEY:
        return None

    prompt = f"""You write art history and market analysis for The Hammer Price, a Substack for informed collectors. Voice: authoritative, specific, not academic.

Auction result:
{_lot_context(lot)}

Write THE ARTIST section (~280 words). Cover:
1. Who this artist is — nationality, birth/death years if known, training, major periods of activity.
2. The movement or school they belong to — be specific (not just "modern art"). Name influences, contemporaries, the critical context they emerged from.
3. How their auction market has behaved over time — when did they peak? Any periods of critical or commercial revival? Where do they sit in the market hierarchy today?
4. What this result means in the arc of their auction history — is this a new high, a confirmation of a trend, a correction?

Rules:
- Prose paragraphs only — no bullet points.
- Name specific movements, decades, critics, or contemporaries where relevant.
- If you're uncertain about a specific date or fact, write what is probable and well-supported.
- Don't pad. Every sentence should add information.

Reply with only the section text."""

    raw = _call([{"role": "user", "content": prompt}], max_tokens=700)
    return raw.strip() if raw else None


def generate_substack_post(lot: dict) -> dict | None:
    """
    Generate all sections of a Substack post for a single auction lot.
    Returns a dict with keys: title, subtitle, price_commentary, work_analysis, art_history.
    Returns None if the API is unavailable.
    """
    if not OPENROUTER_KEY:
        return None

    title_raw        = generate_substack_title(lot)
    price_commentary = generate_substack_price_commentary(lot)
    work_analysis    = generate_substack_work_analysis(lot)
    art_history      = generate_substack_art_history(lot)

    if not any([title_raw, price_commentary, work_analysis, art_history]):
        return None

    title    = ""
    subtitle = ""
    if title_raw:
        for line in title_raw.splitlines():
            if line.upper().startswith("TITLE:"):
                title = line.split(":", 1)[1].strip()
            elif line.upper().startswith("SUBTITLE:"):
                subtitle = line.split(":", 1)[1].strip()

    def _clean(text: str | None) -> str:
        """Strip any section heading the model echoed back (e.g. '# THE WORK')."""
        if not text:
            return ""
        return re.sub(r"^\s*#+\s+[A-Z][A-Z\s]+\n+", "", text).strip()

    return {
        "title":             title,
        "subtitle":          subtitle,
        "price_commentary":  _clean(price_commentary),
        "work_analysis":     _clean(work_analysis),
        "art_history":       _clean(art_history),
    }


# ── Text-to-speech ─────────────────────────────────────────────────────────────

ELEVENLABS_KEY     = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE   = os.getenv("ELEVENLABS_VOICE_ID", "LXu5MIFyvPZCxBst8fPP")  # Adam — deep, universally available
ELEVENLABS_MODEL   = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")

EDGE_TTS_VOICE = "en-GB-RyanNeural"   # fallback: deep British male


def _elevenlabs_tts(text: str, output_path: str) -> list[dict]:
    """
    Generate TTS via ElevenLabs SDK with character-level timestamps.
    Returns word_timings = [{"word": str, "start": float_secs}, ...].
    Writes MP3 to output_path.
    """
    import base64
    from elevenlabs import VoiceSettings
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=ELEVENLABS_KEY)
    response = client.text_to_speech.convert_with_timestamps(
        voice_id=ELEVENLABS_VOICE,
        text=text,
        model_id=ELEVENLABS_MODEL,
        output_format="mp3_44100_128",
        voice_settings=VoiceSettings(stability=0.45, similarity_boost=0.80, style=0.2),
    )

    with open(output_path, "wb") as f:
        f.write(base64.b64decode(response.audio_base_64))

    # Convert character-level alignment → word-level timings
    alignment = response.alignment
    chars  = (alignment.characters or []) if alignment else []
    starts = (alignment.character_start_times_seconds or []) if alignment else []

    word_timings: list[dict] = []
    current_word = ""
    word_start   = 0.0
    for char, t in zip(chars, starts):
        if char in (" ", "\n", "\t"):
            if current_word:
                word_timings.append({"word": current_word, "start": word_start})
                current_word = ""
        else:
            if not current_word:
                word_start = t
            current_word += char
    if current_word:
        word_timings.append({"word": current_word, "start": word_start})

    return word_timings


async def _edgetts_with_timing_async(text: str, output_path: str, voice: str) -> list[dict]:
    """Fallback: Edge-TTS with word-boundary events."""
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
                    "start": event["offset"] / 10_000_000,
                })
    return word_timings


def generate_voiceover(text: str, output_path: str, voice: str = EDGE_TTS_VOICE) -> tuple[bool, list[dict]]:
    """
    Synthesise text to MP3. Tries ElevenLabs first (if key present), falls back to Edge-TTS.
    Returns (success, word_timings) where word_timings = [{"word": str, "start": float_secs}, ...].
    """
    if ELEVENLABS_KEY and ELEVENLABS_VOICE:
        try:
            timings = _elevenlabs_tts(text, output_path)
            print(f"  ✓ ElevenLabs TTS ({ELEVENLABS_VOICE}) — {len(timings)} words")
            return True, timings
        except Exception as e:
            print(f"  ⚠ ElevenLabs error (voice={ELEVENLABS_VOICE}): {e} — falling back to Edge-TTS")
    elif ELEVENLABS_KEY and not ELEVENLABS_VOICE:
        print(f"  ⚠ ELEVENLABS_VOICE_ID is empty — falling back to Edge-TTS")

    try:
        timings = asyncio.run(_edgetts_with_timing_async(text, output_path, voice))
        print(f"  ✓ Edge-TTS — {len(timings)} words")
        return True, timings
    except Exception as e:
        print(f"  ⚠ TTS error: {e}")
        return False, []


def synthesize_gavel(output_path: str) -> bool:
    """
    Synthesize an auction-hammer strike sound using stdlib + ffmpeg MP3 conversion.
    Low-frequency thud + noise click — no external audio deps required.
    Returns True on success.
    """
    import math
    import random as _rand
    import struct
    import subprocess
    import wave

    sample_rate = 44100
    duration    = 0.38
    n           = int(sample_rate * duration)
    _rand.seed(42)

    samples = []
    for i in range(n):
        t     = i / sample_rate
        thud  = math.sin(2 * math.pi * 85  * t) * math.exp(-t * 20) * 0.90
        body  = math.sin(2 * math.pi * 160 * t) * math.exp(-t * 35) * 0.30
        click = (_rand.random() * 2 - 1)         * math.exp(-t * 90) * 0.45
        val   = int((thud + body + click) * 32767)
        samples.append(struct.pack("<h", max(-32768, min(32767, val))))

    wav_tmp = output_path.replace(".mp3", "_gavel_tmp.wav")
    with wave.open(wav_tmp, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"".join(samples))

    r = subprocess.run(["ffmpeg", "-y", "-i", wav_tmp, output_path], capture_output=True)
    try:
        os.remove(wav_tmp)
    except OSError:
        pass
    return r.returncode == 0
