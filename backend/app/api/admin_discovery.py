import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.discovery import DiscoveryBatchJob
from app.models.founder import StartupFounder
from app.models.investor import BatchJobStatus
from app.models.startup import ClassificationStatus, Startup, StartupStatus

from app.models.user import User

router = APIRouter()


@router.post("/api/admin/discovery/import")
async def import_bulk_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    """Upload a bulk Delaware CSV and start import."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    csv_text = content.decode("utf-8", errors="replace")

    # Check no import already running
    result = await db.execute(
        select(DiscoveryBatchJob).where(
            DiscoveryBatchJob.job_type == "bulk_import",
            DiscoveryBatchJob.status.in_([BatchJobStatus.running.value, BatchJobStatus.paused.value]),
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An import job is already running")

    job = DiscoveryBatchJob(job_type="bulk_import")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from app.services.discovery_import import import_csv
    background_tasks.add_task(import_csv, csv_text, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.post("/api/admin/discovery/batch")
async def start_discovery_batch(
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    """Start the classification + enrichment pipeline on unprocessed discovered startups."""
    result = await db.execute(
        select(DiscoveryBatchJob).where(
            DiscoveryBatchJob.job_type == "enrich",
            DiscoveryBatchJob.status.in_([BatchJobStatus.running.value, BatchJobStatus.paused.value]),
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A pipeline batch is already running")

    job = DiscoveryBatchJob(job_type="enrich")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from app.services.discovery_pipeline import run_discovery_pipeline
    background_tasks.add_task(run_discovery_pipeline, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.put("/api/admin/discovery/batch/{job_id}/pause")
async def pause_discovery_batch(
    job_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(DiscoveryBatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.running.value:
        raise HTTPException(status_code=400, detail="Job is not running")

    job.status = BatchJobStatus.paused.value
    job.paused_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": str(job.id), "status": job.status}


@router.put("/api/admin/discovery/batch/{job_id}/resume")
async def resume_discovery_batch(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(DiscoveryBatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.paused.value:
        raise HTTPException(status_code=400, detail="Job is not paused")

    job.status = BatchJobStatus.running.value
    await db.commit()

    if job.job_type == "bulk_import":
        from app.services.discovery_import import import_csv
        background_tasks.add_task(import_csv, "", str(job.id))
    else:
        from app.services.discovery_pipeline import run_discovery_pipeline
        background_tasks.add_task(run_discovery_pipeline, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.get("/api/admin/discovery/batch/status")
async def get_discovery_batch_status(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    """Get status of most recent import and pipeline jobs."""
    # Most recent import job
    import_result = await db.execute(
        select(DiscoveryBatchJob)
        .where(DiscoveryBatchJob.job_type == "bulk_import")
        .order_by(DiscoveryBatchJob.created_at.desc())
        .limit(1)
    )
    import_job = import_result.scalar_one_or_none()

    # Most recent pipeline job
    pipeline_result = await db.execute(
        select(DiscoveryBatchJob)
        .where(DiscoveryBatchJob.job_type == "enrich")
        .order_by(DiscoveryBatchJob.created_at.desc())
        .limit(1)
    )
    pipeline_job = pipeline_result.scalar_one_or_none()

    def _job_dict(job):
        if not job:
            return None
        return {
            "id": str(job.id),
            "status": job.status,
            "job_type": job.job_type,
            "total_items": job.total_items,
            "processed_items": job.processed_items,
            "current_item_name": job.current_item_name,
            "items_created": job.items_created,
            "error": job.error,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "paused_at": job.paused_at.isoformat() if job.paused_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    # Stats
    total_imported = await db.execute(
        select(func.count()).select_from(Startup).where(Startup.discovery_source == "delaware")
    )
    classified_startup = await db.execute(
        select(func.count()).select_from(Startup).where(
            Startup.discovery_source == "delaware",
            Startup.classification_status == ClassificationStatus.startup,
        )
    )
    enriched = await db.execute(
        select(func.count()).select_from(Startup).where(
            Startup.discovery_source == "delaware",
            Startup.enrichment_status == "complete",
        )
    )
    promoted = await db.execute(
        select(func.count()).select_from(Startup).where(
            Startup.discovery_source == "delaware",
            Startup.status == StartupStatus.approved,
        )
    )

    return {
        "import_job": _job_dict(import_job),
        "pipeline_job": _job_dict(pipeline_job),
        "stats": {
            "total_imported": total_imported.scalar() or 0,
            "classified_startup": classified_startup.scalar() or 0,
            "enriched": enriched.scalar() or 0,
            "promoted": promoted.scalar() or 0,
        },
    }


@router.get("/api/admin/discovery/startups")
async def list_discovered_startups(
    classification: str = "all",
    enrichment: str = "all",
    q: str | None = None,
    sort: str = "delaware_filed_at",
    order: str = "desc",
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Startup).where(Startup.discovery_source == "delaware")

    if classification != "all":
        try:
            cs = ClassificationStatus(classification)
            query = query.where(Startup.classification_status == cs)
        except ValueError:
            pass

    if enrichment != "all":
        query = query.where(Startup.enrichment_status == enrichment)

    if q:
        like = f"%{q}%"
        query = query.where(
            Startup.name.ilike(like) | Startup.delaware_corp_name.ilike(like)
        )

    # Count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # Sort
    sort_map = {
        "delaware_filed_at": Startup.delaware_filed_at,
        "name": Startup.name,
        "created_at": Startup.created_at,
        "classification_status": Startup.classification_status,
    }
    sort_col = sort_map.get(sort, Startup.delaware_filed_at)
    if order == "asc":
        query = query.order_by(sort_col.asc().nullslast())
    else:
        query = query.order_by(sort_col.desc().nullslast())

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    startups = result.scalars().all()

    # Load founders for these startups
    startup_ids = [s.id for s in startups]
    founders_result = await db.execute(
        select(StartupFounder).where(StartupFounder.startup_id.in_(startup_ids))
    )
    all_founders = founders_result.scalars().all()
    founders_by_startup = {}
    for f in all_founders:
        founders_by_startup.setdefault(str(f.startup_id), []).append(f)

    pages = max(1, (total + per_page - 1) // per_page)

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "items": [
            {
                "id": str(s.id),
                "name": s.name,
                "delaware_corp_name": s.delaware_corp_name,
                "delaware_file_number": s.delaware_file_number,
                "delaware_filed_at": s.delaware_filed_at.isoformat() if s.delaware_filed_at else None,
                "status": s.status.value if hasattr(s.status, 'value') else s.status,
                "classification_status": s.classification_status.value if hasattr(s.classification_status, 'value') else s.classification_status,
                "classification_metadata": s.classification_metadata,
                "enrichment_status": s.enrichment_status.value if hasattr(s.enrichment_status, 'value') else s.enrichment_status,
                "description": s.description if s.description else None,
                "tagline": s.tagline,
                "website_url": s.website_url,
                "stage": s.stage.value if hasattr(s.stage, 'value') else s.stage,
                "total_funding": s.total_funding,
                "employee_count": s.employee_count,
                "location_city": s.location_city,
                "location_state": s.location_state,
                "founders": [
                    {
                        "id": str(f.id),
                        "name": f.name,
                        "title": f.title,
                        "headline": f.headline,
                        "location": f.location,
                        "linkedin_url": f.linkedin_url,
                        "profile_photo_url": f.profile_photo_url,
                        "work_history": f.work_history,
                        "education_history": f.education_history,
                    }
                    for f in founders_by_startup.get(str(s.id), [])
                ],
                "created_at": s.created_at.isoformat(),
            }
            for s in startups
        ],
    }


@router.put("/api/admin/discovery/startups/{startup_id}/promote")
async def promote_startup(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    startup = await db.get(Startup, startup_id)
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")
    if startup.discovery_source != "delaware":
        raise HTTPException(status_code=400, detail="Not a discovered startup")

    startup.status = StartupStatus.approved
    await db.commit()
    return {"ok": True, "message": f"Promoted {startup.name} to approved"}


@router.put("/api/admin/discovery/startups/{startup_id}/reject")
async def reject_startup(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    startup = await db.get(Startup, startup_id)
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")

    startup.classification_status = ClassificationStatus.not_startup
    await db.commit()
    return {"ok": True, "message": f"Rejected {startup.name}"}
