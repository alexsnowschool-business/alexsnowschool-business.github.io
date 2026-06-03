"""Append one contact form submission to submissions.csv.

Called by the GitLab CI job. All fields come from environment variables
injected by the pipeline trigger (FORM_NAME, FORM_EMAIL, etc.).
"""

import csv
import os
from datetime import datetime, timezone
from pathlib import Path

FILE = Path(__file__).parent / "submissions.csv"
FIELDS = ["submitted_at", "name", "email", "who", "package", "message"]

row = {
    "submitted_at": os.environ.get("FORM_SUBMITTED_AT") or datetime.now(timezone.utc).isoformat(),
    "name":    os.environ.get("FORM_NAME", "").strip(),
    "email":   os.environ.get("FORM_EMAIL", "").strip(),
    "who":     os.environ.get("FORM_WHO", "").strip(),
    "package": os.environ.get("FORM_PACKAGE", "").strip(),
    "message": os.environ.get("FORM_MESSAGE", "").strip(),
}

write_header = not FILE.exists() or FILE.stat().st_size == 0

with FILE.open("a", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=FIELDS)
    if write_header:
        writer.writeheader()
    writer.writerow(row)

print(f"Stored: {row['name']} <{row['email']}> — package: {row['package']}")
