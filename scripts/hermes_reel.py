#!/usr/bin/env python3
"""
Hermès retail vs. resale reel generator.

Joins:
  - data/hermes.db              : official new prices from hermes.com/de/de/
  - hermes-archive/catalogue.json : Vestiaire Collective pre-owned prices

Formula: "Hermès charges €X. On Vestiaire: $Y. That's +Z%."

Usage:
    python scripts/hermes_reel.py                   # best premium available
    python scripts/hermes_reel.py --model "Birkin 30"
    python scripts/hermes_reel.py --list            # show all model premiums
    python scripts/hermes_reel.py --run             # also render the reel
    python scripts/hermes_reel.py --brand "@provenance"
"""

import argparse
import json
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
from datetime import date
from pathlib import Path

from PIL import Image

import httpx
from dotenv import load_dotenv

SCRIPT_DIR   = Path(__file__).resolve().parent
BUSINESS_DIR = SCRIPT_DIR.parent

load_dotenv(BUSINESS_DIR / ".env", override=False)

HERMES_DB      = BUSINESS_DIR / "data" / "hermes.db"
CATALOGUE_JSON = BUSINESS_DIR / "hermes-archive" / "catalogue.json"
REEL_TEMPLATE  = BUSINESS_DIR / "reel_template"
REELS_DIR      = BUSINESS_DIR / "reels"

# Approximate EUR → USD conversion rate (update manually as needed)
EUR_TO_USD = 1.08

# ── AI / TTS credentials ───────────────────────────────────────────────────────
# Voice uses HERMES_ELEVENLABS_API_KEY so you can bill it to a separate account.
# Falls back to the shared ELEVENLABS_API_KEY if the hermes-specific one is absent.
OPENROUTER_KEY    = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL  = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
OPENROUTER_URL    = "https://openrouter.ai/api/v1/chat/completions"

ELEVENLABS_KEY    = os.getenv("HERMES_ELEVENLABS_API_KEY") or os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE  = (os.getenv("HERMES_ELEVENLABS_VOICE_ID") or
                     os.getenv("ELEVENLABS_VOICE_ID") or
                     "LXu5MIFyvPZCxBst8fPP")
ELEVENLABS_MODEL  = (os.getenv("HERMES_ELEVENLABS_MODEL_ID") or
                     os.getenv("ELEVENLABS_MODEL_ID") or
                     "eleven_turbo_v2_5")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.vestiairecollective.com/",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}

# ── Known retail prices (EUR) for allocation-only bags not sold on hermes.com ─
# Source: publicly documented Hermès Europe price lists (2024–2025)
KNOWN_RETAIL_EUR: dict[str, float] = {
    "Birkin 25": 8_350,
    "Birkin 30": 9_900,
    "Birkin 35": 10_850,
    "Birkin 40": 11_650,
    "Kelly 25":  7_650,
    "Kelly 28":  8_750,
    "Kelly 32":  9_450,
    "Kelly 35":  10_250,
    "Kelly Mini": 7_000,
    "Kelly Moove": 5_150,
    "Constance":  10_200,
    "Constance Elan": 9_100,
    "Lindy 26":  5_250,
    "Lindy 30":  5_750,
}

# ── Keyword mapping: bag model name → keywords found in hermes.db German names ─
# Used to extract retail prices for models that DO appear on hermes.com
MODEL_KEYWORDS: dict[str, list[str]] = {
    "Evelyne":     ["evelyne", "évelyne"],
    "Herbag":      ["herbag"],
    "Garden Party": ["garden party"],
    "Bolide":      ["bolide"],
    "Picotin":     ["picotin"],
    "Lindy":       ["lindy", "halzan"],
    "Jypsiere":    ["jypsière", "jypsiere"],
    "24/24":       ["24/24"],
}

# ── Hook templates: (min_premium_pct, [question variants], [answer variants]) ─
_HOOKS = [
    (200,
     [
         "the boutique won't sell you this.",
         "you can't buy this. the waitlist can.",
         "hermès priced this at {retail}. the market says {resale}.",
         "retail {retail}. resale {resale}. read that again.",
         "what does a {pct} premium tell you?",
     ],
     [
         "hermès controls the supply. the secondary market controls the price. "
         "a {pct} premium above retail isn't a fluke — it's the cost of the waitlist, "
         "the relationship, and the patience required to buy new.",
         "the boutique has one price. the market has another. "
         "at {pct} above retail, the room has already decided what this bag is worth — "
         "and it's not the number on the hermès invoice.",
         "scarcity is the product. the {pct} premium is the proof. "
         "hermès has priced this at {retail} for decades. "
         "the secondary market prices what a decade of waiting actually costs.",
     ]),

    (100,
     [
         "hermès says {retail}. vestiaire says {resale}.",
         "the premium is {pct} and it's not going away.",
         "more than double. that's the hermès secondary market.",
         "you pay {retail} new — if they'll sell it to you.",
         "retail vs. resale: {retail} to {resale}.",
     ],
     [
         "the secondary market for hermès isn't driven by speculation — it's driven by access. "
         "the boutique has a waitlist. vestiaire has a buy button. "
         "that difference costs {pct}.",
         "a {pct} premium means two things: the bag holds its value, and supply can't meet demand. "
         "hermès hasn't changed that equation in fifty years.",
         "retail and resale diverge on hermès more than almost any other luxury brand. "
         "the {pct} gap between {retail} and {resale} is the price of exclusivity, made visible.",
     ]),

    (50,
     [
         "above retail — even pre-owned.",
         "the resale premium: {pct}.",
         "hermès {retail}. resale {resale}.",
         "the market pays more than the boutique charges.",
         "why does pre-owned hermès cost more than new?",
     ],
     [
         "pre-owned hermès often sells above new retail. "
         "the reason is simple: you can find it today, without the relationship, "
         "without the waiting. that access commands a {pct} premium.",
         "the {pct} resale premium on this bag reflects consistent collector demand. "
         "hermès has maintained its pricing discipline; the secondary market "
         "adds what the boutique won't — immediacy.",
         "a bag that sells above its retail price secondhand is a store of value, not just a purchase. "
         "the {pct} premium here is the market's verdict on hermès's supply strategy.",
     ]),

    (0,
     [
         "hermès holds its value.",
         "pre-owned near retail — that's the hermès market.",
         "retail {retail}. resale {resale}.",
         "the secondary market tracks retail closely on this one.",
         "a {pct} resale premium: modest but real.",
     ],
     [
         "not every hermès bag commands a dramatic premium, but most hold value near retail. "
         "a {pct} overshoot on {model} confirms consistent secondary market demand.",
         "the resale market for hermès is liquid. "
         "even a modest {pct} premium confirms the brand's secondary market depth "
         "— buyers are always present, and prices don't collapse.",
         "hermès maintains value because supply stays controlled. "
         "the {pct} premium here is quiet but telling: the market is always slightly ahead of retail.",
     ]),
]


# ── Price formatters ───────────────────────────────────────────────────────────

def _fmt_eur(v: float) -> str:
    return f"€{v:,.0f}"


def _fmt_usd(v: float) -> str:
    return f"${v:,.0f}"


def _premium_pct(retail_eur: float, resale_usd: float) -> float:
    retail_usd = retail_eur * EUR_TO_USD
    return round((resale_usd / retail_usd - 1) * 100, 1)


# ── Load retail prices ─────────────────────────────────────────────────────────

def _load_db_retail() -> dict[str, tuple[float, list[str]]]:
    """
    Returns {model_keyword: (median_price_eur, [image_urls])} from hermes.db.
    Groups by extracted English model keyword.
    """
    if not HERMES_DB.exists():
        return {}

    conn = sqlite3.connect(HERMES_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT name, price_value, image_urls FROM items "
        "WHERE platform='hermes.com' AND price_value > 0"
    ).fetchall()
    conn.close()

    groups: dict[str, list[tuple[float, list[str]]]] = {}
    for row in rows:
        name_lower = (row["name"] or "").lower()
        for model, keywords in MODEL_KEYWORDS.items():
            if any(kw in name_lower for kw in keywords):
                urls = json.loads(row["image_urls"] or "[]")
                groups.setdefault(model, []).append((row["price_value"], urls))
                break

    result = {}
    for model, entries in groups.items():
        prices = [e[0] for e in entries]
        all_images = []
        for _, urls in entries:
            all_images.extend(urls)
        result[model] = (statistics.median(prices), all_images[:8])
    return result


# ── Load resale stats from catalogue.json ─────────────────────────────────────

def _load_resale_stats() -> dict[str, dict]:
    """
    Returns {model: {median_usd, avg_usd, count, images: [urls]}}
    from Vestiaire Collective entries in catalogue.json.
    """
    if not CATALOGUE_JSON.exists():
        print(f"✗ catalogue.json not found: {CATALOGUE_JSON}")
        sys.exit(1)

    items = json.load(CATALOGUE_JSON.open())
    vest  = [
        i for i in items
        if i.get("platform") == "vestiairecollective.com"
        and i.get("price_value")
        and i.get("price_value", 0) > 0
    ]

    groups: dict[str, list] = {}
    for item in vest:
        m = item.get("model") or ""
        if not m:
            continue
        groups.setdefault(m, []).append(item)

    stats = {}
    for model, entries in groups.items():
        prices = [e["price_value"] for e in entries]
        # Collect images from the item closest to the median price
        median_p = statistics.median(prices)
        best     = min(entries, key=lambda e: abs(e["price_value"] - median_p))
        urls = best.get("image_urls") or []
        if isinstance(urls, str):
            try:
                urls = json.loads(urls)
            except Exception:
                urls = []
        stats[model] = {
            "median_usd": median_p,
            "avg_usd":    statistics.mean(prices),
            "count":      len(prices),
            "images":     urls[:6],
            "source_url": best.get("source_url", ""),
        }
    return stats


# ── Build premium table ────────────────────────────────────────────────────────

def _build_premiums(
    db_retail: dict[str, tuple[float, list[str]]],
    resale:    dict[str, dict],
) -> list[dict]:
    """
    Merge retail + resale into a premium table, sorted by premium descending.
    """
    rows = []

    # Models with retail price in hermes.db
    for model, (retail_eur, images) in db_retail.items():
        # Find matching Vestiaire model (exact or substring)
        resale_key = _find_resale_key(model, resale)
        if not resale_key:
            continue
        stats = resale[resale_key]
        pct   = _premium_pct(retail_eur, stats["median_usd"])
        rows.append({
            "model":       model,
            "resale_key":  resale_key,
            "retail_eur":  retail_eur,
            "resale_usd":  stats["median_usd"],
            "resale_count": stats["count"],
            "premium_pct": pct,
            "images":      images or stats["images"],
            "source_url":  stats["source_url"],
            "retail_source": "hermes.db",
        })

    # Hero bags from KNOWN_RETAIL
    for model, retail_eur in KNOWN_RETAIL_EUR.items():
        # skip if already in db_retail
        if model in db_retail:
            continue
        resale_key = _find_resale_key(model, resale)
        if not resale_key:
            continue
        stats = resale[resale_key]
        pct   = _premium_pct(retail_eur, stats["median_usd"])
        rows.append({
            "model":       model,
            "resale_key":  resale_key,
            "retail_eur":  retail_eur,
            "resale_usd":  stats["median_usd"],
            "resale_count": stats["count"],
            "premium_pct": pct,
            "images":      stats["images"],
            "source_url":  stats["source_url"],
            "retail_source": "reference",
        })

    rows.sort(key=lambda r: -r["premium_pct"])
    return rows


def _find_resale_key(model: str, resale: dict) -> str | None:
    """Find the best matching key in the resale stats dict for a given model name."""
    # Exact match first
    if model in resale:
        return model
    # Case-insensitive exact
    model_low = model.lower()
    for key in resale:
        if key.lower() == model_low:
            return key
    # Substring: model name contained in key or key contained in model
    for key in resale:
        if model_low in key.lower() or key.lower() in model_low:
            return key
    return None


# ── Image downloading ──────────────────────────────────────────────────────────

def _download_images_playwright(urls: list[str], dest_dir: Path, max_images: int = 6) -> list[Path]:
    """Download images via a real Chromium browser to bypass CDN bot-protection."""
    import asyncio
    from playwright.async_api import async_playwright

    async def _fetch_all():
        saved = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                user_agent=_HEADERS["User-Agent"],
                locale="en-US",
            )
            page = await context.new_page()
            # Prime Cloudflare cookies with a real page visit first.
            await page.goto("https://www.vestiairecollective.com/", wait_until="domcontentloaded", timeout=30_000)

            _CT_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
            for i, url in enumerate(urls[:max_images]):
                try:
                    # Navigate directly to the image URL — Cloudflare sees a real browser
                    # navigation, not a fetch(), so TLS/header fingerprints pass inspection.
                    resp = await page.goto(url, wait_until="load", timeout=20_000)
                    if not resp or not resp.ok:
                        status = resp.status if resp else "no response"
                        print(f"  ✗ {url[:70]}... — HTTP {status}")
                        continue
                    ct  = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                    ext = _CT_EXT.get(ct) or (
                        ".jpg" if ("jpg" in url.lower() or "jpeg" in url.lower()) else ".png"
                    )
                    fname = dest_dir / f"{i + 1:02d}{ext}"
                    fname.write_bytes(await resp.body())
                    print(f"  ✓ {fname.name}")
                    saved.append(fname)
                except Exception as e:
                    print(f"  ✗ {url[:70]}... — {e}")
            await browser.close()
        return saved

    return asyncio.run(_fetch_all())


def _download_images(urls: list[str], dest_dir: Path, max_images: int = 6) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Try Playwright first — bypasses CDN bot-protection that blocks httpx in CI.
    import importlib.util
    if importlib.util.find_spec("playwright") is not None:
        return _download_images_playwright(urls, dest_dir, max_images)

    # Fallback: plain httpx (works locally if not IP-blocked).
    _CT_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    saved = []
    with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=20) as client:
        for i, url in enumerate(urls[:max_images]):
            try:
                r = client.get(url)
                r.raise_for_status()
                ct  = r.headers.get("content-type", "").split(";")[0].strip().lower()
                ext = _CT_EXT.get(ct) or (
                    ".jpg" if ("jpg" in url.lower() or "jpeg" in url.lower()) else ".png"
                )
                fname = dest_dir / f"{i + 1:02d}{ext}"
                fname.write_bytes(r.content)
                print(f"  ✓ {fname.name}")
                saved.append(fname)
            except Exception as e:
                print(f"  ✗ {url[:70]}... — {e}")
    return saved


