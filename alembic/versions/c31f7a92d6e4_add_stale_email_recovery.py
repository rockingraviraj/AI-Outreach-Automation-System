"""add stale email recovery and delivery uncertainty tracking

Revision ID: c31f7a92d6e4
Revises: 92b06b72d331
Create Date: 2026-11-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c31f7a92d6e4"
down_revision: Union[str, Sequence[str], None] = "92b06b72d331"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "emails",
        sa.Column(
            "smtp_attempt_started_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    op.add_column(
        "emails",
        sa.Column(
            "recovery_requested_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_emails_status_processing_started_at",
        "emails",
        ["status", "processing_started_at"],
        unique=False,
    )

    op.create_index(
        "ix_emails_status_recovery_requested_at",
        "emails",
        ["status", "recovery_requested_at"],
        unique=False,
    )

    # Rows left in "sending" by the old worker have no SMTP boundary marker.
    # We cannot determine whether the old worker already submitted them to SMTP.
    # Conservatively quarantine them instead of allowing the new recovery task
    # to assume they are safe to resend. Deployment must stop API/worker first.
    op.execute(
        """
        UPDATE emails
        SET status = 'delivery_unknown',
            processing_token = NULL,
            processing_started_at = NULL,
            recovery_requested_at = NULL
        WHERE status = 'sending'
        """
    )

    # Reconcile campaigns which were running but now have only terminal email
    # outcomes after legacy sending rows have been quarantined.
    op.execute(
        """
        UPDATE campaigns AS c
        SET status = CASE
            WHEN EXISTS (
                SELECT 1
                FROM emails AS e
                WHERE e.campaign_id = c.id
                  AND e.status IN ('failed', 'delivery_unknown')
            ) THEN 'failed'
            ELSE 'completed'
        END
        WHERE c.status = 'running'
          AND EXISTS (
              SELECT 1 FROM emails AS e
              WHERE e.campaign_id = c.id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM emails AS e
              WHERE e.campaign_id = c.id
                AND e.status NOT IN (
                    'sent', 'opened', 'failed', 'delivery_unknown'
                )
          )
        """
    )

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
            "AND status IN "
            "('pending', 'sending', 'sent', 'opened', 'delivery_unknown')"
        ),
    )


def downgrade() -> None:
    # The previous schema has no delivery_unknown state. Preserve the rows by
    # mapping that state to failed before restoring the older partial index.
    op.execute(
        "UPDATE emails "
        "SET status = 'failed' "
        "WHERE status = 'delivery_unknown'"
    )

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

    op.drop_index(
        "ix_emails_status_recovery_requested_at",
        table_name="emails",
    )
    op.drop_index(
        "ix_emails_status_processing_started_at",
        table_name="emails",
    )

    op.drop_column("emails", "recovery_requested_at")
    op.drop_column("emails", "smtp_attempt_started_at")
