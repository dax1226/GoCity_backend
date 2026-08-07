"""One-time-password generation, delivery, and verification.

Only HMAC digests are retained in memory.  The phone number is also keyed by
an HMAC fingerprint, so a process dump or debug view does not expose a usable
OTP or a list of phone numbers.  For a multi-worker production deployment,
move the same record shape to Redis with its native TTL; this in-process store
is intentionally a local-development fallback.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import threading
import time
from typing import TypedDict

import httpx

from app.core.security import SECRET_KEY


LOGGER = logging.getLogger("gocity.otp")

MSG91_AUTH_KEY = os.getenv("MSG91_AUTH_KEY")
MSG91_TEMPLATE_ID = os.getenv("MSG91_TEMPLATE_ID")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")


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


OTP_TTL_SECONDS = _positive_int("OTP_TTL_SECONDS", 300)
OTP_RESEND_COOLDOWN_SECONDS = _positive_int("OTP_RESEND_COOLDOWN_SECONDS", 30)
OTP_MAX_VERIFY_ATTEMPTS = _positive_int("OTP_MAX_VERIFY_ATTEMPTS", 5)

# A dedicated secret lets operations rotate OTP verification independently of
# access-token signing.  Falling back to SECRET_KEY keeps existing installs
# secure while they add OTP_HASH_SECRET to their deployment configuration.
_HASH_SECRET = (os.getenv("OTP_HASH_SECRET") or SECRET_KEY).encode("utf-8")
_STORE_LOCK = threading.Lock()


class OTPRecord(TypedDict):
    digest: str
    expires_at: float
    resend_available_at: float
    attempts_remaining: int


# Maps an HMAC phone fingerprint to a record. It never holds a plaintext phone
# number or OTP. Kept public for diagnostic tests only; application code must
# use the functions below.
OTP_STORE: dict[str, OTPRecord] = {}


class OTPDeliveryError(RuntimeError):
    """The configured SMS provider did not accept an OTP delivery request."""


class OTPRateLimited(RuntimeError):
    """An OTP was requested before the resend cooldown elapsed."""

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Please wait before requesting another verification code.")


def _normalise_phone(phone: str) -> str:
    return phone.strip().replace("+", "")


def _fingerprint_phone(phone: str) -> str:
    return hmac.new(_HASH_SECRET, f"phone:{phone}".encode("utf-8"), hashlib.sha256).hexdigest()


def _digest_otp(phone_fingerprint: str, code: str) -> str:
    message = f"login-otp:{phone_fingerprint}:{code}".encode("utf-8")
    return hmac.new(_HASH_SECRET, message, hashlib.sha256).hexdigest()


def _clear_expired_records(now: float) -> None:
    expired = [
        fingerprint
        for fingerprint, record in OTP_STORE.items()
        if record["expires_at"] <= now
    ]
    for fingerprint in expired:
        OTP_STORE.pop(fingerprint, None)


def generate_otp() -> str:
    """Generate a cryptographically secure six-digit verification code."""
    return f"{secrets.randbelow(900_000) + 100_000:06d}"


async def send_otp(phone: str, otp: str) -> None:
    """Persist only a digest, then submit the code to the configured provider.

    An unsuccessful provider call removes the just-created record so callers
    never receive a success response for an unusable code.
    """
    normalized_phone = _normalise_phone(phone)
    phone_fingerprint = _fingerprint_phone(normalized_phone)
    digest = _digest_otp(phone_fingerprint, otp)
    now = time.monotonic()

    with _STORE_LOCK:
        _clear_expired_records(now)
        previous = OTP_STORE.get(phone_fingerprint)
        if previous:
            retry_after = previous["resend_available_at"] - now
            if retry_after > 0:
                raise OTPRateLimited(max(1, int(retry_after + 0.999)))

        OTP_STORE[phone_fingerprint] = {
            "digest": digest,
            "expires_at": now + OTP_TTL_SECONDS,
            "resend_available_at": now + OTP_RESEND_COOLDOWN_SECONDS,
            "attempts_remaining": OTP_MAX_VERIFY_ATTEMPTS,
        }

    try:
        await _deliver_otp(normalized_phone, otp)
    except OTPDeliveryError:
        with _STORE_LOCK:
            record = OTP_STORE.get(phone_fingerprint)
            if record and hmac.compare_digest(record["digest"], digest):
                OTP_STORE.pop(phone_fingerprint, None)
        raise


async def _deliver_otp(phone: str, otp: str) -> None:
    if all((TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER)):
        await _send_via_twilio(phone, otp)
        return

    if MSG91_AUTH_KEY:
        await _send_via_msg91(phone, otp)
        return

    if _development_master_code_enabled():
        # Never log the code itself. Explicitly configured development master
        # codes provide local testing without turning logs into a secret store.
        LOGGER.info("otp_delivery_skipped provider=development")
        return

    LOGGER.error("otp_delivery_unconfigured")
    raise OTPDeliveryError("No OTP delivery provider is configured.")


async def _send_via_twilio(phone: str, otp: str) -> None:
    """Send via Twilio's Message resource using async HTTP (not a blocking SDK)."""
    url = (
        "https://api.twilio.com/2010-04-01/Accounts/"
        f"{TWILIO_ACCOUNT_SID}/Messages.json"
    )
    data = {
        "To": f"+{phone}",
        "From": TWILIO_PHONE_NUMBER,
        "Body": f"Your GoCity verification code is {otp}. It expires in 5 minutes.",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
            response = await client.post(
                url,
                data=data,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            )
    except httpx.HTTPError as exc:
        LOGGER.warning("otp_delivery_failed provider=twilio error=%s", type(exc).__name__)
        raise OTPDeliveryError("Twilio could not be reached.") from exc

    if response.is_success:
        LOGGER.info("otp_delivery_accepted provider=twilio status_code=%s", response.status_code)
        return

    LOGGER.warning("otp_delivery_rejected provider=twilio status_code=%s", response.status_code)
    raise OTPDeliveryError("Twilio rejected the OTP delivery request.")


async def _send_via_msg91(phone: str, otp: str) -> None:
    """Send through MSG91 without placing the OTP in a URL query string."""
    payload = {
        "authkey": MSG91_AUTH_KEY,
        "mobile": phone,
        "otp": otp,
    }
    if MSG91_TEMPLATE_ID:
        payload["template_id"] = MSG91_TEMPLATE_ID

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
            response = await client.post("https://control.msg91.com/api/v5/otp", data=payload)
    except httpx.HTTPError as exc:
        LOGGER.warning("otp_delivery_failed provider=msg91 error=%s", type(exc).__name__)
        raise OTPDeliveryError("MSG91 could not be reached.") from exc

    if response.is_success:
        LOGGER.info("otp_delivery_accepted provider=msg91 status_code=%s", response.status_code)
        return

    LOGGER.warning("otp_delivery_rejected provider=msg91 status_code=%s", response.status_code)
    raise OTPDeliveryError("MSG91 rejected the OTP delivery request.")


def _development_master_code_enabled() -> bool:
    environment = os.getenv("APP_ENV", "production").lower()
    return bool(os.getenv("OTP_DEV_MASTER_CODE")) and environment in {"development", "test"}


def _matches_development_master_code(code: str) -> bool:
    master_code = os.getenv("OTP_DEV_MASTER_CODE")
    return bool(master_code and _development_master_code_enabled() and hmac.compare_digest(code, master_code))


def verify_otp(phone: str, code: str) -> bool:
    """Verify an OTP once, enforcing expiry and a bounded retry budget."""
    normalized_phone = _normalise_phone(phone)
    normalized_code = code.strip()

    if _matches_development_master_code(normalized_code):
        # A development bypass must not leave a superseded normal OTP record
        # alive in memory until its TTL expires.
        with _STORE_LOCK:
            OTP_STORE.pop(_fingerprint_phone(normalized_phone), None)
        return True

    phone_fingerprint = _fingerprint_phone(normalized_phone)
    expected_digest = _digest_otp(phone_fingerprint, normalized_code)
    now = time.monotonic()

    with _STORE_LOCK:
        _clear_expired_records(now)
        record = OTP_STORE.get(phone_fingerprint)
        if not record:
            return False

        if hmac.compare_digest(record["digest"], expected_digest):
            OTP_STORE.pop(phone_fingerprint, None)
            return True

        record["attempts_remaining"] -= 1
        if record["attempts_remaining"] <= 0:
            OTP_STORE.pop(phone_fingerprint, None)
        return False
