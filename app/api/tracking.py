from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.email import Email

router = APIRouter(
    prefix="/tracking",
    tags=["Tracking"]
)


@router.get("/open/{tracking_token}")
def track_open(
    tracking_token: str,
    db: Session = Depends(get_db)
):
    email = (
        db.query(Email)
        .filter(
            Email.tracking_token == tracking_token
        )
        .first()
    )

    if email:
        if email.status != "opened":
            email.status = "opened"
            db.commit()

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
        media_type="image/gif"
    )