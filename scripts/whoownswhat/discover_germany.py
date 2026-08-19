"""
discover_germany.py — Who Owns What
Populates the company_queue table with German index companies:
  - DAX 40  (Germany's blue-chip index)
  - MDAX 50 (mid-cap)
  - TecDAX  (tech-focused, unique entries not already in DAX/MDAX)
  - SDAX    (small-cap, selected)
  - Private (major unlisted German companies)

Run once to seed the queue. Re-running is safe — uses INSERT OR IGNORE.
Companies are then scraped daily by scrape_company_batch.py (5 per run).

Usage:
    python scripts/whoownswhat/discover_germany.py
    python scripts/whoownswhat/discover_germany.py --db custom.db
    python scripts/whoownswhat/discover_germany.py --stats
    python scripts/whoownswhat/discover_germany.py --list DAX40
"""

import argparse
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "whoownswhat.db"

# ── COMPANY REGISTRY ───────────────────────────────────────────────────────
# Format: (slug, name, ticker, index, wiki_title_en, wiki_title_de, wikidata_qid)
# Wikidata QIDs verified against wikidata.org. Wiki titles are EN page titles.
# Already-seeded companies (volkswagen, sap) are included — INSERT OR IGNORE skips them.

DAX_40: list[tuple] = [
    # slug, name, ticker, index, wiki_en, wiki_de, qid
    ("adidas",               "Adidas AG",                    "ADS",   "DAX40", "Adidas",                           "Adidas",                          "Q3895"),
    ("airbus",               "Airbus SE",                    "AIR",   "DAX40", "Airbus",                           "Airbus",                          "Q67"),
    ("allianz",              "Allianz SE",                   "ALV",   "DAX40", "Allianz",                          "Allianz SE",                      "Q487097"),
    ("basf",                 "BASF SE",                      "BAS",   "DAX40", "BASF",                             "BASF",                            "Q9401"),
    ("bayer",                "Bayer AG",                     "BAYN",  "DAX40", "Bayer",                            "Bayer AG",                        "Q152006"),
    ("beiersdorf",           "Beiersdorf AG",                "BEI",   "DAX40", "Beiersdorf",                       "Beiersdorf",                      "Q437360"),
    ("bmw",                  "BMW AG",                       "BMW",   "DAX40", "BMW",                              "BMW AG",                          "Q26678"),
    ("brenntag",             "Brenntag SE",                  "BNR",   "DAX40", "Brenntag",                         "Brenntag",                        "Q796583"),
    ("commerzbank",          "Commerzbank AG",               "CBK",   "DAX40", "Commerzbank",                      "Commerzbank",                     "Q154950"),
    ("continental",          "Continental AG",               "CON",   "DAX40", "Continental AG",                   "Continental AG",                  "Q156579"),
    ("covestro",             "Covestro AG",                  "1COV",  "DAX40", "Covestro",                         "Covestro",                        "Q18635029"),
    ("daimler-truck",        "Daimler Truck Holding AG",     "DTG",   "DAX40", "Daimler Truck",                    "Daimler Truck",                   "Q110493600"),
    ("deutsche-bank",        "Deutsche Bank AG",             "DBK",   "DAX40", "Deutsche Bank",                    "Deutsche Bank",                   "Q66048"),
    ("deutsche-boerse",      "Deutsche Boerse AG",           "DB1",   "DAX40", "Deutsche Boerse",                  "Deutsche Boerse",                 "Q490395"),
    ("deutsche-post",        "Deutsche Post AG",             "DHL",   "DAX40", "Deutsche Post",                    "Deutsche Post",                   "Q157805"),
    ("deutsche-telekom",     "Deutsche Telekom AG",          "DTE",   "DAX40", "Deutsche Telekom",                 "Deutsche Telekom",                "Q104851"),
    ("eon",                  "E.ON SE",                      "EOAN",  "DAX40", "E.ON",                             "E.ON",                            "Q430518"),
    ("fresenius",            "Fresenius SE & Co. KGaA",      "FRE",   "DAX40", "Fresenius",                        "Fresenius SE & Co. KGaA",         "Q523848"),
    ("hannover-re",          "Hannover Re SE",               "HNR1",  "DAX40", "Hannover Re",                      "Hannover Rueck",                  "Q1583246"),
    ("heidelberg-materials", "HeidelbergMaterials AG",       "HEIB",  "DAX40", "HeidelbergMaterials",              "HeidelbergMaterials",             "Q167527"),
    ("henkel",               "Henkel AG & Co. KGaA",         "HEN3",  "DAX40", "Henkel",                           "Henkel",                          "Q312434"),
    ("infineon",             "Infineon Technologies AG",     "IFX",   "DAX40", "Infineon Technologies",            "Infineon Technologies",           "Q556418"),
    ("mercedes-benz",        "Mercedes-Benz Group AG",       "MBG",   "DAX40", "Mercedes-Benz Group",              "Mercedes-Benz Group",             "Q81965"),
    ("merck-kgaa",           "Merck KGaA",                   "MRK",   "DAX40", "Merck Group",                      "Merck KGaA",                      "Q152096"),
    ("mtu-aero",             "MTU Aero Engines AG",          "MTX",   "DAX40", "MTU Aero Engines",                 "MTU Aero Engines",                "Q821863"),
    ("munich-re",            "Muenchener Rueckversicherungs-Gesellschaft AG", "MUV2", "DAX40", "Munich Re", "Munich Re", "Q156548"),
    ("porsche-ag",           "Dr. Ing. h.c. F. Porsche AG",  "P911",  "DAX40", "Porsche",                          "Porsche AG",                      "Q42952"),
    ("porsche-se",           "Porsche Automobil Holding SE",  "PAH3",  "DAX40", "Porsche Automobil Holding",        "Porsche Automobil Holding",       "Q659093"),
    ("qiagen",               "QIAGEN N.V.",                  "QIA",   "DAX40", "Qiagen",                           "QIAGEN",                          "Q1663616"),
    ("rheinmetall",          "Rheinmetall AG",               "RHM",   "DAX40", "Rheinmetall",                      "Rheinmetall",                     "Q182310"),
    ("rwe",                  "RWE AG",                       "RWE",   "DAX40", "RWE",                              "RWE",                             "Q155194"),
    ("sap",                  "SAP SE",                       "SAP",   "DAX40", "SAP SE",                           "SAP SE",                          "Q161635"),
    ("sartorius",            "Sartorius AG",                 "SRT3",  "DAX40", "Sartorius AG",                     "Sartorius AG",                    "Q2143699"),
    ("siemens",              "Siemens AG",                   "SIE",   "DAX40", "Siemens",                          "Siemens AG",                      "Q36534"),
    ("siemens-energy",       "Siemens Energy AG",            "ENR",   "DAX40", "Siemens Energy",                   "Siemens Energy",                  "Q97264734"),
    ("siemens-healthineers", "Siemens Healthineers AG",      "SHL",   "DAX40", "Siemens Healthineers",             "Siemens Healthineers",            "Q42895077"),
    ("symrise",              "Symrise AG",                   "SY1",   "DAX40", "Symrise",                          "Symrise",                         "Q1454255"),
    ("volkswagen",           "Volkswagen AG",                "VOW3",  "DAX40", "Volkswagen",                       "Volkswagen AG",                   "Q246"),
    ("vonovia",              "Vonovia SE",                   "VNA",   "DAX40", "Vonovia",                          "Vonovia",                         "Q2360782"),
    ("zalando",              "Zalando SE",                   "ZAL",   "DAX40", "Zalando",                          "Zalando",                         "Q523471"),
]

