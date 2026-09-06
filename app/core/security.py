from datetime import datetime, timedelta

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings


pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


def validate_password(password: str) -> str:
    if not isinstance(password, str):
        raise ValueError(
            "Password must be a string"
        )

    if not password:
        raise ValueError(
            "Password cannot be empty"
        )

    if len(password.encode("utf-8")) > 72:
        raise ValueError(
            "Password cannot exceed 72 bytes"
        )

    return password


def hash_password(password: str) -> str:
    password = validate_password(password)

    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str
) -> bool:
    plain_password = validate_password(
        plain_password
    )

    return pwd_context.verify(
        plain_password,
        hashed_password
    )


def create_access_token(
    data: dict,
    expires_minutes: int = 60
):
    if expires_minutes <= 0:
        raise ValueError(
            "Token expiration must be greater than zero"
        )

    to_encode = data.copy()

    expire = (
        datetime.utcnow()
        + timedelta(minutes=expires_minutes)
    )

    to_encode.update({
        "exp": expire
    })

    return jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )