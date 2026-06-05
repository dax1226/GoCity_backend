from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.user.service import get_current_user
from app.models.user import User, UserRole
from app.schemas import (
    PhoneRequest,
    OTPVerifyRequest,
    ProfileSetupRequest,
    UserResponse,
    UserProfileUpdate,
    Token,
)
from app.services.otp import generate_otp, send_otp, verify_otp
import re
from datetime import date, datetime
from app.utils.cloudinary_upload import upload_image

router = APIRouter()


def _serialize_user(user: User) -> dict:
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
def send_otp_endpoint(payload: PhoneRequest):
    """Generate and send an OTP to the user's phone number."""
    phone = _normalise_phone(payload.phone)
    otp = generate_otp()
    send_otp(phone, otp)
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
        "user": _serialize_user(db_user),
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
    return _serialize_user(current_user)


@router.get("/me", response_model=UserResponse)
def get_profile(current_user: User = Depends(get_current_user)):
    """Return the full profile for the currently logged-in user."""
    return _serialize_user(current_user)


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

    db.commit()
    db.refresh(current_user)
    return _serialize_user(current_user)


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
