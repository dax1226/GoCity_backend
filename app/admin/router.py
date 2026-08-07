"""Admin-panel endpoints (Next.js Go-city-admin).

Driver document verification flow:
  1. Driver signs in with OTP and uploads License / PAN / RC via the app
     (POST /api/driver/documents/upload) → status "submitted".
  2. Admin reviews the documents here (GET /drivers + the document file
     endpoint) and approves or rejects (POST /drivers/{id}/verification).
  3. Approval sets documents_verified=True → the driver app's verification
     gate (app/driver/router.py) unlocks and the driver can go online and earn.

Every endpoint is protected by the server-to-server ``ADMIN_API_KEY``. The
Next.js console keeps that secret in a Route Handler; it must never be exposed
to browser code as a ``NEXT_PUBLIC_*`` variable.
"""

import logging
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.admin_security import require_admin_api_key
from app.core.database import get_db
from app.models.driver import Driver
from app.models.ride import Booking
from app.models.user import User, UserRole

router = APIRouter(dependencies=[Depends(require_admin_api_key)])
LOGGER = logging.getLogger("gocity.admin")

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

_DOCUMENT_SLOTS = {
    "license": "license_document_path",
    "pan": "pan_document_path",
    "vehicle": "vehicle_document_path",
}


def _normalise_phone(raw: str) -> str:
    """Use the same E.164 India-only convention as the OTP sign-in endpoint."""
    phone = re.sub(r"[\s\-\(\)]+", "", raw.strip())
    if not phone:
        raise HTTPException(status_code=400, detail="Phone number is required")

    digits = phone[1:] if phone.startswith("+") else phone
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) != 10 or not digits.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Invalid phone number. Please enter a 10-digit number.",
        )
    return f"+91{digits}"


def _user_role_value(user: User) -> str:
    role = user.role
    return role.value if isinstance(role, UserRole) else str(role)


# ─── Serializers ─────────────────────────────────────────────────────────────
def _admin_user_dto(user: User) -> dict:
    """Admin-only user representation, including editable profile fields."""
    return {
        "id": user.id,
        "name": user.name or f"User {user.id}",
        "email": user.email or "",
        "phone": user.phone,
        "role": _user_role_value(user),
        "gender": user.gender,
        "date_of_birth": user.date_of_birth,
        "member_since": user.member_since.isoformat() if user.member_since else None,
        "emergency_contact": user.emergency_contact,
        "profile_image": user.profile_image,
    }


def _document_meta(driver: Driver, slot: str) -> dict:
    path = getattr(driver, _DOCUMENT_SLOTS[slot])
    uploaded = bool(path)
    return {
        "uploaded": uploaded,
        "is_image": Path(path).suffix.lower() in _IMAGE_EXTENSIONS if path else False,
        "url": f"/api/admin/drivers/{driver.id}/documents/{slot}" if uploaded else None,
    }


def _admin_driver_dto(driver: Driver, total_rides: int) -> dict:
    return {
        "id": driver.id,
        "name": driver.name,
        "phone": driver.phone,
        "vehicle_type": driver.vehicle_type,
        "vehicle_number": driver.vehicle_number,
        "rating": driver.rating,
        "status": driver.status,
        "current_lat": driver.current_lat,
        "current_lng": driver.current_lng,
        "profile_image": driver.profile_image,
        "documents_verified": bool(driver.documents_verified),
        "document_verification_status": driver.document_verification_status or "pending",
        "license_number": driver.license_number,
        "documents_submitted_at": (
            driver.documents_submitted_at.isoformat()
            if driver.documents_submitted_at
            else None
        ),
        "documents": {slot: _document_meta(driver, slot) for slot in _DOCUMENT_SLOTS},
        "total_rides": total_rides,
    }


def _ride_counts(db: Session) -> dict[int, int]:
    return dict(
        db.query(Booking.driver_id, func.count(Booking.id))
        .filter(Booking.driver_id.isnot(None))
        .group_by(Booking.driver_id)
        .all()
    )


# ─── Customer administration ─────────────────────────────────────────────────
class AdminUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=6, max_length=32)
    email: EmailStr | None = None


class AdminUserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=160)
    email: EmailStr | None = None
    gender: str | None = Field(default=None, max_length=32)
    date_of_birth: str | None = Field(default=None, max_length=32)
    emergency_contact: str | None = Field(default=None, max_length=32)


@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    """List customer accounts for the protected operations console."""
    users = db.query(User).order_by(User.id.asc()).all()
    return [_admin_user_dto(user) for user in users]


@router.post("/users", status_code=201)
def create_user(payload: AdminUserCreate, db: Session = Depends(get_db)):
    """Create a customer account without exposing any browser-side database path.

    The customer still signs in only through the OTP flow, which verifies that
    they control the phone number before they receive an access token.
    """
    phone = _normalise_phone(payload.phone)
    if db.query(User.id).filter(User.phone == phone).first():
        raise HTTPException(status_code=409, detail="A user with this phone number already exists")

    user = User(
        name=payload.name,
        phone=phone,
        email=str(payload.email) if payload.email else None,
        role=UserRole.USER,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create the user") from exc

    db.refresh(user)
    LOGGER.info("admin_user_created user_id=%s", user.id)
    return _admin_user_dto(user)


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
):
    """Update the small set of customer profile fields the console exposes."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No user fields were supplied")

    for field, value in updates.items():
        if field == "email" and value is not None:
            value = str(value)
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    LOGGER.info("admin_user_updated user_id=%s fields=%s", user.id, ",".join(sorted(updates)))
    return _admin_user_dto(user)


# ─── Driver administration ───────────────────────────────────────────────────
class AdminDriverCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=6, max_length=32)
    vehicle_type: str = Field(min_length=1, max_length=80)
    vehicle_number: str = Field(min_length=1, max_length=80)


class AdminDriverStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["offline", "online", "on_trip"]


@router.post("/drivers", status_code=201)
def create_driver(payload: AdminDriverCreate, db: Session = Depends(get_db)):
    """Register a driver profile and its linked rider account through FastAPI."""
    phone = _normalise_phone(payload.phone)
    vehicle_number = payload.vehicle_number.upper()

    if db.query(Driver.id).filter(Driver.phone == phone).first():
        raise HTTPException(status_code=409, detail="A driver with this phone number already exists")
    if db.query(Driver.id).filter(Driver.vehicle_number == vehicle_number).first():
        raise HTTPException(status_code=409, detail="A driver with this vehicle number already exists")

    linked_user = db.query(User).filter(User.phone == phone).first()
    if linked_user is None:
        linked_user = User(name=payload.name, phone=phone, role=UserRole.RIDER)
        db.add(linked_user)
    else:
        # The database currently has one role per account. This explicit admin
        # action is the only place we promote a verified phone owner to rider.
        linked_user.role = UserRole.RIDER

    driver = Driver(
        name=payload.name,
        phone=phone,
        vehicle_type=payload.vehicle_type,
        vehicle_number=vehicle_number,
        rating=5.0,
        status="offline",
        documents_verified=False,
        document_verification_status="pending",
    )
    db.add(driver)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not register the driver") from exc

    db.refresh(driver)
    LOGGER.info("admin_driver_created driver_id=%s", driver.id)
    return _admin_driver_dto(driver, total_rides=0)


@router.patch("/drivers/{driver_id}")
def update_driver_status(
    driver_id: int,
    payload: AdminDriverStatusUpdate,
    db: Session = Depends(get_db),
):
    """Set a driver's operational status, preserving the verification gate."""
    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")
    if payload.status == "online" and not driver.documents_verified:
        raise HTTPException(
            status_code=409,
            detail="Driver documents must be approved before going online",
        )

    driver.status = payload.status
    db.commit()
    db.refresh(driver)
    LOGGER.info("admin_driver_status_updated driver_id=%s status=%s", driver.id, driver.status)
    counts = _ride_counts(db)
    return _admin_driver_dto(driver, counts.get(driver.id, 0))


