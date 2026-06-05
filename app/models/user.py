"""User and user-owned ORM models.

UserRole stays here rather than in app/enums because the structure only
calls for ride_status, payment_status, and driver_status enums — user roles
are tightly coupled to the User row and unlikely to grow.

SavedPlace is colocated with User since it is a strictly user-owned record
(one user → many places).
"""

from sqlalchemy import Column, Integer, String, Enum, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.core.database import Base


class UserRole(str, enum.Enum):
    USER = "USER"
    RIDER = "RIDER"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=True)
    email = Column(String, index=True, nullable=True)
    phone = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=True)
    role = Column(Enum(UserRole), default=UserRole.USER)

    # Profile fields
    gender = Column(String, nullable=True)           # "Male" or "Female"
    date_of_birth = Column(String, nullable=True)     # ISO date string "YYYY-MM-DD"
    member_since = Column(DateTime, default=datetime.utcnow)
    emergency_contact = Column(String, nullable=True)
    profile_image = Column(String, nullable=True)     # Cloudinary URL

    bookings = relationship(
        "Booking", back_populates="user", cascade="all, delete-orphan"
    )


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
