"""Tracking service — driver-location ingest and ride-progress fan-out.

Placeholder. The driver panel will eventually POST GPS updates here; this
module will persist them as notification rows (the existing "GPS wire" —
see app/models/tracking.py) and broadcast them over the WebSocket layer
(app/websocket/ride_tracking.py) to subscribed riders.
"""
