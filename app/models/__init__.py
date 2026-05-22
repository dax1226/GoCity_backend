"""SQLAlchemy ORM models, split by domain.

Importing this package side-effect-registers every table on Base.metadata so
that Base.metadata.create_all(engine) picks them up. main.py only needs to
`from app import models` (or import this package directly) before calling
create_all.
"""

from app.models.user import User, UserRole, SavedPlace  # noqa: F401
from app.models.driver import Driver  # noqa: F401
from app.models.ride import Booking  # noqa: F401
from app.models.tracking import Notification, NotificationType  # noqa: F401
# app.models.payment is a placeholder — no payment ORM models yet.
