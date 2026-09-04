from pydantic import BaseModel, ConfigDict, Field


class CampaignContactAdd(BaseModel):
    contact_ids: list[int] = Field(..., min_length=1, max_length=100)


class CampaignContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    contact_id: int


class CampaignContactListResponse(BaseModel):
    items: list[CampaignContactResponse]
    total: int