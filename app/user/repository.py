"""User-domain persistence layer (slice-local).

Mirrors app/repositories/user_repository.py but scoped to the domain
folder. Use whichever fits the call site — the cross-cutting
repositories/ package is the long-term home; this slice-local one is for
queries that never need to leave the user domain.
"""

from sqlalchemy.orm import Session  # noqa: F401

from app.models.user import User, SavedPlace  # noqa: F401
