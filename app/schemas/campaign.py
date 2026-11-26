
from datetime import datetime

from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    field_validator,
)

from app.core.url_validation import validate_http_url


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    destination_url: str | None = Field(
        default=None,
        max_length=2048,
    )

    @field_validator("destination_url")
    @classmethod
    def validate_destination(cls, value):
        return validate_http_url(value)


class CampaignUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )

    status: str | None = None

    destination_url: str | None = Field(
        default=None,
        max_length=2048,
    )

    @field_validator("destination_url")
    @classmethod
    def validate_destination(cls, value):
        return validate_http_url(value)


class CampaignResponse(BaseModel):
    id: int
    name: str
    status: str
    user_id: int
    created_at: datetime
    destination_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    page: int
    limit: int
    total: int
    pages: int