MDAX_50: list[tuple] = [
    ("aixtron",              "AIXTRON SE",                   "AIXA",  "MDAX",  "Aixtron",                          "Aixtron",                         "Q431246"),
    ("aroundtown",           "Aroundtown SA",                "AT1",   "MDAX",  "Aroundtown",                       "Aroundtown",                      "Q23883580"),
    ("aurubis",              "Aurubis AG",                   "NDA",   "MDAX",  "Aurubis",                          "Aurubis",                         "Q448855"),
    ("auto1",                "AUTO1 Group SE",               "AG1",   "MDAX",  "AUTO1 Group",                      "AUTO1 Group",                     "Q61750673"),
    ("carl-zeiss-meditec",   "Carl Zeiss Meditec AG",        "AFX",   "MDAX",  "Carl Zeiss Meditec",               "Carl Zeiss Meditec",              "Q1041745"),
    ("ceconomy",             "Ceconomy AG",                  "CE2",   "MDAX",  "Ceconomy",                         "Ceconomy",                        "Q15857774"),
    ("compugroup",           "CompuGroup Medical SE",        "COP",   "MDAX",  "CompuGroup Medical",               "CompuGroup Medical",              "Q1116396"),
    ("delivery-hero",        "Delivery Hero SE",             "DHER",  "MDAX",  "Delivery Hero",                    "Delivery Hero",                   "Q26218005"),
    ("deutz",                "DEUTZ AG",                     "DEZ",   "MDAX",  "Deutz AG",                         "Deutz AG",                        "Q625892"),
    ("douglas",              "Douglas AG",                   "DOU",   "MDAX",  "Douglas AG",                       "Douglas AG",                      "Q453981"),
    ("dws-group",            "DWS Group GmbH & Co. KGaA",   "DWS",   "MDAX",  "DWS Group",                        "DWS Group",                       "Q5206503"),
    ("evonik",               "Evonik Industries AG",         "EVK",   "MDAX",  "Evonik Industries",                "Evonik Industries",               "Q627603"),
    ("fielmann",             "Fielmann AG",                  "FIE",   "MDAX",  "Fielmann",                         "Fielmann",                        "Q570747"),
    ("fraport",              "Fraport AG",                   "FRA",   "MDAX",  "Fraport",                          "Fraport",                         "Q663541"),
    ("fresenius-medical",    "Fresenius Medical Care AG",    "FME",   "MDAX",  "Fresenius Medical Care",           "Fresenius Medical Care",          "Q1443576"),
    ("gea-group",            "GEA Group AG",                 "G1A",   "MDAX",  "GEA Group",                        "GEA Group",                       "Q571459"),
    ("gerresheimer",         "Gerresheimer AG",              "GXI",   "MDAX",  "Gerresheimer",                     "Gerresheimer",                    "Q1518006"),
    ("hapag-lloyd",          "Hapag-Lloyd AG",               "HLAG",  "MDAX",  "Hapag-Lloyd",                      "Hapag-Lloyd",                     "Q320862"),
    ("hella",                "HELLA GmbH & Co. KGaA",       "HLE",   "MDAX",  "Hella (company)",                  "Hella GmbH & Co. KGaA",           "Q881564"),
    ("hochtief",             "HOCHTIEF AG",                  "HOT",   "MDAX",  "Hochtief",                         "Hochtief",                        "Q564488"),
    ("hugo-boss",            "Hugo Boss AG",                 "BOSS",  "MDAX",  "Hugo Boss",                        "Hugo Boss",                       "Q491749"),
    ("jenoptik",             "JENOPTIK AG",                  "JEN",   "MDAX",  "Jenoptik",                         "Jenoptik",                        "Q1680866"),
    ("k-plus-s",             "K+S AG",                       "SDZ",   "MDAX",  "K+S",                              "K+S",                             "Q570735"),
    ("knorr-bremse",         "Knorr-Bremse AG",              "KBX",   "MDAX",  "Knorr-Bremse",                     "Knorr-Bremse",                    "Q699693"),
    ("krones",               "Krones AG",                    "KRN",   "MDAX",  "Krones AG",                        "Krones AG",                       "Q568558"),
    ("lanxess",              "LANXESS AG",                   "LXS",   "MDAX",  "Lanxess",                          "Lanxess",                         "Q568413"),
    ("linde",                "Linde plc",                    "LIN",   "MDAX",  "Linde plc",                        "Linde plc",                       "Q81307"),
    ("nemetschek",           "Nemetschek SE",                "NEM",   "MDAX",  "Nemetschek",                       "Nemetschek",                      "Q569117"),
    ("norma-group",          "NORMA Group SE",               "NOEJ",  "MDAX",  "Norma Group",                      "Norma Group",                     "Q2021965"),
    ("osram",                "ams OSRAM AG",                 "OSAS",  "MDAX",  "Osram",                            "Osram",                           "Q693513"),
    ("puma",                 "PUMA SE",                      "PUM",   "MDAX",  "Puma SE",                          "Puma SE",                         "Q157462"),
    ("rational",             "Rational AG",                  "RAA",   "MDAX",  "Rational AG",                      "Rational AG",                     "Q1752696"),
    ("scout24",              "Scout24 SE",                   "G24",   "MDAX",  "Scout24",                          "Scout24",                         "Q2352428"),
    ("sixt",                 "Sixt SE",                      "SIX2",  "MDAX",  "Sixt",                             "Sixt SE",                         "Q570727"),
    ("stabilus",             "Stabilus SE",                  "STM",   "MDAX",  "Stabilus",                         "Stabilus",                        "Q1654869"),
    ("stroeer",              "Stroeer SE & Co. KGaA",        "SAX",   "MDAX",  "Stroer",                           "Stroeer SE",                      "Q1657568"),
    ("suedzucker",           "Suedzucker AG",                "SZU",   "MDAX",  "Suedzucker",                       "Suedzucker",                      "Q571261"),
    ("talanx",               "Talanx AG",                    "TLX",   "MDAX",  "Talanx",                           "Talanx",                          "Q1137576"),
    ("thyssenkrupp",         "ThyssenKrupp AG",              "TKA",   "MDAX",  "Thyssenkrupp",                     "ThyssenKrupp",                    "Q183946"),
    ("traton",               "TRATON SE",                    "8TRA",  "MDAX",  "Traton",                           "Traton SE",                       "Q60743447"),
    ("uniper",               "Uniper SE",                    "UN01",  "MDAX",  "Uniper",                           "Uniper",                          "Q15883073"),
    ("varta",                "VARTA AG",                     "VAR1",  "MDAX",  "Varta AG",                         "Varta AG",                        "Q881432"),
    ("wacker-chemie",        "Wacker Chemie AG",             "WCH",   "MDAX",  "Wacker Chemie",                    "Wacker Chemie",                   "Q676741"),
    ("wuestenrot",           "Wuestenrot & Wuerttembergische AG", "WUW", "MDAX", "Wustenrot & Wurttembergische",  "Wuestenrot & Wuerttembergische",  "Q1427534"),
    ("zf-friedrichshafen",   "ZF Friedrichshafen AG",        None,    "MDAX",  "ZF Friedrichshafen",               "ZF Friedrichshafen",              "Q685025"),
]

