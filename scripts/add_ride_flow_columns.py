"""One-off migration for live tracking and ride-start OTP columns.

`Base.metadata.create_all()` creates new tables but does not ALTER existing
ones, so run this once after deploying the model changes.

Usage:
    cd GoCity_backend
    python -m scripts.add_ride_flow_columns
"""

from sqlalchemy import text

from app.core.database import active_database_url, engine


POSTGRES_COLUMNS = [
    ("driver_lat", "DOUBLE PRECISION"),
    ("driver_lng", "DOUBLE PRECISION"),
    ("driver_loc_updated_at", "TIMESTAMP"),
    # New ride codes are derived from booking id + this expiry timestamp. The
    # legacy ride_otp column remains only so older databases can roll forward
    # safely; new application code never writes plaintext OTPs to it.
    ("ride_otp", "VARCHAR(6)"),
    ("ride_otp_expires_at", "TIMESTAMP"),
    ("ride_otp_attempts_remaining", "INTEGER"),
    ("otp_released", "BOOLEAN DEFAULT FALSE"),
    ("otp_verified", "BOOLEAN DEFAULT FALSE"),
    ("started_at", "TIMESTAMP"),
]

SQLITE_TYPE_MAP = {
    "DOUBLE PRECISION": "REAL",
    "TIMESTAMP": "TIMESTAMP",
    "INTEGER": "INTEGER",
    "VARCHAR(6)": "VARCHAR(6)",
    "BOOLEAN DEFAULT FALSE": "BOOLEAN DEFAULT 0",
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

            col_type = SQLITE_TYPE_MAP[postgres_type] if is_sqlite else postgres_type
            conn.execute(text(f"ALTER TABLE bookings ADD COLUMN {name} {col_type}"))
            print(f"  + {name} {col_type}: added")

        # OTPs on terminal rides are never needed again. Removing these legacy
        # plaintext values is safe and keeps old history from retaining secrets.
        result = conn.execute(
            text(
                "UPDATE bookings SET ride_otp = NULL "
                "WHERE ride_otp IS NOT NULL "
                "AND (status IN ('COMPLETED', 'CANCELLED') OR otp_verified = TRUE)"
            )
        )
        if result.rowcount and result.rowcount > 0:
            print(f"  + cleared legacy OTPs from {result.rowcount} terminal booking(s)")

    print(f"\nDone against {active_database_url.split('@')[-1] or active_database_url}")


if __name__ == "__main__":
    main()
