#!/usr/bin/env python3
"""
Reading Quote Reel — Hermès aesthetic.

Picks unused quotes from the account's quotes.db (3 by default), pairs each
with its own blurred art background from art.db, renders animated 1080×1920
segments with a Ken Burns pan, TTS voiceover per quote (edge-tts, macOS `say`
fallback), ducked ambient music, and a CTA that fades in at the end.

Usage:
    python scripts/quote_reel.py                          # 3 quotes, 3 backgrounds, voiceover
    python scripts/quote_reel.py --count 1                # single-quote reel
    python scripts/quote_reel.py --account stoicism       # use a different account
    python scripts/quote_reel.py --id 42                  # use specific quote id (single)
    python scripts/quote_reel.py --no-voice               # skip TTS voiceover
    python scripts/quote_reel.py --preview                # render frame PNGs only, no video
    python scripts/quote_reel.py --dry-run                # print chosen quotes, do nothing
"""

import argparse
import io
import json
import sqlite3
import subprocess
import sys
import threading
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance

SCRIPT_DIR   = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
BUSINESS_DIR = SCRIPT_DIR.parent
FONTS_DIR    = BUSINESS_DIR / "reel_template" / "fonts"
MUSIC_DIR    = BUSINESS_DIR / "reel_template" / "music"
REELS_DIR    = BUSINESS_DIR / "reels"

W, H         = 1080, 1920
FPS          = 24
TOTAL_S      = 8.0
MUSIC_VOLUME = 0.30   # bumped from 0.25 for a stronger opening audio hook
MUSIC_VOLUME_DUCKED = 0.12  # music level while a voiceover is playing
KB_ZOOM      = 1.08   # Ken Burns: background rendered 8% oversize; we pan across it
FADE_S       = 0.5    # segment fade in/out duration
TTS_VOICE    = "en-US-ChristopherNeural"  # deep mature male; macOS `say` fallback
TTS_RATE     = "-8%"     # slightly slower for an older, unhurried delivery
TTS_PITCH    = "-12Hz"   # lower pitch for gravitas

DEFAULT_PALETTE = {
    "bg":     (14, 10, 6),
    "rule":   (185, 148, 68),
    "quote":  (245, 238, 212),
    "author": (185, 148, 68),
    "book":   (150, 122, 82),
    "tag":    (90, 72, 48),
}


def _palette(cfg: dict) -> dict:
    raw = cfg.get("palette", {})
    return {k: tuple(raw[k]) if k in raw else DEFAULT_PALETTE[k] for k in DEFAULT_PALETTE}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


# ── Fonts ─────────────────────────────────────────────────────────────────────

def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONTS_DIR / name
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


# ── Database helpers ──────────────────────────────────────────────────────────

