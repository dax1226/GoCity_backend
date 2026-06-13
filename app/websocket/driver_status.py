"""WebSocket bridge for live driver movements.

Simple fan-out: subscribe to the Redis ``drivers:moved`` pub/sub channel (every
heartbeat in app/geo/service.py publishes to it) and forward each message to the
connected client.

This is intentionally minimal — the rider map currently polls GET
/api/drivers/nearby every 5s, and this endpoint is the wired-but-simple upgrade
path to push updates instead. A production version would filter by the rider's
viewport/radius before forwarding.

    ws://<host>/ws/drivers/moved

Each frame is the JSON published by heartbeat(): {"driverId","lat","lng"}.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.redis_client import DRIVERS_MOVED_CHANNEL, get_redis

router = APIRouter()


@router.websocket("/ws/drivers/moved")
async def drivers_moved_ws(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        pubsub = get_redis().pubsub()
    except Exception:
        # Redis not reachable — tell the client and bail; it can fall back to
        # polling /api/drivers/nearby.
        await websocket.send_json({"error": "location service unavailable"})
        await websocket.close()
        return

    await pubsub.subscribe(DRIVERS_MOVED_CHANNEL)
    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1.0,
            )
            if message and message.get("type") == "message":
                # data is already a JSON string (decode_responses=True).
                await websocket.send_text(message["data"])
            else:
                # Yield to the loop; keeps the socket responsive without a
                # busy-wait when no driver is moving.
                await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(DRIVERS_MOVED_CHANNEL)
        await pubsub.aclose()
