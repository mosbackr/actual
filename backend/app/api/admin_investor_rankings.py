import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.investor import BatchJobStatus, Investor
from app.models.investor_ranking import InvestorRanking, InvestorRankingBatchJob
from app.models.user import User

router = APIRouter()


@router.post("/api/admin/investors/rankings/batch")
async def start_ranking_batch(
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InvestorRankingBatchJob).where(
            InvestorRankingBatchJob.status.in_([
                BatchJobStatus.running.value,
                BatchJobStatus.paused.value,
            ])
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A ranking batch is already {existing.status}. Pause or wait for it to finish.",
        )

    job = InvestorRankingBatchJob()
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from app.services.investor_ranking import run_ranking_batch
    background_tasks.add_task(run_ranking_batch, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.put("/api/admin/investors/rankings/batch/{job_id}/pause")
async def pause_ranking_batch(
    job_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(InvestorRankingBatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.running.value:
        raise HTTPException(status_code=400, detail="Job is not running")

    from datetime import datetime, timezone
    job.status = BatchJobStatus.paused.value
    job.paused_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": str(job.id), "status": job.status}


@router.put("/api/admin/investors/rankings/batch/{job_id}/resume")
async def resume_ranking_batch(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(InvestorRankingBatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.paused.value:
        raise HTTPException(status_code=400, detail="Job is not paused")

    job.status = BatchJobStatus.running.value
    await db.commit()

    from app.services.investor_ranking import run_ranking_batch
    background_tasks.add_task(run_ranking_batch, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.get("/api/admin/investors/rankings/batch/status")
async def get_ranking_batch_status(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InvestorRankingBatchJob)
        .order_by(InvestorRankingBatchJob.created_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if not job:
        return None

    return {
        "id": str(job.id),
        "status": job.status,
        "total_investors": job.total_investors,
        "processed_investors": job.processed_investors,
        "current_investor_name": job.current_investor_name,
        "investors_scored": job.investors_scored,
        "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "paused_at": job.paused_at.isoformat() if job.paused_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


SORT_COLUMNS = {
    "overall_score": InvestorRanking.overall_score,
    "portfolio_performance": InvestorRanking.portfolio_performance,
    "deal_activity": InvestorRanking.deal_activity,
    "exit_track_record": InvestorRanking.exit_track_record,
    "stage_expertise": InvestorRanking.stage_expertise,
    "sector_expertise": InvestorRanking.sector_expertise,
    "follow_on_rate": InvestorRanking.follow_on_rate,
    "network_quality": InvestorRanking.network_quality,
    "firm_name": Investor.firm_name,
}


@router.get("/api/admin/investors/rankings")
async def list_ranked_investors(
    sort: str = "overall_score",
    order: str = "desc",
    q: str | None = None,
    min_score: float | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(InvestorRanking, Investor)
        .join(Investor, InvestorRanking.investor_id == Investor.id)
    )

    if q:
        like = f"%{q}%"
        query = query.where(
            Investor.firm_name.ilike(like) | Investor.partner_name.ilike(like)
        )
    if min_score is not None:
        query = query.where(InvestorRanking.overall_score >= min_score)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    sort_col = SORT_COLUMNS.get(sort, InvestorRanking.overall_score)
    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    rows = result.all()

    pages = max(1, (total + per_page - 1) // per_page)

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "items": [
            {
                "id": str(ranking.id),
                "investor_id": str(investor.id),
                "firm_name": investor.firm_name,
                "partner_name": investor.partner_name,
                "location": investor.location,
                "stage_focus": investor.stage_focus,
                "sector_focus": investor.sector_focus,
                "overall_score": ranking.overall_score,
                "portfolio_performance": ranking.portfolio_performance,
                "deal_activity": ranking.deal_activity,
                "exit_track_record": ranking.exit_track_record,
                "stage_expertise": ranking.stage_expertise,
                "sector_expertise": ranking.sector_expertise,
                "follow_on_rate": ranking.follow_on_rate,
                "network_quality": ranking.network_quality,
                "narrative": ranking.narrative,
                "scored_at": ranking.scored_at.isoformat(),
            }
            for ranking, investor in rows
        ],
    }


@router.post("/api/admin/investors/rankings/{investor_id}/rescore")
async def rescore_investor(
    investor_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    investor = await db.get(Investor, investor_id)
    if not investor:
        raise HTTPException(status_code=404, detail="Investor not found")

    from app.services.investor_ranking import rescore_single
    background_tasks.add_task(rescore_single, str(investor_id))

    return {"ok": True, "message": f"Re-scoring {investor.firm_name} ({investor.partner_name})"}
