"""Low-overhead request and database timing instrumentation.

The logs deliberately contain route templates and SQL fingerprints instead of
request bodies, query-string values, or bind parameters.  That keeps OTPs,
phone numbers, addresses, and tokens out of normal application logs while
still making slow endpoints and queries identifiable.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Callable
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


LOGGER = logging.getLogger("gocity.observability")


def _positive_float(name: str, default: float) -> float:
    """Read a positive float setting without making a bad env value fatal."""
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        LOGGER.warning("Ignoring invalid %s setting", name)
        return default
    return value if value > 0 else default


SLOW_REQUEST_MS = _positive_float("SLOW_REQUEST_MS", 500.0)
SLOW_QUERY_MS = _positive_float("SLOW_QUERY_MS", 150.0)


def configure_logging() -> None:
    """Configure a useful default only when the host has not configured logs.

    Uvicorn/Gunicorn can still replace this configuration in production.  The
    format is intentionally structured enough for log aggregation without
    requiring another dependency.
    """
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def sql_fingerprint(statement: str, *, max_length: int = 300) -> str:
    """Return a log-safe, compact representation of a SQL statement.

    SQLAlchemy usually binds values separately, but hand-written SQL can still
    embed strings and numbers.  Replacing both prevents personal data and OTPs
    from appearing in query timing logs.
    """
    compact = " ".join(statement.split())
    compact = re.sub(r"'(?:''|[^'])*'", "?", compact)
    compact = re.sub(r'"(?:""|[^"])*"', '"?"', compact)
    compact = re.sub(r"\b\d+(?:\.\d+)?\b", "?", compact)
    return compact[:max_length]


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Attach a request id and emit one latency log entry per HTTP request."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = uuid4().hex
        request.state.request_id = request_id
        started_at = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started_at) * 1000
            route = _route_name(request)
            LOGGER.exception(
                "request_failed request_id=%s method=%s route=%s duration_ms=%.2f",
                request_id,
                request.method,
                route,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - started_at) * 1000
        route = _route_name(request)
        log = LOGGER.warning if duration_ms >= SLOW_REQUEST_MS else LOGGER.info
        log(
            "request_complete request_id=%s method=%s route=%s status_code=%s duration_ms=%.2f",
            request_id,
            request.method,
            route,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response


def _route_name(request: Request) -> str:
    """Prefer FastAPI's template (``/users/{id}``) over raw user input."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or request.url.path
