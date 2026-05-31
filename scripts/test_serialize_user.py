from datetime import date, datetime
from types import SimpleNamespace
import json

from app.user.router import _serialize_user


def main():
    user = SimpleNamespace(
        id=1,
        name="Alice",
        email="alice@example.com",
        phone="+911234567890",
        role="USER",
        gender="Female",
        date_of_birth=date(2006, 9, 30),
        member_since=datetime(2024, 1, 2, 3, 4, 5),
        emergency_contact="+911112223333",
    )

    data = _serialize_user(user)
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
