from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.core.security import create_access_token
from app.user.service import get_current_user
from app.models.driver import Driver
from app.models.ride import Booking, DriverRideRejection
from app.models.tracking import Notification
from app.models.user import SavedPlace, User, UserRole
from app.models.wallet import DriverCustomerRating, DriverWalletTransaction
from app.enums.ride_status import BookingStatus
from app.schemas import (
    PhoneRequest,
    OTPVerifyRequest,
    ProfileSetupRequest,
    UserResponse,
    UserProfileUpdate,
    Token,
)
from app.schemas.user_schema import FCMTokenUpdate
from app.services.otp import (
    OTPDeliveryError,
    OTPRateLimited,
    generate_otp,
    send_otp,
    verify_otp,
)
import re
from datetime import date, datetime
from app.utils.cloudinary_upload import upload_image

router = APIRouter()


def _driver_document_state(user: User, db: Session | None) -> dict:
    """Document-verification state for a driver (RIDER-role) account.

    Statuses: "pending" (documents not yet submitted), "submitted" (awaiting
    admin review), "verified" (approved — driver may take rides), "rejected"
    (admin rejected — driver must re-upload). The app's redirect guards keep
    the driver on the Driver Documents screen until an admin approves them.
    """
    if user.role != UserRole.RIDER:
        return {
            "documents_verified": True,
            "document_verification_status": "not_required",
            "requires_document_verification": False,
        }

    driver = None
    if db is not None:
        driver = db.query(Driver).filter(Driver.phone == user.phone).first()

    documents_verified = bool(driver and driver.documents_verified)
    status = (
        driver.document_verification_status
        if driver and driver.document_verification_status
        else "pending"
    )
    return {
        "documents_verified": documents_verified,
        "document_verification_status": status,
        "requires_document_verification": not documents_verified,
    }


def _serialize_user(user: User, db: Session | None = None) -> dict:
    """Return a JSON-serializable dict for a User suitable for response models.

    Ensures date/time fields are ISO strings so FastAPI/Pydantic validation passes.
    """
    user_dict = {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "gender": user.gender,
        "date_of_birth": None,
        "member_since": None,
        "emergency_contact": user.emergency_contact,

        **_driver_document_state(user, db),

        "profile_image": user.profile_image,

    }

    if getattr(user, "date_of_birth", None) is not None:
        dob = user.date_of_birth
        if isinstance(dob, date):
            user_dict["date_of_birth"] = dob.isoformat()
        else:
            user_dict["date_of_birth"] = str(dob)

    if getattr(user, "member_since", None) is not None:
        ms = user.member_since
        if isinstance(ms, datetime):
            user_dict["member_since"] = ms.isoformat()
        else:
            user_dict["member_since"] = str(ms)

    return user_dict


def _normalise_phone(raw: str) -> str:
    """Return E.164 phone (+91XXXXXXXXXX) or raise HTTPException."""
    phone = re.sub(r"[\s\-\(\)]+", "", raw.strip())
    if not phone:
        raise HTTPException(status_code=400, detail="Phone number is required")

    # Strip leading + to work with digits only
    digits = phone[1:] if phone.startswith("+") else phone

    # 91XXXXXXXXXX (12 digits) → strip country code
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]

    if len(digits) != 10 or not digits.isdigit():
        raise HTTPException(
            status_code=400,
            detail=f"Invalid phone number. Please enter a 10-digit number (e.g. 9876543210).",
        )
    return f"+91{digits}"


@router.post("/send-otp")
async def send_otp_endpoint(payload: PhoneRequest):
    """Generate and send an OTP to the user's phone number."""
    phone = _normalise_phone(payload.phone)
    otp = generate_otp()
    try:
        await send_otp(phone, otp)
    except OTPRateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail="Please wait before requesting another verification code.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except OTPDeliveryError as exc:
        # Do not expose provider details (or the OTP) to API clients.
        raise HTTPException(
            status_code=503,
            detail="Verification SMS is temporarily unavailable. Please try again.",
        ) from exc
    return {"message": "OTP sent successfully"}


