"""Centralised application settings.

Reads every environment variable GoCity needs in one place.
pydantic-settings validates types at startup and makes every setting
importable as a typed attribute:

    from app.core.config import settings

    if settings.razorpay_key_id:
        ...

All values that have no default are optional (None).  Required values —
SECRET_KEY, DATABASE_URL — raise a loud startup error in security.py and
database.py, which already own those guards, so we don't duplicate them here.
"""

import os
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv

# Load .env before pydantic-settings reads the process environment.
# This is a no-op in production where env vars are injected by the platform.
load_dotenv()


class Settings:
    # ── Core ────────────────────────────────────────────────────────────────
    secret_key: str = os.getenv("SECRET_KEY", "")
    database_url: str = os.getenv("DATABASE_URL", "")
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "")

    # ── Logging / observability ──────────────────────────────────────────────
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    slow_request_ms: float = float(os.getenv("SLOW_REQUEST_MS", "500"))
    slow_query_ms: float = float(os.getenv("SLOW_QUERY_MS", "150"))

    # ── OTP lifecycle ────────────────────────────────────────────────────────
    otp_ttl_seconds: int = int(os.getenv("OTP_TTL_SECONDS", "300"))
    otp_resend_cooldown_seconds: int = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "30"))
    otp_max_verify_attempts: int = int(os.getenv("OTP_MAX_VERIFY_ATTEMPTS", "5"))
    ride_otp_ttl_seconds: int = int(os.getenv("RIDE_OTP_TTL_SECONDS", "600"))
    ride_otp_max_verify_attempts: int = int(os.getenv("RIDE_OTP_MAX_VERIFY_ATTEMPTS", "5"))
    otp_hash_secret: str = os.getenv("OTP_HASH_SECRET", "")
    ride_otp_hash_secret: str = os.getenv("RIDE_OTP_HASH_SECRET", "")

    # ── Retention ────────────────────────────────────────────────────────────
    notification_retention_days: int = int(os.getenv("NOTIFICATION_RETENTION_DAYS", "90"))
    retention_sweep_interval_seconds: int = int(os.getenv("RETENTION_SWEEP_INTERVAL_SECONDS", "86400"))
    legacy_ride_otp_max_age_minutes: int = int(os.getenv("LEGACY_RIDE_OTP_MAX_AGE_MINUTES", "15"))

    # ── Redis (optional) ─────────────────────────────────────────────────────
    redis_url: Optional[str] = os.getenv("REDIS_URL")

    # ── Cloudinary (optional) ────────────────────────────────────────────────
    cloudinary_cloud_name: Optional[str] = os.getenv("CLOUDINARY_CLOUD_NAME")
    cloudinary_api_key: Optional[str] = os.getenv("CLOUDINARY_API_KEY")
    cloudinary_api_secret: Optional[str] = os.getenv("CLOUDINARY_API_SECRET")

    # ── Twilio (optional) ────────────────────────────────────────────────────
    twilio_account_sid: Optional[str] = os.getenv("TWILIO_ACCOUNT_SID")
    twilio_auth_token: Optional[str] = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_phone_number: Optional[str] = os.getenv("TWILIO_PHONE_NUMBER")

    # ── Razorpay (optional) ──────────────────────────────────────────────────
    # Set RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET in your .env file.
    # Both are required for live payments; if either is missing the payment
    # endpoints fall back to stub mode so the rest of the app keeps working.
    razorpay_key_id: Optional[str] = os.getenv("RAZORPAY_KEY_ID") or None
    razorpay_key_secret: Optional[str] = os.getenv("RAZORPAY_KEY_SECRET") or None

    @property
    def razorpay_enabled(self) -> bool:
        """True only when both Razorpay credentials are present."""
        return bool(self.razorpay_key_id and self.razorpay_key_secret)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()


# Module-level singleton — preferred import style:
#   from app.core.config import settings
settings = get_settings()
