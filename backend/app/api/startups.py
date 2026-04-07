from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.industry import Industry
from app.models.media import StartupMedia
from app.models.score import StartupScoreHistory
from app.models.startup import Startup, StartupStatus, startup_industries

router = APIRouter()


@router.get("/api/startups")
async def list_startups(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    stage: str | None = None,
    industry: str | None = None,
    q: str | None = None,
    sort: str = "newest",
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Startup)
        .options(selectinload(Startup.industries))
        .where(Startup.status.in_([StartupStatus.approved, StartupStatus.featured]))
    )

    if stage:
        query = query.where(Startup.stage == stage)

    if industry:
        query = query.join(startup_industries).join(Industry).where(Industry.slug == industry)

    if q:
        query = query.where(Startup.name.ilike(f"%{q}%") | Startup.description.ilike(f"%{q}%"))

    if sort == "ai_score":
        query = query.order_by(Startup.ai_score.desc().nulls_last())
    elif sort == "expert_score":
        query = query.order_by(Startup.expert_score.desc().nulls_last())
    elif sort == "user_score":
        query = query.order_by(Startup.user_score.desc().nulls_last())
    else:
        query = query.order_by(Startup.created_at.desc())

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    offset = (page - 1) * per_page
    result = await db.execute(query.offset(offset).limit(per_page))
    startups = result.scalars().unique().all()

    pages = (total + per_page - 1) // per_page

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "items": [
            {
                "id": str(s.id),
                "name": s.name,
                "slug": s.slug,
                "description": s.description,
                "website_url": s.website_url,
                "logo_url": s.logo_url,
                "stage": s.stage.value,
                "location_city": s.location_city,
                "location_state": s.location_state,
                "location_country": s.location_country,
                "ai_score": s.ai_score,
                "expert_score": s.expert_score,
                "user_score": s.user_score,
                "industries": [{"id": str(i.id), "name": i.name, "slug": i.slug} for i in s.industries],
            }
            for s in startups
        ],
    }


@router.get("/api/startups/{slug}")
async def get_startup(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Startup)
        .options(selectinload(Startup.industries))
        .where(Startup.slug == slug)
        .where(Startup.status.in_([StartupStatus.approved, StartupStatus.featured]))
    )
    startup = result.scalar_one_or_none()
    if startup is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    # Fetch media
    media_result = await db.execute(
        select(StartupMedia).where(StartupMedia.startup_id == startup.id).order_by(StartupMedia.published_at.desc())
    )
    media = media_result.scalars().all()

    # Fetch score history
    scores_result = await db.execute(
        select(StartupScoreHistory)
        .where(StartupScoreHistory.startup_id == startup.id)
        .order_by(StartupScoreHistory.recorded_at.asc())
    )
    scores = scores_result.scalars().all()

    return {
        "id": str(startup.id),
        "name": startup.name,
        "slug": startup.slug,
        "description": startup.description,
        "website_url": startup.website_url,
        "logo_url": startup.logo_url,
        "stage": startup.stage.value,
        "location_city": startup.location_city,
        "location_state": startup.location_state,
        "location_country": startup.location_country,
        "founded_date": startup.founded_date.isoformat() if startup.founded_date else None,
        "ai_score": startup.ai_score,
        "expert_score": startup.expert_score,
        "user_score": startup.user_score,
        "industries": [{"id": str(i.id), "name": i.name, "slug": i.slug} for i in startup.industries],
        "media": [
            {
                "id": str(m.id),
                "url": m.url,
                "title": m.title,
                "source": m.source,
                "media_type": m.media_type.value,
                "published_at": m.published_at.isoformat() if m.published_at else None,
            }
            for m in media
        ],
        "score_history": [
            {
                "score_type": sh.score_type.value,
                "score_value": sh.score_value,
                "dimensions_json": sh.dimensions_json,
                "recorded_at": sh.recorded_at.isoformat(),
            }
            for sh in scores
        ],
    }


@router.get("/api/stages")
async def list_stages():
    return [
        {"value": "pre_seed", "label": "Pre-Seed"},
        {"value": "seed", "label": "Seed"},
        {"value": "series_a", "label": "Series A"},
        {"value": "series_b", "label": "Series B"},
        {"value": "series_c", "label": "Series C"},
        {"value": "growth", "label": "Growth"},
    ]
