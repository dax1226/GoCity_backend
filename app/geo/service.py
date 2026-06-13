"""Redis-backed driver geo index — the ride-hailing hot path.

Design (locations live ONLY in Redis, never Postgres):

  drivers:online            GEO set. member = driverId, score = (lng, lat).
  driver:{id}:alive         TTL marker, EX 10s. Heartbeats refresh it; once it
                            expires the driver is considered stale and dropped.
  driver:{id}:meta          HASH of lightweight profile fields (name, vehicle
                            type, rating) for fast callouts. On a cache miss we
                            fall back to Postgres ONCE and backfill the hash.
  drivers:moved             pub/sub channel; every heartbeat publishes the new
                            position so the WebSocket bridge can fan it out.

Postgres is touched only on a meta cache miss (profile data), never for
locations.
"""

from __future__ import annotations

import json
import math
from typing import Any, Callable, Optional

from app.core.redis_client import (
    DRIVERS_MOVED_CHANNEL,
    get_redis,
)

GEO_KEY = "drivers:online"
ALIVE_TTL_SECONDS = 10  # > heartbeat interval (~4s), so 1-2 misses tolerated
DEFAULT_RADIUS_KM = 3.0
DEFAULT_COUNT = 50
AVG_SPEED_KMH = 25.0  # for ETA estimation

# Most recent location a rider app queried /nearby with — i.e. the user's live
# phone GPS. Lets the seed script spawn fake drivers around the user's real
# location instead of a hard-coded city. TTL keeps it "live": it goes stale an
# hour after the app stops polling.
LAST_QUERY_KEY = "geo:last_rider_query"
LAST_QUERY_TTL_SECONDS = 3600


def _alive_key(driver_id: str) -> str:
    return f"driver:{driver_id}:alive"


def _meta_key(driver_id: str) -> str:
    return f"driver:{driver_id}:meta"


def _eta_min(distance_km: float) -> int:
    """Rough ETA in minutes from distance, assuming AVG_SPEED_KMH."""
    if distance_km <= 0:
        return 1
    return max(1, round(distance_km / AVG_SPEED_KMH * 60))


async def heartbeat(
    driver_id: str | int,
    lat: float,
    lng: float,
    *,
    meta: Optional[dict[str, Any]] = None,
) -> None:
    """Upsert a driver's live position and refresh their alive marker.

    Called every ~4s by the driver app. Runs as a single pipeline:
      GEOADD drivers:online <lng> <lat> <id>
      SET   driver:{id}:alive 1 EX 10
      HSET  driver:{id}:meta ...        (only if meta provided)
    Then publishes the move to ``drivers:moved``.
    """
    driver_id = str(driver_id)
    r = get_redis()

    pipe = r.pipeline(transaction=False)
    # NOTE: GEOADD argument order is (longitude, latitude) — easy to get wrong.
    pipe.geoadd(GEO_KEY, (lng, lat, driver_id))
    pipe.set(_alive_key(driver_id), "1", ex=ALIVE_TTL_SECONDS)
    if meta:
        pipe.hset(_meta_key(driver_id), mapping={k: str(v) for k, v in meta.items()})
    await pipe.execute()

    await r.publish(
        DRIVERS_MOVED_CHANNEL,
        json.dumps({"driverId": driver_id, "lat": lat, "lng": lng}),
    )


async def go_offline(driver_id: str | int) -> None:
    """Remove a driver from the live index (clean exit)."""
    driver_id = str(driver_id)
    r = get_redis()
    pipe = r.pipeline(transaction=False)
    pipe.zrem(GEO_KEY, driver_id)
    pipe.delete(_alive_key(driver_id))
    pipe.delete(_meta_key(driver_id))
    await pipe.execute()


