"""
One-shot seed: inserts a known test user so you can log in immediately.

Run from the GoCity_backend directory:
    python seed_test_user.py

Credentials it creates:
    email:    test@gocity.in
    password: test1234

Safe to re-run — it won't duplicate if the user already exists.
"""

from app.core.database import SessionLocal, engine, Base
from app import models  # noqa: F401 — ensures tables are registered before create_all
from app.models import User, UserRole
from app.core.security import get_password_hash


def main() -> None:
    # Make sure tables exist (idempotent).
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        email = "test@gocity.in"
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"User {email!r} already exists (id={existing.id}). Nothing to do.")
            return

        user = User(
            name="Test User",
            email=email,
            phone="9999999999",
            hashed_password=get_password_hash("test1234"),
            role=UserRole.USER,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Created user id={user.id} email={user.email}")
        print("Login with:")
        print("  email:    test@gocity.in")
        print("  password: test1234")
    finally:
        db.close()


if __name__ == "__main__":
    main()
