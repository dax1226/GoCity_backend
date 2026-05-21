"""
Notification routes for GoCity.

Endpoints:
  - GET  /api/notifications           -> list current user's notifications
  - GET  /api/notifications/unread-count -> count of unread notifications
  - PATCH /api/notifications/{id}/read  -> mark a notification as read
  - PATCH /api/notifications/read-all   -> mark all notifications as read
  - POST /api/notifications/simulate    -> simulate a notification (temp,
                                           until driver panel is built)

GPS Wire:
  The `driver_lat` and `driver_lng` fields on each notification are the
  "wire" endpoints. When the driver panel is built, it will POST
  notifications with real GPS coordinates from the driver's device.
  The user panel reads these fields to display driver location.
  For now, the simulate endpoint uses hardcoded demo coordinates.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.user.auth import get_current_user
from app.models import User, Notification, NotificationType, Booking
from app.schemas import NotificationResponse


router = APIRouter()


@router.get("/", response_model=List[NotificationResponse])
def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return current user's notifications, newest first."""
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )
    return notifications


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the count of unread notifications."""
    count = (
        db.query(func.count(Notification.id))
        .filter(
            Notification.user_id == current_user.id,
            Notification.is_read == 0,
        )
        .scalar()
    )
    return {"unread_count": count}


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a single notification as read."""
    notif = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .first()
    )
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.is_read = 1
    db.commit()
    db.refresh(notif)
    return notif


@router.patch("/read-all")
def mark_all_as_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all notifications for the current user as read."""
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == 0,
    ).update({"is_read": 1})
    db.commit()
    return {"message": "All notifications marked as read"}


# ─────────────────────────────────────────────
# Simulation endpoint (temp — until driver panel exists)
# ─────────────────────────────────────────────
# Demo coordinates around Bengaluru for simulation
_DEMO_COORDS = {
    NotificationType.DRIVER_ASSIGNED:  (12.9716, 77.5946),
    NotificationType.DRIVER_EN_ROUTE:  (12.9650, 77.5900),
    NotificationType.DRIVER_ARRIVED:   (12.9600, 77.5850),
    NotificationType.RIDE_STARTED:     (12.9600, 77.5850),
    NotificationType.RIDE_COMPLETED:   (12.9784, 77.6408),
}

_DEMO_MESSAGES = {
    NotificationType.DRIVER_ASSIGNED:  ("Driver Assigned", "Your driver {driver_name} is on the way. Vehicle: {vehicle_number}"),
    NotificationType.DRIVER_EN_ROUTE:  ("Driver En Route", "Your driver {driver_name} is heading to your pickup location."),
    NotificationType.DRIVER_ARRIVED:   ("Driver Arrived", "Your driver {driver_name} has arrived at the pickup point."),
    NotificationType.RIDE_STARTED:     ("Ride Started", "Your ride has started. Enjoy the trip!"),
    NotificationType.RIDE_COMPLETED:   ("Ride Completed", "You have reached your destination. Fare: ₹{fare}"),
    NotificationType.RIDE_CANCELLED:   ("Ride Cancelled", "Your ride has been cancelled."),
    NotificationType.PAYMENT_RECEIVED: ("Payment Received", "Payment of ₹{fare} received successfully."),
    NotificationType.GENERAL:          ("GoCity", "You have a new notification."),
}


@router.post("/simulate", response_model=NotificationResponse)
def simulate_notification(
    notification_type: NotificationType = Query(
        NotificationType.DRIVER_ASSIGNED,
        description="Type of notification to simulate",
    ),
    booking_id: int = Query(None, description="Optional booking ID to link"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Simulate a ride notification for testing.

    GPS Wire: In production, the driver panel will call a similar endpoint
    with real GPS coordinates. This simulation uses demo coordinates so
    the user panel can be tested end-to-end.

    When you build the driver panel, replace this with real driver-side
    POST calls that include actual driver_lat/driver_lng from the device GPS.
    """
    driver_name = "Demo Driver"
    vehicle_number = "KA01XX0000"
    fare = 0.0

    if booking_id:
        booking = db.query(Booking).filter(Booking.id == booking_id).first()
        if booking and booking.driver:
            driver_name = booking.driver.name
            vehicle_number = booking.driver.vehicle_number
            fare = booking.fare
        elif booking:
            fare = booking.fare

    title, msg_template = _DEMO_MESSAGES.get(
        notification_type,
        ("GoCity", "Notification"),
    )
    message = msg_template.format(
        driver_name=driver_name,
        vehicle_number=vehicle_number,
        fare=fare,
    )

    coords = _DEMO_COORDS.get(notification_type, (None, None))

    notif = Notification(
        user_id=current_user.id,
        booking_id=booking_id,
        type=notification_type,
        title=title,
        message=message,
        driver_lat=coords[0],
        driver_lng=coords[1],
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif
