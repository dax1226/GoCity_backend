"""Tests for log-safety of observability helpers."""

import os
import unittest

os.environ.setdefault("SECRET_KEY", "test-secret-not-for-production")

from app.core.observability import sql_fingerprint


class SqlFingerprintTests(unittest.TestCase):
    def test_redacts_literals_but_keeps_query_shape(self):
        statement = (
            "SELECT * FROM users WHERE phone = '+919876543210' "
            "AND otp = '654321' AND id = 42"
        )

        fingerprint = sql_fingerprint(statement)

        self.assertIn("SELECT * FROM users", fingerprint)
        self.assertNotIn("9876543210", fingerprint)
        self.assertNotIn("654321", fingerprint)
        self.assertNotIn("42", fingerprint)


if __name__ == "__main__":
    unittest.main()
