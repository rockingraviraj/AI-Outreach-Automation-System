from datetime import datetime, timedelta
import logging

import app.models

from sqlalchemy import or_, update

from app.core.celery_worker import celery_app
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.email import Email
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.campaign_contact import CampaignContact
from app.services.ai_service import generate_email
from app.services.email_service import send_email
from app.services.tracking_service import build_tracked_email_body


logger = logging.getLogger(__name__)

# A sending lease older than this is considered stale. This is deliberately
# longer than the SMTP timeout and normal AI request duration.
STALE_PROCESSING_SECONDS = 15 * 60
RECOVERY_BATCH_SIZE = 100
RECOVERY_REDISPATCH_SECONDS = 5 * 60


TERMINAL_EMAIL_STATUSES = (
    "sent",
    "opened",
    "failed",
    "delivery_unknown",
)


def update_campaign_status_if_complete(
    db,
    campaign_id: int,
):
    campaign = (
        db.query(Campaign)
        .filter(Campaign.id == campaign_id)
        .first()
    )

    if not campaign:
        return

    total_emails = (
        db.query(Email)
        .filter(Email.campaign_id == campaign_id)
        .count()
    )

    if total_emails == 0:
        return

    unfinished_emails = (
        db.query(Email)
        .filter(
            Email.campaign_id == campaign_id,
            Email.status.notin_(TERMINAL_EMAIL_STATUSES),
        )
        .count()
    )

    if unfinished_emails > 0:
        campaign.status = "running"
        db.commit()
        return

    unsuccessful_emails = (
        db.query(Email)
        .filter(
            Email.campaign_id == campaign_id,
            Email.status.in_(("failed", "delivery_unknown")),
        )
        .count()
    )

    campaign.status = "failed" if unsuccessful_emails > 0 else "completed"
    db.commit()


def claim_email(
    db,
    email_id: int,
    processing_token: str,
):
    now = datetime.utcnow()
    result = db.execute(
        update(Email)
        .where(
            Email.id == email_id,
            Email.status == "pending",
        )
        .values(
            status="sending",
            processing_token=processing_token,
            processing_started_at=now,
            smtp_attempt_started_at=None,
            recovery_requested_at=None,
        )
    )

    if result.rowcount == 1:
        db.commit()
        return "claimed"

    db.rollback()

    email_log = (
        db.query(Email)
        .filter(Email.id == email_id)
        .first()
    )

    if not email_log:
        raise RuntimeError(f"Email log {email_id} not found")

    if email_log.status in {"sent", "opened"}:
        return "completed"

    if email_log.status == "delivery_unknown":
        return "delivery_unknown"

    if (
        email_log.status == "sending"
        and email_log.processing_token == processing_token
    ):
        return "owned"

    if email_log.status == "sending":
        return "processing"

    if email_log.status == "failed":
        return "failed"

    return "unavailable"


def release_email_claim_for_retry(
    db,
    email_id: int,
    processing_token: str,
):
    """Release only a pre-SMTP claim so a Celery retry can claim it again."""
    result = db.execute(
        update(Email)
        .where(
            Email.id == email_id,
            Email.status == "sending",
            Email.processing_token == processing_token,
            Email.smtp_attempt_started_at.is_(None),
        )
        .values(
            status="pending",
            processing_token=None,
            processing_started_at=None,
            recovery_requested_at=datetime.utcnow(),
        )
    )

    db.commit()
    return result.rowcount == 1


def mark_email_failed_if_owned(
    db,
    email_id: int,
    processing_token: str,
):
    """Mark a pre-SMTP failure only while this task still owns the claim."""
    email_log = (
        db.query(Email)
        .filter(
            Email.id == email_id,
            Email.status == "sending",
            Email.processing_token == processing_token,
            Email.smtp_attempt_started_at.is_(None),
        )
        .first()
    )

    if not email_log:
        return False

    campaign_id = email_log.campaign_id
    result = db.execute(
        update(Email)
        .where(
            Email.id == email_id,
            Email.status == "sending",
            Email.processing_token == processing_token,
            Email.smtp_attempt_started_at.is_(None),
        )
        .values(
            status="failed",
            processing_token=None,
            processing_started_at=None,
            recovery_requested_at=None,
        )
    )
    db.commit()

    if result.rowcount == 1 and campaign_id is not None:
        update_campaign_status_if_complete(db, campaign_id)

    return result.rowcount == 1