# ─── Driver document verification ────────────────────────────────────────────
@router.get("/drivers")
def list_drivers(db: Session = Depends(get_db)):
    """Every driver with their document-verification state, for the admin
    panel's Drivers page. Drivers awaiting review ("submitted") come first."""
    drivers = db.query(Driver).order_by(Driver.id.asc()).all()
    counts = _ride_counts(db)
    order = {"submitted": 0, "rejected": 1, "pending": 2, "verified": 3}
    drivers.sort(key=lambda d: order.get(d.document_verification_status or "pending", 2))
    return [_admin_driver_dto(d, counts.get(d.id, 0)) for d in drivers]


@router.get("/drivers/{driver_id}/documents/{slot}")
def get_driver_document(
    driver_id: int,
    slot: str,
    db: Session = Depends(get_db),
):
    """Serve an uploaded driver document (license / pan / vehicle) so the
    admin panel can display it for review."""
    if slot not in _DOCUMENT_SLOTS:
        raise HTTPException(status_code=404, detail="Unknown document type")

    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    path = getattr(driver, _DOCUMENT_SLOTS[slot])
    if not path or not Path(path).is_file():
        raise HTTPException(status_code=404, detail="Document not uploaded")

    return FileResponse(path)


class VerificationPayload(BaseModel):
    action: str  # "approve" | "reject"


@router.post("/drivers/{driver_id}/verification")
def set_driver_verification(
    driver_id: int,
    payload: VerificationPayload,
    db: Session = Depends(get_db),
):
    """Approve or reject a driver's submitted documents.

    Approve → documents_verified=True / status "verified": the driver can go
    online and take rides. Reject → status "rejected": the driver app shows
    the rejection and asks them to re-upload. Rejecting a previously verified
    driver also revokes their access (the driver-app gate re-engages)."""
    action = payload.action.strip().lower()
    if action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'approve' or 'reject'")

    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    if action == "approve":
        driver.documents_verified = True
        driver.document_verification_status = "verified"
    else:
        driver.documents_verified = False
        driver.document_verification_status = "rejected"
        # A revoked/rejected driver must not stay online taking rides.
        if driver.status == "online":
            driver.status = "offline"

    db.commit()
    db.refresh(driver)
    counts = _ride_counts(db)
    return _admin_driver_dto(driver, counts.get(driver.id, 0))


# ─── Live database snapshot (admin Database Viewer) ──────────────────────────
def _live_user(u: User) -> dict:
    return _admin_user_dto(u)


def _live_driver(d: Driver) -> dict:
    return {
        "id": d.id,
        "name": d.name,
        "phone": d.phone,
        "vehicle_type": d.vehicle_type,
        "vehicle_number": d.vehicle_number,
        "rating": d.rating,
        "status": d.status,
        "current_lat": d.current_lat,
        "current_lng": d.current_lng,
        "profile_image": d.profile_image,
        "documents_verified": bool(d.documents_verified),
        "document_verification_status": d.document_verification_status or "pending",
    }


@router.get("/database")
def database_snapshot(db: Session = Depends(get_db)):
    """Protected snapshot consumed by the admin Database Viewer."""
    users = db.query(User).order_by(User.id.asc()).all()
    drivers = db.query(Driver).order_by(Driver.id.asc()).all()
    bookings = (
        db.query(Booking)
        .options(joinedload(Booking.user), joinedload(Booking.driver))
        .order_by(Booking.created_at.desc())
        .all()
    )

    return {
        "users": [_live_user(u) for u in users],
        "drivers": [_live_driver(d) for d in drivers],
        "bookings": [
            {
                "id": b.id,
                "booking_type": b.booking_type,
                "pickup_location": b.pickup_location,
                "drop_location": b.drop_location,
                "vehicle_type": b.vehicle_type,
                "fare": b.fare,
                "status": b.status,
                "payment_method": b.payment_method,
                "sender_name": b.sender_name,
                "receiver_name": b.receiver_name,
                "receiver_phone": b.receiver_phone,
                "parcel_size": b.parcel_size,
                "created_at": b.created_at.isoformat() if b.created_at else "",
                "user": _live_user(b.user) if b.user else None,
                "driver": _live_driver(b.driver) if b.driver else None,
            }
            for b in bookings
        ],
    }
