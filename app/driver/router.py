import math
import random
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel

from app.core.database import get_db
from app.user.service import get_current_user
from app.models.user import User, UserRole
from app.models.driver import Driver
from app.models.ride import Booking
from app.enums.ride_status import BookingType, BookingStatus

router = APIRouter()

# ─── Geo Helpers ─────────────────────────────────────────────────────────────
_EARTH_RADIUS_KM = 6371.0

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km."""
    rlat1, rlat2 = math.radians(lat1), math.radians(lat2)
    dlat = rlat2 - rlat1
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# ─── DTO Helpers ─────────────────────────────────────────────────────────────
def _to_booking_response(b: Booking, d: Driver):
    driver_location = None
    if (
        b.driver_lat is not None
        and b.driver_lng is not None
        and b.driver_loc_updated_at is not None
    ):
        driver_location = {
            "lat": b.driver_lat,
            "lng": b.driver_lng,
            "updated_at": b.driver_loc_updated_at.isoformat(),
        }

    return {
        "id": b.id,
        "booking_type": b.booking_type,
        "pickup_location": b.pickup_location,
        "drop_location": b.drop_location,
        "pickup_lat": b.pickup_lat,
        "pickup_lng": b.pickup_lng,
        "drop_lat": b.drop_lat,
        "drop_lng": b.drop_lng,
        "vehicle_type": b.vehicle_type,
        "fare": b.fare,
        "status": b.status,
        "payment_method": b.payment_method,
        "sender_name": b.sender_name,
        "receiver_name": b.receiver_name,
        "receiver_phone": b.receiver_phone,
        "parcel_size": b.parcel_size,
        "created_at": b.created_at.isoformat(),
        "user": {
            "id": b.user.id,
            "name": b.user.name,
            "email": b.user.email,
            "role": b.user.role,
        },
        "driver": {
            "id": d.id,
            "name": d.name,
            "phone": d.phone,
            "vehicle_type": d.vehicle_type,
            "vehicle_number": d.vehicle_number,
            "rating": d.rating,
            "status": d.status,
            "current_lat": d.current_lat,
            "current_lng": d.current_lng,
        } if d else None,
        "driver_location": driver_location,
        "ride_otp": b.ride_otp,
        "otp_verified": b.otp_verified,
        "started_at": b.started_at.isoformat() if b.started_at else None,
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/profile")
def get_driver_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")
    
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        # Auto-create driver profile for the rider user
        driver = Driver(
            name=current_user.name or "Driver",
            phone=current_user.phone,
            vehicle_type="auto",
            vehicle_number="KA-01-MJ-" + str(random.randint(1000, 9999)),
            rating=5.0,
            status="offline",
            current_lat=12.9716,
            current_lng=77.5946
        )
        db.add(driver)
        db.commit()
        db.refresh(driver)
        
    return {
        "id": driver.id,
        "user_id": current_user.id,
        "name": driver.name,
        "phone": driver.phone,
        "email": current_user.email or f"{current_user.id}@gocity.com",
        "vehicle_type": driver.vehicle_type,
        "vehicle_number": driver.vehicle_number,
        "vehicle_model": "Standard vehicle",
        "rating": driver.rating,
        "status": driver.status,
        "total_rides": len(driver.bookings),
        "member_since": current_user.member_since.isoformat() if current_user.member_since else datetime.utcnow().isoformat(),
        "profile_image": None,
        "documents_verified": True
    }


class GoOnlinePayload(BaseModel):
    lat: float
    lng: float

@router.post("/go-online")
def go_online(
    payload: GoOnlinePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")
    
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
        
    driver.status = "online"
    driver.current_lat = payload.lat
    driver.current_lng = payload.lng
    db.commit()
    db.refresh(driver)
    return {"status": "online", "current_lat": driver.current_lat, "current_lng": driver.current_lng}


@router.post("/go-offline")
def go_offline(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")
    
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
        
    driver.status = "offline"
    db.commit()
    return {"status": "offline"}


@router.get("/rides/available")
def get_available_rides(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")
        
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
        
    # Query pending bookings created by real users
    bookings = db.query(Booking).options(joinedload(Booking.user)).filter(
        Booking.status == BookingStatus.PENDING
    ).all()
    
    response = []
    for b in bookings:
        dist = 5.0
        if b.pickup_lat and b.pickup_lng and b.drop_lat and b.drop_lng:
            dist = round(_haversine_km(b.pickup_lat, b.pickup_lng, b.drop_lat, b.drop_lng), 1)
            
        response.append({
            "booking_id": b.id,
            "booking_type": b.booking_type,
            "pickup_location": b.pickup_location,
            "drop_location": b.drop_location,
            "pickup_lat": b.pickup_lat,
            "pickup_lng": b.pickup_lng,
            "drop_lat": b.drop_lat,
            "drop_lng": b.drop_lng,
            "distance_km": dist,
            "estimated_fare": b.fare,
            "vehicle_type": b.vehicle_type or "auto",
            "payment_method": b.payment_method,
            "passenger_name": b.user.name or "User",
            "passenger_rating": 4.9,
            "created_at": b.created_at.isoformat() + "Z"
        })
    return response


@router.post("/rides/{booking_id}/accept")
def accept_ride(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")
        
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
        
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
        
    if booking.status != BookingStatus.PENDING:
        raise HTTPException(status_code=400, detail="Booking is not pending")
        
    booking.driver_id = driver.id
    booking.status = BookingStatus.ACCEPTED
    driver.status = "on_trip"
    db.commit()
    db.refresh(booking)
    db.refresh(driver)
    
    return _to_booking_response(booking, driver)


@router.post("/rides/{booking_id}/start")
def start_ride(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")
        
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
        
    booking = db.query(Booking).filter(Booking.id == booking_id, Booking.driver_id == driver.id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you")

    if not booking.otp_verified:
        raise HTTPException(status_code=400, detail="OTP not verified. Use /verify-otp first.")

    booking.status = BookingStatus.ONGOING
    if booking.started_at is None:
        booking.started_at = datetime.utcnow()
    db.commit()
    db.refresh(booking)
    return _to_booking_response(booking, driver)


class CompleteRidePayload(BaseModel):
    final_fare: Optional[float] = None

@router.post("/rides/{booking_id}/complete")
def complete_ride(
    booking_id: int,
    payload: Optional[CompleteRidePayload] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")
        
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
        
    booking = db.query(Booking).filter(Booking.id == booking_id, Booking.driver_id == driver.id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you")
        
    booking.status = BookingStatus.COMPLETED
    if payload and payload.final_fare is not None:
        booking.fare = payload.final_fare
    driver.status = "online"
    db.commit()
    db.refresh(booking)
    db.refresh(driver)
    return _to_booking_response(booking, driver)


class CancelRidePayload(BaseModel):
    reason: Optional[str] = None

@router.post("/rides/{booking_id}/cancel")
def cancel_ride(
    booking_id: int,
    payload: Optional[CancelRidePayload] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")
        
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
        
    booking = db.query(Booking).filter(Booking.id == booking_id, Booking.driver_id == driver.id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you")
        
    booking.status = BookingStatus.CANCELLED
    driver.status = "online"
    db.commit()
    db.refresh(booking)
    db.refresh(driver)
    return _to_booking_response(booking, driver)


@router.get("/rides/current")
def get_current_ride(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")
        
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
        
    booking = db.query(Booking).options(joinedload(Booking.user)).filter(
        Booking.driver_id == driver.id,
        Booking.status.in_([BookingStatus.ACCEPTED, BookingStatus.ONGOING])
    ).first()
    
    if not booking:
        return None
        
    return _to_booking_response(booking, driver)


@router.get("/rides/history")
def get_ride_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")
        
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
        
    bookings = db.query(Booking).options(joinedload(Booking.user)).filter(
        Booking.driver_id == driver.id,
        Booking.status.in_([BookingStatus.COMPLETED, BookingStatus.CANCELLED])
    ).order_by(Booking.created_at.desc()).all()
    
    return [_to_booking_response(b, driver) for b in bookings]


class UpdateLocationPayload(BaseModel):
    lat: float
    lng: float

@router.post("/update-location")
def update_location(
    payload: UpdateLocationPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")
        
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
        
    driver.current_lat = payload.lat
    driver.current_lng = payload.lng
    db.commit()
    return {"status": "ok"}


@router.post("/rides/{ride_id}/update-location")
def update_ride_location(
    ride_id: int,
    payload: UpdateLocationPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update driver location for a specific active ride.

    Writes to both the Driver row (so /bookings/me returns fresh
    driver.current_lat/lng for backward compat) and the Booking row
    (so driver_location is available in the BookingResponse).
    """
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")

    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")

    booking = db.query(Booking).filter(
        Booking.id == ride_id,
        Booking.driver_id == driver.id,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you")

    if booking.status not in (BookingStatus.ACCEPTED, BookingStatus.ONGOING):
        raise HTTPException(status_code=400, detail="Ride is not active")

    # Update the Driver row (backward compat — tracking.tsx reads driver.current_lat/lng)
    driver.current_lat = payload.lat
    driver.current_lng = payload.lng

    # Update the Booking row (new — driver_location in BookingResponse)
    booking.driver_lat = payload.lat
    booking.driver_lng = payload.lng
    booking.driver_loc_updated_at = datetime.utcnow()

    db.commit()
    return {"ok": True}


class VerifyOtpPayload(BaseModel):
    otp: str

@router.post("/rides/{ride_id}/verify-otp")
def verify_ride_otp(
    ride_id: int,
    payload: VerifyOtpPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify OTP to start a ride. OTP was generated at booking creation
    and shown to the user. Driver enters it to confirm pickup."""
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")

    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")

    booking = db.query(Booking).options(joinedload(Booking.user)).filter(
        Booking.id == ride_id,
        Booking.driver_id == driver.id,
    ).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or not assigned to you")

    if booking.status != BookingStatus.ACCEPTED:
        raise HTTPException(status_code=400, detail="Ride is not in ACCEPTED state")

    if not booking.ride_otp:
        raise HTTPException(status_code=400, detail="Ride OTP is missing")

    if payload.otp.strip() != booking.ride_otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    booking.otp_verified = True
    booking.status = BookingStatus.ONGOING
    booking.started_at = datetime.utcnow()
    db.commit()
    db.refresh(booking)
    return _to_booking_response(booking, driver)


@router.get("/earnings/summary")
def get_earnings_summary(
    period: str = "today",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")
        
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
        
    bookings = db.query(Booking).filter(
        Booking.driver_id == driver.id,
        Booking.status == BookingStatus.COMPLETED
    ).all()
    
    total_earnings = sum(b.fare for b in bookings)
    total_rides = len(bookings)
    deductions = round(total_earnings * 0.15, 2)
    net_earnings = round(total_earnings - deductions, 2)
    
    return {
        "period": period,
        "total_earnings": total_earnings,
        "total_rides": total_rides,
        "total_hours_online": 6.5,
        "average_rating": driver.rating,
        "tips": 0.0,
        "incentives": 0.0,
        "deductions": deductions,
        "net_earnings": net_earnings
    }


@router.get("/earnings/weekly")
def get_weekly_earnings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.RIDER:
        raise HTTPException(status_code=403, detail="User is not a rider/driver")
        
    driver = db.query(Driver).filter(Driver.phone == current_user.phone).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found")
        
    bookings = db.query(Booking).filter(
        Booking.driver_id == driver.id,
        Booking.status == BookingStatus.COMPLETED
    ).all()
    
    total_earnings = sum(b.fare for b in bookings)
    total_rides = len(bookings)
    
    return {
        "week_start": datetime.utcnow().date().isoformat(),
        "week_end": datetime.utcnow().date().isoformat(),
        "daily_breakdown": [
            { "date": datetime.utcnow().date().isoformat(), "day": "Today", "earnings": total_earnings, "rides": total_rides, "hours": 6.5 }
        ],
        "total": total_earnings,
        "total_rides": total_rides
    }
