# Live driver geo index (Redis hot path)

"Drivers within 3 km" — the in-memory geospatial index that powers the rider
map. **Locations live ONLY in Redis.** Postgres stores completed trips,
profiles, and audit data, and is touched here *only* to backfill the profile
meta cache on a miss — never for locations.

## Files

| File | Role |
| --- | --- |
| `app/core/redis_client.py` | Lazy async Redis client built from `REDIS_URL`. |
| `app/geo/service.py` | GEOADD / GEOSEARCH, alive TTL, meta cache, pub/sub. |
| `app/geo/router.py` | `GET /api/drivers/nearby`, `POST /api/drivers/heartbeat`. |
| `app/websocket/driver_status.py` | `ws://…/ws/drivers/moved` fan-out bridge. |
| `scripts/seed_fake_drivers.py` | Seeds fake drivers for local testing. |

## Redis keys & channel

| Key | Type | TTL | Purpose |
| --- | --- | --- | --- |
| `drivers:online` | GEO set (sorted set) | — | member = `driverId`, score encodes (lng, lat). |
| `driver:{id}:alive` | string | 10 s | Heartbeat liveness marker. Expired ⇒ driver is stale. |
| `driver:{id}:meta` | hash | — | `name`, `vehicleType`, `rating` for fast callouts. |
| `drivers:moved` | pub/sub channel | — | Each heartbeat publishes `{driverId,lat,lng}`. |

The alive TTL (10 s) is deliberately longer than the heartbeat interval (~4 s),
so one or two dropped beats are tolerated before a driver is removed.

## Exact Redis commands

**Heartbeat** (`POST /api/drivers/heartbeat`, driver app every ~4 s) runs, per
driver, in one pipeline — note GEOADD takes **longitude first**:

```
GEOADD drivers:online <lng> <lat> <driverId>
SET    driver:<driverId>:alive 1 EX 10
HSET   driver:<driverId>:meta name <name> vehicleType <type> rating <rating>
PUBLISH drivers:moved {"driverId":"<id>","lat":<lat>,"lng":<lng>}
```

**Nearby** (`GET /api/drivers/nearby?lat=&lng=`) runs:

```
GEOSEARCH drivers:online FROMLONLAT <lng> <lat> BYRADIUS 3 km ASC WITHCOORD WITHDIST COUNT 50
```

then, for each candidate, a pipelined liveness check and meta read:

```
EXISTS  driver:<id>:alive      # 0 ⇒ stale, filtered out (and ZREM'd)
HGETALL driver:<id>:meta       # miss ⇒ read Postgres once, then HSET to backfill
ZREM    drivers:online <stale ids...>   # self-healing eviction
```

**Clean offline** (`go_offline`):

```
ZREM   drivers:online <driverId>
DEL    driver:<driverId>:alive driver:<driverId>:meta
```

## Response shape

`GET /api/drivers/nearby` returns drivers sorted by distance ascending:

```json
[
  {
    "driverId": "1",
    "lat": 12.9806,
    "lng": 77.5946,
    "distanceKm": 1.0,
    "etaMin": 2,
    "vehicleType": "auto",
    "name": "Ravi (#1)",
    "rating": 4.8
  }
]
```

`etaMin` is derived from distance assuming a ~25 km/h average city speed
(`distanceKm / 25 * 60`, floored at 1 minute).

## Local setup

Redis is **optional at boot** — the API starts without it and the geo endpoints
return `503` until Redis is reachable.

1. **Install the client** (already in `requirements.txt`):
   ```
   pip install -r requirements.txt
   ```
2. **Run a Redis** (any one):
   ```
   docker run -p 6379:6379 redis:7-alpine
   # or: choco install redis-64 / brew install redis / managed (Upstash, Redis Cloud)
   ```
3. **Point the app at it** in `.env`:
   ```
   REDIS_URL="redis://localhost:6379/0"      # or your managed rediss:// URL
   ```
4. **Run the API**:
   ```
   uvicorn main:app --reload
   ```

## Seed fake drivers

The fleet auto-centers on the **user's live location** — the coordinates the
rider app last sent to `/api/drivers/nearby`, which the endpoint records in
Redis under `geo:last_rider_query` (1h TTL). So there's **no hard-coded city**:

1. Open the app's **"Drivers near you"** map. It polls `/nearby` with your real
   phone GPS, which the backend remembers.
2. Run the seed script with no `--center` — it picks up that live location.

```bash
# Auto-center on your live phone location (open the app's map first!).
# Continuous heartbeats (markers visibly move). Ctrl-C to stop.
python -m scripts.seed_fake_drivers

# One round then exit
python -m scripts.seed_fake_drivers --once

# Override the center explicitly + set fleet size
python -m scripts.seed_fake_drivers --center 23.0225,72.5714 --count 10

# Demo the killed-heartbeat path: #3 and #7 expire within ~10s
python -m scripts.seed_fake_drivers --drop 3,7
```

Half the fleet is placed inside the 3 km radius and half outside, so
`/api/drivers/nearby` centered on the same point returns only the inside half.

> If you run it before the app has queried `/nearby`, it exits with a message
> telling you to open the map first (or pass `--center`). It never falls back to
> a default location.

## Quick manual check

```bash
# Prime the live location, seed around it, then query that same point.
# (Replace the coords with your own — or just open the app's map first.)
curl "http://localhost:8000/api/drivers/nearby?lat=23.5952&lng=72.3668&radius_km=3"
python -m scripts.seed_fake_drivers --once
curl "http://localhost:8000/api/drivers/nearby?lat=23.5952&lng=72.3668&radius_km=3"

# Watch live movements over the WebSocket bridge:
#   ws://localhost:8000/ws/drivers/moved
```
