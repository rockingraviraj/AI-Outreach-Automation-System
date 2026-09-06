from math import ceil

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Depends,
    HTTPException,
    Query,
    status,
)
from pydantic import EmailStr, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import pandas as pd

from app.db.session import get_db
from app.models.contact import Contact
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.contact import (
    ContactCreate,
    ContactUpdate,
    CONTACT_STATUSES,
)


router = APIRouter(
    prefix="/contacts",
    tags=["Contacts"]
)


# =========================================================
# CREATE CONTACT
# POST /contacts
# =========================================================

@router.post(
    "",
    status_code=status.HTTP_201_CREATED
)
def create_contact(
    contact_data: ContactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = contact_data.name.strip()
    email = str(contact_data.email).strip().lower()

    if not name:
        raise HTTPException(
            status_code=422,
            detail="Name cannot be empty"
        )

    if contact_data.status not in CONTACT_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="Invalid contact status"
        )

    existing_contact = (
        db.query(Contact)
        .filter(
            Contact.user_id == current_user.id,
            Contact.email == email
        )
        .first()
    )

    if existing_contact:
        raise HTTPException(
            status_code=409,
            detail="Contact with this email already exists"
        )

    contact = Contact(
        user_id=current_user.id,
        name=name,
        email=email,
        company=(
            contact_data.company.strip()
            if contact_data.company
            else ""
        ),
        linkedin_url=(
            contact_data.linkedin_url.strip()
            if contact_data.linkedin_url
            else ""
        ),
        status=contact_data.status,
    )

    try:
        db.add(contact)
        db.commit()
        db.refresh(contact)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Contact with this email already exists"
        )

    return contact


# =========================================================
# LIST CONTACTS
# GET /contacts
# =========================================================

@router.get("")
def get_contacts(
    page: int = Query(
        default=1,
        ge=1
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100
    ),
    search: str | None = Query(
        default=None
    ),
    company: str | None = Query(
        default=None
    ),
    email: str | None = Query(
        default=None
    ),
    status_filter: str | None = Query(
        default=None,
        alias="status"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if (
        status_filter is not None
        and status_filter not in CONTACT_STATUSES
    ):
        raise HTTPException(
            status_code=422,
            detail="Invalid contact status"
        )

    query = (
        db.query(Contact)
        .filter(
            Contact.user_id == current_user.id
        )
    )

    if search:
        search_value = f"%{search.strip()}%"

        query = query.filter(
            Contact.name.ilike(search_value)
            |
            Contact.email.ilike(search_value)
            |
            Contact.company.ilike(search_value)
        )

    if company:
        query = query.filter(
            Contact.company.ilike(
                f"%{company.strip()}%"
            )
        )

    if email:
        query = query.filter(
            Contact.email.ilike(
                f"%{email.strip()}%"
            )
        )

    if status_filter:
        query = query.filter(
            Contact.status == status_filter
        )

    query = query.order_by(
        Contact.id.desc()
    )

    total = query.count()

    pages = ceil(
        total / limit
    ) if total else 0

    contacts = (
        query
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return {
        "items": contacts,
        "page": page,
        "limit": limit,
        "total": total,
        "pages": pages,
    }


# =========================================================
# GET SINGLE CONTACT
# GET /contacts/{contact_id}
# =========================================================

@router.get("/{contact_id}")
def get_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == contact_id,
            Contact.user_id == current_user.id
        )
        .first()
    )

    if contact is None:
        raise HTTPException(
            status_code=404,
            detail="Contact not found"
        )

    return contact


# =========================================================
# UPDATE CONTACT
# PATCH /contacts/{contact_id}
# =========================================================

@router.patch("/{contact_id}")
def update_contact(
    contact_id: int,
    contact_data: ContactUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == contact_id,
            Contact.user_id == current_user.id
        )
        .first()
    )

    if contact is None:
        raise HTTPException(
            status_code=404,
            detail="Contact not found"
        )

    if contact_data.name is not None:
        name = contact_data.name.strip()

        if not name:
            raise HTTPException(
                status_code=422,
                detail="Name cannot be empty"
            )

        contact.name = name

    if contact_data.email is not None:
        email = str(
            contact_data.email
        ).strip().lower()

        existing_contact = (
            db.query(Contact)
            .filter(
                Contact.user_id == current_user.id,
                Contact.email == email,
                Contact.id != contact.id
            )
            .first()
        )

        if existing_contact:
            raise HTTPException(
                status_code=409,
                detail="Contact with this email already exists"
            )

        contact.email = email

    if contact_data.company is not None:
        contact.company = contact_data.company.strip()

    if contact_data.linkedin_url is not None:
        contact.linkedin_url = (
            contact_data.linkedin_url.strip()
        )

    if contact_data.status is not None:
        if contact_data.status not in CONTACT_STATUSES:
            raise HTTPException(
                status_code=422,
                detail="Invalid contact status"
            )

        contact.status = contact_data.status

    try:
        db.commit()
        db.refresh(contact)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Unable to update contact"
        )

    return contact


