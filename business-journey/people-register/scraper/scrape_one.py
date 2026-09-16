"""CLI entrypoint for the one-company thread (design draft section 10, steps 1-4).

    docker compose run --rm scraper python scrape_one.py --company "Example GmbH"

Current status (2026-09-16):
- Handelsregister search (find a company, get its register number/court/
  status) is real and verified against the live site.
- Insolvency-notice search reaches the real site
  (neu.insolvenzbekanntmachungen.de) but the search POST 500s — see
  bundesanzeiger.py's module docstring.
- Officer/appointment extraction isn't implemented at all yet — that data
  lives in a generated document per Handelsregister result, not the search
  results HTML (see handelsregister.py's module docstring).

So this can't complete the full pipeline yet. It fetches real Handelsregister
matches for the company and stops there, printing what it found, instead of
pretending the rest works.
"""

import argparse

import handelsregister


def run(company_name: str) -> None:
    _url, html = handelsregister.search_companies(company_name)
    companies = handelsregister.parse_search_results(html)

    if not companies:
        print(f"No Handelsregister matches for {company_name!r}.")
        return

    print(f"Found {len(companies)} Handelsregister match(es) for {company_name!r}:")
    for company in companies:
        print(f"  {company['company_name']} — {company['court']} {company['register_number']} ({company['status']})")

    print(
        "\nStopping here: officer extraction and insolvency-notice parsing "
        "aren't implemented yet (see handelsregister.py / bundesanzeiger.py "
        "docstrings for what's blocking each)."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True, help="Company name to search for")
    args = parser.parse_args()
    run(args.company)
