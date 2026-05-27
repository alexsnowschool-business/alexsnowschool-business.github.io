#!/usr/bin/env python3
"""
Upload a reel MP4 as a YouTube Short using YouTube Data API v3 (OAuth2 refresh-token flow).

Usage:
    python scripts/post_to_youtube.py reels/<slug>
    python scripts/post_to_youtube.py reels/<slug> --dry-run

Requires in .env or environment:
    YOUTUBE_CLIENT_ID      — OAuth2 client ID
    YOUTUBE_CLIENT_SECRET  — OAuth2 client secret
    YOUTUBE_REFRESH_TOKEN  — long-lived refresh token (see scripts/youtube_auth.py)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
BUSINESS_DIR = SCRIPT_DIR.parent

load_dotenv(BUSINESS_DIR / ".env", override=False)

CLIENT_ID     = os.getenv("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")

TOKEN_URL  = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"


# ── Caption parser ─────────────────────────────────────────────────────────────

def _parse_tiktok_caption(captions_md: str) -> str:
    pattern = rf"{re.escape('## 🎵 TikTok')}.*?###\s+Caption\s+```(.*?)```"
    m = re.search(pattern, captions_md, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _extract_hashtags(text: str) -> list[str]:
    return [tag.lstrip("#") for tag in re.findall(r"#\w+", text)]


# ── OAuth2 ─────────────────────────────────────────────────────────────────────

def _get_access_token(client: httpx.Client) -> str:
    r = client.post(TOKEN_URL, data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type":    "refresh_token",
    })
    if r.status_code != 200:
        print(f"  ✗ Token exchange failed: {r.status_code} — {r.text[:300]}")
        sys.exit(1)
    token = r.json().get("access_token")
    if not token:
        print(f"  ✗ No access_token in response: {r.text[:300]}")
        sys.exit(1)
    return token


# ── Resumable upload ───────────────────────────────────────────────────────────

def _upload_video(client: httpx.Client, access_token: str, video_path: Path,
                  title: str, description: str, tags: list[str]) -> str | None:
    metadata = {
        "snippet": {
            "title":       title,
            "description": description,
            "tags":        tags,
            "categoryId":  "1",
        },
        "status": {
            "privacyStatus":           "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    file_size = video_path.stat().st_size

    # Step 1: initiate resumable upload session
    init_r = client.post(
        UPLOAD_URL,
        params={"uploadType": "resumable", "part": "snippet,status"},
        headers={
            "Authorization":           f"Bearer {access_token}",
            "Content-Type":            "application/json; charset=UTF-8",
            "X-Upload-Content-Type":   "video/mp4",
            "X-Upload-Content-Length": str(file_size),
        },
        content=json.dumps(metadata).encode(),
    )

    if init_r.status_code not in (200, 201):
        print(f"  ✗ Upload init failed: {init_r.status_code} — {init_r.text[:300]}")
        return None

    session_uri = init_r.headers.get("Location")
    if not session_uri:
        print("  ✗ No Location header in upload init response")
        return None

    # Step 2: upload the file
    print(f"  Uploading {file_size / 1_048_576:.1f} MB...")
    with video_path.open("rb") as f:
        upload_r = client.put(
            session_uri,
            content=f.read(),
            headers={"Content-Type": "video/mp4"},
            timeout=300,
        )

    if upload_r.status_code not in (200, 201):
        print(f"  ✗ Upload failed: {upload_r.status_code} — {upload_r.text[:300]}")
        return None

    video_id = upload_r.json().get("id")
    return video_id


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a reel as a YouTube Short")
    parser.add_argument("reel_dir", help="Reel folder path relative to project root")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force",   action="store_true", help="Re-upload even if already marked as uploaded")
    args = parser.parse_args()

    if not REFRESH_TOKEN:
        print("⚠ YOUTUBE_REFRESH_TOKEN not set — skipping YouTube upload")
        sys.exit(0)
    if not CLIENT_ID or not CLIENT_SECRET:
        print("⚠ YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET not set — skipping YouTube upload")
        sys.exit(0)

    reel_dir      = BUSINESS_DIR / args.reel_dir
    video_path    = reel_dir / "output" / "reel.mp4"
    captions_path = reel_dir / "output" / "captions.md"
    reel_slug     = reel_dir.name

    if not video_path.exists():
        print(f"✗ No reel.mp4 in {reel_dir / 'output'}")
        sys.exit(1)
    if not captions_path.exists():
        print(f"✗ No captions.md in {reel_dir / 'output'}")
        sys.exit(1)

    # Guard against duplicate uploads for the same reel slug
    yt_marker = reel_dir / "output" / ".youtube_uploaded"
    if yt_marker.exists() and not args.dry_run and not args.force:
        print(f"⚠ YouTube upload already recorded for {reel_slug} — pass --force to override")
        sys.exit(0)

    tiktok_caption = _parse_tiktok_caption(captions_path.read_text())
    if not tiktok_caption:
        print("✗ Could not parse TikTok caption from captions.md")
        sys.exit(1)

    first_line  = next((l for l in tiktok_caption.splitlines() if l.strip()), "")
    title       = first_line.strip()[:100]
    description = tiktok_caption + "\n#Shorts"
    tags        = _extract_hashtags(tiktok_caption) + ["Shorts"]

    print("═" * 60)
    print("  YOUTUBE UPLOADER — The Hammer Price")
    print(f"  Reel:  {reel_slug}")
    print(f"  Mode:  {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("═" * 60)
    print(f"\n  Title:  {title}")
    print(f"  Tags:   {', '.join(tags)}")

    if args.dry_run:
        print("\n  [dry-run] would upload to YouTube Shorts")
        print(f"  [dry-run] Description:\n{description[:300]}...")
        print("\n═" * 60)
        return

    print("\n▸ Exchanging refresh token...")
    with httpx.Client(timeout=30) as client:
        access_token = _get_access_token(client)
        print("  ✓ Access token obtained")

        print("\n▸ Uploading to YouTube...")
        video_id = _upload_video(client, access_token, video_path, title, description, tags)

    print("\n" + "═" * 60)
    if video_id:
        print(f"  ✓ YouTube Short live — https://youtube.com/shorts/{video_id}")
        yt_marker.write_text(f"https://youtube.com/shorts/{video_id}\n")
    else:
        print("  ✗ YouTube upload failed")
        sys.exit(1)
    print("═" * 60)


if __name__ == "__main__":
    main()
