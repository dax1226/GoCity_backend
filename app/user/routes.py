from fastapi import APIRouter, Depends, HTTPException, status

from sqlalchemy.orm import Session

from passlib.context import CryptContext

from datetime import datetime, timedelta

from jose import JWTError, jwt

import os



from app.core.database import get_db

from app.models import User

from app.schemas import UserCreate, UserResponse, Token, LoginRequest



router = APIRouter()



# Password hashing

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



# JWT settings

SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey") # Should be set in .env

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 days



def get_password_hash(password):

    return pwd_context.hash(password)



def verify_password(plain_password, hashed_password):

    return pwd_context.verify(plain_password, hashed_password)



def create_access_token(data: dict):

    to_encode = data.copy()

    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt



@router.post("/signup", response_model=Token)

def signup(user: UserCreate, db: Session = Depends(get_db)):

    db_user = db.query(User).filter(User.email == user.email).first()

    if db_user:

        raise HTTPException(status_code=400, detail="Email already registered")

   

    hashed_password = get_password_hash(user.password)

    new_user = User(

        name=user.name,

        email=user.email,

        phone=user.phone,

        hashed_password=hashed_password,

        role=user.role

    )

    db.add(new_user)

    db.commit()

    db.refresh(new_user)

   

    access_token = create_access_token(data={"sub": str(new_user.id)})

    return {"access_token": access_token, "token_type": "bearer", "user": new_user}



@router.post("/login", response_model=Token)

def login(request: LoginRequest, db: Session = Depends(get_db)):

    db_user = db.query(User).filter(User.email == request.email).first()

    if not db_user or not verify_password(request.password, db_user.hashed_password):

        raise HTTPException(status_code=400, detail="Incorrect email or password")

   

    access_token = create_access_token(data={"sub": str(db_user.id)})

    return {"access_token": access_token, "token_type": "bearer", "user": db_user}