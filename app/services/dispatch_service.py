"""Dispatch service — orchestrates driver assignment, ride-state
transitions, and notification fan-out.

Placeholder. Today the booking router (app/booking/router.py) does this
inline: pick a driver, mark the booking ACCEPTED, flip the driver to
on_trip. As soon as that flow needs additional steps (push notifications,
WebSocket events, retries when no driver available), pull it together here
so each piece can be reasoned about and tested independently.
"""
