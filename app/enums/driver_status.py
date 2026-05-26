"""Driver availability enum.

Today Driver.status is a free-form String column ("online" / "on_trip" — see
app/booking/router.py for the only writers). This enum captures the values
already in use so call-sites can move off magic strings.

When ready, narrow the SQLAlchemy column to `Column(Enum(DriverStatus))` and
migrate via Alembic.
"""

import enum


class DriverStatus(str, enum.Enum):
    ONLINE = "online"
    ON_TRIP = "on_trip"
    OFFLINE = "offline"
