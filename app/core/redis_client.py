"""Redis connection for the geospatial hot path.

Locations live ONLY in Redis (never Postgres). This module exposes a single
lazily-created async client built from the REDIS_URL env var.

The client is created with ``decode_responses=True`` so GEO/HASH results come
back as ``str`` instead of ``bytes`` — every caller in app/geo expects plain
strings.

Redis is optional at boot: if REDIS_URL points at an unreachable server the app
still starts, and the geo endpoints surface a clean 503 (see app/geo/router.py)
instead of crashing. This matches the "stand Redis up later" setup documented in
app/geo/README.md.
"""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# redis-py ships the async client under redis.asyncio. Imported lazily inside
# get_redis() so the whole app does not hard-fail to import if the package is
# not installed yet (it lives in requirements.txt; install with pip).
REDIS_URL = (os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()

# Channel the API publishes driver movements to. The WebSocket bridge
# (app/websocket/driver_status.py) subscribes to this to fan out live updates.
DRIVERS_MOVED_CHANNEL = "drivers:moved"

_client = None  # type: ignore[var-annotated]


class RedisUnavailable(RuntimeError):
    """Raised when REDIS_URL is set but the server cannot be reached."""


def get_redis():
    """Return a process-wide async Redis client (created on first use)."""
    global _client
    if _client is None:
        try:
            from redis.asyncio import Redis  # noqa: WPS433 (intentional lazy import)
        except ImportError as exc:  # pragma: no cover - dependency missing
            raise RedisUnavailable(
                "The 'redis' package is not installed. Run "
                "`pip install -r requirements.txt`."
            ) from exc

        _client = Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            health_check_interval=30,
        )
    return _client


async def ping() -> bool:
    """Best-effort connectivity check. Returns False instead of raising."""
    try:
        return bool(await get_redis().ping())
    except Exception:
        return False


async def close() -> None:
    """Close the shared client (call on app shutdown)."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        finally:
            _client = None
