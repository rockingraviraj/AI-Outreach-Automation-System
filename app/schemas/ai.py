from typing import Literal

from pydantic import BaseModel, Field


class AIGenerateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    company: str = Field(..., min_length=1, max_length=150)


class AIGenerateResponse(BaseModel):
    subject: str
    body: str
    source: Literal["ai", "fallback"]