def mark_smtp_attempt_started(
    db,
    email_id: int,
    processing_token: str,
):
    """Durably record the SMTP boundary before making the external call."""
    result = db.execute(
        update(Email)
        .where(
            Email.id == email_id,
            Email.status == "sending",
            Email.processing_token == processing_token,
            Email.smtp_attempt_started_at.is_(None),
        )
        .values(
            smtp_attempt_started_at=datetime.utcnow(),
        )
    )

    if result.rowcount == 1:
        db.commit()
        return True

    db.rollback()
    return False


def mark_email_sent_if_owned(
    db,
    email_id: int,
    processing_token: str,
):
    """Persist success only if the task still owns an SMTP-started claim."""
    result = db.execute(
        update(Email)
        .where(
            Email.id == email_id,
            Email.status == "sending",
            Email.processing_token == processing_token,
            Email.smtp_attempt_started_at.is_not(None),
        )
        .values(
            status="sent",
            sent_at=datetime.utcnow(),
            processing_token=None,
            processing_started_at=None,
            recovery_requested_at=None,
        )
    )
    db.commit()

    if result.rowcount != 1:
        return False

    campaign_id = (
        db.query(Email.campaign_id)
        .filter(Email.id == email_id)
        .scalar()
    )
    if campaign_id is not None:
        update_campaign_status_if_complete(db, campaign_id)

    return True


def mark_email_delivery_unknown_if_owned(
    db,
    email_id: int,
    processing_token: str,
):
    """Never automatically retry after the SMTP side-effect boundary."""
    email_log = (
        db.query(Email)
        .filter(
            Email.id == email_id,
            Email.status == "sending",
            Email.processing_token == processing_token,
            Email.smtp_attempt_started_at.is_not(None),
        )
        .first()
    )

    if not email_log:
        return False

    campaign_id = email_log.campaign_id
    result = db.execute(
        update(Email)
        .where(
            Email.id == email_id,
            Email.status == "sending",
            Email.processing_token == processing_token,
            Email.smtp_attempt_started_at.is_not(None),
        )
        .values(
            status="delivery_unknown",
            processing_token=None,
            processing_started_at=None,
            recovery_requested_at=None,
        )
    )
    db.commit()

    if result.rowcount == 1 and campaign_id is not None:
        update_campaign_status_if_complete(db, campaign_id)

    return result.rowcount == 1


def get_email_status(db, email_id: int):
    return (
        db.query(Email.status)
        .filter(Email.id == email_id)
        .scalar()
    )


