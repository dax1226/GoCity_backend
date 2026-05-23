"""Pydantic request/response schemas, split by domain.

Re-exports the most commonly used names so routers can do
`from app.schemas import UserResponse, BookingResponse` if they prefer the
flat surface. New code should prefer the explicit submodules
(`from app.schemas.user_schema import UserResponse`).
"""

from app.schemas.user_schema import (  # noqa: F401
    PhoneRequest,
    OTPVerifyRequest,
    ProfileSetupRequest,
    UserResponse,
    UserProfileUpdate,
    Token,
    SavedPlaceCreate,
    SavedPlaceResponse,
)
from app.schemas.ride_schema import (  # noqa: F401
    DriverResponse,
    RideBookingCreate,
    CabBookingCreate,
    ParcelBookingCreate,
    BookingResponse,
    DatabaseSnapshot,
)
from app.schemas.tracking_schema import (  # noqa: F401
    NotificationResponse,
    NotificationCreate,
)
from app.schemas.payment_schema import (  # noqa: F401
    CreateOrderRequest,
    CreateOrderResponse,
    VerifyPaymentRequest,
    VerifyPaymentResponse,
)
