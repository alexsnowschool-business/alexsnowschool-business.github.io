"""
export_data_js.py — Who Owns What
Reads the SQLite database and exports a fresh data.js file for the static frontend.

This is the bridge between the database (source of truth) and the static site.
Run after any scraper or manual data update.

Usage:
    python scripts/whoownswhat/export_data_js.py
    python scripts/whoownswhat/export_data_js.py --db custom.db --out whoownswhat/data.js
"""

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "whoownswhat.db"
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "whoownswhat" / "data.js"


def q(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    """Execute a query and return rows as dicts."""
    conn.row_factory = sqlite3.Row
    cur = conn.execute(sql, params)
    return [dict(r) for r in cur.fetchall()]


def build_entity(conn: sqlite3.Connection, e: dict) -> dict:
    eid = e["id"]
    out: dict = {
        "type": e["type"],
        "country": e["country"],
        "name": e["name"],
        "summary": e.get("summary") or "",
    }

    if e["type"] == "company":
        for k in ("ticker", "exchange", "sector", "headquarters", "founded",
                  "employees", "revenue"):
            out[k] = e.get(k) or ""
        out["marketCap"] = e.get("market_cap") or ""

        # Shareholders
        out["shareholders"] = [
            {"name": r["name"], "stake": r["stake"], "type": r["type"],
             "source": r["source"], "url": r["source_url"] or ""}
            for r in q(conn, "SELECT * FROM shareholders WHERE entity_id=?", (eid,))
        ]

        # Compensation
        comp_rows = q(conn, "SELECT * FROM compensation WHERE entity_id=? ORDER BY fiscal_year DESC LIMIT 1", (eid,))
        if comp_rows:
            c = comp_rows[0]
            out["compensation"] = {
                "ceeName": c["ceo_name"], "ceoTitle": c["ceo_title"],
                "ceoTotal": c["ceo_total"], "ceoSalary": c["ceo_salary"],
                "ceoEquity": c["ceo_equity"],
                "medianWorker": c["median_worker"],
                "ceoWorkerRatio": c["ceo_worker_ratio"],
                "source": c["source"], "url": c["source_url"] or "",
            }

        # Lobbying
        out["lobbying"] = [
            {"year": r["year"], "amount": r["amount"],
             "source": r["source"], "url": r["source_url"] or ""}
            for r in q(conn, "SELECT * FROM lobbying WHERE entity_id=? ORDER BY year DESC", (eid,))
        ]

        # Political spending
        pol = q(conn, "SELECT * FROM political_spending WHERE entity_id=? LIMIT 1", (eid,))
        if pol:
            p = pol[0]
            out["politicalSpending"] = {
                "pac": p["pac"], "total2023": p["total"],
                "note": p["note"], "source": p["source"],
                "url": p["source_url"] or "",
            }

        # Fines
        out["fines"] = [
            {"year": r["year"], "description": r["description"],
             "source": r["source"], "url": r["source_url"] or ""}
            for r in q(conn, "SELECT * FROM fines WHERE entity_id=?", (eid,))
        ]

        # Labour
        out["labor"] = [
            {"description": r["description"], "source": r["source"],
             "url": r["source_url"] or ""}
            for r in q(conn, "SELECT * FROM labor WHERE entity_id=?", (eid,))
        ]

        # Competitors
        out["competitors"] = [
            r["name"]
            for r in q(conn, "SELECT name FROM competitors WHERE entity_id=?", (eid,))
        ]

    else:  # person
        for k in ("title", "nationality", "born"):
            out[k] = e.get(k) or ""
        out["netWorth"]       = e.get("net_worth") or ""
        out["netWorthRank"]   = e.get("net_worth_rank") or ""
        out["netWorthSource"] = e.get("net_worth_source") or ""
        out["netWorthUrl"]    = e.get("net_worth_url") or ""

        # Assets
        out["assets"] = [
            {"name": r["name"], "description": r["description"] or "",
             "source": r["source"] or "", "url": r["source_url"] or ""}
            for r in q(conn, "SELECT * FROM assets WHERE entity_id=?", (eid,))
        ]

        # Board memberships
        out["boardMemberships"] = [
            {"org": r["org"], "role": r["role"] or "", "source": r["source"] or ""}
            for r in q(conn, "SELECT * FROM board_memberships WHERE entity_id=?", (eid,))
        ]

        # Foundations
        out["foundations"] = [
            {"name": r["name"], "description": r["description"] or "",
             "source": r["source"] or "", "url": r["source_url"] or ""}
            for r in q(conn, "SELECT * FROM foundations WHERE entity_id=?", (eid,))
        ]

        # Political spending
        pol = q(conn, "SELECT * FROM political_spending WHERE entity_id=? LIMIT 1", (eid,))
        if pol:
            p = pol[0]
            out["politicalSpending"] = {
                "pac": p["pac"], "summary": p["note"] or "",
                "total2024": p.get("cycle") and p["total"],
                "source": p["source"], "url": p["source_url"] or "",
            }

        # Timeline
        out["timeline"] = [
            {"year": r["year"], "event": r["event"]}
            for r in q(conn, "SELECT * FROM timeline WHERE entity_id=? ORDER BY year", (eid,))
        ]

    # Sources (shared)
    out["sources"] = [
        {"title": r["title"], "url": r["url"] or ""}
        for r in q(conn, "SELECT * FROM sources WHERE entity_id=?", (eid,))
    ]

    return out


def build_fact_cards(conn: sqlite3.Connection) -> list[dict]:
    rows = q(conn, "SELECT * FROM fact_cards WHERE active=1 ORDER BY country, id")
    return [
        {
            "category": r["category"],
            "headline": r["headline"],
            "detail": r["detail"] or "",
            "source": r["source"] or "",
            "url": r["source_url"] or "",
        }
        for r in rows
    ]


def build_meta() -> dict:
    return {
        "countries": {
            "germany": {"label": "Germany", "flag": "DE", "currency": "EUR", "active": True},
            "us":      {"label": "United States", "flag": "US", "currency": "USD", "active": False},
            "uk":      {"label": "United Kingdom", "flag": "GB", "currency": "GBP", "active": False},
            "france":  {"label": "France", "flag": "FR", "currency": "EUR", "active": False},
        }
    }


def export(db_path: Path, out_path: Path) -> None:
    conn = sqlite3.connect(db_path)

    entity_rows = q(conn, "SELECT * FROM entities ORDER BY country, type, name")
    entities: dict = {}
    for row in entity_rows:
        eid = row["id"]
        entities[eid] = build_entity(conn, row)

    fact_cards = build_fact_cards(conn)
    meta = build_meta()

    conn.close()

    # Serialise
    payload = json.dumps(
        {"meta": meta, "entities": entities, "factCards": fact_cards},
        ensure_ascii=False, indent=4
    )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    js_content = (
        f"// data.js — Who Owns What\n"
        f"// AUTO-GENERATED by export_data_js.py — {generated_at}\n"
        f"// Source of truth: data/whoownswhat.db\n"
        f"// DO NOT EDIT MANUALLY — run export_data_js.py after any DB change.\n\n"
        f"const WOW_DATA = {payload};\n"
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(js_content, encoding="utf-8")
    print(f"Exported {len(entities)} entities + {len(fact_cards)} fact cards → {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Who Owns What DB to data.js")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}. Run init_db.py then seed_db.py first.")
        raise SystemExit(1)

    export(db_path, Path(args.out))


if __name__ == "__main__":
    main()
