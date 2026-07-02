import math
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from uuid import uuid4


from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from fastapi import APIRouter, Depends, HTTPException, File, UploadFile

from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel

from app.core.database import get_db
from app.user.service import get_current_user
from app.models.user import User, UserRole
from app.models.driver import Driver
from app.models.ride import Booking, DriverRideRejection
from app.models.wallet import DriverCustomerRating, DriverWalletTransaction
from app.booking.service import expire_stale_pending_bookings
from app.enums.ride_status import BookingType, BookingStatus
from app.utils.cloudinary_upload import upload_image

router = APIRouter()

# ─── Geo Helpers ─────────────────────────────────────────────────────────────
_EARTH_RADIUS_KM = 6371.0
_UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads" / "driver_documents"
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
_DOCUMENT_EXTENSIONS = _IMAGE_EXTENSIONS | {".pdf"}
_VERIFICATION_REQUIRED_DETAIL = (
    "Driver documents must be verified before using the driver app."
)

# ─── Pickup workflow / wallet constants ──────────────────────────────────────
_ARRIVED_GEOFENCE_M = 200       # driver must be within this of pickup to tap ARRIVED
_PERFECT_PICKUP_RADIUS_M = 150  # "Perfect Pick-up" if ride starts inside this
_WAIT_GRACE_MINUTES = 3         # free waiting time after ARRIVED
_WAIT_CHARGE_PER_MIN = 2.0      # ₹/min after the grace period
_COMMISSION_RATE = 0.15         # GoCity commission on completed rides
_RATING_WINDOW_HOURS = 24       # driver can rate the customer up to 24h after drop
_IST_OFFSET = timedelta(hours=5, minutes=30)


def _ensure_driver_user(current_user: User) -> None:
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")


def _create_driver_profile(db: Session, current_user: User) -> Driver:
    driver = Driver(
        name=current_user.name or "Driver",
        phone=current_user.phone,
        vehicle_type="auto",
        vehicle_number="KA-01-MJ-" + str(random.randint(1000, 9999)),
        rating=5.0,
        status="offline",
        current_lat=12.9716,
        current_lng=77.5946,
        documents_verified=False,
        document_verification_status="pending",
    )
    db.add(driver)
    db.commit()
    db.refresh(driver)
    return driver


def _get_driver(
    db: Session,
    current_user: User,
    *,
    auto_create: bool = False,
    require_verified: bool = True,
) -> Driver:
    _ensure_driver_user(current_user)
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver and auto_create:
        driver = _create_driver_profile(db, current_user)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
    # TEMP: Automated document verification was removed (drivers only upload
    # documents for out-of-band admin review), so unverified drivers are NOT
    # blocked from using the driver app. Re-enable this gate once the admin
    # review/approval flow is in place.
    # if require_verified and not driver.documents_verified:
    #     raise HTTPException(status_code=403, detail=_VERIFICATION_REQUIRED_DETAIL)
    return driver


def _driver_profile_response(driver: Driver, current_user: User) -> dict:
    return {
        "id": driver.id,
        "user_id": current_user.id,
        "name": driver.name,
        "phone": driver.phone,
        "email": current_user.email or f"{current_user.id}@gocity.com",
        "vehicle_type": driver.vehicle_type,
        "vehicle_number": driver.vehicle_number,
        "vehicle_model": "Standard vehicle",
        "rating": driver.rating,
        "status": driver.status,
        "total_rides": len(driver.bookings),
        "member_since": current_user.member_since.isoformat() if current_user.member_since else datetime.utcnow().isoformat(),
        "profile_image": None,
        "documents_verified": bool(driver.documents_verified),
        "document_verification_status": driver.document_verification_status or "pending",
    }


def _upload_filename(filename: str | None, fallback_suffix: str) -> tuple[str, str]:
    suffix = Path(filename or "").suffix.lower() or fallback_suffix
    return suffix, f"{uuid4().hex}{suffix}"