# =========================================================
# DELETE CONTACT
# DELETE /contacts/{contact_id}
# =========================================================

@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT
)
def delete_contact(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == contact_id,
            Contact.user_id == current_user.id
        )
        .first()
    )

    if contact is None:
        raise HTTPException(
            status_code=404,
            detail="Contact not found"
        )

    db.delete(contact)

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "Contact cannot be deleted because "
                "related records exist"
            )
        )

    return None


# =========================================================
# CSV UPLOAD
# POST /contacts/upload
# =========================================================

@router.post("/upload")
def upload_contacts(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="File name is required"
        )

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Only CSV file allowed"
        )

    try:
        df = pd.read_csv(file.file)

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Unable to read CSV file"
        )

    required_columns = [
        "name",
        "email"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Missing column: "
                f"{', '.join(missing_columns)}"
            )
        )

    if df.empty:
        raise HTTPException(
            status_code=400,
            detail="CSV file is empty"
        )

    valid_contacts = []
    errors = []

    for index, row in df.iterrows():
        row_number = index + 2

        raw_name = row.get("name")
        raw_email = row.get("email")

        if (
            pd.isna(raw_name)
            or not str(raw_name).strip()
        ):
            errors.append({
                "row": row_number,
                "field": "name",
                "message": "Name is required"
            })
            continue

        if (
            pd.isna(raw_email)
            or not str(raw_email).strip()
        ):
            errors.append({
                "row": row_number,
                "field": "email",
                "message": "Email is required"
            })
            continue

        name = str(raw_name).strip()
        email = str(raw_email).strip().lower()

        try:
            validated_email = str(
                EmailStr._validate(email)
            )

        except (ValidationError, ValueError):
            errors.append({
                "row": row_number,
                "field": "email",
                "message": f"Invalid email: {email}"
            })
            continue

        company = row.get("company")
        linkedin_url = row.get("linkedin_url")

        company = (
            ""
            if pd.isna(company)
            else str(company).strip()
        )

        linkedin_url = (
            ""
            if pd.isna(linkedin_url)
            else str(linkedin_url).strip()
        )

        valid_contacts.append({
            "name": name,
            "email": validated_email,
            "company": company,
            "linkedin_url": linkedin_url
        })

    if errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "CSV validation failed",
                "errors": errors
            }
        )

    added = 0
    duplicates = 0

    for contact_data in valid_contacts:
        existing_contact = (
            db.query(Contact)
            .filter(
                Contact.email == contact_data["email"],
                Contact.user_id == current_user.id
            )
            .first()
        )

        if existing_contact:
            duplicates += 1
            continue

        contact = Contact(
            user_id=current_user.id,
            name=contact_data["name"],
            email=contact_data["email"],
            company=contact_data["company"],
            linkedin_url=contact_data["linkedin_url"],
            status="new"
        )

        db.add(contact)
        added += 1

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Unable to import contacts"
        )

    return {
        "message": "Contacts uploaded successfully",
        "added": added,
        "duplicates": duplicates
    }