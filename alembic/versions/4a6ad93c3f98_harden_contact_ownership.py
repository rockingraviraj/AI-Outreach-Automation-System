"""harden contact ownership

Revision ID: 4a6ad93c3f98
Revises: f05aeccfe621
Create Date: 2026-08-25 20:05:15.938370
"""

from typing import Sequence, Union

from alembic import op


revision: str = "4a6ad93c3f98"
down_revision: Union[str, Sequence[str], None] = "f05aeccfe621"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Contact ownership is already part of the initial schema migration.

    This revision is intentionally kept as a no-op so the existing
    migration history remains valid.
    """
    pass


def downgrade() -> None:
    """
    No schema changes are associated with this compatibility revision.
    """
    pass