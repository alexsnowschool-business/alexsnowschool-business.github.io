"""Processing pipeline: event log -> graph view (design draft section 5).

The graph tables (people, companies, roles) are a rebuildable view, never
hand-patched. `rebuild_graph` truncates and replays the entire event log in
occurred_at order — fine at v0.1 scale (one company); revisit incremental
rebuilds if event volume grows.
"""

import json
from datetime import date


def insert_event(conn, *, type: str, source: str, source_document_id: str, occurred_at: date, payload: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO events (type, source, source_document_id, occurred_at, payload)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [type, source, source_document_id, occurred_at, json.dumps(payload)],
        )
    conn.commit()


def _upsert_company(cur, *, register_number: str, name: str, business_purpose_raw: str | None = None) -> str:
    cur.execute(
        """
        INSERT INTO companies (name, register_number, business_purpose_raw)
        VALUES (%s, %s, %s)
        ON CONFLICT (register_number) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        [name, register_number, business_purpose_raw],
    )
    return cur.fetchone()["id"]


def _upsert_person(cur, *, name: str, date_of_birth=None) -> str:
    # v0.1 identity matching: name only (design draft section 2 scope note).
    cur.execute("SELECT id FROM people WHERE name = %s", [name])
    existing = cur.fetchone()
    if existing:
        return existing["id"]
    cur.execute(
        "INSERT INTO people (name, date_of_birth) VALUES (%s, %s) RETURNING id",
        [name, date_of_birth],
    )
    return cur.fetchone()["id"]


def rebuild_graph(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE roles, people, companies")

        cur.execute("SELECT * FROM events ORDER BY occurred_at, ingested_at")
        for event in cur.fetchall():
            payload = event["payload"]
            if event["type"] == "person_appointed":
                company_id = _upsert_company(
                    cur,
                    register_number=payload["company_register_number"],
                    name=payload["company_name"],
                    business_purpose_raw=payload.get("business_purpose_raw"),
                )
                person_id = _upsert_person(cur, name=payload["person_name"], date_of_birth=payload.get("date_of_birth"))
                cur.execute(
                    """
                    INSERT INTO roles (person_id, company_id, role_type, started_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    [person_id, company_id, payload["role_type"], payload["started_at"]],
                )

            elif event["type"] == "person_departed":
                cur.execute(
                    """
                    UPDATE roles SET ended_at = %s
                    WHERE person_id = (SELECT id FROM people WHERE name = %s)
                      AND company_id = (SELECT id FROM companies WHERE register_number = %s)
                      AND role_type = %s
                      AND ended_at IS NULL
                    """,
                    [
                        payload["ended_at"],
                        payload["person_name"],
                        payload["company_register_number"],
                        payload["role_type"],
                    ],
                )

            elif event["type"] == "company_insolvent":
                company_id = _upsert_company(
                    cur,
                    register_number=payload["company_register_number"],
                    name=payload["company_name"],
                )
                cur.execute("UPDATE companies SET status = 'insolvent' WHERE id = %s", [company_id])

    conn.commit()
