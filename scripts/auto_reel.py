#!/usr/bin/env python3
"""
Auto-reel generator — picks the most shocking auction results from data/art.db,
downloads artwork images, and writes a ready-to-run reel folder for
reel_template/make_reel.py.

Usage (run from alexsnowschool-business/):
    python scripts/auto_reel.py                   # uses this week's scrapes
    python scripts/auto_reel.py --week 2026-05-08 # any date in the target week
    python scripts/auto_reel.py --run             # also renders the reel
    python scripts/auto_reel.py --voice           # generate TTS narration
    python scripts/auto_reel.py --all-time        # ignore week, pick best ever
"""

import argparse
import json
import math
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

from PIL import Image
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
BUSINESS_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
import reel_utils
import campaign_artist as _ca

load_dotenv(BUSINESS_DIR / ".env", override=False)

DB_PATH       = BUSINESS_DIR / "data" / "art.db"
REELS_DIR     = BUSINESS_DIR / "reels"
REEL_TEMPLATE = BUSINESS_DIR / "reel_template"

# ── API credentials ────────────────────────────────────────────────────────────
OPENROUTER_KEY   = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
ELEVENLABS_KEY   = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE_ID", "LXu5MIFyvPZCxBst8fPP")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5")

# ── HTTP headers ───────────────────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}

# ── Pacing constants ───────────────────────────────────────────────────────────
_MAX_REEL_SECONDS  = 65.0
_FRAME_FADE_S      = 0.1
_APPRECIATION_MAX_WORDS = 200


# ── Notable-artist index ───────────────────────────────────────────────────────

