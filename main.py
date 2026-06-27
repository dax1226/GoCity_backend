from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.user.router import router as user_router
from app.booking.router import router as booking_router
from app.notification.router import router as notification_router
from app.saved_place.router import router as saved_place_router
from app.payment.router import router as payment_router
from app.driver.router import router as driver_router
from app.geo.router import router as geo_router
from app.websocket.driver_status import router as driver_status_ws_router
from app.admin.router import router as admin_router
from app.core.database import engine, Base

# Importing the models package side-effect-registers every table on
# Base.metadata so create_all picks them up.
from app import models  # noqa: F401

# Create tables
Base.metadata.create_all(bind=engine)


app = FastAPI(title="GoCity Backend", version="1.0.0")


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(user_router,    prefix="/api/users",    tags=["users"])
app.include_router(booking_router, prefix="/api/bookings", tags=["bookings"])
app.include_router(notification_router, prefix="/api/notifications", tags=["notifications"])
app.include_router(saved_place_router, prefix="/api/saved-places", tags=["saved-places"])
app.include_router(payment_router, prefix="/api/payment", tags=["payment"])
app.include_router(driver_router, prefix="/api/driver", tags=["driver"])
app.include_router(geo_router, prefix="/api/drivers", tags=["drivers-geo"])
app.include_router(driver_status_ws_router, tags=["drivers-geo-ws"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])


@app.get("/")
def read_root():
    return {"message": "Welcome to GoCity Backend API"}