@celery_app.task(
    bind=True,
    max_retries=3,
)
def send_email_task(
    self,
    email_id: int,
):
    db = SessionLocal()
    processing_token = self.request.id
    claimed_by_this_execution = False
    smtp_attempt_started = False

    try:
        if not processing_token:
            raise RuntimeError(
                "Celery task ID is required for email processing ownership"
            )

        email_log = (
            db.query(Email)
            .filter(Email.id == email_id)
            .first()
        )

        if not email_log:
            raise RuntimeError(f"Email log {email_id} not found")

        if email_log.status in {"sent", "opened"}:
            if email_log.campaign_id is not None:
                update_campaign_status_if_complete(
                    db,
                    email_log.campaign_id,
                )
            return {"email_id": email_id, "status": email_log.status}

        if email_log.status == "delivery_unknown":
            return {"email_id": email_id, "status": "delivery_unknown"}

        claim_status = claim_email(db, email_id, processing_token)
        claimed_by_this_execution = claim_status == "claimed"

        if claim_status == "owned":
            return {"email_id": email_id, "status": "already_processing"}
        if claim_status == "completed":
            return {"email_id": email_id, "status": "already_completed"}
        if claim_status == "processing":
            return {"email_id": email_id, "status": "already_processing"}
        if claim_status == "failed":
            return {"email_id": email_id, "status": "failed"}
        if claim_status == "delivery_unknown":
            return {"email_id": email_id, "status": "delivery_unknown"}
        if claim_status == "unavailable":
            return {"email_id": email_id, "status": "unavailable"}

        email_log = (
            db.query(Email)
            .filter(Email.id == email_id)
            .first()
        )

        if not email_log:
            raise RuntimeError(f"Email log {email_id} not found after claim")

        if email_log.campaign_id is not None:
            contact = (
                db.query(Contact)
                .join(
                    CampaignContact,
                    CampaignContact.contact_id == Contact.id,
                )
                .filter(
                    Contact.id == email_log.contact_id,
                    CampaignContact.campaign_id == email_log.campaign_id,
                )
                .first()
            )
        else:
            contact = (
                db.query(Contact)
                .filter(Contact.id == email_log.contact_id)
                .first()
            )

        if not contact:
            marked_failed = mark_email_failed_if_owned(
                db,
                email_id,
                processing_token,
            )
            claimed_by_this_execution = False
            return {
                "email_id": email_id,
                "status": "failed" if marked_failed else (get_email_status(db, email_id) or "unavailable"),
            }

        # Controlled pre-SMTP failure for integration testing.
        if settings.FORCE_EMAIL_FAILURE:
            raise RuntimeError("FORCED EMAIL FAILURE FOR E2E TEST")

        ai_content = generate_email(
            contact.name,
            contact.company or "your company",
        )

        body = build_tracked_email_body(
           ai_content=ai_content,
           tracking_token=email_log.tracking_token,
           destination_url=email_log.destination_url,
        )

        # Persist the generated body while the claim is still in the
        # pre-SMTP phase. If this database write fails, the task can safely
        # release its claim and retry without classifying delivery as unknown.
        email_log.body = body
        db.commit()

        # Re-validate ownership and durably persist the SMTP boundary
        # immediately before calling the external mail server. If recovery
        # won the race, do not send.
        smtp_attempt_started = mark_smtp_attempt_started(
            db,
            email_id,
            processing_token,
        )

        if not smtp_attempt_started:
            claimed_by_this_execution = False
            return {
                "email_id": email_id,
                "status": get_email_status(db, email_id) or "ownership_lost",
            }

        success = send_email(
            contact.email,
            email_log.subject,
            body,
        )

        if not success:
            raise RuntimeError("Email delivery result is uncertain")

        marked_sent = mark_email_sent_if_owned(
            db,
            email_id,
            processing_token,
        )
        claimed_by_this_execution = False

        if not marked_sent:
            return {
                "email_id": email_id,
                "status": get_email_status(db, email_id) or "ownership_lost",
            }

        return {"email_id": email_id, "status": "sent"}

    except Exception as exc:
        logger.exception("EMAIL TASK ERROR: %r", exc)
        db.rollback()

        # Once SMTP might have been contacted, do not retry automatically.
        # The SMTP server may have accepted the message before a timeout/crash.
        if smtp_attempt_started:
            try:
                marked_unknown = mark_email_delivery_unknown_if_owned(
                    db,
                    email_id,
                    processing_token,
                )
                logger.warning(
                    "EMAIL DELIVERY UNKNOWN RECORDED: %s",
                    marked_unknown,
                )
            except Exception:
                db.rollback()
                logger.exception("FAILED TO RECORD DELIVERY_UNKNOWN")
            raise

        if self.request.retries < self.max_retries:
            if claimed_by_this_execution:
                try:
                    released = release_email_claim_for_retry(
                        db,
                        email_id,
                        processing_token,
                    )
                    logger.warning("EMAIL RETRY CLAIM RELEASED: %s", released)
                except Exception:
                    db.rollback()
                    logger.exception("EMAIL RETRY CLAIM RELEASE ERROR")
                    raise

            raise self.retry(exc=exc, countdown=10)

        try:
            if claimed_by_this_execution:
                marked_failed = mark_email_failed_if_owned(
                    db,
                    email_id,
                    processing_token,
                )
                logger.warning("EMAIL FINAL FAILURE RECORDED: %s", marked_failed)
        except Exception:
            db.rollback()
            logger.exception("FINAL EMAIL STATUS ERROR")

        raise

    finally:
        db.close()


