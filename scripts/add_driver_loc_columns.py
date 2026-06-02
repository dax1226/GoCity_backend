"""One-off migration: add live driver-location columns to `bookings`.

The Booking model gained driver_lat / driver_lng / driver_loc_updated_at,
but the app only runs create_all() (which never ALTERs an existing table),
so the pre-existing Postgres `bookings` table is missing them.

Idempotent — safe to run more than once. Works on Postgres and SQLite.

    python -m scripts.add_driver_loc_columns
"""

from sqlalchemy import text

from app.core.database import engine, active_database_url


COLUMNS = [
    ("driver_lat", "DOUBLE PRECISION"),
    ("driver_lng", "DOUBLE PRECISION"),
    ("driver_loc_updated_at", "TIMESTAMP"),
]


def main() -> None:
    is_sqlite = active_database_url.startswith("sqlite")
    # SQLite has no DOUBLE PRECISION / IF NOT EXISTS on ADD COLUMN (older versions).
    col_type_map = {"DOUBLE PRECISION": "REAL", "TIMESTAMP": "TIMESTAMP"} if is_sqlite else {}

    with engine.begin() as conn:
        if is_sqlite:
            existing = {row[1] for row in conn.execute(text("PRAGMA table_info(bookings)"))}
        else:
            existing = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'bookings'"
                    )
                )
            }

        for name, col_type in COLUMNS:
            if name in existing:
                print(f"  - {name}: already present, skipping")
                continue
            sql_type = col_type_map.get(col_type, col_type)
            conn.execute(text(f"ALTER TABLE bookings ADD COLUMN {name} {sql_type}"))
            print(f"  + {name} {sql_type}: added")

    print(f"\nDone against {active_database_url.split('@')[-1] or active_database_url}")


if __name__ == "__main__":
    main()
