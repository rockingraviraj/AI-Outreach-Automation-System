from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.ai import (
    AIGenerateRequest,
    AIGenerateResponse,
)
from app.services.ai_service import generate_email_preview


router = APIRouter(
    prefix="/ai",
    tags=["AI"]
)


@router.post(
    "/generate",
    response_model=AIGenerateResponse,
)
def generate(
    data: AIGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    name = data.name.strip()
    company = data.company.strip()

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

    result = generate_email_preview(
        name,
        company
    )

    return result