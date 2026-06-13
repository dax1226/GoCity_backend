"""One-off migration for the driver panel upgrade (pickup workflow columns).

`Base.metadata.create_all()` creates the new wallet/rating tables but does not
ALTER the existing bookings table, so run this once after deploying the model
changes.

Usage:
    cd GoCity_backend
    python -m scripts.add_driver_panel_columns
"""

from sqlalchemy import text

from app.core.database import active_database_url, engine


POSTGRES_COLUMNS = [
    ("arrived_at", "TIMESTAMP"),
    ("wait_charge_amount", "DOUBLE PRECISION DEFAULT 0"),
    ("pickup_verified", "BOOLEAN DEFAULT FALSE"),
    ("completed_at", "TIMESTAMP"),
]

SQLITE_TYPE_MAP = {
    "BOOLEAN DEFAULT FALSE": "BOOLEAN DEFAULT 0",
    "DOUBLE PRECISION DEFAULT 0": "REAL DEFAULT 0",
    "TIMESTAMP": "TIMESTAMP",
}


def _existing_columns(conn, is_sqlite: bool) -> set[str]:
    if is_sqlite:
        return {row[1] for row in conn.execute(text("PRAGMA table_info(bookings)"))}

    return {
        row[0]
        for row in conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'bookings'"
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
            conn.execute(text(f"ALTER TABLE bookings ADD COLUMN {name} {col_type}"))
            print(f"  + {name} {col_type}: added")

    print(f"\nDone against {active_database_url.split('@')[-1] or active_database_url}")


if __name__ == "__main__":
    main()
