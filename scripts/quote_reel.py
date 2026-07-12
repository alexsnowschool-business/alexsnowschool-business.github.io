#!/usr/bin/env python3
"""
Reading Quote Reel — Hermès aesthetic.

Picks an unused quote from the account's quotes.db, downloads a random art
piece image from art.db as a blurred background, renders a single 1080×1920
frame, and produces a 15-second MP4 with low-volume ambient music.

Usage:
    python scripts/quote_reel.py                          # auto-pick next unused quote
    python scripts/quote_reel.py --account stoicism       # use a different account
    python scripts/quote_reel.py --id 42                  # use specific quote id
    python scripts/quote_reel.py --preview                # render frame PNG only, no video
    python scripts/quote_reel.py --dry-run                # print chosen quote, do nothing
"""

import argparse
import io
import json
import os
import random
import sqlite3
import subprocess
import sys
import textwrap
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

W, H    = 1080, 1920
FPS     = 24
HOLD_S  = 14.5
FADE_S  = 0.5
TOTAL_S = HOLD_S + FADE_S  # 15.0

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
        row = conn.execute(
            "SELECT id, text, author, book FROM quotes "
            "WHERE used_at IS NULL ORDER BY RANDOM() LIMIT 1"
        ).fetchone()
    if not row:
        return None
    return {"id": row[0], "text": row[1], "author": row[2], "book": row[3]}


def mark_quote_used(conn: sqlite3.Connection, quote_id: int):
    conn.execute(
        "UPDATE quotes SET used_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), quote_id),
    )
    conn.commit()


def pick_art_image_url(art_conn: sqlite3.Connection) -> tuple[str, str, str] | None:
    """Return (image_url, artist, title) for a random art item with images."""
    rows = art_conn.execute(
        "SELECT artist, title, image_urls FROM art_items "
        "WHERE image_urls IS NOT NULL AND image_urls NOT IN ('', '[]') "
        "ORDER BY RANDOM() LIMIT 20"
    ).fetchall()
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


def prepare_background(art_img: Image.Image | None, palette: dict) -> Image.Image:
    """Warm background with art visible at edges, darkened in centre for legibility."""
    base = Image.new("RGB", (W, H), palette["bg"])
    if art_img is None:
        return base

    # Cover-crop to canvas
    aw, ah = art_img.size
    scale = max(W / aw, H / ah)
    nw, nh = int(aw * scale), int(ah * scale)
    art_img = art_img.resize((nw, nh), Image.LANCZOS)
    x = (nw - W) // 2
    y = (nh - H) // 2
    art_img = art_img.crop((x, y, x + W, y + H))

    # Light warm colour grade — keep the painting visible
    art_img = ImageEnhance.Color(art_img).enhance(0.80)
    art_img = ImageEnhance.Contrast(art_img).enhance(0.95)
    art_img = ImageEnhance.Brightness(art_img).enhance(0.75)
    r, g, b = art_img.split()
    r = r.point(lambda v: min(255, int(v * 1.04)))
    b = b.point(lambda v: max(0, int(v * 0.88)))
    art_img = Image.merge("RGB", (r, g, b))

    # Soft blur — still recognisable as a painting
    art_img = art_img.filter(ImageFilter.GaussianBlur(radius=6))

    base.paste(art_img)

    # Centre-weighted gradient overlay: light at top/bottom, dark in the middle
    # so the quote zone is legible while the art shows at the edges
    overlay = Image.new("RGB", (W, H), palette["bg"])
    mask    = Image.new("L", (W, H), 0)
    d       = ImageDraw.Draw(mask)

    center      = H // 2
    band_half   = int(H * 0.30)   # half-height of the dark centre band
    edge_alpha  = 80              # how dark at top/bottom edges
    centre_alpha = 185            # how dark at the quote centre

    for y in range(H):
        dist = abs(y - center)
        if dist <= band_half:
            # Inside centre band — linearly interpolate to max darkness
            t     = 1.0 - dist / band_half
            alpha = int(edge_alpha + (centre_alpha - edge_alpha) * t)
        else:
            alpha = edge_alpha
        d.line([(0, y), (W, y)], fill=alpha)

    base.paste(overlay, mask=mask)
    return base


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


