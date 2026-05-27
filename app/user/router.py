from fastapi import APIRouter, Depends, HTTPException
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

router = APIRouter()


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
        "user": db_user,
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
    return current_user


@router.get("/me", response_model=UserResponse)
def get_profile(current_user: User = Depends(get_current_user)):
    """Return the full profile for the currently logged-in user."""
    return current_user


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
    return current_user
