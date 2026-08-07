"""Retention jobs for operational, reconstructable data."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_

from app.core.database import SessionLocal
from app.enums.ride_status import BookingStatus
from app.models.ride import Booking
from app.models.tracking import Notification


LOGGER = logging.getLogger("gocity.retention")


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        LOGGER.warning("Ignoring invalid %s setting", name)
        return default
    return value if value > 0 else default


# User-facing notifications are operational data rather than a system of
# record. Keeping 90 days gives support enough context without unbounded growth.
NOTIFICATION_RETENTION_DAYS = _positive_int("NOTIFICATION_RETENTION_DAYS", 90)
RETENTION_SWEEP_INTERVAL_SECONDS = _positive_int("RETENTION_SWEEP_INTERVAL_SECONDS", 86_400)
LEGACY_RIDE_OTP_MAX_AGE_MINUTES = _positive_int("LEGACY_RIDE_OTP_MAX_AGE_MINUTES", 15)


def purge_expired_notifications(*, now: datetime | None = None) -> int:
    """Delete notification rows older than the configured retention window."""
    current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = current_time - timedelta(days=NOTIFICATION_RETENTION_DAYS)
    db = SessionLocal()
    try:
        deleted = (
            db.query(Notification)
            .filter(Notification.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        if deleted:
            LOGGER.info("notification_retention_purge deleted=%s", deleted)
        return int(deleted or 0)
    except Exception:
        db.rollback()
        LOGGER.exception("notification_retention_purge_failed")
        return 0
    finally:
        db.close()


def purge_legacy_ride_otps(*, now: datetime | None = None) -> int:
    """Remove any plaintext OTP left by versions before the stateless rollout.

    New ride flows never write ``bookings.ride_otp``. Terminal and verified
    rows are safe to clear immediately; an unstarted legacy ride is given a
    short grace period before its old code is invalidated and the driver can
    issue a new stateless code from the Start Trip action.
    """
    current_time = now or datetime.now(timezone.utc).replace(tzinfo=None)
    stale_before = current_time - timedelta(minutes=LEGACY_RIDE_OTP_MAX_AGE_MINUTES)
    db = SessionLocal()
    try:
        deleted = (
            db.query(Booking)
            .filter(
                Booking.ride_otp.isnot(None),
                or_(
                    Booking.otp_verified.is_(True),
                    Booking.status.in_([BookingStatus.COMPLETED, BookingStatus.CANCELLED]),
                    Booking.created_at < stale_before,
                ),
            )
            .update({Booking.ride_otp: None}, synchronize_session=False)
        )
        db.commit()
        if deleted:
            LOGGER.info("legacy_ride_otp_purge cleared=%s", deleted)
        return int(deleted or 0)
    except Exception:
        db.rollback()
        LOGGER.exception("legacy_ride_otp_purge_failed")
        return 0
    finally:
        db.close()


def purge_expired_operational_data() -> None:
    """Run all retention policies once; each policy commits independently."""
    purge_expired_notifications()
    purge_legacy_ride_otps()


async def retention_loop() -> None:
    """Run immediately at startup, then at a conservative daily cadence."""
    while True:
        await asyncio.to_thread(purge_expired_operational_data)
        await asyncio.sleep(RETENTION_SWEEP_INTERVAL_SECONDS)
