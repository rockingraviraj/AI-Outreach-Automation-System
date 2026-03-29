from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from datetime import datetime
from app.db.base import Base


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)

    campaign_id = Column(Integer, nullable=True)
    contact_id = Column(Integer, ForeignKey("contacts.id"))

    subject = Column(String, nullable=False)
    body = Column(String, nullable=False)

    status = Column(String, default="pending")  # pending / sent / failed
    sent_at = Column(DateTime, default=None)