"""
SQLAlchemy models.

Geo columns are plain Float (lat, lng) so the app runs on both SQLite and
PostgreSQL without changes. For production on Postgres you can layer a
PostGIS GEOGRAPHY column on top via Alembic — see database/schema.sql for
the target schema.
"""

from sqlalchemy import Column, Integer, String, Enum, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.core.database import Base


class UserRole(str, enum.Enum):
    USER = "USER"
    RIDER = "RIDER"


class BookingType(str, enum.Enum):
    RIDE = "RIDE"
    CAB = "CAB"
    PARCEL = "PARCEL"


class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    ONGOING = "ONGOING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    phone = Column(String)
    hashed_password = Column(String)
    role = Column(Enum(UserRole), default=UserRole.USER)

    # Profile fields
    gender = Column(String, nullable=True)           # "Male" or "Female"
    date_of_birth = Column(String, nullable=True)     # ISO date string "YYYY-MM-DD"
    member_since = Column(DateTime, default=datetime.utcnow)
    emergency_contact = Column(String, nullable=True)

    bookings = relationship(
        "Booking", back_populates="user", cascade="all, delete-orphan"
    )


class Driver(Base):
    __tablename__ = "drivers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String)
    vehicle_type = Column(String, nullable=False)
    vehicle_number = Column(String, unique=True, nullable=False)
    rating = Column(Float, default=5.0)
    status = Column(String, default="online")

    # Last known driver location (degrees, WGS84)
    current_lat = Column(Float, nullable=True)
    current_lng = Column(Float, nullable=True)

    bookings = relationship("Booking", back_populates="driver")


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

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="bookings")
    driver = relationship("Driver", back_populates="bookings")


class NotificationType(str, enum.Enum):
    DRIVER_ASSIGNED = "DRIVER_ASSIGNED"
    DRIVER_EN_ROUTE = "DRIVER_EN_ROUTE"
    DRIVER_ARRIVED = "DRIVER_ARRIVED"
    RIDE_STARTED = "RIDE_STARTED"
    RIDE_COMPLETED = "RIDE_COMPLETED"
    RIDE_CANCELLED = "RIDE_CANCELLED"
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
    GENERAL = "GENERAL"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    booking_id = Column(Integer, ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True)

    type = Column(Enum(NotificationType), default=NotificationType.GENERAL)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    is_read = Column(Integer, default=0)  # 0=unread, 1=read (SQLite-safe)

    # GPS wire: driver location at the time of notification.
    # The driver panel will populate these fields when it's built.
    # For now they remain NULL — ready for GPS connection.
    driver_lat = Column(Float, nullable=True)
    driver_lng = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    booking = relationship("Booking")


class SavedPlace(Base):
    __tablename__ = "saved_places"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label = Column(String, nullable=False)       # e.g. "Home", "Office", custom name
    address = Column(String, nullable=False)      # full address text
    icon = Column(String, default="location")     # icon name: home, briefcase, location, heart, star
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
