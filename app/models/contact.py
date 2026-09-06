from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint

from app.db.base import Base


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    name = Column(
        String,
        nullable=False
    )

    email = Column(
        String,
        nullable=False,
        index=True
    )

    company = Column(
        String,
        nullable=True
    )

    linkedin_url = Column(
        String,
        nullable=True
    )

    status = Column(
        String(20),
        nullable=False,
        default="new",
        index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "email",
            name="uq_contacts_user_email"
        ),
    )