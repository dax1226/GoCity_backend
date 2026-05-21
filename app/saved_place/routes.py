"""Saved Places CRUD routes."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.user.auth import get_current_user
from app.models import User, SavedPlace
from app.schemas import SavedPlaceCreate, SavedPlaceResponse

router = APIRouter()


@router.get("/", response_model=List[SavedPlaceResponse])
def list_saved_places(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(SavedPlace)
        .filter(SavedPlace.user_id == current_user.id)
        .order_by(SavedPlace.created_at.desc())
        .all()
    )


@router.post("/", response_model=SavedPlaceResponse)
def create_saved_place(
    payload: SavedPlaceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    place = SavedPlace(
        user_id=current_user.id,
        label=payload.label,
        address=payload.address,
        icon=payload.icon or "location",
        lat=payload.lat,
        lng=payload.lng,
    )
    db.add(place)
    db.commit()
    db.refresh(place)
    return place


@router.delete("/{place_id}")
def delete_saved_place(
    place_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    place = db.query(SavedPlace).filter(
        SavedPlace.id == place_id,
        SavedPlace.user_id == current_user.id,
    ).first()
    if not place:
        raise HTTPException(status_code=404, detail="Place not found")
    db.delete(place)
    db.commit()
    return {"detail": "Deleted"}
