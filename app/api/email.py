from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.session import get_db
from app.models.email import Email
from app.models.contact import Contact
from app.services.email_service import send_email
from app.workers.email_tasks import send_email_task
from app.services.ai_service import generate_email

router = APIRouter(prefix="/email", tags=["Email"])


# 🔥 SINGLE CONTACT EMAIL (WITH AI + TRACKING)
@router.post("/send-to-contact/{contact_id}")
def send_to_contact(contact_id: int, db: Session = Depends(get_db)):

    contact = db.query(Contact).filter(Contact.id == contact_id).first()

    if not contact:
        return {"error": "Contact not found"}

    # ✅ Create log FIRST
    email_log = Email(
        contact_id=contact.id,
        subject="Hello from AI System",
        body="",
        status="pending"
    )
    db.add(email_log)
    db.commit()
    db.refresh(email_log)

    # 🔥 AI CONTENT
    ai_content = generate_email(contact.name, contact.company)

    # ✅ Final body (AI + tracking)
    body = f"""
{ai_content}

<img src="http://127.0.0.1:8000/tracking/open/{email_log.id}" />
"""

    success = send_email(contact.email, "Hello from AI System", body)

    # ✅ Update log
    email_log.body = body
    email_log.status = "sent" if success else "failed"
    email_log.sent_at = datetime.utcnow() if success else None

    db.commit()

    return {"status": email_log.status}


# 🔥 BULK CAMPAIGN (SYNC + AI)
@router.post("/send-campaign/{campaign_id}")
def send_campaign(campaign_id: int, db: Session = Depends(get_db)):

    contacts = db.query(Contact).all()

    if not contacts:
        return {"error": "No contacts found"}

    results = []

    for contact in contacts:

        # ✅ Create log first
        email_log = Email(
            campaign_id=campaign_id,
            contact_id=contact.id,
            subject="Campaign Email 🚀",
            body="",
            status="pending"
        )
        db.add(email_log)
        db.commit()
        db.refresh(email_log)

        # 🔥 AI CONTENT
        ai_content = generate_email(contact.name, contact.company)

        # ✅ Final body
        body = f"""
{ai_content}

<img src="http://127.0.0.1:8000/tracking/open/{email_log.id}" />
"""

        success = send_email(contact.email, "Campaign Email 🚀", body)

        email_log.body = body
        email_log.status = "sent" if success else "failed"
        email_log.sent_at = datetime.utcnow() if success else None

        db.commit()

        results.append({
            "contact": contact.email,
            "status": email_log.status
        })

    return {
        "message": "Campaign executed",
        "results": results
    }


# 🔥 BULK CAMPAIGN (ASYNC - CELERY + AI)
@router.post("/send-campaign-async/{campaign_id}")
def send_campaign_async(campaign_id: int, db: Session = Depends(get_db)):

    contacts = db.query(Contact).all()

    if not contacts:
        return {"error": "No contacts found"}

    for contact in contacts:

        # ✅ Create log first
        email_log = Email(
            campaign_id=campaign_id,
            contact_id=contact.id,
            subject="Async Campaign 🚀",
            body="",
            status="pending"
        )
        db.add(email_log)
        db.commit()
        db.refresh(email_log)

        # 🔥 AI CONTENT
        ai_content = generate_email(contact.name, contact.company)

        # ✅ Final body
        body = f"""
{ai_content}

<img src="http://127.0.0.1:8000/tracking/open/{email_log.id}" />
"""

        # ✅ Send to queue
        send_email_task.delay(contact.email, "Async Campaign 🚀", body)

        # Save body
        email_log.body = body
        db.commit()

    return {"message": "Campaign queued successfully"}