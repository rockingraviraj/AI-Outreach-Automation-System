from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate


router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)


# =========================================================
# SIGNUP
# POST /auth/signup
# =========================================================

@router.post("/signup")
def signup(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    name = user.name.strip()
    email = user.email.strip().lower()

    if not name:
        raise HTTPException(
            status_code=422,
            detail="Name cannot be empty"
        )

    if not email:
        raise HTTPException(
            status_code=422,
            detail="Email cannot be empty"
        )

    try:
        hashed_pw = hash_password(
            user.password
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc)
        )

    existing_user = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="Email already registered"
        )

    new_user = User(
        name=name,
        email=email,
        password_hash=hashed_pw
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Email already registered"
        )

    return {
        "message": "User created successfully"
    }


# =========================================================
# LOGIN
# POST /auth/login
# =========================================================

@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    email = form_data.username.strip().lower()

    db_user = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )

    if not db_user:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    if not db_user.password_hash:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    try:
        valid_password = verify_password(
            form_data.password,
            db_user.password_hash
        )

    except ValueError:
        valid_password = False

    if not valid_password:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    token = create_access_token({
        "sub": str(db_user.id)
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }