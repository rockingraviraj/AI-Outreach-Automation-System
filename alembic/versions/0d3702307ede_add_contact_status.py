"""add contact status

Revision ID: 0d3702307ede
Revises: 40baf6235a71
Create Date: 2026-09-06 21:24:13.315934

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0d3702307ede"
down_revision: Union[str, Sequence[str], None] = "40baf6235a71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "contacts",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=True,
        ),
    )

    op.execute(
        "UPDATE contacts SET status = 'new' WHERE status IS NULL"
    )

    op.alter_column(
        "contacts",
        "status",
        existing_type=sa.String(length=20),
        nullable=False,
    )

    op.create_index(
        op.f("ix_contacts_status"),
        "contacts",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_contacts_status"),
        table_name="contacts",
    )

    op.drop_column(
        "contacts",
        "status",
    )