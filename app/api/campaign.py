from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.user import User
from app.models.contact import Contact
from app.models.campaign_contact import CampaignContact
from app.models.email import Email

from app.core.dependencies import get_current_user
from app.db.session import get_db

from app.schemas.campaign import (
    CampaignCreate,
    CampaignListResponse,
    CampaignResponse,
    CampaignUpdate,
)

from app.schemas.campaign_contact import (
    CampaignContactAdd,
    CampaignContactListResponse,
)


router = APIRouter(
    prefix="/campaign",
    tags=["Campaign"]
)


# =========================================================
# HELPERS
# =========================================================

def get_owned_campaign(
    campaign_id: int,
    db: Session,
    current_user: User
) -> Campaign:
    campaign = (
        db.query(Campaign)
        .filter(
            Campaign.id == campaign_id,
            Campaign.user_id == current_user.id
        )
        .first()
    )

    if campaign is None:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found"
        )

    return campaign


def ensure_campaign_editable(campaign: Campaign):
    if campaign.status != "draft":
        raise HTTPException(
            status_code=409,
            detail=(
                "Campaign can only be modified while it is in draft status"
            )
        )


# =========================================================
# CREATE CAMPAIGN
# POST /campaign
# =========================================================

@router.post(
    "",
    response_model=CampaignResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_campaign(
    campaign_data: CampaignCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = campaign_data.name.strip()

    if not name:
        raise HTTPException(
            status_code=422,
            detail="Campaign name cannot be empty"
        )

    if len(name) > 100:
        raise HTTPException(
            status_code=422,
            detail="Campaign name cannot exceed 100 characters"
        )

    campaign = Campaign(
        name=name,
        user_id=current_user.id,
        status="draft",
    )

    try:
        db.add(campaign)
        db.commit()
        db.refresh(campaign)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Unable to create campaign"
        )

    return campaign


# =========================================================
# LEGACY CREATE CAMPAIGN
# POST /campaign/create
# =========================================================

@router.post("/create")
def create_campaign_legacy(
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = name.strip()

    if not name:
        raise HTTPException(
            status_code=422,
            detail="Campaign name cannot be empty"
        )

    if len(name) > 100:
        raise HTTPException(
            status_code=422,
            detail="Campaign name cannot exceed 100 characters"
        )

    campaign = Campaign(
        name=name,
        user_id=current_user.id,
        status="draft",
    )

    try:
        db.add(campaign)
        db.commit()
        db.refresh(campaign)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Unable to create campaign"
        )

    return {
        "message": "Campaign created",
        "campaign_id": campaign.id,
        "user_id": current_user.id,
        "status": campaign.status,
    }


# =========================================================
# LIST CAMPAIGNS
# GET /campaign
# =========================================================

@router.get(
    "",
    response_model=CampaignListResponse,
)
def get_campaigns(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(Campaign)
        .filter(
            Campaign.user_id == current_user.id
        )
        .order_by(
            Campaign.created_at.desc()
        )
    )

    total = query.count()

    pages = ceil(total / limit) if total else 0

    campaigns = (
        query
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    return CampaignListResponse(
        items=campaigns,
        page=page,
        limit=limit,
        total=total,
        pages=pages,
    )


# =========================================================
# GET SINGLE CAMPAIGN
# GET /campaign/{campaign_id}
# =========================================================

@router.get(
    "/{campaign_id}",
    response_model=CampaignResponse,
)
def get_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_owned_campaign(
        campaign_id,
        db,
        current_user
    )


# =========================================================
# UPDATE CAMPAIGN
# PATCH /campaign/{campaign_id}
#
# Name can be edited only while draft.
# Status is controlled by execution flow.
# =========================================================

@router.patch(
    "/{campaign_id}",
    response_model=CampaignResponse,
)
def update_campaign(
    campaign_id: int,
    campaign_data: CampaignUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = get_owned_campaign(
        campaign_id,
        db,
        current_user
    )

    if campaign_data.status is not None:
        raise HTTPException(
            status_code=409,
            detail="Campaign status is managed by the execution system"
        )

    if campaign_data.name is not None:
        ensure_campaign_editable(campaign)

        name = campaign_data.name.strip()

        if not name:
            raise HTTPException(
                status_code=422,
                detail="Campaign name cannot be empty"
            )

        if len(name) > 100:
            raise HTTPException(
                status_code=422,
                detail="Campaign name cannot exceed 100 characters"
            )

        campaign.name = name

    try:
        db.commit()
        db.refresh(campaign)

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Unable to update campaign"
        )

    return campaign


# =========================================================
# DELETE CAMPAIGN
# DELETE /campaign/{campaign_id}
#
# Campaigns with email history cannot be deleted.
# This protects historical outreach records.
# =========================================================

@router.delete(
    "/{campaign_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_campaign(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = get_owned_campaign(
        campaign_id,
        db,
        current_user
    )

    if campaign.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Only draft campaigns can be deleted"
        )

    email_count = (
        db.query(Email)
        .filter(
            Email.campaign_id == campaign.id
        )
        .count()
    )

    if email_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "Campaign cannot be deleted because email history exists"
            )
        )

    db.delete(campaign)

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Unable to delete campaign"
        )

    return None


