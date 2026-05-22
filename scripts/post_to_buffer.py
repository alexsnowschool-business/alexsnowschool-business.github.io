#!/usr/bin/env python3
"""
Post a generated reel to Instagram and TikTok via Buffer API.

Usage:
    python scripts/post_to_buffer.py reels/<slug>
    python scripts/post_to_buffer.py reels/<slug> --schedule "2026-05-24T19:00:00+07:00"
    python scripts/post_to_buffer.py reels/<slug> --dry-run

Requires env vars (or a .env file in the project root):
    BUFFER_TOKEN             — Buffer API access token
    BUFFER_INSTAGRAM_ID      — Buffer profile ID for Instagram
    BUFFER_TIKTOK_ID         — Buffer profile ID for TikTok (optional)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
BUSINESS_DIR = SCRIPT_DIR.parent

load_dotenv(BUSINESS_DIR / ".env")

BUFFER_API   = "https://api.bufferapp.com/1"
TOKEN        = os.getenv("BUFFER_TOKEN")
IG_PROFILE   = os.getenv("BUFFER_INSTAGRAM_ID")
TT_PROFILE   = os.getenv("BUFFER_TIKTOK_ID")


# ── Caption parser ─────────────────────────────────────────────────────────────

def _parse_captions(captions_md: str) -> dict[str, str]:
    """Extract Instagram and TikTok caption blocks from captions.md."""
    ig = re.search(r"── INSTAGRAM ──.*?\n(.*?)(?=──|\Z)", captions_md, re.DOTALL)
    tt = re.search(r"── TIKTOK ──.*?\n(.*?)(?=──|\Z)", captions_md, re.DOTALL)
    return {
        "instagram": ig.group(1).strip() if ig else "",
        "tiktok":    tt.group(1).strip() if tt else "",
    }


# ── Buffer API helpers ─────────────────────────────────────────────────────────

def _upload_media(client: httpx.Client, video_path: Path, dry_run: bool) -> str | None:
    """Upload video to Buffer and return the media_id."""
    if dry_run:
        print(f"  [dry-run] would upload: {video_path.name} ({video_path.stat().st_size / 1024 / 1024:.1f} MB)")
        return "DRY_RUN_MEDIA_ID"

    print(f"  Uploading {video_path.name} ({video_path.stat().st_size / 1024 / 1024:.1f} MB)...")
    with open(video_path, "rb") as f:
        r = client.post(
            f"{BUFFER_API}/media/upload",
            files={"file": (video_path.name, f, "video/mp4")},
        )
    if r.status_code != 200:
        print(f"  ✗ Media upload failed: {r.status_code} — {r.text[:300]}")
        return None
    media_id = r.json().get("media_id")
    print(f"  ✓ Uploaded — media_id: {media_id}")
    return media_id


def _create_update(
    client: httpx.Client,
    profile_id: str,
    platform: str,
    text: str,
    media_id: str,
    scheduled_at: str | None,
    dry_run: bool,
) -> bool:
    """Schedule a single Buffer update. Returns True on success."""
    if dry_run:
        ts = scheduled_at or "now (added to queue)"
        print(f"  [dry-run] {platform}: would post to profile {profile_id} at {ts}")
        print(f"  Caption preview: {text[:120]}...")
        return True

    payload: dict = {
        "profile_ids[]": profile_id,
        "text":          text,
        "media[id]":     media_id,
    }
    if scheduled_at:
        # Convert ISO string to Unix timestamp
        dt = datetime.fromisoformat(scheduled_at)
        payload["scheduled_at"] = str(int(dt.astimezone(timezone.utc).timestamp()))
    else:
        payload["now"] = "false"   # add to queue

    r = client.post(f"{BUFFER_API}/updates/create", data=payload)
    if r.status_code == 200:
        update_id = r.json().get("updates", [{}])[0].get("id", "?")
        print(f"  ✓ {platform} scheduled — update id: {update_id}")
        return True
    else:
        print(f"  ✗ {platform} failed: {r.status_code} — {r.text[:300]}")
        return False


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Post a reel to Buffer")
    parser.add_argument("reel_dir",   help="Path to reel folder (e.g. reels/weekly-2026-05-22)")
    parser.add_argument("--schedule", default=None,
                        help="ISO 8601 datetime to schedule (e.g. 2026-05-24T19:00:00+07:00). "
                             "Omit to add to Buffer queue.")
    parser.add_argument("--instagram", action="store_true", default=True,  help="Post to Instagram (default)")
    parser.add_argument("--tiktok",    action="store_true", default=True,  help="Post to TikTok (default)")
    parser.add_argument("--no-instagram", dest="instagram", action="store_false")
    parser.add_argument("--no-tiktok",    dest="tiktok",    action="store_false")
    parser.add_argument("--dry-run",  action="store_true", help="Validate without posting")
    args = parser.parse_args()

    reel_dir = BUSINESS_DIR / args.reel_dir
    if not reel_dir.exists():
        print(f"✗ Reel folder not found: {reel_dir}")
        sys.exit(1)

    video_path   = reel_dir / "output" / "reel.mp4"
    captions_path = reel_dir / "output" / "captions.md"

    if not video_path.exists():
        print(f"✗ No reel.mp4 found in {reel_dir / 'output'} — run auto_reel.py first")
        sys.exit(1)
    if not captions_path.exists():
        print(f"✗ No captions.md found — run make_captions.py first")
        sys.exit(1)

    if not args.dry_run and not TOKEN:
        print("✗ BUFFER_TOKEN not set — add it to .env or export it")
        sys.exit(1)

    captions = _parse_captions(captions_path.read_text())

    print("═" * 60)
    print("  BUFFER POSTER — The Hammer Price")
    print(f"  Reel:  {reel_dir.name}")
    print(f"  Mode:  {'DRY RUN' if args.dry_run else 'LIVE'}")
    if args.schedule:
        print(f"  Sched: {args.schedule}")
    print("═" * 60)

    headers = {"Authorization": f"Bearer {TOKEN}"} if not args.dry_run else {}
    with httpx.Client(headers=headers, timeout=60) as client:

        # Upload video once, reuse media_id for both platforms
        print("\n▸ Uploading video...")
        media_id = _upload_media(client, video_path, args.dry_run)
        if not media_id:
            sys.exit(1)

        print("\n▸ Scheduling posts...")
        results = []

        if args.instagram and (IG_PROFILE or args.dry_run):
            ok = _create_update(
                client, IG_PROFILE or "IG_PROFILE_ID",
                "Instagram", captions["instagram"],
                media_id, args.schedule, args.dry_run,
            )
            results.append(("Instagram", ok))
        elif args.instagram:
            print("  ⚠ BUFFER_INSTAGRAM_ID not set — skipping Instagram")

        if args.tiktok and (TT_PROFILE or args.dry_run):
            ok = _create_update(
                client, TT_PROFILE or "TT_PROFILE_ID",
                "TikTok", captions["tiktok"],
                media_id, args.schedule, args.dry_run,
            )
            results.append(("TikTok", ok))
        elif args.tiktok and not TT_PROFILE:
            print("  ⚠ BUFFER_TIKTOK_ID not set — skipping TikTok")

    print("\n" + "═" * 60)
    for platform, ok in results:
        status = "✓" if ok else "✗"
        print(f"  {status} {platform}")
    print("═" * 60)


if __name__ == "__main__":
    main()
