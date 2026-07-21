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
  - GET  /api/bookings/nearest-drivers  -> closest drivers to a pickup point
                                          (Haversine — works on SQLite + Postgres)
  - PATCH /api/bookings/{id}/status     -> update booking status

The driver-matching helpers (_pick_driver, _ensure_seed_drivers, ...) and the
Haversine math are kept inline here for now; they are slated to move to
app/booking/service.py and app/utils/geo.py once the service layer migration
proceeds.
"""

import math
import random
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.user.service import get_current_user
from app.models.user import User, UserRole
from app.models.driver import Driver
from app.models.ride import Booking
from app.enums.ride_status import BookingType, BookingStatus
from app.booking.service import expire_stale_pending_bookings
from app.schemas.ride_schema import (
    RideBookingCreate,
    CabBookingCreate,
    ParcelBookingCreate,
    BookingResponse,
    DriverResponse,
    DriverLocationResponse,
    DatabaseSnapshot,
)
from app.services.otp import generate_otp
from app.utils.fare import PER_KM_RATE, fare_between_points, fare_for_distance
from app.load_assist import (
    PICKUP_TRUCK_CATEGORY,
    calculate_service_fare,
    validate_load_assist_payload,
)


router = APIRouter()

# Parcel slabs delivered by loading vehicles (tempo / truck / van / pickup) —
# the only parcels eligible for the loading/unloading add-on. Must stay in
# sync with _SMALL_PARCEL_SIZES in app/driver/router.py.
_LOAD_ASSIST_PARCEL_SIZES = ("large_package", "bulk_package")


def _process_load_assist(load_assist: Optional[dict], parcel_size: str) -> Optional[dict]:
    """Validate the loading/unloading add-on and return it with the service
    fare computed server-side. Returns None when the add-on is not selected."""
    if not isinstance(load_assist, dict) or load_assist.get("selected") is not True:
        return None

    if (parcel_size or "").lower() not in _LOAD_ASSIST_PARCEL_SIZES:
        raise HTTPException(
            status_code=400,
            detail="Loading/unloading service is available only for 5-10 KG and 10-20 KG parcels.",
        )

    # Heavy parcels are dispatched to loading vehicles (pickup trucks), which
    # is the vehicle category the add-on spec gates on.
    spec_payload = {"vehicleCategory": PICKUP_TRUCK_CATEGORY, "loadAssist": load_assist}
    validation = validate_load_assist_payload(spec_payload)
    if not validation.is_valid:
        raise HTTPException(status_code=400, detail="; ".join(validation.errors))

    breakdown = calculate_service_fare(spec_payload)
    return {**load_assist, "serviceFare": breakdown.service_fare}


# ─────────────────────────────────────────────
# Geo helpers — Haversine distance (km between two WGS84 points)
# ─────────────────────────────────────────────
_EARTH_RADIUS_KM = 6371.0


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km. Pure-Python so it works on SQLite,
    Postgres, MySQL — anything."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = rlat2 - rlat1
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# ─────────────────────────────────────────────
# Seed + driver matching
# ─────────────────────────────────────────────
SEED_DRIVERS = [
    # (name, phone, vehicle_type, vehicle_number, rating, lat, lng)
    ("Ramesh Kumar", "+91 98765 43210", "bike",  "KA01JK1234", 4.8, 12.9716, 77.5946),
    ("Suresh Rao",   "+91 98765 11111", "auto",  "KA03AB5678", 4.6, 12.9352, 77.6245),
    ("Vijay Singh",  "+91 98765 22222", "sedan", "KA05CD9012", 4.9, 12.9784, 77.6408),
    ("Anil Kumar",   "+91 98765 33333", "suv",   "KA02EF3456", 4.7, 12.9698, 77.7500),
    ("Praveen Das",  "+91 98765 44444", "mini",  "KA09GH7788", 4.5, 12.9279, 77.6271),
]


def _ensure_seed_drivers(db: Session) -> None:
    """Populate a few demo drivers if the table is empty so a booking can
    always be assigned a rider without manual setup."""
    if db.query(Driver).count() > 0:
        return

    db.add_all([
        Driver(
            name=n, phone=p, vehicle_type=vt, vehicle_number=vn,
            rating=r, status="online",
            current_lat=lat, current_lng=lng,
            documents_verified=True,
            document_verification_status="verified",
        )
        for (n, p, vt, vn, r, lat, lng) in SEED_DRIVERS
    ])
    db.commit()


def _pick_driver(
    db: Session,
    vehicle_type: Optional[str],
    pickup_lat: Optional[float] = None,
    pickup_lng: Optional[float] = None,
) -> Optional[Driver]:
    """Pick an online driver that matches the vehicle type, preferring the
    geographically nearest one when pickup coordinates are given. Drivers
    marked "on_trip" (mid-ride) are excluded so the same driver isn't assigned
    to two simultaneous bookings."""
    _ensure_seed_drivers(db)

    online_drivers = db.query(Driver).filter(
        Driver.status == "online",
        Driver.documents_verified.is_(True),
    ).all()
    if not online_drivers:
        return None

    # Loose vehicle-type match: "gobike" -> bike, "GoCity Mini" -> mini.
    if vehicle_type:
        vt = vehicle_type.lower()
        candidates = [
            d for d in online_drivers
            if d.vehicle_type.lower() in vt or vt in d.vehicle_type.lower()
        ]
        if not candidates:
            candidates = online_drivers
    else:
        candidates = online_drivers

    # Pick the geographically nearest driver if we have a pickup point.
    if pickup_lat is not None and pickup_lng is not None:
        located = [d for d in candidates if d.current_lat is not None and d.current_lng is not None]
        if located:
            return min(
                located,
                key=lambda d: _haversine_km(pickup_lat, pickup_lng, d.current_lat, d.current_lng),
            )

    return random.choice(candidates)


def _assign_driver_to_booking(db: Session, driver: Optional[Driver]) -> None:
    """Mark a driver as on-trip once they've been assigned to a booking."""
    if driver is not None:
        driver.status = "on_trip"


