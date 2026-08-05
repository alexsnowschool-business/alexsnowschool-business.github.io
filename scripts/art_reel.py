#!/usr/bin/env python3
"""
art_reel.py — price-first single-lot cards

Three PNGs per lot, rendered directly with Pillow — no video pipeline, no TTS:
  00_number.png   — shock stat on dark background  (+N% above estimate)
  01_art.png      — full-bleed artwork + artist / house / year
  02_verdict.png  — estimate / sold / one-liner verdict
  meta.json       — lot data + social captions

Usage:
    python scripts/art_reel.py              # this week's best lot
    python scripts/art_reel.py --all-time   # best ever unposted
    python scripts/art_reel.py --artist "Basquiat"
    python scripts/art_reel.py --list       # preview top candidates
    python scripts/art_reel.py --list-artists
"""

import argparse
import json
import math
import os
import random
import re
import sqlite3
import sys
import unicodedata
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
BUSINESS_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
import campaign_artist as _ca

load_dotenv(BUSINESS_DIR / ".env", override=False)

DB_PATH    = BUSINESS_DIR / "data" / "art.db"
OUTPUT_DIR = BUSINESS_DIR / "output" / "art"
FONTS_DIR  = BUSINESS_DIR / "reel_template" / "fonts"

# ── Card dimensions ────────────────────────────────────────────────────────────
W, H   = 1080, 1350
MARGIN = 72

# ── Palette ────────────────────────────────────────────────────────────────────
BG        = (20, 18, 16)
GOLD      = (201, 168, 76)
GOLD_DIM  = (100, 82, 45)
IVORY     = (245, 240, 232)
IVORY_DIM = (185, 165, 130)
GHOST     = (90, 83, 68)

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


# ── Font cache ─────────────────────────────────────────────────────────────────

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(FONTS_DIR / name), size)
    return _font_cache[key]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt(usd: float) -> str:
    return f"${usd:,.0f}"

def _pct_above(hammer: float, low: float) -> float:
    return round((hammer / low - 1) * 100, 1)

def _clean_artist(name: str) -> str:
    return re.sub(r"\s*\([^)]+\)\s*$", "", name or "").strip().title()

def _clean_house(raw: str) -> str:
    for key, label in [
        ("sotheby",  "Sotheby's"),
        ("christie", "Christie's"),
        ("phillips", "Phillips"),
        ("bonham",   "Bonhams"),
        ("ketterer", "Ketterer"),
        ("van ham",  "Van Ham"),
        ("grisebach","Grisebach"),
        ("lempertz", "Lempertz"),
    ]:
        if key in (raw or "").lower():
            return label
    return raw or "—"

