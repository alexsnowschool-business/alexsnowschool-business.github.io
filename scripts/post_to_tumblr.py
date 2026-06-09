#!/usr/bin/env python3
"""
Upload a reel MP4 as a Tumblr video post using the pytumblr library.

Usage:
    python scripts/post_to_tumblr.py reels/<slug>
    python scripts/post_to_tumblr.py reels/<slug> --dry-run

Requires in .env or environment:
    TUMBLR_CONSUMER_KEY     — OAuth1 consumer key (from tumblr.com/oauth/apps)
    TUMBLR_CONSUMER_SECRET  — OAuth1 consumer secret
    TUMBLR_OAUTH_TOKEN      — access token (see scripts/tumblr_auth.py)
    TUMBLR_OAUTH_SECRET     — access token secret
    TUMBLR_BLOG_NAME        — your blog name, e.g. "thehammerprice"
"""

import argparse
import os
import re
import sys
from pathlib import Path

import pytumblr
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
BUSINESS_DIR = SCRIPT_DIR.parent

load_dotenv(BUSINESS_DIR / ".env", override=False)

CONSUMER_KEY    = os.getenv("TUMBLR_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("TUMBLR_CONSUMER_SECRET")
OAUTH_TOKEN     = os.getenv("TUMBLR_OAUTH_TOKEN")
OAUTH_SECRET    = os.getenv("TUMBLR_OAUTH_SECRET")
BLOG_NAME       = os.getenv("TUMBLR_BLOG_NAME")


# ── Caption parser ─────────────────────────────────────────────────────────────

def _parse_tumblr_section(captions_md: str) -> tuple[str, str, list[str]]:
    """Extract title, body, and tags from the Tumblr section of captions.md."""
    title_m = re.search(r"##\s+📓 Tumblr.*?###\s+Title\s+```(.*?)```", captions_md, re.DOTALL)
    body_m  = re.search(r"###\s+Caption\s+```(.*?)```.*?###\s+Tags",     captions_md, re.DOTALL)
    tags_m  = re.search(r"###\s+Tags\s+```(.*?)```",                      captions_md, re.DOTALL)

    title = title_m.group(1).strip() if title_m else ""
    body  = body_m.group(1).strip()  if body_m  else ""
    tags  = [t.strip() for t in tags_m.group(1).split(",")] if tags_m else []
    return title, body, tags


def _parse_instagram_caption(captions_md: str) -> str:
    """Fallback: extract the Instagram caption block."""
    pattern = r"##\s+📸 Instagram.*?###\s+Caption\s+```(.*?)```"
    m = re.search(pattern, captions_md, re.DOTALL | re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _extract_hashtags(text: str) -> list[str]:
    return [tag.lstrip("#") for tag in re.findall(r"#\w+", text)]


def _caption_without_hashtags(text: str) -> str:
    lines = [l for l in text.splitlines() if not re.match(r"^#\w+", l.strip())]
    return "\n".join(lines).strip()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Upload a reel as a Tumblr video post")
    parser.add_argument("reel_dir", help="Reel folder path relative to project root")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force",   action="store_true", help="Re-post even if already marked as posted")
    args = parser.parse_args()

    missing = [k for k, v in {
        "TUMBLR_CONSUMER_KEY":    CONSUMER_KEY,
        "TUMBLR_CONSUMER_SECRET": CONSUMER_SECRET,
        "TUMBLR_OAUTH_TOKEN":     OAUTH_TOKEN,
        "TUMBLR_OAUTH_SECRET":    OAUTH_SECRET,
        "TUMBLR_BLOG_NAME":       BLOG_NAME,
    }.items() if not v]
    if missing:
        print(f"⚠ Missing env vars: {', '.join(missing)}")
        sys.exit(1)

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

    marker = reel_dir / "output" / ".tumblr_posted"
    if marker.exists() and not args.dry_run and not args.force:
        print(f"⚠ Tumblr post already recorded for {reel_slug} — pass --force to override")
        sys.exit(0)

    captions_text = captions_path.read_text()
    tb_title, caption_body, tags = _parse_tumblr_section(captions_text)
    if not caption_body:
        # Fallback to Instagram caption if Tumblr section is absent (older captions.md)
        caption_raw  = _parse_instagram_caption(captions_text)
        if not caption_raw:
            print("✗ Could not parse caption from captions.md")
            sys.exit(1)
        caption_body = _caption_without_hashtags(caption_raw)
        tags         = _extract_hashtags(caption_raw)
        tb_title     = ""
        print("  ⚠ No Tumblr section found — falling back to Instagram caption")

    print("═" * 60)
    print("  TUMBLR POSTER — The Hammer Price")
    print(f"  Reel:  {reel_slug}")
    print(f"  Blog:  {BLOG_NAME}.tumblr.com")
    print(f"  Mode:  {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("═" * 60)
    if tb_title:
        print(f"\n  Title:   {tb_title}")
    print(f"\n  Caption:\n{caption_body[:200]}...")
    print(f"  Tags:    {', '.join(tags[:8])}")

    if args.dry_run:
        print("\n  [dry-run] would post video to Tumblr")
        print("═" * 60)
        return

    client = pytumblr.TumblrRestClient(
        CONSUMER_KEY,
        CONSUMER_SECRET,
        OAUTH_TOKEN,
        OAUTH_SECRET,
    )

    # Verify auth and resolve the actual blog URL before posting
    print("\n▸ Verifying credentials...")
    user_info = client.info()
    if "user" not in user_info:
        print(f"  ✗ Auth check failed: {user_info}")
        sys.exit(1)
    blogs = user_info["user"].get("blogs", [])
    print(f"  ✓ Authenticated as: {user_info['user']['name']}")
    for b in blogs:
        print(f"    blog: {b['name']}  url: {b['url']}")

    print(f"\n▸ Posting to {BLOG_NAME}.tumblr.com...")
    create_kwargs = dict(caption=caption_body, data=str(video_path), tags=tags)
    if tb_title:
        create_kwargs["title"] = tb_title
    response = client.create_video(BLOG_NAME, **create_kwargs)

    print(f"  API response: {response}")

    print("\n" + "═" * 60)
    if "id" in response:
        post_id = response["id"]
        # Use the actual blog URL from the info call if available
        blog_url = next((b["url"].rstrip("/") for b in blogs if b["name"] == BLOG_NAME), f"https://{BLOG_NAME}.tumblr.com")
        post_url = f"{blog_url}/post/{post_id}"
        print(f"  ✓ Tumblr post live — {post_url}")
        marker.write_text(f"{post_url}\n")
    else:
        print(f"  ✗ Tumblr post failed: {response}")
        sys.exit(1)
    print("═" * 60)


if __name__ == "__main__":
    main()
