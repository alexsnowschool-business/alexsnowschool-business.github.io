"""CLI entrypoint for the one-company thread (design draft section 10, steps 1-4).

    docker compose run --rm scraper python scrape_one.py --company "Example GmbH"

Current status (2026-09-16):
- Insolvency-notice search (neu.insolvenzbekanntmachungen.de, not
  bundesanzeiger.de — see bundesanzeiger.py docstring) is real and
  verified. Only notices with a populated register number (company/juristic
  person cases, not personal Verbraucherinsolvenz) can become a
  `company_insolvent` event, since companies.register_number is NOT NULL.
- Handelsregister search (find a company, get its register number/court/
  status) is real and verified.
- Officer/appointment extraction isn't implemented at all yet — that data
  lives in a generated document per Handelsregister result, not the search
  results HTML (see handelsregister.py's module docstring). Without it,
  `person_appointed` events can't be produced, so the graph view will show
  companies but no linked people yet.
"""

import argparse

import bundesanzeiger
import handelsregister
from database import get_connection
from pipeline import insert_event, rebuild_graph


def run(company_name: str) -> None:
    conn = get_connection()

    _url, notice_html = bundesanzeiger.search_insolvency_notices(company_name)
    notices = bundesanzeiger.parse_search_results(notice_html)
    print(f"Found {len(notices)} insolvency notice(s) for {company_name!r}.")

    inserted = 0
    for notice in notices:
        if not notice["register_number"]:
            print(f"  Skipping {notice['name']} ({notice['case_reference']}): no register number (not a company case).")
            continue
        payload = bundesanzeiger.parse_insolvency_notice(notice)
        insert_event(
            conn,
            type="company_insolvent",
            source="bundesanzeiger",
            source_document_id=_url,
            occurred_at=payload["filed_at"],
            payload=payload,
        )
        inserted += 1
        print(f"  Inserted company_insolvent event for {payload['company_name']}.")

    _url, hr_html = handelsregister.search_companies(company_name)
    companies = handelsregister.parse_search_results(hr_html)
    print(f"Found {len(companies)} Handelsregister match(es) for {company_name!r}.")
    for company in companies[:5]:
        print(f"  {company['company_name']} — {company['court']} {company['register_number']} ({company['status']})")

    if inserted:
        rebuild_graph(conn)
        print(f"\nRebuilt graph view ({inserted} insolvency event(s) applied).")

    print(
        "\nOfficer/appointment extraction isn't implemented yet (see "
        "handelsregister.py docstring), so no person_appointed events were "
        "created — the graph view has companies but no linked people."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True, help="Company or last name to search for")
    args = parser.parse_args()
    run(args.company)
