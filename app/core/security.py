from passlib.context import CryptContext
from datetime import datetime, timedelta
from jose import jwt
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
ALGORITHM = os.getenv("ALGORITHM", "HS256")

# 🔥 bcrypt config (stable)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ✅ HASH PASSWORD (FINAL FIXED)
def hash_password(password: str) -> str:
    if not isinstance(password, str):
        password = str(password)

    # 🔥 IMPORTANT FIX (bcrypt limit)
    password = password[:72]

    return pwd_context.hash(password)


# ✅ VERIFY PASSWORD (FINAL FIXED)
def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not isinstance(plain_password, str):
        plain_password = str(plain_password)

    plain_password = plain_password[:72]

    return pwd_context.verify(plain_password, hashed_password)


# ✅ CREATE JWT TOKEN
def create_access_token(data: dict, expires_minutes: int = 60):
    to_encode = data.copy()

    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})

    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)