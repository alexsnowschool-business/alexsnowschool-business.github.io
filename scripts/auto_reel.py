#!/usr/bin/env python3
"""
Auto-reel generator — picks the most shocking auction results from data/art.db,
downloads artwork images, and writes a ready-to-run reel folder for
reel_template/make_reel.py.

Usage (run from alexsnowschool-business/):
    python scripts/auto_reel.py                   # uses this week's scrapes
    python scripts/auto_reel.py --week 2026-05-08 # any date in the target week
    python scripts/auto_reel.py --run             # also renders the reel + captions
    python scripts/auto_reel.py --all-time        # ignore week, pick best ever
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import httpx
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR    = Path(__file__).resolve().parent
BUSINESS_DIR  = SCRIPT_DIR.parent

load_dotenv(BUSINESS_DIR / ".env", override=False)
DB_PATH       = BUSINESS_DIR / "data" / "art.db"
REELS_DIR     = BUSINESS_DIR / "reels"
REEL_TEMPLATE = BUSINESS_DIR / "reel_template"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_price(usd: float) -> str:
    """Format a USD price compactly: $441,000 or $13.8M."""
    if usd >= 1_000_000:
        return f"${usd / 1_000_000:.1f}M"
    return f"${usd:,.0f}"


def _pct_above(hammer: float, low: float) -> float:
    return round((hammer / low - 1) * 100, 1)


def _clean_artist(name: str) -> str:
    """Strip birth-year suffix like '(B. 1953)'."""
    return re.sub(r"\s*\([^)]+\)\s*$", "", name).strip().title()


def _week_bounds(ref_date: date) -> tuple[str, str]:
    """Return (monday, sunday) as ISO strings for the week containing ref_date."""
    monday = ref_date - timedelta(days=ref_date.weekday())
    sunday = monday + timedelta(days=6)
    return monday.isoformat(), sunday.isoformat()


# ── DB queries ─────────────────────────────────────────────────────────────────

def _ensure_posted_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posted_reels (
            lot_id      TEXT PRIMARY KEY,
            artist      TEXT,
            title       TEXT,
            hammer_usd  REAL,
            reel_slug   TEXT,
            platforms   TEXT,
            posted_at   TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def _posted_ids(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT lot_id FROM posted_reels").fetchall()
    return {r[0] for r in rows}


def _query_top_lots(conn: sqlite3.Connection, week_start: str, week_end: str,
                    limit: int = 8, exclude_ids: set | None = None) -> list[dict]:
    """Top outperforming lots scraped in the given week, excluding already-posted ones."""
    exclude = tuple(exclude_ids or [])
    placeholders = ",".join("?" * len(exclude)) if exclude else "NULL"
    rows = conn.execute(f"""
        SELECT id, artist, title, hammer_usd, estimate_low, estimate_high,
               sale_name, sale_date, scraped_at, auction_house, image_urls,
               ROUND((hammer_usd * 1.0 / estimate_low - 1) * 100, 1) AS pct_above,
               source_url
        FROM art_items
        WHERE sale_performance = 'above'
          AND hammer_usd IS NOT NULL
          AND estimate_low IS NOT NULL
          AND estimate_low > 0
          AND substr(scraped_at, 1, 10) BETWEEN ? AND ?
          {"AND id NOT IN (" + placeholders + ")" if exclude else ""}
        ORDER BY pct_above DESC
        LIMIT ?
    """, (week_start, week_end, *exclude, limit)).fetchall()
    return [dict(r) for r in rows]


def _query_alltime_top(conn: sqlite3.Connection, limit: int = 8,
                       exclude_ids: set | None = None) -> list[dict]:
    """All-time top outperforming lots, excluding already-posted ones."""
    exclude = tuple(exclude_ids or [])
    placeholders = ",".join("?" * len(exclude)) if exclude else "NULL"
    rows = conn.execute(f"""
        SELECT id, artist, title, hammer_usd, estimate_low, estimate_high,
               sale_name, sale_date, scraped_at, auction_house, image_urls,
               ROUND((hammer_usd * 1.0 / estimate_low - 1) * 100, 1) AS pct_above,
               source_url
        FROM art_items
        WHERE sale_performance = 'above'
          AND hammer_usd IS NOT NULL
          AND estimate_low IS NOT NULL
          AND estimate_low > 0
          {"AND id NOT IN (" + placeholders + ")" if exclude else ""}
        ORDER BY pct_above DESC
        LIMIT ?
    """, (*exclude, limit)).fetchall()
    return [dict(r) for r in rows]


def _query_random_week_lot(conn: sqlite3.Connection,
                           exclude_ids: set | None = None) -> list[dict]:
    """Pick top lot from a random week that has unposted content."""
    exclude = tuple(exclude_ids or [])
    placeholders = ",".join("?" * len(exclude)) if exclude else "NULL"
    rows = conn.execute(f"""
        SELECT id, artist, title, hammer_usd, estimate_low, estimate_high,
               sale_name, sale_date, scraped_at, auction_house, image_urls,
               ROUND((hammer_usd * 1.0 / estimate_low - 1) * 100, 1) AS pct_above,
               source_url,
               strftime('%Y-%W', scraped_at) AS week_key
        FROM art_items
        WHERE sale_performance = 'above'
          AND hammer_usd IS NOT NULL
          AND estimate_low IS NOT NULL
          AND estimate_low > 0
          {"AND id NOT IN (" + placeholders + ")" if exclude else ""}
        GROUP BY week_key
        HAVING MAX(pct_above)
        ORDER BY RANDOM()
        LIMIT 1
    """, (*exclude,)).fetchall()
    return [dict(r) for r in rows]


def _record_posted(conn: sqlite3.Connection, lot: dict, reel_slug: str,
                   platforms: list[str]) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO posted_reels (lot_id, artist, title, hammer_usd, reel_slug, platforms)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        lot["id"], lot.get("artist"), lot.get("title"),
        lot.get("hammer_usd"), reel_slug, ",".join(platforms),
    ))
    conn.commit()
    print(f"  ✓ Recorded in posted_reels: {lot.get('artist')} — {lot.get('title')}")


# ── Image downloading ──────────────────────────────────────────────────────────

def _download_lot_images(lot: dict, images_dir: Path, max_images: int = 8) -> list[Path]:
    """Download all unique images for a single lot. Returns list of saved paths."""
    images_dir.mkdir(parents=True, exist_ok=True)
    raw_urls = json.loads(lot.get("image_urls") or "[]")

    # Deduplicate while preserving order
    seen, urls = set(), []
    for u in raw_urls:
        if u not in seen:
            seen.add(u)
            urls.append(u)

    saved: list[Path] = []
    with httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=20) as client:
        for i, url in enumerate(urls[:max_images]):
            ext   = ".jpg" if "jpg" in url.lower() or "jpeg" in url.lower() else ".png"
            fname = images_dir / f"src_{i + 1:02d}{ext}"
            try:
                r = client.get(url)
                r.raise_for_status()
                fname.write_bytes(r.content)
                print(f"  ✓ {fname.name}  (image {i + 1}/{len(urls[:max_images])})")
                saved.append(fname)
            except Exception as e:
                print(f"  ✗ {url[:60]}... — {e}")

    return saved


# ── Roman numerals ────────────────────────────────────────────────────────────

_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
          "XI", "XII", "XIII", "XIV", "XV", "XVI"]

def _roman(n: int) -> str:
    return _ROMAN[n] if n < len(_ROMAN) else str(n + 1)


# ── Per-frame captions ─────────────────────────────────────────────────────────

# Each entry: (min_pct, question, answer)
# Each entry: (min_pct, [question variants], [answer variants])
# Format vars: {artist} {title} {house} {hammer} {estimate} {pct} {n}
# Angles covered per tier: data pattern · collector psychology · market timing · catalogue vs room · price numbers
_HOOK_TEMPLATES = [
    (800,
     [
         "nobody priced this right.",
         "the estimate was wrong by {pct}.",
         "the room ignored the catalogue.",
         "{house} said {estimate}. the room said {hammer}.",
         "what does {n} above estimate tell you?",
     ],
     [
         # canon revision
         "a result this far above estimate isn't a market anomaly — it's the room rewriting the artist's place in the canon. "
         "what the catalogue priced as one thing, collectors recognized as something else entirely.",
         # legacy
         "estimates reflect what an artist has done. hammer prices reflect what collectors believe they will mean. "
         "at {n} above estimate, the room made a clear statement about {artist}'s legacy.",
         # art history rewrite
         "'{title}' walked into that room as a catalogue entry. it left as a record. "
         "that's how art history gets repriced — not in museums, but at auction.",
         # critical reappraisal
         "the specialist's estimate is built on precedent. "
         "a {pct} overshoot means the room had already moved past that precedent — "
         "and recognized something in {artist}'s work that the catalogue hadn't caught up to.",
     ]),

    (500,
     [
         "the estimate was a suggestion.",
         "a {n} result doesn't happen by accident.",
         "the catalogue missed the room by {pct}.",
         "{house} set the floor at {estimate}. the bidders ignored it.",
         "what does it mean when the market pays {hammer} for a {estimate} estimate?",
     ],
     [
         # critical moment
         "at this level, collectors aren't just buying a work — they're staking a position on the artist. "
         "the estimate reflects where {artist} has been. {hammer} is where the room thinks they're going.",
         # museum-to-market
         "results like this happen when critical and market consensus finally align. "
         "a museum moment, a major publication, a retrospective — something shifted the conversation before this sale, and the room responded.",
         # provenance
         "provenance and period matter at this price. "
         "'{title}' carried a history the estimate didn't fully price — and the room understood what it was acquiring.",
         # artist significance
         "a {pct} overshoot of this scale is a verdict on an artist's significance. "
         "the catalogue reflects the past record. the hammer is the new one.",
     ]),

    (300,
     [
         "the catalogue got this wrong by {pct}.",
         "the specialists underestimated the room.",
         "priced for safety. sold for ambition.",
         "from {estimate} to {hammer} — what changed?",
         "why does {artist} keep beating estimate?",
     ],
     [
         # critical reappraisal
         "auction rooms reprice artists faster than institutions do. "
         "{artist} had been estimated on old assumptions — the room corrected them.",
         # period and movement
         "the estimate was set by precedent. the room was pricing on where {artist} now sits in the conversation — "
         "and that's a very different number.",
         # collector conviction
         "a result {pct} above estimate means someone arrived with deep knowledge of the work and the artist. "
         "that kind of conviction — anchored in research, not sentiment — is what moves an artist's market.",
         # legacy building
         "the low estimate was {estimate}. it sold for {hammer}. "
         "that gap is enough to reset the artist's record, shift the reference point for every future valuation, and start a new chapter.",
     ]),

    (150,
     [
         "the room disagreed with the experts.",
         "the house priced it low. the room priced it right.",
         "conviction beat the catalogue.",
         "{estimate} estimate. {hammer} reality.",
         "why did this sell for {pct} above estimate?",
     ],
     [
         # art historical moment
         "the estimate is built from past sales. "
         "when the room bids {pct} above that, it's saying: the past doesn't tell the full story of this artist anymore.",
         # collector knowledge
         "serious collectors don't bid on estimates — they bid on their own research. "
         "a {pct} overshoot usually means someone in that room understood {artist}'s significance better than the catalogue did.",
         # market recognition
         "the auction house priced {artist} conservatively. "
         "the room disagreed — and when a room this competitive disagrees, the result becomes the new reference point.",
         # period significance
         "'{title}' is from a period in {artist}'s career that the market has been reassessing. "
         "the {pct} overshoot reflects that — a work carrying more weight than the estimate assumed.",
     ]),

    (80,
     [
         "the room knew something the catalogue didn't.",
         "more buyers arrived than the estimate assumed.",
         "the market priced what the house wouldn't.",
         "{pct} above estimate — is that a pattern or a fluke?",
         "the estimate was {estimate}. the hammer was {hammer}.",
     ],
     [
         # quality recognition
         "the estimate is a floor, not a forecast. "
         "when the room bids above it, it usually means the work carried more quality — or more significance — than the catalogue captured.",
         # artist momentum
         "{artist}'s presence in major collections and exhibitions has been building. "
         "a {pct} overshoot confirms the market has been paying attention.",
         # work significance
         "'{title}' outperformed because the room valued what it is, not just what {artist} has sold for before. "
         "the estimate anchors on history. the hammer reflects the present.",
         # collector demand
         "when two serious collectors want the same work, the estimate becomes irrelevant. "
         "what matters is who understands the artist's importance — and who wants to own a piece of it.",
     ]),

    (40,
     [
         "priced to sell. sold for more.",
         "above estimate — the most common story in the room.",
         "the floor held. the ceiling didn't.",
         "from {estimate} to {hammer} — small gap, real signal.",
         "the room had more conviction than the catalogue.",
     ],
     [
         # consistent demand
         "a result above estimate — even modestly — confirms that demand for {artist}'s work is real and consistent. "
         "the catalogue sets the floor. the room decides the ceiling.",
         # artist standing
         "the estimate reflects what specialists expected based on precedent. "
         "{hammer} is what collectors in that room were willing to pay — and that's always the more honest number.",
         # work quality
         "when a work sells above estimate, it's usually because the room found something in it the catalogue missed — "
         "quality, condition, period, or simply the right buyer at the right moment.",
         # market signal
         "a modest overshoot like this is quiet but meaningful. "
         "it tells you demand is ahead of where the specialists priced {artist}'s market.",
     ]),

    (0,
     [
         "above estimate — even here.",
         "the floor held. just.",
         "sold above the low estimate.",
         "{hammer} on a {estimate} estimate.",
         "even a small overshoot tells a story.",
     ],
     [
         # demand signal
         "even a small overshoot confirms there was more than one serious buyer in the room. "
         "for {artist}, that demand matters — it keeps the market active and the next estimate honest.",
         # collector interest
         "the estimate is a starting point. the hammer is the truth. "
         "here, the truth was just a little higher than the catalogue expected — and that's enough to move the conversation.",
         # artist market
         "a result above estimate — however modest — means the market for {artist} is healthy. "
         "collectors are paying attention, and competition, even at this level, is a signal worth reading.",
         # historical record
         "every lot that sells above estimate becomes part of an artist's price history. "
         "'{title}' just added one more data point — and it moved in the right direction.",
     ]),
]


def _split_phrases(text: str) -> list[str]:
    """Split answer text into sentence fragments for phrase-by-phrase reveal."""
    import re
    parts = re.split(r'(?<=\.) ', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _hook_caption(lot: dict, pct: float) -> tuple[str, str]:
    """Return (question, answer) — randomly selected from per-tier variants."""
    import random
    mult     = round(pct / 100 + 1, 1)
    artist   = _clean_artist(lot.get("artist") or "Unknown")
    title    = (lot.get("title") or "Untitled")[:40]
    house    = (lot.get("auction_house") or "the auction house")
    hammer   = _fmt_price(lot["hammer_usd"])
    est_low  = lot["estimate_low"]
    est_high = lot.get("estimate_high") or est_low
    estimate = f"{_fmt_price(est_low)}–{_fmt_price(est_high)}"

    fmt = dict(
        n=f"{mult:.0f}×",
        artist=artist,
        title=title,
        house=house,
        hammer=hammer,
        estimate=estimate,
        pct=f"{pct:,.0f}%",
    )

    for threshold, q_variants, a_variants in _HOOK_TEMPLATES:
        if pct >= threshold:
            question = random.choice(q_variants).format(**fmt)
            answer   = random.choice(a_variants).format(**fmt)
            return question, answer

    return "the hammer price tells the real story.", "follow the data."


def _build_reveal_sequence(lot: dict, tag_base: str, ai_answer: str | None = None,
                           tts_duration: float = 0.0) -> list[dict]:
    """Progressive reveal for a single lot — targets ~25s total.

    Frames:
      1 — estimate + sold price (hook lands immediately)
      2 — full data box (+ % above estimate)
      3 — question appears large (no answer yet)
      4+ — answer reveals word-by-word (AI-generated or template fallback)
    """
    hammer        = lot["hammer_usd"]
    est_low       = lot["estimate_low"]
    est_high      = lot.get("estimate_high") or est_low
    pct           = _pct_above(hammer, est_low)
    artist_name   = _clean_artist(lot.get("artist") or "Unknown")
    painting_title = (lot.get("title") or "Untitled")

    tag   = f"{tag_base}  ·  lot I"
    E     = f"estimate: {_fmt_price(est_low)}–{_fmt_price(est_high)}"
    S     = f"sold: {_fmt_price(hammer)}."
    P     = f"+{pct:,.0f}% above estimate."

    question, template_answer = _hook_caption(lot, pct)
    answer  = ai_answer or template_answer
    phrases = _split_phrases(answer)

    def _data(line1="", line2="", line3="", q=None, a="", hold=4.0):
        return {
            "show_caption":  bool(line1 or line2 or line3),
            "tag":           tag,
            "line1":         line1,
            "line2":         line2,
            "line3":         line3,
            "hook_question": q,
            "hook_answer":   a,
            "upper_artist":  artist_name,
            "upper_title":   painting_title,
            "hold_seconds":  hold,
        }

    frames = [
        # 1 — estimate + sold price open together (hook lands immediately, short hold)
        _data(line1=E, line2=S, hold=2.0),
        # 2 — outperformance % completes the data box
        _data(line1=E, line2=S, line3=P),
        # 3 — question appears large (no answer yet)
        _data(line1=E, line2=S, line3=P, q=question, hold=4.0),
    ]

    # Answer reveal: one frame per phrase; final frame hold driven by TTS duration
    for j in range(len(phrases)):
        partial = " ".join(phrases[:j + 1])
        if j < len(phrases) - 1:
            hold = 3.0
        else:
            if tts_duration > 0:
                hold = round(tts_duration + 2.0, 1)   # TTS duration + 2s reading tail
            else:
                n_words = len(partial.split())
                hold = max(8.0, round((n_words * 2) / 3 + 2, 1))
        frames.append(_data(line1=E, line2=S, line3=P, q=question, a=partial, hold=hold))

    return frames


# ── Config generation ──────────────────────────────────────────────────────────

def _generate_config(hook: dict, week_label: str, all_time: bool, reveal: list[dict] | None = None) -> str:
    artist    = _clean_artist(hook.get("artist") or "Unknown")
    title     = (hook.get("title") or "Untitled")[:50]
    hammer    = hook["hammer_usd"]
    est_low   = hook["estimate_low"]
    est_high  = hook.get("estimate_high") or est_low
    pct       = _pct_above(hammer, est_low)
    house     = hook.get("auction_house") or "Auction House"
    sale_name = (hook.get("sale_name") or "Contemporary Sale")[:40]
    scraped   = (hook.get("scraped_at") or "")[:10]

    est_str    = f"estimate: {_fmt_price(est_low)}–{_fmt_price(est_high)}"
    sold_str   = f"sold: {_fmt_price(hammer)}."
    pct_str    = f"+{pct:,.0f}% above estimate."

    tag_line   = "@thehammerprice  ·  weekly results" if not all_time else "@thehammerprice  ·  auction data"
    house_upper = house.upper()
    sale_upper  = sale_name.upper()

    caption_full_line1 = f"the auction house said {_fmt_price(est_low)}. the room said {_fmt_price(hammer)}."
    caption_full_line2 = (
        f"{artist}'s '{title}' — +{pct:,.0f}% above the low estimate. "
        f"this is what happens when the data knows something the catalogue doesn't."
    )
    personal_note = (
        "51% of lots at the major houses sell above estimate. "
        "that's not randomness — it's a pattern, and it's exploitable."
    )
    engagement_hook = (
        "what's the biggest auction surprise you've ever seen? "
        "drop the lot in the comments #thehammerprice #artmarket #auctionresults"
    )

    lot_id = hook.get("id", "")

    lines = [
        '"""',
        "╔══════════════════════════════════════════════════════════════╗",
        f"║  REEL CONFIG — auto-generated for week {week_label}",
        f"║  Hook lot: {artist} — {title[:30]}",
        "║  Generated by scripts/auto_reel.py",
        "╚══════════════════════════════════════════════════════════════╝",
        '"""',
        "",
        "CONFIG = {",
        f'    "lot_id":         "{lot_id}",',
        "    # ── Caption — The Shock Number ────────────────────────────",
        f'    "caption_tag":    "{tag_line}",',
        f'    "caption_line1":  "{est_str}",',
        f'    "caption_line2":  "{sold_str}",',
        f'    "caption_line3":  "{pct_str}",',
        "",
        "    # ── Location metadata ─────────────────────────────────────",
        f'    "location_coords": "{house_upper}",',
        f'    "location_name":   "{sale_upper}",',
        f'    "location_season": "{scraped[:4]}  ·  SALE RESULT",',
        '    "frame_label":     "@thehammerprice",',
        "",
        "    # ── Style ─────────────────────────────────────────────────",
        '    "vibe":             "auction_editorial",',
        '    "caption_position": "center",',
        "",
        "    # ── Font overrides ─────────────────────────────────────────",
        '    "fonts_override": {',
        '        "serif_lg":   ("InstrumentSerif-Regular.ttf", 82),',
        '        "serif_med":  ("InstrumentSerif-Regular.ttf",  58),',
        '        "italic_med": ("InstrumentSerif-Italic.ttf",  40),',
        '        "mono":       ("IBMPlexMono-Regular.ttf",      17),',
        '        "mono_sm":    ("IBMPlexMono-Regular.ttf",      14),',
        "    },",
        "",
        "    # ── Per-line colours ──────────────────────────────────────",
        "    \"color_line1\": (210, 200, 178),",
        "    \"color_line2\": (201, 168, 76),",
        "    \"color_line3\": (230, 215, 175),",
        "",
        "    \"caption_all_frames\": False,",
        "",
        "    # ── Pacing — 3fps, ~25s (5 frames × 4s + 4 × 0.5s fade) ───",
        "    \"fps\":          3,",
        "    \"hold_seconds\": 4.0,",
        "    \"fade_seconds\": 0.5,",
        "",
        "    # ── Captions metadata ─────────────────────────────────────",
        '    "topic":          "culture",',
        f'    "location":       "{house}",',
        f'    "season":         "{scraped[:4]}",',
        '    "caption_full":   (',
        f'        "{caption_full_line1}\\n\\n"',
        f'        "{caption_full_line2}"',
        "    ),",
        '    "caption_hero":   "they priced it wrong",',
        f'    "personal_note":  "{personal_note}",',
        f'    "engagement_hook": "{engagement_hook}",',
    ]

    # ── per_frame_captions (reveal sequence) ─────────────────
    if reveal:
        lines.append("")
        lines.append("    # ── Progressive reveal — one entry per frame ─────────────")
        lines.append("    \"per_frame_captions\": [")
        for fc in reveal:
            lines.append("        {")
            for key, val in fc.items():
                lines.append(f'            {repr(key)}: {repr(val)},')
            lines.append("        },")
        lines.append("    ],")

    lines.append("}")
    return "\n".join(lines) + "\n"


