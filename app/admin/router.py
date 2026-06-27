"""Admin HTTP routes.

Read-only, cross-domain views for the in-app admin panel (the `app/admin`
screens in the Expo client). These endpoints are intentionally
**unauthenticated** for now: the admin panel is a local operator tool with
no login, and no admin-role system exists yet.

⚠️  Do NOT expose this service publicly without adding an admin auth gate —
    `/database` returns PII (names, emails, phones) for every user and driver.
    The auth-gated twin still lives at `GET /api/bookings/database`; this
    admin copy drops auth so the panel (which has no login) can read it.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.user import User
from app.models.driver import Driver
from app.models.ride import Booking
from app.schemas.ride_schema import DatabaseSnapshot

# Reuse the booking router's DTO builders so the admin snapshot stays
# byte-for-byte consistent with the rest of the app (OTP hiding, driver
# location shaping, etc.).
from app.booking.router import _to_response, _driver_dto

router = APIRouter()


@router.get("/database", response_model=DatabaseSnapshot)
def admin_database_snapshot(db: Session = Depends(get_db)):
    """Full snapshot of users, drivers and bookings for the admin Database Viewer.

    Returns every user, driver and booking (newest bookings first) so the
    panel can render a spreadsheet-like dump of what is stored after a
    ride / cab / parcel booking. Unauthenticated by design (local admin tool).
    """
    users = db.query(User).order_by(User.id.asc()).all()
    drivers = db.query(Driver).order_by(Driver.id.asc()).all()
    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.user), joinedload(Booking.driver))
        .order_by(Booking.created_at.desc())
        .all()
    )

    return DatabaseSnapshot(
        users=users,
        drivers=[_driver_dto(d) for d in drivers],
        bookings=[_to_response(b) for b in bookings],
    )