# ── Hook text ─────────────────────────────────────────────────────────────────

import random


def _hook(row: dict) -> tuple[str, str]:
    pct      = row["premium_pct"]
    retail   = _fmt_eur(row["retail_eur"])
    resale   = _fmt_usd(row["resale_usd"])
    model    = row["model"]
    fmt      = dict(retail=retail, resale=resale, pct=f"+{pct:,.0f}%", model=model)

    for threshold, q_variants, a_variants in _HOOKS:
        if pct >= threshold:
            return (
                random.choice(q_variants).format(**fmt),
                random.choice(a_variants).format(**fmt),
            )
    return "the hermès secondary market.", "supply and demand."


# ── Config generation ──────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def _generate_config(row: dict, reel_slug: str, brand: str, reveal: list[dict],
                     narration_captions: list[dict] | None = None) -> str:
    model     = row["model"]
    retail    = _fmt_eur(row["retail_eur"])
    resale    = _fmt_usd(row["resale_usd"])
    pct       = row["premium_pct"]
    count     = row["resale_count"]

    line1 = f"retail  ·  {retail}"
    line2 = resale
    line3 = f"+{pct:,.0f}%  above retail"

    caption_full = (
        f"hermès prices the {model} at {retail} new — if they'll sell it to you. "
        f"on vestiaire today: {resale}. "
        f"that's {pct:,.0f}% above retail. "
        f"the secondary market prices what the boutique won't."
    )

    lines = [
        '"""',
        f"╔══════════════════════════════════════════════════════════════╗",
        f"║  REEL CONFIG — {model:<44}  ║",
        f"║  Generated by scripts/hermes_reel.py                        ║",
        f"╚══════════════════════════════════════════════════════════════╝",
        '"""',
        "",
        "CONFIG = {",
        f'    "lot_id":         "{_esc(reel_slug)}",',
        "",
        "    # ── Caption ────────────────────────────────────────────────",
        f'    "caption_tag":    "{_esc(brand)}  ·  retail vs resale",',
        f'    "caption_line1":        "{_esc(line1)}",',
        f'    "caption_line2_label":  "secondary market",',
        f'    "caption_line2":        "{_esc(line2)}",',
        f'    "caption_line3":        "{_esc(line3)}",',
        "",
        "    # ── Location metadata ─────────────────────────────────────",
        f'    "location_coords": "HERMÈS",',
        f'    "location_name":   "{_esc(model.upper())}",',
        f'    "location_season": "{date.today().year}  ·  RESALE PREMIUM",',
        f'    "frame_label":     "{_esc(brand)}",',
        "",
        "    # ── Layout ────────────────────────────────────────────────",
        '    "photo_split":        False,',
        '    "photo_fit_first":    False,',
        '    "photo_center_crop":  True,',
        '    "hide_chrome":        True,',
        '    "block_reveal":       False,',
        '    "caption_no_box":     False,',
        "",
        "    # ── Style ─────────────────────────────────────────────────",
        '    "vibe":             "warm_dark",',
        '    "caption_position": "center",',
        "",
        "    # ── Font overrides ─────────────────────────────────────────",
        '    "fonts_override": {',
        '        "serif_lg":   ("InstrumentSerif-Regular.ttf", 120),',
        '        "serif_med":  ("InstrumentSerif-Regular.ttf",  68),',
        '        "italic_med": ("InstrumentSerif-Italic.ttf",  72),',
        '        "jura_light": ("Jura-Light.ttf",              22),',
        '        "mono":       ("IBMPlexMono-Regular.ttf",      20),',
        '        "mono_sm":    ("IBMPlexMono-Regular.ttf",      16),',
        "    },",
        "",
        "    # ── Colours ───────────────────────────────────────────────",
        "    \"color_tag\":   (245, 242, 235),",           # near-white — matches retail label
        "    \"color_line1\": (245, 242, 235),",          # near-white retail label
        "    \"color_line2\": (196, 158, 40),",           # rich gold — resale price dominates
        "    \"color_line3\": (245, 242, 235),",          # near-white premium %
        "",
        "    \"caption_all_frames\": False,",
        "",
        "    # ── Pacing ────────────────────────────────────────────────",
        '    "fps":          5,',
        '    "hold_seconds": 0.0,',
        '    "fade_seconds": 0.0,',
        "",
        "    # ── Social captions ───────────────────────────────────────",
        '    "topic":          "luxury",',
        f'    "location":       "hermès",',
        f'    "season":         "{date.today().year}",',
        '    "caption_full":   (',
        f'        "{_esc(caption_full)}"',
        "    ),",
        f'    "caption_hero":   "the boutique has one price.",',
        '    "personal_note":  "the hermès secondary market is one of the most liquid luxury resale markets in the world.",',
        '    "engagement_hook": "what\'s the biggest resale premium you\'ve ever seen? #hermès #luxuryresale #hermesbirkin",',
    ]

    if reveal:
        lines.append("")
        lines.append("    # ── Per-frame reveal ──────────────────────────────────────")
        lines.append("    \"per_frame_captions\": [")
        for fc in reveal:
            lines.append("        {")
            for key, val in fc.items():
                lines.append(f"            {repr(key)}: {repr(val)},")
            lines.append("        },")
        lines.append("    ],")

    if narration_captions:
        lines.append("")
        lines.append("    # ── Word-by-word narration captions ───────────────────────")
        lines.append("    \"narration_captions\": [")
        for cap in narration_captions:
            lines.append(
                f"        {{\"start\": {cap['start']:.3f}, "
                f"\"end\": {cap['end']:.3f}, "
                f"\"text\": {repr(cap['text'])}}},")
        lines.append("    ],")

    lines.append("}")
    return "\n".join(lines) + "\n"


# ── Voiceover: narration generation ──────────────────────────────────────────

def _generate_narration(row: dict) -> str | None:
    """
    Ask OpenRouter to write a ~1-min voiceover script for the bag.
    Returns the script string, or None if the call fails.
    """
    if not OPENROUTER_KEY:
        print("  ✗ OPENROUTER_API_KEY not set — cannot generate narration")
        return None

    model   = row["model"]
    retail  = _fmt_eur(row["retail_eur"])
    resale  = _fmt_usd(row["resale_usd"])
    pct     = row["premium_pct"]
    count   = row["resale_count"]

    prompt = f"""Write a 160-180 word voiceover script for a TikTok reel about Hermès resale prices. It must read naturally when spoken aloud at a calm pace — exactly 60 to 70 seconds. and don't include here is your script or any other preamble.
      The script should be editorial and informative, like something a luxury finance journalist would say — no hype, no emojis, no hashtags.
      Use the following data points about the bag to craft a compelling narrative that explains the price gap between retail and resale,
      and what it signals about Hermès as a store of value.

Bag: {model}
Hermès retail price: {retail} (boutique only, requires a client relationship)
Vestiaire Collective resale median: {resale} (based on {count} listings)
Premium above retail: +{pct:.0f}%

Tone: calm, editorial, luxury finance journalist — no hype, no emojis, no hashtags.
Structure:
- Open with the price gap as the hook (first 2 sentences)
- Explain WHY the secondary market commands this premium (access, scarcity, waitlist)
- Give the raw numbers clearly
- Close with what this signals about the Hermès market as a store of value

Speak directly to the viewer. Short sentences. No filler phrases. Output only the script text, nothing else."""

    try:
        r = httpx.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "HTTP-Referer": "https://github.com/alexsnowschool-business",
                "X-Title": "provenance-hermes-reel",
            },
            json={
                "model":       OPENROUTER_MODEL,
                "messages":    [{"role": "user", "content": prompt}],
                "max_tokens":  350,
                "temperature": 0.80,
            },
            timeout=30,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        # Strip common LLM preamble labels the model adds despite instructions.
        import re
        text = re.sub(r"(?i)^(here'?s?( is)?( your)?( the)? script:?\s*)+", "", text).strip()
        print(f"  ✓ Narration generated ({len(text.split())} words)")
        return text
    except Exception as e:
        print(f"  ✗ OpenRouter error: {e}")
        return None


# ── Voiceover: ElevenLabs TTS (with Edge TTS fallback) ────────────────────────

EDGE_TTS_VOICE = os.getenv("EDGE_TTS_VOICE", "en-US-AriaNeural")


def _synthesise_via_edge_tts(text: str, output_path: Path) -> bool:
    """Free fallback TTS via Microsoft Edge TTS (no API key required)."""
    try:
        import asyncio
        import edge_tts

        async def _run():
            communicate = edge_tts.Communicate(text, EDGE_TTS_VOICE)
            await communicate.save(str(output_path))

        asyncio.run(_run())
        print(f"  ✓ Edge TTS (voice={EDGE_TTS_VOICE}) → {output_path.name}")
        return True
    except ImportError:
        print("  ✗ edge-tts not installed (pip install edge-tts)")
        return False
    except Exception as e:
        print(f"  ✗ Edge TTS error: {e}")
        return False


