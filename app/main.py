from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models

from app.api.auth import router as auth_router
from app.api.user import router as user_router
from app.api.contact import router as contact_router
from app.api.email import router as email_router
from app.api.campaign import router as campaign_router
from app.api import tracking, analytics
from app.api.ai import router as ai_router

from app.core.config import settings


app = FastAPI(
    title="AI Outreach Automation System",
    version="1.0.0",
    description="AI-powered outreach automation backend"
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "PATCH",
        "DELETE",
        "OPTIONS"
    ],
    allow_headers=[
        "Authorization",
        "Content-Type"
    ],
)


# =========================================================
# API ROUTERS
# =========================================================

app.include_router(auth_router)
app.include_router(user_router)
app.include_router(contact_router)
app.include_router(email_router)
app.include_router(campaign_router)
app.include_router(tracking.router)
app.include_router(analytics.router)
app.include_router(ai_router)


# =========================================================
# ROOT / HEALTH
# =========================================================

@app.get("/")
def root():
    return {
        "message": "Backend running 🚀"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }