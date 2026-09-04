"""add campaign contacts and tracking tokens

Revision ID: 40baf6235a71
Revises: 4a6ad93c3f98
Create Date: 2026-09-03

"""

from typing import Sequence, Union
import secrets

from alembic import op
import sqlalchemy as sa


revision: str = "40baf6235a71"
down_revision: Union[str, Sequence[str], None] = "4a6ad93c3f98"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # 1. Create campaign_contacts
    # ---------------------------------------------------------

    op.create_table(
        "campaign_contacts",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "campaign_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "contact_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            name="fk_campaign_contacts_campaign_id_campaigns",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name="fk_campaign_contacts_contact_id_contacts",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id",
            "contact_id",
            name="uq_campaign_contacts_campaign_contact",
        ),
    )

    op.create_index(
        "ix_campaign_contacts_id",
        "campaign_contacts",
        ["id"],
        unique=False,
    )

    op.create_index(
        "ix_campaign_contacts_campaign_id",
        "campaign_contacts",
        ["campaign_id"],
        unique=False,
    )

    op.create_index(
        "ix_campaign_contacts_contact_id",
        "campaign_contacts",
        ["contact_id"],
        unique=False,
    )

    # ---------------------------------------------------------
    # 2. Add tracking_token as nullable temporarily
    # ---------------------------------------------------------

    op.add_column(
        "emails",
        sa.Column(
            "tracking_token",
            sa.String(length=64),
            nullable=True,
        ),
    )

    # ---------------------------------------------------------
    # 3. Generate tracking tokens for existing emails
    # ---------------------------------------------------------

    connection = op.get_bind()

    emails = connection.execute(
        sa.text("SELECT id FROM emails")
    ).fetchall()

    for row in emails:
        token = secrets.token_urlsafe(48)

        connection.execute(
            sa.text(
                """
                UPDATE emails
                SET tracking_token = :token
                WHERE id = :email_id
                """
            ),
            {
                "token": token,
                "email_id": row.id,
            },
        )

    # ---------------------------------------------------------
    # 4. Make tracking_token NOT NULL
    # ---------------------------------------------------------

    op.alter_column(
        "emails",
        "tracking_token",
        existing_type=sa.String(length=64),
        nullable=False,
    )

    # ---------------------------------------------------------
    # 5. Add unique constraint/index for tracking_token
    # ---------------------------------------------------------

    op.create_unique_constraint(
        "uq_emails_tracking_token",
        "emails",
        ["tracking_token"],
    )

    op.create_index(
        "ix_emails_tracking_token",
        "emails",
        ["tracking_token"],
        unique=False,
    )

    # ---------------------------------------------------------
    # 6. Backfill campaign_contacts from existing campaign emails
    # ---------------------------------------------------------

    connection.execute(
        sa.text(
            """
            INSERT INTO campaign_contacts (campaign_id, contact_id)
            SELECT DISTINCT campaign_id, contact_id
            FROM emails
            WHERE campaign_id IS NOT NULL
            ON CONFLICT (campaign_id, contact_id) DO NOTHING
            """
        )
    )

    # ---------------------------------------------------------
    # 7. Protect contacts from duplicate email per user
    # ---------------------------------------------------------

    op.create_unique_constraint(
        "uq_contacts_user_email",
        "contacts",
        ["user_id", "email"],
    )


def downgrade() -> None:
    # Remove contact uniqueness
    op.drop_constraint(
        "uq_contacts_user_email",
        "contacts",
        type_="unique",
    )

    # Remove campaign_contacts
    op.drop_index(
        "ix_campaign_contacts_contact_id",
        table_name="campaign_contacts",
    )

    op.drop_index(
        "ix_campaign_contacts_campaign_id",
        table_name="campaign_contacts",
    )

    op.drop_index(
        "ix_campaign_contacts_id",
        table_name="campaign_contacts",
    )

    op.drop_table("campaign_contacts")

    # Remove tracking token indexes/constraint
    op.drop_index(
        "ix_emails_tracking_token",
        table_name="emails",
    )

    op.drop_constraint(
        "uq_emails_tracking_token",
        "emails",
        type_="unique",
    )

    op.drop_column(
        "emails",
        "tracking_token",
    )