KNOWN_ARTISTS: frozenset[str] = frozenset({
    # Abstract Expressionism
    'Franz Kline', 'Hans Hofmann',
    # Abstract Expressionism · Action Painting
    'Jackson Pollock',
    # Abstract Expressionism · Biomorphic Abstraction
    'Arshile Gorky',
    # Abstract Expressionism · Colour Field
    'Helen Frankenthaler', 'Kenneth Noland', 'Sam Francis',
    # Abstract Expressionism · Colour-Field
    'Ed Clark',
    # Abstract Expressionism · Contemporary
    'Jack Whitten', 'Louise Fishman',
    # Abstract Expressionism · Elegy Series
    'Robert Motherwell',
    # Abstract Expressionism · Hard-Edge Abstraction
    'Al Held',
    # Abstract Expressionism · Minimalism
    'Alexander Liberman',
    # Abstract Expressionism · Pictograph
    'Adolph Gottlieb',
    # Abstract Expressionism · Sculpture
    'David Smith', 'John Chamberlain', 'Louise Nevelson',
    # Abstract Expressionism · Second Generation
    'Joan Mitchell',
    # Abstract Expressionism · Women Series
    'Willem de Kooning',
    # Abstract · Colour-Field
    'Piero Dorazio',
    # Abstract · Lyrical Abstraction
    'Rhee Seundja',
    # Abstract · Modernism
    'Rudolf Bauer',
    # Abstract · Stripe Painting
    'Sean Scully',
    # Abstract · Waterfall Paintings
    'Pat Steir',
    # Abstraction · Expressionism
    'Otto Freundlich',
    # Abstraction · Figurative Modernism
    'Jean Hélion',
    # American Illustration · Social Realism
    'Norman Rockwell',
    # Art Brut · Contemporary
    'Jean Dubuffet',
    # Arte Povera · Contemporary
    'Marisa Merz',
    # Avant-Garde · Infinity · Obsessional Art
    'Yayoi Kusama',
    # Colour Field · Abstract
    'Stanley Whitney',
    # Colour-Field · Abstract Expressionism
    'Lynne Drexler', 'Sam Gilliam',
    # Conceptual Art · Minimalism
    'Sol LeWitt',
    # Conceptual Figuration · Postmodernism
    'Mark Tansey',
    # Conceptual · Contemporary
    'Adam Pendleton', 'Barbara Kruger', 'Cheyney Thompson', 'R.H. Quaytman',
    # Conceptual · Minimalism
    'Bernar Venet',
    # Conceptual · Neo-Conceptual
    'Adam McEwen',
    # Conceptual · Postmodernism
    'Sherrie Levine',
    # Contemporary Figuration · Intimacy
    'Jenna Gribbon',
    # Contemporary · Abstract
    'Günther Förg', 'Jennifer Guidi', 'Katherine Bradford', 'Kei Imazu', 'Loie Hollowell',
    'Lucy Bull', 'Mark Bradford', 'Mark Grotjahn', 'Maysha Mohamedi', 'Sadamasa Motonaga',
    'Sarah Crowner', 'Spencer Lewis',
    # Contemporary · Black American Identity
    'Rashid Johnson',
    # Contemporary · Conceptual
    'Damien Hirst', 'Hank Willis Thomas', 'Jaune Quick-to-See Smith', 'Tracey Emin',
    # Contemporary · Figurative
    'Alvin Armstrong', 'Angela Heisch', 'Asuka Anastacia Ogawa', 'Brian Calvin',
    'Caroline Walker', 'Chantal Joffe', 'Cristina de Miguel', 'Danielle McKinney',
    'Doron Langberg', 'Emmanuel Taku', 'Firenze Lai', 'Grant Yun', 'Hilary Pecis',
    'Huang Yishan', 'Ivy Haldeman', 'Izumi Kato', 'Jesse Mockrin', 'Ji Xin',
    'Joel Mesler', 'John Currin', 'Jonas Wood', 'Jonathan Lyndon Chase', 'Kehinde Wiley',
    'Ksenia Dermenzhi', 'Lisa Yuskavage', 'Liu Ye', 'María Berrío', 'Michaela Yearwood-Dan',
    'Mickalene Thomas', 'Minoru Nomata', 'Mohammed Sami', 'Philip Tsiàras', 'Qin Qi',
    'Rebecca Ness', 'Salman Toor', 'Scott Kahn', 'Shona McAndrew', 'Tyler Ballon',
    'Yu Nishimura', 'Yuan Yuan', 'Zhang Xiaogang',
    # Contemporary · Installation
    'Jim Hodges', 'Juan Muñoz', 'Katharina Grosse', 'Leonardo Drew', 'Sterling Ruby',
    # Contemporary · Minimalism
    'Maria Taniguchi',
    # Contemporary · Modernism
    'Etel Adnan',
    # Contemporary · Neo-Conceptual
    'Avery Singer',
    # Contemporary · Neo-Expressionism
    'Angel Otero', 'Genieve Figgis',
    # Contemporary · New Media
    'Christian Marclay',
    # Contemporary · Pop Art
    'Mr.', 'Takashi Murakami', 'Yoshitomo Nara',
    # Contemporary · Sculpture
    'Anish Kapoor', 'Annie Morris', 'Antony Gormley', 'Conrad Shawcross',
    'Deborah Butterfield', 'Franz West', 'Katsura Funakoshi', 'Ken Price',
    'Kohei Nawa', 'Santiago Calatrava', 'The Haas Brothers',
    # Cubism
    'Albert Gleizes', 'Jean Metzinger',
    # Cubism · Modernism
    'Pablo Picasso',
    # Cubism · Post-Impressionism
    'Henri Hayden',
    # Dada
    'Hannah Höch',
    # Dada · Surrealism
    'Man Ray',
    # Dansaekhwa · Abstract
    'Ha Chong-Hyun', 'Yun Hyong-Keun',
    # Expressionism · Der Blaue Reiter
    'Gabriele Münter',
    # Expressionism · Die Brücke
    'Karl Schmidt-Rottluff', 'Otto Mueller',
    # Expressionism · Figurative Modernism
    'Bob Thompson',
    # Fauvism · Expressionism
    'André Derain',
    # Fauvism · Modernism · Decoration
    'Henri Matisse',
    # Figurative Expressionism
    'David Park',
    # Figurative Expressionism · Bay Area Figurative
    'Joan Brown',
    # Figurative Modernism · Contemporary
    'Alex Katz',
    # Figurative Realism · Portrait
    'Alice Neel',
    # Figurative · African-American Narrative
    'Ernie Barnes',
    # German Expressionism · Die Brücke
    'Ernst Ludwig Kirchner',
    # Gutai · Contemporary
    'Takesada Matsutani',
    # Impressionism
    'Berthe Morisot',
    # Impressionism · Figure Painting
    'Pierre-Auguste Renoir',
    # Impressionism · Post-Impressionism
    'Blanche Hoschedé-Monet',
    # Impressionism · Realism
    'Edgar Degas',
    # Minimalism
    'Donald Judd',
    # Minimalism · Abstraction
    'Agnes Martin',
    # Minimalism · Contemporary
    'Blinky Palermo', 'Joel Shapiro', 'Robert Mangold', 'Robert Ryman',
    # Minimalism · Hard-Edge · Shaped Canvas
    'Frank Stella',
    # Minimalism · Process Art
    'Richard Serra',
    # Modernism · Constructivism
    'László Moholy-Nagy',
    # Modernism · Jewish Folk Tradition
    'Marc Chagall',
    # Modernism · Kinetic Sculpture
    'Alexander Calder',
    # Modernism · Minimalism
    'Josef Albers',
    # Modernism · Sculpture
    'Anthony Caro', 'Auguste Rodin', 'Camille Claudel', 'Chana Orloff',
    'Constantin Brâncuși', 'Diego Giacometti', 'Rembrandt Bugatti',
    # Neo-Conceptual · Contemporary
    'Ashley Bickerton',
    # Neo-Dada · Combines
    'Robert Rauschenberg',
    # Neo-Dada · Pop Art
    'Jim Dine',
    # Neo-Expressionism
    'Georg Baselitz',
    # Neo-Expressionism · Artificial Realism
    'George Condo',
    # Neo-Expressionism · British Figuration
    'Cecily Brown',
    # Neo-Expressionism · Contemporary
    'Adrian Ghenie', 'Anselm Kiefer', 'David Wojnarowicz', 'Eddie Martinez',
    'Rita Ackermann', 'Robert Colescott', 'Robert Nava', 'Ross Bleckner',
    'Sigmar Polke', 'Zeng Fanzhi', 'Zhou Chunya',
    # Neo-Expressionism · Figurative Drawing
    'Robert Longo',
    # Neo-Expressionism · Postmodernism
    'David Salle',
    # Neo-Expressionism · Street Art
    'Aboudia', 'Jean-Michel Basquiat',
    # Neo-Expressionism · Transavanguardia
    'Sandro Chia',
    # New Media · Contemporary
    'Wang Yuyang',
    # Op Art · Modernism
    'Victor Vasarely',
    # Photography
    'Diane Arbus', 'Garry Winogrand', 'Henri Cartier-Bresson', 'Nan Goldin',
    'Philip-Lorca diCorcia', 'Robert Frank', 'Robert Mapplethorpe', 'William Eggleston',
    # Photography · Conceptual
    'Anne Collier',
    # Photography · Contemporary
    'Francesca Woodman', 'Peter Beard',
    # Photorealism
    'Richard Estes',
    # Photorealism · Contemporary
    'Chuck Close',
    # Pop Art · Ben-Day Dots · Comic Book
    'Roy Lichtenstein',
    # Pop Art · British Painting · Figuration
    'David Hockney',
    # Pop Art · California Realism
    'Wayne Thiebaud',
    # Pop Art · Seriality · Factory
    'Andy Warhol',
    # Pop Art · Street Art
    'Kenny Scharf',
    # Pop Art · West Coast · Language in Painting
    'Ed Ruscha',
    # Post-Impressionism
    'Henri de Toulouse-Lautrec', 'Pierre Bonnard',
    # Post-Impressionism · Fauvism
    'Albert Marquet',
    # Post-Impressionism · Impressionism
    'Johan Barthold Jongkind',
    # Post-Impressionism · Neo-Dada
    'Yves Klein',
    # Post-Impressionism · Neo-Impressionism
    'Henri-Edmond Cross',
    # Post-Minimalism · Contemporary
    'Lynda Benglis',
    # Pre-Impressionism · Marine Painting
    'Eugène Boudin',
    # Street Art · Contemporary
    'Futura 2000', 'Invader', 'José Parlá', 'Mehdi Ghadyanloo',
    # Street Art · Pop Art
    'Keith Haring',
    # Street Art · Post-Pop
    'KAWS',
})

_KNOWN_ARTISTS_LOWER: frozenset[str] = frozenset(k.lower() for k in KNOWN_ARTISTS)


