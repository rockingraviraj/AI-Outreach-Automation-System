from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
import os

from dotenv import load_dotenv


# ---------------------------------------------------------
# Load .env
# ---------------------------------------------------------

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

env_path = os.path.join(
    BASE_DIR,
    ".env"
)

load_dotenv(dotenv_path=env_path)


# ---------------------------------------------------------
# Database URL
# ---------------------------------------------------------

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL is not set in .env file"
    )


# ---------------------------------------------------------
# SQLAlchemy Engine
# ---------------------------------------------------------

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False
    } if DATABASE_URL.startswith("sqlite") else {}
)


# ---------------------------------------------------------
# Enable SQLite Foreign-Key Enforcement
# ---------------------------------------------------------

if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()

        cursor.execute(
            "PRAGMA foreign_keys=ON"
        )

        cursor.close()


# ---------------------------------------------------------
# Session Factory
# ---------------------------------------------------------

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


# ---------------------------------------------------------
# Database Dependency
# ---------------------------------------------------------

def get_db():
    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()