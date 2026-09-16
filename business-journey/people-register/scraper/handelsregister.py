"""Handelsregister (commercial register) company lookups.

Verified against the live site (2026-09-16) by hand-driving the actual
multi-step JSF/PrimeFaces postback flow:

1. GET /rp_web/welcome.xhtml -> capture JSESSIONID cookie + ViewState.
2. POST to the same URL with naviForm's "normaleSucheLink" submit params to
   navigate to the search form (this is a PrimeFaces nav link, not a plain
   href).
3. POST company keywords to the search form's real action,
   /rp_web/normalesuche/welcome.xhtml (NOT the page URL you're currently
   on — the form's `action` attribute points elsewhere), with `form:btnSuche`
   as a plain non-ajax submit button.

The results list (`ergebnissForm:selectedSuchErgebnisFormTable`) gives
company name, court, register number, and status ("aktuell"/deleted) — this
is what `parse_search_results` below extracts, and it's real, tested code.

Officer names/appointment dates are NOT in this results HTML. They live in
a generated document (the "AD" / Aktueller Ausdruck link per result row),
fetched via a further PrimeFaces `addSubmitParam` + `ergebnissForm` submit
that produces a download (likely a PDF). That flow needs to be captured
from a real browser network trace before it can be replicated here — the
exact action URL for the document endpoint wasn't findable by guessing.
TODO: reconnect the Chrome extension, drive one real "AD" download by hand,
inspect the request in read_network_requests, and fill in
`fetch_current_printout` / a PDF-parsing officer extractor here.
"""

import re

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://www.handelsregister.de"
WELCOME_URL = f"{BASE_URL}/rp_web/welcome.xhtml"
SEARCH_ACTION_URL = f"{BASE_URL}/rp_web/normalesuche/welcome.xhtml"


def _view_state(html: str) -> str:
    match = re.search(r'name="javax\.faces\.ViewState"[^>]*value="([^"]*)"', html)
    if not match:
        raise RuntimeError("javax.faces.ViewState not found on page — site markup may have changed")
    return match.group(1)


def search_companies(keyword: str) -> tuple[str, str]:
    """Run a real Handelsregister keyword search. Returns (source_document_id-ish url, html).

    Stores nothing itself — caller is expected to pass the html through
    fetch.py's raw-storage convention if persisting it (kept separate here
    since this needs a stateful session, unlike the single-GET sources).
    """
    # Without a browser-like User-Agent the server drops the connection
    # outright (verified: default httpx UA gets RemoteProtocolError).
    headers = {"User-Agent": "Mozilla/5.0 (compatible; people-register-scraper/0.1)"}
    with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
        start = client.get(WELCOME_URL)
        start.raise_for_status()
        view_state = _view_state(start.text)

        nav = client.post(
            WELCOME_URL,
            data={
                "naviForm": "naviForm",
                "naviForm:normaleSucheLink": "naviForm:normaleSucheLink",
                "target": "normaleSucheLink",
                "javax.faces.ViewState": view_state,
            },
        )
        nav.raise_for_status()
        view_state = _view_state(nav.text)

        results = client.post(
            SEARCH_ACTION_URL,
            data={
                "form": "form",
                "form:schlagwortOptionen": "1",  # "alle Wörter" match mode
                "form:NiederlassungSitz": "",
                "form:registerNummer": "",
                "form:registerArt_input": "",
                "form:registergericht_input": "",
                "form:ergebnisseProSeite_input": "25",
                "form:schlagwoerter": keyword,
                "form:btnSuche": "Suchen",
                "javax.faces.ViewState": view_state,
            },
        )
        results.raise_for_status()
        return results.url.path, results.text


def parse_search_results(html: str) -> list[dict]:
    """Parse the search-results list into company entries.

    Returns [{company_name, court, register_number, status, sitz}, ...].
    `status` is "aktuell" for open entries or the German text shown for
    closed/deleted ones — this is registration status, not insolvency
    status (insolvency comes from the Bundesanzeiger/insolvency-notice
    source instead, per design draft section 2).
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    for header_cell in soup.select("td.fontTableNameSize"):
        header_text = header_cell.get_text(" ", strip=True)
        match = re.search(r"Amtsgericht ([\w.\- ]+?)\s+(HRA|HRB|GnR|GsR|PR|VR)\s*(\S+)", header_text)
        if not match:
            continue
        court, register_art, register_nummer = match.groups()

        row_table = header_cell.find_parent("table")
        name_span = row_table.select_one("span.marginLeft20")
        sitz_span = row_table.select_one("td.sitzSuchErgebnisse span")
        # Both sitz and status columns use the same "verticalText" span
        # class with no other distinguishing hook — sitz comes first,
        # status second (verified against a live results row).
        vertical_spans = row_table.select("span.verticalText")
        status_span = vertical_spans[1] if len(vertical_spans) > 1 else None

        companies.append(
            {
                "company_name": name_span.get_text(strip=True).strip('"') if name_span else None,
                "court": court.strip(),
                "register_number": f"{register_art} {register_nummer}",
                "sitz": sitz_span.get_text(strip=True) if sitz_span else None,
                "status": status_span.get_text(strip=True) if status_span else None,
            }
        )

    return companies