# TecDAX — tech-focused index. Only companies not already in DAX40 or MDAX50.
TECDAX: list[tuple] = [
    ("1und1",                "1&1 AG",                       "1U1",   "TecDAX","1&1 AG",                           "1&1 AG",                          "Q56869091"),
    ("bechtle",              "Bechtle AG",                   "BC8",   "TecDAX","Bechtle",                          "Bechtle AG",                      "Q706673"),
    ("cancom",               "CANCOM SE",                    "COK",   "TecDAX","Cancom",                           "CANCOM SE",                       "Q1040869"),
    ("draegerwerk",          "Draegerwerk AG & Co. KGaA",    "DRW3",  "TecDAX","Draeger",                          "Draegerwerk",                     "Q467671"),
    ("eckert-ziegler",       "Eckert & Ziegler SE",          "EUZ",   "TecDAX","Eckert & Ziegler",                 "Eckert & Ziegler",                "Q1296099"),
    ("evotec",               "Evotec SE",                    "EVT",   "TecDAX","Evotec",                           "Evotec SE",                       "Q3049395"),
    ("hypoport",             "Hypoport SE",                  "HYQ",   "TecDAX","Hypoport",                         "Hypoport",                        "Q1622694"),
    ("pfeiffer-vacuum",      "Pfeiffer Vacuum Technology SE","PFV",   "TecDAX","Pfeiffer Vacuum",                  "Pfeiffer Vacuum",                 "Q2045920"),
    ("siltronic",            "Siltronic AG",                 "WAF",   "TecDAX","Siltronic",                        "Siltronic",                       "Q2305975"),
    ("sma-solar",            "SMA Solar Technology AG",      "S92",   "TecDAX","SMA Solar Technology",             "SMA Solar Technology",            "Q881598"),
    ("suess-microtec",       "Suess MicroTec SE",            "SMHN",  "TecDAX","Suess MicroTec",                   "Suss MicroTec",                   "Q2375804"),
    ("teamviewer",           "TeamViewer SE",                "TMV",   "TecDAX","TeamViewer",                       "TeamViewer SE",                   "Q78202028"),
    ("united-internet",      "United Internet AG",           "UTDI",  "TecDAX","United Internet",                  "United Internet AG",              "Q1145118"),
]

