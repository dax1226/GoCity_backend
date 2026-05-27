"""Driver HTTP routes.

Placeholder — there are no driver-facing endpoints yet. The driver panel
(driver app) will land first, and routes for driver auth, location
heartbeat, trip lifecycle, and earnings will be added here.

Today, drivers are populated via the seed flow in app/booking/router.py
and read via /api/bookings/nearest-drivers.
"""

from fastapi import APIRouter

router = APIRouter()
