"""Targeted Celery worker retry regression test.

Runs send_email_task locally with Celery's eager Task.apply() path. It tests:
1) A transient AI-generation failure followed by a successful retry.
2) Persistent AI-generation failures exhausting max_retries and recording
   the final email status as failed.

The database records are temporary. AI and SMTP are mocked. No Celery broker
messages are published and no real email is sent.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.contact import Contact
from app.models.email import Email
from app.models.user import User
from app.workers.email_tasks import send_email_task


def create_test_records(label: str, marker: str) -> tuple[int, int, int]:
    db = SessionLocal()
    try:
        user = User(
            name=f"Worker Retry Regression {label}",
            email=f"worker.retry.{label.lower()}.{marker}@example.com",
            password_hash=None,
            is_verified=False,
        )
        db.add(user)
        db.flush()

        contact = Contact(
            user_id=user.id,
            name=f"Retry Regression Contact {label}",
            email=f"worker.retry.contact.{label.lower()}.{marker}@example.com",
            company="Regression Test",
            status="new",
        )
        db.add(contact)
        db.flush()

        email_log = Email(
            campaign_id=None,
            contact_id=contact.id,
            subject=f"Worker retry regression {label}",
            body="",
            status="pending",
            tracking_token=uuid.uuid4().hex + uuid.uuid4().hex,
        )
        db.add(email_log)
        db.commit()
        db.refresh(email_log)
        return user.id, contact.id, email_log.id
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def read_email_state(email_id: int) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        row = db.query(Email).filter(Email.id == email_id).first()
        if row is None:
            return None
        return {
            "status": row.status,
            "processing_token": row.processing_token,
            "processing_started_at": row.processing_started_at,
            "sent_at": row.sent_at,
        }
    finally:
        db.close()


def cleanup_records(user_id: int | None, contact_id: int | None, email_id: int | None) -> None:
    db = SessionLocal()
    try:
        if email_id is not None:
            db.query(Email).filter(Email.id == email_id).delete(synchronize_session=False)
        if contact_id is not None:
            db.query(Contact).filter(Contact.id == contact_id).delete(synchronize_session=False)
        if user_id is not None:
            db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_transient_failure_then_success(marker: str) -> bool:
    user_id = contact_id = email_id = None
    generate_calls = 0
    send_calls = 0
    observed_claims: list[tuple[str | None, str | None]] = []
    release_observations: list[tuple[bool, str | None, str | None]] = []

    task_id = f"retry-success-{marker}"
    print("\n--- TEST 1: TRANSIENT FAILURE THEN SUCCESS ---")
    print("TASK ID:", task_id)

    try:
        user_id, contact_id, email_id = create_test_records("Transient", marker)
        print(f"PASS: TEMP RECORDS CREATED | user={user_id}; contact={contact_id}; email={email_id}")

        from app.workers import email_tasks as worker_module
        original_release = worker_module.release_email_claim_for_retry

        def mock_generate(name: str, company: str) -> str:
            nonlocal generate_calls
            generate_calls += 1
            state = read_email_state(email_id)
            observed_claims.append((state["status"], state["processing_token"]))
            if generate_calls == 1:
                raise RuntimeError("MOCK TRANSIENT AI FAILURE")
            return "Mocked email body after successful retry"

        def observe_release(db, target_email_id: int, processing_token: str) -> bool:
            released = original_release(db, target_email_id, processing_token)
            state = read_email_state(target_email_id)
            release_observations.append(
                (released, state["status"], state["processing_token"])
            )
            return released

        def mock_send(to_email: str, subject: str, body: str) -> bool:
            nonlocal send_calls
            send_calls += 1
            return True

        with patch(
            "app.workers.email_tasks.generate_email",
            side_effect=mock_generate,
        ), patch(
            "app.workers.email_tasks.send_email",
            side_effect=mock_send,
        ), patch(
            "app.workers.email_tasks.release_email_claim_for_retry",
            side_effect=observe_release,
        ):
            result = send_email_task.apply(
                args=[email_id],
                task_id=task_id,
                retries=0,
                throw=False,
            )

        final_state = read_email_state(email_id)
        result_value = result.result if isinstance(result.result, dict) else repr(result.result)

        print("TASK RESULT:", result_value)
        print("TASK STATE:", result.state)
        print("GENERATE CALLS:", generate_calls)
        print("MOCK SMTP SEND CALLS:", send_calls)
        print("OBSERVED PROCESSING CLAIMS:", observed_claims)
        print("RETRY RELEASE OBSERVATIONS:", release_observations)
        print("FINAL EMAIL STATE:", final_state)

        expected = (
            result.successful()
            and isinstance(result.result, dict)
            and result.result.get("status") == "sent"
            and generate_calls == 2
            and send_calls == 1
            and len(release_observations) == 1
            and release_observations[0] == (True, "pending", None)
            and len(observed_claims) == 2
            and all(status == "sending" and token == task_id for status, token in observed_claims)
            and final_state is not None
            and final_state["status"] == "sent"
            and final_state["processing_token"] is None
            and final_state["processing_started_at"] is None
        )

        if expected:
            print("PASS: TRANSIENT FAILURE RELEASED CLAIM AND RETRY SUCCEEDED")
            return True

        print("FAIL: TRANSIENT RETRY DID NOT MATCH EXPECTED BEHAVIOUR")
        return False

    except Exception as exc:
        print("FAIL: TRANSIENT RETRY TEST ERROR:", type(exc).__name__, str(exc))
        return False
    finally:
        cleanup_records(user_id, contact_id, email_id)
        print("CLEANUP: transient test records removed")


def run_exhausted_retries(marker: str) -> bool:
    user_id = contact_id = email_id = None
    generate_calls = 0
    send_calls = 0
    release_observations: list[tuple[bool, str | None, str | None]] = []
    final_failure_observations: list[tuple[bool, str | None, str | None]] = []

    task_id = f"retry-exhausted-{marker}"
    print("\n--- TEST 2: MAX RETRIES EXHAUSTED ---")
    print("TASK ID:", task_id)

    try:
        user_id, contact_id, email_id = create_test_records("Exhausted", marker)
        print(f"PASS: TEMP RECORDS CREATED | user={user_id}; contact={contact_id}; email={email_id}")

        from app.workers import email_tasks as worker_module
        original_release = worker_module.release_email_claim_for_retry
        original_mark_failed = worker_module.mark_email_failed_if_owned

        def mock_generate(name: str, company: str) -> str:
            nonlocal generate_calls
            generate_calls += 1
            raise RuntimeError("MOCK PERMANENT AI FAILURE")

        def observe_release(db, target_email_id: int, processing_token: str) -> bool:
            released = original_release(db, target_email_id, processing_token)
            state = read_email_state(target_email_id)
            release_observations.append(
                (released, state["status"], state["processing_token"])
            )
            return released

        def observe_final_failure(db, target_email_id: int, processing_token: str) -> bool:
            marked = original_mark_failed(db, target_email_id, processing_token)
            state = read_email_state(target_email_id)
            final_failure_observations.append(
                (marked, state["status"], state["processing_token"])
            )
            return marked

        def mock_send(to_email: str, subject: str, body: str) -> bool:
            nonlocal send_calls
            send_calls += 1
            return True

        with patch(
            "app.workers.email_tasks.generate_email",
            side_effect=mock_generate,
        ), patch(
            "app.workers.email_tasks.send_email",
            side_effect=mock_send,
        ), patch(
            "app.workers.email_tasks.release_email_claim_for_retry",
            side_effect=observe_release,
        ), patch(
            "app.workers.email_tasks.mark_email_failed_if_owned",
            side_effect=observe_final_failure,
        ):
            result = send_email_task.apply(
                args=[email_id],
                task_id=task_id,
                retries=0,
                throw=False,
            )

        final_state = read_email_state(email_id)
        print("TASK STATE:", result.state)
        print("TASK RESULT TYPE:", type(result.result).__name__)
        print("GENERATE CALLS:", generate_calls)
        print("MOCK SMTP SEND CALLS:", send_calls)
        print("RETRY RELEASE OBSERVATIONS:", release_observations)
        print("FINAL FAILURE OBSERVATIONS:", final_failure_observations)
        print("FINAL EMAIL STATE:", final_state)

        expected = (
            result.failed()
            and generate_calls == send_email_task.max_retries + 1
            and send_calls == 0
            and len(release_observations) == send_email_task.max_retries
            and all(item == (True, "pending", None) for item in release_observations)
            and len(final_failure_observations) == 1
            and final_failure_observations[0] == (True, "failed", None)
            and final_state is not None
            and final_state["status"] == "failed"
            and final_state["processing_token"] is None
            and final_state["processing_started_at"] is None
        )

        if expected:
            print("PASS: MAX RETRIES EXHAUSTED AND EMAIL MARKED FAILED")
            return True

        print("FAIL: MAX-RETRY FINAL STATE DID NOT MATCH EXPECTED BEHAVIOUR")
        return False

    except Exception as exc:
        print("FAIL: MAX-RETRY TEST ERROR:", type(exc).__name__, str(exc))
        return False
    finally:
        cleanup_records(user_id, contact_id, email_id)
        print("CLEANUP: exhausted-retry test records removed")


def main() -> int:
    if settings.FORCE_EMAIL_FAILURE:
        print("ABORT: FORCE_EMAIL_FAILURE must be False; this test mocks AI failures.")
        return 2

    marker = uuid.uuid4().hex[:12]
    print("=== WORKER RETRY REGRESSION START ===")
    print("MODE: local Celery Task.apply(); AI and SMTP mocked")
    print("REAL EMAIL DELIVERY: DISABLED")
    print("REAL CELERY BROKER DISPATCH: DISABLED")
    print("MAX_RETRIES:", send_email_task.max_retries)

    transient_ok = run_transient_failure_then_success(marker)
    exhausted_ok = run_exhausted_retries(marker)

    db = SessionLocal()
    try:
        leftover = (
            db.query(User)
            .filter(User.email.like(f"worker.retry.%{marker}@example.com"))
            .count()
        )
    finally:
        db.close()

    print("\n=== WORKER RETRY REGRESSION SUMMARY ===")
    print("TRANSIENT RETRY:", "PASS" if transient_ok else "FAIL")
    print("MAX-RETRY FAILURE:", "PASS" if exhausted_ok else "FAIL")
    print("LEFTOVER TEMP USERS:", leftover)

    if transient_ok and exhausted_ok and leftover == 0:
        print("WORKER RETRY REGRESSION: PASSED")
        return 0

    print("WORKER RETRY REGRESSION: FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
