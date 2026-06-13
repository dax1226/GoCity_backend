"""One-off migration for driver document verification columns.

`Base.metadata.create_all()` creates new tables but does not ALTER existing
ones, so run this once after deploying the model changes.

Usage:
    cd GoCity_backend
    python -m scripts.add_driver_document_columns
"""

from sqlalchemy import text

from app.core.database import active_database_url, engine


POSTGRES_COLUMNS = [
    ("documents_verified", "BOOLEAN DEFAULT FALSE"),
    ("document_verification_status", "VARCHAR(32) DEFAULT 'pending'"),
    ("license_number", "VARCHAR(64)"),
    ("license_document_path", "VARCHAR(512)"),
    ("pan_document_path", "VARCHAR(512)"),
    ("vehicle_document_path", "VARCHAR(512)"),
    ("documents_submitted_at", "TIMESTAMP"),
]

SQLITE_TYPE_MAP = {
    "BOOLEAN DEFAULT FALSE": "BOOLEAN DEFAULT 0",
    "DOUBLE PRECISION": "REAL",
    "TIMESTAMP": "TIMESTAMP",
}


def _existing_columns(conn, is_sqlite: bool) -> set[str]:
    if is_sqlite:
        return {row[1] for row in conn.execute(text("PRAGMA table_info(drivers)"))}

    return {
        row[0]
        for row in conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'drivers'"
            )
        )
    }


def main() -> None:
    is_sqlite = active_database_url.startswith("sqlite")

    with engine.begin() as conn:
        existing = _existing_columns(conn, is_sqlite)

        for name, postgres_type in POSTGRES_COLUMNS:
            if name in existing:
                print(f"  - {name}: already present")
                continue

            col_type = SQLITE_TYPE_MAP.get(postgres_type, postgres_type) if is_sqlite else postgres_type
            conn.execute(text(f"ALTER TABLE drivers ADD COLUMN {name} {col_type}"))
            print(f"  + {name} {col_type}: added")

    print(f"\nDone against {active_database_url.split('@')[-1] or active_database_url}")


if __name__ == "__main__":
    main()
