"""Insolvency notices.

Correction from the original design draft assumption: insolvency notices
are NOT published on bundesanzeiger.de (that site covers company
disclosures/financial statements — a different legal publication channel).
They're published at https://neu.insolvenzbekanntmachungen.de, the
"Insolvenzbekanntmachungen" portal. Verified 2026-09-16 by tracing the
site's redirect chain (insolvenzbekanntmachungen.de ->
neu.insolvenzbekanntmachungen.de) and driving its real JSF search form.

The search POST initially returned HTTP 500 despite matching every visible
form field. Root cause: this app rejects non-ajax POSTs that are missing
`Origin`/`Referer` headers matching its own host — plain httpx/curl
requests without a browser-like header set trigger a server-side error
instead of a clean 4xx. Sending both headers (see `_HEADERS` below) fixed
it — verified against real live searches, e.g. "Goertz" returned a real
notice: case 68c IK 523/25, Amtsgericht Hamburg, Goertz Hans-Peter,
04.09.2026.

Not yet implemented: the "Veröffentlichungstext anzeigen" (view full
publication text) popup, which is where the insolvency administrator's name
would come from. It's a JSF ajax partial-render triggered by an
`<input type="image">` — my ajax POST reached the server (200 OK) but the
partial-response came back empty, meaning some required param (likely the
image button's `name.x`/`name.y` click-coordinate pair, or a mismatched
`execute`/`render` target) is still missing. `parse_insolvency_notice`
below only extracts what's in the results-list HTML (case reference, court,
name, date, register) — `administrator` is left `None` until that's cracked.
"""

import re
from datetime import datetime
from urllib.parse import urlencode

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://neu.insolvenzbekanntmachungen.de"
SEARCH_URL = f"{BASE_URL}/ap/suche.jsf"

# The Origin/Referer pair is what fixed the 500 — see module docstring.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)",
    "Origin": BASE_URL,
    "Referer": SEARCH_URL,
}


def _view_state(html: str) -> str:
    match = re.search(r'name="jakarta\.faces\.ViewState"[^>]*value="([^"]*)"', html)
    if not match:
        raise RuntimeError("jakarta.faces.ViewState not found on page — site markup may have changed")
    return match.group(1)


def _default_search_form_data(html: str) -> list[tuple[str, str]]:
    """Read every field of #frm_suche and its current default value.

    JSF forms 500 if fields are missing/mismatched (see module docstring),
    so we replay exactly what a browser would submit rather than
    hand-listing fields and risking a stale guess.
    """
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", id="frm_suche")
    data: list[tuple[str, str]] = []

    for input_ in form.find_all("input"):
        name = input_.get("name")
        if not name or input_.has_attr("disabled"):
            continue
        input_type = input_.get("type", "text")
        if input_type in ("checkbox", "radio"):
            if input_.has_attr("checked"):
                data.append((name, input_.get("value", "on")))
            continue
        data.append((name, input_.get("value", "")))

    for select in form.find_all("select"):
        name = select.get("name")
        if not name or select.has_attr("disabled"):
            continue
        option = select.find("option", selected=True) or select.find("option")
        data.append((name, option.get("value", "") if option else ""))

    for textarea in form.find_all("textarea"):
        name = textarea.get("name")
        if name:
            data.append((name, textarea.text or ""))

    return data


def search_insolvency_notices(company_or_last_name: str) -> tuple[str, str]:
    """Search for insolvency notices by company/last name. Returns (url, html)."""
    with httpx.Client(timeout=30, follow_redirects=True, headers=HEADERS) as client:
        start = client.get(SEARCH_URL)
        start.raise_for_status()

        form_data = _default_search_form_data(start.text)
        form_data = [
            (name, company_or_last_name if name == "frm_suche:litx_firmaNachName:text" else value)
            for name, value in form_data
        ]

        # httpx's `data=` doesn't accept a list of (possibly-repeated) tuples
        # cleanly, and this form can repeat a name (radio groups) — encode
        # by hand instead.
        body = urlencode(form_data)
        results = client.post(
            SEARCH_URL,
            content=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        results.raise_for_status()
        return str(results.url), results.text


def parse_search_results(html: str) -> list[dict]:
    """Parse the results table (#tbl_ergebnis) into notice entries.

    Returns [{case_reference, court, name, sitz, register_number,
    filed_at}, ...]. `register_number` is empty for natural-person
    insolvencies (only company/juristic-person cases populate it).
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="tbl_ergebnis")
    if table is None:
        return []

    notices = []
    for row in table.select("tbody tr"):
        date_span = row.select_one('span[id$=":otx_datum"]')
        case_span = row.select_one('span[id$=":otx_azAkt"]')
        court_span = row.select_one('span[id$=":otx_Gericht"]')
        name_span = row.select_one('span[id$=":otx_schuldner"]')
        sitz_span = row.select_one('span[id$=":otx_Sitz"]')
        register_span = row.select_one('span[id$=":otx_register"]')

        filed_at = None
        if date_span and date_span.get_text(strip=True):
            filed_at = datetime.strptime(date_span.get_text(strip=True), "%d.%m.%Y").date()

        notices.append(
            {
                "filed_at": filed_at,
                "case_reference": case_span.get_text(strip=True) if case_span else None,
                "court": court_span.get_text(strip=True) if court_span else None,
                "name": name_span.get_text(strip=True) if name_span else None,
                "sitz": sitz_span.get_text(strip=True) if sitz_span else None,
                "register_number": register_span.get_text(strip=True) if register_span else None,
            }
        )

    return notices


def parse_insolvency_notice(entry: dict) -> dict:
    """Map one parsed result-row entry to the `company_insolvent` event payload.

    `administrator` is always None for now — see module docstring on the
    unfinished detail-popup ajax flow.
    """
    return {
        "company_name": entry["name"],
        "register_number": entry["register_number"] or None,
        "court": entry["court"],
        "filed_at": entry["filed_at"],
        "administrator": None,
    }
