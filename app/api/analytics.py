
from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.email import Email
from app.models.email_click_event import EmailClickEvent
from app.models.user import User
from app.models.contact import Contact
from app.models.campaign import Campaign
from app.core.dependencies import get_current_user


router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
)


@router.get("/")
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total_contacts = (
        db.query(Contact)
        .filter(Contact.user_id == current_user.id)
        .count()
    )

    total_campaigns = (
        db.query(Campaign)
        .filter(Campaign.user_id == current_user.id)
        .count()
    )

    user_contact_ids = (
        select(Contact.id)
        .where(Contact.user_id == current_user.id)
    )

    emails = (
        db.query(Email)
        .filter(Email.contact_id.in_(user_contact_ids))
    )

    total_emails = emails.count()
    sent = emails.filter(Email.status == "sent").count()
    opened = emails.filter(Email.status == "opened").count()
    failed = emails.filter(Email.status == "failed").count()
    pending = emails.filter(Email.status == "pending").count()
    sending = emails.filter(Email.status == "sending").count()
    delivery_unknown = emails.filter(
        Email.status == "delivery_unknown"
    ).count()

    delivered = sent + opened

    open_rate = (
        round((opened / delivered) * 100, 2)
        if delivered > 0 else 0.0
    )

    # -----------------------------------------------------
    # OVERALL CLICK ANALYTICS
    # -----------------------------------------------------

    click_stats = (
        db.query(
            func.count(EmailClickEvent.id).label("total_clicks"),
            func.count(
                func.distinct(EmailClickEvent.email_id)
            ).label("unique_clicked_emails"),
        )
        .join(
            Email,
            Email.id == EmailClickEvent.email_id,
        )
        .join(
            Contact,
            Contact.id == Email.contact_id,
        )
        .filter(
            Contact.user_id == current_user.id
        )
        .one()
    )

    total_clicks = int(click_stats.total_clicks or 0)

    unique_clicked_emails = int(
        click_stats.unique_clicked_emails or 0
    )

    click_rate = (
        round(
            (unique_clicked_emails / delivered) * 100,
            2,
        )
        if delivered > 0 else 0.0
    )

    # -----------------------------------------------------
    # PRE-AGGREGATE CLICKS PER EMAIL
    # -----------------------------------------------------

    # One row per email prevents repeated clicks from
    # inflating campaign email and delivery counts.

    clicks_by_email = (
        db.query(
            EmailClickEvent.email_id.label("email_id"),
            func.count(
                EmailClickEvent.id
            ).label("click_count"),
        )
        .group_by(
            EmailClickEvent.email_id
        )
        .subquery()
    )

    # -----------------------------------------------------
    # CAMPAIGN ANALYTICS
    # -----------------------------------------------------

    campaign_stats = (
        db.query(
            Campaign.id.label("campaign_id"),
            Campaign.name.label("campaign_name"),
            Campaign.status.label("campaign_status"),

            func.count(
                Email.id
            ).label("total_emails"),

            func.coalesce(
                func.sum(
                    case(
                        (Email.status == "sent", 1),
                        else_=0,
                    )
                ),
                0,
            ).label("sent"),

            func.coalesce(
                func.sum(
                    case(
                        (Email.status == "opened", 1),
                        else_=0,
                    )
                ),
                0,
            ).label("opened"),

            func.coalesce(
                func.sum(
                    case(
                        (Email.status == "failed", 1),
                        else_=0,
                    )
                ),
                0,
            ).label("failed"),

            func.coalesce(
                func.sum(
                    case(
                        (Email.status == "pending", 1),
                        else_=0,
                    )
                ),
                0,
            ).label("pending"),

            func.coalesce(
                func.sum(
                    case(
                        (Email.status == "sending", 1),
                        else_=0,
                    )
                ),
                0,
            ).label("sending"),

            func.coalesce(
                func.sum(
                    case(
                        (Email.status == "delivery_unknown", 1),
                        else_=0,
                    )
                ),
                0,
            ).label("delivery_unknown"),

            func.coalesce(
                func.sum(clicks_by_email.c.click_count),
                0,
            ).label("total_clicks"),

            func.count(
                clicks_by_email.c.email_id
            ).label("unique_clicked_emails"),
        )
        .outerjoin(
            Email,
            Email.campaign_id == Campaign.id,
        )
        .outerjoin(
            clicks_by_email,
            clicks_by_email.c.email_id == Email.id,
        )
        .filter(
            Campaign.user_id == current_user.id
        )
        .group_by(
            Campaign.id,
            Campaign.name,
            Campaign.status,
        )
        .order_by(
            Campaign.id.desc()
        )
        .all()
    )

    campaigns = []

    for campaign in campaign_stats:
        campaign_sent = int(campaign.sent or 0)
        campaign_opened = int(campaign.opened or 0)

        campaign_delivered = (
            campaign_sent + campaign_opened
        )

        campaign_open_rate = (
            round(
                (campaign_opened / campaign_delivered) * 100,
                2,
            )
            if campaign_delivered > 0 else 0.0
        )

        campaign_total_clicks = int(
            campaign.total_clicks or 0
        )

        campaign_unique_clicked = int(
            campaign.unique_clicked_emails or 0
        )

        campaign_click_rate = (
            round(
                (
                    campaign_unique_clicked
                    / campaign_delivered
                ) * 100,
                2,
            )
            if campaign_delivered > 0 else 0.0
        )

        campaigns.append({
            "campaign_id": campaign.campaign_id,
            "campaign_name": campaign.campaign_name,
            "campaign_status": campaign.campaign_status,
            "total_emails": int(campaign.total_emails or 0),
            "sent": campaign_sent,
            "opened": campaign_opened,
            "failed": int(campaign.failed or 0),
            "pending": int(campaign.pending or 0),
            "sending": int(campaign.sending or 0),
            "delivery_unknown": int(
                campaign.delivery_unknown or 0
            ),
            "delivered": campaign_delivered,
            "open_rate": campaign_open_rate,
            "total_clicks": campaign_total_clicks,
            "unique_clicked_emails": campaign_unique_clicked,
            "click_rate": campaign_click_rate,
        })

    # -----------------------------------------------------
    # FINAL RESPONSE
    # -----------------------------------------------------

    return {
        "total_contacts": total_contacts,
        "total_campaigns": total_campaigns,
        "total_emails": total_emails,
        "sent": sent,
        "opened": opened,
        "failed": failed,
        "pending": pending,
        "sending": sending,
        "delivery_unknown": delivery_unknown,
        "delivered": delivered,
        "open_rate": open_rate,
        "total_clicks": total_clicks,
        "unique_clicked_emails": unique_clicked_emails,
        "click_rate": click_rate,
        "campaigns": campaigns,
    }