async def record_rider_query(lat: float, lng: float) -> None:
    """Remember the location a rider app last queried /nearby with.

    Used only as a convenience signal for the seed script so it can center the
    fake fleet on the user's live phone location. Never read on the hot path.
    """
    await get_redis().set(
        LAST_QUERY_KEY,
        json.dumps({"lat": lat, "lng": lng}),
        ex=LAST_QUERY_TTL_SECONDS,
    )


async def get_last_rider_query() -> Optional[tuple[float, float]]:
    """Return the user's last-known live location (lat, lng), or None if stale."""
    raw = await get_redis().get(LAST_QUERY_KEY)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return float(data["lat"]), float(data["lng"])
    except (ValueError, KeyError, TypeError):
        return None


async def get_meta(
    driver_id: str,
    *,
    db_lookup: Optional[Callable[[str], Optional[dict[str, Any]]]] = None,
) -> dict[str, Any]:
    """Read cached profile meta; fall back to Postgres once on a miss.

    ``db_lookup`` is an optional callable (driverId -> dict | None) that hits
    Postgres. On a hash miss we call it, then backfill driver:{id}:meta so the
    next read stays on the hot path.
    """
    r = get_redis()
    meta = await r.hgetall(_meta_key(driver_id))
    if meta:
        return meta

    if db_lookup is not None:
        fetched = db_lookup(driver_id)
        if fetched:
            stringified = {k: str(v) for k, v in fetched.items()}
            await r.hset(_meta_key(driver_id), mapping=stringified)
            return stringified

    return {}


async def nearby(
    lat: float,
    lng: float,
    *,
    radius_km: float = DEFAULT_RADIUS_KM,
    count: int = DEFAULT_COUNT,
    db_lookup: Optional[Callable[[str], Optional[dict[str, Any]]]] = None,
) -> list[dict[str, Any]]:
    """Find live drivers within ``radius_km`` of (lat, lng), nearest first.

    GEOSEARCH drivers:online FROMLONLAT <lng> <lat> BYRADIUS <r> km ASC
              WITHCOORD WITHDIST COUNT <count>

    Then: drop any candidate whose alive marker has expired (stale), enrich the
    survivors with cached meta (Postgres fallback on miss), and shape the JSON.
    """
    r = get_redis()

    # redis-py returns [member, distance, [lng, lat]] per row with these flags.
    raw = await r.geosearch(
        GEO_KEY,
        longitude=lng,
        latitude=lat,
        radius=radius_km,
        unit="km",
        sort="ASC",
        count=count,
        withcoord=True,
        withdist=True,
    )
    if not raw:
        return []

    driver_ids = [row[0] for row in raw]

    # Liveness check: a member in the GEO set whose alive marker has expired is
    # stale (heartbeat stopped). Batch the EXISTS checks in one pipeline.
    alive_pipe = r.pipeline(transaction=False)
    for did in driver_ids:
        alive_pipe.exists(_alive_key(did))
    alive_flags = await alive_pipe.execute()

    results: list[dict[str, Any]] = []
    stale: list[str] = []

    for row, is_alive in zip(raw, alive_flags):
        driver_id, dist, coord = row[0], float(row[1]), row[2]
        if not is_alive:
            stale.append(driver_id)
            continue

        meta = await get_meta(driver_id, db_lookup=db_lookup)
        distance_km = round(dist, 2)
        rating_raw = meta.get("rating")
        results.append(
            {
                "driverId": driver_id,
                "lat": float(coord[1]),
                "lng": float(coord[0]),
                "distanceKm": distance_km,
                "etaMin": _eta_min(distance_km),
                "vehicleType": meta.get("vehicleType") or meta.get("vehicle_type"),
                "name": meta.get("name"),
                "rating": float(rating_raw) if rating_raw not in (None, "") else None,
            }
        )

    # Opportunistically evict stale members so the index self-heals.
    if stale:
        await r.zrem(GEO_KEY, *stale)

    # GEOSEARCH ASC already sorts by distance, but re-sort defensively.
    results.sort(key=lambda d: d["distanceKm"])
    return results
