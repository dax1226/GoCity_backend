"""Quick Redis connectivity check for the driver geo index.

Usage (from GoCity_backend/):
    python -m scripts.check_redis

Prints a clear OK/FAIL using the same REDIS_URL the app reads, so you can
confirm your .env before booting uvicorn.
"""

from __future__ import annotations

import asyncio

from app.core.redis_client import REDIS_URL, get_redis


def _masked(url: str) -> str:
    """Hide the password when echoing the URL back."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.split("@", 1)
        user = creds.split(":", 1)[0] if ":" in creds else creds
        return f"{scheme}://{user}:****@{host}"
    return url


async def main() -> int:
    print(f"[check] REDIS_URL = {_masked(REDIS_URL)}")
    try:
        r = get_redis()
        pong = await r.ping()
        await r.set("gocity:healthcheck", "ok", ex=10)
        value = await r.get("gocity:healthcheck")
        print(f"[check] PING -> {pong}")
        print(f"[check] SET/GET roundtrip -> {value}")
        print("[check] OK ✅  Redis is reachable. Start uvicorn and seed drivers.")
        return 0
    except Exception as exc:  # noqa: BLE001 - surface any connection error plainly
        print(f"[check] FAIL ❌  {type(exc).__name__}: {exc}")
        print("[check] Check REDIS_URL in .env. For Upstash use the rediss:// URL")
        print("[check] from the 'redis-py' tab (ends with :6379), not the https REST one.")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
