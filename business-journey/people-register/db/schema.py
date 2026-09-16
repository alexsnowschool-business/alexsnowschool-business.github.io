"""Schema for the German people & company register (design draft section 5).

Applied via `manage_db.py init`. All statements are IF NOT EXISTS, so this is
safe to re-run.
"""

SCHEMA_STATEMENTS = [
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",

    # 5.1 Event log: source of truth, append-only, never edited or deleted.
    """
    CREATE TABLE IF NOT EXISTS events (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        type                TEXT NOT NULL CHECK (type IN (
                                'person_appointed',
                                'person_departed',
                                'company_insolvent'
                            )),
        source              TEXT NOT NULL CHECK (source IN (
                                'handelsregister',
                                'bundesanzeiger'
                            )),
        source_document_id  TEXT NOT NULL,
        occurred_at         DATE NOT NULL,
        ingested_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
        payload             JSONB NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_source_document ON events (source_document_id)",

    # 5.2 Graph store: a computed view, rebuildable from the event log.
    # Never hand-patch these tables directly; rebuild from events instead.
    """
    CREATE TABLE IF NOT EXISTS people (
        id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name                TEXT NOT NULL,
        date_of_birth       DATE,
        matched_confidence  REAL NOT NULL DEFAULT 1.0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS companies (
        id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name                  TEXT NOT NULL,
        register_number       TEXT NOT NULL UNIQUE,
        business_purpose_raw  TEXT,
        sector_code           TEXT,
        sector_description    TEXT,
        status                TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'insolvent'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roles (
        person_id   UUID NOT NULL REFERENCES people(id) ON DELETE CASCADE,
        company_id  UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        role_type   TEXT NOT NULL CHECK (role_type IN ('director', 'authorized_officer')),
        started_at  DATE NOT NULL,
        ended_at    DATE,
        PRIMARY KEY (person_id, company_id, role_type, started_at)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_roles_company ON roles (company_id)",
    "CREATE INDEX IF NOT EXISTS idx_people_name ON people (name)",
    "CREATE INDEX IF NOT EXISTS idx_companies_name ON companies (name)",
]
