from pydantic import BaseModel, ConfigDict, EmailStr, Field


CONTACT_STATUSES = [
    "new",
    "contacted",
    "replied",
    "converted",
    "unsubscribed",
]


class ContactCreate(BaseModel):
    name: str = Field(
        ...,
        min_length=1,
        max_length=100
    )
    email: EmailStr
    company: str | None = Field(
        default=None,
        max_length=150
    )
    linkedin_url: str | None = Field(
        default=None,
        max_length=500
    )
    status: str = Field(
        default="new",
        min_length=1,
        max_length=20
    )


class ContactUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100
    )
    email: EmailStr | None = None
    company: str | None = Field(
        default=None,
        max_length=150
    )
    linkedin_url: str | None = Field(
        default=None,
        max_length=500
    )
    status: str | None = Field(
        default=None,
        min_length=1,
        max_length=20
    )


class ContactResponse(BaseModel):
    id: int
    user_id: int
    name: str
    email: EmailStr
    company: str | None
    linkedin_url: str | None
    status: str

    model_config = ConfigDict(
        from_attributes=True
    )