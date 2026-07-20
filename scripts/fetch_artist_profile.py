#!/usr/bin/env python3
"""
Fetch an artist profile from Google Arts & Culture.
Caches results to data/artist_cache/<ArtistName>.json.

Usage:
    python scripts/fetch_artist_profile.py "Salvador Dali"
    python scripts/fetch_artist_profile.py          # uses current campaign artist
    python scripts/fetch_artist_profile.py "Dali" --force
"""

import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import httpx
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "artist_cache"
GAC_BASE = "https://artsandculture.google.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _cache_path(artist_name: str) -> Path:
    safe = re.sub(r"[^\w\s-]", "", artist_name).strip().replace(" ", "_")
    return CACHE_DIR / f"{safe}.json"


def _get_entity_url(artist_name: str) -> str | None:
    """Search GAC and return the best matching /entity/ URL."""
    last_name = _strip_accents(artist_name.split()[-1]).lower()

    for query_str in [artist_name, f"{artist_name} artist"]:
        query = _strip_accents(query_str).replace(" ", "+")
        resp = requests.get(f"{GAC_BASE}/search?q={query}", headers=HEADERS, timeout=15)
        resp.raise_for_status()

        matches = re.findall(r'"/entity/([^"]+)"', resp.text)
        # Check full slug_id (e.g. "tracey-emin/m0abc") not just the first segment.
        for slug_id in matches:
            if last_name in _strip_accents(slug_id).lower():
                return f"{GAC_BASE}/entity/{slug_id}"

        time.sleep(0.5)

    # No match found — don't blindly return the first result.
    return None


_WIKI_HEADERS = {"User-Agent": "artist-profile-bot/1.0 (educational research)"}


def _llm_quote(artist_name: str) -> str:
    """Ask the LLM for one well-known, verifiable quote from the given artist."""
    if not _OPENROUTER_KEY:
        return ""

    prompt = (
        f"Give me one short, well-known quote attributed to {artist_name}. "
        "Return ONLY the quote text itself — no attribution, no quotation marks, "
        "no explanation, no extra text. The quote must be 10–40 words."
    )

    try:
        r = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {_OPENROUTER_KEY}",
                "HTTP-Referer": "https://github.com/alexsnowschool-business",
                "X-Title": "artist-profile-bot",
            },
            json={
                "model": _OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 100,
                "temperature": 0.3,
            },
            timeout=30,
        )
        r.raise_for_status()
        quote = r.json()["choices"][0]["message"]["content"].strip()
        quote = re.sub(r'^["“]|["”]$', "", quote).strip()
        return quote
    except Exception as e:
        print(f"  [warn] LLM quote failed: {e}")
        return ""


def _wikipedia_portrait(artist_name: str) -> str:
    """Return a high-res portrait URL from Wikipedia's pageimages API."""
    try:
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": artist_name,
                "prop": "pageimages",
                "pithumbsize": 1200,
                "format": "json",
            },
            headers=_WIKI_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        return page.get("thumbnail", {}).get("source", "")
    except Exception:
        return ""


