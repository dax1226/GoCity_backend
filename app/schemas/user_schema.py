"""User-facing Pydantic schemas: auth, profile, saved places."""

from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

from app.models.user import UserRole


# ─────────────────────────────────────────────
# User auth
# ─────────────────────────────────────────────
class PhoneRequest(BaseModel):
    phone: str


class OTPVerifyRequest(BaseModel):
    phone: str
    otp: str


class ProfileSetupRequest(BaseModel):
    name: str
    role: UserRole


class UserResponse(BaseModel):
    id: int
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: str
    role: UserRole
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    member_since: Optional[datetime] = None
    emergency_contact: Optional[str] = None

    documents_verified: bool = False
    document_verification_status: Optional[str] = None
    requires_document_verification: bool = False

    profile_image: Optional[str] = None


    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    """Partial update — only non-None fields are written."""
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    emergency_contact: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse
    is_new_user: bool = False


# ─── Saved Places ────────────────────────────
class SavedPlaceCreate(BaseModel):
    label: str
    address: str
    icon: Optional[str] = "location"
    lat: Optional[float] = None
    lng: Optional[float] = None


class SavedPlaceResponse(BaseModel):
    id: int
    user_id: int
    label: str
    address: str
    icon: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True

class FCMTokenUpdate(BaseModel):
    fcm_token: str