async def _save_form_upload(
    upload: UploadFile | None,
    target_dir: Path,
    prefix: str,
    allowed_extensions: set[str],
) -> str:
    if upload is None:
        raise HTTPException(status_code=400, detail=f"{prefix} document is required")

    suffix, filename = _upload_filename(upload.filename, ".jpg")
    if suffix not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise HTTPException(
            status_code=400,
            detail=f"{prefix} must be one of: {allowed}",
        )

    content = await upload.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"{prefix} document is empty")

    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{prefix}_{filename}"
    target.write_bytes(content)
    return str(target)


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = rlat2 - rlat1
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# ─── Parcel dispatch eligibility ──────────────────────────────────────────────
# A parcel request is only offered to a driver whose registered vehicle is
# actually able to carry it:
#   - Loading vehicles (tempo / mini-truck / van / pickup) get every parcel size.
#   - Bikes, cars and autos (rickshaws) only get small parcels a person can
#     reasonably carry on those vehicles.
# Anything else does not receive parcel requests at all.
_LOADING_VEHICLE_KEYWORDS = (
    "loading", "truck", "tempo", "van", "pickup", "lorry", "carrier", "cargo",
)
_SMALL_PARCEL_VEHICLE_KEYWORDS = (
    "bike", "motorcycle", "scooter", "moped",
    "auto", "rickshaw", "rikshaw", "tuk",
    "car", "sedan", "suv", "mini", "hatchback",
)
# Parcel sizes light enough for a bike / car / auto (the 0-1 kg and 1-5 kg
# slabs). Heavier slabs (large_package / bulk_package) are loading-vehicle only.
_SMALL_PARCEL_SIZES = ("small_package", "medium_package")


def _is_loading_vehicle(vehicle_type: Optional[str]) -> bool:
    vt = (vehicle_type or "").lower()
    return any(k in vt for k in _LOADING_VEHICLE_KEYWORDS)


def _driver_can_carry_parcel(vehicle_type: Optional[str], parcel_size: Optional[str]) -> bool:
    """Whether a parcel booking should be offered to a driver with this vehicle.

    Loading vehicles are eligible for any parcel; bike/car/auto drivers only for
    small parcels."""
    if _is_loading_vehicle(vehicle_type):
        return True

    vt = (vehicle_type or "").lower()
    if any(k in vt for k in _SMALL_PARCEL_VEHICLE_KEYWORDS):
        return (parcel_size or "").lower() in _SMALL_PARCEL_SIZES

    return False


# ─── DTO Helpers ─────────────────────────────────────────────────────────────
def _to_booking_response(b: Booking, d: Driver):
    driver_location = None
    if (
        b.driver_lat is not None
        and b.driver_lng is not None
        and b.driver_loc_updated_at is not None
    ):
        driver_location = {
            "lat": b.driver_lat,
            "lng": b.driver_lng,
            "updated_at": b.driver_loc_updated_at.isoformat(),
        }

    return {
        "id": b.id,
        "booking_type": b.booking_type,
        "pickup_location": b.pickup_location,
        "drop_location": b.drop_location,
        "pickup_lat": b.pickup_lat,
        "pickup_lng": b.pickup_lng,
        "drop_lat": b.drop_lat,
        "drop_lng": b.drop_lng,
        "vehicle_type": b.vehicle_type,
        "fare": b.fare,
        "status": b.status,
        "payment_method": b.payment_method,
        "sender_name": b.sender_name,
        "receiver_name": b.receiver_name,
        "receiver_phone": b.receiver_phone,
        "parcel_size": b.parcel_size,
        "created_at": b.created_at.isoformat(),
        "user": {
            "id": b.user.id,
            "name": b.user.name,
            "email": b.user.email,
            "role": b.user.role,
        },
        "driver": {
            "id": d.id,
            "name": d.name,
            "phone": d.phone,
            "vehicle_type": d.vehicle_type,
            "vehicle_number": d.vehicle_number,
            "rating": d.rating,
            "status": d.status,
            "current_lat": d.current_lat,
            "current_lng": d.current_lng,
        } if d else None,
        "driver_location": driver_location,
        "ride_otp": b.ride_otp,
        "otp_released": b.otp_released,
        "otp_verified": b.otp_verified,
        "started_at": b.started_at.isoformat() if b.started_at else None,
        "arrived_at": b.arrived_at.isoformat() if b.arrived_at else None,
        "wait_charge_amount": b.wait_charge_amount or 0.0,
        "pickup_verified": bool(b.pickup_verified),
        "completed_at": b.completed_at.isoformat() if b.completed_at else None,
    }


