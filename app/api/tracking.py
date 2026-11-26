
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.email import Email
from app.models.email_click_event import EmailClickEvent
from app.workers.email_tasks import update_campaign_status_if_complete
from app.core.url_validation import validate_http_url


router = APIRouter(
    prefix="/tracking",
    tags=["Tracking"],
)


@router.get("/open/{tracking_token}")
def track_open(
    tracking_token: str,
    db: Session = Depends(get_db),
):
    email = (
        db.query(Email)
        .filter(Email.tracking_token == tracking_token)
        .first()
    )

    # Preserve existing delivery uncertainty handling.
    if email and email.status in {"sent", "delivery_unknown"}:
        campaign_id = email.campaign_id
        email.status = "opened"
        db.commit()

        if campaign_id is not None:
            update_campaign_status_if_complete(db, campaign_id)

    # 1x1 transparent pixel
    pixel = (
        b'\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00'
        b'\x80\x00\x00\x00\x00\x00\xff\xff\xff'
        b'!\xf9\x04\x01\x00\x00\x00\x00'
        b',\x00\x00\x00\x00\x01\x00\x01\x00\x00'
        b'\x02\x02L\x01\x00;'
    )

    return Response(
        content=pixel,
        media_type="image/gif",
    )


@router.get("/click/{tracking_token}")
def track_click(
    tracking_token: str,
    db: Session = Depends(get_db),
):
    email = (
        db.query(Email)
        .filter(Email.tracking_token == tracking_token)
        .first()
    )

    if not email or not email.destination_url:
        raise HTTPException(
            status_code=404,
            detail="Tracked destination not found",
        )

    # Validate again before redirecting. Never trust a stored URL blindly.
    try:
        destination_url = validate_http_url(
            email.destination_url
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid tracked destination",
        )

    if not destination_url:
        raise HTTPException(
            status_code=404,
            detail="Tracked destination not found",
        )

    # Record every click, including repeated clicks.
    click_event = EmailClickEvent(
        email_id=email.id,
    )

    db.add(click_event)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Unable to record click event",
        )

    return RedirectResponse(
        url=destination_url,
        status_code=302,
    )
