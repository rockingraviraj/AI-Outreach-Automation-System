from fastapi import APIRouter, Depends, HTTPException
from app.services.ai_service import generate_email
from app.models.user import User
from app.core.dependencies import get_current_user


router = APIRouter(
    prefix="/ai",
    tags=["AI"]
)


@router.get("/generate")
def generate(
    name: str,
    company: str,
    current_user: User = Depends(get_current_user)
):
    name = name.strip()
    company = company.strip()

    if not name:
        raise HTTPException(
            status_code=422,
            detail="Name cannot be empty"
        )

    if not company:
        raise HTTPException(
            status_code=422,
            detail="Company cannot be empty"
        )

    if len(name) > 100:
        raise HTTPException(
            status_code=422,
            detail="Name cannot exceed 100 characters"
        )

    if len(company) > 150:
        raise HTTPException(
            status_code=422,
            detail="Company cannot exceed 150 characters"
        )

    email = generate_email(
        name,
        company
    )

    return {
        "email": email
    }