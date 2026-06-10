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
import re
import random
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

# Allow sibling scripts/ modules to be imported directly
sys.path.insert(0, str(SCRIPT_DIR))
import reel_utils

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
EDGE_TTS_VOICE    = os.getenv("EDGE_TTS_VOICE", "en-US-AriaNeural")

# Vestiaire Collective headers (for httpx fallback; Playwright uses native headers)
_VC_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.vestiairecollective.com/",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}

# ── Minimum resale premium to qualify for a reel (resale must exceed retail by at least this %) ─
MIN_PREMIUM_PCT: float = 20.0

# ── How many days before a posted model becomes eligible again ────────────────
POSTED_COOLDOWN_DAYS: int = 14

# ── Fallback retail prices — used only if hermes.db retail_prices table is empty ─
# Birkin/Kelly/Constance are in-store only and never appear on hermes.com.
# These are seeded into hermes.db on first run; thereafter the DB copy is used.
# Prices in EUR — Hermès Europe, January 2026 increase.
_RETAIL_SEED: dict[str, float] = {
    "Birkin 25":   9_600,
    "Birkin 30":  10_600,
    "Birkin 35":  11_600,
    "Birkin 40":  12_700,
    "Kelly 25":    9_600,
    "Kelly 28":   10_100,
    "Kelly 32":   11_100,
    "Kelly Mini":  8_700,
    "Constance":   7_200,   # mixed Constance 18/24 weighted average, Jan 2026
}

# Refresh DB prices if they are older than this many days.
_RETAIL_PRICE_TTL_DAYS = 30

