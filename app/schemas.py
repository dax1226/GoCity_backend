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

    class Config:
        from_attributes = True


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


class CabBookingCreate(BaseModel):
    pickup_location: str
    drop_location: str
    vehicle_type: str
    fare: float = 0.0
    payment_method: str = "wallet"


class ParcelBookingCreate(BaseModel):
    pickup_location: str
    drop_location: str
    sender_name: str
    receiver_name: str
    receiver_phone: str
    parcel_size: str
    fare: float = 0.0
    payment_method: str = "wallet"


# ─────────────────────────────────────────────
# Booking response (used by /bookings & /database)
# ─────────────────────────────────────────────
class BookingResponse(BaseModel):
    id: int
    booking_type: BookingType
    pickup_location: str
    drop_location: str
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
