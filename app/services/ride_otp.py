"""Stateless, time-limited OTPs for starting rides.

The numeric code is deterministically derived from a server secret, booking id,
and an expiry timestamp.  The database stores only that expiry timestamp —
never the plaintext code or even a reversible encrypted form — while the
passenger can still retrieve the same code after a page refresh.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

from app.core.security import SECRET_KEY


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


RIDE_OTP_TTL_SECONDS = _positive_int("RIDE_OTP_TTL_SECONDS", 600)
RIDE_OTP_MAX_VERIFY_ATTEMPTS = _positive_int("RIDE_OTP_MAX_VERIFY_ATTEMPTS", 5)
_RIDE_OTP_SECRET = (os.getenv("RIDE_OTP_HASH_SECRET") or SECRET_KEY).encode("utf-8")


def utc_now() -> datetime:
    """Return a naive UTC datetime for compatibility with the current schema."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def issue_ride_otp_expiry(*, now: datetime | None = None) -> datetime:
    """Issue a fresh code by recording its only durable input: expiry time."""
    current_time = now or utc_now()
    return current_time.replace(microsecond=0) + timedelta(seconds=RIDE_OTP_TTL_SECONDS)


def reveal_ride_otp(booking_id: int, expires_at: datetime | None, *, now: datetime | None = None) -> str | None:
    """Return the currently valid code, or ``None`` when it is expired/missing."""
    if expires_at is None:
        return None

    normalized_expiry = _as_naive_utc(expires_at)
    current_time = _as_naive_utc(now or utc_now())
    if normalized_expiry <= current_time:
        return None

    payload = f"ride-start:{booking_id}:{int(normalized_expiry.timestamp())}".encode("utf-8")
    digest = hmac.new(_RIDE_OTP_SECRET, payload, hashlib.sha256).digest()
    return f"{int.from_bytes(digest[:8], byteorder='big') % 1_000_000:06d}"


def verify_ride_otp(
    booking_id: int,
    expires_at: datetime | None,
    submitted_code: str,
    *,
    now: datetime | None = None,
) -> bool:
    expected_code = reveal_ride_otp(booking_id, expires_at, now=now)
    return bool(expected_code and hmac.compare_digest(expected_code, submitted_code.strip()))


def _as_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(microsecond=0)
    return value.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)
