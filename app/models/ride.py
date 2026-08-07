"""Ride / booking ORM model.

Geo columns are plain Float (lat, lng) so the app runs on both SQLite and
PostgreSQL without changes. For production on Postgres you can layer a
PostGIS GEOGRAPHY column on top via Alembic — see database/schema.sql for
the target schema.

The single Booking table backs three booking surfaces (RIDE / CAB / PARCEL)
distinguished by the booking_type enum.
"""

from sqlalchemy import Column, Integer, String, Enum, Float, DateTime, ForeignKey, Boolean, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime

from app.core.database import Base
from app.enums.ride_status import BookingType, BookingStatus


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    driver_id = Column(Integer, ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True)

    booking_type = Column(Enum(BookingType), nullable=False)
    pickup_location = Column(String, nullable=False)
    drop_location = Column(String, nullable=False)

    # Coordinates (degrees, WGS84). Distance queries use Haversine.
    pickup_lat = Column(Float, nullable=True)
    pickup_lng = Column(Float, nullable=True)
    drop_lat = Column(Float, nullable=True)
    drop_lng = Column(Float, nullable=True)

    vehicle_type = Column(String, nullable=True)
    fare = Column(Float, default=0.0)
    status = Column(Enum(BookingStatus), default=BookingStatus.PENDING)
    payment_method = Column(String, default="wallet")

    # Parcel-only fields
    sender_name = Column(String, nullable=True)
    receiver_name = Column(String, nullable=True)
    receiver_phone = Column(String, nullable=True)
    parcel_size = Column(String, nullable=True)
    # Loading/unloading add-on details for heavy (loading-vehicle) parcels.
    # Spec shape: {selected, serviceType, pickup{...}, drop{...}, goodsType,
    # itemCount, customerNotes, serviceFare} — see app/load_assist/service.py.
    load_assist = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Live driver location (updated by driver during ACCEPTED / ONGOING)
    driver_lat = Column(Float, nullable=True)
    driver_lng = Column(Float, nullable=True)
    driver_loc_updated_at = Column(DateTime, nullable=True)

    # OTP for trip start verification.
    # ``ride_otp`` is a legacy column retained only for a staged rollout. New
    # rows leave it NULL: a code is deterministically derived from booking id
    # + ``ride_otp_expires_at`` using a server secret, so plaintext OTPs never
    # land in the database.
    ride_otp = Column(String(6), nullable=True)
    ride_otp_expires_at = Column(DateTime, nullable=True)
    ride_otp_attempts_remaining = Column(Integer, nullable=True)
    otp_released = Column(Boolean, default=False)
    otp_verified = Column(Boolean, default=False)
    started_at = Column(DateTime, nullable=True)

    # Pickup workflow (driver panel). arrived_at is set when the driver taps
    # ARRIVED inside the pickup geofence; the 3-minute wait-charge grace period
    # is measured from it. pickup_verified records a "Perfect Pick-up" — the
    # ride was started within the pickup geofence.
    arrived_at = Column(DateTime, nullable=True)
    wait_charge_amount = Column(Float, default=0.0)
    pickup_verified = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="bookings")
    driver = relationship("Driver", back_populates="bookings")


class DriverRideRejection(Base):
    """A driver dismissed (or cancelled) this booking — never offer it to them
    again. Other drivers still see the booking in their available list."""

    __tablename__ = "driver_ride_rejections"
    __table_args__ = (
        UniqueConstraint("driver_id", "booking_id", name="uq_driver_booking_rejection"),
    )

    id = Column(Integer, primary_key=True, index=True)
    driver_id = Column(Integer, ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