def _wikipedia_timeline(artist_name: str) -> list[dict]:
    """Fetch Wikipedia extract and use LLM to extract a clean life timeline."""
    # 1. Fetch Wikipedia plain-text extract
    try:
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": artist_name,
                "prop": "extracts",
                "exintro": False,
                "explaintext": True,
                "exsectionformat": "plain",
                "format": "json",
            },
            headers=_WIKI_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        text  = next(iter(pages.values()), {}).get("extract", "")
    except Exception:
        return []

    if not text or not _OPENROUTER_KEY:
        return []

    # Truncate to keep prompt cost low — first 3000 chars covers early life + key career
    excerpt = text[:3000]

    prompt = f"""Extract a chronological life timeline for {artist_name} from the text below.

Return ONLY a JSON array of objects, each with:
  "year": integer (4-digit year)
  "event": string (max 70 chars, plain English, no footnotes, no wikitext)

Rules:
- 6 to 8 entries maximum
- Include: birth, 2-3 key career milestones, death (if applicable)
- Event text must be a complete, readable phrase — not a sentence fragment
- No markdown, no explanation — raw JSON array only

Text:
{excerpt}"""

    try:
        r = httpx.post(
            _OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {_OPENROUTER_KEY}",
                "HTTP-Referer": "https://github.com/alexsnowschool-business",
                "X-Title": "artist-profile-bot",
            },
            json={
                "model": _OPENROUTER_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
                "temperature": 0.2,
            },
            timeout=30,
        )
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  [warn] LLM timeline failed: {e}")
        return []

    # Parse JSON — strip any accidental markdown fences
    raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
    try:
        events = json.loads(raw)
        events = [e for e in events if isinstance(e.get("year"), int) and e.get("event")]
        events.sort(key=lambda e: e["year"])
        return events[:8]
    except (json.JSONDecodeError, TypeError) as e:
        print(f"  [warn] LLM timeline parse error: {e}\n  raw: {raw[:200]}")
        return []


def _parse_entity_page(url: str, artist_name_hint: str = "") -> dict:
    """Parse a GAC entity page for artist profile data."""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    text = resp.text

    profile: dict = {"gac_url": url}

    # --- Name + Bio + Image from JSON-LD ---
    for script in soup.find_all("script"):
        raw = script.string or ""
        if "schema.googleapis.com" in raw and "mainEntity" in raw:
            try:
                data = json.loads(raw)
                entity = data.get("mainEntity", {})
                profile["full_name"] = entity.get("name", "")
                profile["bio"] = entity.get("description", "")
                raw_img = entity.get("image", "")
                # Append Google Content Server size param for a usable resolution
                profile["image_url"] = (raw_img + "=s1200") if raw_img else ""
            except (json.JSONDecodeError, AttributeError):
                pass
            break

    # --- Dates from h2 (e.g. "May 11, 1904 - Jan 23, 1989") ---
    date_tag = soup.find("h2", class_="CazOhd")
    if date_tag:
        date_text = date_tag.get_text(strip=True)
        parts = re.split(r"\s*[-–]\s*", date_text)
        profile["birth_date"] = parts[0].strip() if len(parts) >= 1 else ""
        profile["death_date"] = parts[1].strip() if len(parts) >= 2 else ""
    else:
        # Fallback: regex scan
        m = re.search(r"(\w+ \d{1,2},\s*\d{4})\s*[-–]\s*(\w+ \d{1,2},\s*\d{4})", text)
        if m:
            profile["birth_date"] = m.group(1)
            profile["death_date"] = m.group(2)

    # --- Artworks + image URLs from stella.common.cobject ---
    # Full format: ["stella.common.cobject","Title (year)","desc","tbn_url",...,["wikiart_url"]]
    cobject_blocks = re.findall(
        r'\["stella\.common\.cobject","([^"]+\(\d{4}\))","([^"]*)","([^"]*)"[^\]]*'
        r'\["(http[^"]+)"\]',
        text,
    )
    seen: set[str] = set()
    unique_artworks: list[dict] = []
    for title, _desc, tbn_url, ext_url in cobject_blocks:
        if title not in seen:
            seen.add(title)
            # Decode unicode escapes in URLs (= → =)
            tbn_clean = tbn_url.replace("\\u003d", "=").replace("\\u003e", ">")
            unique_artworks.append({
                "title": title,
                "image_url": tbn_clean,
                "ext_url": ext_url,   # WikiArt or Wikipedia link (higher quality source)
            })
    # Fallback: titles-only cobjects (no ext_url)
    if not unique_artworks:
        for title, tbn_url in re.findall(
            r'\["stella\.common\.cobject","([^"]+\(\d{4}\))","[^"]*","([^"]*)"', text
        ):
            if title not in seen:
                seen.add(title)
                tbn_clean = tbn_url.replace("\\u003d", "=").replace("\\u003e", ">")
                unique_artworks.append({"title": title, "image_url": tbn_clean, "ext_url": ""})
    profile["famous_artworks"] = unique_artworks[:10]

    # --- Nationality from bio text ---
    bio = profile.get("bio", "")
    nat_match = re.search(
        r"\b(Spanish|French|Dutch|Italian|German|British|American|Russian|"
        r"Flemish|Catalan|Norwegian|Austrian|Swiss|Belgian|Danish|Swedish|"
        r"Japanese|Chinese|Mexican|Argentine|Brazilian|Colombian|Ivorian|"
        r"Nigerian|Ghanaian|South African|Australian|Canadian|Polish|Czech)\b",
        bio,
    )
    profile["nationality"] = nat_match.group(1) if nat_match else ""

    # --- Art movement: prefer the artist's primary/defining movement ---
    # Order matters — more specific movements listed first to win over generic ones
    MOVEMENT_PRIORITY = [
        "Surrealism", "Post-Impressionism", "Abstract Expressionism",
        "Neo-Expressionism", "Fauvism", "Dadaism", "Pop Art", "Minimalism",
        "Symbolism", "Cubism", "Expressionism", "Baroque", "Romanticism",
        "Realism", "Impressionism", "Modernism", "Modernist", "Renaissance",
        "Abstract art", "Contemporary art",
    ]
    bio_lower = bio.lower()
    profile["art_movement"] = next(
        (m for m in MOVEMENT_PRIORITY if m.lower() in bio_lower), ""
    )

    # --- Artist portrait from Wikipedia pageimages API ---
    wiki_name = profile.get("full_name") or artist_name_hint
    profile["portrait_url"] = _wikipedia_portrait(wiki_name)

    # --- Timeline from Wikipedia plain-text extract ---
    profile["timeline"] = _wikipedia_timeline(wiki_name)

    # --- Quote from LLM ---
    profile["quote"] = _llm_quote(wiki_name)

    return profile


