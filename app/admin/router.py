"""Admin-panel endpoints (Next.js Go-city-admin).

Driver document verification flow:
  1. Driver signs in with OTP and uploads License / PAN / RC via the app
     (POST /api/driver/documents/upload) → status "submitted".
  2. Admin reviews the documents here (GET /drivers + the document file
     endpoint) and approves or rejects (POST /drivers/{id}/verification).
  3. Approval sets documents_verified=True → the driver app's verification
     gate (app/driver/router.py) unlocks and the driver can go online and earn.

TODO: the project has no admin auth/role yet, so these endpoints are
unauthenticated — same as the admin panel's existing expectations
(see Go-city-admin/utils/dataService.ts). Gate them once an admin role exists.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.driver import Driver
from app.models.ride import Booking
from app.models.user import User

router = APIRouter()

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}

_DOCUMENT_SLOTS = {
    "license": "license_document_path",
    "pan": "pan_document_path",
    "vehicle": "vehicle_document_path",
}


# ─── Serializers ─────────────────────────────────────────────────────────────
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
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "phone": u.phone,
        "role": u.role,
    }


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
    }


@router.get("/database")
def database_snapshot(db: Session = Depends(get_db)):
    """Unauthenticated snapshot of users / drivers / bookings consumed by the
    admin panel's Database Viewer (dataService.fetchLiveDatabase)."""
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
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "user": _live_user(b.user) if b.user else None,
                "driver": _live_driver(b.driver) if b.driver else None,
            }
            for b in bookings
        ],
    }
