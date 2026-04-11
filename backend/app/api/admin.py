import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.config import settings
from app.db.session import get_db
from app.models.expert import ApplicationStatus, ExpertProfile
from app.models.industry import Industry
from app.models.startup import Startup, StartupStage, StartupStatus, startup_industries
from app.models.user import User, UserRole

router = APIRouter()


@router.get("/api/admin/users")
async def list_users(
    role: str | None = None,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).order_by(User.created_at.desc())
    if role is not None:
        query = query.where(User.role == UserRole(role))
    result = await db.execute(query)
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
    from sqlalchemy.orm import selectinload
    from app.models.assignment import StartupAssignment
    from app.models.dimension import StartupDimension

    result = await db.execute(
        select(Startup)
        .options(selectinload(Startup.industries))
        .where(Startup.status == StartupStatus.pending)
        .order_by(Startup.created_at.desc())
    )
    startups = result.scalars().all()

    response = []
    for s in startups:
        assign_result = await db.execute(
            select(StartupAssignment).where(StartupAssignment.startup_id == s.id)
        )
        assignment_count = len(assign_result.scalars().all())
        dim_result = await db.execute(
            select(StartupDimension).where(StartupDimension.startup_id == s.id).limit(1)
        )
        dimensions_configured = dim_result.scalar_one_or_none() is not None
        response.append({
            "id": str(s.id), "name": s.name, "slug": s.slug,
            "description": s.description, "stage": s.stage.value,
            "status": s.status.value, "created_at": s.created_at.isoformat(),
            "industries": [{"id": str(i.id), "name": i.name, "slug": i.slug} for i in s.industries],
            "enrichment_status": s.enrichment_status.value if hasattr(s, 'enrichment_status') else "none",
            "assignment_count": assignment_count,
            "dimensions_configured": dimensions_configured,
        })
    return response


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
    background_tasks: BackgroundTasks,
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

    # Trigger enrichment if status changed to approved
    if body.status == "approved":
        from app.services.enrichment import run_enrichment_pipeline
        background_tasks.add_task(run_enrichment_pipeline, str(startup_id))

    await db.refresh(startup)

    return {
        "id": str(startup.id),
        "name": startup.name,
        "slug": startup.slug,
        "description": startup.description,
        "stage": startup.stage.value,
        "status": startup.status.value,
    }


class StartupCreateIn(BaseModel):
    name: str
    description: str
    website_url: str | None = None
    stage: str = "seed"
    status: str = "pending"
    location_city: str | None = None
    location_state: str | None = None
    location_country: str = "US"
    industry_ids: list[str] = []


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug


@router.get("/api/admin/startups")
async def list_all_startups(
    status: str | None = None,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload

    query = select(Startup).options(selectinload(Startup.industries)).order_by(Startup.created_at.desc())
    if status is not None:
        query = query.where(Startup.status == StartupStatus(status))
    result = await db.execute(query)
    startups = result.scalars().unique().all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "slug": s.slug,
            "description": s.description,
            "website_url": s.website_url,
            "logo_url": s.logo_url,
            "stage": s.stage.value,
            "status": s.status.value,
            "location_city": s.location_city,
            "location_state": s.location_state,
            "location_country": s.location_country,
            "industries": [{"id": str(i.id), "name": i.name, "slug": i.slug} for i in s.industries],
            "created_at": s.created_at.isoformat(),
        }
        for s in startups
    ]


@router.post("/api/admin/startups")
async def create_startup(
    body: StartupCreateIn,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    slug = _slugify(body.name)
    # Ensure unique slug
    existing = await db.execute(select(Startup).where(Startup.slug == slug))
    if existing.scalar_one_or_none() is not None:
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    startup = Startup(
        name=body.name,
        slug=slug,
        description=body.description,
        website_url=body.website_url or None,
        stage=StartupStage(body.stage),
        status=StartupStatus(body.status),
        location_city=body.location_city or None,
        location_state=body.location_state or None,
        location_country=body.location_country,
    )
    db.add(startup)
    await db.flush()

    # Attach industries
    if body.industry_ids:
        industry_result = await db.execute(
            select(Industry).where(Industry.id.in_([uuid.UUID(iid) for iid in body.industry_ids]))
        )
        for ind in industry_result.scalars().all():
            startup.industries.append(ind)

    await db.commit()
    await db.refresh(startup)

    return {
        "id": str(startup.id),
        "name": startup.name,
        "slug": startup.slug,
        "description": startup.description,
        "website_url": startup.website_url,
        "logo_url": startup.logo_url,
        "stage": startup.stage.value,
        "status": startup.status.value,
    }


@router.post("/api/admin/startups/{startup_id}/fetch-logo")
async def fetch_startup_logo(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    if not settings.logo_dev_token:
        raise HTTPException(status_code=500, detail="ACUTAL_LOGO_DEV_TOKEN not configured")

    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    startup = result.scalar_one_or_none()
    if startup is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    if not startup.website_url:
        raise HTTPException(status_code=400, detail="Startup has no website URL")

    # Extract domain from website URL
    try:
        parsed = urlparse(startup.website_url if "://" in startup.website_url else f"https://{startup.website_url}")
        domain = parsed.hostname or ""
        domain = re.sub(r"^www\.", "", domain)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid website URL")

    if not domain:
        raise HTTPException(status_code=400, detail="Could not extract domain from URL")

    # Fetch from Logo.dev
    logo_url = f"https://img.logo.dev/{domain}?token={settings.logo_dev_token}&format=png&size=128"
    async with httpx.AsyncClient() as client:
        resp = await client.head(logo_url, follow_redirects=True)
        if resp.status_code != 200:
            raise HTTPException(status_code=404, detail=f"No logo found for {domain}")

    # Store the Logo.dev URL directly
    startup.logo_url = logo_url
    await db.commit()
    await db.refresh(startup)

    return {"logo_url": startup.logo_url, "domain": domain}


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
