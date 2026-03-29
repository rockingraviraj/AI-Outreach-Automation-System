from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.campaign import Campaign

router = APIRouter(prefix="/campaign", tags=["Campaign"])


@router.post("/create")
def create_campaign(name: str, db: Session = Depends(get_db)):

    campaign = Campaign(
        name=name,
        user_id=1   # temporary
    )

    db.add(campaign)
    db.commit()
    db.refresh(campaign)

    return {
        "message": "Campaign created",
        "campaign_id": campaign.id
    }