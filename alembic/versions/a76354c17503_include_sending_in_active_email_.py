"""include sending in active email idempotency

Revision ID: a76354c17503
Revises: 6f2c1a8b9d44
Create Date: 2026-09-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a76354c17503"
down_revision: Union[str, Sequence[str], None] = "6f2c1a8b9d44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index(
        "uq_emails_active_campaign_contact",
        table_name="emails",
    )

    op.create_index(
        "uq_emails_active_campaign_contact",
        "emails",
        ["campaign_id", "contact_id"],
        unique=True,
        postgresql_where=sa.text(
            "campaign_id IS NOT NULL "
            "AND status IN ('pending', 'sending', 'sent', 'opened')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_emails_active_campaign_contact",
        table_name="emails",
    )

    op.create_index(
        "uq_emails_active_campaign_contact",
        "emails",
        ["campaign_id", "contact_id"],
        unique=True,
        postgresql_where=sa.text(
            "campaign_id IS NOT NULL "
            "AND status IN ('pending', 'sent', 'opened')"
        ),
    )