def _driver_dto(d: Driver) -> DriverResponse:
    return DriverResponse(
        id=d.id, name=d.name, phone=d.phone,
        vehicle_type=d.vehicle_type, vehicle_number=d.vehicle_number,
        rating=d.rating, status=d.status,
        current_lat=d.current_lat, current_lng=d.current_lng,
    )


def _to_response(booking: Booking) -> BookingResponse:
    driver_location = None
    if (
        booking.driver_lat is not None
        and booking.driver_lng is not None
        and booking.driver_loc_updated_at is not None
    ):
        driver_location = DriverLocationResponse(
            lat=booking.driver_lat,
            lng=booking.driver_lng,
            updated_at=booking.driver_loc_updated_at,
        )
    return BookingResponse(
        id=booking.id,
        booking_type=booking.booking_type,
        pickup_location=booking.pickup_location,
        drop_location=booking.drop_location,
        pickup_lat=booking.pickup_lat,
        pickup_lng=booking.pickup_lng,
        drop_lat=booking.drop_lat,
        drop_lng=booking.drop_lng,
        vehicle_type=booking.vehicle_type,
        fare=booking.fare,
        status=booking.status,
        payment_method=booking.payment_method,
        sender_name=booking.sender_name,
        receiver_name=booking.receiver_name,
        receiver_phone=booking.receiver_phone,
        parcel_size=booking.parcel_size,
        load_assist=booking.load_assist,
        created_at=booking.created_at,
        user=booking.user,
        driver=_driver_dto(booking.driver) if booking.driver else None,
        driver_location=driver_location,
        # Only reveal the OTP to the passenger once the driver has pressed
        # "Start Trip" (otp_released). Before that it stays hidden.
        ride_otp=booking.ride_otp if booking.otp_released else None,
        otp_released=booking.otp_released,
        otp_verified=booking.otp_verified,
        started_at=booking.started_at,
    )


