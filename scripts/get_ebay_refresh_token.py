"""
One-time setup: get an eBay OAuth2 refresh token for use in GitHub Actions.

Run this locally once:
    python3 scripts/get_ebay_refresh_token.py

Then add the printed EBAY_REFRESH_TOKEN value as a GitHub repository secret.
It stays valid for 18 months.

HOW TO FIND YOUR RuName:
  1. Go to developer.ebay.com → Hi [name] → Application Access Keys
  2. Click your Production app keyset
  3. Under "OAuth - Get a token by signing in with eBay" click "View RuName"
     (it looks like: AlexSnow-AlexSnow-PRD-xxxxxxxx-xxxxxx)
  4. Make sure your redirect URL (e.g. https://localhost) is listed under
     "Accepted redirect_uri value(s)" for that RuName
"""

import base64
import json
import os
import sys
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path


SCOPE = "https://api.ebay.com/oauth/api_scope"
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


def exchange_code(code: str, ru_name: str, app_id: str, cert_id: str) -> dict:
    credentials = base64.b64encode(f"{app_id}:{cert_id}".encode()).decode()
    data = urllib.parse.urlencode({
        "grant_type":   "authorization_code",
        "code":         code,
        "redirect_uri": ru_name,
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def main():
    app_id, cert_id = load_credentials()

    print("\n=== eBay Refresh Token Setup ===\n")
    print("Find your RuName at:")
    print("  developer.ebay.com → Application Access Keys → Production app")
    print("  → 'OAuth - Get a token by signing in with eBay' → View RuName\n")
    ru_name = input("Paste your RuName here: ").strip()
    if not ru_name:
        sys.exit("RuName is required.")

    auth_url = (
        "https://auth.ebay.com/oauth2/authorize"
        f"?client_id={app_id}"
        f"&redirect_uri={urllib.parse.quote(ru_name, safe='')}"
        f"&response_type=code"
        f"&scope={urllib.parse.quote(SCOPE, safe='')}"
    )

    print("\nOpening your browser to the eBay consent page...")
    webbrowser.open(auth_url)
    print("\nSign in to eBay and approve the request.")
    print("Your browser will redirect — copy the FULL URL from the address bar")
    print("(it will contain ?code=... or &code=...) and paste it below.\n")

    redirect_url = input("Paste the redirect URL: ").strip()

    parsed = urllib.parse.urlparse(redirect_url)
    params = urllib.parse.parse_qs(parsed.query)
    code = params.get("code", [None])[0]
    if not code:
        # Some redirect URLs use fragment (#) instead of query string
        params = urllib.parse.parse_qs(parsed.fragment)
        code = params.get("code", [None])[0]
    if not code:
        sys.exit("Could not find 'code' in the redirect URL. Did you copy the full URL?")

    print("\nExchanging code for tokens...")
    try:
        tokens = exchange_code(code, ru_name, app_id, cert_id)
    except urllib.error.HTTPError as e:
        sys.exit(f"Token exchange failed ({e.code}): {e.read().decode()}")

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        sys.exit(f"No refresh_token in response: {tokens}")

    expires_days = tokens.get("refresh_token_expires_in", 0) // 86400

    print("\n✓ Success!\n")
    print("Add this as a GitHub repository secret named  EBAY_REFRESH_TOKEN:")
    print(f"\n  {refresh_token}\n")
    print("Settings → Secrets and variables → Actions → New repository secret")
    print(f"\nThis refresh token expires in ~{expires_days} days.")


if __name__ == "__main__":
    main()
