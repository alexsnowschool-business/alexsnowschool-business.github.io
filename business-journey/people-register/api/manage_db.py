"""DB schema management. Run inside the api container:

    docker compose run --rm api python manage_db.py init
"""

import sys

from database import get_connection
from db.schema import SCHEMA_STATEMENTS


def init():
    with get_connection() as conn, conn.cursor() as cur:
        for statement in SCHEMA_STATEMENTS:
            cur.execute(statement)
        conn.commit()
    print("Schema applied.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "init":
        print("Usage: python manage_db.py init")
        sys.exit(1)
    init()
