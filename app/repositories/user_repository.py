"""User persistence layer.

Stub. Today, app/user/router.py queries User directly via SQLAlchemy.
Migrate those queries here as the service layer fills out, e.g.:

    def get_by_email(db: Session, email: str) -> User | None: ...
    def create(db: Session, payload: UserCreate, hashed_password: str) -> User: ...
    def update_profile(db: Session, user: User, payload: UserProfileUpdate) -> User: ...
"""

from sqlalchemy.orm import Session  # noqa: F401  (kept for the future signatures above)

from app.models.user import User, SavedPlace  # noqa: F401