# ─── Wallet ledger helpers ───────────────────────────────────────────────────
def _wallet_balance(db: Session, driver_id: int) -> float:
    last = (
        db.query(DriverWalletTransaction)
        .filter(DriverWalletTransaction.driver_id == driver_id)
        .order_by(DriverWalletTransaction.id.desc())
        .first()
    )
    return float(last.balance_after) if last else 0.0


def _add_wallet_transaction(
    db: Session,
    driver_id: int,
    txn_type: str,
    amount: float,
    booking_id: Optional[int] = None,
    description: Optional[str] = None,
) -> DriverWalletTransaction:
    """Append a ledger row (positive amount = credit, negative = debit).

    Does not commit — the caller commits together with its other changes."""
    balance = round(_wallet_balance(db, driver_id) + amount, 2)
    txn = DriverWalletTransaction(
        driver_id=driver_id,
        type=txn_type,
        amount=round(amount, 2),
        balance_after=balance,
        booking_id=booking_id,
        description=description,
    )
    db.add(txn)
    return txn


def _period_start_utc(period: str) -> Optional[datetime]:
    """UTC start of the requested IST-local period (today / week / month)."""
    ist_now = datetime.utcnow() + _IST_OFFSET
    ist_midnight = ist_now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period in ("today", "day"):
        start_ist = ist_midnight
    elif period == "week":
        start_ist = ist_midnight - timedelta(days=ist_now.weekday())
    elif period == "month":
        start_ist = ist_midnight.replace(day=1)
    else:
        return None
    return start_ist - _IST_OFFSET


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/profile")
def get_driver_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _get_driver(
        db,
        current_user,
        auto_create=True,
        require_verified=False,
    )
    return _driver_profile_response(driver, current_user)


class UpdateVehiclePayload(BaseModel):
    vehicle_number: Optional[str] = None
    vehicle_type: Optional[str] = None


