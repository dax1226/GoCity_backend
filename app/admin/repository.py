"""Admin-domain persistence layer (slice-local).

Stub. Admin tooling reads across all domains, so queries here typically
fan out to the per-domain repositories rather than introducing new
SQLAlchemy queries.
"""

from sqlalchemy.orm import Session  # noqa: F401
