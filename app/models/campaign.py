from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from datetime import datetime

from app.db.base import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    name = Column(String(100), nullable=False)
    status = Column(String(20), default="draft", nullable=False)

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )