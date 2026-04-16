import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.expert import ExpertProfile
from app.models.industry import Industry
from app.models.skill import Skill
from app.models.user import User
from app.schemas.expert import ExpertApplicationIn
from app.services import email_service

router = APIRouter()


@router.post("/api/experts/apply", status_code=201)
async def apply_as_expert(
    body: ExpertApplicationIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check if already applied
    existing = await db.execute(
        select(ExpertProfile).where(ExpertProfile.user_id == user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Application already submitted")

    profile = ExpertProfile(
        id=uuid.uuid4(),
        user_id=user.id,
        bio=body.bio,
        years_experience=body.years_experience,
    )

    # Load industries
    for ind_id in body.industry_ids:
        result = await db.execute(select(Industry).where(Industry.id == uuid.UUID(ind_id)))
        ind = result.scalar_one_or_none()
        if ind:
            profile.industries.append(ind)

    # Load skills
    for skill_id in body.skill_ids:
        result = await db.execute(select(Skill).where(Skill.id == uuid.UUID(skill_id)))
        skill = result.scalar_one_or_none()
        if skill:
            profile.skills.append(skill)

    db.add(profile)
    await db.commit()

    email_service.send_expert_applied(user_email=user.email, user_name=user.name)

    # Re-fetch with eager loading to avoid lazy-load issues in async context
    result = await db.execute(
        select(ExpertProfile)
        .where(ExpertProfile.id == profile.id)
        .options(selectinload(ExpertProfile.industries), selectinload(ExpertProfile.skills))
    )
    profile = result.scalar_one()

    return {
        "id": str(profile.id),
        "bio": profile.bio,
        "years_experience": profile.years_experience,
        "application_status": profile.application_status.value,
        "industries": [i.name for i in profile.industries],
        "skills": [s.name for s in profile.skills],
        "created_at": profile.created_at.isoformat(),
    }


@router.get("/api/expert/applications/mine")
async def my_application(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ExpertProfile)
        .where(ExpertProfile.user_id == user.id)
        .options(selectinload(ExpertProfile.industries), selectinload(ExpertProfile.skills))
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="No application found")

    return {
        "id": str(profile.id),
        "bio": profile.bio,
        "years_experience": profile.years_experience,
        "application_status": profile.application_status.value,
        "industries": [i.name for i in profile.industries],
        "skills": [s.name for s in profile.skills],
        "created_at": profile.created_at.isoformat(),
    }