# ── AI caption writer ──────────────────────────────────────────────────────────

def _write_ai_captions(captions: dict, reel_dir: Path, lot: dict) -> None:
    """Write AI-generated captions in the same captions.md format as make_captions.py."""
    from datetime import datetime
    out = reel_dir / "output" / "captions.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    artist = lot.get("artist", "Unknown")
    house  = lot.get("auction_house", "Auction")
    year   = datetime.now().year
    ig_times = "Tue–Fri, 11am–1pm or 7–9pm (your local time)"
    tt_times = "Tue–Thu 7–9pm or Sat morning (your local time)"
    with open(out, "w") as f:
        f.write(f"# Social Media Captions\n")
        f.write(f"*{artist} · {house} · {year}*\n\n---\n\n")
        f.write("## 📸 Instagram\n\n")
        f.write(f"**Best time to post:** {ig_times}\n")
        f.write(f"**Cover image:** `output/reel.png`\n\n")
        f.write("### Caption\n\n```\n")
        f.write(captions["instagram"])
        f.write("\n```\n\n---\n\n")
        f.write("## 🎵 TikTok\n\n")
        f.write(f"**Best time to post:** {tt_times}\n")
        f.write(f"**Video:** `output/reel.mp4`\n\n")
        f.write("### Caption\n\n```\n")
        f.write(captions["tiktok"])
        f.write(f"\n```\n\n---\n*Generated {datetime.now().strftime('%B %d, %Y')} · AI*\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-generate a reel from weekly art auction data")
    parser.add_argument("--week",      default=None, help="ISO date in target week (default: today)")
    parser.add_argument("--all-time",  action="store_true", help="Use all-time top lots instead of weekly")
    parser.add_argument("--run",       action="store_true", help="Run make_reel.py + make_captions.py after generation")
    parser.add_argument("--top-n",     type=int, default=8, help="Max lots to query (default: 8)")
    parser.add_argument("--lot-index", type=int, default=0, help="Which lot to use (0 = top, 1 = 2nd, etc.)")
    args = parser.parse_args()

    # ── Resolve week ───────────────────────────────────────────
    ref_date   = date.fromisoformat(args.week) if args.week else date.today()
    week_start, week_end = _week_bounds(ref_date)
    week_label = f"{week_start} / {week_end}"
    reel_slug  = f"weekly-{week_start}"

    print("═" * 60)
    print("  AUTO-REEL GENERATOR — The Hammer Price")
    if args.all_time:
        print("  Mode: all-time top outperformers")
    else:
        print(f"  Week: {week_label}")
    print("═" * 60)

    if not DB_PATH.exists():
        print(f"✗ Database not found: {DB_PATH}")
        sys.exit(1)

    # ── Query lots ─────────────────────────────────────────────
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _ensure_posted_table(conn)
    skip = _posted_ids(conn)
    if skip:
        print(f"\n  ℹ Skipping {len(skip)} already-posted lot(s).")

    top_n = max(args.top_n, args.lot_index + 1)
    if args.all_time:
        lots = _query_alltime_top(conn, limit=top_n, exclude_ids=skip)
        reel_slug = f"weekly-{date.today().isoformat()}-alltime"
    else:
        lots = _query_top_lots(conn, week_start, week_end, limit=top_n, exclude_ids=skip)
        if not lots:
            print(f"\n  No new data for week {week_label} — trying random unposted week...")
            rand = _query_random_week_lot(conn, exclude_ids=skip)
            if rand:
                # re-query that week's top lots
                w = rand[0]["scraped_at"][:10]
                wb_start, wb_end = _week_bounds(date.fromisoformat(w))
                lots = _query_top_lots(conn, wb_start, wb_end, limit=top_n, exclude_ids=skip)
                reel_slug = f"weekly-{wb_start}-random"
                print(f"  Using random week: {wb_start}")
            if not lots:
                print("  Falling back to all-time top unposted lots.")
                lots = _query_alltime_top(conn, limit=top_n, exclude_ids=skip)
                reel_slug = f"weekly-{week_start}-fallback"
    conn.close()

    if not lots:
        print("✗ No suitable lots found in database.")
        sys.exit(1)

    if args.lot_index >= len(lots):
        print(f"✗ --lot-index {args.lot_index} out of range (only {len(lots)} lots found)")
        sys.exit(1)

    if args.lot_index > 0:
        reel_slug = reel_slug.replace("alltime", f"alltime-lot{args.lot_index + 1}")
        reel_slug = reel_slug.replace("fallback", f"fallback-lot{args.lot_index + 1}")
        if "alltime" not in reel_slug and "fallback" not in reel_slug:
            reel_slug += f"-lot{args.lot_index + 1}"

    hook = lots[args.lot_index]
    artist = _clean_artist(hook.get("artist") or "Unknown")
    print(f"\n▸ Hook lot: {artist} — {hook.get('title', 'Untitled')[:50]}")
    print(f"  Estimate: {_fmt_price(hook['estimate_low'])}–{_fmt_price(hook.get('estimate_high') or hook['estimate_low'])}")
    print(f"  Hammer:   {_fmt_price(hook['hammer_usd'])}")
    print(f"  Result:   +{_pct_above(hook['hammer_usd'], hook['estimate_low']):,.0f}% above estimate")
    print(f"  House:    {hook.get('auction_house')}")

    # ── Create reel folder ─────────────────────────────────────
    reel_dir   = REELS_DIR / reel_slug
    images_dir = reel_dir / "images"
    output_dir = reel_dir / "output"

    reel_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n▸ Reel folder: {reel_dir}")

    # ── Download all images of the single hook lot ─────────────
    print(f"\n▸ Downloading images for hook lot...")
    src_images = _download_lot_images(hook, reel_dir / "_src", max_images=8)

    if not src_images:
        print("✗ No images downloaded — cannot generate reel.")
        sys.exit(1)

    # ── Build reveal sequence ──────────────────────────────────
    tag_base = "@thehammerprice  ·  weekly results" if not args.all_time else "@thehammerprice  ·  auction data"

    # Try AI-generated art history answer for the hook; fall back to template if unavailable
    ai_hook_answer = None
    if os.getenv("OPENROUTER_API_KEY"):
        try:
            sys.path.insert(0, str(SCRIPT_DIR))
            from ai_content import generate_hook_answer
            _pct = _pct_above(hook["hammer_usd"], hook["estimate_low"])
            _question, _tmpl_answer = _hook_caption(hook, _pct)
            _lot_preview = {
                "artist":       _clean_artist(hook.get("artist") or "Unknown"),
                "title":        (hook.get("title") or "Untitled")[:60],
                "auction_house": hook.get("auction_house") or "the auction house",
                "hammer_fmt":   _fmt_price(hook["hammer_usd"]),
                "estimate_fmt": f"{_fmt_price(hook['estimate_low'])}–{_fmt_price(hook.get('estimate_high') or hook['estimate_low'])}",
                "pct_above":    _pct,
            }
            print("\n▸ Generating AI hook answer...")
            ai_hook_answer = generate_hook_answer(_lot_preview, _question)
            if ai_hook_answer:
                print(f"  ✓ AI answer: {ai_hook_answer[:80]}...")
            else:
                print("  ⚠ AI hook answer failed — using template")
                ai_hook_answer = _tmpl_answer  # use template so TTS and video match
        except Exception as e:
            print(f"  ⚠ AI hook answer error: {e} — using template")
            _pct2 = _pct_above(hook["hammer_usd"], hook["estimate_low"])
            _, ai_hook_answer = _hook_caption(hook, _pct2)

    # ── Generate voiceover with word timestamps ────────────────
    # TTS narrates only the answer text; audio is offset to start
    # at the same moment the answer frame appears on screen.
    voiceover_path = str(reel_dir / "voiceover.mp3")
    word_timings   = []
    tts_duration   = 0.0
    print("\n▸ Generating voiceover...")
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from ai_content import generate_voiceover
        ok, word_timings = generate_voiceover(ai_hook_answer or "", voiceover_path)
        if ok and word_timings:
            tts_duration = word_timings[-1]["start"] + 1.5   # last word + 1.5s tail
            print(f"  ✓ Voiceover saved ({tts_duration:.1f}s, {len(word_timings)} words)")
        else:
            voiceover_path = None
            print("  ⚠ Voiceover failed")
    except Exception as e:
        print(f"  ⚠ Voiceover error: {e}")
        voiceover_path = None

    # Build reveal — pass tts_duration so the answer frame hold fits the audio
    reveal = _build_reveal_sequence(hook, tag_base, ai_answer=ai_hook_answer,
                                    tts_duration=tts_duration)

    # Calculate how many seconds of video play before the first answer frame,
    # so the audio can be offset to start exactly when answer words appear.
    _fade_s = 0.5   # matches config fade_seconds
    _pre_frames = [fc for fc in reveal if not fc.get("hook_answer")]
    audio_offset = (sum(fc["hold_seconds"] for fc in _pre_frames)
                    + len(_pre_frames) * _fade_s)

    # Save timing data for make_reel.py
    import json as _json
    timing_data = {"audio_offset": round(audio_offset, 3), "word_timings": word_timings}
    (reel_dir / "voiceover_timing.json").write_text(_json.dumps(timing_data, indent=2))

    # Map each reveal frame to an image file (cycle through available sources)
    import shutil
    for i, _ in enumerate(reveal):
        src  = src_images[i % len(src_images)]
        dest = images_dir / f"frame_{i + 1:02d}{src.suffix}"
        shutil.copy2(src, dest)
    n_images = len(reveal)
    print(f"  {len(src_images)} source image(s) → {n_images} frames")

    # ── Write reel_config.py ───────────────────────────────────
    config_path = reel_dir / "reel_config.py"
    config_src  = _generate_config(hook, week_label, args.all_time, reveal=reveal)
    config_path.write_text(config_src)
    print(f"\n▸ Config written: {config_path}")

    # ── Summary ────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("  READY TO RENDER")
    print(f"  Reel folder: reels/{reel_slug}/")
    print(f"  Frames: {n_images} (progressive reveal)")
    print()
    print("  To render:")
    print(f"    cd ../reel-automation")
    print(f"    python reel_template/make_reel.py reels/{reel_slug}")
    print(f"    python reel_template/make_captions.py reels/{reel_slug}")
    print("═" * 60)

    # ── Optionally run ─────────────────────────────────────────
    if args.run:
        reel_automation = REEL_TEMPLATE.parent
        print("\n▸ Running make_reel.py...")
        r1 = subprocess.run(
            [sys.executable, str(REEL_TEMPLATE / "make_reel.py"), str(reel_dir)],
            cwd=str(reel_automation),
        )
        if r1.returncode == 0:
            # Try AI captions first, fall back to template-based make_captions.py
            ai_done = False
            if os.getenv("OPENROUTER_API_KEY"):
                print("\n▸ Generating AI captions via OpenRouter...")
                try:
                    sys.path.insert(0, str(SCRIPT_DIR))
                    from ai_content import generate_captions, generate_art_history
                    hammer   = hook["hammer_usd"]
                    est_low  = hook["estimate_low"]
                    est_high = hook.get("estimate_high") or est_low
                    pct      = _pct_above(hammer, est_low)
                    lot_data = {
                        "artist":       _clean_artist(hook.get("artist") or "Unknown"),
                        "title":        (hook.get("title") or "Untitled")[:60],
                        "auction_house": hook.get("auction_house") or "the auction house",
                        "hammer_fmt":   _fmt_price(hammer),
                        "estimate_fmt": f"{_fmt_price(est_low)}–{_fmt_price(est_high)}",
                        "pct_above":    pct,
                        "sale_name":    (hook.get("sale_name") or "").strip(),
                        "source_url":   (hook.get("source_url") or "").strip(),
                    }
                    captions = generate_captions(lot_data)
                    if captions:
                        # Append art history to the Instagram caption body
                        art_history = generate_art_history(lot_data)
                        if art_history:
                            captions["instagram"] = captions["instagram"].replace(
                                "\n\n#thehammerprice",
                                f"\n\n{art_history}\n\n#thehammerprice",
                            )
                        _write_ai_captions(captions, reel_dir, lot_data)
                        ai_done = True
                        print("  ✓ AI captions saved")
                    else:
                        print("  ⚠ AI generation failed — falling back to templates")
                except Exception as e:
                    print(f"  ⚠ AI captions error: {e} — falling back to templates")

            if not ai_done:
                print("\n▸ Running make_captions.py...")
                subprocess.run(
                    [sys.executable, str(REEL_TEMPLATE / "make_captions.py"), str(reel_dir)],
                    cwd=str(reel_automation),
                )


if __name__ == "__main__":
    main()
