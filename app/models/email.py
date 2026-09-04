from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from datetime import datetime

from app.db.base import Base


class Email(Base):
    __tablename__ = "emails"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    campaign_id = Column(
        Integer,
        ForeignKey("campaigns.id"),
        nullable=True,
        index=True
    )

    contact_id = Column(
        Integer,
        ForeignKey("contacts.id"),
        nullable=False,
        index=True
    )

    subject = Column(
        String,
        nullable=False
    )

    body = Column(
        String,
        nullable=False
    )

    status = Column(
        String,
        default="pending",
        nullable=False,
        index=True
    )

    tracking_token = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True
    )

    sent_at = Column(
        DateTime,
        nullable=True
    )