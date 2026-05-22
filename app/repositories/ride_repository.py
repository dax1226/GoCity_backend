"""Ride / booking / driver persistence layer.

Stub. Candidates to migrate here from app/booking/router.py:
    - online drivers query (driver matching)
    - bookings-by-user listing
    - bookings + users + drivers snapshot for the database viewer

Keep distance math (Haversine) in app/utils/geo.py — repositories return
rows, not computed columns.
"""

from sqlalchemy.orm import Session  # noqa: F401

from app.models.ride import Booking  # noqa: F401
from app.models.driver import Driver  # noqa: F401
