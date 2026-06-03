#!/usr/bin/env python3
"""Contact form submission API for Student Road to Germany.

Run from the repo root or studentroadtogermany/ directory:
    python3 studentroadtogermany/api.py

API endpoint:
    POST http://localhost:3002/api/contact   — store a form submission
    GET  http://localhost:3002/api/submissions — list all submissions (owner use)
"""

import json
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DB_PATH = Path(__file__).parent / "submissions.db"
PORT = 3002


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                submitted_at TEXT    NOT NULL,
                name         TEXT    NOT NULL,
                email        TEXT    NOT NULL,
                who          TEXT,
                package      TEXT,
                message      TEXT
            )
        """)
        conn.commit()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # noqa: N802
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {fmt % args}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):  # noqa: N802
        if self.path != "/api/contact":
            self._json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError):
            self._json(400, {"error": "invalid JSON"})
            return

        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip()

        if not name or not email:
            self._json(422, {"error": "name and email are required"})
            return

        submitted_at = datetime.now(timezone.utc).isoformat()
        with get_db() as conn:
            conn.execute(
                """INSERT INTO submissions
                       (submitted_at, name, email, who, package, message)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    submitted_at,
                    name,
                    email,
                    str(data.get("who", "")).strip(),
                    str(data.get("package", "")).strip(),
                    str(data.get("message", "")).strip(),
                ),
            )
            conn.commit()

        print(f"  Saved: {name} <{email}>")
        self._json(201, {"ok": True})

    def do_GET(self):  # noqa: N802
        if self.path != "/api/submissions":
            self._json(404, {"error": "not found"})
            return

        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM submissions ORDER BY submitted_at DESC"
            ).fetchall()

        self._json(200, {"submissions": [dict(r) for r in rows]})


if __name__ == "__main__":
    init_db()
    server = HTTPServer(("", PORT), Handler)
    print(f"Contact API  →  http://localhost:{PORT}/api/contact")
    print(f"Submissions  →  http://localhost:{PORT}/api/submissions")
    print(f"Database     →  {DB_PATH}")
    server.serve_forever()