# ─────────────────────────────────────────────
# Create endpoints
# ─────────────────────────────────────────────
@router.post("/ride", response_model=BookingResponse)
def create_ride_booking(
    payload: RideBookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = Booking(
        user_id=current_user.id,
        driver_id=None,
        booking_type=BookingType.RIDE,
        pickup_location=payload.pickup_location,
        drop_location=payload.drop_location,
        pickup_lat=payload.pickup_lat,
        pickup_lng=payload.pickup_lng,
        drop_lat=payload.drop_lat,
        drop_lng=payload.drop_lng,
        vehicle_type=payload.vehicle_type,
        fare=payload.fare,
        status=BookingStatus.PENDING,
        payment_method=payload.payment_method,
        ride_otp=generate_otp(),
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
    booking = Booking(
        user_id=current_user.id,
        driver_id=None,
        booking_type=BookingType.CAB,
        pickup_location=payload.pickup_location,
        drop_location=payload.drop_location,
        pickup_lat=payload.pickup_lat,
        pickup_lng=payload.pickup_lng,
        drop_lat=payload.drop_lat,
        drop_lng=payload.drop_lng,
        vehicle_type=payload.vehicle_type,
        fare=payload.fare,
        status=BookingStatus.PENDING,
        payment_method=payload.payment_method,
        ride_otp=generate_otp(),
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
    load_assist = _process_load_assist(payload.load_assist, payload.parcel_size)
    booking = Booking(
        user_id=current_user.id,
        driver_id=None,
        booking_type=BookingType.PARCEL,
        pickup_location=payload.pickup_location,
        drop_location=payload.drop_location,
        pickup_lat=payload.pickup_lat,
        pickup_lng=payload.pickup_lng,
        drop_lat=payload.drop_lat,
        drop_lng=payload.drop_lng,
        vehicle_type="parcel-bike",
        fare=payload.fare,
        status=BookingStatus.PENDING,
        payment_method=payload.payment_method,
        sender_name=payload.sender_name,
        receiver_name=payload.receiver_name,
        receiver_phone=payload.receiver_phone,
        parcel_size=payload.parcel_size,
        load_assist=load_assist,
        ride_otp=generate_otp(),
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return _to_response(booking)


# ─────────────────────────────────────────────
# Listing / query endpoints
# ─────────────────────────────────────────────
@router.get("/me", response_model=List[BookingResponse])
def list_my_bookings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Resolve the passenger's own stale request (if any) before listing, so a
    # forgotten "Searching for Rider" flips to "Cancelled" instead of hanging.
    expire_stale_pending_bookings(db)

    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.user), joinedload(Booking.driver))
        .filter(Booking.user_id == current_user.id)
        .order_by(Booking.created_at.desc())
        .all()
    )
    return [_to_response(b) for b in bookings]


@router.get("/fare-estimate")
def fare_estimate(
    pickup_lat: Optional[float] = Query(None, description="Pickup latitude"),
    pickup_lng: Optional[float] = Query(None, description="Pickup longitude"),
    drop_lat: Optional[float] = Query(None, description="Drop latitude"),
    drop_lng: Optional[float] = Query(None, description="Drop longitude"),
    distance_km: Optional[float] = Query(
        None, description="Trip distance in km (alternative to passing coordinates)"
    ),
):
    """Distance-based fare estimate at a flat ₹19/km.

    Pass either an explicit `distance_km`, or the pickup/drop coordinates and
    the great-circle distance is measured for you. Coordinates take precedence
    when both are supplied.
    """
    has_coords = None not in (pickup_lat, pickup_lng, drop_lat, drop_lng)
    if has_coords:
        return fare_between_points(pickup_lat, pickup_lng, drop_lat, drop_lng)

    if distance_km is None:
        raise HTTPException(
            status_code=400,
            detail="Provide distance_km, or all of pickup_lat/pickup_lng/drop_lat/drop_lng.",
        )

    return {
        "distance_km": round(max(0.0, distance_km), 2),
        "per_km_rate": PER_KM_RATE,
        "fare": fare_for_distance(distance_km),
    }


@router.get("/nearest-drivers", response_model=List[DriverResponse])
def nearest_drivers(
    lat: float = Query(..., description="Pickup latitude"),
    lng: float = Query(..., description="Pickup longitude"),
    radius_km: float = Query(5.0, description="Search radius in km"),
    limit: int = Query(10, description="Max drivers to return"),
    db: Session = Depends(get_db),
):
    """Return online drivers within `radius_km` of (lat, lng), sorted by
    Haversine distance. Works on SQLite and Postgres alike."""
    _ensure_seed_drivers(db)

    # Join with User table to select only real users registered with RIDER role
    online = (
        db.query(Driver)
        .join(User, Driver.phone == User.phone)
        .filter(
            User.role == UserRole.RIDER,
            Driver.status == "online",
            Driver.documents_verified.is_(True),
            Driver.current_lat.isnot(None),
            Driver.current_lng.isnot(None),
        )
        .all()
    )

    with_dist = [
        (d, _haversine_km(lat, lng, d.current_lat, d.current_lng))
        for d in online
    ]
    with_dist = [pair for pair in with_dist if pair[1] <= radius_km]
    with_dist.sort(key=lambda pair: pair[1])

    return [_driver_dto(d) for d, _ in with_dist[:limit]]


@router.get("/database", response_model=DatabaseSnapshot)
def database_snapshot(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Used by the in-app database viewer.

    Returns the rider and user records associated with every booking, plus
    the underlying users + drivers tables so the screen can render a
    spreadsheet-like dump of what is stored after a ride/cab/parcel booking.

    Auth required — this endpoint exposes PII (emails, phones, names) for
    every user and driver in the system. TODO: gate on an admin role once
    one exists; for now any authenticated user can read it.
    """
    users = db.query(User).order_by(User.id.asc()).all()
    drivers_raw = db.query(Driver).order_by(Driver.id.asc()).all()
    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.user), joinedload(Booking.driver))
        .order_by(Booking.created_at.desc())
        .all()
    )

    return DatabaseSnapshot(
        users=users,
        drivers=[_driver_dto(d) for d in drivers_raw],
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

    # Free the driver back to "online" when the ride ends so they can be
    # matched to new bookings.
    terminal_states = (BookingStatus.COMPLETED, BookingStatus.CANCELLED)
    if new_status in terminal_states and booking.driver is not None:
        booking.driver.status = "online"

    booking.status = new_status
    db.commit()
    db.refresh(booking)
    return _to_response(booking)


@router.delete("/{booking_id}", status_code=200)
def delete_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a booking permanently from the database.

    Only the booking owner can delete. If a driver was assigned,
    their status is freed back to 'online'.
    """
    booking = (
        db.query(Booking)
        .options(joinedload(Booking.driver))
        .filter(Booking.id == booking_id)
        .first()
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your booking")

    # Free the driver back to 'online' so they can take new rides
    if booking.driver is not None:
        booking.driver.status = "online"
        db.commit()

    db.delete(booking)
    db.commit()
    return {"ok": True, "deleted_id": booking_id}
