import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.investor import BatchJobStatus, Investor, InvestorBatchJob
from app.models.user import User

router = APIRouter()


@router.post("/api/admin/investors/batch")
async def start_investor_batch(
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Check no job is already running or paused
    result = await db.execute(
        select(InvestorBatchJob).where(
            InvestorBatchJob.status.in_([
                BatchJobStatus.running.value,
                BatchJobStatus.paused.value,
            ])
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A batch job is already {existing.status}. Pause or wait for it to finish.",
        )

    job = InvestorBatchJob()
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from app.services.investor_extraction import run_investor_batch

    background_tasks.add_task(run_investor_batch, str(job.id))

    return {
        "id": str(job.id),
        "status": job.status,
    }


@router.put("/api/admin/investors/batch/{job_id}/pause")
async def pause_investor_batch(
    job_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(InvestorBatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.running.value:
        raise HTTPException(status_code=400, detail="Job is not running")

    from datetime import datetime, timezone

    job.status = BatchJobStatus.paused.value
    job.paused_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": str(job.id), "status": job.status}


@router.put("/api/admin/investors/batch/{job_id}/resume")
async def resume_investor_batch(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(InvestorBatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.paused.value:
        raise HTTPException(status_code=400, detail="Job is not paused")

    job.status = BatchJobStatus.running.value
    await db.commit()

    from app.services.investor_extraction import run_investor_batch

    background_tasks.add_task(run_investor_batch, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.get("/api/admin/investors/batch/status")
async def get_batch_status(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InvestorBatchJob).order_by(InvestorBatchJob.created_at.desc()).limit(1)
    )
    job = result.scalar_one_or_none()
    if not job:
        return None

    return {
        "id": str(job.id),
        "status": job.status,
        "total_startups": job.total_startups,
        "processed_startups": job.processed_startups,
        "current_startup_name": job.current_startup_name,
        "investors_found": job.investors_found,
        "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "paused_at": job.paused_at.isoformat() if job.paused_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/api/admin/investors")
async def list_investors(
    q: str | None = None,
    stage_focus: str | None = None,
    sector_focus: str | None = None,
    location: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort: str = "firm_name",
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Investor)

    if q:
        like = f"%{q}%"
        query = query.where(
            Investor.firm_name.ilike(like)
            | Investor.partner_name.ilike(like)
            | Investor.email.ilike(like)
        )
    if stage_focus:
        query = query.where(Investor.stage_focus.ilike(f"%{stage_focus}%"))
    if sector_focus:
        query = query.where(Investor.sector_focus.ilike(f"%{sector_focus}%"))
    if location:
        query = query.where(Investor.location.ilike(f"%{location}%"))

    # Count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # Sort
    if sort == "created_at":
        query = query.order_by(Investor.created_at.desc())
    elif sort == "partner_name":
        query = query.order_by(Investor.partner_name)
    else:
        query = query.order_by(Investor.firm_name)

    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    investors = result.scalars().all()

    pages = max(1, (total + per_page - 1) // per_page)

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "items": [
            {
                "id": str(inv.id),
                "firm_name": inv.firm_name,
                "partner_name": inv.partner_name,
                "email": inv.email,
                "website": inv.website,
                "stage_focus": inv.stage_focus,
                "sector_focus": inv.sector_focus,
                "location": inv.location,
                "aum_fund_size": inv.aum_fund_size,
                "recent_investments": inv.recent_investments,
                "fit_reason": inv.fit_reason,
                "source_startups": inv.source_startups,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in investors
        ],
    }


@router.delete("/api/admin/investors/{investor_id}")
async def delete_investor(
    investor_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    inv = await db.get(Investor, investor_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Investor not found")
    await db.delete(inv)
    await db.commit()
    return {"ok": True}
