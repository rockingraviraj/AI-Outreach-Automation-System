from datetime import datetime
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.email import Email
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.models.campaign_contact import CampaignContact
from app.models.user import User

from app.core.dependencies import get_current_user
from app.services.ai_service import generate_email
from app.services.email_service import send_email
from app.workers.email_tasks import send_email_task


router = APIRouter(
    prefix="/email",
    tags=["Email"]
)


def get_app_base_url() -> str:
    return os.getenv(
        "APP_BASE_URL",
        "http://127.0.0.1:8000"
    ).rstrip("/")


def generate_tracking_token() -> str:
    return secrets.token_urlsafe(48)


# =========================================================
# SINGLE CONTACT EMAIL
# POST /email/send-to-contact/{contact_id}
# =========================================================

@router.post("/send-to-contact/{contact_id}")
def send_to_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == contact_id,
            Contact.user_id == current_user.id
        )
        .first()
    )

    if not contact:
        raise HTTPException(
            status_code=404,
            detail="Contact not found"
        )

    subject = "Hello from AI Outreach System"

    email_log = Email(
        contact_id=contact.id,
        subject=subject,
        body="",
        status="pending",
        tracking_token=generate_tracking_token()
    )

    db.add(email_log)
    db.commit()
    db.refresh(email_log)

    try:
        ai_content = generate_email(
            contact.name,
            contact.company or "your company"
        )

        tracking_url = (
            f"{get_app_base_url()}"
            f"/tracking/open/{email_log.tracking_token}"
        )

        body = f"""
        <html>
            <body>
                {ai_content}

                <img
                    src="{tracking_url}"
                    width="1"
                    height="1"
                    alt=""
                    style="display:none;"
                />
            </body>
        </html>
        """

        success = send_email(
            contact.email,
            subject,
            body
        )

        email_log.body = body

        if success:
            email_log.status = "sent"
            email_log.sent_at = datetime.utcnow()
        else:
            email_log.status = "failed"

        db.commit()

        return {
            "email_id": email_log.id,
            "status": email_log.status
        }

    except Exception as exc:
        print("EMAIL SEND ERROR:", repr(exc))

        db.rollback()

        try:
            failed_log = (
                db.query(Email)
                .filter(
                    Email.id == email_log.id
                )
                .first()
            )

            if failed_log:
                failed_log.status = "failed"
                db.commit()

        except Exception as db_error:
            print("EMAIL DB ERROR:", repr(db_error))
            db.rollback()

        raise HTTPException(
            status_code=502,
            detail="Email delivery failed"
        )


# =========================================================
# SYNC CAMPAIGN
# POST /email/send-campaign/{campaign_id}
# =========================================================

