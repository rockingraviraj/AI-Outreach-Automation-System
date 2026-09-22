from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime,
    Index,
    UniqueConstraint,
    text
)

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
        nullable=False
    )

    sent_at = Column(
        DateTime,
        nullable=True
    )

    processing_token = Column(
        String(100),
        nullable=True,
        index=True
    )

    processing_started_at = Column(
        DateTime,
        nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "tracking_token",
            name="uq_emails_tracking_token"
        ),
        Index(
            "ix_emails_tracking_token",
            "tracking_token",
            unique=False
        ),
        Index(
            "uq_emails_active_campaign_contact",
            "campaign_id",
            "contact_id",
            unique=True,
            postgresql_where=text(
                "campaign_id IS NOT NULL "
                "AND status IN ('pending', 'sending', 'sent', 'opened')"
            ),
        ),
    )