def fetch_profile(artist_name: str, force: bool = False) -> dict:
    """Return cached profile or fetch fresh from GAC."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = _cache_path(artist_name)

    if cache.exists() and not force:
        print(f"[cache] {cache.name}")
        return json.loads(cache.read_text())

    print(f"[search] {artist_name!r}")
    entity_url = _get_entity_url(artist_name)
    if not entity_url:
        print(f"[warn] No GAC entity found for {artist_name!r} — building Wikipedia stub")
        stub: dict = {
            "artist_name": artist_name,
            "full_name": "",
            "bio": "",
            "portrait_url": _wikipedia_portrait(artist_name),
            "timeline": _wikipedia_timeline(artist_name),
            "quote": _llm_quote(artist_name),
            "famous_artworks": [],
            "nationality": "",
            "art_movement": "",
            "birth_date": "",
            "death_date": "",
        }
        cache.write_text(json.dumps(stub, indent=2, ensure_ascii=False))
        print(f"[saved]  {cache.name}")
        return stub

    print(f"[fetch]  {entity_url}")
    time.sleep(1)
    profile = _parse_entity_page(entity_url, artist_name_hint=artist_name)
    profile["artist_name"] = artist_name

    cache.write_text(json.dumps(profile, indent=2, ensure_ascii=False))
    print(f"[saved]  {cache.name}")
    return profile


if __name__ == "__main__":
    force = "--force" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if args:
        name = " ".join(args)
    else:
        import subprocess
        result = subprocess.run(
            ["python3", "scripts/campaign_artist.py"],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parent.parent,
        )
        name = result.stdout.strip()
        if not name:
            print("No artist name provided and campaign_artist.py returned nothing.")
            sys.exit(1)
        print(f"[campaign] {name}")

    profile = fetch_profile(name, force=force)
    print(json.dumps(profile, indent=2, ensure_ascii=False))