def _strip_accents(s: str | None) -> str | None:
    if s is None:
        return None
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def _wrap(draw: ImageDraw.ImageDraw, text: str,
          font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words = text.split()
    lines, line = [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_w:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines

def _crop_fill(img: Image.Image, w: int, h: int) -> Image.Image:
    iw, ih = img.size
    if iw / ih > w / h:
        nw = int(ih * w / h)
        img = img.crop(((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih))
    else:
        nh = int(iw * h / w)
        top = max(0, (ih - nh) // 3)
        img = img.crop((0, top, iw, top + nh))
    return img.resize((w, h), Image.LANCZOS)

def _download_photo(url: str | None) -> Image.Image | None:
    if not url:
        return None
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception as e:
        print(f"  ⚠ photo download failed: {e}")
        return None

def _first_image_url(lot: dict) -> str | None:
    raw = lot.get("image_urls")
    if isinstance(raw, list):
        return raw[0] if raw else None
    if isinstance(raw, str):
        try:
            return json.loads(raw)[0]
        except (TypeError, ValueError, IndexError):
            return None
    return None

def _week_bounds(ref_date: date) -> tuple[str, str]:
    monday = ref_date - timedelta(days=ref_date.weekday())
    return monday.isoformat(), (monday + timedelta(days=6)).isoformat()

def _make_slug(s: str, max_len: int = 30) -> str:
    s = _strip_accents(s) or s
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:max_len].rstrip("-")


# ── Card renderers ─────────────────────────────────────────────────────────────

def render_number_card(lot: dict) -> Image.Image:
    """Frame 1: +N% above estimate — the hook, full screen on dark bg."""
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    pct  = _pct_above(lot["hammer_usd"], lot["estimate_low"])
    cw   = W - MARGIN * 2

    # Main stat — scale down if too wide
    pct_str  = f"+{pct:,.0f}%"
    pct_size = 200
    pct_font = _font("Outfit-Bold.ttf", pct_size)
    while draw.textlength(pct_str, font=pct_font) > cw and pct_size > 80:
        pct_size -= 10
        pct_font  = _font("Outfit-Bold.ttf", pct_size)

    sub_font = _font("Outfit-Regular.ttf", 48)
    sub_str  = "above estimate"

    pb      = draw.textbbox((0, 0), pct_str, font=pct_font)
    sb      = draw.textbbox((0, 0), sub_str, font=sub_font)
    pct_h   = pb[3] - pb[1]
    sub_h   = sb[3] - sb[1]
    block_h = pct_h + 20 + sub_h
    y       = (H - block_h) // 2 - 40   # slightly above center

    pct_w = draw.textlength(pct_str, font=pct_font)
    draw.text(((W - pct_w) // 2, y), pct_str, font=pct_font, fill=GOLD)
    y += pct_h + 20
    sub_w = draw.textlength(sub_str, font=sub_font)
    draw.text(((W - sub_w) // 2, y), sub_str, font=sub_font, fill=IVORY_DIM)

    # Bottom rule + artist name + brand tag
    rule_y = H - MARGIN - 52
    af     = _font("Outfit-Regular.ttf", 30)
    artist = _clean_artist(lot.get("artist") or "Unknown")
    draw.line([(MARGIN, rule_y), (W - MARGIN, rule_y)], fill=GHOST, width=1)
    draw.text((MARGIN, rule_y + 14), artist.lower(), font=af, fill=GHOST)
    tag   = "@thehammerprice"
    tag_w = draw.textlength(tag, font=af)
    draw.text((W - MARGIN - tag_w, rule_y + 14), tag, font=af, fill=GOLD_DIM)

    return img


def render_art_card(lot: dict, photo: Image.Image | None) -> Image.Image:
    """Frame 2: full-bleed artwork + artist / house / year overlay."""
    img = Image.new("RGB", (W, H), (30, 27, 24))
    if photo:
        img.paste(_crop_fill(photo, W, H), (0, 0))

    # Bottom gradient — lower 42%
    fade_top = int(H * 0.58)
    fade_h   = H - fade_top
    fade     = Image.new("RGB", (W, fade_h), (8, 7, 6))
    mask     = Image.new("L", (W, fade_h), 0)
    md       = ImageDraw.Draw(mask)
    for row in range(fade_h):
        alpha = int(230 * (row / fade_h) ** 1.3)
        md.line([(0, row), (W, row)], fill=alpha)
    img.paste(fade, (0, fade_top), mask)

    draw   = ImageDraw.Draw(img)
    artist = _clean_artist(lot.get("artist") or "Unknown")
    house  = _clean_house(lot.get("auction_house") or "")
    year   = (lot.get("sale_date") or lot.get("scraped_at") or "")[:4]
    meta   = "  ·  ".join(x for x in [house, year] if x)

    af = _font("Outfit-Bold.ttf", 52)
    mf = _font("Outfit-Regular.ttf", 30)
    ab = draw.textbbox((0, 0), artist, font=af)
    mb = draw.textbbox((0, 0), meta, font=mf)
    y  = H - MARGIN - (ab[3] - ab[1]) - 12 - (mb[3] - mb[1])

    draw.text((MARGIN, y), artist, font=af, fill=IVORY)
    y += (ab[3] - ab[1]) + 12
    draw.text((MARGIN, y), meta, font=mf, fill=IVORY_DIM)

    return img


def render_verdict_card(lot: dict, one_liner: str) -> Image.Image:
    """Frame 3: estimate / sold / one-liner verdict on dark bg."""
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    cw   = W - MARGIN * 2

    hammer = lot["hammer_usd"]
    est_lo = lot["estimate_low"]
    est_hi = lot.get("estimate_high") or est_lo

    lf = _font("Outfit-Regular.ttf", 28)   # labels
    df = _font("Outfit-Regular.ttf", 40)   # estimate value
    vf = _font("Outfit-Bold.ttf",    60)   # sold value
    ol = _font("Outfit-Regular.ttf", 36)   # one-liner

    y = H // 3 - 40

    # estimate
    draw.text((MARGIN, y), "estimate", font=lf, fill=GHOST)
    y += draw.textbbox((0, 0), "estimate", font=lf)[3] + 8
    est_str = f"{_fmt(est_lo)}–{_fmt(est_hi)}"
    draw.text((MARGIN, y), est_str, font=df, fill=IVORY_DIM)
    y += draw.textbbox((0, 0), est_str, font=df)[3] + 30

    # divider
    draw.line([(MARGIN, y), (W - MARGIN, y)], fill=GHOST, width=1)
    y += 22

    # sold
    draw.text((MARGIN, y), "sold", font=lf, fill=GHOST)
    y += draw.textbbox((0, 0), "sold", font=lf)[3] + 8
    draw.text((MARGIN, y), _fmt(hammer), font=vf, fill=GOLD)
    y += draw.textbbox((0, 0), _fmt(hammer), font=vf)[3] + 48

    # one-liner (max 3 lines)
    for line in _wrap(draw, one_liner, ol, cw)[:3]:
        draw.text((MARGIN, y), line, font=ol, fill=IVORY)
        y += draw.textbbox((0, 0), line, font=ol)[3] + 10

    # Brand footer
    tf    = _font("Outfit-Regular.ttf", 26)
    tag   = "@thehammerprice"
    ry    = H - MARGIN - 46
    draw.line([(MARGIN, ry), (W - MARGIN, ry)], fill=GHOST, width=1)
    draw.text((MARGIN, ry + 14), tag, font=tf, fill=GOLD_DIM)

    return img


# ── Scoring ────────────────────────────────────────────────────────────────────

def _artist_is_notable(artist: str, notable_set: set[str] | None = None) -> bool:
    cleaned = _clean_artist(artist)
    if notable_set and cleaned in notable_set:
        return True
    cl = cleaned.lower()
    return any(k in cl or cl in k for k in _KNOWN_ARTISTS_LOWER)

def _score_lot(lot: dict, notable_set: set[str] | None = None) -> float:
    pct          = _pct_above(lot["hammer_usd"], lot["estimate_low"])
    hammer_usd   = lot["hammer_usd"] or 0
    pct_bonus    = math.log1p(max(pct, 0)) * 10
    hammer_bonus = math.log10(hammer_usd) * 5 if hammer_usd >= 100_000 else 0
    is_known     = _artist_is_notable(lot.get("artist") or "", notable_set)
    return pct_bonus + (is_known * 20) + (hammer_bonus * 0.75)


# ── Captions ───────────────────────────────────────────────────────────────────

def _hook_caption(lot: dict, pct: float) -> tuple[str, str]:
    """Return (question, answer) from the per-tier hook templates."""
    mult     = round(pct / 100 + 1, 1)
    artist   = _clean_artist(lot.get("artist") or "Unknown")
    title    = (lot.get("title") or "Untitled")[:40]
    house    = lot.get("auction_house") or "the auction house"
    hammer   = _fmt(lot["hammer_usd"])
    est_lo   = lot["estimate_low"]
    est_hi   = lot.get("estimate_high") or est_lo
    estimate = f"{_fmt(est_lo)}–{_fmt(est_hi)}"
    fmt = dict(n=f"{mult:.0f}×", artist=artist, title=title, house=house,
               hammer=hammer, estimate=estimate, pct=f"{pct:,.0f}%")
    for threshold, q_variants, a_variants in _HOOK_TEMPLATES:
        if pct >= threshold:
            return (random.choice(q_variants).format(**fmt),
                    random.choice(a_variants).format(**fmt))
    return "the hammer price tells the real story.", "follow the data."

def _social_captions(lot: dict, question: str, answer: str) -> dict:
    """Instagram (full) + TikTok (tight) social captions."""
    pct    = _pct_above(lot["hammer_usd"], lot["estimate_low"])
    artist = _clean_artist(lot.get("artist") or "Unknown").lower()
    house  = _clean_house(lot.get("auction_house") or "").lower()

    # Trim answer to first 2 sentences for the caption body
    sentences    = re.split(r'(?<=[.!?])\s+', answer.strip())
    short_answer = " ".join(sentences[:2])

    ig = (
        f"+{pct:,.0f}% above estimate.\n\n"
        f"{question}\n\n"
        f"{short_answer}\n\n"
        f"estimate {_fmt(lot['estimate_low'])}  ·  "
        f"sold {_fmt(lot['hammer_usd'])}  ·  {house}\n\n"
        f"#thehammerprice #artmarket #auctionresults #artcollecting"
    )
    tt = (
        f"+{pct:,.0f}% above estimate. {question}\n"
        f"follow for weekly auction data.\n\n"
        f"#thehammerprice #artmarket #auctionresults #foryou #artcollecting"
    )
    return {"instagram": ig, "tiktok": tt}


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.create_function("strip_accents", 1, _strip_accents)
    return conn

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
    return {r[0] for r in conn.execute("SELECT lot_id FROM posted_reels").fetchall()}

def _posted_count_for_artist(conn: sqlite3.Connection, artist: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM posted_reels WHERE LOWER(artist) LIKE LOWER(?)",
        (f"%{artist}%",),
    ).fetchone()
    return row[0] if row else 0

def _record_posted(conn: sqlite3.Connection, lot: dict, slug: str,
                   platforms: list[str]) -> None:
    conn.execute("""
        INSERT OR REPLACE INTO posted_reels
            (lot_id, artist, title, hammer_usd, reel_slug, platforms)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (lot["id"], lot.get("artist"), lot.get("title"),
          lot.get("hammer_usd"), slug, ",".join(platforms)))
    conn.commit()
    print(f"  ✓ recorded: {lot.get('artist')} — {lot.get('title', '')[:40]}")

def _like_clauses(artist: str | None, title: str | None) -> tuple[str, list]:
    parts, params = [], []
    if artist:
        parts.append("AND strip_accents(LOWER(artist)) LIKE strip_accents(LOWER(?))")
        params.append(f"%{artist}%")
    if title:
        parts.append("AND title LIKE ?")
        params.append(f"%{title}%")
    return " ".join(parts), params

def _query_lots(conn: sqlite3.Connection, limit: int = 50,
                exclude_ids: set | None = None,
                artist: str | None = None, title: str | None = None,
                week_start: str | None = None, week_end: str | None = None,
                order_by: str = "pct_above DESC") -> list[dict]:
    exclude      = tuple(exclude_ids or [])
    placeholders = ",".join("?" * len(exclude)) if exclude else "NULL"
    flt_sql, flt_params = _like_clauses(artist, title)
    date_sql    = "AND substr(scraped_at, 1, 10) BETWEEN ? AND ?" if week_start else ""
    date_params = (week_start, week_end) if week_start else ()
    rows = conn.execute(f"""
        SELECT id, artist, title, hammer_usd, estimate_low, estimate_high,
               sale_name, sale_date, scraped_at, auction_house, image_urls, source_url,
               ROUND((hammer_usd * 1.0 / estimate_low - 1) * 100, 1) AS pct_above
        FROM art_items
        WHERE sale_performance = 'above'
          AND hammer_usd IS NOT NULL
          AND estimate_low IS NOT NULL AND estimate_low > 0
          {date_sql}
          {flt_sql}
          {"AND id NOT IN (" + placeholders + ")" if exclude else ""}
        ORDER BY {order_by}
        LIMIT ?
    """, (*date_params, *flt_params, *exclude, limit)).fetchall()
    return [dict(r) for r in rows]

def _query_random_week_lot(conn: sqlite3.Connection,
                           exclude_ids: set | None = None,
                           artist: str | None = None) -> list[dict]:
    exclude      = tuple(exclude_ids or [])
    placeholders = ",".join("?" * len(exclude)) if exclude else "NULL"
    flt_sql, flt_params = _like_clauses(artist, None)
    rows = conn.execute(f"""
        SELECT id, artist, title, hammer_usd, estimate_low, estimate_high,
               sale_name, sale_date, scraped_at, auction_house, image_urls, source_url,
               ROUND((hammer_usd * 1.0 / estimate_low - 1) * 100, 1) AS pct_above,
               strftime('%Y-%W', scraped_at) AS week_key
        FROM art_items
        WHERE sale_performance = 'above'
          AND hammer_usd IS NOT NULL
          AND estimate_low IS NOT NULL AND estimate_low > 0
          {flt_sql}
          {"AND id NOT IN (" + placeholders + ")" if exclude else ""}
        GROUP BY week_key HAVING MAX(pct_above)
        ORDER BY RANDOM() LIMIT 1
    """, (*flt_params, *exclude)).fetchall()
    return [dict(r) for r in rows]

def _build_notable_artists_set(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("""
        SELECT artist FROM art_items
        WHERE hammer_usd IS NOT NULL AND artist IS NOT NULL
        GROUP BY artist HAVING COUNT(*) >= 2 OR AVG(hammer_usd) > 50000
    """).fetchall()
    return {_clean_artist(r[0]) for r in rows if r[0]}

def _list_artists(conn: sqlite3.Connection) -> None:
    rows = conn.execute("""
        SELECT artist, COUNT(*) AS lots,
               ROUND(AVG(hammer_usd)) AS avg_hammer,
               ROUND(MAX(hammer_usd)) AS max_hammer,
               ROUND(AVG((hammer_usd * 1.0 / NULLIF(estimate_low, 0) - 1) * 100), 1) AS avg_pct
        FROM art_items
        WHERE hammer_usd IS NOT NULL AND artist IS NOT NULL
        GROUP BY artist ORDER BY lots DESC, avg_hammer DESC
    """).fetchall()
    if not rows:
        print("No artists found in database.")
        return
    print(f"\n{'#':<5} {'Artist':<40} {'Lots':>5} {'Avg $':>10} {'Max $':>10} {'Avg %+':>7}")
    print("─" * 80)
    for i, r in enumerate(rows, 1):
        name = _clean_artist(r["artist"] or "Unknown")
        avg  = f"${int(r['avg_hammer']):,}" if r["avg_hammer"] else "—"
        mx   = f"${int(r['max_hammer']):,}" if r["max_hammer"] else "—"
        pct  = f"+{r['avg_pct']:.1f}%"      if r["avg_pct"]    else "—"
        print(f"{i:<5} {name:<40} {r['lots']:>5} {avg:>10} {mx:>10} {pct:>7}")
    print(f"\n  {len(rows)} artists total. Use --artist \"<name>\" to filter.")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate price-first auction lot cards"
    )
    parser.add_argument("--list",         action="store_true", help="Preview top candidates without generating")
    parser.add_argument("--list-artists", action="store_true", help="List all artists in DB and exit")
    parser.add_argument("--all-time",     action="store_true", help="Best ever unposted (ignores week)")
    parser.add_argument("--week",         default=None,        help="ISO date in target week (default: today)")
    parser.add_argument("--artist",       default=None,        help="Filter by artist name (substring)")
    parser.add_argument("--title",        default=None,        help="Filter by title (substring)")
    parser.add_argument("--output-dir",   default=str(OUTPUT_DIR))
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"✗ Database not found: {DB_PATH}")
        sys.exit(1)

    conn = _open_db(DB_PATH)
    _ensure_posted_table(conn)

    if args.list_artists:
        _list_artists(conn)
        conn.close()
        sys.exit(0)

    ref_date             = date.fromisoformat(args.week) if args.week else date.today()
    week_start, week_end = _week_bounds(ref_date)
    order_by             = "hammer_usd DESC" if args.artist else "pct_above DESC"

    print("═" * 60)
    print("  ART REEL — The Hammer Price")
    print(f"  Mode: {'all-time' if args.all_time else f'week {week_start} / {week_end}'}")
    if args.artist:
        print(f"  Artist: \"{args.artist}\"")
    print("═" * 60)

    skip = _posted_ids(conn)
    if skip:
        print(f"\n  ℹ Skipping {len(skip)} already-posted lot(s).")

    # ── Query ──────────────────────────────────────────────────
    if args.all_time:
        lots = _query_lots(conn, 50, skip, args.artist, args.title, order_by=order_by)

        # Campaign rotation fallback — if all lots for this artist are posted
        if not lots and args.artist:
            rotation = list(dict.fromkeys(_ca.get_rotation(DB_PATH)))
            try:
                start_idx = next(i for i, a in enumerate(rotation)
                                 if a.lower() == args.artist.lower())
            except StopIteration:
                start_idx = 0
            for offset in range(1, len(rotation)):
                next_artist = rotation[(start_idx + offset) % len(rotation)]
                if _posted_count_for_artist(conn, next_artist) >= _ca.MAX_LOTS_PER_ARTIST:
                    continue
                if _query_lots(conn, 1, skip, next_artist, order_by=order_by):
                    print(f"\n  ⚠ All {args.artist} lots posted — trying: {next_artist}")
                    lots = _query_lots(conn, 50, skip, next_artist, order_by=order_by)
                    break
            if not lots:
                print(f"\n  ⚠ No rotation candidate found — falling back to unfiltered.")
                lots = _query_lots(conn, 50, skip, order_by=order_by)
    else:
        lots = _query_lots(conn, 50, skip, args.artist, args.title,
                           week_start, week_end, order_by)
        if not lots:
            rand = _query_random_week_lot(conn, skip, args.artist)
            if rand:
                ws, we = _week_bounds(date.fromisoformat(rand[0]["scraped_at"][:10]))
                print(f"  No data this week — using random week: {ws}")
                lots = _query_lots(conn, 50, skip, args.artist, args.title, ws, we, order_by)
        if not lots:
            print("  Falling back to all-time top unposted.")
            lots = _query_lots(conn, 50, skip, args.artist, args.title, order_by=order_by)

    # ── Score + pick top lot ───────────────────────────────────
    notable = _build_notable_artists_set(conn)
    scored  = sorted(((l, _score_lot(l, notable)) for l in lots),
                     key=lambda x: x[1], reverse=True)

    if not scored:
        print("✗ No suitable lots found.")
        conn.close()
        sys.exit(1)

    lot    = scored[0][0]
    artist = _clean_artist(lot.get("artist") or "Unknown")
    pct    = _pct_above(lot["hammer_usd"], lot["estimate_low"])

    print(f"\n▸ {artist}")
    print(f"  {(lot.get('title') or 'Untitled')[:60]}")
    print(f"  estimate  {_fmt(lot['estimate_low'])}–{_fmt(lot.get('estimate_high') or lot['estimate_low'])}")
    print(f"  sold      {_fmt(lot['hammer_usd'])}  (+{pct:.0f}%)")
    print(f"  {lot.get('auction_house')}")

    # Preview candidates in --list mode (show top 5 and exit)
    if args.list:
        print(f"\n  {'#':<4} {'Artist':<30} {'Hammer':>12} {'%+':>7}  Score")
        print("  " + "─" * 60)
        for i, (l, score) in enumerate(scored[:5], 1):
            p = _pct_above(l["hammer_usd"], l["estimate_low"])
            print(f"  {i:<4} {_clean_artist(l.get('artist') or '')[:29]:<30} "
                  f"{_fmt(l['hammer_usd']):>12}  {p:>5.0f}%  {score:.0f}")
        conn.close()
        return

    # ── Build output path ──────────────────────────────────────
    slug    = (f"{ref_date.isoformat()}_"
               f"{_make_slug(artist)}_"
               f"{_make_slug(lot.get('title') or 'untitled', 20)}")
    out_dir = Path(args.output_dir) / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Download photo ─────────────────────────────────────────
    print("\n▸ Downloading artwork...")
    photo = _download_photo(_first_image_url(lot))
    print("  ✓ photo" if photo else "  ⚠ no photo — art card will use dark bg")

    # ── Hook + captions ────────────────────────────────────────
    question, answer = _hook_caption(lot, pct)
    captions         = _social_captions(lot, question, answer)

    # ── Render 3 cards ─────────────────────────────────────────
    print("\n▸ Rendering cards...")
    cards = [
        ("00_number.png",  render_number_card(lot)),
        ("01_art.png",     render_art_card(lot, photo)),
        ("02_verdict.png", render_verdict_card(lot, question)),
    ]
    for name, img in cards:
        img.save(out_dir / name)
        print(f"  ✓ {name}")

    # ── meta.json ──────────────────────────────────────────────
    meta = {
        "date":          ref_date.isoformat(),
        "slug":          slug,
        "lot_id":        lot.get("id"),
        "artist":        artist,
        "title":         lot.get("title"),
        "auction_house": _clean_house(lot.get("auction_house") or ""),
        "hammer_usd":    lot.get("hammer_usd"),
        "estimate_low":  lot.get("estimate_low"),
        "estimate_high": lot.get("estimate_high"),
        "pct_above":     pct,
        "question":      question,
        "answer":        answer,
        "captions":      captions,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    # ── Record in posted_reels ─────────────────────────────────
    _record_posted(conn, lot, slug, ["instagram", "tiktok"])
    conn.close()

    # ── Summary ────────────────────────────────────────────────
    print(f"\n✓ 3 cards → {out_dir}")
    print(f"\n  Instagram caption:\n")
    print("  " + captions["instagram"].replace("\n", "\n  "))
    print(f"\n  Post with:")
    print(f"    python scripts/post_beat_the_estimate_to_buffer.py "
          f"{out_dir.relative_to(BUSINESS_DIR)} --dry-run")


if __name__ == "__main__":
    main()
