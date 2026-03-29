from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.email import Email

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/")
def get_stats(db: Session = Depends(get_db)):

    total = db.query(Email).count()
    sent = db.query(Email).filter(Email.status == "sent").count()
    opened = db.query(Email).filter(Email.status == "opened").count()

    return {
        "total": total,
        "sent": sent,
        "opened": opened
    }