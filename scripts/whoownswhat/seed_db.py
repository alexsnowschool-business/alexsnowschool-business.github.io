"""
seed_db.py — Who Owns What
Loads the static seed data (Germany Phase I) into the SQLite database.
Safe to re-run: uses INSERT OR REPLACE for entities, deletes + re-inserts
all sub-tables for each entity to stay idempotent.

Usage:
    python scripts/whoownswhat/seed_db.py
    python scripts/whoownswhat/seed_db.py --db path/to/custom.db
"""

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "whoownswhat.db"

NOW = datetime.now(timezone.utc).isoformat()

# ── SEED DATA ──────────────────────────────────────────────────────────────
# Mirrors data.js. Keep in sync — export_data_js.py reads from here.

ENTITIES: list[dict] = [

    # ── COMPANIES ──────────────────────────────────────────────────────────

    {
        "id": "volkswagen", "type": "company", "country": "germany",
        "name": "Volkswagen AG", "ticker": "VOW3",
        "exchange": "XETRA / Frankfurt Stock Exchange",
        "sector": "Automotive",
        "headquarters": "Wolfsburg, Lower Saxony, Germany",
        "founded": "1937", "employees": "684,000",
        "revenue": "€293 billion (2023)", "market_cap": "~€55 billion",
        "summary": (
            "Volkswagen AG is Europe's largest automaker and one of the world's largest by vehicle sales. "
            "Its brands include VW, Audi, Porsche, SEAT, Skoda, Lamborghini, Bentley, and MAN. "
            "The German state of Lower Saxony holds a blocking minority stake under the VW Law (Volkswagen-Gesetz)."
        ),
        "shareholders": [
            {"name": "Porsche Automobil Holding SE", "stake": "53.3% (voting)",
             "type": "Family / Strategic (Piech & Porsche families)",
             "source": "Volkswagen AG Annual Report 2023 / Bundesanzeiger",
             "source_url": "https://www.bundesanzeiger.de", "as_of": "2023"},
            {"name": "State of Lower Saxony (Niedersachsen)", "stake": "11.8% (blocking minority)",
             "type": "Government / Public Entity",
             "source": "Volkswagen AG Annual Report 2023",
             "source_url": "https://annualreport2023.volkswagen-group.com", "as_of": "2023"},
            {"name": "Qatar Investment Authority", "stake": "14.6%",
             "type": "Sovereign Wealth Fund",
             "source": "VW Annual Report 2023 / BaFin",
             "source_url": "https://www.bafin.de", "as_of": "2023"},
            {"name": "Vanguard Group", "stake": "~1.5% (ordinary shares)",
             "type": "Institutional",
             "source": "BaFin voting rights notifications",
             "source_url": "https://www.bafin.de", "as_of": "2023"},
            {"name": "Free float", "stake": "~18.8%",
             "type": "Public",
             "source": "Volkswagen AG Investor Relations",
             "source_url": "https://www.volkswagenag.com/en/InvestorRelations.html", "as_of": "2023"},
        ],
        "compensation": {
            "fiscal_year": 2023, "ceo_name": "Oliver Blume",
            "ceo_title": "Chairman of the Board of Management",
            "ceo_total": "€10.3M", "ceo_salary": "€1.3M",
            "ceo_equity": "€6.2M (long-term incentive)",
            "median_worker": "~€62,000", "ceo_worker_ratio": "~166:1",
            "source": "Volkswagen AG Geschäftsbericht 2023 (Vergütungsbericht)",
            "source_url": "https://annualreport2023.volkswagen-group.com",
        },
        "lobbying": [
            {"year": "2024", "amount": "€6.2M", "currency": "EUR",
             "source": "Bundestag Lobbyregister",
             "source_url": "https://lobbyregister.bundestag.de"},
            {"year": "2023", "amount": "€5.8M", "currency": "EUR",
             "source": "Bundestag Lobbyregister",
             "source_url": "https://lobbyregister.bundestag.de"},
            {"year": "2022", "amount": "€4.9M", "currency": "EUR",
             "source": "Bundestag Lobbyregister",
             "source_url": "https://lobbyregister.bundestag.de"},
        ],
        "political_spending": [
            {"cycle": "2023",
             "pac": "N/A — prohibited by Parteiengesetz §25",
             "total": "€0",
             "note": (
                 "German law (Parteiengesetz §25) prohibits direct donations to political parties "
                 "from corporations. VW engages through VDA (Verband der Automobilindustrie)."
             ),
             "source": "Parteiengesetz §25 / Bundestag Lobbyregister",
             "source_url": "https://lobbyregister.bundestag.de"},
        ],
        "fines": [
            {"year": "2015–2021",
             "description": (
                 "Dieselgate: VW admitted to defeat devices in ~11M diesel vehicles. "
                 "Total costs >€30 billion globally."
             ),
             "source": "U.S. DOJ / Staatsanwaltschaft Braunschweig",
             "source_url": "https://www.justice.gov/opa/pr/volkswagen-ag-agrees-plead-guilty-and-pay-43-billion-connection-allegations-conspiracy-and"},
        ],
        "labor": [
            {"description": (
                 "VW has full co-determination (Mitbestimmung): Supervisory Board is 50% "
                 "employee representatives. IG Metall holds several seats."
             ),
             "source": "VW Corporate Governance / IG Metall",
             "source_url": "https://www.igmetall.de"},
            {"description": (
                 "In 2024, VW announced closure of at least three German plants and 35,000+ job cuts. "
                 "IG Metall launched strikes."
             ),
             "source": "Handelsblatt / Reuters (2024)",
             "source_url": "https://www.handelsblatt.com"},
        ],
        "competitors": [
            "BMW AG (BMW, XETRA)", "Mercedes-Benz Group AG (MBG, XETRA)",
            "Stellantis N.V. (STLA)", "Toyota Motor Corp.", "Renault Group",
        ],
        "sources": [
            {"title": "Volkswagen AG Annual Report 2023",
             "url": "https://annualreport2023.volkswagen-group.com"},
            {"title": "Bundestag Lobbyregister — Volkswagen AG",
             "url": "https://lobbyregister.bundestag.de"},
            {"title": "BaFin — VW voting rights notifications",
             "url": "https://www.bafin.de"},
            {"title": "U.S. DOJ — Volkswagen Dieselgate plea",
             "url": "https://www.justice.gov/opa/pr/volkswagen-ag-agrees-plead-guilty-and-pay-43-billion-connection-allegations-conspiracy-and"},
        ],
    },

    {
        "id": "sap", "type": "company", "country": "germany",
        "name": "SAP SE", "ticker": "SAP",
        "exchange": "XETRA / NYSE (ADR)",
        "sector": "Enterprise Software / Technology",
        "headquarters": "Walldorf, Baden-Württemberg, Germany",
        "founded": "1972", "employees": "107,000",
        "revenue": "€31.2 billion (2023)", "market_cap": "~€230 billion",
        "summary": (
            "SAP SE is the world's leading enterprise application software company, with customers in over 180 countries. "
            "Co-founded in 1972 by Hasso Plattner and colleagues as a spin-off from IBM Germany."
        ),
        "shareholders": [
            {"name": "Hasso Plattner (+ HHP Research Foundation)", "stake": "~9.5%",
             "type": "Co-Founder", "source": "SAP SE Annual Report 2023 / Bundesanzeiger",
             "source_url": "https://www.bundesanzeiger.de", "as_of": "2023"},
            {"name": "Vanguard Group", "stake": "~4.8%",
             "type": "Institutional", "source": "BaFin voting rights notifications",
             "source_url": "https://www.bafin.de", "as_of": "2023"},
            {"name": "BlackRock Inc.", "stake": "~4.0%",
             "type": "Institutional", "source": "BaFin voting rights notifications",
             "source_url": "https://www.bafin.de", "as_of": "2023"},
            {"name": "Free float", "stake": "~78%",
             "type": "Public", "source": "SAP SE Investor Relations",
             "source_url": "https://www.sap.com/investors.html", "as_of": "2023"},
        ],
        "compensation": {
            "fiscal_year": 2023, "ceo_name": "Christian Klein",
            "ceo_title": "Chief Executive Officer (Vorstandsvorsitzender)",
            "ceo_total": "€12.8M", "ceo_salary": "€900K",
            "ceo_equity": "€10.2M (performance shares + RSUs)",
            "median_worker": "~€95,000", "ceo_worker_ratio": "~135:1",
            "source": "SAP SE Annual Report 2023 (Remuneration Report)",
            "source_url": "https://www.sap.com/investors/en/reports.html",
        },
        "lobbying": [
            {"year": "2024", "amount": "€3.3M", "currency": "EUR",
             "source": "Bundestag Lobbyregister",
             "source_url": "https://lobbyregister.bundestag.de"},
            {"year": "2023", "amount": "€2.9M", "currency": "EUR",
             "source": "Bundestag Lobbyregister",
             "source_url": "https://lobbyregister.bundestag.de"},
            {"year": "2022", "amount": "€2.4M", "currency": "EUR",
             "source": "Bundestag Lobbyregister",
             "source_url": "https://lobbyregister.bundestag.de"},
        ],
        "political_spending": [
            {"cycle": "2023",
             "pac": "N/A — prohibited by Parteiengesetz §25",
             "total": "€0",
             "note": "SAP lobbies through BITKOM and DIGITALEUROPE. Key topics: AI Act, data regulation.",
             "source": "Parteiengesetz §25 / BITKOM / Bundestag Lobbyregister",
             "source_url": "https://lobbyregister.bundestag.de"},
        ],
        "fines": [
            {"year": "2024",
             "description": (
                 "SAP agreed to pay ~$222M to resolve U.S. DOJ FCPA investigation: bribery of "
                 "government officials in South Africa, Malawi, Tanzania, Ghana, Indonesia, and Panama."
             ),
             "source": "U.S. DOJ / SEC (January 2024)",
             "source_url": "https://www.justice.gov/opa/pr/sap-agrees-pay-over-220-million-resolve-foreign-corrupt-practices-act-charges"},
        ],
        "labor": [
            {"description": (
                 "SAP announced global restructuring affecting ~8,000 employees (7.5% of workforce) "
                 "in January 2024, shifting resources toward AI."
             ),
             "source": "SAP press release / Handelsblatt (2024)",
             "source_url": "https://news.sap.com"},
        ],
        "competitors": [
            "Oracle Corp. (ORCL, NYSE)", "Microsoft Dynamics", "Salesforce (CRM)", "Workday (WDAY)",
        ],
        "sources": [
            {"title": "SAP SE Annual Report 2023", "url": "https://www.sap.com/investors/en/reports.html"},
            {"title": "Bundestag Lobbyregister — SAP SE", "url": "https://lobbyregister.bundestag.de"},
            {"title": "U.S. DOJ — SAP FCPA settlement (2024)",
             "url": "https://www.justice.gov/opa/pr/sap-agrees-pay-over-220-million-resolve-foreign-corrupt-practices-act-charges"},
        ],
    },

    # ── INDIVIDUALS ─────────────────────────────────────────────────────────

    {
        "id": "susanne-klatten", "type": "person", "country": "germany",
        "name": "Susanne Klatten",
        "title": "Billionaire investor; 19.2% stake in BMW AG; majority owner of Altana AG",
        "nationality": "German", "born": "1962",
        "net_worth": "€27 billion (~$29B)", "net_worth_rank": "#2 wealthiest woman in Germany",
        "net_worth_source": "Manager Magazin Reichenliste 2024",
        "net_worth_url": "https://www.manager-magazin.de/finanzen/reichenliste/",
        "summary": (
            "Susanne Klatten is the daughter of Herbert Quandt, who rescued BMW from bankruptcy in 1959. "
            "Together with her brother Stefan Quandt, she controls ~45% of BMW AG. "
            "She also holds a majority stake in specialty chemicals company Altana AG."
        ),
        "assets": [
            {"name": "BMW AG (BMW, XETRA)", "description": "19.2% stake — ~€12B at 2024 market prices.",
             "source": "BMW AG Annual Report 2023 / BaFin", "source_url": "https://www.bafin.de"},
            {"name": "Altana AG (majority stake via SKion GmbH)",
             "description": "Leading specialty chemicals company. EBITDA ~€600M. Privately held.",
             "source": "Bundesanzeiger / Altana AG", "source_url": "https://www.altana.de"},
            {"name": "SKion GmbH",
             "description": "Personal holding company for all industrial and financial investments.",
             "source": "Bundesanzeiger", "source_url": "https://www.bundesanzeiger.de"},
        ],
        "board_memberships": [
            {"org": "BMW AG", "role": "Member of the Supervisory Board (shareholder side)",
             "source": "BMW AG Annual Report 2023"},
            {"org": "Altana AG", "role": "Majority owner and Supervisory Board member",
             "source": "Altana AG"},
        ],
        "foundations": [
            {"name": "Philanthropic activity via SKion GmbH (informal)",
             "description": "Donates to medical research (bone marrow, cancer) and arts organisations. No major named foundation.",
             "source": "Manager Magazin", "source_url": "https://www.manager-magazin.de"},
        ],
        "political_spending": [
            {"cycle": None, "pac": "None", "total": None,
             "note": "No documented political donations. German law prohibits corporate party donations.",
             "source": "Parteiengesetz §25 / no public records",
             "source_url": "https://lobbyregister.bundestag.de"},
        ],
        "timeline": [
            {"year": "1962", "event": "Born in Munich to Herbert and Johanna Quandt."},
            {"year": "1982", "event": "Studies business under a pseudonym to avoid media attention."},
            {"year": "1997", "event": "Joins the BMW Supervisory Board."},
            {"year": "2003", "event": "Takes majority control of Altana AG."},
            {"year": "2008", "event": "Subject of blackmail by fraudster Helg Sgarbi; resulting criminal conviction."},
            {"year": "2016", "event": "Named Germany's wealthiest woman by Manager Magazin."},
            {"year": "2023", "event": "BMW Group reports record profits; BMW stake exceeds €11B."},
        ],
        "sources": [
            {"title": "Manager Magazin Reichenliste 2024",
             "url": "https://www.manager-magazin.de/finanzen/reichenliste/"},
            {"title": "BMW AG Annual Report 2023",
             "url": "https://www.bmwgroup.com/en/investor-relations/financial-reports.html"},
            {"title": "BaFin — BMW voting rights notifications",
             "url": "https://www.bafin.de"},
            {"title": "Forbes — Susanne Klatten",
             "url": "https://www.forbes.com/profile/susanne-klatten/"},
        ],
    },

    {
        "id": "dieter-schwarz", "type": "person", "country": "germany",
        "name": "Dieter Schwarz",
        "title": "Owner, Schwarz Group (Lidl & Kaufland)",
        "nationality": "German", "born": "1939",
        "net_worth": "€47 billion (~$51B)", "net_worth_rank": "#1 wealthiest in Germany",
        "net_worth_source": "Manager Magazin Reichenliste 2024",
        "net_worth_url": "https://www.manager-magazin.de/finanzen/reichenliste/",
        "summary": (
            "Dieter Schwarz owns 100% of the Schwarz Group — parent of Lidl (~12,000 stores, 31 countries) "
            "and Kaufland. Neither company is publicly listed. Schwarz has never given a public interview."
        ),
        "assets": [
            {"name": "Schwarz Group (Lidl + Kaufland)",
             "description": "100% private. Combined revenue: ~€150 billion (2023). Europe's largest retailer by revenue.",
             "source": "Bundesanzeiger / Manager Magazin estimates",
             "source_url": "https://www.bundesanzeiger.de"},
            {"name": "Dieter Schwarz Stiftung",
             "description": "Foundation funding Technische Hochschule Heilbronn and regional education projects. Assets: ~€5B+.",
             "source": "Dieter Schwarz Stiftung", "source_url": "https://www.dieter-schwarz-stiftung.de"},
        ],
        "board_memberships": [
            {"org": "Schwarz Group", "role": "Sole owner (no public board)",
             "source": "Schwarz Gruppe / Bundesanzeiger"},
        ],
        "foundations": [
            {"name": "Dieter Schwarz Stiftung",
             "description": "Funds Technische Hochschule Heilbronn, Bildungscampus Heilbronn (€600M+ campus), and social welfare.",
             "source": "Dieter Schwarz Stiftung",
             "source_url": "https://www.dieter-schwarz-stiftung.de"},
        ],
        "political_spending": [
            {"cycle": None, "pac": "None", "total": None,
             "note": "No documented political donations. German law prohibits corporate party donations. Schwarz is intensely private.",
             "source": "Parteiengesetz §25 / no public records",
             "source_url": "https://lobbyregister.bundestag.de"},
        ],
        "timeline": [
            {"year": "1963", "event": "Joins father Josef Schwarz's wholesale food company in Heilbronn."},
            {"year": "1973", "event": "Opens first Lidl store in Ludwigshafen, modelled on Aldi's discount concept."},
            {"year": "1988", "event": "Lidl expands into France — beginning European rollout."},
            {"year": "2000", "event": "Schwarz Group becomes Germany's largest food retailer."},
            {"year": "2015", "event": "Lidl enters the U.S. market."},
            {"year": "2024", "event": "Schwarz Group revenue surpasses €150B — Europe's largest retailer."},
        ],
        "sources": [
            {"title": "Manager Magazin Reichenliste 2024",
             "url": "https://www.manager-magazin.de/finanzen/reichenliste/"},
            {"title": "Bundesanzeiger — Schwarz Gruppe filings (limited)",
             "url": "https://www.bundesanzeiger.de"},
            {"title": "Dieter Schwarz Stiftung",
             "url": "https://www.dieter-schwarz-stiftung.de"},
        ],
    },

    {
        "id": "hasso-plattner", "type": "person", "country": "germany",
        "name": "Hasso Plattner",
        "title": "Co-founder & Supervisory Board Chairman, SAP SE",
        "nationality": "German", "born": "1944",
        "net_worth": "€14 billion (~$15B)", "net_worth_rank": "Top 10 wealthiest in Germany",
        "net_worth_source": "Manager Magazin Reichenliste 2024",
        "net_worth_url": "https://www.manager-magazin.de/finanzen/reichenliste/",
        "summary": (
            "Hasso Plattner co-founded SAP SE in 1972 with four IBM Germany colleagues. "
            "He chairs the Supervisory Board and holds ~9.5% of SAP shares (via personal holdings and HHP Research Foundation). "
            "He founded and endowed the Hasso Plattner Institute (HPI) at the University of Potsdam."
        ),
        "assets": [
            {"name": "SAP SE (~9.5% stake)", "description": "Worth ~€22B at peak SAP market cap (~€230B, 2024).",
             "source": "SAP SE Annual Report 2023 / BaFin", "source_url": "https://www.bafin.de"},
            {"name": "Hasso Plattner Institute (HPI), Potsdam",
             "description": "Germany's leading IT institute, co-located with University of Potsdam. Plattner donated €100M+ in initial endowment.",
             "source": "HPI official website", "source_url": "https://hpi.de"},
        ],
        "board_memberships": [
            {"org": "SAP SE", "role": "Chairman of the Supervisory Board",
             "source": "SAP SE Annual Report 2023"},
        ],
        "foundations": [
            {"name": "Hasso Plattner Foundation",
             "description": "Funds HPI Potsdam and HPI School of Design Thinking. Total donations exceed €700M.",
             "source": "HPI / Hasso Plattner Foundation",
             "source_url": "https://hpi.de/en/about-hpi/hasso-plattner.html"},
        ],
        "political_spending": [
            {"cycle": None, "pac": "None", "total": None,
             "note": "No documented political donations. Influence operates through SAP, HPI, and BITKOM.",
             "source": "No public records", "source_url": "https://lobbyregister.bundestag.de"},
        ],
        "timeline": [
            {"year": "1968", "event": "Joins IBM Germany in Mannheim."},
            {"year": "1972", "event": "Co-founds SAP with four IBM colleagues in Weinheim."},
            {"year": "1998", "event": "Founds and endows the Hasso Plattner Institute at University of Potsdam."},
            {"year": "2003", "event": "Steps down as SAP co-CEO; becomes Supervisory Board Chairman."},
            {"year": "2010", "event": "SAP launches HANA (in-memory database) — Plattner's core architectural concept."},
            {"year": "2023", "event": "SAP market cap surpasses €200B — Europe's most valuable software company."},
        ],
        "sources": [
            {"title": "Manager Magazin Reichenliste 2024",
             "url": "https://www.manager-magazin.de/finanzen/reichenliste/"},
            {"title": "SAP SE Annual Report 2023",
             "url": "https://www.sap.com/investors/en/reports.html"},
            {"title": "Hasso Plattner Institute — About",
             "url": "https://hpi.de/en/about-hpi/hasso-plattner.html"},
        ],
    },
]


