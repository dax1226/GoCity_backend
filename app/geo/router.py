"""HTTP endpoints for the live driver geo index (Redis hot path).

Mounted at /api/drivers (see main.py):
  GET  /api/drivers/nearby?lat=&lng=   -> riders: list drivers within 3 km
  POST /api/drivers/heartbeat          -> driver app: upsert live position

All location reads/writes go through Redis (app/geo/service.py). Postgres is
touched only to backfill the profile-meta cache on a miss.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis_client import ping
from app.geo import service as geo_service
from app.models.driver import Driver
from app.models.user import User
from app.user.service import get_current_user
from app.utils.geo import haversine_km

router = APIRouter()


def _driver_meta_lookup(db: Session):
    """Build a (driverId -> meta dict | None) Postgres fallback for get_meta.

    Only invoked on a Redis meta cache miss. Returns the lightweight profile
    fields the callout needs; the service backfills driver:{id}:meta with these.
    """

    def lookup(driver_id: str) -> Optional[dict[str, Any]]:
        try:
            pk = int(driver_id)
        except (TypeError, ValueError):
            return None
        driver = db.query(Driver).filter(Driver.id == pk).first()
        if not driver:
            return None
        return {
            "name": driver.name or "Driver",
            "vehicleType": driver.vehicle_type or "auto",
            "rating": driver.rating if driver.rating is not None else 5.0,
        }

    return lookup


def _nearby_from_database(
    db: Session,
    lat: float,
    lng: float,
    radius_km: float,
) -> list[dict[str, Any]]:
    """Degraded-mode nearby lookup when the Redis geo index is unavailable.

    The driver heartbeat persists each location to the Driver row first, so
    riders can still discover online drivers during a Redis outage. This path
    is intentionally only a fallback; Redis remains the scalable hot path.
    """
    candidates = (
        db.query(Driver)
        .filter(
            Driver.status == "online",
            Driver.current_lat.isnot(None),
            Driver.current_lng.isnot(None),
        )
        .all()
    )

    nearby: list[dict[str, Any]] = []
    for driver in candidates:
        distance_km = haversine_km(lat, lng, driver.current_lat, driver.current_lng)
        if distance_km > radius_km:
            continue
        rounded_distance = round(distance_km, 2)
        nearby.append(
            {
                "driverId": str(driver.id),
                "lat": driver.current_lat,
                "lng": driver.current_lng,
                "distanceKm": rounded_distance,
                "etaMin": max(1, round(rounded_distance / 25 * 60)),
                "vehicleType": driver.vehicle_type,
                "name": driver.name,
                "rating": driver.rating,
            }
        )

    nearby.sort(key=lambda driver: driver["distanceKm"])
    return nearby


@router.get("/nearby")
async def get_nearby_drivers(
    lat: float = Query(..., ge=-90, le=90, description="Rider latitude"),
    lng: float = Query(..., ge=-180, le=180, description="Rider longitude"),
    radius_km: float = Query(3.0, gt=0, le=50, description="Search radius (km)"),
    db: Session = Depends(get_db),
):
    """Drivers within ``radius_km`` of (lat, lng), nearest first.

    Reads exclusively from Redis GEOSEARCH; filters out drivers whose alive
    marker expired; enriches survivors with cached meta (Postgres fallback on
    a miss). Public so the rider map can poll it without driver auth.
    """
    if await ping():
        try:
            # Remember the user's live location so the seed script can center
            # fake drivers on it (dev convenience only; see the seed script).
            await geo_service.record_rider_query(lat, lng)
            return await geo_service.nearby(
                lat,
                lng,
                radius_km=radius_km,
                db_lookup=_driver_meta_lookup(db),
            )
        except Exception:
            # A Redis connection can drop after its health check. Fall through
            # to the persisted locations instead of taking the rider map down.
            pass

    return _nearby_from_database(db, lat, lng, radius_km)


class HeartbeatPayload(BaseModel):
    lat: float
    lng: float


@router.post("/heartbeat")
async def driver_heartbeat(
    payload: HeartbeatPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Driver app heartbeat (~every 8s): upsert position + refresh alive TTL.

    Identity comes from the auth token, never the body. Profile meta is read
    from the Driver row and cached so /nearby callouts stay on the hot path.
    """
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")

    # Keep a durable last-known location before attempting Redis. It powers the
    # database fallback above and makes live sharing resilient to a Redis
    # outage, instead of silently discarding every driver heartbeat.
    driver.current_lat = payload.lat
    driver.current_lng = payload.lng
    db.commit()

    live_index_updated = False
    if await ping():
        try:
            await geo_service.heartbeat(
                driver.id,
                payload.lat,
                payload.lng,
                meta={
                    "name": driver.name or "Driver",
                    "vehicleType": driver.vehicle_type or "auto",
                    "rating": driver.rating if driver.rating is not None else 5.0,
                },
            )
            live_index_updated = True
        except Exception:
            # The persisted location above is still usable by /nearby.
            pass

    return {"ok": True, "driverId": str(driver.id), "liveIndexUpdated": live_index_updated}
