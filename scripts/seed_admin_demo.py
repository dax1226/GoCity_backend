"""Seed demo data for the in-app admin Database Viewer.

Populates a realistic spread of users, drivers and bookings (RIDE / CAB /
PARCEL across every status) so the admin panel has something meaningful to
show. Safe to re-run:

  * users   are matched on `phone`          (unique)  -> created if missing
  * drivers are matched on `vehicle_number` (unique)  -> created if missing
  * demo bookings are only created when fewer than DEMO_BOOKINGS exist, so
    repeated runs don't pile up duplicates.

Run from the backend root:
    venv/Scripts/python scripts/seed_admin_demo.py
"""

import os
import sys
from datetime import datetime, timedelta

# Make `app` importable when run as a script from the backend root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.models.driver import Driver  # noqa: E402
from app.models.ride import Booking  # noqa: E402
from app.enums.ride_status import BookingType, BookingStatus  # noqa: E402

DEMO_BOOKINGS = 8

DEMO_USERS = [
    dict(name="Aarav Sharma",   email="aarav.sharma@example.com",   phone="+919812300001", role=UserRole.USER,  gender="Male"),
    dict(name="Diya Mehta",     email="diya.mehta@example.com",     phone="+919812300002", role=UserRole.USER,  gender="Female"),
    dict(name="Kabir Nair",     email="kabir.nair@example.com",     phone="+919812300003", role=UserRole.USER,  gender="Male"),
    dict(name="Ananya Reddy",   email="ananya.reddy@example.com",   phone="+919812300004", role=UserRole.USER,  gender="Female"),
    dict(name="Rohan Gupta",    email="rohan.gupta@example.com",    phone="+919812300005", role=UserRole.RIDER, gender="Male"),
]

DEMO_DRIVERS = [
    dict(name="Imran Khan",     phone="+919870000011", vehicle_type="Auto",  vehicle_number="KA-01-AB-1101", rating=4.8, status="online",  current_lat=12.9716, current_lng=77.5946),
    dict(name="Suresh Patil",   phone="+919870000012", vehicle_type="Sedan", vehicle_number="KA-05-CD-2202", rating=4.6, status="on_trip", current_lat=12.9352, current_lng=77.6245),
    dict(name="Lakshmi Rao",    phone="+919870000013", vehicle_type="Bike",  vehicle_number="KA-03-EF-3303", rating=4.9, status="online",  current_lat=12.9784, current_lng=77.6408),
    dict(name="Vikram Singh",   phone="+919870000014", vehicle_type="SUV",   vehicle_number="KA-02-GH-4404", rating=4.4, status="offline", current_lat=None,     current_lng=None),
]

# (booking_type, status, pickup, drop, vehicle, fare, payment, driver_idx_or_None, parcel)
DEMO_TRIPS = [
    (BookingType.RIDE,   BookingStatus.COMPLETED, "Koramangala 5th Block", "Indiranagar Metro",      "Bike",  78.0,  "wallet", 2, None),
    (BookingType.RIDE,   BookingStatus.ONGOING,   "MG Road",               "Whitefield",             "Sedan", 320.0, "cash",   1, None),
    (BookingType.CAB,    BookingStatus.ACCEPTED,  "Kempegowda Airport T1",  "Hebbal Flyover",        "SUV",   640.0, "card",   3, None),
    (BookingType.CAB,    BookingStatus.PENDING,   "Jayanagar 4th Block",   "Electronic City Phase 1","Sedan", 410.0, "wallet", None, None),
    (BookingType.RIDE,   BookingStatus.CANCELLED, "HSR Layout Sector 2",   "BTM Layout",             "Auto",  95.0,  "wallet", None, None),
    (BookingType.PARCEL, BookingStatus.COMPLETED, "Marathahalli Bridge",   "Bellandur Gate",         None,    60.0,  "wallet", 1,
        dict(sender_name="Aarav Sharma", receiver_name="Neha Joshi", receiver_phone="+919900112233", parcel_size="Small")),
    (BookingType.PARCEL, BookingStatus.ACCEPTED,  "Banashankari 2nd Stage","Rajajinagar",            None,    120.0, "cash",   3,
        dict(sender_name="Diya Mehta",   receiver_name="Arjun Das",  receiver_phone="+919900445566", parcel_size="Medium")),
    (BookingType.CAB,    BookingStatus.COMPLETED, "Yelahanka New Town",    "Manyata Tech Park",      "SUV",   520.0, "card",   2, None),
]


def upsert_user(db, data):
    user = db.query(User).filter(User.phone == data["phone"]).first()
    if user:
        return user
    user = User(member_since=datetime.utcnow() - timedelta(days=30), **data)
    db.add(user)
    db.flush()
    return user


def upsert_driver(db, data):
    drv = db.query(Driver).filter(Driver.vehicle_number == data["vehicle_number"]).first()
    if drv:
        return drv
    drv = Driver(documents_verified=True, document_verification_status="verified", **data)
    db.add(drv)
    db.flush()
    return drv


def main():
    db = SessionLocal()
    try:
        users = [upsert_user(db, d) for d in DEMO_USERS]
        drivers = [upsert_driver(db, d) for d in DEMO_DRIVERS]
        db.commit()
        print(f"Users now: {db.query(User).count()} | Drivers now: {db.query(Driver).count()}")

        existing = db.query(Booking).count()
        if existing >= DEMO_BOOKINGS:
            print(f"Bookings already present ({existing}) — skipping demo bookings.")
            return

        now = datetime.utcnow()
        created = 0
        for i, (btype, status, pickup, drop, vehicle, fare, pay, drv_idx, parcel) in enumerate(DEMO_TRIPS):
            customer = users[i % len(users)]
            driver = drivers[drv_idx] if drv_idx is not None else None
            booking = Booking(
                user_id=customer.id,
                driver_id=driver.id if driver else None,
                booking_type=btype,
                status=status,
                pickup_location=pickup,
                drop_location=drop,
                vehicle_type=vehicle,
                fare=fare,
                payment_method=pay,
                created_at=now - timedelta(hours=i * 5 + 1),
                pickup_lat=12.9716, pickup_lng=77.5946,
                drop_lat=12.9352, drop_lng=77.6245,
            )
            if parcel:
                booking.sender_name = parcel["sender_name"]
                booking.receiver_name = parcel["receiver_name"]
                booking.receiver_phone = parcel["receiver_phone"]
                booking.parcel_size = parcel["parcel_size"]
            db.add(booking)
            created += 1

        db.commit()
        print(f"Created {created} demo bookings. Total bookings: {db.query(Booking).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
