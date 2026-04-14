from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.ai_review import StartupAIReview
from app.models.founder import StartupFounder
from app.models.funding_round import StartupFundingRound
from app.models.industry import Industry
from app.models.media import StartupMedia
from app.models.score import StartupScoreHistory
from app.models.dimension import StartupDimension
from app.models.startup import EntityType, EnrichmentStatus, Startup, StartupStatus, startup_industries
from app.models.template import DueDiligenceTemplate, TemplateDimension

router = APIRouter()


@router.get("/api/startups")
async def list_startups(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    stage: List[str] = Query(default=[]),
    industry: List[str] = Query(default=[]),
    region: List[str] = Query(default=[]),
    investor: List[str] = Query(default=[]),
    q: str | None = None,
    sort: str = "ai_score",
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Startup)
        .options(selectinload(Startup.industries))
        .where(Startup.status.in_([StartupStatus.approved, StartupStatus.featured]))
        .where(Startup.entity_type == EntityType.startup)
        .where(Startup.enrichment_status == EnrichmentStatus.complete)
    )

    if stage:
        query = query.where(Startup.stage.in_(stage))

    if industry:
        industry_subq = (
            select(startup_industries.c.startup_id)
            .join(Industry, startup_industries.c.industry_id == Industry.id)
            .where(Industry.slug.in_(industry))
            .distinct()
        )
        query = query.where(Startup.id.in_(industry_subq))

    if region:
        query = query.where(Startup.location_state.in_(region))

    if investor:
        from sqlalchemy import or_
        investor_conditions = []
        for inv in investor:
            pattern = f"%{inv}%"
            investor_conditions.append(StartupFundingRound.lead_investor.ilike(pattern))
            investor_conditions.append(StartupFundingRound.other_investors.ilike(pattern))
        query = query.where(
            Startup.id.in_(
                select(StartupFundingRound.startup_id).where(or_(*investor_conditions)).distinct()
            )
        )

    if q:
        query = query.where(Startup.name.ilike(f"%{q}%") | Startup.description.ilike(f"%{q}%"))

    if sort == "ai_score":
        query = query.order_by(Startup.ai_score.desc().nulls_last())
    elif sort == "expert_score":
        query = query.order_by(Startup.expert_score.desc().nulls_last())
    elif sort == "user_score":
        query = query.order_by(Startup.user_score.desc().nulls_last())
    elif sort == "trending":
        # Trending = most community/expert activity: has scores, reviews, media
        trending_score = (
            case((Startup.ai_score.isnot(None), 1), else_=0)
            + case((Startup.expert_score.isnot(None), 2), else_=0)
            + case((Startup.user_score.isnot(None), 2), else_=0)
        )
        query = query.order_by(trending_score.desc(), Startup.created_at.desc())
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
                "tagline": s.tagline,
                "form_sources": s.form_sources or [],
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

    # Fetch founders
    founders_result = await db.execute(
        select(StartupFounder).where(StartupFounder.startup_id == startup.id).order_by(StartupFounder.sort_order)
    )
    founders = founders_result.scalars().all()

    # Fetch funding rounds
    funding_result = await db.execute(
        select(StartupFundingRound).where(StartupFundingRound.startup_id == startup.id).order_by(StartupFundingRound.sort_order)
    )
    funding_rounds = funding_result.scalars().all()

    # Fetch AI review
    review_result = await db.execute(
        select(StartupAIReview).where(StartupAIReview.startup_id == startup.id)
    )
    ai_review = review_result.scalar_one_or_none()

    # Fetch dimensions (from template-based scoring)
    dims_result = await db.execute(
        select(StartupDimension)
        .where(StartupDimension.startup_id == startup.id)
        .order_by(StartupDimension.sort_order)
    )
    dimensions = dims_result.scalars().all()

    # If no dimensions assigned, fall back to matching template dimensions
    template_dims = []
    if not dimensions:
        industry_slug = startup.industries[0].slug if startup.industries else None
        stage_value = startup.stage.value if startup.stage else None
        template = None

        # 1. Exact match: industry + stage
        if industry_slug and stage_value:
            t = await db.execute(
                select(DueDiligenceTemplate).where(
                    DueDiligenceTemplate.industry_slug == industry_slug,
                    DueDiligenceTemplate.stage == stage_value,
                )
            )
            template = t.scalars().first()

        # 2. Industry-only match
        if template is None and industry_slug:
            t = await db.execute(
                select(DueDiligenceTemplate).where(
                    DueDiligenceTemplate.industry_slug == industry_slug,
                    DueDiligenceTemplate.stage.is_(None),
                )
            )
            template = t.scalars().first()

        # 3. Stage-only match
        if template is None and stage_value:
            t = await db.execute(
                select(DueDiligenceTemplate).where(
                    DueDiligenceTemplate.industry_slug.is_(None),
                    DueDiligenceTemplate.stage == stage_value,
                )
            )
            template = t.scalars().first()

        # 4. General fallback
        if template is None:
            t = await db.execute(
                select(DueDiligenceTemplate).where(DueDiligenceTemplate.name == "General")
            )
            template = t.scalars().first()

        if template is not None:
            td_result = await db.execute(
                select(TemplateDimension)
                .where(TemplateDimension.template_id == template.id)
                .order_by(TemplateDimension.sort_order)
            )
            template_dims = td_result.scalars().all()

    return {
        "id": str(startup.id),
        "name": startup.name,
        "slug": startup.slug,
        "form_sources": startup.form_sources or [],
        "data_sources": startup.data_sources or {},
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
        "tagline": startup.tagline,
        "total_funding": startup.total_funding,
        "employee_count": startup.employee_count,
        "linkedin_url": startup.linkedin_url,
        "twitter_url": startup.twitter_url,
        "crunchbase_url": startup.crunchbase_url,
        "competitors": startup.competitors,
        "tech_stack": startup.tech_stack,
        "key_metrics": startup.key_metrics,
        "company_status": startup.company_status.value if startup.company_status else "unknown",
        "revenue_estimate": startup.revenue_estimate,
        "business_model": startup.business_model,
        "founders": [
            {
                "name": f.name, "title": f.title, "linkedin_url": f.linkedin_url,
                "is_founder": f.is_founder, "prior_experience": f.prior_experience,
                "education": f.education,
            }
            for f in founders
        ],
        "funding_rounds": [
            {
                "round_name": fr.round_name, "amount": fr.amount, "date": fr.date,
                "lead_investor": fr.lead_investor, "other_investors": fr.other_investors,
                "pre_money_valuation": fr.pre_money_valuation, "post_money_valuation": fr.post_money_valuation,
            }
            for fr in funding_rounds
        ],
        "ai_review": {
            "overall_score": ai_review.overall_score,
            "investment_thesis": ai_review.investment_thesis,
            "key_risks": ai_review.key_risks,
            "verdict": ai_review.verdict,
            "dimension_scores": ai_review.dimension_scores,
            "created_at": ai_review.created_at.isoformat(),
        } if ai_review else None,
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
        "dimensions": [
            {"name": d.dimension_name, "slug": d.dimension_slug, "weight": d.weight}
            for d in dimensions
        ] if dimensions else [
            {"name": td.dimension_name, "slug": td.dimension_slug, "weight": td.weight}
            for td in template_dims
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
        {"value": "public", "label": "Public"},
    ]


US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL",
    "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}


@router.get("/api/filters")
async def get_filter_options(db: AsyncSession = Depends(get_db)):
    """Return unique regions and investors for filter dropdowns."""
    approved = Startup.status.in_([StartupStatus.approved, StartupStatus.featured])

    # Unique regions (US states only)
    region_result = await db.execute(
        select(Startup.location_state)
        .where(approved)
        .where(Startup.location_state.in_(US_STATES))
        .distinct()
        .order_by(Startup.location_state)
    )
    regions = [r for (r,) in region_result.all()]

    return {"regions": regions}