def render_frame(quote: dict, bg: Image.Image, palette: dict,
                 handle: str = "", niche: str = "",
                 art_artist: str = "", art_title: str = "") -> Image.Image:
    img  = bg.copy().convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    # Fonts
    quote_font  = load_font("Lora-Italic.ttf", 72)
    author_font = load_font("InstrumentSerif-Regular.ttf", 38)
    book_font   = load_font("InstrumentSerif-Italic.ttf", 32)
    tag_font    = load_font("InstrumentSans-Italic.ttf", 24)

    pad_x      = 96   # horizontal margin
    max_text_w = W - pad_x * 2
    center_y   = H // 2

    # ── Opening quotation mark ────────────────────────────────
    open_font = load_font("Lora-Italic.ttf", 140)
    draw.text((pad_x - 10, center_y - 340), "“", font=open_font,
              fill=(*palette["rule"], 60))

    # ── Quote text ────────────────────────────────────────────
    lines      = wrap_quote(quote["text"], quote_font, max_text_w, draw)
    line_h     = quote_font.size + 18
    total_h    = len(lines) * line_h
    text_top   = center_y - total_h // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=quote_font)
        lw   = bbox[2] - bbox[0]
        x    = (W - lw) // 2
        y    = text_top + i * line_h
        # Shadow
        draw.text((x + 2, y + 3), line, font=quote_font, fill=(0, 0, 0, 120))
        draw.text((x, y), line, font=quote_font, fill=palette["quote"])

    text_bottom = text_top + total_h

    # ── Rule ──────────────────────────────────────────────────
    rule_y = text_bottom + 48
    rule_w = 60
    draw.line([(W // 2 - rule_w, rule_y), (W // 2 + rule_w, rule_y)],
              fill=palette["rule"], width=1)

    # ── Author ────────────────────────────────────────────────
    author_text = quote["author"] if quote["author"] else "Unknown"
    bbox = draw.textbbox((0, 0), author_text, font=author_font)
    aw   = bbox[2] - bbox[0]
    ax   = (W - aw) // 2
    draw.text((ax + 1, rule_y + 19), author_text, font=author_font, fill=(0, 0, 0, 100))
    draw.text((ax, rule_y + 18), author_text, font=author_font, fill=palette["author"])

    # ── Book ──────────────────────────────────────────────────
    if quote["book"]:
        book_text = quote["book"]
        bbox = draw.textbbox((0, 0), book_text, font=book_font)
        bw   = bbox[2] - bbox[0]
        draw.text(((W - bw) // 2, rule_y + 18 + 46), book_text,
                  font=book_font, fill=palette["book"])

    # ── Bottom tag ────────────────────────────────────────────
    tag_parts = [p for p in [handle, niche] if p]
    tag_text  = "  ·  ".join(tag_parts) if tag_parts else ""
    if tag_text:
        bbox = draw.textbbox((0, 0), tag_text, font=tag_font)
        tw   = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, H - 96), tag_text, font=tag_font, fill=palette["tag"])

    # ── Artwork credit (very dim, top left) ───────────────────
    if art_artist and art_title:
        credit = f"{art_artist.title()} · {art_title}"
        if len(credit) > 55:
            credit = credit[:52] + "…"
        credit_font = load_font("InstrumentSans-Italic.ttf", 20)
        draw.text((pad_x, 72), credit, font=credit_font, fill=(*palette["tag"], 140))

    return img


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


# ── Video export ──────────────────────────────────────────────────────────────

def export_video(frame_path: Path, out_path: Path, music_track: Path | None):
    """Encode single frame into an 8-second MP4 with ambient music and fade in/out."""
    vf = f"fade=t=out:st={TOTAL_S - FADE_S:.2f}:d={FADE_S}"
    fade_start = max(0.0, TOTAL_S - 2.0)

    if music_track:
        # Low-volume ambient mix: fade in 0.5s, fade out last 2s
        af = (
            f"[1:a]"
            f"afade=t=in:st=0:d={FADE_S},"
            f"afade=t=out:st={fade_start:.2f}:d=2.0,"
            f"volume=0.15,"
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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Reading quote reel generator")
    parser.add_argument("--account", default="lifequoteshere",
                        help="Account slug matching accounts/<slug>.yaml")
    parser.add_argument("--id",      type=int, help="Specific quote id to use")
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
        print("Run: python scripts/goodreads_scraper.py")
        sys.exit(1)

    q_conn   = sqlite3.connect(QUOTES_DB)
    art_conn = sqlite3.connect(ART_DB)

    # ── Pick quote ────────────────────────────────────────────
    quote = pick_quote(q_conn, args.id)
    if not quote:
        print("No unused quotes available. Run: python scripts/goodreads_scraper.py")
        sys.exit(1)

    print(f"\nQuote #{quote['id']}")
    print(f"  Text:   {quote['text'][:80]}{'…' if len(quote['text']) > 80 else ''}")
    print(f"  Author: {quote['author']}")
    print(f"  Book:   {quote['book']}")

    if args.dry_run:
        q_conn.close()
        art_conn.close()
        return

    # ── Pick art background ───────────────────────────────────
    art_result = pick_art_image_url(art_conn)
    art_img    = None
    art_artist = ""
    art_title  = ""

    if art_result:
        img_url, art_artist, art_title = art_result
        print(f"\n  Art: {art_artist} — {art_title}")
        print(f"  URL: {img_url}")
        art_img = download_image(img_url)
    else:
        print("\n  No art images found; using plain dark background")

    art_conn.close()

    # ── Output folder ─────────────────────────────────────────
    import reel_utils
    slug = reel_utils.make_slug(f"{quote['author']} {quote['text'][:30]}")
    folder_name = f"quote-{date.today().isoformat()}_{slug}"
    reel_dir = REELS_DIR / folder_name
    reel_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  Output: {reel_dir}")

    # ── Render frame ──────────────────────────────────────────
    bg    = prepare_background(art_img, palette)
    frame = render_frame(quote, bg, palette, handle, niche, art_artist, art_title)

    frame_path = reel_dir / "frame.png"
    frame.convert("RGB").save(frame_path, "PNG")
    print(f"  Frame saved: {frame_path.name}")

    # Write sidecar metadata for the Buffer poster
    meta_path = reel_dir / "quote_meta.json"
    meta_path.write_text(json.dumps({
        "id":         quote["id"],
        "text":       quote["text"],
        "author":     quote["author"],
        "book":       quote["book"],
        "art_artist": art_artist,
        "art_title":  art_title,
    }, ensure_ascii=False, indent=2))

    if args.preview:
        print("\n  Preview mode — skipping video encoding")
        q_conn.close()
        return

    # ── Export video ──────────────────────────────────────────
    music_track = pick_music_track(folder_name)
    out_path    = reel_dir / f"{folder_name}.mp4"
    export_video(frame_path, out_path, music_track)
    print(f"  Video: {out_path.name}  ({TOTAL_S:.0f}s)")

    # ── Mark quote used ───────────────────────────────────────
    mark_quote_used(q_conn, quote["id"])
    q_conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