# SDAX — small-cap index, selected companies
SDAX: list[tuple] = [
    ("aareal-bank",          "Aareal Bank AG",               "ARL",   "SDAX",  "Aareal Bank",                      "Aareal Bank",                     "Q688037"),
    ("bertrandt",            "Bertrandt AG",                 "BDT",   "SDAX",  "Bertrandt",                        "Bertrandt AG",                    "Q564617"),
    ("borussia-dortmund",    "Borussia Dortmund GmbH & Co. KGaA", "BVB", "SDAX", "Borussia Dortmund",             "Borussia Dortmund GmbH & Co. KGaA","Q2747"),
    ("cewe",                 "CEWE Stiftung & Co. OHGaA",   "CWC",   "SDAX",  "Cewe Color",                       "CEWE Stiftung",                   "Q1067817"),
    ("dermapharm",           "Dermapharm Holding SE",        "DMP",   "SDAX",  "Dermapharm",                       "Dermapharm Holding",              "Q55629048"),
    ("duerr",                "Duerr AG",                     "DUE",   "SDAX",  "Durr AG",                          "Duerr AG",                        "Q554047"),
    ("elring-klinger",       "ElringKlinger AG",             "ZIL2",  "SDAX",  "ElringKlinger",                    "ElringKlinger AG",                "Q654447"),
    ("encavis",              "Encavis AG",                   "ECV",   "SDAX",  "Encavis",                          "Encavis AG",                      "Q1358063"),
    ("grenke",               "GRENKE AG",                    "GLJ",   "SDAX",  "Grenke",                           "GRENKE AG",                       "Q2064186"),
    ("hhla",                 "Hamburger Hafen und Logistik AG", "HHLA", "SDAX", "Hamburger Hafen und Logistik",    "Hamburger Hafen und Logistik",    "Q1565403"),
    ("hornbach",             "Hornbach Holding AG & Co. KGaA","HBH",  "SDAX",  "Hornbach Holding",                 "Hornbach Holding",                "Q1625785"),
    ("jungheinrich",         "Jungheinrich AG",              "JUN3",  "SDAX",  "Jungheinrich",                     "Jungheinrich AG",                 "Q669416"),
    ("kion-group",           "KION Group AG",                "KGX",   "SDAX",  "Kion Group",                       "KION Group",                      "Q1741165"),
    ("kws-saat",             "KWS Saat SE & Co. KGaA",      "KWS",   "SDAX",  "KWS Saat",                         "KWS Saat",                        "Q2301897"),
    ("leoni",                "Leoni AG",                     "LEI",   "SDAX",  "Leoni AG",                         "Leoni AG",                        "Q651449"),
    ("metro",                "Metro AG",                     "B4B",   "SDAX",  "Metro AG",                         "Metro AG",                        "Q169403"),
    ("renk-group",           "RENK Group AG",                "RENK",  "SDAX",  "Renk Group",                       "Renk Group",                      "Q2144553"),
    ("salzgitter",           "Salzgitter AG",                "SZG",   "SDAX",  "Salzgitter AG",                    "Salzgitter AG",                   "Q503327"),
    ("sgl-carbon",           "SGL Carbon SE",                "SGL",   "SDAX",  "SGL Carbon",                       "SGL Carbon",                      "Q1570660"),
    ("takkt",                "TAKKT AG",                     "TTK",   "SDAX",  "Takkt AG",                         "TAKKT AG",                        "Q2396688"),
    ("vitesco",              "Vitesco Technologies Group AG", "VTSC",  "SDAX",  "Vitesco Technologies",             "Vitesco Technologies",            "Q98093023"),
    ("westwing",             "Westwing Group AG",            "WWG",   "SDAX",  "Westwing",                         "Westwing Group",                  "Q43069296"),
    ("enbw",                 "EnBW Energie Baden-Wuerttemberg AG", "EBK", "SDAX", "EnBW",                          "EnBW",                            "Q457536"),
]

