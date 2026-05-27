"""Notification / tracking persistence layer.

Stub. Candidates to migrate here from app/notification/router.py:
    - list current-user notifications (paged)
    - count unread
    - mark single notification read / mark-all-read bulk update
"""

from sqlalchemy.orm import Session  # noqa: F401

from app.models.tracking import Notification  # noqa: F401
