"""add email processing ownership

Revision ID: 92b06b72d331
Revises: a76354c17503
Create Date: 2026-09-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "92b06b72d331"
down_revision: Union[str, Sequence[str], None] = "a76354c17503"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "emails",
        sa.Column(
            "processing_token",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.add_column(
        "emails",
        sa.Column(
            "processing_started_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_emails_processing_token",
        "emails",
        ["processing_token"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_emails_processing_token",
        table_name="emails",
    )

    op.drop_column(
        "emails",
        "processing_started_at",
    )

    op.drop_column(
        "emails",
        "processing_token",
    )