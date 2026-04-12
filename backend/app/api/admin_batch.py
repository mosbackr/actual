from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.batch_job import (
    BatchJob,
    BatchJobPhase,
    BatchJobStatus,
    BatchJobStep,
    BatchJobType,
    BatchStepStatus,
    BatchStepType,
)
from app.models.startup import Startup
from app.models.user import User
from app.services.batch_locations import BATCH_LOCATIONS, BATCH_STAGES, format_location
from app.services.batch_worker import run_batch_worker

router = APIRouter()


class BatchStartRequest(BaseModel):
    job_type: str = "initial"
    refresh_days: int = 30


@router.post("/api/admin/batch/start")
async def start_batch(
    body: BatchStartRequest,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Check no job is already running
    existing = await db.execute(
        select(BatchJob).where(
            BatchJob.status.in_([BatchJobStatus.running, BatchJobStatus.pending])
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="A batch job is already running")

    # Create job
    job_type = BatchJobType.refresh if body.job_type == "refresh" else BatchJobType.initial
    job = BatchJob(
        job_type=job_type,
        status=BatchJobStatus.running,
        refresh_days=body.refresh_days if job_type == BatchJobType.refresh else None,
        current_phase=BatchJobPhase.discovering_investors,
    )
    db.add(job)
    await db.flush()

    # Generate initial discover_investors steps
    sort_order = 0
    for loc in BATCH_LOCATIONS:
        for stage in BATCH_STAGES:
            step = BatchJobStep(
                job_id=job.id,
                step_type=BatchStepType.discover_investors,
                params={
                    "city": loc["city"],
                    "state": loc["state"],
                    "country": loc["country"],
                    "stage": stage,
                },
                sort_order=sort_order,
            )
            db.add(step)
            sort_order += 1

    job.progress_summary = {
        "locations_total": sort_order,
        "locations_completed": 0,
        "investors_found": 0,
        "startups_found": 0,
        "startups_added": 0,
        "startups_skipped_duplicate": 0,
        "startups_enriched": 0,
        "startups_enrich_failed": 0,
    }

    await db.commit()

    # Launch worker
    background_tasks.add_task(run_batch_worker, str(job.id))

    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "total_steps": sort_order,
    }


@router.post("/api/admin/batch/{job_id}/pause")
async def pause_batch(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BatchJob).where(BatchJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.running:
        raise HTTPException(status_code=400, detail=f"Cannot pause job in {job.status.value} state")

    job.status = BatchJobStatus.paused
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "paused"}


@router.post("/api/admin/batch/{job_id}/resume")
async def resume_batch(
    job_id: str,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BatchJob).where(BatchJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in (BatchJobStatus.paused, BatchJobStatus.cancelled):
        raise HTTPException(
            status_code=400, detail=f"Cannot resume job in {job.status.value} state"
        )

    # Reset any steps stuck in "running" state (from a crashed worker)
    stuck_steps = await db.execute(
        select(BatchJobStep)
        .where(BatchJobStep.job_id == job.id)
        .where(BatchJobStep.status == BatchStepStatus.running)
    )
    for step in stuck_steps.scalars().all():
        step.status = BatchStepStatus.pending

    job.status = BatchJobStatus.running
    job.error = None
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()

    background_tasks.add_task(run_batch_worker, str(job.id))
    return {"status": "running"}


@router.post("/api/admin/batch/{job_id}/cancel")
async def cancel_batch(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BatchJob).where(BatchJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = BatchJobStatus.cancelled
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "cancelled"}


@router.get("/api/admin/batch/active")
async def get_active_batch(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BatchJob).order_by(BatchJob.created_at.desc()).limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None

    elapsed = (datetime.now(timezone.utc) - job.created_at).total_seconds()

    return {
        "id": str(job.id),
        "job_type": job.job_type.value,
        "status": job.status.value,
        "current_phase": job.current_phase.value,
        "progress_summary": job.progress_summary,
        "error": job.error,
        "refresh_days": job.refresh_days,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "elapsed_seconds": int(elapsed),
    }


@router.get("/api/admin/batch/{job_id}/steps")
async def get_batch_steps(
    job_id: str,
    step_type: str | None = None,
    status: str | None = None,
    page: int = 1,
    per_page: int = 50,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    query = select(BatchJobStep).where(BatchJobStep.job_id == job_id)

    if step_type:
        query = query.where(BatchJobStep.step_type == step_type)
    if status:
        query = query.where(BatchJobStep.status == status)

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate
    offset = (page - 1) * per_page
    result = await db.execute(
        query.order_by(BatchJobStep.sort_order).offset(offset).limit(per_page)
    )
    steps = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [
            {
                "id": str(s.id),
                "step_type": s.step_type.value,
                "status": s.status.value,
                "params": s.params,
                "result": s.result,
                "error": s.error,
                "sort_order": s.sort_order,
                "created_at": s.created_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in steps
        ],
    }


@router.get("/api/admin/batch/{job_id}/investors")
async def get_batch_investors(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Get all find_startups steps for this job
    result = await db.execute(
        select(BatchJobStep)
        .where(BatchJobStep.job_id == job_id)
        .where(BatchJobStep.step_type == BatchStepType.find_startups)
        .order_by(BatchJobStep.sort_order)
    )
    steps = result.scalars().all()

    items = []
    for s in steps:
        p = s.params
        startups_found = 0
        if s.result and "startups" in s.result:
            startups_found = len(s.result["startups"])
        items.append(
            {
                "name": p.get("investor", ""),
                "city": p.get("city", ""),
                "state": p.get("state"),
                "country": p.get("country", ""),
                "stage": p.get("stage", ""),
                "startups_found": startups_found,
                "status": s.status.value,
            }
        )

    return {"total": len(items), "items": items}


@router.get("/api/admin/batch/{job_id}/startups")
async def get_batch_startups(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Get all add_to_triage and enrich steps
    triage_result = await db.execute(
        select(BatchJobStep)
        .where(BatchJobStep.job_id == job_id)
        .where(BatchJobStep.step_type == BatchStepType.add_to_triage)
        .where(BatchJobStep.status == BatchStepStatus.completed)
    )
    triage_steps = triage_result.scalars().all()

    # Collect all created startup IDs
    startup_ids = []
    startup_sources = {}
    for ts in triage_steps:
        source = ts.params.get("source_investor", "")
        for created in (ts.result or {}).get("created", []):
            sid = created["id"]
            startup_ids.append(sid)
            startup_sources[sid] = source

    if not startup_ids:
        return {"total": 0, "items": []}

    # Fetch actual startup records
    startups_result = await db.execute(
        select(Startup).where(Startup.id.in_(startup_ids))
    )
    startups = {str(s.id): s for s in startups_result.scalars().all()}

    # Get enrich step status for each startup
    enrich_result = await db.execute(
        select(BatchJobStep)
        .where(BatchJobStep.job_id == job_id)
        .where(BatchJobStep.step_type == BatchStepType.enrich)
    )
    enrich_status = {}
    for es in enrich_result.scalars().all():
        sid = es.params.get("startup_id")
        if sid:
            enrich_status[sid] = {
                "status": es.status.value,
                "error": es.error,
                "ai_score": (es.result or {}).get("ai_score"),
            }

    items = []
    for sid in startup_ids:
        s = startups.get(sid)
        if s is None:
            continue
        es = enrich_status.get(sid, {})
        items.append(
            {
                "id": sid,
                "name": s.name,
                "source_investor": startup_sources.get(sid, ""),
                "stage": s.stage.value,
                "location_city": s.location_city,
                "location_state": s.location_state,
                "triage_status": s.status.value,
                "enrichment_status": s.enrichment_status.value if s.enrichment_status else "none",
                "ai_score": s.ai_score,
                "enrich_error": es.get("error"),
            }
        )

    return {"total": len(items), "items": items}


@router.get("/api/admin/batch/{job_id}/log")
async def get_batch_log(
    job_id: str,
    page: int = 1,
    per_page: int = 100,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Get completed/failed steps, most recent first
    result = await db.execute(
        select(BatchJobStep)
        .where(BatchJobStep.job_id == job_id)
        .where(
            BatchJobStep.status.in_(
                [BatchStepStatus.completed, BatchStepStatus.failed, BatchStepStatus.running]
            )
        )
        .order_by(BatchJobStep.completed_at.desc().nulls_last())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    steps = result.scalars().all()

    items = []
    for s in steps:
        p = s.params or {}
        # Build human-readable message
        if s.step_type == BatchStepType.discover_investors:
            loc = f"{p.get('city', '')}, {p.get('state') or p.get('country', '')}"
            stage = p.get("stage", "")
            if s.status == BatchStepStatus.completed:
                count = len((s.result or {}).get("investors", []))
                msg = f"Found {count} {stage} investors in {loc}"
            elif s.status == BatchStepStatus.running:
                msg = f"Searching for {stage} investors in {loc}..."
            else:
                msg = f"Failed to find investors in {loc}: {s.error or 'unknown error'}"
        elif s.step_type == BatchStepType.find_startups:
            inv = p.get("investor", "")
            stage = p.get("stage", "")
            if s.status == BatchStepStatus.completed:
                count = len((s.result or {}).get("startups", []))
                msg = f"Found {count} startups from {inv} ({stage})"
            elif s.status == BatchStepStatus.running:
                msg = f"Finding startups from {inv} ({stage})..."
            else:
                msg = f"Failed to find startups from {inv}: {s.error or 'unknown error'}"
        elif s.step_type == BatchStepType.add_to_triage:
            inv = p.get("source_investor", "")
            if s.status == BatchStepStatus.completed:
                created = len((s.result or {}).get("created", []))
                skipped = len((s.result or {}).get("skipped", []))
                msg = f"Added {created} startups to triage from {inv}"
                if skipped:
                    msg += f" ({skipped} duplicates skipped)"
            else:
                msg = f"Failed to add startups from {inv}: {s.error or 'unknown error'}"
        elif s.step_type == BatchStepType.enrich:
            name = p.get("startup_name", "")
            if s.status == BatchStepStatus.completed:
                score = (s.result or {}).get("ai_score")
                msg = f"Enriched {name}"
                if score is not None:
                    msg += f" — AI score: {score:.0f}"
            elif s.status == BatchStepStatus.running:
                msg = f"Enriching {name}..."
            else:
                msg = f"Failed to enrich {name}: {s.error or 'unknown error'}"
        else:
            msg = f"Step {s.step_type.value}: {s.status.value}"

        items.append(
            {
                "timestamp": (s.completed_at or s.created_at).isoformat(),
                "message": msg,
                "step_type": s.step_type.value,
                "status": s.status.value,
            }
        )

    return {"items": items}
