from pydantic import BaseModel, Field, field_validator

from app.core.url_validation import validate_http_url


class SendContactEmailRequest(BaseModel):
    destination_url: str | None = Field(
        default=None,
        max_length=2048,
    )

    @field_validator("destination_url")
    @classmethod
    def validate_destination(cls, value):
        return validate_http_url(value)