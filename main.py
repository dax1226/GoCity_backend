from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.user.routes import router as user_router
from app.booking.routes import router as booking_router
from app.core.database import engine, Base

# Make sure all models are imported before create_all
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


@app.get("/")
def read_root():
    return {"message": "Welcome to GoCity Backend API"}
