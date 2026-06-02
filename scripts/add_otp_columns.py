"""Add OTP columns to existing bookings table.

Usage:
    cd GoCity_backend
    python scripts/add_otp_columns.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "gocity.db")

def main():
    db_path = os.path.abspath(DB_PATH)
    if not os.path.exists(db_path):
        print(f"[OK] Database not found at {db_path} — columns will be created on next startup.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(bookings);")
    existing_cols = {row[1] for row in cursor.fetchall()}

    columns_to_add = [
        ("ride_otp", "VARCHAR(6)"),
        ("otp_verified", "BOOLEAN DEFAULT 0"),
    ]

    added = []
    for col_name, col_type in columns_to_add:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE bookings ADD COLUMN {col_name} {col_type};")
            added.append(col_name)
            print(f"  [+] Added column: {col_name} ({col_type})")
        else:
            print(f"  [=] Column already exists: {col_name}")

    conn.commit()
    conn.close()
    if added:
        print(f"\n[OK] Added {len(added)} column(s)")
    else:
        print(f"\n[OK] All columns already present")

if __name__ == "__main__":
    main()