FACT_CARDS: list[dict] = [
    {"country": "germany", "category": "CEO Pay · Germany",
     "headline": "The average DAX 40 CEO earns approximately 50× the median German worker's wage.",
     "detail": (
         "Average total compensation for a DAX 40 CEO was €7.8M in 2022, vs. a median German worker wage "
         "of ~€40,500. Germany's ratio is lower than the U.S. S&P 500 average (272×) due to co-determination "
         "laws and collective bargaining."
     ),
     "source": "DSW / Handelsblatt CEO pay study 2023 / Statista",
     "source_url": "https://www.statista.com/statistics/462682/germany-average-wages/"},
    {"country": "germany", "category": "Lobbying · Germany",
     "headline": "Germany's mandatory Bundestag Lobby Register launched in 2022. Over 6,000 organisations are registered.",
     "detail": (
         "The Lobbyregistergesetz (mandatory lobbying registration law) came into force in January 2022. "
         "Organisations must disclose lobbying budget, number of lobbyists, and covered issues. "
         "BDI and VDA are among the largest registered spenders."
     ),
     "source": "Bundestag Lobbyregister / Lobbycontrol e.V.",
     "source_url": "https://lobbyregister.bundestag.de"},
    {"country": "germany", "category": "Corporate Ownership · Germany",
     "headline": "German law prohibits corporations from donating directly to political parties.",
     "detail": (
         "Parteiengesetz §25 prohibits donations from public companies, state-adjacent entities, "
         "and organisations significantly publicly funded. Individual donations over €10,000 must be "
         "published; over €50,000 must be published immediately."
     ),
     "source": "Parteiengesetz §25 / Bundeszentrale für politische Bildung",
     "source_url": "https://www.gesetze-im-internet.de/partg/__25.html"},
    {"country": "germany", "category": "Quandt Family · BMW",
     "headline": "The Quandt siblings control 45% of BMW AG — worth over €27 billion combined.",
     "detail": (
         "Stefan Quandt (25.8%) and Susanne Klatten (19.2%) control a blocking minority in BMW AG. "
         "Their father Herbert Quandt rescued BMW from bankruptcy in 1959 by acquiring his majority stake."
     ),
     "source": "BMW AG Annual Report 2023 / Manager Magazin",
     "source_url": "https://www.bmwgroup.com/en/investor-relations/financial-reports.html"},
    {"country": "germany", "category": "Dieselgate · Volkswagen",
     "headline": "VW's emissions scandal cost over €30 billion in fines, settlements, and remediation.",
     "detail": (
         "In 2015, Volkswagen admitted to defeat devices in ~11M diesel vehicles. "
         "Total cost >€30B globally: $2.8B U.S. criminal fine, $1.5B civil settlement, €1B German fine."
     ),
     "source": "U.S. DOJ / Staatsanwaltschaft Braunschweig / Reuters",
     "source_url": "https://www.justice.gov/opa/pr/volkswagen-ag-agrees-plead-guilty-and-pay-43-billion-connection-allegations-conspiracy-and"},
    {"country": "germany", "category": "State Ownership · Germany",
     "headline": "The German Federal Government owns approximately 27.8% of Deutsche Telekom.",
     "detail": (
         "Deutsche Telekom was privatised from Deutsche Bundespost in 1995, but the Federal Government "
         "retained its stake via KfW Bankengruppe. Germany also holds direct or indirect majority stakes "
         "in Deutsche Post, Deutsche Bahn, and partial stakes in Lufthansa."
     ),
     "source": "Beteiligungsbericht des Bundes / Bundesministerium der Finanzen",
     "source_url": "https://www.bundesregierung.de"},
]


