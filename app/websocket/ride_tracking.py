"""WebSocket channel: live ride tracking.

Placeholder. Subscribed clients (rider app) receive driver-location
updates and ride-state transitions for a specific booking.
Server-side, app/services/tracking_service.py ingests driver GPS pings
and pushes them to subscribers via the ConnectionManager in
app/core/websocket.py.
"""
