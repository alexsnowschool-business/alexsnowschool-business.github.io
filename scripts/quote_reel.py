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
MUSIC_VOLUME = 0.25

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
        self.author_font = load_font("InstrumentSerif-Regular.ttf", 38)
        self.book_font   = load_font("InstrumentSerif-Italic.ttf", 32)
        self.tag_font    = load_font("InstrumentSans-Italic.ttf", 24)
        self.open_font   = load_font("Lora-Italic.ttf", 140)
        self.credit_font = load_font("InstrumentSans-Italic.ttf", 20)

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
                     author_alpha: int) -> Image.Image:
    """Render one animation frame given per-element alpha values."""
    img  = bg.copy().convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")

    palette  = layout.palette
    pad_x    = layout.pad_x
    center_y = H // 2

    # Static elements — shown as soon as any text has started appearing
    if lines_visible > 0 or current_line_alpha > 0:
        # Opening quotation mark
        draw.text((pad_x - 10, center_y - 340), "“", font=layout.open_font,
                  fill=(*palette["rule"], 60))

        # Artwork credit (very dim, top left)
        if art_artist and art_title:
            credit = f"{art_artist.title()} · {art_title}"
            if len(credit) > 55:
                credit = credit[:52] + "…"
            draw.text((pad_x, 72), credit, font=layout.credit_font,
                      fill=(*palette["tag"], 140))

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

        author_text  = layout.quote["author"] if layout.quote["author"] else "Unknown"
        bbox         = draw.textbbox((0, 0), author_text, font=layout.author_font)
        aw           = bbox[2] - bbox[0]
        ax           = (W - aw) // 2
        shadow_alpha = int(100 * author_alpha / 255)
        draw.text((ax + 1, rule_y + 19), author_text, font=layout.author_font,
                  fill=(0, 0, 0, shadow_alpha))
        draw.text((ax, rule_y + 18), author_text, font=layout.author_font,
                  fill=(*palette["author"], author_alpha))

        if layout.quote["book"]:
            book_text = layout.quote["book"]
            bbox      = draw.textbbox((0, 0), book_text, font=layout.book_font)
            bw        = bbox[2] - bbox[0]
            draw.text(((W - bw) // 2, rule_y + 18 + 46), book_text,
                      font=layout.book_font,
                      fill=(*palette["book"], author_alpha))

    return img


def render_frame(quote: dict, bg: Image.Image, palette: dict,
                 handle: str = "", niche: str = "",
                 art_artist: str = "", art_title: str = "") -> Image.Image:
    """Render a fully-composed static frame (used for --preview)."""
    layout = QuoteLayout(quote, palette)
    return _render_frame_at(layout, bg, handle, niche, art_artist, art_title,
                            len(layout.lines), 255, 255)


def generate_frames(quote: dict, bg: Image.Image, bg_plain: Image.Image, palette: dict,
                    handle: str, niche: str, art_artist: str, art_title: str,
                    fps: int = FPS, total_s: float = TOTAL_S,
                    fade_s: float = 0.5):
    """Generator that yields PIL RGBA Images, one per animation frame."""
    layout  = QuoteLayout(quote, palette)
    n_lines = len(layout.lines)

    bg_hold_s          = 1.2
    overlay_fade_s     = 0.5
    reveal_per_element = 0.5
    reveal_s           = (n_lines + 1) * reveal_per_element
    hold_s             = max(2.0, total_s - bg_hold_s - overlay_fade_s - reveal_s)

    reveal_frames       = int(reveal_per_element * fps)
    bg_hold_frames      = int(bg_hold_s * fps)
    overlay_fade_frames = int(overlay_fade_s * fps)
    hold_frames         = int(hold_s * fps)

    def frame(bg_layer, lines_visible, current_line_alpha, author_alpha):
        return _render_frame_at(layout, bg_layer, handle, niche, art_artist, art_title,
                                lines_visible, current_line_alpha, author_alpha)

    # 1. Cover hold — plain painting, no overlay, no text
    cover_frame = frame(bg_plain, 0, 0, 0)
    for _ in range(bg_hold_frames):
        yield cover_frame

    # 2. Overlay fade — painting darkens, still no text
    for f in range(overlay_fade_frames):
        t = (f + 1) / overlay_fade_frames
        blended = Image.blend(bg_plain, bg, t)
        yield frame(blended, 0, 0, 0)

    # 3. Line reveals — full overlay bg, text fades in line by line
    for line_idx in range(n_lines):
        for f in range(reveal_frames):
            alpha = int(255 * (f + 1) / reveal_frames)
            yield frame(bg, line_idx, alpha, 0)

    # 4. Author reveal
    for f in range(reveal_frames):
        alpha = int(255 * (f + 1) / reveal_frames)
        yield frame(bg, n_lines, 255, alpha)

    # 5. Hold on final frame
    final_frame = frame(bg, n_lines, 255, 255)
    for _ in range(hold_frames):
        yield final_frame


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
    fade_start = max(0.0, TOTAL_S - 2.0)

    if music_track:
        af = (
            f"[1:a]"
            f"afade=t=in:st=0:d=0.5,"
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
                          fps: int = FPS, total_s: float = TOTAL_S):
    """Pipe raw RGB frames to FFmpeg via stdin to produce an animated MP4."""
    fade_start = max(0.0, total_s - 2.0)

    raw_video_args = [
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{W}x{H}",
        "-r", str(fps),
        "-pix_fmt", "rgb24",
        "-i", "pipe:0",
    ]

    if music_track:
        af = (
            f"[1:a]"
            f"afade=t=in:st=0:d=0.5,"
            f"afade=t=out:st={fade_start:.2f}:d=2.0,"
            f"volume={MUSIC_VOLUME},"
            f"atrim=duration={total_s:.2f}"
            f"[aout]"
        )
        cmd = (
            ["ffmpeg", "-y"]
            + raw_video_args
            + [
                "-stream_loop", "-1", "-i", str(music_track),
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
        )
        print(f"  ♪ Music: {music_track.name}")
    else:
        cmd = (
            ["ffmpeg", "-y"]
            + raw_video_args
            + [
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", str(total_s),
                "-c:v", "libx264", "-preset", "slow", "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                str(out_path),
            ]
        )
        print("  ♪ No music tracks found — silent track")

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
        print("Run: python scraper/goodreads_scraper.py")
        sys.exit(1)

    q_conn   = sqlite3.connect(QUOTES_DB)
    art_conn = sqlite3.connect(ART_DB)

    # ── Pick quote ────────────────────────────────────────────
    quote = pick_quote(q_conn, args.id)
    if not quote:
        print("No unused quotes available. Run: python scraper/goodreads_scraper.py")
        sys.exit(1)

    print(f"\nQuote #{quote['id']} ({len(quote['text'])} chars)")
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

    bg_plain = prepare_art(art_img, palette)
    bg       = prepare_background(art_img, palette)

    if args.preview:
        frame      = render_frame(quote, bg, palette, handle, niche, art_artist, art_title)
        frame_path = reel_dir / "frame.png"
        frame.convert("RGB").save(frame_path, "PNG")
        print(f"  Frame saved: {frame_path.name}")

        meta_path = reel_dir / "quote_meta.json"
        meta_path.write_text(json.dumps({
            "id":         quote["id"],
            "text":       quote["text"],
            "author":     quote["author"],
            "book":       quote["book"],
            "art_artist": art_artist,
            "art_title":  art_title,
        }, ensure_ascii=False, indent=2))

        print("\n  Preview mode — skipping video encoding")
        q_conn.close()
        return

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

    # ── Export animated video ─────────────────────────────────
    music_track = pick_music_track(folder_name)
    out_path    = reel_dir / f"{folder_name}.mp4"
    frames      = generate_frames(quote, bg, bg_plain, palette, handle, niche,
                                  art_artist, art_title)
    export_animated_video(frames, out_path, music_track)
    print(f"  Video: {out_path.name}  ({TOTAL_S:.0f}s)")

    # ── Mark quote used ───────────────────────────────────────
    mark_quote_used(q_conn, quote["id"])
    q_conn.close()

    print("\nDone.")


if __name__ == "__main__":
    main()
