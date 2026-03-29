from fastapi import APIRouter
from app.services.ai_service import generate_email

router = APIRouter(prefix="/ai", tags=["AI"])


@router.get("/generate")
def generate(name: str, company: str):

    email = generate_email(name, company)

    return {"email": email}