# =========================================================
# ADD CONTACTS TO CAMPAIGN
# POST /campaign/{campaign_id}/contacts
# =========================================================

@router.post(
    "/{campaign_id}/contacts",
    response_model=CampaignContactListResponse,
)
def add_campaign_contacts(
    campaign_id: int,
    data: CampaignContactAdd,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = get_owned_campaign(
        campaign_id,
        db,
        current_user
    )

    ensure_campaign_editable(campaign)

    contact_ids = list(dict.fromkeys(data.contact_ids))

    contacts = (
        db.query(Contact)
        .filter(
            Contact.id.in_(contact_ids),
            Contact.user_id == current_user.id,
        )
        .all()
    )

    found_contact_ids = {
        contact.id
        for contact in contacts
    }

    invalid_contact_ids = [
        contact_id
        for contact_id in contact_ids
        if contact_id not in found_contact_ids
    ]

    if invalid_contact_ids:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "One or more contacts not found",
                "contact_ids": invalid_contact_ids,
            },
        )

    existing_links = (
        db.query(CampaignContact)
        .filter(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.contact_id.in_(contact_ids),
        )
        .all()
    )

    existing_contact_ids = {
        link.contact_id
        for link in existing_links
    }

    new_links = []

    for contact_id in contact_ids:
        if contact_id in existing_contact_ids:
            continue

        new_links.append(
            CampaignContact(
                campaign_id=campaign_id,
                contact_id=contact_id,
            )
        )

    try:
        if new_links:
            db.add_all(new_links)
            db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Unable to add campaign contacts"
        )

    links = (
        db.query(CampaignContact)
        .filter(
            CampaignContact.campaign_id == campaign_id
        )
        .order_by(
            CampaignContact.id.asc()
        )
        .all()
    )

    return CampaignContactListResponse(
        items=links,
        total=len(links),
    )


# =========================================================
# GET CAMPAIGN CONTACTS
# GET /campaign/{campaign_id}/contacts
# =========================================================

@router.get(
    "/{campaign_id}/contacts",
    response_model=CampaignContactListResponse,
)
def get_campaign_contacts(
    campaign_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = get_owned_campaign(
        campaign_id,
        db,
        current_user
    )

    links = (
        db.query(CampaignContact)
        .filter(
            CampaignContact.campaign_id == campaign.id
        )
        .order_by(
            CampaignContact.id.asc()
        )
        .all()
    )

    return CampaignContactListResponse(
        items=links,
        total=len(links),
    )


# =========================================================
# REMOVE CONTACT FROM CAMPAIGN
# DELETE /campaign/{campaign_id}/contacts/{contact_id}
# =========================================================

@router.delete(
    "/{campaign_id}/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_campaign_contact(
    campaign_id: int,
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    campaign = get_owned_campaign(
        campaign_id,
        db,
        current_user
    )

    ensure_campaign_editable(campaign)

    contact = (
        db.query(Contact)
        .filter(
            Contact.id == contact_id,
            Contact.user_id == current_user.id,
        )
        .first()
    )

    if contact is None:
        raise HTTPException(
            status_code=404,
            detail="Contact not found"
        )

    link = (
        db.query(CampaignContact)
        .filter(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.contact_id == contact_id,
        )
        .first()
    )

    if link is None:
        raise HTTPException(
            status_code=404,
            detail="Contact is not associated with this campaign"
        )

    db.delete(link)

    try:
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Unable to remove campaign contact"
        )

    return None