#!/usr/bin/env python3
"""
One-time script to obtain Tumblr OAuth1 access tokens.

Run this locally once, then add the printed tokens to .env / GitHub Secrets:
    TUMBLR_CONSUMER_KEY
    TUMBLR_CONSUMER_SECRET
    TUMBLR_OAUTH_TOKEN
    TUMBLR_OAUTH_SECRET

Register your app at https://www.tumblr.com/oauth/apps to get the consumer key/secret.
Set the callback URL to: http://localhost:8080
"""

import os
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session

SCRIPT_DIR   = Path(__file__).resolve().parent
BUSINESS_DIR = SCRIPT_DIR.parent

load_dotenv(BUSINESS_DIR / ".env", override=False)

CONSUMER_KEY    = os.getenv("TUMBLR_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("TUMBLR_CONSUMER_SECRET")

REQUEST_TOKEN_URL = "https://www.tumblr.com/oauth/request_token"
AUTHORIZE_URL     = "https://www.tumblr.com/oauth/authorize"
ACCESS_TOKEN_URL  = "https://www.tumblr.com/oauth/access_token"
CALLBACK_URL      = "http://localhost:8080"

_callback_params: dict = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        _callback_params["oauth_token"]    = params.get("oauth_token", [None])[0]
        _callback_params["oauth_verifier"] = params.get("oauth_verifier", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if _callback_params.get("oauth_verifier"):
            self.wfile.write(b"<h2>Authorized! You can close this tab.</h2>")
        else:
            self.wfile.write(b"<h2>Error: no verifier received.</h2>")

    def log_message(self, *args):
        pass


def main() -> None:
    if not CONSUMER_KEY or not CONSUMER_SECRET:
        print("✗ Set TUMBLR_CONSUMER_KEY and TUMBLR_CONSUMER_SECRET in .env first")
        sys.exit(1)

    print("═" * 60)
    print("  TUMBLR AUTH — The Hammer Price")
    print("═" * 60)

    # Step 1: get request token
    print("\nStep 1: Obtaining request token...")
    oauth = OAuth1Session(CONSUMER_KEY, client_secret=CONSUMER_SECRET, callback_uri=CALLBACK_URL)
    r = oauth.fetch_request_token(REQUEST_TOKEN_URL)
    request_token  = r["oauth_token"]
    request_secret = r["oauth_token_secret"]
    print(f"  ✓ Request token obtained")

    # Step 2: redirect user to Tumblr for authorization
    auth_url = f"{AUTHORIZE_URL}?oauth_token={request_token}"
    print(f"\nStep 2: Opening Tumblr authorization page...")
    print(f"  If the browser doesn't open, visit:\n  {auth_url}\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    print("Step 3: Waiting for callback on http://localhost:8080 ...")
    server = HTTPServer(("localhost", 8080), _Handler)
    server.handle_request()

    verifier = _callback_params.get("oauth_verifier")
    if not verifier:
        print("✗ No OAuth verifier received")
        sys.exit(1)
    print("  ✓ Verifier received\n")

    # Step 4: exchange for access token
    print("Step 4: Exchanging for access tokens...")
    oauth = OAuth1Session(
        CONSUMER_KEY,
        client_secret=CONSUMER_SECRET,
        resource_owner_key=request_token,
        resource_owner_secret=request_secret,
        verifier=verifier,
    )
    tokens = oauth.fetch_access_token(ACCESS_TOKEN_URL)

    oauth_token  = tokens["oauth_token"]
    oauth_secret = tokens["oauth_token_secret"]

    print("═" * 60)
    print("  ✓ Access tokens obtained")
    print()
    print("  Add these to your .env / GitHub Secrets:")
    print(f"  TUMBLR_OAUTH_TOKEN={oauth_token}")
    print(f"  TUMBLR_OAUTH_SECRET={oauth_secret}")
    print("═" * 60)


if __name__ == "__main__":
    main()
