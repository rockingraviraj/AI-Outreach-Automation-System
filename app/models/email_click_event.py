
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    DateTime,
    Index,
)

from app.db.base import Base


class EmailClickEvent(Base):
    __tablename__ = "email_click_events"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    email_id = Column(
        Integer,
        ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    clicked_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_email_click_events_email_clicked_at",
            "email_id",
            "clicked_at",
        ),
    )
