"""Driver ORM model.

Driver.status is intentionally a free-form String column for now — see
app/enums/driver_status.py for the values currently in use ("online" /
"on_trip"). Narrow to Enum(DriverStatus) once existing data is migrated.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Float
from sqlalchemy.orm import relationship

from app.core.database import Base


class Driver(Base):
    __tablename__ = "drivers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String)
    vehicle_type = Column(String, nullable=False)
    vehicle_number = Column(String, unique=True, nullable=False)
    rating = Column(Float, default=5.0)
    status = Column(String, default="online")
    profile_image = Column(String, nullable=True)     # Cloudinary URL

    # Driver document uploads. New driver profiles default to "pending" until
    # the driver submits their documents; an admin reviews them out-of-band.
    # (Automated verification was removed — see documents upload endpoint.)
    documents_verified = Column(Boolean, default=False, nullable=False)
    document_verification_status = Column(String, default="pending", nullable=False)
    license_number = Column(String, nullable=True)
    license_document_path = Column(String, nullable=True)
    pan_document_path = Column(String, nullable=True)
    vehicle_document_path = Column(String, nullable=True)
    documents_submitted_at = Column(DateTime, nullable=True)

    # Last known driver location (degrees, WGS84)
    current_lat = Column(Float, nullable=True)
    current_lng = Column(Float, nullable=True)

    bookings = relationship("Booking", back_populates="driver")