@router.patch("/profile")
def update_driver_profile(
    payload: UpdateVehiclePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Let a driver edit their own vehicle info (number + type)."""
    driver = _get_driver(db, current_user, auto_create=True, require_verified=False)

    if payload.vehicle_number is not None:
        number = payload.vehicle_number.strip()
        if not number:
            raise HTTPException(status_code=400, detail="Vehicle number cannot be empty")
        driver.vehicle_number = number
    if payload.vehicle_type is not None:
        vtype = payload.vehicle_type.strip()
        if not vtype:
            raise HTTPException(status_code=400, detail="Vehicle type cannot be empty")
        driver.vehicle_type = vtype

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="That vehicle number is already registered.")
    db.refresh(driver)
    return _driver_profile_response(driver, current_user)


@router.post("/documents/upload")
async def upload_driver_documents(
    license_number: str = Form(...),
    license_image: UploadFile = File(...),
    pan_document: UploadFile = File(...),
    vehicle_document: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Store the driver's submitted documents (License, PAN, RC Book).

    Automated verification was removed — this only saves the uploaded files and
    marks the driver as "pending" for out-of-band admin review.
    """
    driver = _get_driver(
        db,
        current_user,
        auto_create=True,
        require_verified=False,
    )

    license_number = license_number.strip()
    if not license_number:
        raise HTTPException(status_code=400, detail="License number is required")

    target_dir = _UPLOAD_ROOT / f"driver_{driver.id}"
    license_path = await _save_form_upload(
        license_image,
        target_dir,
        "license",
        _IMAGE_EXTENSIONS,
    )
    pan_path = await _save_form_upload(
        pan_document,
        target_dir,
        "pan",
        _DOCUMENT_EXTENSIONS,
    )
    vehicle_path = await _save_form_upload(
        vehicle_document,
        target_dir,
        "vehicle",
        _DOCUMENT_EXTENSIONS,
    )

    driver.license_number = license_number
    driver.license_document_path = license_path
    driver.pan_document_path = pan_path
    driver.vehicle_document_path = vehicle_path
    driver.documents_submitted_at = datetime.utcnow()
    driver.documents_verified = False
    driver.document_verification_status = "pending"
    db.commit()
    db.refresh(driver)

    return {

        "documents_submitted": True,
        "document_verification_status": driver.document_verification_status,
        "message": "Documents uploaded. They are pending review.",

        "id": driver.id,
        "user_id": current_user.id,
        "name": driver.name,
        "phone": driver.phone,
        "email": current_user.email or f"{current_user.id}@gocity.com",
        "vehicle_type": driver.vehicle_type,
        "vehicle_number": driver.vehicle_number,
        "vehicle_model": "Standard vehicle",
        "rating": driver.rating,
        "status": driver.status,
        "total_rides": len(driver.bookings),
        "member_since": current_user.member_since.isoformat() if current_user.member_since else datetime.utcnow().isoformat(),
        "profile_image": driver.profile_image,
        "documents_verified": True

    }


@router.post("/me/profile-image")
def upload_driver_profile_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")
        
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
        
    contents = file.file.read()
    url = upload_image(contents, folder="gocity/drivers")
    if not url:
        raise HTTPException(status_code=500, detail="Failed to upload image to Cloudinary")
        
    driver.profile_image = url
    current_user.profile_image = url
    db.commit()
    db.refresh(driver)
    db.refresh(current_user)
    
    return {"status": "ok", "profile_image": url}


class GoOnlinePayload(BaseModel):
    lat: float
    lng: float

@router.post("/go-online")
def go_online(
    payload: GoOnlinePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _get_driver(db, current_user)

    driver.status = "online"
    driver.current_lat = payload.lat
    driver.current_lng = payload.lng
    db.commit()
    db.refresh(driver)
    return {"status": "online", "current_lat": driver.current_lat, "current_lng": driver.current_lng}


@router.post("/go-offline")
def go_offline(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _get_driver(db, current_user)

    driver.status = "offline"
    db.commit()
    return {"status": "offline"}


@router.get("/rides/available")
def get_available_rides(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _get_driver(db, current_user)

    # Auto-cancel requests that have been sitting unaccepted too long, so a
    # passenger's forgotten booking never lingers here as a "fresh" request.
    expire_stale_pending_bookings(db)

    # Bookings this driver has dismissed/cancelled are never offered again.
    rejected_ids = {
        row[0]
        for row in db.query(DriverRideRejection.booking_id).filter(
            DriverRideRejection.driver_id == driver.id
        )
    }

    # Query pending bookings created by real users
    bookings = db.query(Booking).options(joinedload(Booking.user)).filter(
        Booking.status == BookingStatus.PENDING
    ).all()

    response = []
    for b in bookings:
        if b.id in rejected_ids:
            continue
        # Parcel dispatch is vehicle-aware: only offer a parcel to a driver
        # whose registered vehicle can actually carry it (loading vehicle for
        # any size; bike/car/auto for small parcels only). Ride/cab requests
        # are unaffected and still shown to every online driver.
        if b.booking_type == BookingType.PARCEL and not _driver_can_carry_parcel(
            driver.vehicle_type, b.parcel_size
        ):
            continue

        dist = 5.0
        if b.pickup_lat and b.pickup_lng and b.drop_lat and b.drop_lng:
            dist = round(_haversine_km(b.pickup_lat, b.pickup_lng, b.drop_lat, b.drop_lng), 1)

        response.append({
            "booking_id": b.id,
            "booking_type": b.booking_type,
            "pickup_location": b.pickup_location,
            "drop_location": b.drop_location,
            "pickup_lat": b.pickup_lat,
            "pickup_lng": b.pickup_lng,
            "drop_lat": b.drop_lat,
            "drop_lng": b.drop_lng,
            "distance_km": dist,
            "estimated_fare": b.fare,
            "vehicle_type": b.vehicle_type or "auto",
            "parcel_size": b.parcel_size,
            "payment_method": b.payment_method,
            "passenger_name": b.user.name or "User",
            "passenger_rating": 4.9,
            "created_at": b.created_at.isoformat() + "Z"
        })
    return response


@router.post("/rides/{booking_id}/accept")
def accept_ride(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _get_driver(db, current_user)

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
        
    if booking.status != BookingStatus.PENDING:
        raise HTTPException(status_code=400, detail="Booking is not pending")
        
    booking.driver_id = driver.id
    booking.status = BookingStatus.ACCEPTED
    driver.status = "on_trip"
    db.commit()
    db.refresh(booking)
    db.refresh(driver)

    return _to_booking_response(booking, driver)


def _record_ride_rejection(db: Session, driver_id: int, booking_id: int) -> None:
    """Remember that this driver dismissed/cancelled this booking (idempotent).

    Uses INSERT ... ON CONFLICT DO NOTHING so two near-simultaneous rejects of
    the same booking (the app polls the request list and can fire duplicate
    taps) can't trip the uq_driver_booking_rejection unique constraint and 500.
    A SELECT-then-INSERT check races under concurrency; this is atomic in the DB.
    Does not commit — the caller commits together with its other changes."""
    stmt = (
        pg_insert(DriverRideRejection.__table__)
        .values(
            driver_id=driver_id,
            booking_id=booking_id,
            created_at=datetime.utcnow(),
        )
        .on_conflict_do_nothing(constraint="uq_driver_booking_rejection")
    )
    db.execute(stmt)


@router.post("/rides/{booking_id}/reject")
def reject_ride(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Driver dismissed an incoming ride request — never show it to them again.

    The booking stays PENDING and remains visible to every other driver."""
    driver = _get_driver(db, current_user)

    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    _record_ride_rejection(db, driver.id, booking.id)
    db.commit()
    return {"ok": True}


class ArrivedPayload(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None


@router.post("/rides/{booking_id}/arrived")
def arrive_at_pickup(
    booking_id: int,
    payload: Optional[ArrivedPayload] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Driver tapped ARRIVED at the pickup point.

    Geofenced: when both driver and pickup coordinates are known, the driver
    must be within the pickup zone. Sets arrived_at, which starts the
    3-minute wait-charge grace period. Idempotent — a second tap returns the
    booking unchanged."""
    driver = _get_driver(db, current_user)

    booking = db.query(Booking).options(joinedload(Booking.user)).filter(
        Booking.id == booking_id, Booking.driver_id == driver.id
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you")

    if booking.status != BookingStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Ride is not in ACCEPTED state")

    if booking.arrived_at:
        return _to_booking_response(booking, driver)

    lat = payload.lat if payload else None
    lng = payload.lng if payload else None
    if lat is None or lng is None:
        lat, lng = booking.driver_lat, booking.driver_lng

    if (
        lat is not None and lng is not None
        and booking.pickup_lat is not None and booking.pickup_lng is not None
    ):
        distance_m = _haversine_km(lat, lng, booking.pickup_lat, booking.pickup_lng) * 1000
        if distance_m > _ARRIVED_GEOFENCE_M:
            raise HTTPException(
                status_code=400,
                detail=f"You're not at the pickup zone yet ({int(distance_m)}m away).",
            )

    booking.arrived_at = datetime.utcnow()
    db.commit()
    db.refresh(booking)
    return _to_booking_response(booking, driver)


@router.post("/rides/{booking_id}/start")
def start_ride(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Driver pressed "Start Trip" — release the ride OTP to the passenger.

    This does NOT begin the ride. It only flips otp_released so the passenger's
    booking polling reveals the OTP. The passenger reads it back and the driver
    confirms it via /verify-otp, which is what actually moves the ride to
    ONGOING.
    """
    driver = _get_driver(db, current_user)

    booking = db.query(Booking).options(joinedload(Booking.user)).filter(
        Booking.id == booking_id, Booking.driver_id == driver.id
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you")

    if booking.status != BookingStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Ride is not in ACCEPTED state")

    if not booking.ride_otp:
        raise HTTPException(status_code=400, detail="Ride OTP is missing")

    booking.otp_released = True
    db.commit()
    db.refresh(booking)
    return _to_booking_response(booking, driver)


class CompleteRidePayload(BaseModel):
    final_fare: Optional[float] = None

@router.post("/rides/{booking_id}/complete")
def complete_ride(
    booking_id: int,
    payload: Optional[CompleteRidePayload] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _get_driver(db, current_user)

    booking = db.query(Booking).filter(Booking.id == booking_id, Booking.driver_id == driver.id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you")

    if booking.status == BookingStatus.COMPLETED:
        # Idempotent: a retry / double-tap of "Complete Trip" must not error
        # or write duplicate wallet ledger entries.
        return _to_booking_response(booking, driver)
    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Ride was cancelled and cannot be completed")

    if payload and payload.final_fare is not None:
        booking.fare = payload.final_fare
    # Wait charge (set at OTP verification) is collected on top of the fare.
    booking.fare = round((booking.fare or 0.0) + (booking.wait_charge_amount or 0.0), 2)

    booking.status = BookingStatus.COMPLETED
    booking.completed_at = datetime.utcnow()
    driver.status = "online"

    # Wallet ledger: cash fares stay with the driver, online fares are owed to
    # them (RIDE_CREDIT); GoCity commission is deducted either way.
    total = booking.fare or 0.0
    ride_label = f"{(booking.booking_type.value if booking.booking_type else 'ride').lower()} #{booking.id}"
    if (booking.payment_method or "").lower() != "cash":
        _add_wallet_transaction(
            db, driver.id, "RIDE_CREDIT", total, booking.id,
            f"Fare for {ride_label} ({booking.payment_method})",
        )
    commission = round(total * _COMMISSION_RATE, 2)
    if commission > 0:
        _add_wallet_transaction(
            db, driver.id, "ORDER_DEDUCTION", -commission, booking.id,
            f"GoCity commission ({int(_COMMISSION_RATE * 100)}%) on {ride_label}",
        )

    db.commit()
    db.refresh(booking)
    db.refresh(driver)
    return _to_booking_response(booking, driver)


class CancelRidePayload(BaseModel):
    reason: Optional[str] = None

@router.post("/rides/{booking_id}/cancel")
def cancel_ride(
    booking_id: int,
    payload: Optional[CancelRidePayload] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _get_driver(db, current_user)

    booking = db.query(Booking).filter(Booking.id == booking_id, Booking.driver_id == driver.id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you")
        
    booking.status = BookingStatus.CANCELLED
    driver.status = "online"
    # If this booking is ever re-queued (or the dispatch logic changes), the
    # driver who cancelled it must not be offered it again.
    _record_ride_rejection(db, driver.id, booking.id)
    db.commit()
    db.refresh(booking)
    db.refresh(driver)
    return _to_booking_response(booking, driver)


@router.get("/rides/current")
def get_current_ride(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _get_driver(db, current_user)

    booking = db.query(Booking).options(joinedload(Booking.user)).filter(
        Booking.driver_id == driver.id,
        Booking.status.in_([BookingStatus.ACCEPTED, BookingStatus.ONGOING])
    ).first()
    
    if not booking:
        return None
        
    return _to_booking_response(booking, driver)


@router.get("/rides/history")
def get_ride_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _get_driver(db, current_user)

    bookings = db.query(Booking).options(joinedload(Booking.user)).filter(
        Booking.driver_id == driver.id,
        Booking.status.in_([BookingStatus.COMPLETED, BookingStatus.CANCELLED])
    ).order_by(Booking.created_at.desc()).all()
    
    return [_to_booking_response(b, driver) for b in bookings]


class UpdateLocationPayload(BaseModel):
    lat: float
    lng: float

@router.post("/update-location")
def update_location(
    payload: UpdateLocationPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _get_driver(db, current_user)

    driver.current_lat = payload.lat
    driver.current_lng = payload.lng
    db.commit()
    return {"status": "ok"}


@router.post("/rides/{ride_id}/update-location")
def update_ride_location(
    ride_id: int,
    payload: UpdateLocationPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update driver location for a specific active ride.

    Writes to both the Driver row (so /bookings/me returns fresh
    driver.current_lat/lng for backward compat) and the Booking row
    (so driver_location is available in the BookingResponse).
    """
    driver = _get_driver(db, current_user)

    booking = db.query(Booking).filter(
        Booking.id == ride_id,
        Booking.driver_id == driver.id,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you")

    if booking.status not in (BookingStatus.ACCEPTED, BookingStatus.ONGOING):
        raise HTTPException(status_code=400, detail="Ride is not active")

    # Update the Driver row (backward compat — tracking.tsx reads driver.current_lat/lng)
    driver.current_lat = payload.lat
    driver.current_lng = payload.lng

    # Update the Booking row (new — driver_location in BookingResponse)
    booking.driver_lat = payload.lat
    booking.driver_lng = payload.lng
    booking.driver_loc_updated_at = datetime.utcnow()

    db.commit()
    return {"ok": True}


class VerifyOtpPayload(BaseModel):
    otp: str
    lat: Optional[float] = None
    lng: Optional[float] = None

@router.post("/rides/{ride_id}/verify-otp")
def verify_ride_otp(
    ride_id: int,
    payload: VerifyOtpPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify OTP to start a ride. OTP was generated at booking creation
    and shown to the user. Driver enters it to confirm pickup."""
    driver = _get_driver(db, current_user)

    booking = db.query(Booking).options(joinedload(Booking.user)).filter(
        Booking.id == ride_id,
        Booking.driver_id == driver.id,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you")

    if booking.status != BookingStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Ride is not in ACCEPTED state")

    if not booking.otp_released:
        raise HTTPException(status_code=400, detail="Press Start Trip to release the OTP first")

    if not booking.ride_otp:
        raise HTTPException(status_code=400, detail="Ride OTP is missing")

    if payload.otp.strip() != booking.ride_otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    now = datetime.utcnow()
    booking.otp_verified = True
    booking.status = BookingStatus.ONGOING
    booking.started_at = now

    # Wait charge: ₹2/min beyond the 3-minute grace period after ARRIVED.
    if booking.arrived_at:
        waited_min = (now - booking.arrived_at).total_seconds() / 60.0
        chargeable = max(0.0, waited_min - _WAIT_GRACE_MINUTES)
        booking.wait_charge_amount = round(chargeable * _WAIT_CHARGE_PER_MIN, 2)

    # Perfect Pick-up: ride started inside the pickup geofence. Uses the coords
    # sent with the OTP, falling back to the last pushed driver location.
    lat = payload.lat if payload.lat is not None else booking.driver_lat
    lng = payload.lng if payload.lng is not None else booking.driver_lng
    if (
        lat is not None and lng is not None
        and booking.pickup_lat is not None and booking.pickup_lng is not None
    ):
        distance_m = _haversine_km(lat, lng, booking.pickup_lat, booking.pickup_lng) * 1000
        booking.pickup_verified = distance_m <= _PERFECT_PICKUP_RADIUS_M

    db.commit()
    db.refresh(booking)
    return _to_booking_response(booking, driver)


class RateCustomerPayload(BaseModel):
    stars: int
    tags: Optional[List[str]] = None
    comment: Optional[str] = None


@router.post("/rides/{booking_id}/rate-customer")
def rate_customer(
    booking_id: int,
    payload: RateCustomerPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Driver rates the customer after a completed ride (1–5 stars + tags).

    One rating per ride, allowed up to 24 hours after completion."""
    driver = _get_driver(db, current_user)

    if not 1 <= payload.stars <= 5:
        raise HTTPException(status_code=400, detail="Stars must be between 1 and 5")

    booking = db.query(Booking).filter(
        Booking.id == booking_id, Booking.driver_id == driver.id
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you")

    if booking.status != BookingStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Ride is not completed yet")

    rated_from = booking.completed_at or booking.created_at
    if rated_from and datetime.utcnow() - rated_from > timedelta(hours=_RATING_WINDOW_HOURS):
        raise HTTPException(status_code=410, detail="The rating window for this ride has expired")

    existing = db.query(DriverCustomerRating).filter(
        DriverCustomerRating.booking_id == booking.id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="You already rated this customer")

    rating = DriverCustomerRating(
        booking_id=booking.id,
        driver_id=driver.id,
        user_id=booking.user_id,
        stars=payload.stars,
        tags=",".join(t.strip() for t in (payload.tags or []) if t.strip()) or None,
        comment=(payload.comment or "").strip() or None,
    )
    db.add(rating)
    db.commit()
    db.refresh(rating)
    return {"success": True, "rating_id": rating.id}


@router.get("/home-summary")
def get_home_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregated data for the driver homepage: greeting, today's earnings and
    completed/cancelled orders, rating, and wallet balance."""
    driver = _get_driver(db, current_user, auto_create=True, require_verified=False)

    ist_hour = (datetime.utcnow() + _IST_OFFSET).hour
    if ist_hour < 12:
        greeting = "Good Morning"
    elif ist_hour < 17:
        greeting = "Good Afternoon"
    else:
        greeting = "Good Evening"

    day_start = _period_start_utc("today")
    finished_today = db.query(Booking).filter(
        Booking.driver_id == driver.id,
        Booking.status.in_([BookingStatus.COMPLETED, BookingStatus.CANCELLED]),
        func.coalesce(Booking.completed_at, Booking.created_at) >= day_start,
    ).all()
    completed = [b for b in finished_today if b.status == BookingStatus.COMPLETED]

    return {
        "driver_name": driver.name,
        "greeting": greeting,
        "today_earnings": round(sum(b.fare or 0.0 for b in completed), 2),
        "today_orders": {
            "completed": len(completed),
            "cancelled": len(finished_today) - len(completed),
        },
        "rating": driver.rating,
        "wallet_balance": _wallet_balance(db, driver.id),
        "perfect_pickups_today": sum(1 for b in completed if b.pickup_verified),
    }


@router.get("/wallet/balance")
def get_wallet_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _get_driver(db, current_user, require_verified=False)
    return {"balance": _wallet_balance(db, driver.id), "currency": "INR"}


@router.get("/wallet/transactions")
def get_wallet_transactions(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _get_driver(db, current_user, require_verified=False)
    txns = (
        db.query(DriverWalletTransaction)
        .filter(DriverWalletTransaction.driver_id == driver.id)
        .order_by(DriverWalletTransaction.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [
        {
            "id": t.id,
            "type": t.type,
            "amount": t.amount,
            "balance_after": t.balance_after,
            "booking_id": t.booking_id,
            "description": t.description,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in txns
    ]


@router.get("/earnings/summary")
def get_earnings_summary(
    period: str = "today",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _get_driver(db, current_user)

    query = db.query(Booking).filter(
        Booking.driver_id == driver.id,
        Booking.status == BookingStatus.COMPLETED,
    )
    start = _period_start_utc(period)
    if start:
        query = query.filter(func.coalesce(Booking.completed_at, Booking.created_at) >= start)
    bookings = query.all()

    total_earnings = round(sum(b.fare or 0.0 for b in bookings), 2)
    total_rides = len(bookings)
    deductions = round(total_earnings * _COMMISSION_RATE, 2)
    net_earnings = round(total_earnings - deductions, 2)

    return {
        "period": period,
        "total_earnings": total_earnings,
        "total_rides": total_rides,
        "total_hours_online": 6.5,
        "average_rating": driver.rating,
        "tips": 0.0,
        "incentives": 0.0,
        "deductions": deductions,
        "net_earnings": net_earnings
    }


@router.get("/earnings/weekly")
def get_weekly_earnings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = _get_driver(db, current_user)

    bookings = db.query(Booking).filter(
        Booking.driver_id == driver.id,
        Booking.status == BookingStatus.COMPLETED
    ).all()
    
    total_earnings = sum(b.fare for b in bookings)
    total_rides = len(bookings)
    
    return {
        "week_start": datetime.utcnow().date().isoformat(),
        "week_end": datetime.utcnow().date().isoformat(),
        "daily_breakdown": [
            { "date": datetime.utcnow().date().isoformat(), "day": "Today", "earnings": total_earnings, "rides": total_rides, "hours": 6.5 }
        ],
        "total": total_earnings,
        "total_rides": total_rides
    }
