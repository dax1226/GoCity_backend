"""Persistence tests for protected FastAPI admin operations.

The API-key dependency has focused coverage in ``test_admin_security``. These
tests exercise the route functions with an isolated SQLite session so customer
and driver mutations never need the developer's configured database.
"""

import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.admin.router import (
    AdminDriverCreate,
    AdminDriverStatusUpdate,
    AdminUserCreate,
    AdminUserUpdate,
    VerificationPayload,
    create_driver,
    create_user,
    router as admin_router,
    set_driver_verification,
    update_driver_status,
    update_user,
)
from app.core.database import Base, get_db
from app.models.driver import Driver
from app.models.user import User, UserRole


class AdminRouteTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.app = FastAPI()
        self.app.include_router(admin_router, prefix="/api/admin")

        def test_db():
            yield self.session

        self.app.dependency_overrides[get_db] = test_db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_customer_create_and_profile_update_are_persisted(self):
        created = create_user(
            AdminUserCreate(name="Asha Patel", phone="98765 43210", email="asha@example.com"),
            self.session,
        )

        self.assertEqual(created["phone"], "+919876543210")
        self.assertEqual(created["role"], "USER")
        self.assertEqual(self.session.query(User).count(), 1)

        updated = update_user(
            created["id"],
            AdminUserUpdate(gender="Female", emergency_contact="9876543211"),
            self.session,
        )
        self.assertEqual(updated["gender"], "Female")
        self.assertEqual(updated["emergency_contact"], "9876543211")

        with self.assertRaises(HTTPException) as duplicate:
            create_user(
                AdminUserCreate(name="Duplicate", phone="+91 98765 43210"),
                self.session,
            )
        self.assertEqual(duplicate.exception.status_code, 409)

    def test_driver_requires_approval_before_going_online(self):
        created = create_driver(
            AdminDriverCreate(
                name="Rahul Kumar",
                phone="99887 76655",
                vehicle_type="auto",
                vehicle_number="ka-01-ab-1234",
            ),
            self.session,
        )

        self.assertEqual(created["vehicle_number"], "KA-01-AB-1234")
        self.assertFalse(created["documents_verified"])
        self.assertEqual(
            self.session.query(User).filter(User.phone == "+919988776655").one().role,
            UserRole.RIDER,
        )

        with self.assertRaises(HTTPException) as blocked:
            update_driver_status(
                created["id"],
                AdminDriverStatusUpdate(status="online"),
                self.session,
            )
        self.assertEqual(blocked.exception.status_code, 409)

        approved = set_driver_verification(
            created["id"],
            VerificationPayload(action="approve"),
            self.session,
        )
        self.assertTrue(approved["documents_verified"])

        online = update_driver_status(
            created["id"],
            AdminDriverStatusUpdate(status="online"),
            self.session,
        )
        self.assertEqual(online["status"], "online")

        rejected = set_driver_verification(
            created["id"],
            VerificationPayload(action="reject"),
            self.session,
        )
        self.assertFalse(rejected["documents_verified"])
        self.assertEqual(rejected["status"], "offline")
        self.assertEqual(self.session.query(Driver).count(), 1)

    def test_http_route_enforces_the_key_and_creates_a_customer(self):
        with patch.dict(os.environ, {"ADMIN_API_KEY": "test-admin-key"}, clear=False):
            missing_key = self.client.post(
                "/api/admin/users",
                json={"name": "Maya Singh", "phone": "9123456789"},
            )
            allowed = self.client.post(
                "/api/admin/users",
                headers={"x-admin-api-key": "test-admin-key"},
                json={"name": "Maya Singh", "phone": "9123456789"},
            )

        self.assertEqual(missing_key.status_code, 401)
        self.assertEqual(allowed.status_code, 201)
        self.assertEqual(allowed.json()["phone"], "+919123456789")


if __name__ == "__main__":
    unittest.main()
