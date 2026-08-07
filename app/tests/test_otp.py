"""Focused tests for OTP secrecy, expiry, and verification behaviour."""

import asyncio
import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

# Test runs should not depend on a developer's local .env file.
os.environ.setdefault("SECRET_KEY", "test-secret-not-for-production")

from app.services import otp
from app.services.ride_otp import (
    issue_ride_otp_expiry,
    reveal_ride_otp,
    verify_ride_otp,
)


class LoginOTPTests(unittest.TestCase):
    PHONE = "+919876543210"
    CODE = "654321"

    def setUp(self):
        otp.OTP_STORE.clear()

    def _send(self, code: str = CODE):
        with patch.object(otp, "_deliver_otp", new=AsyncMock()):
            asyncio.run(otp.send_otp(self.PHONE, code))

    def test_store_contains_only_hashed_values(self):
        self._send()

        self.assertEqual(len(otp.OTP_STORE), 1)
        fingerprint, record = next(iter(otp.OTP_STORE.items()))
        self.assertNotIn(self.PHONE, fingerprint)
        self.assertNotIn(self.CODE, str(record))
        self.assertIn("digest", record)

    def test_valid_code_is_one_time_use(self):
        self._send()

        self.assertTrue(otp.verify_otp(self.PHONE, self.CODE))
        self.assertFalse(otp.verify_otp(self.PHONE, self.CODE))

    def test_invalid_attempts_exhaust_the_record(self):
        self._send()

        for _ in range(otp.OTP_MAX_VERIFY_ATTEMPTS):
            self.assertFalse(otp.verify_otp(self.PHONE, "000000"))
        self.assertFalse(otp.verify_otp(self.PHONE, self.CODE))
        self.assertEqual(otp.OTP_STORE, {})

    def test_resend_is_rate_limited(self):
        self._send()

        with patch.object(otp, "_deliver_otp", new=AsyncMock()):
            with self.assertRaises(otp.OTPRateLimited) as context:
                asyncio.run(otp.send_otp(self.PHONE, "111111"))

        self.assertGreaterEqual(context.exception.retry_after_seconds, 1)

    def test_delivery_failure_removes_the_code(self):
        with patch.object(
            otp,
            "_deliver_otp",
            new=AsyncMock(side_effect=otp.OTPDeliveryError("provider failed")),
        ):
            with self.assertRaises(otp.OTPDeliveryError):
                asyncio.run(otp.send_otp(self.PHONE, self.CODE))

        self.assertEqual(otp.OTP_STORE, {})

    def test_master_code_requires_explicit_nonproduction_configuration(self):
        self._send()
        with patch.dict(
            os.environ,
            {"APP_ENV": "test", "OTP_DEV_MASTER_CODE": "112233"},
            clear=False,
        ):
            self.assertTrue(otp.verify_otp(self.PHONE, "112233"))
            self.assertEqual(otp.OTP_STORE, {})

        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=False):
            self.assertFalse(otp.verify_otp(self.PHONE, "112233"))


class RideOTPTests(unittest.TestCase):
    def test_code_is_deterministic_but_not_stored(self):
        now = datetime(2026, 8, 5, 12, 0, 0)
        expiry = issue_ride_otp_expiry(now=now)

        first = reveal_ride_otp(42, expiry, now=now)
        second = reveal_ride_otp(42, expiry, now=now + timedelta(seconds=1))

        self.assertIsNotNone(first)
        self.assertEqual(first, second)
        self.assertTrue(verify_ride_otp(42, expiry, first, now=now))
        self.assertFalse(verify_ride_otp(42, expiry, "000000", now=now))

    def test_code_is_unavailable_after_expiry(self):
        now = datetime(2026, 8, 5, 12, 0, 0)
        expiry = now + timedelta(seconds=1)

        self.assertIsNone(reveal_ride_otp(42, expiry, now=expiry))
        self.assertFalse(verify_ride_otp(42, expiry, "000000", now=expiry))


if __name__ == "__main__":
    unittest.main()