# Major private German companies (not listed on any index)
PRIVATE_GERMAN: list[tuple] = [
    # Retail / FMCG
    ("bosch",                "Robert Bosch GmbH",            None,    "Private","Robert Bosch GmbH",               "Robert Bosch GmbH",               "Q234021"),
    ("lidl",                 "Lidl GmbH & Co. KG",           None,    "Private","Lidl",                            "Lidl",                            "Q151954"),
    ("aldi-nord",            "ALDI Nord",                    None,    "Private","Aldi Nord",                        "Aldi Nord",                       "Q175703"),
    ("aldi-sued",            "ALDI Sud",                     None,    "Private","Aldi Sud",                         "Aldi Sued",                       "Q175700"),
    ("edeka",                "EDEKA Zentrale AG & Co. KG",   None,    "Private","Edeka",                           "Edeka",                           "Q390211"),
    ("rewe",                 "REWE Group",                   None,    "Private","Rewe Group",                       "Rewe Group",                      "Q565773"),
    ("schwarz-gruppe",       "Schwarz Gruppe",               None,    "Private","Schwarz Group",                   "Schwarz Gruppe",                  "Q2341711"),
    ("otto-group",           "Otto Group",                   None,    "Private","Otto Group",                       "Otto Group",                      "Q487781"),
    ("deichmann",            "Deichmann SE",                 None,    "Private","Deichmann",                        "Deichmann",                       "Q568433"),
    ("tchibo",               "Tchibo GmbH",                  None,    "Private","Tchibo",                           "Tchibo",                          "Q492879"),
    ("rossmann",             "Dirk Rossmann GmbH",           None,    "Private","Rossmann (company)",              "Rossmann (Unternehmen)",          "Q315543"),
    ("dm-drogerie",          "dm-drogerie markt GmbH & Co. KG", None, "Private","Dm-drogerie markt",              "dm-drogerie markt",               "Q528717"),
    ("obi",                  "OBI GmbH & Co. Deutschland KG",None,    "Private","OBI (store)",                     "OBI",                             "Q1616885"),
    ("haribo",               "Haribo GmbH & Co. KG",         None,    "Private","Haribo",                          "Haribo",                          "Q522931"),
    ("melitta",              "Melitta Group",                None,    "Private","Melitta",                          "Melitta",                         "Q659247"),
    ("dr-oetker",            "Dr. August Oetker KG",         None,    "Private","Dr. Oetker",                      "Dr. Oetker",                      "Q567173"),
    # Industrials / Engineering
    ("heraeus",              "Heraeus Holding GmbH",         None,    "Private","Heraeus",                         "Heraeus",                         "Q702657"),
    ("bertelsmann",          "Bertelsmann SE & Co. KGaA",    None,    "Private","Bertelsmann",                     "Bertelsmann",                     "Q3010"),
    ("trumpf",               "TRUMPF GmbH + Co. KG",         None,    "Private","Trumpf (company)",                "TRUMPF",                          "Q703011"),
    ("freudenberg",          "Freudenberg Group",            None,    "Private","Freudenberg Group",               "Freudenberg-Gruppe",              "Q1390884"),
    ("schaeffler",           "Schaeffler AG",                "SHA",   "Private","Schaeffler AG",                   "Schaeffler AG",                   "Q2269827"),
    ("mann-hummel",          "Mann+Hummel Group",            None,    "Private","Mann+Hummel",                     "Mann+Hummel",                     "Q879124"),
    ("stihl",                "Andreas Stihl AG & Co. KG",   None,    "Private","Stihl",                            "Stihl",                           "Q492803"),
    ("wuerth",               "Wuerth Group",                 None,    "Private","Würth Group",                     "Wuerth-Gruppe",                   "Q697816"),
    ("festo",                "Festo SE & Co. KG",            None,    "Private","Festo",                           "Festo",                           "Q573440"),
    ("kaercher",             "Alfred Kaercher SE & Co. KG",  None,    "Private","Kärcher",                         "Alfred Kaercher SE & Co. KG",     "Q487478"),
    ("claas",                "CLAAS KGaA mbH",               None,    "Private","Claas",                           "CLAAS",                           "Q471958"),
    ("faber-castell",        "Faber-Castell AG",             None,    "Private","Faber-Castell",                   "Faber-Castell",                   "Q461684"),
    ("miele",                "Miele & Cie. KG",              None,    "Private","Miele",                           "Miele",                           "Q497882"),
    ("phoenix-contact",      "Phoenix Contact GmbH & Co. KG",None,    "Private","Phoenix Contact",                 "Phoenix Contact",                 "Q888038"),
    ("webasto",              "Webasto SE",                   None,    "Private","Webasto",                         "Webasto",                         "Q698219"),
    ("brose",                "Brose Fahrzeugteile SE & Co.", None,    "Private","Brose Fahrzeugteile",             "Brose",                           "Q880398"),
    ("tengelmann",           "Tengelmann Group",             None,    "Private","Tengelmann",                      "Tengelmann",                      "Q541534"),
    ("sick",                 "SICK AG",                      "SIK",   "Private","Sick AG",                         "SICK AG",                         "Q698239"),
    ("wirtgen",              "Wirtgen Group",                None,    "Private","Wirtgen Group",                   "Wirtgen Group",                   "Q1779234"),
]

