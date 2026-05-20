<<<<<<< HEAD
from sqlalchemy import Column, Integer, String, Enum, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.core.database import Base

=======
from sqlalchemy import Column, Integer, String, Enum
from app.core.database import Base
import enum
>>>>>>> 07f3a484d2d45324f75a9dd31819171e9e2f1ff1

class UserRole(str, enum.Enum):
    USER = "USER"
    RIDER = "RIDER"

<<<<<<< HEAD

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

=======
class User(Base):
    __tablename__ = "users"
    
>>>>>>> 07f3a484d2d45324f75a9dd31819171e9e2f1ff1
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String, unique=True, index=True)
    phone = Column(String)
    hashed_password = Column(String)
    role = Column(Enum(UserRole), default=UserRole.USER)
<<<<<<< HEAD

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

    bookings = relationship("Booking", back_populates="driver")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    driver_id = Column(Integer, ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True)

    booking_type = Column(Enum(BookingType), nullable=False)
    pickup_location = Column(String, nullable=False)
    drop_location = Column(String, nullable=False)
    vehicle_type = Column(String, nullable=True)
    fare = Column(Float, default=0.0)
    status = Column(Enum(BookingStatus), default=BookingStatus.PENDING)
    payment_method = Column(String, default="wallet")

    # parcel-only fields
    sender_name = Column(String, nullable=True)
    receiver_name = Column(String, nullable=True)
    receiver_phone = Column(String, nullable=True)
    parcel_size = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="bookings")
    driver = relationship("Driver", back_populates="bookings")
=======
>>>>>>> 07f3a484d2d45324f75a9dd31819171e9e2f1ff1