@router.post("/send-campaign/{campaign_id}")
def send_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.user_id == current_user.id
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found"
        )

    if campaign.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Only draft campaigns can be executed"
        )

    contacts = (
        db.query(Contact)
        .join(
            CampaignContact,
            CampaignContact.contact_id == Contact.id
        )
        .filter(
            CampaignContact.campaign_id == campaign.id,
            Contact.user_id == current_user.id
        )
        .all()
    )

    if not contacts:
        raise HTTPException(
            status_code=400,
            detail="No contacts selected for this campaign"
        )

    campaign.status = "running"
    db.commit()

    results = []

    try:
        for contact in contacts:
            existing_email = (
                db.query(Email)
                .filter(
                    Email.campaign_id == campaign.id,
                    Email.contact_id == contact.id,
                    Email.status.in_(
                        ["pending", "sent", "opened"]
                    )
                )
                .first()
            )

            if existing_email:
                results.append({
                    "email_id": existing_email.id,
                    "contact": contact.email,
                    "status": existing_email.status,
                    "skipped": True
                })
                continue

            subject = "Campaign Email"

            email_log = Email(
                campaign_id=campaign.id,
                contact_id=contact.id,
                subject=subject,
                body="",
                status="pending",
                tracking_token=generate_tracking_token()
            )

            db.add(email_log)
            db.commit()
            db.refresh(email_log)

            try:
                ai_content = generate_email(
                    contact.name,
                    contact.company or "your company"
                )

                tracking_url = (
                    f"{get_app_base_url()}"
                    f"/tracking/open/{email_log.tracking_token}"
                )

                body = f"""
                <html>
                    <body>
                        {ai_content}

                        <img
                            src="{tracking_url}"
                            width="1"
                            height="1"
                            alt=""
                            style="display:none;"
                        />
                    </body>
                </html>
                """

                success = send_email(
                    contact.email,
                    subject,
                    body
                )

                email_log.body = body

                if success:
                    email_log.status = "sent"
                    email_log.sent_at = datetime.utcnow()
                else:
                    email_log.status = "failed"

                db.commit()

                results.append({
                    "email_id": email_log.id,
                    "contact": contact.email,
                    "status": email_log.status
                })

            except Exception as exc:
                print(
                    "CAMPAIGN EMAIL ERROR:",
                    repr(exc)
                )

                db.rollback()

                failed_log = (
                    db.query(Email)
                    .filter(
                        Email.id == email_log.id
                    )
                    .first()
                )

                if failed_log:
                    failed_log.status = "failed"
                    db.commit()

                results.append({
                    "email_id": email_log.id,
                    "contact": contact.email,
                    "status": "failed"
                })

        failed_count = sum(
            1
            for result in results
            if result.get("status") == "failed"
        )

        campaign.status = (
            "failed"
            if failed_count > 0
            else "completed"
        )

        db.commit()

    except Exception as exc:
        print(
            "CAMPAIGN EXECUTION ERROR:",
            repr(exc)
        )

        db.rollback()

        campaign = (
            db.query(Campaign)
            .filter(
                Campaign.id == campaign_id,
                Campaign.user_id == current_user.id
            )
            .first()
        )

        if campaign:
            campaign.status = "failed"
            db.commit()

        raise HTTPException(
            status_code=500,
            detail="Campaign execution failed"
        )

    return {
        "message": "Campaign executed",
        "campaign_id": campaign.id,
        "status": campaign.status,
        "results": results
    }


# =========================================================
# ASYNC CAMPAIGN
# POST /email/send-campaign-async/{campaign_id}
# =========================================================

@router.post("/send-campaign-async/{campaign_id}")
def send_campaign_async(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.user_id == current_user.id
        )
        .first()
    )

    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found"
        )

    if campaign.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Only draft campaigns can be executed"
        )

    contacts = (
        db.query(Contact)
        .join(
            CampaignContact,
            CampaignContact.contact_id == Contact.id
        )
        .filter(
            CampaignContact.campaign_id == campaign.id,
            Contact.user_id == current_user.id
        )
        .all()
    )

    if not contacts:
        raise HTTPException(
            status_code=400,
            detail="No contacts selected for this campaign"
        )

    queued_ids = []

    for contact in contacts:
        existing_email = (
            db.query(Email)
            .filter(
                Email.campaign_id == campaign.id,
                Email.contact_id == contact.id,
                Email.status.in_(
                    ["pending", "sent", "opened"]
                )
            )
            .first()
        )

        if existing_email:
            continue

        email_log = Email(
            campaign_id=campaign.id,
            contact_id=contact.id,
            subject="Async Campaign Email",
            body="",
            status="pending",
            tracking_token=generate_tracking_token()
        )

        db.add(email_log)
        db.flush()

        queued_ids.append(email_log.id)

    if not queued_ids:
        return {
            "message": "No new contacts to queue",
            "campaign_id": campaign.id,
            "status": campaign.status,
            "emails_queued": 0,
            "email_ids": []
        }

    campaign.status = "running"

    try:
        db.commit()

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Unable to queue campaign"
        )

    try:
        for email_id in queued_ids:
            send_email_task.delay(email_id)

    except Exception as exc:
        print(
            "CELERY QUEUE ERROR:",
            repr(exc)
        )

        campaign = (
            db.query(Campaign)
            .filter(
                Campaign.id == campaign_id,
                Campaign.user_id == current_user.id
            )
            .first()
        )

        if campaign:
            campaign.status = "failed"
            db.commit()

        raise HTTPException(
            status_code=503,
            detail="Unable to queue campaign tasks"
        )

    return {
        "message": "Campaign queued successfully",
        "campaign_id": campaign.id,
        "status": campaign.status,
        "emails_queued": len(queued_ids),
        "email_ids": queued_ids
    }