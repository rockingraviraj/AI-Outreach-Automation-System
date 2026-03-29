from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from datetime import datetime
from app.db.base import Base

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)

    name = Column(String, nullable=False)
    status = Column(String, default="draft")  # draft/active/paused

    created_at = Column(DateTime, default=datetime.utcnow)