# ── Keyword mapping: bag model name → substrings found in hermes.db German names ─
# Retail prices are read live from hermes.db (hermes.com scrape).
# Birkin/Kelly are handled separately via _load_known_retail() (cached in hermes.db).
MODEL_KEYWORDS: dict[str, list[str]] = {
    "Evelyne":              ["evelyne", "évelyne"],
    "Herbag":               ["herbag"],
    "Garden Party":         ["garden party"],
    "Bolide":               ["bolide"],
    "Picotin":              ["picotin"],
    "Lindy":                ["lindy", "halzan"],
    "Jypsiere":             ["jypsière", "jypsiere"],
    "24/24":                ["24/24"],
    "Kelly Messenger":      ["kelly messenger"],
    "HAC":                  ["hac à dos"],
    "Collier d'Attelage":   ["collier d'attelage"],
    "In-the-Loop":          ["in-the-loop"],
    "Steeple":              ["steeple"],
    "Neo Garden":           ["néo garden"],
    "Medor":                ["médor", "medór", "medor"],
    "Sabot":                ["tasche sabot"],
    "Cab H":                ["cab'h", "cabh"],
    "Double Longe":         ["double longe"],
    "Faubourg Express":     ["faubourg express"],
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
        all_images: list[str] = []
        for _, urls in entries:
            all_images.extend(urls)
        result[model] = (statistics.median(prices), all_images[:8])
    return result


# ── Birkin / Kelly retail prices (auto-refreshed in hermes.db) ────────────────

def _ensure_retail_prices_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS retail_prices (
            model       TEXT PRIMARY KEY,
            retail_eur  REAL NOT NULL,
            source      TEXT,
            updated_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def _fetch_birkin_kelly_prices() -> dict[str, float]:
    """
    Scrape current EUR retail prices from PurseBop price guides.
    Returns a {model: eur_price} dict, or empty dict on any failure.
    """
    results: dict[str, float] = {}
    pages = [
        ("https://www.pursebop.com/the-hermes-birkin-price-guide-2026/", "Birkin"),
        ("https://www.pursebop.com/the-hermes-kelly-price-guide-2026/",  "Kelly"),
    ]
    headers = {"User-Agent": "Mozilla/5.0 (compatible; hermes-reel-bot/1.0)"}

    for url, family in pages:
        try:
            r = httpx.get(url, headers=headers, follow_redirects=True, timeout=15)
            r.raise_for_status()
            for m in re.finditer(
                rf"{family}\s+(\d{{2}}|Mini|Elan|Moove)[^\n]*?€([\d,]+)",
                r.text,
            ):
                size_raw, price_raw = m.group(1), m.group(2).replace(",", "")
                model = f"{family} {size_raw}"
                price = float(price_raw)
                if model not in results or price < results[model]:
                    results[model] = price
        except Exception:
            pass
    return results


def _load_known_retail() -> dict[str, float]:
    """
    Return {model: retail_eur} for Birkin and Kelly, reading from hermes.db.
    Refreshes from web if the prices are older than _RETAIL_PRICE_TTL_DAYS.
    Falls back to _RETAIL_SEED if the DB is missing or the fetch fails.
    """
    if not HERMES_DB.exists():
        return _RETAIL_SEED.copy()

    conn = sqlite3.connect(HERMES_DB)
    conn.row_factory = sqlite3.Row
    _ensure_retail_prices_table(conn)

    rows   = conn.execute("SELECT model, retail_eur, updated_at FROM retail_prices").fetchall()
    cached = {r["model"]: r["retail_eur"] for r in rows}

    stale = True
    if rows:
        from datetime import datetime, timezone
        oldest = min(r["updated_at"] for r in rows)
        try:
            age   = (datetime.now(timezone.utc) - datetime.fromisoformat(oldest.replace("Z", "+00:00"))).days
            stale = age >= _RETAIL_PRICE_TTL_DAYS
        except Exception:
            pass

    if stale:
        print("  ↻ Refreshing Birkin/Kelly retail prices from web…", end=" ", flush=True)
        fresh = _fetch_birkin_kelly_prices()
        if fresh:
            for model, price in fresh.items():
                conn.execute(
                    "INSERT INTO retail_prices (model, retail_eur, source, updated_at) "
                    "VALUES (?, ?, 'pursebop.com', datetime('now')) "
                    "ON CONFLICT(model) DO UPDATE SET retail_eur=excluded.retail_eur, "
                    "source=excluded.source, updated_at=excluded.updated_at",
                    (model, price),
                )
            cached.update(fresh)
            print(f"updated {len(fresh)} prices.")
        else:
            print("fetch failed, using cached values.")

        # Always backfill any seed model the web scrape didn't cover (e.g. Kelly Mini, Constance)
        seeded = 0
        for model, price in _RETAIL_SEED.items():
            if model not in cached:
                conn.execute(
                    "INSERT OR IGNORE INTO retail_prices (model, retail_eur, source) VALUES (?, ?, 'seed')",
                    (model, price),
                )
                cached[model] = price
                seeded += 1
        if seeded:
            print(f"  + seeded {seeded} model(s) not returned by web scrape.")
        conn.commit()

    conn.close()
    return cached


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
        prices   = [e["price_value"] for e in entries]
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
    rows = []

    for model, (retail_eur, images) in db_retail.items():
        resale_key = _find_resale_key(model, resale)
        if not resale_key:
            continue
        stats = resale[resale_key]
        pct   = _premium_pct(retail_eur, stats["median_usd"])
        if pct < MIN_PREMIUM_PCT:
            continue
        rows.append({
            "model":         model,
            "resale_key":    resale_key,
            "retail_eur":    retail_eur,
            "resale_usd":    stats["median_usd"],
            "resale_count":  stats["count"],
            "premium_pct":   pct,
            "images":        images or stats["images"],
            "source_url":    stats["source_url"],
            "retail_source": "hermes.db",
        })

    db_models = {r["model"] for r in rows}
    for model, retail_eur in _load_known_retail().items():
        if model in db_models:
            continue
        resale_key = _find_resale_key(model, resale)
        if not resale_key:
            continue
        stats = resale[resale_key]
        pct   = _premium_pct(retail_eur, stats["median_usd"])
        if pct < MIN_PREMIUM_PCT:
            continue
        rows.append({
            "model":         model,
            "resale_key":    resale_key,
            "retail_eur":    retail_eur,
            "resale_usd":    stats["median_usd"],
            "resale_count":  stats["count"],
            "premium_pct":   pct,
            "images":        stats["images"],
            "source_url":    stats["source_url"],
            "retail_source": "retail_prices",
        })

    rows.sort(key=lambda r: -r["premium_pct"])
    return rows


def _find_resale_key(model: str, resale: dict) -> str | None:
    """Find the best matching key in the resale stats dict for a given model name."""
    if model in resale:
        return model
    model_low = model.lower()
    for key in resale:
        if key.lower() == model_low:
            return key
    for key in resale:
        if model_low in key.lower() or key.lower() in model_low:
            return key
    return None


# ── Hook text ─────────────────────────────────────────────────────────────────

def _hook(row: dict) -> tuple[str, str]:
    pct    = row["premium_pct"]
    retail = _fmt_eur(row["retail_eur"])
    resale = _fmt_usd(row["resale_usd"])
    model  = row["model"]
    fmt    = dict(retail=retail, resale=resale, pct=f"+{pct:,.0f}%", model=model)

    for threshold, q_variants, a_variants in _HOOKS:
        if pct >= threshold:
            return (
                random.choice(q_variants).format(**fmt),
                random.choice(a_variants).format(**fmt),
            )
    return "the hermès secondary market.", "supply and demand."


# ── Config generation ──────────────────────────────────────────────────────────

def _generate_config(row: dict, reel_slug: str, brand: str, reveal: list[dict],
                     narration_captions: list[dict] | None = None) -> str:
    model  = row["model"]
    retail = _fmt_eur(row["retail_eur"])
    resale = _fmt_usd(row["resale_usd"])
    pct    = row["premium_pct"]

    line1 = f"retail  ·  {retail}"
    line2 = resale
    line3 = f"+{pct:,.0f}%  above retail"

    caption_full = (
        f"hermès prices the {model} at {retail} new — if they'll sell it to you. "
        f"on vestiaire today: {resale}. "
        f"that's {pct:,.0f}% above retail. "
        f"the secondary market prices what the boutique won't."
    )

    _e = reel_utils.esc
    lines = [
        '"""',
        f"╔══════════════════════════════════════════════════════════════╗",
        f"║  REEL CONFIG — {model:<44}  ║",
        f"║  Generated by scripts/hermes_reel.py                        ║",
        f"╚══════════════════════════════════════════════════════════════╝",
        '"""',
        "",
        "CONFIG = {",
        f'    "lot_id":         "{_e(reel_slug)}",',
        "",
        "    # ── Caption ────────────────────────────────────────────────",
        f'    "caption_tag":    "{_e(brand)}  ·  retail vs resale",',
        f'    "caption_line1":        "{_e(line1)}",',
        f'    "caption_line2_label":  "secondary market",',
        f'    "caption_line2":        "{_e(line2)}",',
        f'    "caption_line3":        "{_e(line3)}",',
        "",
        "    # ── Location metadata ─────────────────────────────────────",
        f'    "location_coords": "HERMÈS",',
        f'    "location_name":   "{_e(model.upper())}",',
        f'    "location_season": "{date.today().year}  ·  RESALE PREMIUM",',
        f'    "frame_label":     "{_e(brand)}",',
        "",
        "    # ── Layout ────────────────────────────────────────────────",
        '    "photo_split":        False,',
        '    "photo_fit_first":    True,',
        '    "photo_center_crop":  True,',
        '    "hide_chrome":        False,',
        '    "block_reveal":       False,',
        '    "caption_no_box":     False,',
        "",
        "    # ── Style ─────────────────────────────────────────────────",
        '    "vibe":             "auction_editorial",',
        '    "caption_position": "center",',
        "",
        "    # ── Colours ───────────────────────────────────────────────",
        "    \"color_tag\":   (245, 242, 235),",
        "    \"color_line1\": (245, 242, 235),",
        "    \"color_line2\": (196, 158, 40),",
        "    \"color_line3\": (245, 242, 235),",
        "",
        "    \"caption_all_frames\": False,",
        "    \"cover_hold_seconds\": 2.0,   # held at start for platform thumbnail auto-selection",
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
        f'        "{_e(caption_full)}"',
        "    ),",
        f'    "caption_hero":   "the boutique has one price.",',
        '    "personal_note":  "the hermès secondary market is one of the most liquid luxury resale markets in the world.",',
        '    "engagement_hook": "what\'s the biggest resale premium you\'ve ever seen?",',
    ]

    if reveal:
        lines.append("")
        lines.append("    # ── Per-frame reveal ──────────────────────────────────────")
        lines.append('    "per_frame_captions": [')
        for fc in reveal:
            lines.append("        {")
            for key, val in fc.items():
                lines.append(f"            {repr(key)}: {repr(val)},")
            lines.append("        },")
        lines.append("    ],")

    if narration_captions:
        lines.append("")
        lines.append("    # ── Word-by-word narration captions ───────────────────────")
        lines.append('    "narration_captions": [')
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

    model  = row["model"]
    retail = _fmt_eur(row["retail_eur"])
    resale = _fmt_usd(row["resale_usd"])
    pct    = row["premium_pct"]
    count  = row["resale_count"]

    _ANGLES = [
        ("the waitlist paradox",
         "Open by revealing that buying this bag at retail is nearly impossible — not because of price, but because of access. "
         "Then show how that manufactured scarcity is precisely what drives the resale premium. "
         "Close by asking what it means when a brand's distribution model is the product.",
         {"scarce_market": True}),
        ("the store of value lens",
         "Open by framing this as an asset allocation question, not a fashion one. "
         "Compare the resale premium to a conventional yield. "
         "Close by noting what the secondary market's depth signals about long-term demand.",
         {"high_premium": True}),
        ("the arbitrage gap",
         f"Open with a simple question: what happens when retail price and market price diverge by {pct:.0f}%. "
         "Walk through who captures that spread and why. "
         "Close by explaining why this gap has persisted rather than corrected.",
         {"high_premium": True, "liquid_market": True}),
        ("the brand as gatekeeper",
         "Open by describing Hermès' quota system — the reason most clients never reach the counter. "
         "Show how gatekeeping directly inflates the resale floor. "
         "Close with what this model says about scarcity as a deliberate strategy.",
         {"scarce_market": True}),
        ("the second market as price discovery",
         "Open by noting that Vestiaire Collective, not Hermès, sets the real market price. "
         "Explain why the secondary market is a more honest signal of demand than boutique retail. "
         f"Close with what {count} active listings reveal about liquidity for this model.",
         {"liquid_market": True}),
        ("the myth of depreciation",
         "Open by challenging the conventional wisdom that luxury goods lose value the moment you buy them. "
         "Use the resale premium as evidence that this bag defies that rule. "
         "Close by distinguishing between luxury consumption and luxury ownership.",
         {"high_premium": True}),
        ("the currency hedge angle",
         "Open by noting that hard assets — art, watches, Hermès — tend to hold value when currency does not. "
         "Frame the resale premium as a real-world inflation test this bag has passed. "
         "Close by asking what it says about fiat when leather trades at a premium to the price tag.",
         {"extreme_premium": True}),
        ("the buyer psychology",
         f"Open by describing the person paying {pct:.0f}% above retail — not reckless, but informed. "
         "Explain what they are actually buying: certainty of access, no boutique politics, immediate ownership. "
         "Close with what willingness to overpay reveals about the perceived cost of waiting.",
         {"high_premium": True, "scarce_market": False}),
        ("the supply ceiling",
         "Open by explaining that Hermès controls production volume as tightly as it controls distribution. "
         "Show how a fixed supply ceiling under rising demand is a mathematical guarantee of premium pricing. "
         f"Close by asking whether {count} listings represent abundance or evidence of how rarely these surface.",
         {"scarce_market": True, "extreme_premium": False}),
        ("the inheritance play",
         "Open by reframing this bag not as a purchase but as a transfer of wealth across generations. "
         "Note that the resale market provides a floor — a price the market will not go below. "
         "Close by contrasting this with other luxury categories where resale is an afterthought.",
         {"extreme_premium": True, "liquid_market": False}),
        ("the authenticity premium",
         "Open by pointing out that on the secondary market, provenance matters as much as the object itself. "
         "Explain how Hermès' tight distribution actually makes authentication easier and fraud rarer. "
         "Close with why that trust infrastructure is part of what the buyer is paying for.",
         {"liquid_market": True}),
        ("cultural capital made tangible",
         "Open through Bourdieu's lens: this bag is not just an object — it is cultural capital made physical. "
         "Explain how owning it signals membership in a field where the rules of entry are unwritten and unequal. "
         "Close by asking whether the resale premium is really a price for leather, or a price for belonging.",
         {"high_premium": True}),
        ("distinction and the field",
         "Open by invoking Bourdieu's concept of distinction — the social logic that makes taste a form of power. "
         "Show how Hermès operates at the top of the luxury field precisely because it cannot be bought by money alone. "
         "Close with what the secondary market reveals: that distinction, once acquired, is transferable.",
         {"extreme_premium": True}),
        ("symbolic violence of the waitlist",
         "Open by naming what the Hermès quota system actually is: a soft mechanism that sorts people without ever saying so. "
         "Draw on Bourdieu's idea of symbolic violence — dominance that feels like a natural order. "
         "Close by noting that the resale premium is what happens when people pay to skip a hierarchy they were never invited into.",
         {"scarce_market": True}),
        ("habitus and the luxury consumer",
         "Open by describing the Hermès buyer not as someone who wants this bag, but as someone for whom wanting it is already natural — Bourdieu's habitus at work. "
         "Explain how the brand has shaped the dispositions of its clientele over generations. "
         "Close with why the secondary market exists: for those with the economic capital but not yet the social capital to reach the counter.",
         {}),
        ("the field of luxury as a closed game",
         "Open with Bourdieu's insight that every social field has its own rules, stakes, and gatekeepers. "
         "Show how Hermès has structured its field so that money is necessary but not sufficient. "
         "Close by asking what it means that the secondary market has become the only open door — and what it costs to walk through it.",
         {"scarce_market": True, "high_premium": True}),
    ]

    _signals = {
        "high_premium":    pct > 80,
        "extreme_premium": pct > 130,
        "scarce_market":   count < 20,
        "liquid_market":   count > 50,
    }

    def _score(tags: dict) -> float:
        return sum(1 for k, v in tags.items() if _signals.get(k) == v) + random.uniform(0, 0.4)

    angle_name, angle_instruction, _ = max(_ANGLES, key=lambda a: _score(a[2]))

    prompt = f"""Write a 160-180 word voiceover script for a TikTok reel about Hermès resale prices.
It must read naturally when spoken aloud at a calm pace — exactly 60 to 70 seconds.
Do not include any preamble, label, or title — output only the script text.

Bag: {model}
Hermès retail price: {retail}
Vestiaire Collective resale median: {resale} (based on {count} listings)
Premium above retail: +{pct:.0f}%

Tone: calm, editorial, luxury finance journalist — no hype, no emojis, no hashtags.
Angle — {angle_name}:
{angle_instruction}

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
        text = re.sub(r"(?i)^(here'?s?( is)?( your)?( the)? script:?\s*)+", "", text).strip()
        print(f"  ✓ Narration generated ({len(text.split())} words)")
        return text
    except Exception as e:
        print(f"  ✗ OpenRouter error: {e}")
        return None


# ── Reveal sequence ───────────────────────────────────────────────────────────

def _build_reveal(row: dict, brand: str, n_images: int, voice_duration: float = 0.0) -> list[dict]:
    """
    3-act reveal matching auto_reel.py's structure:
      Act I   — product image; hook question displayed prominently (title frame)
      Act II  — clean product images; voice narrates
      Act III — price reveal: retail / resale / premium %

    make_reel.py's cover_hold_seconds prepends Act III as the thumbnail bait.
    """
    model  = row["model"]
    retail = _fmt_eur(row["retail_eur"])
    resale = _fmt_usd(row["resale_usd"])
    pct    = row["premium_pct"]
    hook_q, _ = _hook(row)

    tag = f"{brand}  ·  retail vs resale"

    # Timing — scale to voiceover length when available
    n_mid = max(1, n_images - 2)
    if voice_duration > 0:
        act1_s   = round(voice_duration * 0.20, 1)
        act3_s   = round(voice_duration * 0.25, 1)
        mid_each = round((voice_duration - act1_s - act3_s) / n_mid, 1)
    else:
        act1_s   = 6.0
        mid_each = round(4.0 / n_mid, 1)
        act3_s   = 10.0

    def _clean_frame(hold: float) -> dict:
        return {
            "show_caption":  False,
            "tag":           tag,
            "line1":         "",
            "line2":         "",
            "line3":         "",
            "hook_question": None,
            "hook_answer":   "",
            "upper_artist":  "",
            "upper_title":   "",
            "hold_seconds":  hold,
        }

    # Act I: hook question + model name (title frame — no price data yet)
    act1: dict = {
        "show_caption":     False,
        "tag":              tag,
        "line1":            "",
        "line2":            "",
        "line3":            "",
        "hook_question":    hook_q,
        "hook_answer":      "",
        "upper_artist":     "",
        "upper_title":      model,
        "hold_seconds":     act1_s,
    }

    # Act II: clean frames
    frames: list[dict] = [act1]
    for _ in range(n_mid):
        frames.append(_clean_frame(hold=mid_each))

    # Act III: price reveal (also used as cover thumbnail by make_reel.py)
    act3: dict = {
        "show_caption":     True,
        "caption_position": "center",
        "tag":              tag,
        "line1":            f"retail  ·  {retail}",
        "line2":            resale,
        "line3":            f"+{pct:,.0f}%  above retail",
        "hook_question":    None,
        "hook_answer":      "",
        "upper_artist":     "",
        "upper_title":      model,
        "hold_seconds":     act3_s,
    }
    frames.append(act3)

    return frames


# ── Tracking ──────────────────────────────────────────────────────────────────

def _ensure_posted_table(conn: sqlite3.Connection) -> None:
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(posted_hermes_reels)").fetchall()}

    if not existing_cols:
        conn.execute("""
            CREATE TABLE posted_hermes_reels (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                model         TEXT NOT NULL,
                retail_eur    REAL,
                resale_usd    REAL,
                premium_pct   REAL,
                resale_count  INTEGER,
                retail_source TEXT,
                source_url    TEXT,
                n_images      INTEGER,
                voice_used    INTEGER DEFAULT 0,
                brand         TEXT,
                reel_slug     TEXT,
                reel_dir      TEXT,
                posted_at     TEXT DEFAULT (datetime('now'))
            )
        """)
    elif "id" not in existing_cols:
        # Old schema had model as PRIMARY KEY — migrate to append-log with auto id
        conn.execute("ALTER TABLE posted_hermes_reels RENAME TO _posted_hermes_reels_old")
        conn.execute("""
            CREATE TABLE posted_hermes_reels (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                model         TEXT NOT NULL,
                retail_eur    REAL,
                resale_usd    REAL,
                premium_pct   REAL,
                resale_count  INTEGER,
                retail_source TEXT,
                source_url    TEXT,
                n_images      INTEGER,
                voice_used    INTEGER DEFAULT 0,
                brand         TEXT,
                reel_slug     TEXT,
                reel_dir      TEXT,
                posted_at     TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            INSERT INTO posted_hermes_reels (model, retail_eur, resale_usd, premium_pct, reel_slug, posted_at)
            SELECT model, retail_eur, resale_usd, premium_pct, reel_slug, posted_at
            FROM _posted_hermes_reels_old
        """)
        conn.execute("DROP TABLE _posted_hermes_reels_old")
        print("  ↻ Migrated posted_hermes_reels table to append-log schema.")
    else:
        # Add any columns introduced after the initial migration
        for col, col_type in [
            ("resale_count",  "INTEGER"),
            ("retail_source", "TEXT"),
            ("source_url",    "TEXT"),
            ("n_images",      "INTEGER"),
            ("voice_used",    "INTEGER DEFAULT 0"),
            ("brand",         "TEXT"),
            ("reel_dir",      "TEXT"),
        ]:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE posted_hermes_reels ADD COLUMN {col} {col_type}")

    conn.commit()


def _posted_models(conn: sqlite3.Connection) -> dict[str, str]:
    """Return {model: posted_at} for models posted within POSTED_COOLDOWN_DAYS."""
    rows = conn.execute(
        "SELECT model, posted_at FROM posted_hermes_reels "
        "WHERE posted_at >= datetime('now', ?)",
        (f"-{POSTED_COOLDOWN_DAYS} days",),
    ).fetchall()
    return {r["model"]: r["posted_at"] for r in rows}


def _record_posted(
    conn: sqlite3.Connection,
    row: dict,
    reel_slug: str,
    *,
    n_images: int = 0,
    voice_used: bool = False,
    brand: str = "",
    reel_dir: str = "",
) -> None:
    conn.execute("""
        INSERT INTO posted_hermes_reels
            (model, retail_eur, resale_usd, premium_pct, resale_count, retail_source,
             source_url, n_images, voice_used, brand, reel_slug, reel_dir, posted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        row["model"],
        row["retail_eur"],
        row["resale_usd"],
        row["premium_pct"],
        row.get("resale_count"),
        row.get("retail_source"),
        row.get("source_url", ""),
        n_images,
        int(voice_used),
        brand,
        reel_slug,
        reel_dir,
    ))
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
    posted = _posted_models(conn) if not args.all else {}
    conn.close()

    if args.model:
        candidates = [r for r in premiums if r["model"].lower() == args.model.lower()]
        if not candidates:
            candidates = [r for r in premiums if args.model.lower() in r["model"].lower()]
        if not candidates:
            print(f"✗ Model '{args.model}' not found. Use --list to see available models.")
            sys.exit(1)
        chosen = candidates[0]
    else:
        unposted = [r for r in premiums if r["model"] not in posted]
        if not unposted:
            print(f"  ℹ All models posted within {POSTED_COOLDOWN_DAYS}d cooldown — picking least-recently posted.")
            unposted = sorted(premiums, key=lambda r: posted.get(r["model"], ""))
        with_imgs = [r for r in unposted if r["images"]]
        pool = with_imgs or unposted
        # Weighted random: weight = sqrt(premium_pct) so high-premium bags are
        # favoured but not always chosen — avoids the same top model every cycle.
        weights = [max(r["premium_pct"], 1) ** 0.5 for r in pool]
        chosen = random.choices(pool, weights=weights, k=1)[0]

    print(f"\n▸ Model:         {chosen['model']}")
    print(f"  Retail:        {_fmt_eur(chosen['retail_eur'])}  ({chosen['retail_source']})")
    print(f"  Resale (med):  {_fmt_usd(chosen['resale_usd'])}  (n={chosen['resale_count']})")
    print(f"  Premium:       +{chosen['premium_pct']:,.0f}%")

    # ── Create reel folder ─────────────────────────────────────
    _model_slug = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]", "-", chosen['model'].lower())).strip("-")
    slug      = f"hermes-{_model_slug}-{date.today().isoformat()}"
    reel_dir  = REELS_DIR / slug
    img_dir   = reel_dir / "images"
    out_dir   = reel_dir / "output"

    for d in (reel_dir, img_dir, out_dir):
        d.mkdir(parents=True, exist_ok=True)

    print(f"\n▸ Reel folder:   reels/{slug}/")

    # ── Download images ────────────────────────────────────────
    print("\n▸ Downloading images...")
    saved = reel_utils.download_images(
        chosen["images"],
        reel_dir / "_src",
        headers=_VC_HEADERS,
        prime_url="https://www.vestiairecollective.com/",
    )

    if not saved:
        print("✗ No images downloaded.")
        sys.exit(1)

    # Copy into images/, converting WebP → JPEG
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
            ok, word_timestamps = reel_utils.synthesise_voiceover(
                narration, vo_path,
                elevenlabs_key=ELEVENLABS_KEY,
                voice_id=ELEVENLABS_VOICE,
                model_id=ELEVENLABS_MODEL,
                edge_voice=EDGE_TTS_VOICE,
            )
            if ok:
                voice_duration = reel_utils.audio_duration(vo_path)
                print(f"  Audio duration: {voice_duration:.1f}s")
                if not word_timestamps and voice_duration > 0:
                    word_timestamps = reel_utils.evenly_spaced_words(narration, voice_duration)
                if word_timestamps:
                    srt_path      = reel_dir / "captions.srt"
                    narr_captions = reel_utils.words_to_captions(word_timestamps)
                    reel_utils.write_srt(word_timestamps, srt_path)

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
    _record_posted(
        conn2, chosen, slug,
        n_images=n_images,
        voice_used=bool(args.voice and voice_duration > 0),
        brand=args.brand,
        reel_dir=str(reel_dir.relative_to(BUSINESS_DIR)),
    )
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

    if srt_path and srt_path.exists():
        videos = sorted(out_dir.glob("*.mp4"))
        videos = [v for v in videos if "_captioned" not in v.stem]
        if videos:
            print("\n▸ Burning word captions into video...")
            reel_utils.burn_captions(videos[0], srt_path)
        else:
            print(f"\n  ℹ No rendered video found yet — run make_reel.py first, captions will burn automatically on next run.")


if __name__ == "__main__":
    main()
