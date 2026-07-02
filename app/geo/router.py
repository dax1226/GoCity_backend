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
from app.core.redis_client import RedisUnavailable, ping
from app.geo import service as geo_service
from app.models.driver import Driver
from app.models.user import User
from app.user.service import get_current_user

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


async def _require_redis() -> None:
    if not await ping():
        raise HTTPException(
            status_code=503,
            detail=(
                "Driver location service (Redis) is unavailable. "
                "Start Redis and set REDIS_URL — see app/geo/README.md."
            ),
        )


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
    await _require_redis()
    # Remember the user's live location so the seed script can center fake
    # drivers on it (dev convenience only; see scripts/seed_fake_drivers.py).
    await geo_service.record_rider_query(lat, lng)
    return await geo_service.nearby(
        lat,
        lng,
        radius_km=radius_km,
        db_lookup=_driver_meta_lookup(db),
    )


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
    await _require_redis()

    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")

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
    except RedisUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"ok": True, "driverId": str(driver.id)}
