"""add active email idempotency index

Revision ID: 6f2c1a8b9d44
Revises: 0d3702307ede
Create Date: 2026-09-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6f2c1a8b9d44"
down_revision: Union[str, Sequence[str], None] = "0d3702307ede"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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


def downgrade() -> None:
    op.drop_index(
        "uq_emails_active_campaign_contact",
        table_name="emails",
    )