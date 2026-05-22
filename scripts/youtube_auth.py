#!/usr/bin/env python3
"""
One-time script to obtain a YouTube OAuth2 refresh token.

Run this locally once, copy the printed refresh token into GitHub Secrets
as YOUTUBE_REFRESH_TOKEN.

Requires in .env or environment:
    YOUTUBE_CLIENT_ID
    YOUTUBE_CLIENT_SECRET

Your OAuth2 client must have http://localhost:8080 as an authorized redirect URI.
"""

import os
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
from dotenv import load_dotenv

SCRIPT_DIR   = Path(__file__).resolve().parent
BUSINESS_DIR = SCRIPT_DIR.parent

load_dotenv(BUSINESS_DIR / ".env", override=False)

CLIENT_ID     = os.getenv("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")

AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE     = "https://www.googleapis.com/auth/youtube.upload"
REDIRECT  = "http://localhost:8080"

_auth_code: str | None = None


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        _auth_code = params.get("code", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if _auth_code:
            self.wfile.write(b"<h2>Authorized! You can close this tab.</h2>")
        else:
            self.wfile.write(b"<h2>Error: no code received.</h2>")

    def log_message(self, *args):
        pass  # suppress request logs


def main() -> None:
    if not CLIENT_ID or not CLIENT_SECRET:
        print("✗ Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env first")
        sys.exit(1)

    params = urllib.parse.urlencode({
        "client_id":     CLIENT_ID,
        "redirect_uri":  REDIRECT,
        "response_type": "code",
        "scope":         SCOPE,
        "access_type":   "offline",
        "prompt":        "consent",
    })
    url = f"{AUTH_URL}?{params}"

    print("═" * 60)
    print("  YOUTUBE AUTH — The Hammer Price")
    print("═" * 60)
    print("\nStep 1: Opening Google OAuth consent page...")
    print(f"  If the browser doesn't open, visit:\n  {url}\n")

    try:
        webbrowser.open(url)
    except Exception:
        pass

    print("Step 2: Waiting for redirect on http://localhost:8080 ...")
    server = HTTPServer(("localhost", 8080), _Handler)
    server.handle_request()

    if not _auth_code:
        print("✗ No authorization code received")
        sys.exit(1)

    print("  ✓ Auth code received\n")
    print("Step 3: Exchanging code for tokens...")

    r = httpx.post(TOKEN_URL, data={
        "code":          _auth_code,
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri":  REDIRECT,
        "grant_type":    "authorization_code",
    })

    if r.status_code != 200:
        print(f"✗ Token exchange failed: {r.status_code} — {r.text[:300]}")
        sys.exit(1)

    data          = r.json()
    refresh_token = data.get("refresh_token")
    access_token  = data.get("access_token")

    print("═" * 60)
    print("  ✓ Tokens obtained")
    print(f"  Access token (expires soon): {access_token[:40]}...")
    print()
    print("  REFRESH TOKEN (save this as GitHub secret YOUTUBE_REFRESH_TOKEN):")
    print(f"  {refresh_token}")
    print("═" * 60)


if __name__ == "__main__":
    main()
