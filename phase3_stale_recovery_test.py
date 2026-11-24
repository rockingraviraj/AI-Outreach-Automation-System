"""Controlled stale email recovery regression test.

- Uses temporary User, Contact and Email rows.
- Does not send real emails.
- Mocks Celery dispatch.
- Deletes only records created by this test.
"""

import secrets
import traceback
from datetime import datetime, timedelta
from unittest.mock import patch

from app.db.session import SessionLocal
from app.models.user import User
from app.models.contact import Contact
from app.models.email import Email
from app.workers.email_tasks import recover_stale_email_tasks


RUN_ID = secrets.token_hex(5)
TEMP_USER_EMAIL = f"stale.recovery.{RUN_ID}@example.com"
TEMP_USER_NAME = "Stale Recovery Regression"

created_email_ids = []
failures = []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"{status}: {label} | {detail}")

    if not condition:
        failures.append(label)


def load_emails(email_ids):
    db = SessionLocal()
    try:
        return {
            row.id: row
            for row in db.query(Email)
            .filter(Email.id.in_(email_ids))
            .all()
        }
    finally:
        db.close()


def cleanup():
    db = SessionLocal()

    try:
        if created_email_ids:
            db.query(Email).filter(
                Email.id.in_(created_email_ids)
            ).delete(synchronize_session=False)

        user = (
            db.query(User)
            .filter(User.email == TEMP_USER_EMAIL)
            .first()
        )

        if user:
            db.query(Contact).filter(
                Contact.user_id == user.id
            ).delete(synchronize_session=False)

            db.delete(user)

        db.commit()
        print("CLEANUP: temporary emails, contacts and user deleted.")

    except Exception:
        db.rollback()
        print("CLEANUP ERROR:")
        traceback.print_exc()
        failures.append("TEMP DATA CLEANUP")

    finally:
        db.close()


