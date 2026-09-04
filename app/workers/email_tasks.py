from datetime import datetime
import os

import app.models

from app.core.celery_worker import celery_app
from app.db.session import SessionLocal
from app.models.email import Email
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.campaign_contact import CampaignContact
from app.services.ai_service import generate_email
from app.services.email_service import send_email


def update_campaign_status_if_complete(
    db,
    campaign_id: int
):
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id
        )
        .first()
    )

    if not campaign:
        return

    total_emails = (
        db.query(Email)
        .filter(
            Email.campaign_id == campaign_id
        )
        .count()
    )

    if total_emails == 0:
        return

    unfinished_emails = (
        db.query(Email)
        .filter(
            Email.campaign_id == campaign_id,
            Email.status.notin_(
                ["sent", "opened", "failed"]
            )
        )
        .count()
    )

    if unfinished_emails > 0:
        campaign.status = "running"
        db.commit()
        return

    failed_emails = (
        db.query(Email)
        .filter(
            Email.campaign_id == campaign_id,
            Email.status == "failed"
        )
        .count()
    )

    if failed_emails > 0:
        campaign.status = "failed"
    else:
        campaign.status = "completed"

    db.commit()


@celery_app.task(
    bind=True,
    max_retries=3
)
def send_email_task(
    self,
    email_id: int
):
    db = SessionLocal()

    try:
        email_log = (
            db.query(Email)
            .filter(
                Email.id == email_id
            )
            .first()
        )

        if not email_log:
            raise RuntimeError(
                f"Email log {email_id} not found"
            )

        # Already successfully sent/opened.
        if email_log.status in {"sent", "opened"}:
            if email_log.campaign_id is not None:
                update_campaign_status_if_complete(
                    db,
                    email_log.campaign_id
                )

            return {
                "email_id": email_id,
                "status": email_log.status
            }

        # Verify campaign/contact relationship.
        if email_log.campaign_id is not None:
            contact = (
                db.query(Contact)
                .join(
                    CampaignContact,
                    CampaignContact.contact_id == Contact.id
                )
                .filter(
                    Contact.id == email_log.contact_id,
                    CampaignContact.campaign_id == email_log.campaign_id
                )
                .first()
            )
        else:
            contact = (
                db.query(Contact)
                .filter(
                    Contact.id == email_log.contact_id
                )
                .first()
            )

        if not contact:
            email_log.status = "failed"
            db.commit()

            if email_log.campaign_id is not None:
                update_campaign_status_if_complete(
                    db,
                    email_log.campaign_id
                )

            return {
                "email_id": email_id,
                "status": "failed"
            }

        # -------------------------------------------------
        # CONTROLLED FAILURE MODE FOR E2E TESTING
        # -------------------------------------------------

        force_failure = os.getenv(
            "FORCE_EMAIL_FAILURE",
            "false"
        ).lower() == "true"

        if force_failure:
            raise RuntimeError(
                "FORCED EMAIL FAILURE FOR E2E TEST"
            )

        # -------------------------------------------------
        # AI generation
        # -------------------------------------------------

        ai_content = generate_email(
            contact.name,
            contact.company or "your company"
        )

        app_base_url = os.getenv(
            "APP_BASE_URL",
            "http://127.0.0.1:8000"
        ).rstrip("/")

        body = f"""
        <html>
            <body>
                {ai_content}

                <img
                    src="{app_base_url}/tracking/open/{email_log.tracking_token}"
                    width="1"
                    height="1"
                    alt=""
                    style="display:none;"
                />
            </body>
        </html>
        """

        email_log.body = body

        send_email(
            contact.email,
            email_log.subject,
            body
        )

        email_log.status = "sent"
        email_log.sent_at = datetime.utcnow()

        db.commit()

        if email_log.campaign_id is not None:
            update_campaign_status_if_complete(
                db,
                email_log.campaign_id
            )

        return {
            "email_id": email_id,
            "status": "sent"
        }

    except Exception as exc:
        print(
            "EMAIL TASK ERROR:",
            repr(exc)
        )

        db.rollback()

        # Retry up to 3 times.
        if self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc,
                countdown=10
            )

        # Final failure.
        try:
            email_log = (
                db.query(Email)
                .filter(
                    Email.id == email_id
                )
                .first()
            )

            if email_log:
                email_log.status = "failed"
                db.commit()

                if email_log.campaign_id is not None:
                    update_campaign_status_if_complete(
                        db,
                        email_log.campaign_id
                    )

        except Exception as final_error:
            print(
                "FINAL EMAIL STATUS ERROR:",
                repr(final_error)
            )
            db.rollback()

        raise

    finally:
        db.close()