@router.post("/verify-otp", response_model=Token)
def verify_otp_endpoint(payload: OTPVerifyRequest, db: Session = Depends(get_db)):
    """Verify the OTP. Creates a new user if the phone is not registered."""
    phone = _normalise_phone(payload.phone)
    otp = payload.otp.strip()
    
    if not verify_otp(phone, otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    # Look up existing user
    db_user = db.query(User).filter(User.phone == phone).first()
    is_new_user = False

    if not db_user:
        # Create a stub user. The user will set their name/role in profile setup.
        db_user = User(
            phone=phone,
            role=UserRole.USER,  # Default role, updated in setup-profile if needed
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        is_new_user = True

    access_token = create_access_token(data={"sub": str(db_user.id)})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": _serialize_user(db_user, db),
        "is_new_user": is_new_user,
    }


@router.post("/setup-profile", response_model=UserResponse)
def setup_profile_endpoint(
    payload: ProfileSetupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Complete profile setup for new users (set name and role)."""
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Name cannot be empty")
        
    current_user.name = payload.name.strip()
    current_user.role = payload.role
    db.commit()
    db.refresh(current_user)
    return _serialize_user(current_user, db)


@router.get("/me", response_model=UserResponse)
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the full profile for the currently logged-in user."""
    return _serialize_user(current_user, db)


@router.patch("/me", response_model=UserResponse)
def update_profile(
    payload: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update profile fields. Only non-None fields in the payload are written."""
    update_data = payload.model_dump(exclude_none=True)
    
    # Don't allow changing phone here since it's the primary ID
    if "phone" in update_data:
        update_data.pop("phone")
        
    for field, value in update_data.items():
        setattr(current_user, field, value)

    try:
        db.commit()
    except IntegrityError:
        # users.email is UNIQUE — a foreseeable conflict (the address belongs to
        # another account) must be a clean 400, not a 500 crash.
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="This email is already registered to another account.",
        )
    db.refresh(current_user)

    return _serialize_user(current_user, db)


@router.delete("/me")
def delete_account(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Permanently delete the authenticated account and its personal data.

    An active booking must be completed or cancelled first. This avoids
    orphaning an in-progress ride for either the customer or driver. Completed
    history, saved places, notifications, ratings, and an optional driver
    profile/ledger are removed in one database transaction.
    """
    active_statuses = (
        BookingStatus.PENDING,
        BookingStatus.ACCEPTED,
        BookingStatus.ONGOING,
    )
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()

    own_active_booking = (
        db.query(Booking.id)
        .filter(
            Booking.user_id == current_user.id,
            Booking.status.in_(active_statuses),
        )
        .first()
    )
    driver_active_booking = None
    if driver is not None:
        driver_active_booking = (
            db.query(Booking.id)
            .filter(
                Booking.driver_id == driver.id,
                Booking.status.in_(active_statuses),
            )
            .first()
        )

    if own_active_booking or driver_active_booking:
        raise HTTPException(
            status_code=409,
            detail="Cancel or complete your active ride before deleting this account.",
        )

    owned_booking_ids = [
        booking_id
        for (booking_id,) in db.query(Booking.id)
        .filter(Booking.user_id == current_user.id)
        .all()
    ]

    try:
        # Records owned directly by the user.
        db.query(Notification).filter(Notification.user_id == current_user.id).delete(
            synchronize_session=False,
        )
        db.query(SavedPlace).filter(SavedPlace.user_id == current_user.id).delete(
            synchronize_session=False,
        )
        db.query(DriverCustomerRating).filter(
            DriverCustomerRating.user_id == current_user.id,
        ).delete(synchronize_session=False)

        if owned_booking_ids:
            # Preserve other users' notifications/ledger rows, but detach them
            # from the booking that is about to be deleted.
            db.query(Notification).filter(
                Notification.booking_id.in_(owned_booking_ids),
            ).update({Notification.booking_id: None}, synchronize_session=False)
            db.query(DriverWalletTransaction).filter(
                DriverWalletTransaction.booking_id.in_(owned_booking_ids),
            ).update({DriverWalletTransaction.booking_id: None}, synchronize_session=False)
            db.query(DriverCustomerRating).filter(
                DriverCustomerRating.booking_id.in_(owned_booking_ids),
            ).delete(synchronize_session=False)
            db.query(DriverRideRejection).filter(
                DriverRideRejection.booking_id.in_(owned_booking_ids),
            ).delete(synchronize_session=False)

        if driver is not None:
            # Driver accounts are linked to users by phone. Remove only the
            # driver's financial/profile records; another customer's completed
            # booking history remains, with the deleted driver detached.
            db.query(DriverRideRejection).filter(
                DriverRideRejection.driver_id == driver.id,
            ).delete(synchronize_session=False)
            db.query(DriverWalletTransaction).filter(
                DriverWalletTransaction.driver_id == driver.id,
            ).delete(synchronize_session=False)
            db.query(DriverCustomerRating).filter(
                or_(
                    DriverCustomerRating.driver_id == driver.id,
                    DriverCustomerRating.user_id == current_user.id,
                ),
            ).delete(synchronize_session=False)
            db.query(Booking).filter(
                Booking.driver_id == driver.id,
                Booking.user_id != current_user.id,
            ).update(
                {
                    Booking.driver_id: None,
                    Booking.driver_lat: None,
                    Booking.driver_lng: None,
                    Booking.driver_loc_updated_at: None,
                },
                synchronize_session=False,
            )
            db.delete(driver)

        # Explicitly delete bookings rather than relying on database-specific
        # foreign-key cascade configuration (the app supports SQLite + Postgres).
        db.query(Booking).filter(Booking.user_id == current_user.id).delete(
            synchronize_session=False,
        )
        db.delete(current_user)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not delete the account. Please try again.")

    return {"message": "Account deleted"}


@router.post("/me/profile-image", response_model=UserResponse)
def upload_user_profile_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload and set the user's profile image."""
    contents = file.file.read()
    url = upload_image(contents, folder="gocity/users")
    if not url:
        raise HTTPException(status_code=500, detail="Failed to upload image to Cloudinary")
    
    current_user.profile_image = url
    from app.models.driver import Driver
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if driver:
        driver.profile_image = url
        
    db.commit()
    db.refresh(current_user)
    
    return _serialize_user(current_user)

@router.patch('/me/fcm-token')
def update_fcm_token(payload: FCMTokenUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    "Update the user FCM token for push notifications."
    current_user.fcm_token = payload.fcm_token
    db.commit()
    return {'message': 'FCM token updated successfully'}


@router.delete('/me/fcm-token')
def clear_fcm_token(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Invalidate the current device token during logout.

    The current schema supports one active token per user, so clearing it is
    safer than allowing a signed-out device to keep receiving notifications.
    """
    current_user.fcm_token = None
    db.commit()
    return {'message': 'FCM token cleared'}