# ── Hook templates ─────────────────────────────────────────────────────────────
# Each entry: (min_pct, [question variants], [answer variants])
# Format vars: {artist} {title} {house} {hammer} {estimate} {pct} {n}

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
         "a result this far above estimate isn't a market anomaly — it's the room rewriting the artist's place in the canon. "
         "what the catalogue priced as one thing, collectors recognized as something else entirely.",

         "estimates reflect what an artist has done. hammer prices reflect what collectors believe they will mean. "
         "at {n} above estimate, the room made a clear statement about {artist}'s legacy.",

         "'{title}' walked into that room as a catalogue entry. it left as a record. "
         "that's how art history gets repriced — not in museums, but at auction.",

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
         "at this level, collectors aren't just buying a work — they're staking a position on the artist. "
         "the estimate reflects where {artist} has been. {hammer} is where the room thinks they're going.",

         "results like this happen when critical and market consensus finally align. "
         "a museum moment, a major publication, a retrospective — something shifted the conversation before this sale, and the room responded.",

         "provenance and period matter at this price. "
         "'{title}' carried a history the estimate didn't fully price — and the room understood what it was acquiring.",

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
         "auction rooms reprice artists faster than institutions do. "
         "{artist} had been estimated on old assumptions — the room corrected them.",

         "the estimate was set by precedent. the room was pricing on where {artist} now sits in the conversation — "
         "and that's a very different number.",

         "a result {pct} above estimate means someone arrived with deep knowledge of the work and the artist. "
         "that kind of conviction — anchored in research, not sentiment — is what moves an artist's market.",

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
         "the estimate is built from past sales. "
         "when the room bids {pct} above that, it's saying: the past doesn't tell the full story of this artist anymore.",

         "serious collectors don't bid on estimates — they bid on their own research. "
         "a {pct} overshoot usually means someone in that room understood {artist}'s significance better than the catalogue did.",

         "the auction house priced {artist} conservatively. "
         "the room disagreed — and when a room this competitive disagrees, the result becomes the new reference point.",

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
         "the estimate is a floor, not a forecast. "
         "when the room bids above it, it usually means the work carried more quality — or more significance — than the catalogue captured.",

         "{artist}'s presence in major collections and exhibitions has been building. "
         "a {pct} overshoot confirms the market has been paying attention.",

         "'{title}' outperformed because the room valued what it is, not just what {artist} has sold for before. "
         "the estimate anchors on history. the hammer reflects the present.",

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
         "a result above estimate — even modestly — confirms that demand for {artist}'s work is real and consistent. "
         "the catalogue sets the floor. the room decides the ceiling.",

         "the estimate reflects what specialists expected based on precedent. "
         "{hammer} is what collectors in that room were willing to pay — and that's always the more honest number.",

         "when a work sells above estimate, it's usually because the room found something in it the catalogue missed — "
         "quality, condition, period, or simply the right buyer at the right moment.",

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
         "even a small overshoot confirms there was more than one serious buyer in the room. "
         "for {artist}, that demand matters — it keeps the market active and the next estimate honest.",

         "the estimate is a starting point. the hammer is the truth. "
         "here, the truth was just a little higher than the catalogue expected — and that's enough to move the conversation.",

         "a result above estimate — however modest — means the market for {artist} is healthy. "
         "collectors are paying attention, and competition, even at this level, is a signal worth reading.",

         "every lot that sells above estimate becomes part of an artist's price history. "
         "'{title}' just added one more data point — and it moved in the right direction.",
     ]),
]


# ── Formatters ─────────────────────────────────────────────────────────────────

def _fmt_price(usd: float) -> str:
    """Format a USD price with full zeros: $441,000 or $1,380,000."""
    return f"${usd:,.0f}"


def _fmt_price_tts(usd: float) -> str:
    """Spoken-English price for TTS."""
    if usd >= 1_000_000:
        return f"{usd / 1_000_000:.1f} million dollars"
    if usd >= 1_000:
        return f"{usd / 1_000:.0f} thousand dollars"
    return f"{usd:.0f} dollars"


def _prices_to_speech(text: str) -> str:
    """Replace $X,XXX-style price tokens in arbitrary text with their spoken form."""
    def _sub(m: re.Match) -> str:
        digits = m.group(1).replace(",", "")
        return _fmt_price_tts(float(digits))
    return re.sub(r"\$([0-9][0-9,]*)", _sub, text)


def _pct_above(hammer: float, low: float) -> float:
    return round((hammer / low - 1) * 100, 1)


def _clean_artist(name: str) -> str:
    """Strip birth-year suffix like '(B. 1953)'."""
    return re.sub(r"\s*\([^)]+\)\s*$", "", name).strip().title()


_esc      = reel_utils.esc
_make_slug = reel_utils.make_slug


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


def _like_clauses(artist: str | None, title: str | None) -> tuple[str, list]:
    """Return combined (sql_fragment, params) for optional artist and title LIKE filters."""
    parts, params = [], []
    if artist:
        parts.append("AND artist LIKE ?")
        params.append(f"%{artist}%")
    if title:
        parts.append("AND title LIKE ?")
        params.append(f"%{title}%")
    return " ".join(parts), params


def _query_lots(conn: sqlite3.Connection, limit: int = 8,
                exclude_ids: set | None = None,
                artist: str | None = None, title: str | None = None,
                week_start: str | None = None, week_end: str | None = None) -> list[dict]:
    """Top outperforming lots. Restricts to week range when week_start/week_end are given."""
    exclude = tuple(exclude_ids or [])
    placeholders = ",".join("?" * len(exclude)) if exclude else "NULL"
    flt_sql, flt_params = _like_clauses(artist, title)
    date_sql    = "AND substr(scraped_at, 1, 10) BETWEEN ? AND ?" if week_start else ""
    date_params = (week_start, week_end) if week_start else ()
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
          {date_sql}
          {flt_sql}
          {"AND id NOT IN (" + placeholders + ")" if exclude else ""}
        ORDER BY pct_above DESC
        LIMIT ?
    """, (*date_params, *flt_params, *exclude, limit)).fetchall()
    return [dict(r) for r in rows]


def _query_top_lots(conn: sqlite3.Connection, week_start: str, week_end: str,
                    limit: int = 8, exclude_ids: set | None = None,
                    artist: str | None = None, title: str | None = None) -> list[dict]:
    """Top outperforming lots scraped in the given week, excluding already-posted ones."""
    return _query_lots(conn, limit, exclude_ids, artist, title, week_start, week_end)


def _query_alltime_top(conn: sqlite3.Connection, limit: int = 8,
                       exclude_ids: set | None = None,
                       artist: str | None = None, title: str | None = None) -> list[dict]:
    """All-time top outperforming lots, excluding already-posted ones."""
    return _query_lots(conn, limit, exclude_ids, artist, title)


def _query_random_week_lot(conn: sqlite3.Connection,
                           exclude_ids: set | None = None,
                           artist: str | None = None, title: str | None = None) -> list[dict]:
    """Pick top lot from a random week that has unposted content."""
    exclude = tuple(exclude_ids or [])
    placeholders = ",".join("?" * len(exclude)) if exclude else "NULL"
    flt_sql, flt_params = _like_clauses(artist, title)
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
          {flt_sql}
          {"AND id NOT IN (" + placeholders + ")" if exclude else ""}
        GROUP BY week_key
        HAVING MAX(pct_above)
        ORDER BY RANDOM()
        LIMIT 1
    """, (*flt_params, *exclude)).fetchall()
    return [dict(r) for r in rows]


