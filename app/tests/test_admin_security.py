"""Tests for the fail-closed admin API guard."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "test-secret-not-for-production")

from fastapi import HTTPException

from app.core.admin_security import require_admin_api_key


class AdminSecurityTests(unittest.TestCase):
    def test_missing_configuration_disables_the_admin_api(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as context:
                require_admin_api_key(None)

        self.assertEqual(context.exception.status_code, 503)

    def test_wrong_key_is_rejected(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": "correct-key"}, clear=False):
            with self.assertRaises(HTTPException) as context:
                require_admin_api_key("wrong-key")

        self.assertEqual(context.exception.status_code, 401)

    def test_correct_key_is_accepted(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": "correct-key"}, clear=False):
            self.assertIsNone(require_admin_api_key("correct-key"))


if __name__ == "__main__":
    unittest.main()
