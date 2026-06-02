"""Add driver location columns to existing bookings table.

Run this script once after deploying the model changes to add the new
columns to an existing SQLite database without losing data.

Usage:
    cd GoCity_backend
    python scripts/add_driver_location_columns.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "gocity.db")

def main():
    db_path = os.path.abspath(DB_PATH)
    if not os.path.exists(db_path):
        print(f"[OK] Database not found at {db_path} — it will be created fresh with new columns on next startup.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check existing columns
    cursor.execute("PRAGMA table_info(bookings);")
    existing_cols = {row[1] for row in cursor.fetchall()}

    columns_to_add = [
        ("driver_lat", "FLOAT"),
        ("driver_lng", "FLOAT"),
        ("driver_loc_updated_at", "DATETIME"),
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
        print(f"\n[OK] Added {len(added)} column(s) to bookings table at {db_path}")
    else:
        print(f"\n[OK] All columns already present in {db_path}")

if __name__ == "__main__":
    main()
