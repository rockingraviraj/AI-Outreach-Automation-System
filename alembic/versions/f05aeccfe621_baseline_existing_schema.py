"""baseline existing schema

Revision ID: f05aeccfe621
Revises:
Create Date: 2026-08-25 15:24:00.836688
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f05aeccfe621"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Apply the schema changes to the existing SQLite database.
    SQLite-safe through Alembic batch operations.
    """

    # -----------------------------------------------------
    # Campaigns
    # -----------------------------------------------------

    with op.batch_alter_table("campaigns", schema=None) as batch_op:

        batch_op.alter_column(
            "user_id",
            existing_type=sa.INTEGER(),
            nullable=False,
        )

        batch_op.alter_column(
            "status",
            existing_type=sa.VARCHAR(),
            nullable=False,
        )

        batch_op.alter_column(
            "created_at",
            existing_type=sa.DATETIME(),
            nullable=False,
        )

        batch_op.create_index(
            "ix_campaigns_user_id",
            ["user_id"],
            unique=False,
        )

        batch_op.create_foreign_key(
            "fk_campaigns_user_id_users",
            "users",
            ["user_id"],
            ["id"],
        )

    # -----------------------------------------------------
    # Emails
    # -----------------------------------------------------

    with op.batch_alter_table("emails", schema=None) as batch_op:

        batch_op.alter_column(
            "contact_id",
            existing_type=sa.INTEGER(),
            nullable=False,
        )

        batch_op.alter_column(
            "status",
            existing_type=sa.VARCHAR(),
            nullable=False,
        )

        batch_op.create_index(
            "ix_emails_campaign_id",
            ["campaign_id"],
            unique=False,
        )

        batch_op.create_index(
            "ix_emails_contact_id",
            ["contact_id"],
            unique=False,
        )

        batch_op.create_index(
            "ix_emails_status",
            ["status"],
            unique=False,
        )

        batch_op.create_foreign_key(
            "fk_emails_campaign_id_campaigns",
            "campaigns",
            ["campaign_id"],
            ["id"],
        )


def downgrade() -> None:
    """
    Reverse the schema changes.
    """

    # -----------------------------------------------------
    # Emails rollback
    # -----------------------------------------------------

    with op.batch_alter_table("emails", schema=None) as batch_op:

        batch_op.drop_constraint(
            "fk_emails_campaign_id_campaigns",
            type_="foreignkey",
        )

        batch_op.drop_index(
            "ix_emails_status"
        )

        batch_op.drop_index(
            "ix_emails_contact_id"
        )

        batch_op.drop_index(
            "ix_emails_campaign_id"
        )

        batch_op.alter_column(
            "status",
            existing_type=sa.VARCHAR(),
            nullable=True,
        )

        batch_op.alter_column(
            "contact_id",
            existing_type=sa.INTEGER(),
            nullable=True,
        )

    # -----------------------------------------------------
    # Campaigns rollback
    # -----------------------------------------------------

    with op.batch_alter_table("campaigns", schema=None) as batch_op:

        batch_op.drop_constraint(
            "fk_campaigns_user_id_users",
            type_="foreignkey",
        )

        batch_op.drop_index(
            "ix_campaigns_user_id"
        )

        batch_op.alter_column(
            "created_at",
            existing_type=sa.DATETIME(),
            nullable=True,
        )

        batch_op.alter_column(
            "status",
            existing_type=sa.VARCHAR(),
            nullable=True,
        )

        batch_op.alter_column(
            "user_id",
            existing_type=sa.INTEGER(),
            nullable=True,
        )