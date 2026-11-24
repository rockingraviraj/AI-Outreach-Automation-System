"""Safe regression test for worker campaign completion status transitions.

Uses the host application's configured database. Creates only temporary rows,
never dispatches Celery tasks, and never calls AI or SMTP services.
"""
from __future__ import annotations

import secrets
import uuid

from sqlalchemy import or_

from app.db.session import SessionLocal
from app.models.user import User
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.campaign_contact import CampaignContact
from app.models.email import Email
from app.workers.email_tasks import update_campaign_status_if_complete


def expect(actual: str, expected: str, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"PASS: {label} | status={actual}")


def main() -> None:
    suffix = uuid.uuid4().hex[:12]
    test_email = f"phase3.worker.campaign.{suffix}@example.com"
    db = SessionLocal()
    print("=== WORKER CAMPAIGN STATUS REGRESSION START ===")
    print("MODE: direct status-helper test; no Celery dispatch; no AI/SMTP")
    print("REAL EMAIL DELIVERY: DISABLED")

    try:
        user = User(
            name="Phase 3 Worker Campaign Regression",
            email=test_email,
            password_hash="regression-test-only",
        )
        db.add(user)
        db.flush()

        contacts = [
            Contact(
                user_id=user.id,
                name=f"Worker Campaign Contact {i + 1}",
                email=f"phase3.worker.{suffix}.{i + 1}@example.com",
                company="Regression Test",
                status="new",
            )
            for i in range(4)
        ]
        db.add_all(contacts)
        db.flush()

        completed_campaign = Campaign(
            user_id=user.id,
            name=f"Worker Completion {suffix}",
            status="running",
        )
        failed_campaign = Campaign(
            user_id=user.id,
            name=f"Worker Failure {suffix}",
            status="running",
        )
        db.add_all([completed_campaign, failed_campaign])
        db.flush()

        associations = [
            CampaignContact(campaign_id=completed_campaign.id, contact_id=contacts[0].id),
            CampaignContact(campaign_id=completed_campaign.id, contact_id=contacts[1].id),
            CampaignContact(campaign_id=failed_campaign.id, contact_id=contacts[2].id),
            CampaignContact(campaign_id=failed_campaign.id, contact_id=contacts[3].id),
        ]
        db.add_all(associations)

        email_rows = [
            Email(
                campaign_id=completed_campaign.id,
                contact_id=contacts[0].id,
                subject="Worker completion test 1",
                body="",
                status="pending",
                tracking_token=secrets.token_urlsafe(32),
            ),
            Email(
                campaign_id=completed_campaign.id,
                contact_id=contacts[1].id,
                subject="Worker completion test 2",
                body="",
                status="sending",
                tracking_token=secrets.token_urlsafe(32),
            ),
            Email(
                campaign_id=failed_campaign.id,
                contact_id=contacts[2].id,
                subject="Worker failure test 1",
                body="",
                status="failed",
                tracking_token=secrets.token_urlsafe(32),
            ),
            Email(
                campaign_id=failed_campaign.id,
                contact_id=contacts[3].id,
                subject="Worker failure test 2",
                body="",
                status="pending",
                tracking_token=secrets.token_urlsafe(32),
            ),
        ]
        db.add_all(email_rows)
        db.commit()

        completed_campaign_id = completed_campaign.id
        failed_campaign_id = failed_campaign.id
        email_ids = [row.id for row in email_rows]
        print(
            "PASS: TEMP RECORDS CREATED | "
            f"user={user.id}; campaigns={completed_campaign_id},{failed_campaign_id}; "
            f"emails={email_ids}"
        )

        # A pending/sending email means the campaign must remain running.
        update_campaign_status_if_complete(db, completed_campaign_id)
        db.refresh(completed_campaign)
        expect(completed_campaign.status, "running", "PENDING/SENDING KEEP CAMPAIGN RUNNING")

        # Once all emails are sent/opened, the campaign must complete.
        db.query(Email).filter(Email.id == email_ids[0]).update(
            {Email.status: "sent"}, synchronize_session=False
        )
        db.query(Email).filter(Email.id == email_ids[1]).update(
            {Email.status: "opened"}, synchronize_session=False
        )
        db.commit()
        update_campaign_status_if_complete(db, completed_campaign_id)
        db.refresh(completed_campaign)
        expect(completed_campaign.status, "completed", "SENT + OPENED MARK CAMPAIGN COMPLETED")

        # A failed email plus a pending email must still leave the campaign running.
        update_campaign_status_if_complete(db, failed_campaign_id)
        db.refresh(failed_campaign)
        expect(failed_campaign.status, "running", "FAILED + PENDING KEEP CAMPAIGN RUNNING")

        # Once all emails are terminal and at least one failed, campaign must fail.
        db.query(Email).filter(Email.id == email_ids[3]).update(
            {Email.status: "sent"}, synchronize_session=False
        )
        db.commit()
        update_campaign_status_if_complete(db, failed_campaign_id)
        db.refresh(failed_campaign)
        expect(failed_campaign.status, "failed", "FINAL FAILED EMAIL MARKS CAMPAIGN FAILED")

        print("WORKER CAMPAIGN STATUS REGRESSION: PASSED")

    except Exception as exc:
        db.rollback()
        print("WORKER CAMPAIGN STATUS REGRESSION: FAILED")
        print(f"ERROR: {type(exc).__name__}: {exc}")
        raise

    finally:
        try:
            db.rollback()
            temp_user = db.query(User).filter(User.email == test_email).first()
            if temp_user:
                campaign_ids = [
                    row.id
                    for row in db.query(Campaign.id).filter(
                        Campaign.user_id == temp_user.id
                    ).all()
                ]
                contact_ids = [
                    row.id
                    for row in db.query(Contact.id).filter(
                        Contact.user_id == temp_user.id
                    ).all()
                ]

                if campaign_ids or contact_ids:
                    email_filter = []
                    if campaign_ids:
                        email_filter.append(Email.campaign_id.in_(campaign_ids))
                    if contact_ids:
                        email_filter.append(Email.contact_id.in_(contact_ids))
                    db.query(Email).filter(or_(*email_filter)).delete(
                        synchronize_session=False
                    )

                if campaign_ids:
                    db.query(CampaignContact).filter(
                        CampaignContact.campaign_id.in_(campaign_ids)
                    ).delete(synchronize_session=False)
                    db.query(Campaign).filter(
                        Campaign.id.in_(campaign_ids)
                    ).delete(synchronize_session=False)

                db.query(Contact).filter(
                    Contact.user_id == temp_user.id
                ).delete(synchronize_session=False)
                db.delete(temp_user)
                db.commit()

            leftovers = db.query(User).filter(User.email == test_email).count()
            if leftovers == 0:
                print("PASS: TEMP DATA CLEANUP | leftover_users=0")
            else:
                print(f"CLEANUP WARNING: leftover_users={leftovers}")
        except Exception as cleanup_error:
            db.rollback()
            print(f"CLEANUP ERROR: {type(cleanup_error).__name__}: {cleanup_error}")
        finally:
            db.close()
            print("=== WORKER CAMPAIGN STATUS REGRESSION END ===")


if __name__ == "__main__":
    main()
