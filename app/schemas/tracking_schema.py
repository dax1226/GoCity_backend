"""Notification / tracking Pydantic schemas."""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


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
