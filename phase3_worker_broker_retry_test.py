"""Real Redis/Celery broker retry test with forced worker-side failure.

Run from the project root on the host after starting the isolated worker
that consumes only the `worker-test` queue with FORCE_EMAIL_FAILURE=true.
No SMTP delivery is possible because the worker raises before AI/SMTP calls.
"""

from __future__ import annotations

import secrets
import time
import uuid
from datetime import datetime

from celery.result import AsyncResult
from sqlalchemy import text

from app.core.config import settings
from app.core.celery_worker import celery_app
from app.db.session import SessionLocal
from app.models.user import User
from app.models.contact import Contact
from app.models.email import Email
from app.workers.email_tasks import send_email_task


def main() -> int:
    print("=== REAL REDIS/CELERY BROKER RETRY TEST START ===")
    print("MODE: Host creates temporary DB records; real Redis broker; isolated worker")
    print("WORKER SAFETY: FORCE_EMAIL_FAILURE must be true on worker-test consumer")
    print("REAL SMTP DELIVERY: BLOCKED BEFORE AI/SMTP BY FORCED FAILURE")
    print("QUEUE: worker-test")
    print("MAX_RETRIES:", send_email_task.max_retries)

    if send_email_task.max_retries != 3:
        print("FAIL: Expected max_retries=3")
        return 1

    db = SessionLocal()
    user_id = contact_id = email_id = None
    task_result: AsyncResult | None = None
    terminal = False
    success = False
    run_id = uuid.uuid4().hex[:12]
    task_id = f"broker-retry-{run_id}"

    try:
        # Confirm host database and Redis configuration are reachable.
        db.execute(text("SELECT 1")).scalar_one()
        print("PASS: HOST DATABASE CONNECTION")
        print("BROKER URL CONFIGURED:", bool(settings.REDIS_URL))

        user = User(
            name=f"Broker Retry Test {run_id}",
            email=f"phase3.broker.retry.{run_id}@example.com",
            password_hash=None,
        )
        db.add(user)
        db.flush()
        user_id = user.id

        contact = Contact(
            user_id=user.id,
            name=f"Broker Retry Contact {run_id}",
            email=f"phase3.broker.contact.{run_id}@example.com",
            company="Regression Test",
            status="new",
        )
        db.add(contact)
        db.flush()
        contact_id = contact.id

        email = Email(
            campaign_id=None,
            contact_id=contact.id,
            subject=f"Broker retry regression {run_id}",
            body="",
            status="pending",
            tracking_token=secrets.token_urlsafe(48),
        )
        db.add(email)
        db.commit()
        db.refresh(email)
        email_id = email.id
        print(
            f"PASS: TEMP RECORDS CREATED | user={user_id}; "
            f"contact={contact_id}; email={email_id}"
        )

        task_result = send_email_task.apply_async(
            args=[email_id],
            task_id=task_id,
            queue="worker-test",
        )
        print("TASK DISPATCHED:", task_result.id)
        print("WAITING FOR BROKER TASK AND 3 RETRIES (UP TO 110 SECONDS)...")

        try:
            # The expected terminal state is FAILURE because the test worker
            # intentionally raises before AI generation and SMTP delivery.
            task_result.get(timeout=110, propagate=False)
        except Exception as wait_error:
            # A timeout or backend error must not trigger cleanup while the
            # broker could still deliver/retry this task.
            print("TASK RESULT WAIT ERROR:", repr(wait_error))

        state = task_result.state
        terminal = state in {"SUCCESS", "FAILURE", "REVOKED"}
        print("CELERY TASK STATE:", state)

        db.expire_all()
        final_email = db.query(Email).filter(Email.id == email_id).one_or_none()
        if final_email is None:
            print("FAIL: Email row disappeared before verification")
            terminal = True
            return 1

        final_status = final_email.status
        processing_token = final_email.processing_token
        processing_started_at = final_email.processing_started_at
        sent_at = final_email.sent_at

        print("FINAL EMAIL STATUS:", final_status)
        print("PROCESSING TOKEN CLEARED:", processing_token is None)
        print("PROCESSING TIMESTAMP CLEARED:", processing_started_at is None)
        print("SENT_AT IS NULL:", sent_at is None)

        checks = {
            "Celery task ended in FAILURE": state == "FAILURE",
            "Email persisted as failed": final_status == "failed",
            "Processing token cleared": processing_token is None,
            "Processing timestamp cleared": processing_started_at is None,
            "No sent_at timestamp": sent_at is None,
        }
        for label, passed in checks.items():
            print(("PASS" if passed else "FAIL") + ": " + label)

        success = all(checks.values())
        terminal = terminal or success
        print("BROKER RETRY TEST:", "PASSED" if success else "FAILED")
        return 0 if success else 1

    except Exception as exc:
        db.rollback()
        print("TEST ERROR:", repr(exc))
        return 1

    finally:
        # Do not delete records if a timed-out task might still be executing
        # or scheduled for retry. That would make a later broker delivery hit
        # a missing Email/Contact row.
        if terminal and email_id is not None:
            try:
                db.rollback()
                db.query(Email).filter(Email.id == email_id).delete(synchronize_session=False)
                if contact_id is not None:
                    db.query(Contact).filter(Contact.id == contact_id).delete(synchronize_session=False)
                if user_id is not None:
                    db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
                db.commit()
                print("CLEANUP: temporary email, contact, and user removed")
                if user_id is not None:
                    leftovers = (
                        db.query(User)
                        .filter(User.id == user_id)
                        .count()
                    )
                    print("LEFTOVER TEMP USERS:", leftovers)
            except Exception as cleanup_error:
                db.rollback()
                print("CLEANUP ERROR:", repr(cleanup_error))
        elif email_id is not None:
            print(
                "CLEANUP SKIPPED: task is not confirmed terminal; "
                f"preserved email_id={email_id}, contact_id={contact_id}, user_id={user_id}. "
                "Inspect worker/queue before manual cleanup."
            )

        db.close()
        print("=== REAL REDIS/CELERY BROKER RETRY TEST END ===")


if __name__ == "__main__":
    raise SystemExit(main())