def _synthesise_voiceover(text: str, output_path: Path) -> tuple[bool, list[dict]]:
    """
    Synthesise text to MP3. Tries ElevenLabs first; falls back to Edge TTS.
    Returns (success, word_timestamps). Word timestamps are populated only when
    ElevenLabs is used (it returns character-level alignment); Edge TTS returns [].
    """
    if ELEVENLABS_KEY and ELEVENLABS_VOICE:
        try:
            import base64
            from elevenlabs import VoiceSettings
            from elevenlabs.client import ElevenLabs

            client   = ElevenLabs(api_key=ELEVENLABS_KEY)
            response = client.text_to_speech.convert_with_timestamps(
                voice_id=ELEVENLABS_VOICE,
                text=text,
                model_id=ELEVENLABS_MODEL,
                output_format="mp3_44100_128",
                voice_settings=VoiceSettings(stability=0.45, similarity_boost=0.80, style=0.2),
            )
            output_path.write_bytes(base64.b64decode(response.audio_base_64))
            print(f"  ✓ ElevenLabs TTS (voice={ELEVENLABS_VOICE}) → {output_path.name}")
            raw = response.alignment
            alignment = raw.__dict__ if hasattr(raw, "__dict__") else (raw or {})
            words = _alignment_to_words(alignment)
            return True, words
        except Exception as e:
            print(f"  ✗ ElevenLabs error: {e} — falling back to Edge TTS")

    print("  ▸ Using Edge TTS fallback")
    ok = _synthesise_via_edge_tts(text, output_path)
    return ok, []


def _audio_duration(path: Path) -> float:
    """Return MP3 duration in seconds via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


# ── Word-level caption helpers ─────────────────────────────────────────────────

def _alignment_to_words(alignment: dict) -> list[dict]:
    """Convert ElevenLabs character-level alignment into word-level timestamps."""
    chars  = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends   = alignment.get("character_end_times_seconds", [])

    words: list[dict] = []
    buf: list[str] = []
    buf_start = buf_end = None

    for ch, s, e in zip(chars, starts, ends):
        if ch in (" ", "\n", "\t"):
            if buf:
                words.append({"word": "".join(buf), "start": buf_start, "end": buf_end})
                buf, buf_start, buf_end = [], None, None
        else:
            if buf_start is None:
                buf_start = s
            buf_end = e
            buf.append(ch)

    if buf:
        words.append({"word": "".join(buf), "start": buf_start, "end": buf_end})
    return words


def _evenly_spaced_words(text: str, duration: float) -> list[dict]:
    """Fallback: distribute words evenly across the audio duration."""
    tokens = text.split()
    if not tokens or duration <= 0:
        return []
    step = duration / len(tokens)
    return [{"word": w, "start": i * step, "end": (i + 1) * step}
            for i, w in enumerate(tokens)]


def _srt_ts(seconds: float) -> str:
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _words_to_captions(words: list[dict], group: int = 3) -> list[dict]:
    """Group word timestamps into caption cues (uppercase) for the config."""
    captions = []
    for i in range(0, len(words), group):
        chunk = words[i : i + group]
        captions.append({
            "start": chunk[0]["start"],
            "end":   chunk[-1]["end"],
            "text":  " ".join(w["word"] for w in chunk).lower(),
        })
    return captions


def _write_srt(words: list[dict], path: Path, group: int = 3) -> None:
    """Write word-level captions as SRT, grouping `group` words per cue (uppercase)."""
    lines = []
    for idx, i in enumerate(range(0, len(words), group), start=1):
        chunk = words[i : i + group]
        text  = " ".join(w["word"] for w in chunk).lower()
        lines += [
            str(idx),
            f"{_srt_ts(chunk[0]['start'])} --> {_srt_ts(chunk[-1]['end'])}",
            text,
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  ✓ Captions SRT: {path.name}  ({(len(words) + group - 1) // group} cues)")


def _burn_captions(video_path: Path, srt_path: Path) -> Path | None:
    """Burn SRT subtitles into a video with ffmpeg. Returns the output path or None."""
    out = video_path.with_stem(video_path.stem + "_captioned")
    style = (
        "FontName=Arial,FontSize=20,Bold=1,Alignment=2,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"subtitles={srt_path}:force_style='{style}'",
        "-c:a", "copy",
        str(out),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  ✓ Captioned video: {out.name}")
            return out
        print(f"  ✗ ffmpeg subtitles error: {result.stderr[-400:]}")
        return None
    except FileNotFoundError:
        print("  ✗ ffmpeg not found — install it to burn captions into the video")
        return None


# ── Reveal sequence ───────────────────────────────────────────────────────────

def _build_reveal(row: dict, brand: str, n_images: int, voice_duration: float = 0.0) -> list[dict]:
    model   = row["model"]
    retail  = _fmt_eur(row["retail_eur"])
    resale  = _fmt_usd(row["resale_usd"])
    pct     = row["premium_pct"]
    hook_q, _ = _hook(row)

    tag = f"{brand}  ·  retail vs resale"

    def _f(line1="", line2="", line3="", hold=5.0, ua="", ut=""):
        return {
            "show_caption":  bool(line1 or line2 or line3),
            "tag":           tag,
            "line1":         line1,
            "line2":         line2,
            "line3":         line3,
            "hook_question": None,
            "hook_answer":   "",
            "upper_artist":  ua,
            "upper_title":   ut,
            "hold_seconds":  hold,
        }

    n_mid = max(1, n_images - 2)

    # Scale hold times to fit the voiceover; fall back to short defaults otherwise.
    if voice_duration > 0:
        act1_s   = round(voice_duration * 0.20, 1)
        act3_s   = round(voice_duration * 0.25, 1)
        mid_each = round((voice_duration - act1_s - act3_s) / n_mid, 1)
    else:
        act1_s   = 6.0
        mid_each = round(4.0 / n_mid, 1)
        act3_s   = 10.0

    # Act I: retail and resale prices only — clean, no hook teaser line.
    act1: dict = {
        "show_caption":     True,
        "caption_position": "center",
        "tag":              tag,
        "line1":            f"retail  ·  {retail}",
        "line2":            resale,
        "line3":            "",
        "hook_question":    None,
        "hook_answer":      "",
        "upper_artist":     "",
        "upper_title":      model,
        "hold_seconds":     act1_s,
    }
    frames = [act1]
    # Act II + III: clean images only — no caption overlay
    for _ in range(n_mid + 1):
        frames.append(_f(hold=mid_each))
    return frames


# ── Tracking ──────────────────────────────────────────────────────────────────

def _ensure_posted_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posted_hermes_reels (
            model       TEXT PRIMARY KEY,
            retail_eur  REAL,
            resale_usd  REAL,
            premium_pct REAL,
            reel_slug   TEXT,
            posted_at   TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def _posted_models(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT model FROM posted_hermes_reels").fetchall()
    return {r[0] for r in rows}


def _record_posted(conn: sqlite3.Connection, row: dict, reel_slug: str) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO posted_hermes_reels
            (model, retail_eur, resale_usd, premium_pct, reel_slug)
        VALUES (?, ?, ?, ?, ?)
    """, (row["model"], row["retail_eur"], row["resale_usd"],
          row["premium_pct"], reel_slug))
    conn.commit()


# ── List mode ─────────────────────────────────────────────────────────────────

def _print_list(premiums: list[dict]) -> None:
    print(f"\n{'Model':<22} {'Retail (EUR)':>12} {'Resale (USD)':>12} {'Premium':>8} {'N':>5}  Source")
    print("-" * 80)
    for r in premiums:
        print(
            f"{r['model']:<22} {_fmt_eur(r['retail_eur']):>12} "
            f"{_fmt_usd(r['resale_usd']):>12} {r['premium_pct']:>7.0f}% "
            f"{r['resale_count']:>5}  {r['retail_source']}"
        )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a retail-vs-resale reel for Hermès bags."
    )
    parser.add_argument("--model",   default=None, help="Specific model name (e.g. 'Birkin 30')")
    parser.add_argument("--list",    action="store_true", help="Print premium table and exit")
    parser.add_argument("--run",     action="store_true", help="Render reel after generation")
    parser.add_argument("--brand",   default="@provenance.resale", help="Brand handle for captions")
    parser.add_argument("--all",     action="store_true", help="Ignore already-posted models")
    parser.add_argument("--voice",   action="store_true",
                        help="Generate ~1.1 min AI narration and synthesise via ElevenLabs")
    args = parser.parse_args()

    print("═" * 62)
    print("  HERMÈS REEL GENERATOR — Retail vs. Resale")
    print("═" * 62)

    db_retail = _load_db_retail()
    resale    = _load_resale_stats()
    premiums  = _build_premiums(db_retail, resale)

    if not premiums:
        print("✗ No matching models found. Check that hermes.db and catalogue.json exist.")
        sys.exit(1)

    if args.list:
        _print_list(premiums)
        return

    # ── Pick model ─────────────────────────────────────────────
    conn = sqlite3.connect(HERMES_DB)
    conn.row_factory = sqlite3.Row
    _ensure_posted_table(conn)
    posted = _posted_models(conn) if not args.all else set()
    conn.close()

    if args.model:
        candidates = [r for r in premiums if r["model"].lower() == args.model.lower()]
        if not candidates:
            # Fuzzy fallback
            candidates = [r for r in premiums if args.model.lower() in r["model"].lower()]
        if not candidates:
            print(f"✗ Model '{args.model}' not found. Use --list to see available models.")
            sys.exit(1)
        chosen = candidates[0]
    else:
        unposted = [r for r in premiums if r["model"] not in posted]
        if not unposted:
            print("  ℹ All models have been posted — re-using top model.")
            unposted = premiums
        # Prefer models with images
        with_imgs = [r for r in unposted if r["images"]]
        chosen = with_imgs[0] if with_imgs else unposted[0]

    print(f"\n▸ Model:         {chosen['model']}")
    print(f"  Retail:        {_fmt_eur(chosen['retail_eur'])}  ({chosen['retail_source']})")
    print(f"  Resale (med):  {_fmt_usd(chosen['resale_usd'])}  (n={chosen['resale_count']})")
    print(f"  Premium:       +{chosen['premium_pct']:,.0f}%")

    # ── Create reel folder ─────────────────────────────────────
    slug      = f"hermes-{chosen['model'].lower().replace(' ', '-')}-{date.today().isoformat()}"
    reel_dir  = REELS_DIR / slug
    img_dir   = reel_dir / "images"
    out_dir   = reel_dir / "output"

    for d in (reel_dir, img_dir, out_dir):
        d.mkdir(parents=True, exist_ok=True)

    print(f"\n▸ Reel folder:   reels/{slug}/")

    # ── Download images ────────────────────────────────────────
    print("\n▸ Downloading images...")
    saved = _download_images(chosen["images"], reel_dir / "_src")

    if not saved:
        print("✗ No images downloaded.")
        sys.exit(1)

    # Copy with numeric prefix into images/, converting WebP → JPEG for make_reel.py
    n_images = 0
    for idx, src in enumerate(saved):
        if src.suffix.lower() == ".webp":
            dest = img_dir / f"{idx + 1:02d}_{src.stem}.jpg"
            try:
                with Image.open(src) as im:
                    im.convert("RGB").save(dest, "JPEG", quality=95)
            except Exception as e:
                print(f"  ⚠ WebP conversion failed for {src.name}: {e} — skipping")
                continue
        else:
            dest = img_dir / f"{idx + 1:02d}_{src.name}"
            shutil.copy2(src, dest)
        n_images += 1
    print(f"  {n_images} image(s) ready")

    # ── Voiceover (optional) ───────────────────────────────────
    voice_duration  = 0.0
    srt_path: Path | None = None
    narr_captions:  list[dict] = []
    if args.voice:
        print("\n▸ Generating voiceover narration...")
        narration = _generate_narration(chosen)
        if narration:
            print(f"  Script preview: {narration[:120]}...")
            vo_path = reel_dir / "voiceover.mp3"
            ok, word_timestamps = _synthesise_voiceover(narration, vo_path)
            if ok:
                voice_duration = _audio_duration(vo_path)
                print(f"  Audio duration: {voice_duration:.1f}s")
                if not word_timestamps and voice_duration > 0:
                    word_timestamps = _evenly_spaced_words(narration, voice_duration)
                if word_timestamps:
                    srt_path      = reel_dir / "captions.srt"
                    narr_captions = _words_to_captions(word_timestamps)
                    _write_srt(word_timestamps, srt_path)

    # ── Build reveal + config ──────────────────────────────────
    reveal      = _build_reveal(chosen, args.brand, n_images, voice_duration=voice_duration)
    config_src  = _generate_config(chosen, slug, args.brand, reveal,
                                   narration_captions=narr_captions or None)
    config_path = reel_dir / "reel_config.py"
    config_path.write_text(config_src)
    print(f"\n▸ Config written: {config_path.relative_to(BUSINESS_DIR)}")

    # ── Record ─────────────────────────────────────────────────
    conn2 = sqlite3.connect(HERMES_DB)
    conn2.row_factory = sqlite3.Row
    _ensure_posted_table(conn2)
    _record_posted(conn2, chosen, slug)
    conn2.close()

    # ── Summary ────────────────────────────────────────────────
    print("\n" + "═" * 62)
    print("  READY TO RENDER")
    print(f"  Reel folder: reels/{slug}/")
    print()
    print("  To render:")
    print(f"    python reel_template/make_reel.py reels/{slug}")
    print(f"    python reel_template/make_captions.py reels/{slug}")
    if srt_path:
        print()
        print("  To burn word captions manually:")
        print(f"    ffmpeg -i <video.mp4> -vf subtitles={srt_path.name} -c:a copy captioned.mp4")
    print("═" * 62)

    if args.run:
        print("\n▸ Running make_reel.py...")
        subprocess.run(
            [sys.executable, str(REEL_TEMPLATE / "make_reel.py"), str(reel_dir)],
            cwd=str(BUSINESS_DIR),
        )

    # Always burn captions when voice was used — runs after --run or against any
    # video already present in output/ from a prior render.
    if srt_path and srt_path.exists():
        videos = sorted(out_dir.glob("*.mp4"))
        # Skip files that are already captioned to avoid re-burning.
        videos = [v for v in videos if "_captioned" not in v.stem]
        if videos:
            print("\n▸ Burning word captions into video...")
            _burn_captions(videos[0], srt_path)
        else:
            print(f"\n  ℹ No rendered video found yet — run make_reel.py first, captions will burn automatically on next run.")


if __name__ == "__main__":
    main()
