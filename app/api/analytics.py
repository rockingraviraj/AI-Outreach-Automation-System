from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.email import Email
from app.models.user import User
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.core.dependencies import get_current_user


router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"]
)


# =========================================================
# OVERALL ANALYTICS
# GET /analytics/
# =========================================================

@router.get("/")
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # -----------------------------------------------------
    # CONTACTS
    # -----------------------------------------------------

    total_contacts = (
        db.query(Contact)
        .filter(
            Contact.user_id == current_user.id
        )
        .count()
    )

    # -----------------------------------------------------
    # CAMPAIGNS
    # -----------------------------------------------------

    total_campaigns = (
        db.query(Campaign)
        .filter(
            Campaign.user_id == current_user.id
        )
        .count()
    )

    # -----------------------------------------------------
    # USER EMAILS
    # -----------------------------------------------------

    user_contact_ids = (
        db.query(Contact.id)
        .filter(
            Contact.user_id == current_user.id
        )
        .subquery()
    )

    emails = (
        db.query(Email)
        .filter(
            Email.contact_id.in_(user_contact_ids)
        )
    )

    total_emails = emails.count()

    sent = (
        emails
        .filter(
            Email.status == "sent"
        )
        .count()
    )

    opened = (
        emails
        .filter(
            Email.status == "opened"
        )
        .count()
    )

    failed = (
        emails
        .filter(
            Email.status == "failed"
        )
        .count()
    )

    pending = (
        emails
        .filter(
            Email.status == "pending"
        )
        .count()
    )

    # OPENED emails are no longer in "sent" status.
    # Therefore delivered = sent + opened.
    delivered = sent + opened

    open_rate = 0.0

    if delivered > 0:
        open_rate = round(
            (opened / delivered) * 100,
            2
        )

    # -----------------------------------------------------
    # CAMPAIGN-WISE ANALYTICS
    # -----------------------------------------------------

    campaign_stats = (
        db.query(
            Campaign.id.label("campaign_id"),
            Campaign.name.label("campaign_name"),
            Campaign.status.label("campaign_status"),

            func.count(Email.id).label("total_emails"),

            func.coalesce(
                func.sum(
                    case(
                        (
                            Email.status == "sent",
                            1
                        ),
                        else_=0
                    )
                ),
                0
            ).label("sent"),

            func.coalesce(
                func.sum(
                    case(
                        (
                            Email.status == "opened",
                            1
                        ),
                        else_=0
                    )
                ),
                0
            ).label("opened"),

            func.coalesce(
                func.sum(
                    case(
                        (
                            Email.status == "failed",
                            1
                        ),
                        else_=0
                    )
                ),
                0
            ).label("failed"),

            func.coalesce(
                func.sum(
                    case(
                        (
                            Email.status == "pending",
                            1
                        ),
                        else_=0
                    )
                ),
                0
            ).label("pending"),
        )
        .outerjoin(
            Email,
            Email.campaign_id == Campaign.id
        )
        .filter(
            Campaign.user_id == current_user.id
        )
        .group_by(
            Campaign.id,
            Campaign.name,
            Campaign.status
        )
        .order_by(
            Campaign.id.desc()
        )
        .all()
    )

    campaigns = []

    for campaign in campaign_stats:
        campaign_sent = int(
            campaign.sent or 0
        )

        campaign_opened = int(
            campaign.opened or 0
        )

        campaign_failed = int(
            campaign.failed or 0
        )

        campaign_pending = int(
            campaign.pending or 0
        )

        campaign_total = int(
            campaign.total_emails or 0
        )

        campaign_delivered = (
            campaign_sent + campaign_opened
        )

        campaign_open_rate = 0.0

        if campaign_delivered > 0:
            campaign_open_rate = round(
                (
                    campaign_opened
                    / campaign_delivered
                ) * 100,
                2
            )

        campaigns.append({
            "campaign_id": campaign.campaign_id,
            "campaign_name": campaign.campaign_name,
            "campaign_status": campaign.campaign_status,
            "total_emails": campaign_total,
            "sent": campaign_sent,
            "opened": campaign_opened,
            "failed": campaign_failed,
            "pending": campaign_pending,
            "delivered": campaign_delivered,
            "open_rate": campaign_open_rate,
        })

    return {
        "total_contacts": total_contacts,
        "total_campaigns": total_campaigns,
        "total_emails": total_emails,
        "sent": sent,
        "opened": opened,
        "failed": failed,
        "pending": pending,
        "delivered": delivered,
        "open_rate": open_rate,
        "campaigns": campaigns,
    }