import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.ai_review import StartupAIReview
from app.models.founder import StartupFounder
from app.models.funding_round import StartupFundingRound
from app.models.startup import EnrichmentStatus, Startup
from app.models.user import User
from app.services.enrichment import run_enrichment_pipeline

router = APIRouter()


@router.post("/api/admin/startups/{startup_id}/enrich")
async def enrich_startup(
    startup_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    startup = result.scalar_one_or_none()
    if startup is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    if startup.enrichment_status == EnrichmentStatus.running:
        raise HTTPException(status_code=409, detail="Enrichment already running")

    # Mark as running immediately so duplicate requests are rejected
    startup.enrichment_status = EnrichmentStatus.running
    startup.enrichment_error = None
    await db.commit()

    background_tasks.add_task(run_enrichment_pipeline, str(startup_id))

    return {"status": "running"}


@router.get("/api/admin/startups/{startup_id}/enrichment-status")
async def get_enrichment_status(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    startup = result.scalar_one_or_none()
    if startup is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    return {
        "enrichment_status": startup.enrichment_status.value,
        "enrichment_error": startup.enrichment_error,
        "enriched_at": startup.enriched_at.isoformat() if startup.enriched_at else None,
    }


@router.get("/api/admin/startups/{startup_id}/ai-review")
async def get_ai_review(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    startup = result.scalar_one_or_none()
    if startup is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    result = await db.execute(
        select(StartupAIReview).where(StartupAIReview.startup_id == startup_id)
    )
    review = result.scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=404, detail="No AI review found")

    return {
        "id": str(review.id),
        "startup_id": str(review.startup_id),
        "overall_score": review.overall_score,
        "investment_thesis": review.investment_thesis,
        "key_risks": review.key_risks,
        "verdict": review.verdict,
        "dimension_scores": review.dimension_scores,
        "created_at": review.created_at.isoformat(),
    }


@router.get("/api/admin/startups/{startup_id}/full-detail")
async def get_startup_full_detail(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Startup)
        .options(selectinload(Startup.industries))
        .where(Startup.id == startup_id)
    )
    startup = result.scalar_one_or_none()
    if startup is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    # Founders
    founders_result = await db.execute(
        select(StartupFounder)
        .where(StartupFounder.startup_id == startup_id)
        .order_by(StartupFounder.sort_order)
    )
    founders = founders_result.scalars().all()

    # Funding rounds
    rounds_result = await db.execute(
        select(StartupFundingRound)
        .where(StartupFundingRound.startup_id == startup_id)
        .order_by(StartupFundingRound.sort_order)
    )
    funding_rounds = rounds_result.scalars().all()

    # AI review
    review_result = await db.execute(
        select(StartupAIReview).where(StartupAIReview.startup_id == startup_id)
    )
    review = review_result.scalar_one_or_none()

    return {
        "id": str(startup.id),
        "name": startup.name,
        "slug": startup.slug,
        "description": startup.description,
        "tagline": startup.tagline,
        "website_url": startup.website_url,
        "logo_url": startup.logo_url,
        "stage": startup.stage.value,
        "status": startup.status.value,
        "location_city": startup.location_city,
        "location_state": startup.location_state,
        "location_country": startup.location_country,
        "founded_date": startup.founded_date.isoformat() if startup.founded_date else None,
        "total_funding": startup.total_funding,
        "employee_count": startup.employee_count,
        "linkedin_url": startup.linkedin_url,
        "twitter_url": startup.twitter_url,
        "crunchbase_url": startup.crunchbase_url,
        "competitors": startup.competitors,
        "tech_stack": startup.tech_stack,
        "key_metrics": startup.key_metrics,
        "hiring_signals": startup.hiring_signals,
        "patents": startup.patents,
        "ai_score": startup.ai_score,
        "expert_score": startup.expert_score,
        "user_score": startup.user_score,
        "enrichment_status": startup.enrichment_status.value,
        "enrichment_error": startup.enrichment_error,
        "enriched_at": startup.enriched_at.isoformat() if startup.enriched_at else None,
        "created_at": startup.created_at.isoformat(),
        "updated_at": startup.updated_at.isoformat(),
        "industries": [
            {"id": str(i.id), "name": i.name, "slug": i.slug}
            for i in startup.industries
        ],
        "founders": [
            {
                "id": str(f.id),
                "name": f.name,
                "title": f.title,
                "linkedin_url": f.linkedin_url,
                "sort_order": f.sort_order,
            }
            for f in founders
        ],
        "funding_rounds": [
            {
                "id": str(fr.id),
                "round_name": fr.round_name,
                "amount": fr.amount,
                "date": fr.date,
                "lead_investor": fr.lead_investor,
                "sort_order": fr.sort_order,
            }
            for fr in funding_rounds
        ],
        "ai_review": {
            "id": str(review.id),
            "overall_score": review.overall_score,
            "investment_thesis": review.investment_thesis,
            "key_risks": review.key_risks,
            "verdict": review.verdict,
            "dimension_scores": review.dimension_scores,
            "created_at": review.created_at.isoformat(),
        } if review else None,
    }
