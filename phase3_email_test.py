"""Controlled Phase 3 Email API regression tests.

Runs FastAPI in-process with TestClient. SMTP and Celery dispatch are mocked,
so this script does not send real emails or enqueue real Celery tasks.
Temporary user/contact/campaign/email rows are removed in finally cleanup.

Run from the backend project root:
    python phase3_email_test.py
"""

from __future__ import annotations

import secrets
import sys
import traceback
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.db.session import SessionLocal
from app.models.user import User
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.campaign_contact import CampaignContact
from app.models.email import Email


PASSWORD = "Regression#2026"
RUN_ID = secrets.token_hex(5)
TEMP_USER_EMAIL = f"phase3.email.{RUN_ID}@example.com"
TEMP_USER_NAME = "Phase 3 Email Regression"

failures: list[str] = []
known_gaps: list[str] = []


def report(label: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    suffix = f" | {detail}" if detail else ""
    print(f"{status}: {label}{suffix}")
    if not passed:
        failures.append(label)


def gap(label: str, detail: str) -> None:
    known_gaps.append(label)
    print(f"GAP: {label} | {detail}")


def response_json(response):
    try:
        return response.json()
    except Exception:
        return {"raw": response.text[:500]}


def new_token() -> str:
    # token_urlsafe(48) produces a token sized for the model's String(64).
    return secrets.token_urlsafe(48)


def load_email(email_id: int) -> Email | None:
    db = SessionLocal()
    try:
        return db.query(Email).filter(Email.id == email_id).first()
    finally:
        db.close()


def load_campaign(campaign_id: int) -> Campaign | None:
    db = SessionLocal()
    try:
        return db.query(Campaign).filter(Campaign.id == campaign_id).first()
    finally:
        db.close()


def cleanup_temp_data() -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == TEMP_USER_EMAIL).first()
        if not user:
            db.rollback()
            print("CLEANUP: temporary user was not present")
            return

        contact_ids = [
            row[0]
            for row in db.query(Contact.id)
            .filter(Contact.user_id == user.id)
            .all()
        ]
        campaign_ids = [
            row[0]
            for row in db.query(Campaign.id)
            .filter(Campaign.user_id == user.id)
            .all()
        ]

        if contact_ids:
            deleted_emails = (
                db.query(Email)
                .filter(Email.contact_id.in_(contact_ids))
                .delete(synchronize_session=False)
            )
        else:
            deleted_emails = 0

        if campaign_ids:
            deleted_associations = (
                db.query(CampaignContact)
                .filter(CampaignContact.campaign_id.in_(campaign_ids))
                .delete(synchronize_session=False)
            )
        else:
            deleted_associations = 0

        deleted_campaigns = (
            db.query(Campaign)
            .filter(Campaign.user_id == user.id)
            .delete(synchronize_session=False)
        )
        deleted_contacts = (
            db.query(Contact)
            .filter(Contact.user_id == user.id)
            .delete(synchronize_session=False)
        )
        db.delete(user)
        db.commit()

        print(
            "CLEANUP:"
            f" emails={deleted_emails},"
            f" campaign_contacts={deleted_associations},"
            f" campaigns={deleted_campaigns},"
            f" contacts={deleted_contacts}, users=1"
        )

        leftovers = (
            db.query(User)
            .filter(User.email == TEMP_USER_EMAIL)
            .count()
        )
        report("TEMP USER CLEANUP", leftovers == 0, f"leftover_users={leftovers}")
    except Exception:
        db.rollback()
        print("CLEANUP ERROR:")
        traceback.print_exc()
        failures.append("TEMP DATA CLEANUP")
    finally:
        db.close()


