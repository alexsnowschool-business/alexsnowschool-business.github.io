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
from PIL import Image
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
    """Format a USD price with full zeros: $441,000 or $1,380,000."""
    return f"${usd:,.0f}"


def _fmt_price_tts(usd: float) -> str:
    """Spoken-English price for TTS — no symbols or commas that confuse synthesizers."""
    if usd >= 1_000_000:
        return f"{usd / 1_000_000:.1f} million dollars"
    if usd >= 1_000:
        return f"{usd / 1_000:.0f} thousand dollars"
    return f"{usd:.0f} dollars"


def _prices_to_speech(text: str) -> str:
    """Replace $X,XXX-style price tokens in arbitrary text with their spoken form."""
    import re as _re
    def _sub(m: "_re.Match") -> str:
        digits = m.group(1).replace(",", "")
        return _fmt_price_tts(float(digits))
    return _re.sub(r"\$([0-9][0-9,]*)", _sub, text)


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


def _build_notable_artists_set(conn: sqlite3.Connection) -> set[str]:
    """Artists with ≥2 records OR avg hammer > $50k — signals naratable market depth."""
    rows = conn.execute("""
        SELECT artist
        FROM art_items
        WHERE hammer_usd IS NOT NULL AND artist IS NOT NULL
        GROUP BY artist
        HAVING COUNT(*) >= 2 OR AVG(hammer_usd) > 50000
    """).fetchall()
    return {_clean_artist(r[0]) for r in rows if r[0]}


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


