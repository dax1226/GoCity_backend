"""Ride-lifecycle persistence layer (slice-local).

Stub. Reuses the Booking ORM (no separate `rides` table); when ride
events (start_at, end_at, route_polyline) are persisted as their own
columns or table, queries live here.
"""

from sqlalchemy.orm import Session  # noqa: F401

from app.models.ride import Booking  # noqa: F401