def _list_artists(conn: sqlite3.Connection) -> None:
    """Print all artists in the DB ranked by record count and avg hammer price."""
    rows = conn.execute("""
        SELECT artist,
               COUNT(*)                          AS lots,
               ROUND(AVG(hammer_usd))            AS avg_hammer,
               ROUND(MAX(hammer_usd))            AS max_hammer,
               ROUND(AVG((hammer_usd * 1.0 / NULLIF(estimate_low, 0) - 1) * 100), 1) AS avg_pct
        FROM art_items
        WHERE hammer_usd IS NOT NULL AND artist IS NOT NULL
        GROUP BY artist
        ORDER BY lots DESC, avg_hammer DESC
    """).fetchall()
    if not rows:
        print("No artists found in database.")
        return
    print(f"\n{'#':<5} {'Artist':<40} {'Lots':>5} {'Avg $':>10} {'Max $':>10} {'Avg %+':>7}")
    print("─" * 80)
    for i, r in enumerate(rows, 1):
        name = _clean_artist(r["artist"] or "Unknown")
        avg  = f"${int(r['avg_hammer']):,}"  if r["avg_hammer"] else "—"
        mx   = f"${int(r['max_hammer']):,}"  if r["max_hammer"] else "—"
        pct  = f"+{r['avg_pct']:.1f}%"       if r["avg_pct"]    else "—"
        print(f"{i:<5} {name:<40} {r['lots']:>5} {avg:>10} {mx:>10} {pct:>7}")
    print(f"\n  {len(rows)} artists total. Use --artist \"<name>\" to filter.")


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


# ── Lot scoring ────────────────────────────────────────────────────────────────

def _artist_is_notable(artist: str, notable_set: set[str] | None = None) -> bool:
    """True if the artist is naratable — either in the curated list or has DB market depth."""
    cleaned = _clean_artist(artist)
    if notable_set and cleaned in notable_set:
        return True
    cleaned_lower = cleaned.lower()
    return any(
        k in cleaned_lower or cleaned_lower in k
        for k in _KNOWN_ARTISTS_LOWER
    )


def _score_lot(lot: dict, notable_set: set[str] | None = None) -> float:
    """Composite score: market shock + visual richness + artist narability + sale magnitude."""
    pct          = _pct_above(lot["hammer_usd"], lot["estimate_low"])
    is_known     = _artist_is_notable(lot.get("artist") or "", notable_set)
    hammer_usd   = lot["hammer_usd"] or 0
    pct_bonus    = math.log1p(max(pct, 0)) * 10
    # log-scale bonus only for lots above $100k — preserves underdog stories below that
    hammer_bonus = math.log10(hammer_usd) * 5 if hammer_usd >= 100_000 else 0
    return pct_bonus + (is_known * 20) + (hammer_bonus * 0.75)


# ── Image downloading ──────────────────────────────────────────────────────────

def _download_lot_images(lot: dict, dest_dir: Path, max_images: int = 8) -> list[Path]:
    """Download all unique images for a single lot. Returns list of saved paths."""
    urls = list(dict.fromkeys(json.loads(lot.get("image_urls") or "[]")))
    return reel_utils.download_images(urls, dest_dir, max_images, headers=_HEADERS)


# ── Image crop helpers ─────────────────────────────────────────────────────────