def pick_quote(conn: sqlite3.Connection, quote_id: int | None = None) -> dict | None:
    if quote_id is not None:
        row = conn.execute(
            "SELECT id, text, author, book FROM quotes WHERE id = ?", (quote_id,)
        ).fetchone()
    else:
        # Prefer 60-110 char sweet spot
        row = conn.execute(
            "SELECT id, text, author, book FROM quotes "
            "WHERE used_at IS NULL AND LENGTH(text) BETWEEN 60 AND 110 "
            "ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
        if not row:  # fallback to full pool
            row = conn.execute(
                "SELECT id, text, author, book FROM quotes "
                "WHERE used_at IS NULL ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
    if not row:
        return None
    return {"id": row[0], "text": row[1], "author": row[2], "book": row[3]}


def pick_quotes(conn: sqlite3.Connection, n: int) -> list[dict]:
    """Pick up to n unused quotes, preferring the 60-110 char sweet spot."""
    rows = conn.execute(
        "SELECT id, text, author, book FROM quotes "
        "WHERE used_at IS NULL AND LENGTH(text) BETWEEN 60 AND 110 "
        "ORDER BY RANDOM() LIMIT ?", (n,)
    ).fetchall()
    if len(rows) < n:
        have = [r[0] for r in rows]
        placeholders = ",".join("?" * len(have)) or "-1"
        rows += conn.execute(
            f"SELECT id, text, author, book FROM quotes "
            f"WHERE used_at IS NULL AND id NOT IN ({placeholders}) "
            f"ORDER BY RANDOM() LIMIT ?", (*have, n - len(rows))
        ).fetchall()
    return [{"id": r[0], "text": r[1], "author": r[2], "book": r[3]} for r in rows]


def mark_quote_used(conn: sqlite3.Connection, quote_id: int):
    conn.execute(
        "UPDATE quotes SET used_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), quote_id),
    )
    conn.commit()


def pick_art_image_url(art_conn: sqlite3.Connection,
                       only_paintings: bool = False) -> tuple[str, str, str] | None:
    """Return (image_url, artist, title) for a random art item with images.

    `only_paintings` restricts to medium_category = 'painting' — excludes
    photography, sculpture, works on paper, manuscripts, etc.
    """
    query = (
        "SELECT artist, title, image_urls FROM art_items "
        "WHERE image_urls IS NOT NULL AND image_urls NOT IN ('', '[]') "
    )
    if only_paintings:
        query += "AND medium_category = 'painting' "
    query += "ORDER BY RANDOM() LIMIT 20"
    rows = art_conn.execute(query).fetchall()
    for artist, title, urls_json in rows:
        try:
            urls = json.loads(urls_json)
        except (json.JSONDecodeError, TypeError):
            continue
        if urls:
            return urls[0], artist, title
    return None


# ── Image helpers ─────────────────────────────────────────────────────────────

def download_image(url: str) -> Image.Image | None:
    try:
        with httpx.Client(timeout=20, follow_redirects=True) as client:
            r = client.get(url, headers=HEADERS)
            r.raise_for_status()
            return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception as e:
        print(f"  Warning: could not download art image: {e}")
        return None


def prepare_art(art_img: Image.Image | None, palette: dict) -> Image.Image:
    """Colour-grade and blur the painting — no dark overlay. Used as the cover frame."""
    base = Image.new("RGB", (W, H), palette["bg"])
    if art_img is None:
        return base

    aw, ah = art_img.size
    scale = max(W / aw, H / ah)
    nw, nh = int(aw * scale), int(ah * scale)
    art_img = art_img.resize((nw, nh), Image.LANCZOS)
    x = (nw - W) // 2
    y = (nh - H) // 2
    art_img = art_img.crop((x, y, x + W, y + H))

    art_img = ImageEnhance.Color(art_img).enhance(0.90)
    art_img = ImageEnhance.Contrast(art_img).enhance(0.95)
    art_img = ImageEnhance.Brightness(art_img).enhance(0.90)
    r, g, b = art_img.split()
    r = r.point(lambda v: min(255, int(v * 1.04)))
    b = b.point(lambda v: max(0, int(v * 0.88)))
    art_img = Image.merge("RGB", (r, g, b))
    art_img = art_img.filter(ImageFilter.GaussianBlur(radius=3))

    base.paste(art_img)
    return base


def prepare_background(art_img: Image.Image | None, palette: dict) -> Image.Image:
    """Art layer plus centre-weighted dark gradient overlay for text legibility."""
    base = prepare_art(art_img, palette)
    if art_img is None:
        return base

    overlay = Image.new("RGB", (W, H), palette["bg"])
    mask    = Image.new("L", (W, H), 0)
    d       = ImageDraw.Draw(mask)

    center       = H // 2
    band_half    = int(H * 0.30)
    edge_alpha   = 40
    centre_alpha = 140

    for y in range(H):
        dist = abs(y - center)
        if dist <= band_half:
            t     = 1.0 - dist / band_half
            alpha = int(edge_alpha + (centre_alpha - edge_alpha) * t)
        else:
            alpha = edge_alpha
        d.line([(0, y), (W, y)], fill=alpha)

    base.paste(overlay, mask=mask)
    return base


def prepare_art_oversized(art_img: Image.Image | None, palette: dict,
                          zoom: float = KB_ZOOM) -> Image.Image | None:
    """Return a colour-graded, blurred art image at zoom × (W, H).

    The Ken Burns pan crops a W×H window from this larger image each frame,
    producing slow camera movement instead of a static background.
    """
    if art_img is None:
        return None
    ow, oh = int(W * zoom), int(H * zoom)
    aw, ah = art_img.size
    scale  = max(ow / aw, oh / ah)
    nw, nh = int(aw * scale), int(ah * scale)
    img    = art_img.resize((nw, nh), Image.LANCZOS)
    x      = (nw - ow) // 2
    y      = (nh - oh) // 2
    img    = img.crop((x, y, x + ow, y + oh))
    img    = ImageEnhance.Color(img).enhance(0.90)
    img    = ImageEnhance.Contrast(img).enhance(0.95)
    img    = ImageEnhance.Brightness(img).enhance(0.90)
    r, g, b = img.split()
    r = r.point(lambda v: min(255, int(v * 1.04)))
    b = b.point(lambda v: max(0, int(v * 0.88)))
    img    = Image.merge("RGB", (r, g, b))
    img    = img.filter(ImageFilter.GaussianBlur(radius=3))
    return img


def build_overlay_mask(palette: dict) -> tuple[Image.Image, Image.Image]:
    """Precompute the centre-band dark gradient overlay and its alpha mask.

    Returns (overlay_rgb, mask_L) — reused across all Ken Burns frames so the
    per-frame cost is just a crop + paste.
    """
    overlay = Image.new("RGB", (W, H), palette["bg"])
    mask    = Image.new("L",   (W, H), 0)
    d       = ImageDraw.Draw(mask)

    center       = H // 2
    band_half    = int(H * 0.30)
    edge_alpha   = 40
    centre_alpha = 140

    for y_pos in range(H):
        dist = abs(y_pos - center)
        if dist <= band_half:
            t     = 1.0 - dist / band_half
            alpha = int(edge_alpha + (centre_alpha - edge_alpha) * t)
        else:
            alpha = edge_alpha
        d.line([(0, y_pos), (W, y_pos)], fill=alpha)
    return overlay, mask


# ── Frame rendering ───────────────────────────────────────────────────────────

def wrap_quote(text: str, font: ImageFont.FreeTypeFont, max_width: int,
               draw: ImageDraw.ImageDraw) -> list[str]:
    """Word-wrap quote text to fit within max_width pixels."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class QuoteLayout:
    """Computed once per render — stores geometry, fonts, and a reference to quote/palette."""

    def __init__(self, quote: dict, palette: dict):
        # Dummy draw for measurement only
        dummy = ImageDraw.Draw(Image.new("RGBA", (W, H)))

        self.pad_x      = 96
        self.max_text_w = W - 96 * 2

        # Fonts
        self.quote_font  = load_font("Lora-Italic.ttf", 72)
        self.author_font = load_font("Lora-BoldItalic.ttf", 38)
        self.book_font   = load_font("InstrumentSerif-Italic.ttf", 32)
        self.tag_font          = load_font("InstrumentSans-Italic.ttf", 24)
        self.open_font         = load_font("Lora-Italic.ttf", 140)
        self.credit_artist_font = load_font("InstrumentSans-Bold.ttf", 30)
        self.credit_title_font  = load_font("InstrumentSans-BoldItalic.ttf", 26)
        self.label_font         = load_font("InstrumentSans-BoldItalic.ttf", 24)

        self.quote   = quote
        self.palette = palette

        # Geometry
        self.lines     = wrap_quote(quote["text"], self.quote_font, self.max_text_w, dummy)
        self.line_h    = self.quote_font.size + 18
        total_h        = len(self.lines) * self.line_h
        center_y       = H // 2
        self.text_top  = center_y - total_h // 2
        self.text_bottom = self.text_top + total_h
        self.rule_y    = self.text_bottom + 48


def _render_frame_at(layout: QuoteLayout, bg: Image.Image,
                     handle: str, niche: str, art_artist: str, art_title: str,
                     lines_visible: int, current_line_alpha: int,
                     author_alpha: int, cta_alpha: int = 0,
                     cta_text: str = "") -> Image.Image:
    """Render one animation frame given per-element alpha values."""
    img  = bg.copy().convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    palette  = layout.palette
    pad_x    = layout.pad_x
    center_y = H // 2

    # Static elements — shown as soon as any text has started appearing
    if lines_visible > 0 or current_line_alpha > 0:
        # Opening quotation mark
        draw.text((pad_x - 10, center_y - 340), "\u201c", font=layout.open_font,
                  fill=(*palette["rule"], 60))

        # Bottom tag
        tag_parts = [p for p in [handle, niche] if p]
        tag_text  = "  ·  ".join(tag_parts) if tag_parts else ""
        if tag_text:
            bbox = draw.textbbox((0, 0), tag_text, font=layout.tag_font)
            tw   = bbox[2] - bbox[0]
            draw.text(((W - tw) // 2, H - 96), tag_text,
                      font=layout.tag_font, fill=palette["tag"])

    # Quote lines
    for i, line in enumerate(layout.lines):
        if i < lines_visible:
            alpha = 255
        elif i == lines_visible and current_line_alpha > 0:
            alpha = current_line_alpha
        else:
            break

        bbox          = draw.textbbox((0, 0), line, font=layout.quote_font)
        lw            = bbox[2] - bbox[0]
        x             = (W - lw) // 2
        y             = layout.text_top + i * layout.line_h
        shadow_alpha  = int(120 * alpha / 255)
        draw.text((x + 2, y + 3), line, font=layout.quote_font,
                  fill=(0, 0, 0, shadow_alpha))
        draw.text((x, y), line, font=layout.quote_font,
                  fill=(*palette["quote"], alpha))

    # Author block (rule + author name + book) faded by author_alpha
    if author_alpha > 0:
        rule_y = layout.rule_y

        draw.line([(W // 2 - 60, rule_y), (W // 2 + 60, rule_y)],
                  fill=(*palette["rule"], author_alpha), width=1)

        lbl_bbox     = draw.textbbox((0, 0), "Author", font=layout.label_font)
        lbl_w        = lbl_bbox[2] - lbl_bbox[0]
        draw.text(((W - lbl_w) // 2, rule_y + 10), "Author",
                  font=layout.label_font, fill=(*palette["quote"], author_alpha))

        author_text  = layout.quote["author"] if layout.quote["author"] else "Unknown"
        bbox         = draw.textbbox((0, 0), author_text, font=layout.author_font)
        aw           = bbox[2] - bbox[0]
        ax           = (W - aw) // 2
        shadow_alpha = int(140 * author_alpha / 255)
        draw.text((ax + 2, rule_y + 34), author_text, font=layout.author_font,
                  fill=(0, 0, 0, shadow_alpha))
        draw.text((ax, rule_y + 32), author_text, font=layout.author_font,
                  fill=(*palette["author"], author_alpha))

        if layout.quote["book"]:
            book_text = layout.quote["book"]
            bbox      = draw.textbbox((0, 0), book_text, font=layout.book_font)
            bw        = bbox[2] - bbox[0]
            draw.text(((W - bw) // 2, rule_y + 32 + 46), book_text,
                      font=layout.book_font,
                      fill=(*palette["quote"], author_alpha))

        # Art attribution — centered, below author/book, fades in with author block
        if art_artist or art_title:
            paint_y     = rule_y + (136 if layout.quote["book"] else 96)
            artist_text = art_artist.title() if art_artist else ""
            title_text  = art_title if len(art_title) <= 42 else art_title[:39] + "…"

            pc_bbox = draw.textbbox((0, 0), "Painting credit:", font=layout.label_font)
            pc_w    = pc_bbox[2] - pc_bbox[0]
            draw.text(((W - pc_w) // 2, paint_y), "Painting credit:",
                      font=layout.label_font, fill=(*palette["quote"], author_alpha))
            paint_y += (pc_bbox[3] - pc_bbox[1]) + 8

            if artist_text:
                bbox = draw.textbbox((0, 0), artist_text, font=layout.credit_artist_font)
                aw   = bbox[2] - bbox[0]
                draw.text(((W - aw) // 2 + 1, paint_y + 1), artist_text,
                          font=layout.credit_artist_font,
                          fill=(0, 0, 0, int(130 * author_alpha / 255)))
                draw.text(((W - aw) // 2, paint_y), artist_text,
                          font=layout.credit_artist_font,
                          fill=(*palette["author"], author_alpha))
                paint_y += (bbox[3] - bbox[1]) + 8

            if title_text:
                bbox = draw.textbbox((0, 0), title_text, font=layout.credit_title_font)
                tw   = bbox[2] - bbox[0]
                draw.text(((W - tw) // 2, paint_y), title_text,
                          font=layout.credit_title_font,
                          fill=(*palette["quote"], author_alpha))


    # CTA overlay — "reason to stay" prompt that fades in during the end hold
    if cta_alpha > 0 and cta_text:
        cta_bbox = draw.textbbox((0, 0), cta_text, font=layout.label_font)
        cta_w    = cta_bbox[2] - cta_bbox[0]
        draw.text(((W - cta_w) // 2, H - 148), cta_text,
                  font=layout.label_font, fill=(*palette["author"], cta_alpha))

    return img


def render_frame(quote: dict, bg: Image.Image, palette: dict,
                 handle: str = "", niche: str = "",
                 art_artist: str = "", art_title: str = "") -> Image.Image:
    """Render a fully-composed static frame (used for --preview)."""
    layout = QuoteLayout(quote, palette)
    return _render_frame_at(layout, bg, handle, niche, art_artist, art_title,
                            len(layout.lines), 255, 255)


def plan_segment(quote: dict, palette: dict, vo_dur: float,
                 reveal_per_element: float = 0.5) -> dict:
    """Compute a segment's timing so the voiceover always fits.

    Segment = fade in → line reveals → author reveal → hold → fade out.
    The voiceover starts as the first line begins revealing.
    """
    n_lines  = len(QuoteLayout(quote, palette).lines)
    reveal_s = (n_lines + 1) * reveal_per_element
    hold_s   = max(1.2, vo_dur + 0.6 - reveal_s)
    total_s  = 2 * FADE_S + reveal_s + hold_s
    return {"reveal_s": reveal_s, "hold_s": hold_s, "total_s": total_s}


def generate_multi_frames(segments: list[dict], palette: dict,
                          handle: str, niche: str,
                          fps: int = FPS, cta_text: str = ""):
    """Generator yielding PIL RGBA frames for a multi-quote reel.

    Each segment gets its own artwork with a Ken Burns pan: fade in from the
    bg colour, reveal the quote line by line (voiceover starts here), hold
    while the voiceover finishes, fade back out. The CTA fades in during the
    final segment's hold. Segment dicts need: quote, art_img, art_artist,
    art_title, total_s.
    """
    solid = Image.new("RGBA", (W, H), (*palette["bg"], 255))
    last  = len(segments) - 1

    for si, seg in enumerate(segments):
        quote   = seg["quote"]
        layout  = QuoteLayout(quote, palette)
        n_lines = len(layout.lines)

        kb_img = prepare_art_oversized(seg["art_img"], palette)
        kb_overlay, kb_mask = (build_overlay_mask(palette) if kb_img is not None
                               else (None, None))
        bg_static = prepare_background(seg["art_img"], palette)

        fade_frames   = int(FADE_S * fps)
        reveal_frames = int(0.5 * fps)
        seg_frames    = int(seg["total_s"] * fps)
        hold_frames   = max(int(1.2 * fps),
                            seg_frames - 2 * fade_frames -
                            (n_lines + 1) * reveal_frames)
        total_frames  = (2 * fade_frames + (n_lines + 1) * reveal_frames +
                         hold_frames)

        def get_bg(frame_idx: int) -> Image.Image:
            """Ken Burns crop for this segment's frame index."""
            if kb_img is None:
                return bg_static
            progress = frame_idx / max(total_frames - 1, 1)
            max_ox   = kb_img.width  - W
            oy       = (kb_img.height - H) // 2
            ox       = int(max_ox * (1.0 - progress))   # slow right → left drift
            cropped  = kb_img.crop((ox, oy, ox + W, oy + H)).copy()
            cropped.paste(kb_overlay, mask=kb_mask)
            return cropped

        def rend(frame_idx, lines_visible, line_alpha, author_alpha, cta_a=0):
            return _render_frame_at(layout, get_bg(frame_idx), handle, niche,
                                    seg["art_artist"], seg["art_title"],
                                    lines_visible, line_alpha, author_alpha,
                                    cta_alpha=cta_a, cta_text=cta_text)

        fi = 0

        # 1. Fade in from solid bg colour to art (no text yet)
        for f in range(fade_frames):
            t = (f + 1) / fade_frames
            yield Image.blend(solid, rend(fi, 0, 0, 0), t)
            fi += 1

        # 2. Line reveals — voiceover starts with the first line
        for line_idx in range(n_lines):
            for f in range(reveal_frames):
                alpha = int(255 * (f + 1) / reveal_frames)
                yield rend(fi, line_idx, alpha, 0)
                fi += 1

        # 3. Author reveal
        for f in range(reveal_frames):
            alpha = int(255 * (f + 1) / reveal_frames)
            yield rend(fi, n_lines, 255, alpha)
            fi += 1

        # 4. Hold — voiceover finishes; CTA fades in on the last segment
        cta_start = hold_frames // 2
        for f in range(hold_frames):
            cta_a = 0
            if si == last and cta_text and f >= cta_start:
                cta_a = min(255, int(255 * (f - cta_start + 1) /
                                     max(1, hold_frames - cta_start)))
            yield rend(fi, n_lines, 255, 255, cta_a)
            fi += 1

        # 5. Fade out to solid bg colour
        for f in range(fade_frames):
            t = (f + 1) / fade_frames
            yield Image.blend(rend(fi, n_lines, 255, 255), solid, t)
            fi += 1


# ── Music selection ───────────────────────────────────────────────────────────

def pick_music_track(seed: str) -> Path | None:
    """Pick a track from reel_template/music/, rotating by hash of seed."""
    tracks = sorted(
        list(MUSIC_DIR.glob("*.mp3")) +
        list(MUSIC_DIR.glob("*.m4a")) +
        list(MUSIC_DIR.glob("*.wav"))
    )
    if not tracks:
        return None
    return tracks[abs(hash(seed)) % len(tracks)]


# ── Voiceover ─────────────────────────────────────────────────────────────────

def synth_voiceover(text: str, out_path: Path, voice: str = TTS_VOICE) -> Path | None:
    """Synthesize speech for one quote. Tries edge-tts first (works in CI),
    falls back to macOS `say`. Returns the audio path or None."""
    try:
        import asyncio
        import edge_tts

        async def _run():
            await edge_tts.Communicate(
                text, voice, rate=TTS_RATE, pitch=TTS_PITCH
            ).save(str(out_path))

        asyncio.run(_run())
        if out_path.exists() and out_path.stat().st_size > 0:
            return out_path
    except Exception as e:
        print(f"  edge-tts unavailable ({e}); trying macOS say")

    aiff = out_path.with_suffix(".aiff")
    r = subprocess.run(["say", "-v", "Daniel", "-r", "160", "-o", str(aiff), text],
                       capture_output=True)
    if r.returncode == 0 and aiff.exists():
        return aiff

    print("  Warning: no TTS available — segment will have no voiceover")
    return None


def audio_duration(path: Path) -> float:
    """Return audio duration in seconds via ffprobe."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# ── Video export ──────────────────────────────────────────────────────────────

def export_video(frame_path: Path, out_path: Path, music_track: Path | None):
    """Encode single frame into an 8-second MP4 with ambient music and fade in/out."""
    fade_start = max(0.0, TOTAL_S - 2.0)

    if music_track:
        af = (
            f"[1:a]"
            f"afade=t=in:st=0:d=0.2,"
            f"afade=t=out:st={fade_start:.2f}:d=2.0,"
            f"volume={MUSIC_VOLUME},"
            f"atrim=duration={TOTAL_S:.2f}"
            f"[aout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(frame_path),
            "-stream_loop", "-1", "-i", str(music_track),
            "-vf", vf,
            "-filter_complex", af, "-map", "0:v", "-map", "[aout]",
            "-t", str(TOTAL_S),
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(out_path),
        ]
        print(f"  ♪ Music: {music_track.name}")
    else:
        # Fallback: silent track
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(frame_path),
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-vf", vf,
            "-t", str(TOTAL_S),
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            str(out_path),
        ]
        print("  ♪ No music tracks found — silent track")

    print(f"  Encoding → {out_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("FFmpeg error:\n", result.stderr[-800:])
        sys.exit(1)


def export_animated_video(frames_iter, out_path: Path, music_track: Path | None,
                          fps: int = FPS, total_s: float = TOTAL_S,
                          voiceovers: list[tuple[Path, float]] | None = None):
    """Pipe raw RGB frames to FFmpeg via stdin to produce an animated MP4.

    voiceovers: list of (audio_path, offset_seconds) mixed over the music,
    which is ducked to MUSIC_VOLUME_DUCKED while voiceovers are present.
    """
    voiceovers = voiceovers or []
    fade_start = max(0.0, total_s - 2.0)

    raw_video_args = [
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{W}x{H}",
        "-r", str(fps),
        "-pix_fmt", "rgb24",
        "-i", "pipe:0",
    ]

    cmd = ["ffmpeg", "-y"] + raw_video_args

    # Audio input 1: music (or silence)
    if music_track:
        cmd += ["-stream_loop", "-1", "-i", str(music_track)]
        print(f"  ♪ Music: {music_track.name}")
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        print("  ♪ No music tracks found — silent base track")

    # Audio inputs 2..N: voiceovers
    for vo_path, _ in voiceovers:
        cmd += ["-i", str(vo_path)]

    music_vol = MUSIC_VOLUME_DUCKED if voiceovers else MUSIC_VOLUME
    parts = [
        f"[1:a]"
        f"afade=t=in:st=0:d=0.2,"
        f"afade=t=out:st={fade_start:.2f}:d=2.0,"
        f"volume={music_vol},"
        f"atrim=duration={total_s:.2f}"
        f"[a_base]"
    ]
    mix_ins = "[a_base]"
    for i, (_, offset_s) in enumerate(voiceovers):
        delay_ms = int(offset_s * 1000)
        parts.append(f"[{2 + i}:a]adelay={delay_ms}:all=1[a_v{i}]")
        mix_ins += f"[a_v{i}]"

    if voiceovers:
        parts.append(
            f"{mix_ins}amix=inputs={1 + len(voiceovers)}"
            f":duration=first:normalize=0[aout]"
        )
        af = ";".join(parts)
        print(f"  ♪ Voiceovers: {len(voiceovers)} mixed in (music ducked to {music_vol})")
    else:
        af = parts[0].replace("[a_base]", "[aout]")

    cmd += [
        "-filter_complex", af,
        "-map", "0:v",
        "-map", "[aout]",
        "-t", str(total_s),
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]

    print(f"  Encoding → {out_path.name}")

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    stderr_buf: list[bytes] = []

    def _drain_stderr():
        for line in proc.stderr:
            stderr_buf.append(line)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    try:
        for img in frames_iter:
            proc.stdin.write(img.convert("RGB").tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass

    proc.wait()
    stderr_thread.join()

    if proc.returncode != 0:
        stderr_text = b"".join(stderr_buf).decode("utf-8", errors="replace")
        print("FFmpeg error:\n", stderr_text[-800:])
        sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Reading quote reel generator")
    parser.add_argument("--account", default="lifequoteshere",
                        help="Account slug matching accounts/<slug>.yaml")
    parser.add_argument("--id",      type=int, help="Specific quote id to use (single-quote reel)")
    parser.add_argument("--count",   type=int, default=3,
                        help="Number of quotes per reel (default 3)")
    parser.add_argument("--no-voice", action="store_true",
                        help="Skip TTS voiceover")
    parser.add_argument("--preview", action="store_true",
                        help="Render frame PNG only, skip video encoding")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print chosen quote, do nothing else")
    args = parser.parse_args()

    # ── Load account config ───────────────────────────────────
    import account_config
    try:
        cfg = account_config.load(args.account)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    palette   = _palette(cfg)
    handle    = cfg.get("handle", "")
    niche     = cfg.get("niche", "")
    QUOTES_DB = BUSINESS_DIR / cfg.get("quotes_db", "data/quotes.db")
    ART_DB    = BUSINESS_DIR / cfg.get("art_db",    "data/art.db")

    # ── Open databases ────────────────────────────────────────
    if not QUOTES_DB.exists():
        print(f"Error: quotes database not found at {QUOTES_DB}")
        print("Run: python scraper/goodreads_scraper.py")
        sys.exit(1)

    q_conn   = sqlite3.connect(QUOTES_DB)
    art_conn = sqlite3.connect(ART_DB)

    # ── Pick quotes ───────────────────────────────────────────
    if args.id is not None:
        q = pick_quote(q_conn, args.id)
        quotes = [q] if q else []
    else:
        quotes = pick_quotes(q_conn, args.count)

    if not quotes:
        print("No unused quotes available. Run: python scraper/goodreads_scraper.py")
        sys.exit(1)

    for quote in quotes:
        print(f"\nQuote #{quote['id']} ({len(quote['text'])} chars)")
        print(f"  Text:   {quote['text'][:80]}{'…' if len(quote['text']) > 80 else ''}")
        print(f"  Author: {quote['author']}")
        print(f"  Book:   {quote['book']}")

    if args.dry_run:
        q_conn.close()
        art_conn.close()
        return

    # ── Pick one art background per quote ─────────────────────
    segments  = []
    seen_urls = set()
    for quote in quotes:
        art_img    = None
        art_artist = ""
        art_title  = ""
        for _ in range(8):  # retry to avoid duplicate artworks
            art_result = pick_art_image_url(art_conn)
            if not art_result:
                break
            img_url, cand_artist, cand_title = art_result
            if img_url in seen_urls:
                continue
            seen_urls.add(img_url)
            print(f"\n  Art: {cand_artist} — {cand_title}")
            art_img = download_image(img_url)
            if art_img is not None:
                art_artist, art_title = cand_artist, cand_title
                break
        if art_img is None:
            print("\n  No art image for this quote; using plain dark background")
        segments.append({"quote": quote, "art_img": art_img,
                         "art_artist": art_artist, "art_title": art_title})

    art_conn.close()

    # ── Output folder ─────────────────────────────────────────
    import reel_utils
    first = quotes[0]
    slug = reel_utils.make_slug(f"{first['author']} {first['text'][:30]}")
    folder_name = f"quote-{date.today().isoformat()}_{slug}"
    reel_dir = REELS_DIR / folder_name
    reel_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  Output: {reel_dir}")

    if args.preview:
        for i, seg in enumerate(segments):
            bg    = prepare_background(seg["art_img"], palette)
            frame = render_frame(seg["quote"], bg, palette, handle, niche,
                                 seg["art_artist"], seg["art_title"])
            frame_path = reel_dir / f"frame_{i}.png"
            frame.convert("RGB").save(frame_path, "PNG")
            print(f"  Frame saved: {frame_path.name}")

    # ── Voiceovers ────────────────────────────────────────────
    vo_durations = []
    for i, seg in enumerate(segments):
        seg["vo_path"] = None
        seg["vo_dur"]  = 0.0
        if args.no_voice:
            continue
        quote   = seg["quote"]
        vo_text = quote["text"]
        if quote["author"]:
            vo_text += f" By {quote['author']}."
        vo_path = synth_voiceover(vo_text, reel_dir / f"vo_{i}.mp3")
        if vo_path:
            seg["vo_path"] = vo_path
            seg["vo_dur"]  = audio_duration(vo_path)
            print(f"  ♪ Voiceover {i}: {vo_path.name} ({seg['vo_dur']:.1f}s)")
        vo_durations.append(seg["vo_dur"])

    # ── Segment timing ────────────────────────────────────────
    voiceovers = []   # (path, absolute offset in seconds)
    t_cursor   = 0.0
    for seg in segments:
        plan = plan_segment(seg["quote"], palette, seg["vo_dur"])
        seg["total_s"] = plan["total_s"]
        if seg["vo_path"]:
            voiceovers.append((seg["vo_path"], t_cursor + FADE_S))
        t_cursor += plan["total_s"]
    total_s = t_cursor
    print(f"\n  Total duration: {total_s:.1f}s ({len(segments)} segments)")

    # Sidecar metadata for the Buffer poster — first quote at the top level
    # for backward compatibility, all quotes under "quotes"
    meta_path = reel_dir / "quote_meta.json"
    meta_path.write_text(json.dumps({
        "id":         first["id"],
        "text":       first["text"],
        "author":     first["author"],
        "book":       first["book"],
        "art_artist": segments[0]["art_artist"],
        "art_title":  segments[0]["art_title"],
        "quotes": [
            {"id": s["quote"]["id"], "text": s["quote"]["text"],
             "author": s["quote"]["author"], "book": s["quote"]["book"],
             "art_artist": s["art_artist"], "art_title": s["art_title"]}
            for s in segments
        ],
    }, ensure_ascii=False, indent=2))

    if args.preview:
        print("\n  Preview mode — skipping video encoding")
        q_conn.close()
        return

    # ── Export animated video ─────────────────────────────────
    cta_text    = cfg.get("cta", "Follow for daily wisdom")
    music_track = pick_music_track(folder_name)
    out_path    = reel_dir / f"{folder_name}.mp4"
    frames      = generate_multi_frames(segments, palette, handle, niche,
                                        cta_text=cta_text)
    export_animated_video(frames, out_path, music_track,
                          total_s=total_s, voiceovers=voiceovers)
    print(f"  Video: {out_path.name}  ({total_s:.1f}s)")

    # ── Mark quotes used ──────────────────────────────────────
    for quote in quotes:
        mark_quote_used(q_conn, quote["id"])
    q_conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
