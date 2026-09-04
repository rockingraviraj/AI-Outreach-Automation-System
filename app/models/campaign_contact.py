from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint

from app.db.base import Base


class CampaignContact(Base):
    __tablename__ = "campaign_contacts"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    campaign_id = Column(
        Integer,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    contact_id = Column(
        Integer,
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "campaign_id",
            "contact_id",
            name="uq_campaign_contacts_campaign_contact"
        ),
    )