@celery_app.task(
    name="app.workers.email_tasks.recover_stale_email_tasks",
)
def recover_stale_email_tasks():
    """Recover stale pre-SMTP claims and quarantine ambiguous SMTP attempts."""
    db = SessionLocal()
    now = datetime.utcnow()
    stale_cutoff = now - timedelta(seconds=STALE_PROCESSING_SECONDS)
    redispatch_cutoff = now - timedelta(seconds=RECOVERY_REDISPATCH_SECONDS)

    safely_recovered_ids = []
    delivery_unknown_count = 0
    dispatched_count = 0
    dispatch_errors = 0

    try:
        stale_rows = (
            db.query(
                Email.id,
                Email.campaign_id,
                Email.processing_token,
                Email.processing_started_at,
                Email.smtp_attempt_started_at,
            )
            .filter(
                Email.status == "sending",
                or_(
                    Email.processing_started_at.is_(None),
                    Email.processing_started_at <= stale_cutoff,
                ),
            )
            .order_by(Email.processing_started_at.asc().nullsfirst())
            .limit(RECOVERY_BATCH_SIZE)
            .all()
        )

        for row in stale_rows:
            ownership_conditions = [
                Email.id == row.id,
                Email.status == "sending",
                Email.processing_token == row.processing_token,
            ]

            if row.processing_started_at is None:
                ownership_conditions.append(Email.processing_started_at.is_(None))
            else:
                ownership_conditions.append(
                    Email.processing_started_at == row.processing_started_at
                )

            if row.smtp_attempt_started_at is None:
                ownership_conditions.append(Email.smtp_attempt_started_at.is_(None))
                result = db.execute(
                    update(Email)
                    .where(*ownership_conditions)
                    .values(
                        status="pending",
                        processing_token=None,
                        processing_started_at=None,
                        recovery_requested_at=now,
                    )
                )
                db.commit()

                if result.rowcount == 1:
                    safely_recovered_ids.append(row.id)
                    logger.warning(
                        "STALE PRE-SMTP EMAIL RELEASED FOR RECOVERY: %s",
                        row.id,
                    )
            else:
                ownership_conditions.append(
                    Email.smtp_attempt_started_at == row.smtp_attempt_started_at
                )
                result = db.execute(
                    update(Email)
                    .where(*ownership_conditions)
                    .values(
                        status="delivery_unknown",
                        processing_token=None,
                        processing_started_at=None,
                        recovery_requested_at=None,
                    )
                )
                db.commit()

                if result.rowcount == 1:
                    delivery_unknown_count += 1
                    logger.error(
                        "STALE POST-SMTP EMAIL QUARANTINED AS DELIVERY_UNKNOWN: %s",
                        row.id,
                    )
                    if row.campaign_id is not None:
                        update_campaign_status_if_complete(db, row.campaign_id)

        # Re-dispatch recovered pending rows. Keep the marker until a worker
        # actually claims the row; if broker publication fails, a later scan
        # can retry. A successful claim clears recovery_requested_at.
        dispatch_conditions = [
            Email.recovery_requested_at <= redispatch_cutoff,
        ]
        if safely_recovered_ids:
            dispatch_conditions.append(Email.id.in_(safely_recovered_ids))

        candidates = (
            db.query(Email.id, Email.recovery_requested_at)
            .filter(
                Email.status == "pending",
                Email.recovery_requested_at.is_not(None),
                or_(*dispatch_conditions),
            )
            .order_by(Email.recovery_requested_at.asc())
            .limit(RECOVERY_BATCH_SIZE)
            .all()
        )

        for candidate in candidates:
            try:
                send_email_task.apply_async(args=[candidate.id])
                dispatched_count += 1
                db.execute(
                    update(Email)
                    .where(
                        Email.id == candidate.id,
                        Email.status == "pending",
                        Email.recovery_requested_at == candidate.recovery_requested_at,
                    )
                    .values(recovery_requested_at=datetime.utcnow())
                )
                db.commit()
            except Exception:
                db.rollback()
                dispatch_errors += 1
                logger.exception(
                    "FAILED TO RE-DISPATCH RECOVERED EMAIL %s",
                    candidate.id,
                )

        return {
            "stale_scanned": len(stale_rows),
            "safely_recovered": len(safely_recovered_ids),
            "delivery_unknown": delivery_unknown_count,
            "recovery_tasks_dispatched": dispatched_count,
            "dispatch_errors": dispatch_errors,
        }

    finally:
        db.close()
