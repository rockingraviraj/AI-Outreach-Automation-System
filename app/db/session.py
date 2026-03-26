from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# 🔥 Load .env properly (IMPORTANT FIX)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
env_path = os.path.join(BASE_DIR, ".env")

load_dotenv(dotenv_path=env_path)

# 🔥 Get DATABASE URL
DATABASE_URL = os.getenv("DATABASE_URL")

# ❌ Safety check (very important)
if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL is not set in .env file")

# 🔥 Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

# 🔥 Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 🔥 Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()