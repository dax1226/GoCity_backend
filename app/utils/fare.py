"""Fare calculation helpers.

Authoritative, framework-free fare math so it can be unit-tested without
touching FastAPI. Today the frontend sends a precomputed `fare` on every
booking request; these helpers let the backend compute (or validate) a
distance-based fare on its own.

Current model: a flat distance rate of ₹19 per kilometre.
"""

from app.utils.geo import haversine_km

# Flat distance rate — Indian Rupees charged per kilometre travelled.
PER_KM_RATE = 19.0


def fare_for_distance(
    distance_km: float,
    *,
    per_km_rate: float = PER_KM_RATE,
    minimum_fare: float = 0.0,
) -> int:
    """Fare for a trip of `distance_km` kilometres at `per_km_rate` (₹/km).

    Negative distances are treated as zero. The result is clamped to
    `minimum_fare` and rounded to the nearest whole rupee.

    >>> fare_for_distance(10)      # 10 km * ₹19
    190
    >>> fare_for_distance(2.5)     # 2.5 km * ₹19 = 47.5 -> 48
    48
    """
    km = max(0.0, distance_km)
    fare = km * per_km_rate
    return round(max(fare, minimum_fare))


def fare_between_points(
    pickup_lat: float,
    pickup_lng: float,
    drop_lat: float,
    drop_lng: float,
    *,
    per_km_rate: float = PER_KM_RATE,
    minimum_fare: float = 0.0,
) -> dict:
    """Distance-based fare between two WGS84 coordinates.

    Measures the great-circle (Haversine) distance between pickup and drop,
    then prices it at `per_km_rate` ₹/km. Returns both the distance and the
    fare so callers can surface the breakdown.

    Returns a dict: ``{"distance_km": float, "per_km_rate": float, "fare": int}``.
    """
    distance_km = haversine_km(pickup_lat, pickup_lng, drop_lat, drop_lng)
    fare = fare_for_distance(
        distance_km,
        per_km_rate=per_km_rate,
        minimum_fare=minimum_fare,
    )
    return {
        "distance_km": round(distance_km, 2),
        "per_km_rate": per_km_rate,
        "fare": fare,
    }
