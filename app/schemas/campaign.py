from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)


class CampaignResponse(BaseModel):
    id: int
    name: str
    status: str
    user_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    page: int
    limit: int
    total: int
    pages: int