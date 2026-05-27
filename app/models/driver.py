"""Driver ORM model.

Driver.status is intentionally a free-form String column for now — see
app/enums/driver_status.py for the values currently in use ("online" /
"on_trip"). Narrow to Enum(DriverStatus) once existing data is migrated.
"""

from sqlalchemy import Column, Integer, String, Float
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

    # Last known driver location (degrees, WGS84)
    current_lat = Column(Float, nullable=True)
    current_lng = Column(Float, nullable=True)

    bookings = relationship("Booking", back_populates="driver")
