"""Insolvency notices.

Correction from the original design draft assumption: insolvency notices
are NOT published on bundesanzeiger.de (that site covers company
disclosures/financial statements — a different legal publication channel).
They're published at https://neu.insolvenzbekanntmachungen.de, the
"Insolvenzbekanntmachungen" portal. Verified by hand-tracing the site's
redirect chain (insolvenzbekanntmachungen.de -> neu.insolvenzbekanntmachungen.de)
and reading its real search form (2026-09-16).

Status: fetch_insolvency_notice reaches the real search endpoint with a
verified session/ViewState handshake, but the final search POST still
returns HTTP 500 despite matching every visible form field (including the
disabled/select defaults). This looks like a JS-computed value or header
this session's plain httpx POST doesn't reproduce — the kind of thing that
needs a real browser network trace to diagnose, not more guessing.

TODO: once the Chrome extension is reconnected, drive one real search by
hand, capture the exact request via read_network_requests, diff it against
what this module sends, and fix `search_insolvency_notices` accordingly.
Then write `parse_insolvency_notice` against the real results HTML.
"""

import re

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://neu.insolvenzbekanntmachungen.de"
SEARCH_URL = f"{BASE_URL}/ap/suche.jsf"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; people-register-scraper/0.1)"}


def _view_state(html: str) -> str:
    match = re.search(r'name="jakarta\.faces\.ViewState"[^>]*value="([^"]*)"', html)
    if not match:
        raise RuntimeError("jakarta.faces.ViewState not found on page — site markup may have changed")
    return match.group(1)


def search_insolvency_notices(company_name: str) -> tuple[str, str]:
    """Search for insolvency notices by company/last name. Returns (url, html)."""
    with httpx.Client(timeout=30, follow_redirects=True, headers=HEADERS) as client:
        start = client.get(SEARCH_URL)
        start.raise_for_status()
        view_state = _view_state(start.text)

        results = client.post(
            SEARCH_URL,
            data={
                "frm_suche": "frm_suche",
                "frm_suche:ldi_datumVon:datumHtml5": "",
                "frm_suche:ldi_datumBis:datumHtml5": "",
                "frm_suche:litx_firmaNachName:text": company_name,
                "frm_suche:litx_vorname:text": "",
                "frm_suche:litx_sitzWohnsitz:text": "",
                "frm_suche:iaz_aktenzeichen:itx_abteilung": "",
                "frm_suche:iaz_aktenzeichen:itx_lfdNr": "",
                "frm_suche:iaz_aktenzeichen:itx_jahr": "",
                "frm_suche:iaz_aktenzeichen:ih_aktenzeichen": "true",
                "frm_suche:iaz_aktenzeichen:som_registerzeichen:mysom": "NO_CODE",
                "frm_suche:ir_registereintrag:itx_registernummer": "",
                "frm_suche:ir_registereintrag:ih_registereintrag": "true",
                "frm_suche:ir_registereintrag:som_registergericht:mysom": "NO_CODE",
                "frm_suche:ir_registereintrag:som_registerart:mysom": "NO_CODE",
                "frm_suche:lsom_bundesland:codelist:scl_bundesland:mysom": "NO_CODE",
                "frm_suche:lsom_gegenstand:codelist:mysom": "NO_CODE",
                "frm_suche:lsom_wildcard:lsom": "0",
                "frm_suche:cbt_suchen": "Suchen",
                "jakarta.faces.ViewState": view_state,
            },
        )
        results.raise_for_status()
        return str(results.url), results.text


def parse_insolvency_notice(html: str) -> dict:
    """Parse one insolvency notice out of raw HTML.

    Returns a dict matching the `company_insolvent` event payload:
    {company_name, register_number, court, filed_at, administrator}
    """
    BeautifulSoup(html, "html.parser")  # placeholder to keep the import used
    raise NotImplementedError(
        "parse_insolvency_notice needs real result-row selectors — "
        "search_insolvency_notices() doesn't return a successful results "
        "page yet (see module docstring); fix that first, then write this "
        "against the real markup."
    )
