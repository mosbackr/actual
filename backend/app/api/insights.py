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
    """Aggregate startup scoring metrics grouped by country and US state."""
    approved = Startup.status.in_([StartupStatus.approved, StartupStatus.featured])

    # When filtering by industry, use a subquery to avoid count inflation.
    startup_filter = None
    if industry:
        startup_filter = (
            select(startup_industries.c.startup_id)
            .join(Industry, startup_industries.c.industry_id == Industry.id)
            .where(Industry.slug.in_(industry))
            .distinct()
        )

    def apply_filters(q):
        if stage:
            q = q.where(Startup.stage.in_(stage))
        if startup_filter is not None:
            q = q.where(Startup.id.in_(startup_filter))
        return q

    # ── Country-level aggregation (for world map) ──
    country_q = apply_filters(
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
    ).group_by(Startup.location_country)

    country_rows = (await db.execute(country_q)).all()

    # ── US state-level aggregation (for US map) ──
    state_q = apply_filters(
        select(
            Startup.location_state,
            func.count(Startup.id).label("count"),
            func.avg(Startup.ai_score).label("avg_ai"),
            func.avg(Startup.expert_score).label("avg_expert"),
            func.avg(Startup.user_score).label("avg_user"),
        )
        .where(approved)
        .where(Startup.location_country == "US")
        .where(Startup.location_state.isnot(None))
        .where(Startup.location_state != "")
    ).group_by(Startup.location_state)

    state_rows = (await db.execute(state_q)).all()

    # ── Sitewide averages ──
    site_q = apply_filters(
        select(
            func.count(Startup.id).label("count"),
            func.avg(Startup.ai_score).label("avg_ai"),
            func.avg(Startup.expert_score).label("avg_expert"),
            func.avg(Startup.user_score).label("avg_user"),
        )
        .where(approved)
    )
    site = (await db.execute(site_q)).one()

    def rnd(v):
        return round(float(v), 1) if v is not None else None

    countries = []
    for row in country_rows:
        countries.append({
            "region": row.location_country,
            "count": row.count,
            "avg_ai_score": rnd(row.avg_ai),
            "avg_expert_score": rnd(row.avg_expert),
            "avg_user_score": rnd(row.avg_user),
        })
    countries.sort(key=lambda r: r["avg_ai_score"] or 0, reverse=True)

    us_states = []
    for row in state_rows:
        us_states.append({
            "region": row.location_state,
            "count": row.count,
            "avg_ai_score": rnd(row.avg_ai),
            "avg_expert_score": rnd(row.avg_expert),
            "avg_user_score": rnd(row.avg_user),
        })
    us_states.sort(key=lambda r: r["avg_ai_score"] or 0, reverse=True)

    return {
        "countries": countries,
        "us_states": us_states,
        "sitewide": {
            "count": site.count,
            "avg_ai_score": rnd(site.avg_ai),
            "avg_expert_score": rnd(site.avg_expert),
            "avg_user_score": rnd(site.avg_user),
        },
    }
