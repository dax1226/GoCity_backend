"""Tracking / notification ORM models.

Notifications carry the live driver lat/lng at the time they were emitted —
this is the "GPS wire" between the driver panel (future) and the rider app.
A live-tracking ride feed would also fit here once it's built; for now the
notification row is the only persistent tracking record.
"""

from sqlalchemy import Column, Integer, String, Enum, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

from app.core.database import Base


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
