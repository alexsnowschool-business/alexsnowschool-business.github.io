import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request

from database import get_connection
from deps import require_api_key

logging.basicConfig(level=logging.INFO)
access_log = logging.getLogger("access")

app = FastAPI(title="People & Company Register API", version="0.1.0")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Non-functional requirement (design draft section 6): every request
    # logged with requester identity and timestamp, for GDPR accountability.
    requester = request.headers.get("apikey", "anonymous")
    started_at = time.monotonic()
    response = await call_next(request)
    access_log.info(
        "request",
        extra={
            "requester": requester,
            "path": request.url.path,
            "status_code": response.status_code,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_ms": round((time.monotonic() - started_at) * 1000, 1),
        },
    )
    return response


@app.get("/people/{person_id}", dependencies=[Depends(require_api_key)])
def get_person(person_id: uuid.UUID):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name, date_of_birth FROM people WHERE id = %s", [str(person_id)])
        person = cur.fetchone()
        if person is None:
            raise HTTPException(status_code=404, detail="Person not found")

        cur.execute(
            """
            SELECT c.name AS company, r.role_type, r.started_at, r.ended_at, c.status AS company_status
            FROM roles r
            JOIN companies c ON c.id = r.company_id
            WHERE r.person_id = %s
            ORDER BY r.started_at DESC
            """,
            [str(person_id)],
        )
        roles = cur.fetchall()

    risk_flags = ["linked_to_insolvent_company"] if any(r["company_status"] == "insolvent" for r in roles) else []
    return {
        "name": person["name"],
        "roles": [
            {
                "company": r["company"],
                "role_type": r["role_type"],
                "started_at": r["started_at"],
                "ended_at": r["ended_at"],
            }
            for r in roles
        ],
        "risk_flags": risk_flags,
    }


@app.get("/companies/{company_id}", dependencies=[Depends(require_api_key)])
def get_company(company_id: uuid.UUID):
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, register_number, sector_description, status
            FROM companies WHERE id = %s
            """,
            [str(company_id)],
        )
        company = cur.fetchone()
        if company is None:
            raise HTTPException(status_code=404, detail="Company not found")

        cur.execute(
            """
            SELECT p.id, p.name, r.role_type
            FROM roles r
            JOIN people p ON p.id = r.person_id
            WHERE r.company_id = %s AND r.ended_at IS NULL
            """,
            [str(company_id)],
        )
        officers = cur.fetchall()

    return {
        "name": company["name"],
        "register_number": company["register_number"],
        "sector": company["sector_description"],
        "status": company["status"],
        "current_officers": [{"id": o["id"], "name": o["name"], "role_type": o["role_type"]} for o in officers],
    }


@app.get("/risk", dependencies=[Depends(require_api_key)])
def risk_dashboard():
    # Not one of the 3 endpoints in the design draft's API section, but the
    # risk dashboard screen (section 8) needs it — added to close that gap.
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT p.id, p.name, c.name AS company, c.id AS company_id
            FROM roles r
            JOIN people p ON p.id = r.person_id
            JOIN companies c ON c.id = r.company_id
            WHERE c.status = 'insolvent' AND r.ended_at IS NULL
            ORDER BY p.name
            """
        )
        rows = cur.fetchall()

    return {
        "people": [
            {"id": r["id"], "name": r["name"], "company": r["company"], "company_id": r["company_id"]}
            for r in rows
        ]
    }


@app.get("/search", dependencies=[Depends(require_api_key)])
def search(q: str):
    like = f"%{q}%"
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name FROM people WHERE name ILIKE %s LIMIT 20", [like])
        people = cur.fetchall()

        cur.execute("SELECT id, name FROM companies WHERE name ILIKE %s LIMIT 20", [like])
        companies = cur.fetchall()

    return {
        "people": [{"id": p["id"], "name": p["name"]} for p in people],
        "companies": [{"id": c["id"], "name": c["name"]} for c in companies],
    }