# ── HELPERS ────────────────────────────────────────────────────────────────

def upsert_entity(cur: sqlite3.Cursor, e: dict) -> None:
    """Insert or replace the top-level entity row, then rebuild sub-tables."""
    cur.execute("""
        INSERT OR REPLACE INTO entities
            (id, type, country, name, summary, last_scraped,
             ticker, exchange, sector, headquarters, founded, employees, revenue, market_cap,
             title, nationality, born, net_worth, net_worth_rank, net_worth_source, net_worth_url)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        e["id"], e["type"], e["country"], e["name"],
        e.get("summary"), NOW,
        e.get("ticker"), e.get("exchange"), e.get("sector"),
        e.get("headquarters"), e.get("founded"), e.get("employees"),
        e.get("revenue"), e.get("market_cap"),
        e.get("title"), e.get("nationality"), e.get("born"),
        e.get("net_worth"), e.get("net_worth_rank"),
        e.get("net_worth_source"), e.get("net_worth_url"),
    ))

    eid = e["id"]

    # Clear and re-insert all sub-tables
    for table in ("shareholders", "compensation", "lobbying", "political_spending",
                  "fines", "labor", "competitors", "assets",
                  "board_memberships", "foundations", "timeline", "sources"):
        cur.execute(f"DELETE FROM {table} WHERE entity_id = ?", (eid,))

    for s in e.get("shareholders", []):
        cur.execute("INSERT INTO shareholders (entity_id,name,stake,type,source,source_url,as_of) VALUES (?,?,?,?,?,?,?)",
                    (eid, s["name"], s.get("stake"), s.get("type"), s.get("source"), s.get("source_url"), s.get("as_of")))

    comp = e.get("compensation")
    if comp:
        cur.execute("""INSERT INTO compensation
            (entity_id,fiscal_year,ceo_name,ceo_title,ceo_total,ceo_salary,ceo_equity,ceo_other,
             median_worker,ceo_worker_ratio,source,source_url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (eid, comp.get("fiscal_year"), comp.get("ceo_name"), comp.get("ceo_title"),
             comp.get("ceo_total"), comp.get("ceo_salary"), comp.get("ceo_equity"), comp.get("ceo_other"),
             comp.get("median_worker"), comp.get("ceo_worker_ratio"),
             comp.get("source"), comp.get("source_url")))

    for l in e.get("lobbying", []):
        cur.execute("INSERT INTO lobbying (entity_id,year,amount,currency,source,source_url) VALUES (?,?,?,?,?,?)",
                    (eid, l["year"], l["amount"], l.get("currency", "EUR"), l["source"], l.get("source_url")))

    for p in e.get("political_spending", []):
        cur.execute("INSERT INTO political_spending (entity_id,pac,cycle,total,currency,note,source,source_url) VALUES (?,?,?,?,?,?,?,?)",
                    (eid, p.get("pac"), p.get("cycle"), p.get("total"), p.get("currency", "EUR"),
                     p.get("note"), p.get("source"), p.get("source_url")))

    for f in e.get("fines", []):
        cur.execute("INSERT INTO fines (entity_id,year,description,source,source_url) VALUES (?,?,?,?,?)",
                    (eid, f["year"], f["description"], f["source"], f.get("source_url")))

    for lab in e.get("labor", []):
        cur.execute("INSERT INTO labor (entity_id,description,source,source_url) VALUES (?,?,?,?)",
                    (eid, lab["description"], lab["source"], lab.get("source_url")))

    for c in e.get("competitors", []):
        cur.execute("INSERT INTO competitors (entity_id,name) VALUES (?,?)", (eid, c))

    for a in e.get("assets", []):
        cur.execute("INSERT INTO assets (entity_id,name,description,source,source_url) VALUES (?,?,?,?,?)",
                    (eid, a["name"], a.get("description"), a.get("source"), a.get("source_url")))

    for b in e.get("board_memberships", []):
        cur.execute("INSERT INTO board_memberships (entity_id,org,role,source) VALUES (?,?,?,?)",
                    (eid, b["org"], b.get("role"), b.get("source")))

    for fnd in e.get("foundations", []):
        cur.execute("INSERT INTO foundations (entity_id,name,description,source,source_url) VALUES (?,?,?,?,?)",
                    (eid, fnd["name"], fnd.get("description"), fnd.get("source"), fnd.get("source_url")))

    for t in e.get("timeline", []):
        cur.execute("INSERT INTO timeline (entity_id,year,event) VALUES (?,?,?)",
                    (eid, t["year"], t["event"]))

    for src in e.get("sources", []):
        cur.execute("INSERT INTO sources (entity_id,title,url) VALUES (?,?,?)",
                    (eid, src["title"], src["url"]))


def seed_fact_cards(cur: sqlite3.Cursor) -> None:
    """Clear and re-insert all fact cards."""
    cur.execute("DELETE FROM fact_cards WHERE country = 'germany'")
    for card in FACT_CARDS:
        cur.execute("""INSERT INTO fact_cards (country,category,headline,detail,source,source_url)
                       VALUES (?,?,?,?,?,?)""",
                    (card.get("country"), card["category"], card["headline"],
                     card.get("detail"), card["source"], card["source_url"]))
    print(f"  Seeded {len(FACT_CARDS)} fact cards.")


# ── MAIN ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Who Owns What database with Germany Phase I data.")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found at {db_path}. Run init_db.py first.")
        raise SystemExit(1)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    try:
        for entity in ENTITIES:
            upsert_entity(cur, entity)
            print(f"  Upserted: {entity['id']}")
        seed_fact_cards(cur)
        conn.commit()
        print(f"\nSeeded {len(ENTITIES)} entities into {db_path}")
    except Exception as exc:
        conn.rollback()
        raise exc
    finally:
        conn.close()


if __name__ == "__main__":
    main()