ALL_COMPANIES = DAX_40 + MDAX_50 + TECDAX + SDAX + PRIVATE_GERMAN

# Priority ordering for scraping: DAX first, then MDAX, TecDAX, SDAX, Private
_INDEX_PRIORITY = {"DAX40": 0, "MDAX": 1, "TecDAX": 2, "SDAX": 3, "Private": 4}


def populate_queue(conn: sqlite3.Connection, dry_run: bool = False, index_filter: str | None = None) -> None:
    cur = conn.cursor()
    inserted = 0
    skipped = 0

    companies = ALL_COMPANIES
    if index_filter:
        companies = [c for c in ALL_COMPANIES if c[3].lower() == index_filter.lower()]

    # Sort by index priority so DAX companies are picked first by the batch scraper
    companies = sorted(companies, key=lambda c: _INDEX_PRIORITY.get(c[3], 99))

    for row in companies:
        slug, name, ticker, index_name, wiki_en, wiki_de, qid = row

        if dry_run:
            print(f"  Would add: {slug} ({name}) [{index_name}]")
            inserted += 1
            continue

        try:
            cur.execute("""
                INSERT OR IGNORE INTO company_queue
                    (slug, name, ticker, index_name, wiki_title, wiki_title_de, wikidata_qid)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (slug, name, ticker, index_name, wiki_en, wiki_de, qid))
            if cur.rowcount:
                inserted += 1
            else:
                skipped += 1
        except sqlite3.Error as exc:
            print(f"  Error inserting {slug}: {exc}")

    if not dry_run:
        conn.commit()

    total = len(companies)
    print(f"\nQueue populated: {inserted} added, {skipped} already existed.")
    print(f"Total in scope: {total} companies")


def print_stats(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    print("\nQueue statistics:")
    cur.execute("SELECT status, COUNT(*) FROM company_queue GROUP BY status ORDER BY status")
    for status, count in cur.fetchall():
        print(f"  {status:12s}: {count}")
    cur.execute("SELECT COUNT(*) FROM company_queue")
    print(f"  {'TOTAL':12s}: {cur.fetchone()[0]}")
    print()
    cur.execute("""
        SELECT index_name, COUNT(*) as total,
               SUM(CASE WHEN status='scraped' THEN 1 ELSE 0 END) as done
        FROM company_queue
        GROUP BY index_name
        ORDER BY MIN(CASE index_name WHEN 'DAX40' THEN 0 WHEN 'MDAX' THEN 1
                                     WHEN 'TecDAX' THEN 2 WHEN 'SDAX' THEN 3 ELSE 4 END)
    """)
    print("  Progress by index:")
    for index_name, total, done in cur.fetchall():
        bar = "█" * done + "░" * (total - done)
        print(f"  {index_name:10s}: {done:3d}/{total:<3d}  {bar}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Populate the company discovery queue with German index companies."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stats", action="store_true", help="Show queue statistics only")
    parser.add_argument(
        "--list", metavar="INDEX",
        help="Only add companies from a specific index (DAX40, MDAX, TecDAX, SDAX, Private)"
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}. Run init_db.py first.")
        raise SystemExit(1)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

    if args.stats:
        print_stats(conn)
        conn.close()
        return

    try:
        populate_queue(conn, dry_run=args.dry_run, index_filter=args.list)
        if not args.dry_run:
            print_stats(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
