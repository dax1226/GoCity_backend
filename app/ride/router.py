"""Ride-lifecycle HTTP routes.

Placeholder — currently the only ride lifecycle endpoint is the PATCH
/{booking_id}/status route in app/booking/router.py. Once dedicated
start / pause / complete / live-track endpoints are needed, they live here.
"""

from fastapi import APIRouter

router = APIRouter()
