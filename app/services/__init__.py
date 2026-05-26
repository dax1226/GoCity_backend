"""Cross-cutting services that span multiple domains.

Per-domain logic (driver matching for booking, signature verification for
payment, ...) belongs in each slice's own service.py. This package is for
services that genuinely need to coordinate across slices — dispatch
(booking + driver + notification), payments (booking + wallet), tracking
(driver + ride + notification).
"""
