"""Controlled same-Celery-task-ID concurrency regression test.

Runs two local executions of the same Celery task ID against one temporary
Email row. The first execution is deliberately paused after it has claimed
the row and entered mocked AI generation. Only then is the duplicate
execution started. This avoids a two-party barrier, because the expected-safe
behaviour is that the duplicate exits before it reaches AI generation.

AI generation and SMTP are mocked. No Celery broker task is dispatched and no
real email is sent. Temporary DB records are removed in a finally block.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any
from unittest.mock import patch

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.contact import Contact
from app.models.email import Email
from app.models.user import User
from app.workers.email_tasks import send_email_task


def main() -> int:
    if settings.FORCE_EMAIL_FAILURE:
        print("ABORT: FORCE_EMAIL_FAILURE must be False for this test.")
        return 2

    marker = uuid.uuid4().hex[:12]
    user_email = f"worker.sameid.{marker}@example.com"
    contact_email = f"worker.sameid.contact.{marker}@example.com"
    task_id = f"same-task-{marker}"

    user_id: int | None = None
    contact_id: int | None = None
    email_id: int | None = None

    first_generate_entered = threading.Event()
    release_first_generate = threading.Event()
    lock = threading.Lock()
    generate_calls = 0
    send_calls = 0

    print("=== SAME TASK ID CONCURRENCY TEST START ===")
    print("MODE: ordered local concurrent execution; AI and SMTP mocked")
    print("REAL EMAIL DELIVERY: DISABLED")
    print("TASK ID:", task_id)

    db = SessionLocal()
    try:
        user = User(
            name="Worker Same-ID Regression",
            email=user_email,
            password_hash=None,
            is_verified=False,
        )
        db.add(user)
        db.flush()
        user_id = user.id

        contact = Contact(
            user_id=user.id,
            name="Worker Regression Contact",
            email=contact_email,
            company="Regression Test",
            status="new",
        )
        db.add(contact)
        db.flush()
        contact_id = contact.id

        email_log = Email(
            campaign_id=None,
            contact_id=contact.id,
            subject="Same task ID concurrency regression",
            body="",
            status="pending",
            tracking_token=uuid.uuid4().hex + uuid.uuid4().hex,
        )
        db.add(email_log)
        db.commit()
        db.refresh(email_log)
        email_id = email_log.id
        print(
            f"PASS: TEMP RECORDS CREATED | user={user_id}; "
            f"contact={contact_id}; email={email_id}"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    def mocked_generate_email(name: str, company: str) -> str:
        nonlocal generate_calls
        with lock:
            generate_calls += 1
            call_number = generate_calls

        # Hold only the first execution. The duplicate invocation is allowed
        # to finish so the test can observe whether it reaches SMTP as well.
        if call_number == 1:
            first_generate_entered.set()
            if not release_first_generate.wait(timeout=20):
                raise TimeoutError("Timed out waiting to release first AI generation")

        return "Mocked regression email body"

    def mocked_send_email(to_email: str, subject: str, body: str) -> bool:
        nonlocal send_calls
        with lock:
            send_calls += 1
        return True

    def execute_same_task() -> dict[str, Any]:
        result = send_email_task.apply(
            args=[email_id],
            task_id=task_id,
            throw=False,
        )
        value = result.result
        if isinstance(value, dict):
            return value
        return {"result": repr(value), "state": result.state}

    first_result: dict[str, Any] | None = None
    second_result: dict[str, Any] | None = None
    execution_error: str | None = None

    try:
        with patch(
            "app.workers.email_tasks.generate_email",
            side_effect=mocked_generate_email,
        ), patch(
            "app.workers.email_tasks.send_email",
            side_effect=mocked_send_email,
        ):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first_future = pool.submit(execute_same_task)

                if not first_generate_entered.wait(timeout=10):
                    raise RuntimeError(
                        "First task did not reach mocked AI generation; "
                        "it may have failed before claiming the email."
                    )

                # At this point the first invocation has claimed the email
                # (status=sending, processing_token=task_id) and is paused.
                second_future = pool.submit(execute_same_task)

                try:
                    second_result = second_future.result(timeout=10)
                except Exception as exc:
                    execution_error = (
                        f"Second execution: {type(exc).__name__}: {exc}"
                    )
                finally:
                    # Always release the first task before waiting for it.
                    release_first_generate.set()

                try:
                    first_result = first_future.result(timeout=20)
                except Exception as exc:
                    execution_error = execution_error or (
                        f"First execution: {type(exc).__name__}: {exc}"
                    )

        check_db = SessionLocal()
        try:
            final_email = (
                check_db.query(Email)
                .filter(Email.id == email_id)
                .first()
            )
            final_status = final_email.status if final_email else "MISSING"
            final_processing_token = (
                final_email.processing_token if final_email else None
            )
        finally:
            check_db.close()

        print("FIRST TASK RESULT:", first_result)
        print("SECOND TASK RESULT:", second_result)
        print("GENERATE CALLS:", generate_calls)
        print("MOCK SMTP SEND CALLS:", send_calls)
        print("FINAL EMAIL STATUS:", final_status)
        print("PROCESSING TOKEN CLEARED:", final_processing_token is None)

        if execution_error:
            print("FAIL: TASK EXECUTION ERROR:", execution_error)
            return 1

        second_status = (second_result or {}).get("status")
        first_status = (first_result or {}).get("status")

        if (
            generate_calls == 1
            and send_calls == 1
            and first_status == "sent"
            and second_status == "already_processing"
            and final_status in {"sent", "opened"}
            and final_processing_token is None
        ):
            print("PASS: SAME TASK ID DID NOT DUPLICATE THE SEND")
            return 0

        if send_calls > 1:
            print("GAP: SAME TASK ID CAUSED DUPLICATE SEND EXECUTION")
            return 1

        print(
            "FAIL: Unexpected concurrency result; review task results "
            "and worker ownership state."
        )
        return 1

    finally:
        # Do not leave the first invocation blocked if an earlier assertion
        # or test operation raises unexpectedly.
        release_first_generate.set()
        cleanup = SessionLocal()
        try:
            if email_id is not None:
                cleanup.query(Email).filter(Email.id == email_id).delete(
                    synchronize_session=False
                )
            if contact_id is not None:
                cleanup.query(Contact).filter(Contact.id == contact_id).delete(
                    synchronize_session=False
                )
            if user_id is not None:
                cleanup.query(User).filter(User.id == user_id).delete(
                    synchronize_session=False
                )
            cleanup.commit()
            remaining = (
                cleanup.query(User).filter(User.email == user_email).count()
                if user_id is not None
                else 0
            )
            print("CLEANUP: temporary email, contact, and user removed")
            print("LEFTOVER TEMP USERS:", remaining)
        except Exception as cleanup_error:
            cleanup.rollback()
            print("CLEANUP ERROR:", repr(cleanup_error))
        finally:
            cleanup.close()
        print("=== SAME TASK ID CONCURRENCY TEST END ===")


if __name__ == "__main__":
    raise SystemExit(main())