def _generate_grid_crops(src_paths: list[Path], crops_dir: Path, include_original: bool = True, target_size: tuple[int,int] | None = None) -> list[Path]:
    """Generate center + corner square crops for each source image.
    Returns a list of Paths in order: original, center, top_left, top_right, bottom_left, bottom_right for each source.
    """
    crops_dir.mkdir(parents=True, exist_ok=True)
    result: list[Path] = []
    for src in src_paths:
        try:
            with Image.open(src) as im:
                im = im.convert("RGB")
                w, h = im.size
                side = min(w, h)
                positions = {
                    "center": ((w - side) // 2, (h - side) // 2),
                    "top_left": (0, 0),
                    "top_right": (w - side, 0),
                    "bottom_left": (0, h - side),
                    "bottom_right": (w - side, h - side),
                }
                if include_original:
                    result.append(src)
                for name, (left, top) in positions.items():
                    box = (left, top, left + side, top + side)
                    crop = im.crop(box)
                    if target_size:
                        crop = crop.resize(target_size, Image.LANCZOS)
                    out_name = f"{src.stem}_crop_{name}{src.suffix}"
                    out_path = crops_dir / out_name
                    crop.save(out_path, quality=95)
                    result.append(out_path)
        except Exception as e:
            print(f"  ⚠ Crop failed for {src.name}: {e}")
            if include_original and src not in result:
                result.append(src)
    return result

def _generate_sliding_window_crops(src_paths: list[Path], crops_dir: Path, tile_size: int = 256, stride: int | None = None, include_original: bool = True) -> list[Path]:
    """Generate overlapping square tiles (sliding window) for each source image.
    tile_size: size in pixels of each square tile
    stride: step between tiles in pixels; if None defaults to tile_size // 2
    """
    crops_dir.mkdir(parents=True, exist_ok=True)
    result: list[Path] = []
    for src in src_paths:
        try:
            with Image.open(src) as im:
                im = im.convert("RGB")
                w, h = im.size
                ts = min(tile_size, w, h)
                st = stride or max(1, ts // 2)
                # compute x positions
                xs = []
                if w <= ts:
                    xs = [0]
                else:
                    x = 0
                    while x <= w - ts:
                        xs.append(x)
                        x += st
                    if xs[-1] != w - ts:
                        xs.append(w - ts)
                # compute y positions
                ys = []
                if h <= ts:
                    ys = [0]
                else:
                    y = 0
                    while y <= h - ts:
                        ys.append(y)
                        y += st
                    if ys[-1] != h - ts:
                        ys.append(h - ts)
                if include_original:
                    result.append(src)
                for x in xs:
                    for y in ys:
                        box = (x, y, x + ts, y + ts)
                        crop = im.crop(box)
                        out_name = f"{src.stem}_tile_{ts}_{x}_{y}{src.suffix}"
                        out_path = crops_dir / out_name
                        crop.save(out_path, quality=95)
                        result.append(out_path)
        except Exception as e:
            print(f"  ⚠ Sliding crop failed for {src.name}: {e}")
            if include_original and src not in result:
                result.append(src)
    return result

# ── Roman numerals ────────────────────────────────────────────────────────────

_ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
          "XI", "XII", "XIII", "XIV", "XV", "XVI"]

# ── Known-artist list (curated blue-chip / naratable names) ──────────────────

_KNOWN_ARTISTS: frozenset[str] = frozenset({
    # Post-war American
    "Andy Warhol", "Roy Lichtenstein", "Jasper Johns", "Robert Rauschenberg",
    "Ed Ruscha", "Frank Stella", "Ellsworth Kelly", "Donald Judd",
    "Cy Twombly", "Joan Mitchell", "Lee Krasner", "Helen Frankenthaler",
    # Neo-expressionism / street
    "Jean-Michel Basquiat", "Keith Haring", "George Condo",
    # YBA / British
    "Damien Hirst", "Jenny Saville", "Chris Ofili", "Glenn Brown",
    "Cecily Brown", "Peter Doig", "Lucian Freud", "Francis Bacon",
    # German / European
    "Gerhard Richter", "Neo Rauch", "Luc Tuymans", "Marlene Dumas",
    "Rudolf Stingel", "Albert Oehlen", "Pierre Soulages",
    # Contemporary market names
    "Jeff Koons", "Richard Prince", "Christopher Wool", "Mark Bradford",
    "Kerry James Marshall", "Jonas Wood", "Lisa Yuskavage",
    "Banksy", "KAWS", "Takashi Murakami", "Yoshitomo Nara", "Yayoi Kusama",
    "Wolfgang Tillmans", "Andreas Gursky", "Cindy Sherman", "Barbara Kruger",
    # Post-Impressionist / Modern (auction staples)
    "Alberto Giacometti", "Jean Dubuffet", "Yves Klein",
    "Emil Nolde", "Ernst Ludwig Kirchner",
})

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


def _get_audio_duration(path: str) -> float:
    """Return audio duration in seconds via ffprobe, or 0.0 on failure."""
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return 0.0
    try:
        import json as _json
        for s in _json.loads(r.stdout).get("streams", []):
            if s.get("duration"):
                return float(s["duration"])
    except Exception:
        pass
    return 0.0


_VOICE_GAP_SECONDS = 0.4  # minimum silence inserted between consecutive voice clips


def _build_sequential_voiceover(
    frame_tracks: list[tuple[str, float]],  # (path, target_start_seconds) — all clips
    output_path: str,
) -> bool:
    """
    Build voiceover.mp3 entirely via silence-padding concat — no amix.
    Each clip (intro, gavel SFX, frame narration, answer) is placed at its exact
    video timestamp by inserting anullsrc silence before it, then all segments
    are concatenated in one ffmpeg pass.
    """
    valid = [(p, t) for p, t in frame_tracks if os.path.exists(p)]
    if not valid:
        print("  ⚠ No audio tracks to build voiceover")
        return False

    valid.sort(key=lambda x: x[1])

    cmd = ["ffmpeg", "-y"]
    raw_labels: list[str] = []
    input_idx = 0
    current_time = 0.0

    for path, target_start in valid:
        # Enforce a minimum breathing gap between consecutive voice clips
        effective_start = max(target_start, current_time + _VOICE_GAP_SECONDS) if current_time > 0.0 else target_start
        gap = effective_start - current_time
        if gap > 0.02:
            cmd += ["-f", "lavfi", "-t", f"{gap:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
            raw_labels.append(f"[{input_idx}:a]")
            input_idx += 1
        cmd += ["-i", path]
        raw_labels.append(f"[{input_idx}:a]")
        input_idx += 1
        current_time = effective_start + _get_audio_duration(path)

    # Normalize all segments to 44100 Hz stereo before concat
    filter_parts: list[str] = []
    norm_labels: list[str] = []
    for k, lbl in enumerate(raw_labels):
        nl = f"n{k}"
        filter_parts.append(
            f"{lbl}aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[{nl}]"
        )
        norm_labels.append(f"[{nl}]")

    n = len(norm_labels)
    if n == 1:
        filter_parts[-1] = filter_parts[-1].replace("[n0]", "[out]")
    else:
        joined = "".join(norm_labels)
        filter_parts.append(f"{joined}concat=n={n}:v=0:a=1[out]")

    cmd += ["-filter_complex", ";".join(filter_parts),
            "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", "192k", output_path]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ⚠ Voiceover build error: {r.stderr[-400:]}")
        return False
    print(f"  ✓ Sequential voiceover ({len(valid)} clip(s)) → {Path(output_path).name}")
    return True


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


# ── Lot scoring ───────────────────────────────────────────────────────────────

def _artist_is_notable(artist: str, notable_set: set[str] | None = None) -> bool:
    """True if the artist is naratable — either in the curated list or has DB market depth."""
    cleaned = _clean_artist(artist)
    if notable_set and cleaned in notable_set:
        return True
    # Case-insensitive substring match against the curated list
    cleaned_lower = cleaned.lower()
    return any(
        k.lower() in cleaned_lower or cleaned_lower in k.lower()
        for k in _KNOWN_ARTISTS
    )


def _score_lot(lot: dict, notable_set: set[str] | None = None) -> float:
    """Composite score: market shock + visual richness + artist narability."""
    pct        = _pct_above(lot["hammer_usd"], lot["estimate_low"])
    has_images = len(json.loads(lot.get("image_urls") or "[]")) >= 3
    is_known   = _artist_is_notable(lot.get("artist") or "", notable_set)
    return pct * 0.4 + (has_images * 30) + (is_known * 20)


_MAX_REEL_SECONDS = 20.0
_FRAME_FADE_S     = 0.1


def _build_reveal_sequence(lot: dict, tag_base: str, ai_answer: str | None = None,
                           appreciation_duration: float = 0.0,
                           data_tts_duration: float = 0.0,
                           intro_duration: float = 0.0,
                           template_answer: str | None = None,
                           n_act2_images: int = 1,
                           appreciation_text: str = "") -> list[dict]:
    """3-act reveal — painting breathes, context builds, then data lands.

    Act I        : full painting, no data box, just handle — let it breathe
    Act II (×N)  : one frame per crop image; appreciation VO plays over them
    Act III      : price stamp + % above estimate hit all at once
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

    def _data(line1="", line2="", line3="", a="", hold=4.0):
        return {
            "show_caption":  bool(line1 or line2 or line3),
            "tag":           tag,
            "line1":         line1,
            "line2":         line2,
            "line3":         line3,
            "hook_question": None,
            "hook_answer":   a,
            "upper_artist":  artist_name,
            "upper_title":   painting_title,
            "hold_seconds":  hold,
        }

    act1_hold = max(4.0, round(intro_duration + 0.6, 1)) if intro_duration > 0 else 4.0
    act3_hold = max(6.0, round(data_tts_duration + 2.5, 1)) if data_tts_duration > 0 else 6.0

    # Each Act II crop holds long enough that the appreciation VO finishes before
    # the last crop ends; minimum 0.3s so fast montages stay watchable.
    n = max(1, n_act2_images)
    crop_hold_s = max(0.3, round(appreciation_duration / n, 1)) if appreciation_duration > 0 else max(0.3, round(5.0 / n, 1))

    frames = [_data(hold=act1_hold)]
    for frame_idx in range(n):
        # act2_audio_offset = seconds into tts_appreciation.mp3 when this crop starts.
        # make_reel.py uses it to reveal words at the right timestamp across frames.
        f = _data(hold=crop_hold_s, a=appreciation_text)
        if appreciation_text:
            f["act2_audio_offset"] = round(frame_idx * crop_hold_s, 2)
        frames.append(f)
    frames.append(_data(line1=E, line2=S, line3=P, hold=act3_hold))

    # Trim only Act I to keep total ≤ _MAX_REEL_SECONDS; Act II crops and Act III are left intact.
    act1_floor = max(0.5, round(intro_duration + 0.2, 1))
    total = sum(f["hold_seconds"] + _FRAME_FADE_S for f in frames)
    if total > _MAX_REEL_SECONDS:
        cut = min(total - _MAX_REEL_SECONDS, max(0.0, frames[0]["hold_seconds"] - act1_floor))
        frames[0]["hold_seconds"] = round(frames[0]["hold_seconds"] - cut, 1)

    return frames


# ── Config generation ──────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    """Escape a value for safe embedding inside a double-quoted Python string literal."""
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


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
        f'    "lot_id":         "{_esc(lot_id)}",',
        "    # ── Caption — The Shock Number ────────────────────────────",
        f'    "caption_tag":    "{_esc(tag_line)}",',
        f'    "caption_line1":  "{_esc(est_str)}",',
        f'    "caption_line2":  "{_esc(sold_str)}",',
        f'    "caption_line3":  "{_esc(pct_str)}",',
        "",
        "    # ── Location metadata ─────────────────────────────────────",
        f'    "location_coords": "{_esc(house_upper)}",',
        f'    "location_name":   "{_esc(sale_upper)}",',
        f'    "location_season": "{_esc(scraped[:4])}  ·  SALE RESULT",',
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
        "    # ── Pacing — 6fps, ≤22s (initial frames trimmed to fit) ────",
        "    \"fps\":          5,",
        "    \"hold_seconds\": 0.0,",
        "    \"fade_seconds\": 0.0,",
        "",
        "    # ── Captions metadata ─────────────────────────────────────",
        '    "topic":          "culture",',
        f'    "location":       "{_esc(house)}",',
        f'    "season":         "{_esc(scraped[:4])}",',
        '    "caption_full":   (',
        f'        "{_esc(caption_full_line1)}\\n\\n"',
        f'        "{_esc(caption_full_line2)}"',
        "    ),",
        '    "caption_hero":   "they priced it wrong",',
        f'    "personal_note":  "{_esc(personal_note)}",',
        f'    "engagement_hook": "{_esc(engagement_hook)}",',
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
        f.write("\n```\n\n---\n\n")

        if captions.get("linkedin"):
            ln_times = "Tue–Thu, 8–10am or 12–1pm (your local time)"
            f.write("## 💼 LinkedIn\n\n")
            f.write(f"**Best time to post:** {ln_times}\n")
            f.write(f"**Video:** `output/reel.mp4`\n\n")
            f.write("### Caption\n\n```\n")
            f.write(captions["linkedin"])
            f.write("\n```\n\n---\n\n")

        f.write(f"*Generated {datetime.now().strftime('%B %d, %Y')} · AI*\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-generate a reel from weekly art auction data")
    parser.add_argument("--week",      default=None, help="ISO date in target week (default: today)")
    parser.add_argument("--all-time",  action="store_true", help="Use all-time top lots instead of weekly")
    parser.add_argument("--run",       action="store_true", help="Run make_reel.py + make_captions.py after generation")
    parser.add_argument("--top-n",     type=int, default=8, help="Max lots to query (default: 8)")
    parser.add_argument("--lot-index", type=int, default=0, help="Which lot to use (0 = top, 1 = 2nd, etc.)")
    parser.add_argument("--crop-method", choices=("grid","sliding"), default="sliding", help="Crop method to use: grid or sliding-window")
    parser.add_argument("--crop-size", type=int, default=565, help="Square crop/tile size in pixels (e.g., 256).")
    parser.add_argument("--crop-stride", type=int, default=None, help="Stride in pixels for sliding-window; defaults to half of crop-size.")
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
    # Pull a wide candidate pool so composite scoring has material to work with
    _candidate_n = max(top_n * 6, 50)
    if args.all_time:
        lots = _query_alltime_top(conn, limit=_candidate_n, exclude_ids=skip)
        reel_slug = f"weekly-{date.today().isoformat()}-alltime"
    else:
        lots = _query_top_lots(conn, week_start, week_end, limit=_candidate_n, exclude_ids=skip)
        if not lots:
            print(f"\n  No new data for week {week_label} — trying random unposted week...")
            rand = _query_random_week_lot(conn, exclude_ids=skip)
            if rand:
                # re-query that week's top lots
                w = rand[0]["scraped_at"][:10]
                wb_start, wb_end = _week_bounds(date.fromisoformat(w))
                lots = _query_top_lots(conn, wb_start, wb_end, limit=_candidate_n, exclude_ids=skip)
                reel_slug = f"weekly-{wb_start}-random"
                print(f"  Using random week: {wb_start}")
            if not lots:
                print("  Falling back to all-time top unposted lots.")
                lots = _query_alltime_top(conn, limit=_candidate_n, exclude_ids=skip)
                reel_slug = f"weekly-{week_start}-fallback"

    # Build notable-artist set from DB before closing, then composite-score and re-rank
    notable_artists = _build_notable_artists_set(conn)
    conn.close()

    lots = sorted(lots, key=lambda l: _score_lot(l, notable_artists), reverse=True)[:top_n]
    if lots:
        print(f"\n  Composite scores (top {min(3, len(lots))}):")
        for l in lots[:3]:
            print(f"    {_score_lot(l, notable_artists):.0f}  {_clean_artist(l.get('artist') or '')} "
                  f"  +{_pct_above(l['hammer_usd'], l['estimate_low']):.0f}%"
                  f"  imgs={len(json.loads(l.get('image_urls') or '[]'))}"
                  f"  known={_artist_is_notable(l.get('artist') or '', notable_artists)}")

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

    # Generate center + corner crops for each source image and include originals.
    # Crops saved in <reel>/_crops and used alongside originals for more reveal frames.
    crops_dir = reel_dir / "_crops"
    if args.crop_method == "sliding":
        stride = args.crop_stride if args.crop_stride is not None else max(1, args.crop_size // 2)
        cropped_variants = _generate_sliding_window_crops(src_images, crops_dir, tile_size=args.crop_size, stride=stride, include_original=True)
    else:
        target_size = (args.crop_size, args.crop_size) if args.crop_size else None
        cropped_variants = _generate_grid_crops(src_images, crops_dir, include_original=True, target_size=target_size)
    if cropped_variants:
        src_images = cropped_variants
    else:
        print("  ⚠ No crops generated — using originals only.")

    if not src_images:
        print("✗ No images downloaded — cannot generate reel.")
        sys.exit(1)

    # Number of Act II frames = all images except Act I (first) and Act III (last).
    # At least 1 so the sequence always has an Act II.
    _n_act2 = max(1, len(src_images) - 2)

    # ── Build reveal sequence ──────────────────────────────────
    tag_base = "@thehammerprice  ·  weekly results" if not args.all_time else "@thehammerprice  ·  auction data"

    # Generate hook question + template answer once so audio and visual stay in sync
    _pct      = _pct_above(hook["hammer_usd"], hook["estimate_low"])
    _question, _tmpl_answer = _hook_caption(hook, _pct)

    _lot_preview = {
        "artist":        _clean_artist(hook.get("artist") or "Unknown"),
        "title":         (hook.get("title") or "Untitled")[:60],
        "auction_house": hook.get("auction_house") or "the auction house",
        "hammer_fmt":    _fmt_price(hook["hammer_usd"]),
        "estimate_fmt":  f"{_fmt_price(hook['estimate_low'])}–{_fmt_price(hook.get('estimate_high') or hook['estimate_low'])}",
        "pct_above":     _pct,
    }

    # Try AI-generated hook answer; fall back to template if unavailable
    ai_hook_answer = None
    if os.getenv("OPENROUTER_API_KEY"):
        try:
            sys.path.insert(0, str(SCRIPT_DIR))
            from ai_content import generate_hook_answer
            print("\n▸ Generating AI hook answer...")
            ai_hook_answer = generate_hook_answer(_lot_preview, _question)
            if ai_hook_answer:
                print(f"  ✓ AI answer: {ai_hook_answer[:80]}...")
            else:
                print("  ⚠ AI hook answer failed — using template")
                ai_hook_answer = _tmpl_answer
        except Exception as e:
            print(f"  ⚠ AI hook answer error: {e} — using template")
            ai_hook_answer = _tmpl_answer

    # ── Generate full-reel voiceover + sound effects ──────────
    # Tracks (3-act structure):
    #   tts_intro.mp3        — "This is [Title] by [Artist]." at t=0 (Act I)
    #   tts_appreciation.mp3 — context / significance of the work (Act II)
    #   sfx_gavel.mp3        — hammer strike fires at Act III start (when data lands)
    #   tts_data.mp3         — "estimated at X, sold for Y, +N%" (Act III)
    # All baked into voiceover.mp3 via silence-padding concat; audio_offset=0.
    print("\n▸ Generating voiceover tracks...")
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from ai_content import generate_voiceover, synthesize_gavel
    except Exception as e:
        print(f"  ⚠ Import error: {e}")
        generate_voiceover = synthesize_gavel = None

    word_timings  = []
    voiceover_ok  = False

    if generate_voiceover and synthesize_gavel:
        sfx_gavel_path        = str(reel_dir / "sfx_gavel.mp3")
        tts_appreciation_path = str(reel_dir / "tts_appreciation.mp3")
        tts_data_path         = str(reel_dir / "tts_data.mp3")

        _pct_val   = _pct_above(hook["hammer_usd"], hook["estimate_low"])
        _hammer_s  = _fmt_price_tts(hook["hammer_usd"])
        _est_s     = (f"{_fmt_price_tts(hook['estimate_low'])} "
                      f"to {_fmt_price_tts(hook.get('estimate_high') or hook['estimate_low'])}")

        # Step 1 — Act II appreciation TTS (market context / significance of the work)
        # Hard cap as safety net — AI prompt already targets 25 words.
        _APPRECIATION_MAX_WORDS = 30
        _raw_appr = ai_hook_answer or _tmpl_answer or ""
        _appr_words = _raw_appr.split()
        if len(_appr_words) > _APPRECIATION_MAX_WORDS:
            _trimmed = " ".join(_appr_words[:_APPRECIATION_MAX_WORDS])
            # Prefer ending at a sentence boundary in the second half
            for _punct in (".", "!", "?"):
                _pidx = _trimmed.rfind(_punct)
                if _pidx > len(_trimmed) * 0.5:
                    _trimmed = _trimmed[:_pidx + 1]
                    break
            _raw_appr = _trimmed
        _appreciation_text = _prices_to_speech(_raw_appr)
        _ok_appr, word_timings = generate_voiceover(_appreciation_text, tts_appreciation_path)
        appreciation_duration = 0.0
        if _ok_appr and word_timings:
            appreciation_duration = word_timings[-1]["start"] + 1.5
            print(f"  ✓ Act II appreciation TTS ({appreciation_duration:.1f}s, {len(word_timings)} words)")

        # Step 2 — Act III data TTS — pure numbers, no context; hits like a punch
        _data_script = (
            f"estimated at {_est_s}. "
            f"sold for {_hammer_s}. "
            f"that's {round(_pct_val)} percent above the low estimate."
        )
        _ok_data, _ = generate_voiceover(_data_script, tts_data_path)
        data_tts_duration = _get_audio_duration(tts_data_path) if _ok_data else 0.0
        if _ok_data:
            print(f"  ✓ Act III data TTS ({data_tts_duration:.1f}s): \"{_data_script[:60]}\"")

        # Step 3 — Act I intro TTS: "This is [Title] by [Artist]." at t=0
        _artist_s = _clean_artist(hook.get("artist") or "Unknown")
        _title_s  = (hook.get("title") or "Untitled")[:50]
        _intro_script = f"This is {_title_s} by {_artist_s}."
        tts_intro_path = str(reel_dir / "tts_intro.mp3")
        _ok_intro, _ = generate_voiceover(_intro_script, tts_intro_path)
        intro_duration = _get_audio_duration(tts_intro_path) if _ok_intro else 0.0
        if _ok_intro:
            print(f"  ✓ Act I intro TTS: \"{_intro_script[:60]}\" ({intro_duration:.2f}s)")

        # Step 4 — build reveal with correct per-act durations (intro-aware)
        reveal = _build_reveal_sequence(hook, tag_base, ai_answer=ai_hook_answer,
                                        appreciation_duration=appreciation_duration,
                                        data_tts_duration=data_tts_duration,
                                        intro_duration=intro_duration,
                                        template_answer=_tmpl_answer,
                                        n_act2_images=_n_act2,
                                        appreciation_text=_appreciation_text)

        # Step 5 — compute per-frame start times
        # _BLOCK_REVEAL_S must match make_reel.py _render_block_reveal_frames reveal_duration
        _BLOCK_REVEAL_S = 4.0
        _fade_s = 0.5
        _frame_starts: list[float] = []
        _t = 0.0
        for _fc in reveal:
            _frame_starts.append(_t)
            _t += _fc["hold_seconds"] + _fade_s

        # Act I's block reveal plays before Act II starts; shift all Act II/III audio by that amount.
        act2_start = (_frame_starts[1] if len(_frame_starts) > 1 else 0.0) + _BLOCK_REVEAL_S
        # Act III is always the last frame in the reveal list.
        act3_start = (_frame_starts[-1] if _frame_starts else _t) + _BLOCK_REVEAL_S

        # Step 6 — gavel SFX fires at Act III start (when data lands)
        _ok_gavel = synthesize_gavel(sfx_gavel_path)
        _gavel_dur = _get_audio_duration(sfx_gavel_path) if _ok_gavel else 0.0
        if _ok_gavel:
            print(f"  ✓ Gavel SFX (fires at Act III, t={act3_start:.2f}s)")

        # Step 7 — assemble all tracks with their exact video timestamps
        frame_tracks: list[tuple[str, float]] = []

        if _ok_intro:
            frame_tracks.append((tts_intro_path, 0.0))

        if _ok_appr:
            frame_tracks.append((tts_appreciation_path, act2_start))

        if _ok_gavel:
            frame_tracks.append((sfx_gavel_path, act3_start))

        if _ok_data:
            _data_start = act3_start + (_gavel_dur + 0.2 if _ok_gavel else 0.0)
            frame_tracks.append((tts_data_path, _data_start))

        # Step 8 — bake into voiceover.mp3 via silence-padding concat
        voiceover_ok = _build_sequential_voiceover(
            frame_tracks=frame_tracks,
            output_path=str(reel_dir / "voiceover.mp3"),
        )
        if not voiceover_ok:
            import shutil as _shutil
            if os.path.exists(tts_appreciation_path):
                _shutil.copy2(tts_appreciation_path, str(reel_dir / "voiceover.mp3"))
                voiceover_ok = True
    else:
        # No TTS available — build reveal without audio timing
        reveal = _build_reveal_sequence(hook, tag_base, ai_answer=ai_hook_answer,
                                        appreciation_duration=0.0,
                                        data_tts_duration=0.0,
                                        template_answer=_tmpl_answer,
                                        n_act2_images=_n_act2)

    # Save timing data for make_reel.py
    # audio_offset=0 because all tracks are baked into voiceover.mp3 at correct positions;
    # word_timings are 0-based from tts_answer.mp3 (answer frame visual sync unchanged).
    import json as _json
    # Record useful audio event timings so make_reel.py can align visuals to audio.
    data_start = locals().get("_data_start", None)
    data_duration = locals().get("data_tts_duration", 0.0)
    intro_dur = locals().get("intro_duration", 0.0)
    timing_data = {
        "audio_offset": 0.0,
        "word_timings": word_timings,
        "data_start": data_start,
        "data_duration": data_duration,
        "intro_duration": intro_dur,
    }
    (reel_dir / "voiceover_timing.json").write_text(_json.dumps(timing_data, indent=2))

    # Combine all downloaded originals and generated crops into the images folder
    # and prefix every copied file sequentially so make_reel.py sees a numbered list.
    import shutil
    src_dir = reel_dir / "_src"
    crops_dir = reel_dir / "_crops"

    # Wipe images/ before repopulating so re-runs don't accumulate stale files.
    if images_dir.exists():
        shutil.rmtree(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    # Build ordered, unique list of files to copy. Start with src_images to preserve reveal order.
    to_copy: list[Path] = []
    seen_names = set()
    for p in src_images:
        if p and p.name not in seen_names and p.exists():
            to_copy.append(p)
            seen_names.add(p.name)

    # Add any remaining files from _src and _crops that weren't in src_images
    for folder in (src_dir, crops_dir):
        if folder.exists():
            for f in sorted(folder.iterdir()):
                if not f.is_file():
                    continue
                if f.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                    continue
                if f.name in seen_names:
                    continue
                to_copy.append(f)
                seen_names.add(f.name)

    # Copy with numeric prefix
    copied = 0
    for idx, src in enumerate(to_copy):
        dest = images_dir / f"{idx + 1:02d}_{src.name}"
        try:
            shutil.copy2(src, dest)
            copied += 1
        except Exception as e:
            print(f"  ⚠ Copy failed: {src} → {dest} — {e}")

    # Count images
    n_images = sum(1 for f in images_dir.iterdir() if f.is_file() and f.suffix.lower() in ('.jpg', '.jpeg', '.png'))
    n_src_copied = sum(1 for p in to_copy if p.parent == src_dir)
    n_crops_copied = sum(1 for p in to_copy if p.parent == crops_dir)
    print(f"  {len(src_images)} source image(s) + {n_crops_copied} crops copied → {n_images} images in {images_dir}")

    # Clean up _crops — no longer needed once images/ is populated
    import shutil as _shutil
    if crops_dir.exists():
        _shutil.rmtree(crops_dir)
        print(f"  ✓ Removed {crops_dir.name}/")

    # ── Write reel_config.py ───────────────────────────────────
    config_path = reel_dir / "reel_config.py"
    config_src  = _generate_config(hook, week_label, args.all_time, reveal=reveal)
    config_path.write_text(config_src)
    print(f"\n▸ Config written: {config_path}")

    # ── Record in posted_reels ─────────────────────────────────
    conn2 = sqlite3.connect(DB_PATH)
    conn2.row_factory = sqlite3.Row
    _ensure_posted_table(conn2)
    _record_posted(conn2, hook, reel_slug, ["instagram", "tiktok", "linkedin"])
    conn2.close()

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
                        captions["instagram"] = captions["instagram"].replace(
                                "\n\n#thehammerprice",
                                f"\n\n#thehammerprice",
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
