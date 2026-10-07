"""
CLI used by .github/workflows/mark-completed.yml (a manual workflow_dispatch,
triggered from the GitHub Actions UI by pasting an episode title) to record
an episode as completed in data/completed.json.

This file is committed and fetched by the static site alongside
data/episodes.json, so "Completed" status syncs across devices/browsers
instead of living only in one browser's localStorage.

Run: uv run python scripts/mark_completed.py "<exact episode title>"
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

import build_episodes_json  # noqa: E402 -- reuse the same slugify() as the frontend ids

COMPLETED_FILE = BASE_DIR / "data" / "completed.json"


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print("Usage: mark_completed.py <exact episode title>", file=sys.stderr)
        sys.exit(1)

    title = sys.argv[1].strip()
    episode_id = build_episodes_json.slugify(title)

    completed = {}
    if COMPLETED_FILE.exists():
        completed = json.loads(COMPLETED_FILE.read_text(encoding="utf-8"))

    completed[episode_id] = {
        "title": title,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }

    COMPLETED_FILE.parent.mkdir(parents=True, exist_ok=True)
    COMPLETED_FILE.write_text(
        json.dumps(completed, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Marked '{title}' (id={episode_id}) as completed")


if __name__ == "__main__":
    main()
