from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.industry import Industry
from app.models.startup import Startup, StartupStatus, startup_industries

router = APIRouter()


@router.get("/api/insights/regional")
async def regional_insights(
    stage: List[str] = Query(default=[]),
    industry: List[str] = Query(default=[]),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate startup scoring metrics grouped by location_country."""
    approved = Startup.status.in_([StartupStatus.approved, StartupStatus.featured])

    # When filtering by industry, we join through the many-to-many table.
    # Use a subquery to get matching startup IDs to avoid count inflation.
    startup_filter = None
    if industry:
        startup_filter = (
            select(startup_industries.c.startup_id)
            .join(Industry, startup_industries.c.industry_id == Industry.id)
            .where(Industry.slug.in_(industry))
            .distinct()
        )

    base = (
        select(
            Startup.location_country,
            func.count(Startup.id).label("count"),
            func.avg(Startup.ai_score).label("avg_ai"),
            func.avg(Startup.expert_score).label("avg_expert"),
            func.avg(Startup.user_score).label("avg_user"),
        )
        .where(approved)
        .where(Startup.location_country.isnot(None))
        .where(Startup.location_country != "")
    )

    if stage:
        base = base.where(Startup.stage.in_(stage))

    if startup_filter is not None:
        base = base.where(Startup.id.in_(startup_filter))

    base = base.group_by(Startup.location_country)
    result = await db.execute(base)
    rows = result.all()

    # Sitewide averages (same filters, but not grouped)
    site_q = (
        select(
            func.count(Startup.id).label("count"),
            func.avg(Startup.ai_score).label("avg_ai"),
            func.avg(Startup.expert_score).label("avg_expert"),
            func.avg(Startup.user_score).label("avg_user"),
        )
        .where(approved)
    )
    if stage:
        site_q = site_q.where(Startup.stage.in_(stage))
    if startup_filter is not None:
        site_q = site_q.where(Startup.id.in_(startup_filter))

    site_result = await db.execute(site_q)
    site = site_result.one()

    def rnd(v):
        return round(float(v), 1) if v is not None else None

    regions = []
    for row in rows:
        regions.append({
            "region": row.location_country,
            "count": row.count,
            "avg_ai_score": rnd(row.avg_ai),
            "avg_expert_score": rnd(row.avg_expert),
            "avg_user_score": rnd(row.avg_user),
        })

    regions.sort(key=lambda r: r["avg_ai_score"] or 0, reverse=True)

    return {
        "regions": regions,
        "sitewide": {
            "count": site.count,
            "avg_ai_score": rnd(site.avg_ai),
            "avg_expert_score": rnd(site.avg_expert),
            "avg_user_score": rnd(site.avg_user),
        },
    }