def main():
    print("=== STALE EMAIL RECOVERY REGRESSION TEST ===")
    print("SMTP: NOT CALLED")
    print("CELERY DISPATCH: MOCKED")
    print("REAL EMAIL DELIVERY: DISABLED")

    try:
        # --------------------------------------------------
        # 1. Create isolated temporary test data
        # --------------------------------------------------

        db = SessionLocal()

        try:
            user = User(
                name=TEMP_USER_NAME,
                email=TEMP_USER_EMAIL,
                password_hash=None,
            )
            db.add(user)
            db.flush()

            contact = Contact(
                user_id=user.id,
                name="Stale Recovery Test Contact",
                email=f"contact.{RUN_ID}@example.com",
                company="Regression Test",
                status="new",
            )
            db.add(contact)
            db.flush()

            now = datetime.utcnow()
            old_time = now - timedelta(minutes=20)
            recent_time = now - timedelta(minutes=2)

            safe_email = Email(
                contact_id=contact.id,
                subject="Safe Recovery Test",
                body="Temporary test email",
                status="sending",
                tracking_token=secrets.token_urlsafe(48),
                processing_token=f"test-{RUN_ID}-safe",
                processing_started_at=old_time,
                smtp_attempt_started_at=None,
                recovery_requested_at=None,
            )

            uncertain_email = Email(
                contact_id=contact.id,
                subject="Delivery Unknown Test",
                body="Temporary test email",
                status="sending",
                tracking_token=secrets.token_urlsafe(48),
                processing_token=f"test-{RUN_ID}-unknown",
                processing_started_at=old_time,
                smtp_attempt_started_at=old_time,
                recovery_requested_at=None,
            )

            recent_email = Email(
                contact_id=contact.id,
                subject="Recent Processing Test",
                body="Temporary test email",
                status="sending",
                tracking_token=secrets.token_urlsafe(48),
                processing_token=f"test-{RUN_ID}-recent",
                processing_started_at=recent_time,
                smtp_attempt_started_at=None,
                recovery_requested_at=None,
            )

            db.add_all([
                safe_email,
                uncertain_email,
                recent_email,
            ])

            db.flush()

            email_ids = {
                "safe": safe_email.id,
                "unknown": uncertain_email.id,
                "recent": recent_email.id,
            }

            created_email_ids.extend(email_ids.values())

            db.commit()

            print("Created temporary test records:")
            print(email_ids)

        finally:
            db.close()

        # --------------------------------------------------
        # 2. Run recovery task with Celery dispatch mocked
        # --------------------------------------------------

        with patch(
            "app.workers.email_tasks.send_email_task.apply_async"
        ) as dispatch_mock:

            result = recover_stale_email_tasks()

            print("\nFIRST RECOVERY RESULT:")
            print(result)

            check(
                "Recovery task scanned stale emails",
                result["stale_scanned"] >= 2,
                str(result),
            )

            check(
                "Safe stale email recovered",
                result["safely_recovered"] >= 1,
                str(result),
            )

            check(
                "SMTP-started stale email marked delivery_unknown",
                result["delivery_unknown"] >= 1,
                str(result),
            )

            check(
                "Recovery task dispatched one email",
                dispatch_mock.call_count == 1,
                f"dispatch_calls={dispatch_mock.call_count}",
            )

            if dispatch_mock.call_count:
                dispatched_args = dispatch_mock.call_args.kwargs.get("args")

                check(
                    "Only safe email was dispatched",
                    dispatched_args == [email_ids["safe"]],
                    f"dispatched_args={dispatched_args}",
                )

        # --------------------------------------------------
        # 3. Verify resulting database states
        # --------------------------------------------------

        rows = load_emails(list(email_ids.values()))

        safe = rows[email_ids["safe"]]
        unknown = rows[email_ids["unknown"]]
        recent = rows[email_ids["recent"]]

        check(
            "Safe stale email is pending",
            safe.status == "pending",
            f"status={safe.status}",
        )

        check(
            "Safe email ownership cleared",
            safe.processing_token is None
            and safe.processing_started_at is None,
            f"token={safe.processing_token}, "
            f"started_at={safe.processing_started_at}",
        )

        check(
            "Safe email has recovery marker",
            safe.recovery_requested_at is not None,
            f"recovery_requested_at={safe.recovery_requested_at}",
        )

        check(
            "Uncertain email is delivery_unknown",
            unknown.status == "delivery_unknown",
            f"status={unknown.status}",
        )

        check(
            "Uncertain email ownership cleared",
            unknown.processing_token is None
            and unknown.processing_started_at is None,
            f"token={unknown.processing_token}, "
            f"started_at={unknown.processing_started_at}",
        )

        check(
            "Uncertain email was not automatically resent",
            unknown.status == "delivery_unknown",
            "SMTP attempt had already started",
        )

        check(
            "Recent email remains sending",
            recent.status == "sending",
            f"status={recent.status}",
        )

        # --------------------------------------------------
        # 4. Verify dispatch failure preserves retry marker
        # --------------------------------------------------

        db = SessionLocal()

        try:
            safe = (
                db.query(Email)
                .filter(Email.id == email_ids["safe"])
                .first()
            )

            # Make the marker old enough to be eligible again.
            safe.recovery_requested_at = (
                datetime.utcnow() - timedelta(minutes=6)
            )

            expected_marker = safe.recovery_requested_at
            db.commit()

        finally:
            db.close()

        with patch(
            "app.workers.email_tasks.send_email_task.apply_async",
            side_effect=RuntimeError("Simulated broker failure"),
        ) as failed_dispatch_mock:

            failure_result = recover_stale_email_tasks()

            print("\nDISPATCH FAILURE RESULT:")
            print(failure_result)

            check(
                "Dispatch failure was recorded",
                failure_result["dispatch_errors"] >= 1,
                str(failure_result),
            )

            check(
                "Dispatch failure was attempted",
                failed_dispatch_mock.call_count == 1,
                f"dispatch_calls={failed_dispatch_mock.call_count}",
            )

        rows = load_emails([email_ids["safe"]])
        safe_after_failure = rows[email_ids["safe"]]

        check(
            "Email remains pending after dispatch failure",
            safe_after_failure.status == "pending",
            f"status={safe_after_failure.status}",
        )

        check(
            "Recovery marker retained after dispatch failure",
            safe_after_failure.recovery_requested_at == expected_marker,
            f"expected={expected_marker}, "
            f"actual={safe_after_failure.recovery_requested_at}",
        )

    except Exception:
        print("\nTEST EXECUTION ERROR:")
        traceback.print_exc()
        failures.append("TEST EXECUTION")

    finally:
        cleanup()

    print("\n=== FINAL RESULT ===")

    if failures:
        print(f"FAILED: {len(failures)}")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("ALL STALE RECOVERY CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())