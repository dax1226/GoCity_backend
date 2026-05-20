"""
Booking routes for GoCity.

Three booking surfaces, all backed by the single `bookings` table:
  - POST /api/bookings/ride     -> create a ride (bike/auto)
  - POST /api/bookings/cab      -> create a cab (mini/sedan/suv/premium)
  - POST /api/bookings/parcel   -> create a parcel delivery

Listing endpoints:
  - GET  /api/bookings/me               -> current user's bookings
  - GET  /api/bookings/database         -> users + drivers + bookings snapshot
                                          (used by the in-app database viewer)
  - PATCH /api/bookings/{id}/status     -> update booking status
"""

import random
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.user.auth import get_current_user
from app.models import (
    User,
    Driver,
    Booking,
    BookingType,
    BookingStatus,
)
from app.schemas import (
    RideBookingCreate,
    CabBookingCreate,
    ParcelBookingCreate,
    BookingResponse,
    DatabaseSnapshot,
)


router = APIRouter()


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def _ensure_seed_drivers(db: Session) -> None:
    """Populate a few demo drivers if the table is empty so a booking can
    always be assigned a rider without manual setup."""
    if db.query(Driver).count() > 0:
        return

    demo = [
        Driver(name="Ramesh Kumar", phone="+91 98765 43210",
               vehicle_type="bike",  vehicle_number="KA01JK1234",
               rating=4.8, status="online"),
        Driver(name="Suresh Rao",   phone="+91 98765 11111",
               vehicle_type="auto",  vehicle_number="KA03AB5678",
               rating=4.6, status="online"),
        Driver(name="Vijay Singh",  phone="+91 98765 22222",
               vehicle_type="sedan", vehicle_number="KA05CD9012",
               rating=4.9, status="online"),
        Driver(name="Anil Kumar",   phone="+91 98765 33333",
               vehicle_type="suv",   vehicle_number="KA02EF3456",
               rating=4.7, status="online"),
        Driver(name="Praveen Das",  phone="+91 98765 44444",
               vehicle_type="mini",  vehicle_number="KA09GH7788",
               rating=4.5, status="online"),
    ]
    db.add_all(demo)
    db.commit()


def _pick_driver(db: Session, vehicle_type: Optional[str]) -> Optional[Driver]:
    """Pick a driver that matches the vehicle type, falling back to any
    available driver so a booking always has a rider assigned."""
    _ensure_seed_drivers(db)

    all_drivers = db.query(Driver).all()
    if not all_drivers:
        return None

    if vehicle_type:
        vt = vehicle_type.lower()
        matched = [
            d for d in all_drivers
            if d.vehicle_type.lower() in vt or vt in d.vehicle_type.lower()
        ]
        if matched:
            return random.choice(matched)

    return random.choice(all_drivers)


def _to_response(booking: Booking) -> BookingResponse:
    return BookingResponse.model_validate(booking)


# ─────────────────────────────────────────────
# Create endpoints
# ─────────────────────────────────────────────
@router.post("/ride", response_model=BookingResponse)
def create_ride_booking(
    payload: RideBookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _pick_driver(db, payload.vehicle_type)

    booking = Booking(
        user_id=current_user.id,
        driver_id=driver.id if driver else None,
        booking_type=BookingType.RIDE,
        pickup_location=payload.pickup_location,
        drop_location=payload.drop_location,
        vehicle_type=payload.vehicle_type,
        fare=payload.fare,
        status=BookingStatus.ACCEPTED if driver else BookingStatus.PENDING,
        payment_method=payload.payment_method,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return _to_response(booking)


@router.post("/cab", response_model=BookingResponse)
def create_cab_booking(
    payload: CabBookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _pick_driver(db, payload.vehicle_type)

    booking = Booking(
        user_id=current_user.id,
        driver_id=driver.id if driver else None,
        booking_type=BookingType.CAB,
        pickup_location=payload.pickup_location,
        drop_location=payload.drop_location,
        vehicle_type=payload.vehicle_type,
        fare=payload.fare,
        status=BookingStatus.ACCEPTED if driver else BookingStatus.PENDING,
        payment_method=payload.payment_method,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return _to_response(booking)


@router.post("/parcel", response_model=BookingResponse)
def create_parcel_booking(
    payload: ParcelBookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Parcels usually go with a bike rider
    driver = _pick_driver(db, "bike")

    booking = Booking(
        user_id=current_user.id,
        driver_id=driver.id if driver else None,
        booking_type=BookingType.PARCEL,
        pickup_location=payload.pickup_location,
        drop_location=payload.drop_location,
        vehicle_type="parcel-bike",
        fare=payload.fare,
        status=BookingStatus.ACCEPTED if driver else BookingStatus.PENDING,
        payment_method=payload.payment_method,
        sender_name=payload.sender_name,
        receiver_name=payload.receiver_name,
        receiver_phone=payload.receiver_phone,
        parcel_size=payload.parcel_size,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return _to_response(booking)


# ─────────────────────────────────────────────
# Listing endpoints
# ─────────────────────────────────────────────
@router.get("/me", response_model=List[BookingResponse])
def list_my_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.user), joinedload(Booking.driver))
        .filter(Booking.user_id == current_user.id)
        .order_by(Booking.created_at.desc())
        .all()
    )
    return [_to_response(b) for b in bookings]


@router.get("/database", response_model=DatabaseSnapshot)
def database_snapshot(db: Session = Depends(get_db)):
    """Used by the in-app database viewer.

    Returns the rider and user records associated with every booking, plus
    the underlying users + drivers tables so the screen can render a
    spreadsheet-like dump of what is stored after a ride/cab/parcel booking.
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
        users=[u for u in users],
        drivers=[d for d in drivers],
        bookings=[_to_response(b) for b in bookings],
    )


@router.patch("/{booking_id}/status", response_model=BookingResponse)
def update_booking_status(
    booking_id: int,
    new_status: BookingStatus,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = (
        db.query(Booking)
        .options(joinedload(Booking.user), joinedload(Booking.driver))
        .filter(Booking.id == booking_id)
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    booking.status = new_status
    db.commit()
    db.refresh(booking)
    return _to_response(booking)
