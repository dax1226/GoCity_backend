"""Booking-domain service helpers.

Stub. The driver-matching logic (_pick_driver, _ensure_seed_drivers,
SEED_DRIVERS, _haversine_km) and the response shaping (_to_response,
_driver_dto) currently live in app/booking/router.py. They are slated to
move here so the router only handles HTTP wiring.

Cross-cutting dispatch logic that spans rider availability + ride state +
notifications belongs in app/services/dispatch_service.py instead.
"""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.enums.ride_status import BookingStatus
from app.models.ride import Booking

# A ride request that sits unaccepted for this long is treated as abandoned and
# auto-cancelled. It then stops being offered to drivers, and the passenger's
# "Searching for Rider" screen resolves to "Ride Cancelled".
PENDING_REQUEST_TTL_MINUTES = 2


def expire_stale_pending_bookings(db: Session) -> int:
    """Cancel PENDING bookings older than PENDING_REQUEST_TTL_MINUTES.

    Lazy expiry: called from the driver "available rides" poll and the passenger
    "my bookings" poll, so no background scheduler is needed. A single bulk
    UPDATE flips the stale rows; returns how many were expired."""
    cutoff = datetime.utcnow() - timedelta(minutes=PENDING_REQUEST_TTL_MINUTES)
    expired = (
        db.query(Booking)
        .filter(
            Booking.status == BookingStatus.PENDING,
            Booking.created_at < cutoff,
        )
        .update(
            {Booking.status: BookingStatus.CANCELLED},
            synchronize_session=False,
        )
    )
    if expired:
        db.commit()
    return expired
