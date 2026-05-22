"""Booking-domain persistence layer (slice-local).

Stub. Booking and Driver queries currently live inline in
app/booking/router.py. Migrate them here as the service layer fills out.
"""

from sqlalchemy.orm import Session  # noqa: F401

from app.models.ride import Booking  # noqa: F401
from app.models.driver import Driver  # noqa: F401