def _generate_grid_crops(src_paths: list[Path], crops_dir: Path,
                         include_original: bool = True,
                         target_size: tuple[int, int] | None = None) -> list[Path]:
    """Generate center + corner square crops for each source image."""
    crops_dir.mkdir(parents=True, exist_ok=True)
    result: list[Path] = []
    for src in src_paths:
        try:
            with Image.open(src) as im:
                im = im.convert("RGB")
                w, h = im.size
                side = min(w, h)
                positions = {
                    "center":       ((w - side) // 2, (h - side) // 2),
                    "top_left":     (0, 0),
                    "top_right":    (w - side, 0),
                    "bottom_left":  (0, h - side),
                    "bottom_right": (w - side, h - side),
                }
                if include_original:
                    result.append(src)
                for name, (left, top) in positions.items():
                    box  = (left, top, left + side, top + side)
                    crop = im.crop(box)
                    if target_size:
                        crop = crop.resize(target_size, Image.LANCZOS)
                    out_path = crops_dir / f"{src.stem}_crop_{name}{src.suffix}"
                    crop.save(out_path, quality=95)
                    result.append(out_path)
        except Exception as e:
            print(f"  ⚠ Crop failed for {src.name}: {e}")
            if include_original and src not in result:
                result.append(src)
    return result


def _generate_sliding_window_crops(src_paths: list[Path], crops_dir: Path,
                                   tile_size: int = 256, stride: int | None = None,
                                   include_original: bool = True) -> list[Path]:
    """Generate overlapping square tiles (sliding window) for each source image."""
    crops_dir.mkdir(parents=True, exist_ok=True)
    result: list[Path] = []
    for src in src_paths:
        try:
            with Image.open(src) as im:
                im = im.convert("RGB")
                w, h = im.size
                ts = min(tile_size, w, h)
                st = stride or max(1, ts // 2)

                def _positions(dim: int) -> list[int]:
                    if dim <= ts:
                        return [0]
                    pts = list(range(0, dim - ts + 1, st))
                    if pts[-1] != dim - ts:
                        pts.append(dim - ts)
                    return pts

                if include_original:
                    result.append(src)
                for x in _positions(w):
                    for y in _positions(h):
                        crop     = im.crop((x, y, x + ts, y + ts))
                        out_path = crops_dir / f"{src.stem}_tile_{ts}_{x}_{y}{src.suffix}"
                        crop.save(out_path, quality=95)
                        result.append(out_path)
        except Exception as e:
            print(f"  ⚠ Sliding crop failed for {src.name}: {e}")
            if include_original and src not in result:
                result.append(src)
    return result


def _copy_images_to_dir(src_images: list[Path], crops_dir: Path,
                        images_dir: Path) -> int:
    """
    Copy src_images (and any remaining files in crops_dir) into images/ with
    numeric prefixes. WebP files are converted to JPEG. Returns count copied.
    """
    if images_dir.exists():
        shutil.rmtree(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    to_copy: list[Path] = []
    seen_names: set[str] = set()

    for p in src_images:
        if p and p.name not in seen_names and p.exists():
            to_copy.append(p)
            seen_names.add(p.name)

    if crops_dir.exists():
        for f in sorted(crops_dir.iterdir()):
            if not f.is_file():
                continue
            if f.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
                continue
            if f.name in seen_names:
                continue
            to_copy.append(f)
            seen_names.add(f.name)

    copied = 0
    for idx, src in enumerate(to_copy):
        if src.suffix.lower() == ".webp":
            dest = images_dir / f"{idx + 1:02d}_{src.stem}.jpg"
            try:
                with Image.open(src) as im:
                    im.convert("RGB").save(dest, "JPEG", quality=95)
                copied += 1
            except Exception as e:
                print(f"  ⚠ WebP conversion failed for {src.name}: {e} — skipping")
        else:
            dest = images_dir / f"{idx + 1:02d}_{src.name}"
            try:
                shutil.copy2(src, dest)
                copied += 1
            except Exception as e:
                print(f"  ⚠ Copy failed: {src} → {dest} — {e}")
    return copied


# ── Hook caption ───────────────────────────────────────────────────────────────

def _hook_caption(lot: dict, pct: float) -> tuple[str, str]:
    """Return (question, answer) — randomly selected from per-tier variants."""
    mult     = round(pct / 100 + 1, 1)
    artist   = _clean_artist(lot.get("artist") or "Unknown")
    title    = (lot.get("title") or "Untitled")[:40]
    house    = (lot.get("auction_house") or "the auction house")
    hammer   = _fmt_price(lot["hammer_usd"])
    est_low  = lot["estimate_low"]
    est_high = lot.get("estimate_high") or est_low
    estimate = f"{_fmt_price(est_low)}–{_fmt_price(est_high)}"

    fmt = dict(
        n=f"{mult:.0f}×", artist=artist, title=title, house=house,
        hammer=hammer, estimate=estimate, pct=f"{pct:,.0f}%",
    )
    for threshold, q_variants, a_variants in _HOOK_TEMPLATES:
        if pct >= threshold:
            return (
                random.choice(q_variants).format(**fmt),
                random.choice(a_variants).format(**fmt),
            )
    return "the hammer price tells the real story.", "follow the data."


# ── Reveal sequence ────────────────────────────────────────────────────────────

def _build_reveal_sequence(lot: dict, tag_base: str,
                           n_act2_images: int = 1,
                           voice_duration: float = 0.0,
                           act1_words: int = 0,
                           narr_words: int = 0,
                           data_words: int = 0,
                           hook_question: str | None = None) -> list[dict]:
    """
    3-act reveal — all frames are clean (no text box); voice carries all data.
      Act I   — full painting; voice opens the piece (hook question)
      Act II  — crop sequence; voice narrates (art/history/significance)
      Act III — final crop; timed to word proportion so data voice lands in sync
    """
    artist_name    = _clean_artist(lot.get("artist") or "Unknown")
    painting_title = lot.get("title") or "Untitled"
    tag = f"{tag_base}  ·  lot I"

    # Act III data caption
    est_low  = lot.get("estimate_low") or 0
    est_high = lot.get("estimate_high") or est_low
    hammer   = lot.get("hammer_usd") or 0
    pct      = _pct_above(hammer, est_low) if est_low > 0 else 0
    _line1   = f"estimate: {_fmt_price(est_low)}–{_fmt_price(est_high)}"
    _line2   = f"sold: {_fmt_price(hammer)}."
    _line3   = f"+{pct:,.0f}% above estimate."

    def _frame(hold=4.0, show_data=False, show_hook=False, show_upper=True):
        return {
            "show_caption":  show_data,
            "tag":           tag,
            "line1":         _line1 if show_data else "",
            "line2":         _line2 if show_data else "",
            "line3":         _line3 if show_data else "",
            "hook_question": hook_question if show_hook else None,
            "hook_answer":   "",
            "upper_artist":  artist_name if show_upper else "",
            "upper_title":   painting_title if show_upper else "",
            "hold_seconds":  hold,
        }

    if voice_duration > 0:
        total_w     = max(1, act1_words + narr_words + data_words)
        act1_ratio  = act1_words / total_w if act1_words > 0 else 0.12
        act3_ratio  = data_words / total_w if data_words > 0 else 0.15
        act1_hold   = max(2.0, round(voice_duration * act1_ratio, 1))
        act3_hold   = max(3.0, round(voice_duration * act3_ratio, 1))
        crop_hold_s = max(0.3, round(
            (voice_duration - act1_hold - act3_hold) / max(1, n_act2_images), 1
        ))
    else:
        act1_hold   = 8.0
        act3_hold   = 10.0
        crop_hold_s = max(0.3, round(5.0 / max(1, n_act2_images), 1))

    frames = [_frame(hold=act1_hold, show_hook=True)]
    for _ in range(n_act2_images):
        frames.append(_frame(hold=crop_hold_s, show_upper=False))
    frames.append(_frame(hold=act3_hold, show_data=True))

    # Trim Act I only when no voice — with voice, duration is already correct
    if voice_duration <= 0:
        act1_floor = 4.2
        total = sum(f["hold_seconds"] + _FRAME_FADE_S for f in frames)
        if total > _MAX_REEL_SECONDS:
            cut = min(total - _MAX_REEL_SECONDS,
                      max(0.0, frames[0]["hold_seconds"] - act1_floor))
            frames[0]["hold_seconds"] = round(frames[0]["hold_seconds"] - cut, 1)

    return frames


_split_sentences  = reel_utils.split_sentences
_words_to_captions = reel_utils.words_to_captions
_burn_captions     = reel_utils.burn_captions


def _truncate_to_sentences(text: str, max_words: int) -> str:
    """Trim text to max_words, preferring a clean sentence boundary."""
    words = text.split()
    if len(words) <= max_words:
        return text
    trimmed = " ".join(words[:max_words])
    for punct in (".", "!", "?"):
        idx = trimmed.rfind(punct)
        if idx > len(trimmed) * 0.5:
            return trimmed[:idx + 1]
    return trimmed


# ── Config generation ──────────────────────────────────────────────────────────

def _generate_config(hook: dict, week_label: str, all_time: bool,
                     reveal: list[dict] | None = None,
                     narration_captions: list[dict] | None = None) -> str:
    artist    = _clean_artist(hook.get("artist") or "Unknown")
    title     = (hook.get("title") or "Untitled")[:50]
    hammer    = hook["hammer_usd"]
    est_low   = hook["estimate_low"]
    est_high  = hook.get("estimate_high") or est_low
    pct       = _pct_above(hammer, est_low)
    house     = hook.get("auction_house") or "Auction House"
    sale_name = (hook.get("sale_name") or "Contemporary Sale")[:40]
    scraped   = (hook.get("scraped_at") or "")[:10]

    est_str  = f"estimate: {_fmt_price(est_low)}–{_fmt_price(est_high)}"
    sold_str = f"sold: {_fmt_price(hammer)}."
    pct_str  = f"+{pct:,.0f}% above estimate."

    year         = scraped[:4] if scraped else str(date.today().year)
    tag_line     = f"@thehammerprice  ·  {artist.lower()}  ·  {year}"
    house_upper  = house.upper()
    sale_upper   = sale_name.upper()

    caption_full = (
        f"the auction house said {_fmt_price(est_low)}. the room said {_fmt_price(hammer)}. "
        f"{artist}'s {title} sold for +{pct:,.0f}% above the low estimate. "
        f"this is what happens when the data knows something the catalogue does not."
    )
    personal_note   = (
        "51% of lots at the major houses sell above estimate. "
        "that's not randomness — it's a pattern, and it's exploitable."
    )
    engagement_hook = (
        "what's the biggest auction surprise you've ever seen? "
        "drop the lot in the comments #thehammerprice #artmarket #auctionresults"
    )

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
        f'    "lot_id":         "{_esc(hook.get("id", ""))}",',
        "",
        "    # ── Caption ────────────────────────────────────────────────",
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
        "    # ── Layout ────────────────────────────────────────────────",
        '    "photo_fit_first":  True,',
        "",
        "    # ── Style ─────────────────────────────────────────────────",
        '    "vibe":             "auction_editorial",',
        '    "caption_position": "lower_safe",',
        '    "bg_music":         True,',
        '    "transitions_enabled": False,',
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
        '    "color_line1": (210, 200, 178),',
        '    "color_line2": (201, 168, 76),',
        '    "color_line3": (230, 215, 175),',
        "",
        '    "caption_all_frames": False,',
        '    "cover_hold_seconds": 2.0,   # held at start for platform thumbnail auto-selection',
        "",
        "    # ── Pacing ────────────────────────────────────────────────",
        '    "fps":          5,',
        '    "hold_seconds": 0.0,',
        '    "fade_seconds": 0.8,',
        "",
        "    # ── Social captions ───────────────────────────────────────",
        '    "topic":           "culture",',
        f'    "location":        "{_esc(house)}",',
        f'    "season":          "{_esc(scraped[:4])}",',
        '    "caption_full":    (',
        f'        "{_esc(caption_full)}"',
        "    ),",
        '    "caption_hero":    "they priced it wrong",',
        f'    "personal_note":   "{_esc(personal_note)}",',
        f'    "engagement_hook": "{_esc(engagement_hook)}",',
    ]

    if reveal:
        lines.append("")
        lines.append("    # ── Progressive reveal — one entry per frame ─────────────")
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


# ── AI caption writer ──────────────────────────────────────────────────────────

def _write_ai_captions(captions: dict, reel_dir: Path, lot: dict) -> None:
    """Write AI-generated captions in the same captions.md format as make_captions.py."""
    from datetime import datetime
    out = reel_dir / "output" / "captions.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    artist = lot.get("artist", "Unknown")
    house  = lot.get("auction_house", "Auction")
    now    = datetime.now()

    linkedin_block = ""
    if captions.get("linkedin"):
        linkedin_block = (
            "## 💼 LinkedIn\n\n"
            "**Best time to post:** Tue–Thu, 8–10am or 12–1pm (your local time)\n"
            "**Video:** `output/reel.mp4`\n\n"
            f"### Caption\n\n```\n{captions['linkedin']}\n```\n\n---\n\n"
        )

    out.write_text(
        f"# Social Media Captions\n"
        f"*{artist} · {house} · {now.year}*\n\n---\n\n"
        f"## 📸 Instagram\n\n"
        f"**Best time to post:** Tue–Fri, 11am–1pm or 7–9pm (your local time)\n"
        f"**Cover image:** `output/reel.png`\n\n"
        f"### Caption\n\n```\n{captions['instagram']}\n```\n\n---\n\n"
        f"## 🎵 TikTok\n\n"
        f"**Best time to post:** Tue–Thu 7–9pm or Sat morning (your local time)\n"
        f"**Video:** `output/reel.mp4`\n\n"
        f"### Caption\n\n```\n{captions['tiktok']}\n```\n\n---\n\n"
        f"{linkedin_block}"
        f"*Generated {now.strftime('%B %d, %Y')} · AI*\n"
    )


_normalise_word_timings = reel_utils.normalise_word_timings

# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Auto-generate a reel from weekly art auction data"
    )
    parser.add_argument("--week",         default=None,   help="ISO date in target week (default: today)")
    parser.add_argument("--all-time",     action="store_true", help="Use all-time top lots instead of weekly")
    parser.add_argument("--run",          action="store_true", help="Run make_reel.py after generation")
    parser.add_argument("--voice",        action="store_true", help="Generate TTS narration via ElevenLabs")
    parser.add_argument("--top-n",        type=int, default=8,    help="Max lots to query (default: 8)")
    parser.add_argument("--lot-index",    type=int, default=0,    help="Which lot to use (0 = top)")
    parser.add_argument("--crop-method",  choices=("grid", "sliding"), default="grid")
    parser.add_argument("--crop-size",    type=int, default=565,  help="Square crop/tile size in pixels")
    parser.add_argument("--crop-stride",  type=int, default=None, help="Stride for sliding-window crops")
    parser.add_argument("--artist",       default=None, help="Filter lots by artist name (substring match)")
    parser.add_argument("--title",        default=None, help="Filter lots by painting title (substring match)")
    parser.add_argument("--list-artists", action="store_true", help="List all artists in the DB and exit")
    args = parser.parse_args()

    if args.list_artists:
        if not DB_PATH.exists():
            print(f"✗ Database not found: {DB_PATH}")
            sys.exit(1)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        _list_artists(conn)
        conn.close()
        sys.exit(0)

    # ── Resolve week ───────────────────────────────────────────
    ref_date             = date.fromisoformat(args.week) if args.week else date.today()
    week_start, week_end = _week_bounds(ref_date)
    week_label           = f"{week_start} / {week_end}"
    _slug_date           = week_start
    _slug_mode           = ""

    print("═" * 60)
    print("  AUTO-REEL GENERATOR — The Hammer Price")
    print(f"  Mode: {'all-time top outperformers' if args.all_time else f'week {week_label}'}")
    if args.artist:
        print(f"  Artist filter: \"{args.artist}\"")
    if args.title:
        print(f"  Title filter:  \"{args.title}\"")
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

    _candidate_n = max(args.top_n * 6, 50)
    if args.all_time:
        lots       = _query_alltime_top(conn, limit=_candidate_n, exclude_ids=skip,
                                        artist=args.artist, title=args.title)
        if not lots and args.artist:
            # Walk forward through the campaign rotation to find next artist with unposted lots
            rotation = list(dict.fromkeys(_ca.get_rotation(DB_PATH)))
            try:
                start_idx = next(i for i, a in enumerate(rotation)
                                 if a.lower() == args.artist.lower())
            except StopIteration:
                start_idx = 0
            fallback_artist = None
            for offset in range(1, len(rotation)):
                candidate = rotation[(start_idx + offset) % len(rotation)]
                if _query_alltime_top(conn, limit=1, exclude_ids=skip,
                                      artist=candidate, title=args.title):
                    fallback_artist = candidate
                    break
            if fallback_artist:
                print(f"\n  ⚠ All {args.artist} lots already posted — trying next candidate: {fallback_artist}")
                lots = _query_alltime_top(conn, limit=_candidate_n, exclude_ids=skip,
                                          artist=fallback_artist, title=args.title)
            else:
                print(f"\n  ⚠ All {args.artist} lots already posted — no rotation candidates found, falling back to unfiltered.")
                lots = _query_alltime_top(conn, limit=_candidate_n, exclude_ids=skip,
                                          artist=None, title=args.title)
        _slug_date = date.today().isoformat()
        _slug_mode = "alltime"
    else:
        lots = _query_top_lots(conn, week_start, week_end,
                               limit=_candidate_n, exclude_ids=skip,
                               artist=args.artist, title=args.title)
        if not lots:
            print(f"\n  No new data for week {week_label} — trying random unposted week...")
            rand = _query_random_week_lot(conn, exclude_ids=skip,
                                          artist=args.artist, title=args.title)
            if rand:
                w = rand[0]["scraped_at"][:10]
                wb_start, wb_end = _week_bounds(date.fromisoformat(w))
                lots       = _query_top_lots(conn, wb_start, wb_end,
                                             limit=_candidate_n, exclude_ids=skip,
                                             artist=args.artist, title=args.title)
                _slug_date = wb_start
                _slug_mode = "random"
                print(f"  Using random week: {wb_start}")
            if not lots:
                print("  Falling back to all-time top unposted lots.")
                lots       = _query_alltime_top(conn, limit=_candidate_n, exclude_ids=skip,
                                                artist=args.artist, title=args.title)
                _slug_mode = "fallback"

    notable_artists = _build_notable_artists_set(conn)

    scored = sorted(
        ((l, _score_lot(l, notable_artists)) for l in lots),
        key=lambda x: x[1], reverse=True,
    )[:args.top_n]
    lots = [l for l, _ in scored]
    if lots:
        print(f"\n  Composite scores (top {min(3, len(lots))}):")
        for l, score in scored[:3]:
            print(f"    {score:.0f}  "
                  f"{_clean_artist(l.get('artist') or '')}  "
                  f"+{_pct_above(l['hammer_usd'], l['estimate_low']):.0f}%  "
                  f"imgs={len(json.loads(l.get('image_urls') or '[]'))}  "
                  f"known={_artist_is_notable(l.get('artist') or '', notable_artists)}")

    if not lots:
        print("✗ No suitable lots found in database.")
        sys.exit(1)
    if args.lot_index >= len(lots):
        clamped = len(lots) - 1
        print(f"  ⚠ --lot-index {args.lot_index} out of range ({len(lots)} lots found) — using index {clamped}")
        args.lot_index = clamped

    hook   = lots[args.lot_index]
    artist = _clean_artist(hook.get("artist") or "Unknown")

    # Build descriptive slug: {date}_{artist-slug}_{title-slug}[_{mode}][_lot{n}]
    _artist_slug = _make_slug(artist)
    _title_slug  = _make_slug(hook.get("title") or "untitled", max_len=20)
    _parts       = [_slug_date, _artist_slug, _title_slug]
    if _slug_mode:
        _parts.append(_slug_mode)
    if args.lot_index > 0:
        _parts.append(f"lot{args.lot_index + 1}")
    reel_slug = "_".join(_parts)
    print(f"\n▸ Hook lot: {artist} — {hook.get('title', 'Untitled')[:50]}")
    print(f"  Estimate: {_fmt_price(hook['estimate_low'])}–{_fmt_price(hook.get('estimate_high') or hook['estimate_low'])}")
    print(f"  Hammer:   {_fmt_price(hook['hammer_usd'])}")
    print(f"  Result:   +{_pct_above(hook['hammer_usd'], hook['estimate_low']):,.0f}% above estimate")
    print(f"  House:    {hook.get('auction_house')}")

    # ── Create reel folder ─────────────────────────────────────
    reel_dir   = REELS_DIR / reel_slug
    images_dir = reel_dir / "images"
    output_dir = reel_dir / "output"
    crops_dir  = reel_dir / "_crops"

    for d in (reel_dir, output_dir):
        d.mkdir(parents=True, exist_ok=True)

    print(f"\n▸ Reel folder: {reel_dir}")

    # ── Download images ────────────────────────────────────────
    for stale in (reel_dir / "_src", images_dir):
        if stale.exists():
            shutil.rmtree(stale)
    images_dir.mkdir(parents=True, exist_ok=True)

    print("\n▸ Downloading images...")
    src_images = _download_lot_images(hook, reel_dir / "_src", max_images=1)

    # Generate crops
    if args.crop_method == "sliding":
        stride  = args.crop_stride or max(1, args.crop_size // 2)
        variants = _generate_sliding_window_crops(
            src_images, crops_dir, tile_size=args.crop_size,
            stride=stride, include_original=True,
        )
    else:
        target_size = (args.crop_size, args.crop_size) if args.crop_size else None
        variants = _generate_grid_crops(
            src_images, crops_dir, include_original=True, target_size=target_size,
        )
    src_images = variants if variants else src_images

    if not src_images:
        print("✗ No images downloaded — cannot generate reel.")
        sys.exit(1)

    n_images = _copy_images_to_dir(src_images, crops_dir, images_dir)
    n_crops  = sum(1 for p in src_images if p.parent == crops_dir)
    print(f"  {len(src_images) - n_crops} source + {n_crops} crops → {n_images} images in images/")

    if crops_dir.exists():
        shutil.rmtree(crops_dir)

    # Number of Act II frames (all frames except Act I and Act III)
    _n_act2 = max(1, len(src_images) - 2)

    # ── Hook question + template answer ───────────────────────
    _sale_year       = (hook.get("scraped_at") or str(date.today()))[:4]
    tag_base         = f"@thehammerprice  ·  {artist.lower()}  ·  {_sale_year}"
    _pct             = _pct_above(hook["hammer_usd"], hook["estimate_low"])
    _question, _tmpl_answer = _hook_caption(hook, _pct)

    _lot_preview = {
        "artist":        artist,
        "title":         (hook.get("title") or "Untitled")[:60],
        "auction_house": hook.get("auction_house") or "the auction house",
        "hammer_fmt":    _fmt_price(hook["hammer_usd"]),
        "estimate_fmt":  f"{_fmt_price(hook['estimate_low'])}–{_fmt_price(hook.get('estimate_high') or hook['estimate_low'])}",
        "pct_above":     _pct,
    }

    # Try AI-generated hook (specific to artist + result); falls back to template
    if OPENROUTER_KEY:
        try:
            from ai_content import generate_hook_question
            _ai_question = generate_hook_question(_lot_preview, _pct)
            if _ai_question:
                print(f"  ✓ AI hook: {_ai_question}")
                _question = _ai_question
            else:
                print(f"  ▸ Hook: using template ({_question})")
        except Exception as e:
            print(f"  ⚠ AI hook error: {e} — using template")

    # defaults — overwritten inside --voice block if voice is on
    reveal        = _build_reveal_sequence(hook, tag_base, n_act2_images=_n_act2,
                                           hook_question=_question)
    word_timings  = []
    narr_captions = []

    if args.voice:
        print("\n▸ Generating voiceover...")
        try:
            from ai_content import generate_voiceover, generate_hook_answer
        except Exception as e:
            print(f"  ⚠ Import error: {e} — skipping voice")
            generate_voiceover = generate_hook_answer = None

        if generate_voiceover:
            # AI hook answer (falls back to template)
            ai_hook_answer = None
            if generate_hook_answer and OPENROUTER_KEY:
                try:
                    ai_hook_answer = generate_hook_answer(_lot_preview, _question)
                    if ai_hook_answer:
                        print(f"  ✓ AI answer: {ai_hook_answer[:80]}...")
                except Exception as e:
                    print(f"  ⚠ AI hook answer error: {e} — using template")
            ai_hook_answer = ai_hook_answer or _tmpl_answer

            raw_appr = _truncate_to_sentences(ai_hook_answer or "", _APPRECIATION_MAX_WORDS)
            _data_suffix = (
                f"the estimate was {_fmt_price_tts(hook['estimate_low'])} "
                f"to {_fmt_price_tts(hook.get('estimate_high') or hook['estimate_low'])}. "
                f"it sold for {_fmt_price_tts(hook['hammer_usd'])}. "
                f"that's plus {_pct:.0f} percent above estimate."
            )
            _intro           = f"this is {hook.get('title') or 'untitled'}, by {artist}."
            _act1_spoken     = _intro + "  " + _prices_to_speech(_question)
            _narr_spoken     = _prices_to_speech(raw_appr)
            _act1_word_count = len(_act1_spoken.split())
            _narr_word_count = len(_narr_spoken.split())
            _data_word_count = len(_data_suffix.split())
            # Full script: Act I (intro + hook question) → Act II (narration) → Act III (price data)
            appreciation_text = _act1_spoken + "  " + _narr_spoken + "  " + _data_suffix

            vo_path = reel_dir / "voiceover.mp3"
            _ok_appr, word_timings = generate_voiceover(appreciation_text, str(vo_path))
            word_timings = _normalise_word_timings(word_timings)
            if _ok_appr and word_timings:
                narr_captions = _words_to_captions(word_timings)
                appreciation_duration = word_timings[-1]["end"] + 0.5
                print(f"  ✓ Voiceover ({appreciation_duration:.1f}s, {len(word_timings)} words, {len(narr_captions)} cues)")
                reveal = _build_reveal_sequence(
                    hook, tag_base,
                    n_act2_images=_n_act2,
                    voice_duration=appreciation_duration,
                    act1_words=_act1_word_count,
                    narr_words=_narr_word_count,
                    data_words=_data_word_count,
                    hook_question=_question,
                )
    # ── Write reel_config.py ───────────────────────────────────
    config_path = reel_dir / "reel_config.py"
    config_path.write_text(_generate_config(hook, week_label, args.all_time, reveal=reveal, narration_captions=narr_captions or None))
    print(f"\n▸ Config written: {config_path}")

    # ── Record in posted_reels ─────────────────────────────────
    _record_posted(conn, hook, reel_slug, ["instagram", "tiktok", "linkedin"])
    conn.close()

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

    # ── Optionally run make_reel.py ────────────────────────────
    if args.run:
        print("\n▸ Running make_reel.py...")
        r1 = subprocess.run(
            [sys.executable, str(REEL_TEMPLATE / "make_reel.py"), str(reel_dir)],
            cwd=str(REEL_TEMPLATE.parent),
        )

        if r1.returncode == 0:
            ai_done = False
            if OPENROUTER_KEY:
                print("\n▸ Generating AI captions via OpenRouter...")
                try:
                    from ai_content import generate_captions
                    est_high_ = hook.get("estimate_high") or hook["estimate_low"]
                    pct_      = _pct_above(hook["hammer_usd"], hook["estimate_low"])
                    lot_data  = {
                        "artist":        artist,
                        "title":         (hook.get("title") or "Untitled")[:60],
                        "auction_house": hook.get("auction_house") or "the auction house",
                        "hammer_fmt":    _fmt_price(hook["hammer_usd"]),
                        "estimate_fmt":  f"{_fmt_price(hook['estimate_low'])}–{_fmt_price(est_high_)}",
                        "pct_above":     pct_,
                        "sale_name":     (hook.get("sale_name") or "").strip(),
                        "source_url":    (hook.get("source_url") or "").strip(),
                    }
                    captions = generate_captions(lot_data)
                    if captions:
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
                    cwd=str(REEL_TEMPLATE.parent),
                )

if __name__ == "__main__":
    main()