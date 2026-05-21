from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

from app.models import UserRole, BookingType, BookingStatus


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


# ─────────────────────────────────────────────
# Drivers / Riders
# ─────────────────────────────────────────────
class DriverResponse(BaseModel):
    id: int
    name: str
    phone: Optional[str] = None
    vehicle_type: str
    vehicle_number: str
    rating: float
    status: str
    current_lat: Optional[float] = None
    current_lng: Optional[float] = None

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# Booking create requests
# ─────────────────────────────────────────────
class RideBookingCreate(BaseModel):
    pickup_location: str
    drop_location: str
    vehicle_type: str
    fare: float = 0.0
    payment_method: str = "wallet"
    # PostGIS coordinates (optional; backend can geocode later if missing)
    pickup_lat: Optional[float] = None
    pickup_lng: Optional[float] = None
    drop_lat: Optional[float] = None
    drop_lng: Optional[float] = None


class CabBookingCreate(BaseModel):
    pickup_location: str
    drop_location: str
    vehicle_type: str
    fare: float = 0.0
    payment_method: str = "wallet"
    pickup_lat: Optional[float] = None
    pickup_lng: Optional[float] = None
    drop_lat: Optional[float] = None
    drop_lng: Optional[float] = None


class ParcelBookingCreate(BaseModel):
    pickup_location: str
    drop_location: str
    sender_name: str
    receiver_name: str
    receiver_phone: str
    parcel_size: str
    fare: float = 0.0
    payment_method: str = "wallet"
    pickup_lat: Optional[float] = None
    pickup_lng: Optional[float] = None
    drop_lat: Optional[float] = None
    drop_lng: Optional[float] = None


# ─────────────────────────────────────────────
# Booking response (used by /bookings & /database)
# ─────────────────────────────────────────────
class BookingResponse(BaseModel):
    id: int
    booking_type: BookingType
    pickup_location: str
    drop_location: str
    pickup_lat: Optional[float] = None
    pickup_lng: Optional[float] = None
    drop_lat: Optional[float] = None
    drop_lng: Optional[float] = None
    vehicle_type: Optional[str] = None
    fare: float
    status: BookingStatus
    payment_method: str
    sender_name: Optional[str] = None
    receiver_name: Optional[str] = None
    receiver_phone: Optional[str] = None
    parcel_size: Optional[str] = None
    created_at: datetime
    user: UserResponse
    driver: Optional[DriverResponse] = None

    class Config:
        from_attributes = True


class DatabaseSnapshot(BaseModel):
    users: List[UserResponse]
    drivers: List[DriverResponse]
    bookings: List[BookingResponse]


# ─────────────────────────────────────────────
# Notifications
# ─────────────────────────────────────────────
class NotificationResponse(BaseModel):
    id: int
    user_id: int
    booking_id: Optional[int] = None
    type: str
    title: str
    message: str
    is_read: int
    driver_lat: Optional[float] = None
    driver_lng: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationCreate(BaseModel):
    """Used internally or by driver panel in the future."""
    booking_id: Optional[int] = None
    type: str = "GENERAL"
    title: str
    message: str
    driver_lat: Optional[float] = None
    driver_lng: Optional[float] = None


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

