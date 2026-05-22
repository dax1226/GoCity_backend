"""User-facing Pydantic schemas: auth, profile, saved places."""

from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

from app.models.user import UserRole


# ─────────────────────────────────────────────
# User auth
# ─────────────────────────────────────────────
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str
    password: str
    role: UserRole = UserRole.USER


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: Optional[str] = None
    role: UserRole
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    member_since: Optional[datetime] = None
    emergency_contact: Optional[str] = None

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    """Partial update — only non-None fields are written."""
    name: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    emergency_contact: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class LoginRequest(BaseModel):
    email: str
    password: str


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
