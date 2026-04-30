"""
One-time setup: get an eBay OAuth2 refresh token for use in GitHub Actions.

Run this locally once:
    python3 scripts/get_ebay_refresh_token.py

Then add the printed EBAY_REFRESH_TOKEN value as a GitHub repository secret.
It stays valid for 18 months. Re-run this script when it expires.

Requirements:
- EBAY_APP_ID and EBAY_CERT_ID in your .env file (or set as env vars)
- Your eBay developer app must have https://localhost listed as an accepted RuName
  (eBay Developer Portal → your app → Auth accepted URLs → add https://localhost)
"""

import base64
import http.server
import json
import os
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path


SCOPE = "https://api.ebay.com/oauth/api_scope"
REDIRECT_URI = "https://localhost"
AUTH_URL = "https://auth.ebay.com/oauth2/authorize"
TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"


def load_credentials() -> tuple[str, str]:
    app_id = os.environ.get("EBAY_APP_ID", "")
    cert_id = os.environ.get("EBAY_CERT_ID", "")
    if not app_id or not cert_id:
        env_file = Path(".env")
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("EBAY_APP_ID="):
                    app_id = line.split("=", 1)[1].strip()
                elif line.startswith("EBAY_CERT_ID="):
                    cert_id = line.split("=", 1)[1].strip()
    if not app_id:
        sys.exit("EBAY_APP_ID not found in env or .env file.")
    if not cert_id:
        sys.exit("EBAY_CERT_ID not found in env or .env file.")
    return app_id, cert_id


def exchange_code(code: str, app_id: str, cert_id: str) -> dict:
    credentials = base64.b64encode(f"{app_id}:{cert_id}".encode()).decode()
    data = urllib.parse.urlencode({
        "grant_type":   "authorization_code",
        "code":         code,
        "redirect_uri": REDIRECT_URI,
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={
            "Authorization":  f"Basic {credentials}",
            "Content-Type":   "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    app_id, cert_id = load_credentials()

    auth_url = (
        f"{AUTH_URL}?client_id={app_id}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        f"&response_type=code"
        f"&scope={urllib.parse.quote(SCOPE, safe='')}"
    )

    print("\n=== eBay Refresh Token Setup ===\n")
    print("BEFORE YOU START: make sure your eBay developer app has")
    print(f"  {REDIRECT_URI}")
    print("listed under Auth accepted URLs (eBay Developer Portal → your app).\n")
    print("Opening your browser to the eBay consent page...")
    webbrowser.open(auth_url)
    print("\nAfter you sign in and approve, your browser will redirect to")
    print("https://localhost and show a connection error — that's expected.")
    print("Copy the FULL URL from your browser's address bar and paste it below.\n")

    redirect_url = input("Paste the redirect URL here: ").strip()

    parsed = urllib.parse.urlparse(redirect_url)
    params = urllib.parse.parse_qs(parsed.query)
    code = params.get("code", [None])[0]
    if not code:
        sys.exit("Could not find 'code' parameter in the URL. Did you copy the full URL?")

    print("\nExchanging code for tokens...")
    try:
        tokens = exchange_code(code, app_id, cert_id)
    except Exception as e:
        sys.exit(f"Token exchange failed: {e}")

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        sys.exit(f"No refresh_token in response: {tokens}")

    print("\n✓ Success!\n")
    print("Add this as a GitHub repository secret named EBAY_REFRESH_TOKEN:")
    print(f"\n  {refresh_token}\n")
    print("Settings → Secrets and variables → Actions → New repository secret")
    print(f"\nThis refresh token expires in {tokens.get('refresh_token_expires_in', '?')} seconds (~18 months).")


if __name__ == "__main__":
    main()
