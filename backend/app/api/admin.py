import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.expert import ApplicationStatus, ExpertProfile
from app.models.startup import Startup, StartupStage, StartupStatus
from app.models.user import User, UserRole

router = APIRouter()


@router.get("/api/admin/users")
async def list_users(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [
        {"id": str(u.id), "email": u.email, "name": u.name, "role": u.role.value}
        for u in users
    ]


@router.get("/api/admin/startups/pipeline")
async def startup_pipeline(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Startup)
        .where(Startup.status == StartupStatus.pending)
        .order_by(Startup.created_at.desc())
    )
    startups = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "slug": s.slug,
            "description": s.description,
            "stage": s.stage.value,
            "status": s.status.value,
            "created_at": s.created_at.isoformat(),
        }
        for s in startups
    ]


class StartupUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    website_url: str | None = None
    stage: str | None = None
    status: str | None = None
    location_city: str | None = None
    location_state: str | None = None
    location_country: str | None = None


@router.put("/api/admin/startups/{startup_id}")
async def update_startup(
    startup_id: uuid.UUID,
    body: StartupUpdateIn,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    startup = result.scalar_one_or_none()
    if startup is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    for field, value in body.model_dump(exclude_none=True).items():
        if field == "status":
            setattr(startup, field, StartupStatus(value))
        elif field == "stage":
            setattr(startup, field, StartupStage(value))
        else:
            setattr(startup, field, value)

    await db.commit()
    await db.refresh(startup)

    return {
        "id": str(startup.id),
        "name": startup.name,
        "slug": startup.slug,
        "description": startup.description,
        "stage": startup.stage.value,
        "status": startup.status.value,
    }


@router.get("/api/admin/experts/applications")
async def list_expert_applications(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ExpertProfile)
        .where(ExpertProfile.application_status == ApplicationStatus.pending)
        .order_by(ExpertProfile.created_at.desc())
    )
    profiles = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "user_id": str(p.user_id),
            "bio": p.bio,
            "years_experience": p.years_experience,
            "application_status": p.application_status.value,
            "created_at": p.created_at.isoformat(),
        }
        for p in profiles
    ]


@router.put("/api/admin/experts/{profile_id}/approve")
async def approve_expert(
    profile_id: uuid.UUID,
    admin: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ExpertProfile).where(ExpertProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Application not found")

    profile.application_status = ApplicationStatus.approved
    profile.approved_by = admin.id
    profile.approved_at = datetime.now(timezone.utc)

    # Update user role to expert
    user_result = await db.execute(select(User).where(User.id == profile.user_id))
    user = user_result.scalar_one()
    user.role = UserRole.expert

    await db.commit()
    await db.refresh(profile)

    return {
        "id": str(profile.id),
        "application_status": profile.application_status.value,
        "approved_at": profile.approved_at.isoformat(),
    }


@router.put("/api/admin/experts/{profile_id}/reject")
async def reject_expert(
    profile_id: uuid.UUID,
    _admin: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ExpertProfile).where(ExpertProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Application not found")

    profile.application_status = ApplicationStatus.rejected
    await db.commit()
    await db.refresh(profile)

    return {
        "id": str(profile.id),
        "application_status": profile.application_status.value,
    }
