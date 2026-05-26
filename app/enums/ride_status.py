"""Ride lifecycle and booking-type enums.

Moved here from app/models.py during the folder restructure so models,
schemas, and services can all reference the same source of truth.
"""

import enum


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
