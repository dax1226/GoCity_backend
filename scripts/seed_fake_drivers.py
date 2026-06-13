"""Seed fake drivers into the Redis live geo index for local testing.

Pushes heartbeats straight through app/geo/service.py (the same path the real
driver app uses), so it exercises GEOADD + the alive-TTL markers + meta hash +
the drivers:moved pub/sub.

Layout: half the drivers are placed INSIDE the 3 km radius and half OUTSIDE, so
GET /api/drivers/nearby should return only the inside ones.

The fleet is centered on the USER'S LIVE LOCATION — the coordinates the rider
app most recently sent to GET /api/drivers/nearby (recorded in Redis under
geo:last_rider_query). So the workflow is:

    1. Open the app and go to the "Drivers near you" map. It starts polling
       /nearby with your real phone GPS, which the backend remembers.
    2. Run this script with no --center. It picks up that live location and
       drops the fake fleet around you.

Pass --center lat,lng to override (e.g. to test a specific spot).

Usage (from GoCity_backend/):
    # Auto-center on your live phone location (open the app's map first!).
    # Continuous heartbeats with jitter so markers visibly move. Ctrl-C to stop.
    python -m scripts.seed_fake_drivers

    # One shot: seed a single round of heartbeats, then exit.
    python -m scripts.seed_fake_drivers --once

    # Override the center explicitly and tune the fleet size.
    python -m scripts.seed_fake_drivers --center 23.0225,72.5714 --count 10

    # Demonstrate the "killed heartbeat" path: drivers 3 and 7 get ONE
    # heartbeat then are never refreshed, so they drop off within ~10s.
    python -m scripts.seed_fake_drivers --drop 3,7
"""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import sys

from app.core.redis_client import REDIS_URL, ping
from app.geo import service as geo_service

HEARTBEAT_INTERVAL_S = 4

VEHICLE_TYPES = ["auto", "bike", "car", "mini-truck"]
FIRST_NAMES = [
    "Ravi", "Anita", "Suresh", "Priya", "Imran", "Deepa",
    "Vijay", "Kavya", "Arjun", "Meera", "Rahul", "Sneha",
]


def _offset(lat: float, lng: float, north_km: float, east_km: float) -> tuple[float, float]:
    """Shift a lat/lng by a north/east distance in km (small-offset approx)."""
    dlat = north_km / 111.0
    dlng = east_km / (111.0 * math.cos(math.radians(lat)))
    return lat + dlat, lng + dlng


def build_fleet(center: tuple[float, float], count: int) -> list[dict]:
    """Half inside the 3 km radius, half outside — at varied bearings."""
    lat0, lng0 = center
    fleet: list[dict] = []
    inside = count // 2
    for i in range(count):
        # Inside: 0.4–2.6 km. Outside: 3.6–6.5 km.
        dist_km = random.uniform(0.4, 2.6) if i < inside else random.uniform(3.6, 6.5)
        bearing = random.uniform(0, 2 * math.pi)
        north = dist_km * math.cos(bearing)
        east = dist_km * math.sin(bearing)
        lat, lng = _offset(lat0, lng0, north, east)
        fleet.append(
            {
                "id": i + 1,
                "lat": lat,
                "lng": lng,
                "expected": "inside" if i < inside else "outside",
                "meta": {
                    "name": f"{random.choice(FIRST_NAMES)} (#{i + 1})",
                    "vehicleType": random.choice(VEHICLE_TYPES),
                    "rating": round(random.uniform(4.2, 5.0), 1),
                },
            }
        )
    return fleet


def _jitter(driver: dict) -> None:
    """Nudge a driver ~30 m so the live map shows movement between ticks."""
    driver["lat"], driver["lng"] = _offset(
        driver["lat"], driver["lng"],
        random.uniform(-0.03, 0.03),
        random.uniform(-0.03, 0.03),
    )


async def _beat(fleet: list[dict], skip: set[int]) -> None:
    for d in fleet:
        if d["id"] in skip:
            continue
        await geo_service.heartbeat(d["id"], d["lat"], d["lng"], meta=d["meta"])


async def run(args: argparse.Namespace) -> int:
    if not await ping():
        print(f"[seed] Redis unreachable at {REDIS_URL}.")
        print("[seed] Start Redis and/or fix REDIS_URL, then retry. See app/geo/README.md.")
        return 1

    if args.center:
        lat_s, lng_s = args.center.split(",")
        center = (float(lat_s), float(lng_s))
        print(f"[seed] using --center override {center}")
    else:
        center = await geo_service.get_last_rider_query()
        if center is None:
            print("[seed] No live user location found in Redis (geo:last_rider_query).")
            print("[seed] Open the app's 'Drivers near you' map first so it sends your")
            print("[seed] GPS to /api/drivers/nearby — or pass --center lat,lng explicitly.")
            return 1
        print(f"[seed] using live user location from the app {center}")

    drop = {int(x) for x in args.drop.split(",")} if args.drop else set()
    fleet = build_fleet(center, args.count)

    print(f"[seed] center={center} count={args.count} radius=3km")
    for d in fleet:
        tag = " (DROP after first beat)" if d["id"] in drop else ""
        print(
            f"  driver #{d['id']:<2} {d['expected']:<7} "
            f"{d['meta']['vehicleType']:<10} @ {d['lat']:.5f},{d['lng']:.5f}{tag}"
        )

    # First full round (every driver, including the ones we will drop).
    await _beat(fleet, skip=set())
    print(f"[seed] heartbeat sent for {len(fleet)} drivers.")

    if args.once:
        return 0

    print("[seed] looping — Ctrl-C to stop. Dropped drivers expire ~10s after first beat.")
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            for d in fleet:
                if d["id"] not in drop:
                    _jitter(d)
            await _beat(fleet, skip=drop)
            alive = len(fleet) - len(drop)
            print(f"[seed] heartbeat ({alive} alive, {len(drop)} dropped)")
    except KeyboardInterrupt:
        print("\n[seed] stopped. Remaining drivers expire within ~10s.")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed fake drivers into Redis.")
    parser.add_argument("--center", help="lat,lng to center the fleet on")
    parser.add_argument("--count", type=int, default=10, help="number of drivers")
    parser.add_argument("--once", action="store_true", help="seed once then exit")
    parser.add_argument("--drop", help="comma-separated driver #s to stop heartbeating")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