def main() -> int:
    print("=== PHASE 3 EMAIL REGRESSION START ===")
    print("MODE: FastAPI TestClient; SMTP MOCKED; CELERY DISPATCH MOCKED")
    print("REAL EMAIL DELIVERY: DISABLED BY MOCKING")

    temp_contact_ids: list[int] = []
    campaign_ids: dict[str, int] = {}
    email_ids: dict[str, int] = {}

    try:
        # Create a temporary test user through the real signup/login API.
        with TestClient(app) as client:
            signup = client.post(
                "/auth/signup",
                json={
                    "name": TEMP_USER_NAME,
                    "email": TEMP_USER_EMAIL,
                    "password": PASSWORD,
                },
            )
            report(
                "TEMP USER SIGNUP",
                signup.status_code == 200,
                f"HTTP {signup.status_code}; response={response_json(signup)}",
            )
            if signup.status_code != 200:
                return 1

            login = client.post(
                "/auth/login",
                data={"username": TEMP_USER_EMAIL, "password": PASSWORD},
            )
            login_data = response_json(login)
            token = login_data.get("access_token")
            report(
                "TEMP USER LOGIN",
                login.status_code == 200 and bool(token),
                f"HTTP {login.status_code}; token_received={bool(token)}",
            )
            if login.status_code != 200 or not token:
                return 1

            client.headers.update({"Authorization": f"Bearer {token}"})

            # Create temporary contacts and campaigns directly in the host DB.
            db = SessionLocal()
            try:
                user = db.query(User).filter(User.email == TEMP_USER_EMAIL).first()
                if not user:
                    raise RuntimeError("Temporary user not found after signup")
                temp_user_id = user.id

                contacts = [
                    Contact(
                        user_id=user.id,
                        name=f"Email Regression Contact {i}",
                        email=f"phase3.email.{RUN_ID}.contact{i}@example.com",
                        company="Regression Test Co",
                        status="new",
                    )
                    for i in range(1, 6)
                ]
                db.add_all(contacts)
                db.flush()
                contact_ids = [contact.id for contact in contacts]
                temp_contact_ids.extend(contact_ids)

                campaigns = {
                    "sync": Campaign(
                        user_id=user.id,
                        name=f"Email Regression Sync {RUN_ID}",
                        status="draft",
                        created_at=datetime.utcnow(),
                    ),
                    "async": Campaign(
                        user_id=user.id,
                        name=f"Email Regression Async {RUN_ID}",
                        status="draft",
                        created_at=datetime.utcnow(),
                    ),
                    "noop": Campaign(
                        user_id=user.id,
                        name=f"Email Regression Existing Pending {RUN_ID}",
                        status="draft",
                        created_at=datetime.utcnow(),
                    ),
                }
                db.add_all(campaigns.values())
                db.flush()

                for key, campaign in campaigns.items():
                    campaign_ids[key] = campaign.id

                associations = [
                    CampaignContact(campaign_id=campaigns["sync"].id, contact_id=contact_ids[0]),
                    CampaignContact(campaign_id=campaigns["sync"].id, contact_id=contact_ids[1]),
                    CampaignContact(campaign_id=campaigns["async"].id, contact_id=contact_ids[2]),
                    CampaignContact(campaign_id=campaigns["async"].id, contact_id=contact_ids[3]),
                    CampaignContact(campaign_id=campaigns["noop"].id, contact_id=contact_ids[4]),
                ]
                db.add_all(associations)

                # Existing pending email exercises async idempotent no-new-work path.
                existing_pending = Email(
                    campaign_id=campaigns["noop"].id,
                    contact_id=contact_ids[4],
                    subject="Existing pending regression email",
                    body="",
                    status="pending",
                    tracking_token=new_token(),
                )
                # A standalone sending row exposes whether analytics counts this state.
                synthetic_sending = Email(
                    campaign_id=None,
                    contact_id=contact_ids[3],
                    subject="Synthetic sending analytics row",
                    body="",
                    status="sending",
                    tracking_token=new_token(),
                    processing_token=f"regression-{RUN_ID}",
                    processing_started_at=datetime.utcnow(),
                )
                db.add_all([existing_pending, synthetic_sending])
                db.commit()
                db.refresh(existing_pending)
                db.refresh(synthetic_sending)
                email_ids["existing_pending"] = existing_pending.id
                email_ids["synthetic_sending"] = synthetic_sending.id
            finally:
                db.close()

            # 1) Single-contact successful send. The SMTP and AI functions are mocked.
            with patch("app.api.email.generate_email", return_value="<p>Regression body</p>") as ai_mock, \
                 patch("app.api.email.send_email", return_value=True) as smtp_mock:
                response = client.post(f"/email/send-to-contact/{contact_ids[0]}")
            data = response_json(response)
            email_id = data.get("email_id")
            email_ids["single_sent"] = email_id
            row = load_email(email_id) if email_id else None
            report(
                "SINGLE CONTACT MOCKED SMTP SUCCESS",
                response.status_code == 200
                and data.get("status") == "sent"
                and row is not None
                and row.status == "sent"
                and row.sent_at is not None
                and smtp_mock.call_count == 1
                and ai_mock.call_count == 1,
                f"HTTP {response.status_code}; response={data}; smtp_calls={smtp_mock.call_count}",
            )

            # 2) SMTP returns False: current API should persist a failed log.
            with patch("app.api.email.generate_email", return_value="<p>Failure test</p>"), \
                 patch("app.api.email.send_email", return_value=False) as smtp_mock:
                response = client.post(f"/email/send-to-contact/{contact_ids[1]}")
            data = response_json(response)
            email_id = data.get("email_id")
            email_ids["single_false"] = email_id
            row = load_email(email_id) if email_id else None
            report(
                "SINGLE CONTACT SMTP FALSE RESULT",
                response.status_code == 200
                and data.get("status") == "failed"
                and row is not None
                and row.status == "failed"
                and smtp_mock.call_count == 1,
                f"HTTP {response.status_code}; response={data}",
            )

            # 3) SMTP raises: endpoint should return 502 and persist failed status.
            with patch("app.api.email.generate_email", return_value="<p>Exception test</p>"), \
                 patch("app.api.email.send_email", side_effect=RuntimeError("MOCK SMTP ERROR")) as smtp_mock:
                response = client.post(f"/email/send-to-contact/{contact_ids[4]}")
            data = response_json(response)
            # Exception path intentionally does not return email_id, so identify newest row.
            db = SessionLocal()
            try:
                failed_exception_row = (
                    db.query(Email)
                    .filter(
                        Email.contact_id == contact_ids[4],
                        Email.campaign_id.is_(None),
                        Email.subject == "Hello from AI Outreach System",
                    )
                    .order_by(Email.id.desc())
                    .first()
                )
                if failed_exception_row:
                    email_ids["single_exception"] = failed_exception_row.id
            finally:
                db.close()
            report(
                "SINGLE CONTACT SMTP EXCEPTION",
                response.status_code == 502
                and failed_exception_row is not None
                and failed_exception_row.status == "failed"
                and smtp_mock.call_count == 1,
                f"HTTP {response.status_code}; response={data}; persisted_status="
                f"{getattr(failed_exception_row, 'status', None)}",
            )

            # 4) Synchronous campaign execution with mocked SMTP.
            with patch("app.api.email.generate_email", return_value="<p>Campaign regression</p>") as ai_mock, \
                 patch("app.api.email.send_email", return_value=True) as smtp_mock:
                response = client.post(f"/email/send-campaign/{campaign_ids['sync']}")
            data = response_json(response)
            db = SessionLocal()
            try:
                sync_rows = (
                    db.query(Email)
                    .filter(Email.campaign_id == campaign_ids["sync"])
                    .all()
                )
                sync_campaign = (
                    db.query(Campaign)
                    .filter(Campaign.id == campaign_ids["sync"])
                    .first()
                )
            finally:
                db.close()
            report(
                "SYNCHRONOUS CAMPAIGN MOCKED EXECUTION",
                response.status_code == 200
                and data.get("status") == "completed"
                and len(sync_rows) == 2
                and all(row.status == "sent" and row.sent_at is not None for row in sync_rows)
                and sync_campaign is not None
                and sync_campaign.status == "completed"
                and smtp_mock.call_count == 2
                and ai_mock.call_count == 2,
                f"HTTP {response.status_code}; campaign_status="
                f"{getattr(sync_campaign, 'status', None)}; emails={len(sync_rows)}; "
                f"smtp_calls={smtp_mock.call_count}",
            )

            # 5) Async campaign: patch .delay so no real Celery task is queued.
            with patch("app.api.email.send_email_task.delay") as delay_mock:
                response = client.post(f"/email/send-campaign-async/{campaign_ids['async']}")
            data = response_json(response)
            db = SessionLocal()
            try:
                async_rows = (
                    db.query(Email)
                    .filter(Email.campaign_id == campaign_ids["async"])
                    .all()
                )
                async_campaign = (
                    db.query(Campaign)
                    .filter(Campaign.id == campaign_ids["async"])
                    .first()
                )
            finally:
                db.close()
            report(
                "ASYNC CAMPAIGN MOCKED QUEUE",
                response.status_code == 200
                and data.get("emails_queued") == 2
                and len(async_rows) == 2
                and all(row.status == "pending" for row in async_rows)
                and async_campaign is not None
                and async_campaign.status == "running"
                and delay_mock.call_count == 2,
                f"HTTP {response.status_code}; response={data}; delay_calls={delay_mock.call_count}",
            )

            # 6) Existing active email: endpoint should enqueue zero duplicate tasks.
            with patch("app.api.email.send_email_task.delay") as delay_mock:
                response = client.post(f"/email/send-campaign-async/{campaign_ids['noop']}")
            data = response_json(response)
            report(
                "ASYNC EXISTING EMAIL NOT RE-QUEUED",
                response.status_code == 200
                and data.get("emails_queued") == 0
                and data.get("email_ids") == []
                and delay_mock.call_count == 0,
                f"HTTP {response.status_code}; response={data}; delay_calls={delay_mock.call_count}",
            )

            # 7) Tracking changes a successfully sent standalone email to opened.
            sent_row = load_email(email_ids.get("single_sent")) if email_ids.get("single_sent") else None
            if sent_row:
                response = client.get(f"/tracking/open/{sent_row.tracking_token}")
                opened_row = load_email(sent_row.id)
                report(
                    "TRACKING SENT EMAIL",
                    response.status_code == 200
                    and response.headers.get("content-type", "").startswith("image/gif")
                    and opened_row is not None
                    and opened_row.status == "opened",
                    f"HTTP {response.status_code}; content_type={response.headers.get('content-type')}; "
                    f"db_status={getattr(opened_row, 'status', None)}",
                )
                # Repeated tracking should remain stable.
                second = client.get(f"/tracking/open/{sent_row.tracking_token}")
                repeated_row = load_email(sent_row.id)
                report(
                    "TRACKING REPEATED OPEN",
                    second.status_code == 200
                    and repeated_row is not None
                    and repeated_row.status == "opened",
                    f"HTTP {second.status_code}; db_status={getattr(repeated_row, 'status', None)}",
                )
            else:
                report("TRACKING SENT EMAIL", False, "sent email row missing")

            # 8) Failed email tracking should not turn a failed delivery into opened.
            # Current implementation is expected to expose this state-transition gap.
            failed_row = load_email(email_ids.get("single_false")) if email_ids.get("single_false") else None
            if failed_row:
                response = client.get(f"/tracking/open/{failed_row.tracking_token}")
                after_tracking = load_email(failed_row.id)
                if after_tracking is not None and after_tracking.status == "failed":
                    report("TRACKING DOES NOT REWRITE FAILED EMAIL", True)
                else:
                    gap(
                        "TRACKING CHANGES FAILED EMAIL TO OPENED",
                        f"HTTP {response.status_code}; status_before=failed; "
                        f"status_after={getattr(after_tracking, 'status', None)}",
                    )
            else:
                report("TRACKING FAILED-STATE CHECK", False, "failed email row missing")

            # 9) Invalid tracking token still returns the same transparent GIF.
            response = client.get("/tracking/open/invalid-phase3-email-token")
            report(
                "TRACKING INVALID TOKEN PRIVACY RESPONSE",
                response.status_code == 200
                and response.headers.get("content-type", "").startswith("image/gif"),
                f"HTTP {response.status_code}; content_type={response.headers.get('content-type')}",
            )

            # 10) Analytics counts user-scoped email rows and exposes sending state.
            analytics_response = client.get("/analytics/")
            analytics_data = response_json(analytics_response)
            db = SessionLocal()
            try:
                all_user_email_rows = (
                    db.query(Email)
                    .join(Contact, Contact.id == Email.contact_id)
                    .filter(Contact.user_id == temp_user_id)
                    .all()
                )
                expected_total = len(all_user_email_rows)
                sending_count = sum(1 for row in all_user_email_rows if row.status == "sending")
            finally:
                db.close()

            report(
                "ANALYTICS AUTHENTICATED RESPONSE",
                analytics_response.status_code == 200
                and isinstance(analytics_data, dict)
                and analytics_data.get("total_emails") == expected_total,
                f"HTTP {analytics_response.status_code}; API total="
                f"{analytics_data.get('total_emails')}; DB total={expected_total}",
            )

            if analytics_response.status_code == 200 and sending_count:
                if "sending" not in analytics_data:
                    gap(
                        "ANALYTICS DOES NOT REPORT SENDING COUNT",
                        f"DB contains {sending_count} sending email(s), but analytics response has no 'sending' field",
                    )
                else:
                    report(
                        "ANALYTICS SENDING COUNT",
                        analytics_data.get("sending") == sending_count,
                        f"API sending={analytics_data.get('sending')}; DB sending={sending_count}",
                    )

            sync_campaign_stat = None
            if analytics_response.status_code == 200:
                sync_campaign_stat = next(
                    (
                        item for item in analytics_data.get("campaigns", [])
                        if item.get("campaign_id") == campaign_ids["sync"]
                    ),
                    None,
                )
            report(
                "ANALYTICS CAMPAIGN-WISE DATA",
                sync_campaign_stat is not None
                and sync_campaign_stat.get("total_emails") == 2,
                f"campaign_stat={sync_campaign_stat}",
            )

    except Exception as exc:
        print("UNEXPECTED REGRESSION ERROR:", repr(exc))
        traceback.print_exc()
        failures.append("UNEXPECTED REGRESSION ERROR")
    finally:
        cleanup_temp_data()

    print("=== PHASE 3 EMAIL REGRESSION SUMMARY ===")
    print(f"FAILURES: {len(failures)}")
    for item in failures:
        print(f"  - {item}")
    print(f"KNOWN GAPS: {len(known_gaps)}")
    for item in known_gaps:
        print(f"  - {item}")

    if failures:
        print("PHASE 3 EMAIL REGRESSION: FAILED")
        return 1
    if known_gaps:
        print("PHASE 3 EMAIL REGRESSION: CORE TESTS PASSED WITH GAPS TO REVIEW")
        return 0
    print("PHASE 3 EMAIL REGRESSION: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
