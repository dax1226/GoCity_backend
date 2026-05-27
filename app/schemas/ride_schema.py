"""Ride / booking / driver Pydantic schemas.

Drivers don't have their own dedicated CRUD endpoints yet, so their response
schema lives next to the ride schemas that embed it.
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.enums.ride_status import BookingType, BookingStatus
from app.schemas.user_schema import UserResponse


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
