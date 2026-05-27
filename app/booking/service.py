"""Booking-domain service helpers.

Stub. The driver-matching logic (_pick_driver, _ensure_seed_drivers,
SEED_DRIVERS, _haversine_km) and the response shaping (_to_response,
_driver_dto) currently live in app/booking/router.py. They are slated to
move here so the router only handles HTTP wiring.

Cross-cutting dispatch logic that spans rider availability + ride state +
notifications belongs in app/services/dispatch_service.py instead.
"""
