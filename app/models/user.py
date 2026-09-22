from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Index,
    UniqueConstraint
)

from datetime import datetime

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String,
        nullable=False
    )

    email = Column(
        String,
        nullable=False
    )

    password_hash = Column(
        String,
        nullable=True
    )

    is_verified = Column(
        Boolean,
        default=False
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "email",
            name="users_email_key"
        ),
        Index(
            "ix_users_email",
            "email",
            unique=True
        ),
    )