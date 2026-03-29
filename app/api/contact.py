from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import pandas as pd

from app.db.session import get_db
from app.models.contact import Contact
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.post("/upload")
def upload_contacts(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)   # 🔥 back to secure
):

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV file allowed")

    df = pd.read_csv(file.file)

    required_columns = ["name", "email"]
    for col in required_columns:
        if col not in df.columns:
            raise HTTPException(status_code=400, detail=f"Missing column: {col}")

    added = 0

    for _, row in df.iterrows():
        email = str(row["email"]).strip()

        # ✅ correct duplicate check
        exists = db.query(Contact).filter(
            Contact.email == email,
            Contact.user_id == current_user.id
        ).first()

        if exists:
            continue

        contact = Contact(
            user_id=current_user.id,   # 🔥 correct user
            name=str(row["name"]),
            email=email,
            company=str(row.get("company", "")),
            linkedin_url=str(row.get("linkedin_url", ""))
        )

        db.add(contact)
        added += 1

    db.commit()

    return {
        "message": "Contacts uploaded successfully",
        "added": added
    }