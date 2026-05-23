"""One-shot seed: inserts a known test user so you can verify OTP immediately.

Run from the GoCity_backend directory:
    python seed_test_user.py

Credentials it creates:
    phone:    +919999999999
    OTP:      123456 (dev master code)

Safe to re-run — it won't duplicate if the user already exists.
"""

from app.core.database import SessionLocal, engine, Base
from app import models  # noqa: F401 — ensures tables are registered before create_all
from app.models.user import User, UserRole


def main() -> None:
    # Make sure tables exist (idempotent).
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        phone = "+919999999999"
        existing = db.query(User).filter(User.phone == phone).first()
        if existing:
            print(f"User with phone {phone!r} already exists (id={existing.id}). Nothing to do.")
            return

        user = User(
            name="Test User",
            email="test@gocity.in",
            phone=phone,
            role=UserRole.USER,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        print(f"Created user id={user.id} phone={user.phone}")
        print("Login with:")
        print("  phone:    +919999999999")
        print("  OTP code: 123456 (dev master code)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
