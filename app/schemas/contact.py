from pydantic import BaseModel, EmailStr

class ContactCreate(BaseModel):
    name: str
    email: EmailStr
    company: str | None = None
    linkedin_url: str | None = None