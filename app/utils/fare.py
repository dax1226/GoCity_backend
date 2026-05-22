"""Fare calculation helpers.

Placeholder. Today the frontend sends a precomputed `fare` value on every
booking request. When the backend needs authoritative fare computation
(base fare + per-km + per-minute + surge), the formula lives here so it
can be unit-tested without touching FastAPI.
"""
