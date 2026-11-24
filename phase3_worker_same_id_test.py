"""Controlled same-Celery-task-ID concurrency regression test.

This runs the Celery task body locally in two threads with the SAME task ID.
The worker module's generate_email and send_email functions are mocked, so no
OpenAI or SMTP requests are made and no Celery broker task is dispatched.
Temporary DB rows are removed in a finally block.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
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

    barrier = threading.Barrier(2)
    lock = threading.Lock()
    generate_calls = 0
    send_calls = 0
    generated_task_ids: list[str | None] = []

    print("=== SAME TASK ID CONCURRENCY TEST START ===")
    print("MODE: local concurrent task execution; AI and SMTP mocked")
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
        print(f"PASS: TEMP RECORDS CREATED | user={user_id}; contact={contact_id}; email={email_id}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    def mocked_generate_email(name: str, company: str) -> str:
        nonlocal generate_calls
        with lock:
            generate_calls += 1
        # Hold the first execution until the second invocation also reaches
        # message generation. If the second invocation is correctly rejected
        # as already processing, this barrier times out and the test reports
        # that only one invocation reached this point.
        barrier.wait(timeout=12)
        return "Mocked regression email body"

    def mocked_send_email(to_email: str, subject: str, body: str) -> bool:
        nonlocal send_calls
        with lock:
            send_calls += 1
        return True

    def execute_same_task() -> dict[str, Any]:
        # apply() executes synchronously in this calling thread while creating
        # a Celery request context with the supplied task ID.
        result = send_email_task.apply(
            args=[email_id],
            task_id=task_id,
            throw=False,
        )
        value = result.result
        if isinstance(value, dict):
            return value
        return {"result": repr(value), "state": result.state}

    results: list[dict[str, Any]] = []
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
                futures = [pool.submit(execute_same_task) for _ in range(2)]
                for future in futures:
                    try:
                        results.append(future.result(timeout=25))
                    except Exception as exc:  # report test execution errors
                        execution_error = f"{type(exc).__name__}: {exc}"
                        results.append({"exception": execution_error})

        check_db = SessionLocal()
        try:
            final_email = check_db.query(Email).filter(Email.id == email_id).first()
            final_status = final_email.status if final_email else "MISSING"
            final_processing_token = (
                final_email.processing_token if final_email else None
            )
        finally:
            check_db.close()

        print("TASK RESULTS:", results)
        print("GENERATE CALLS:", generate_calls)
        print("MOCK SMTP SEND CALLS:", send_calls)
        print("FINAL EMAIL STATUS:", final_status)
        print("PROCESSING TOKEN CLEARED:", final_processing_token is None)

        # The desired safety property is exactly one mocked send invocation.
        # A count of two confirms the same-task-ID race in the current worker.
        if execution_error:
            print("FAIL: TASK EXECUTION ERROR:", execution_error)
            return 1
        if send_calls == 1 and final_status in {"sent", "opened"} and final_processing_token is None:
            print("PASS: SAME TASK ID DID NOT DUPLICATE THE SEND")
            return 0
        if send_calls > 1:
            print("GAP: SAME TASK ID CAUSED DUPLICATE SEND EXECUTION")
            return 1
        print("INCONCLUSIVE: Expected one send; inspect task results and barrier behaviour.")
        return 2

    finally:
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
