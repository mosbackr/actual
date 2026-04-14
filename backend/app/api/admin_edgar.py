from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.edgar_job import (
    EdgarJob,
    EdgarJobPhase,
    EdgarJobStatus,
    EdgarJobStep,
    EdgarStepStatus,
    EdgarStepType,
)
from app.models.startup import Startup
from app.models.user import User
from app.services.edgar_worker import run_edgar_worker

router = APIRouter()


class EdgarStartRequest(BaseModel):
    scan_mode: str = "full"
    discover_days: int = 365
    form_types: list[str] = ["D", "S-1", "10-K", "C", "1-A"]

    @field_validator("form_types")
    @classmethod
    def validate_form_types(cls, v):
        allowed = {"D", "S-1", "10-K", "C", "1-A"}
        invalid = set(v) - allowed
        if invalid:
            raise ValueError(f"Invalid form types: {invalid}. Allowed: {allowed}")
        return v


@router.post("/api/admin/edgar/start")
async def start_edgar_scan(
    body: EdgarStartRequest,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(EdgarJob).where(
            EdgarJob.status.in_([EdgarJobStatus.running, EdgarJobStatus.pending])
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="An EDGAR scan is already running")

    job = EdgarJob(
        scan_mode=body.scan_mode,
        status=EdgarJobStatus.running,
        current_phase=EdgarJobPhase.resolving_ciks,
    )
    db.add(job)
    await db.flush()

    sort_order = 0

    if body.scan_mode == "discover":
        job.current_phase = EdgarJobPhase.discovering

        for form_type in body.form_types:
            step = EdgarJobStep(
                job_id=job.id,
                step_type=EdgarStepType.discover_filings,
                params={"discover_days": body.discover_days, "form_type": form_type},
                sort_order=sort_order,
            )
            db.add(step)
            sort_order += 1

        job.progress_summary = {
            "filings_discovered": 0,
            "companies_extracted": 0,
            "extract_total": 0,
            "duplicates_skipped": 0,
            "startups_created": 0,
            "enrichments_completed": 0,
            "enrichments_failed": 0,
            "enrich_total": 0,
            "form_types": body.form_types,
        }
    else:
        # Existing scan mode logic (resolve_cik + fetch_filings)
        cik_query = (
            select(Startup.id, Startup.name)
            .where(Startup.location_country == "US")
            .where(Startup.sec_cik.is_(None))
        )
        if body.scan_mode == "new_only":
            cik_query = cik_query.where(Startup.edgar_last_scanned_at.is_(None))

        cik_result = await db.execute(cik_query)
        for startup_id, startup_name in cik_result.all():
            step = EdgarJobStep(
                job_id=job.id,
                step_type=EdgarStepType.resolve_cik,
                params={"startup_id": str(startup_id), "startup_name": startup_name},
                sort_order=sort_order,
            )
            db.add(step)
            sort_order += 1

        fetch_query = (
            select(Startup.id, Startup.name, Startup.sec_cik)
            .where(Startup.sec_cik.is_not(None))
        )
        fetch_result = await db.execute(fetch_query)
        for startup_id, startup_name, sec_cik in fetch_result.all():
            step = EdgarJobStep(
                job_id=job.id,
                step_type=EdgarStepType.fetch_filings,
                params={
                    "startup_id": str(startup_id),
                    "startup_name": startup_name,
                    "cik": sec_cik,
                },
                sort_order=sort_order,
            )
            db.add(step)
            sort_order += 1

        job.progress_summary = {
            "startups_total": sort_order,
            "startups_scanned": 0,
            "ciks_matched": 0,
            "filings_found": 0,
            "filings_total": 0,
            "filings_processed": 0,
            "rounds_updated": 0,
            "rounds_created": 0,
            "valuations_added": 0,
        }

    await db.commit()
    background_tasks.add_task(run_edgar_worker, str(job.id))

    return {
        "job_id": str(job.id),
        "status": job.status,
        "total_steps": sort_order,
    }


@router.post("/api/admin/edgar/{job_id}/pause")
async def pause_edgar(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(EdgarJob).where(EdgarJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != EdgarJobStatus.running:
        raise HTTPException(status_code=400, detail=f"Cannot pause job in {job.status} state")

    job.status = EdgarJobStatus.paused
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "paused"}


@router.post("/api/admin/edgar/{job_id}/resume")
async def resume_edgar(
    job_id: str,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(EdgarJob).where(EdgarJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in (EdgarJobStatus.paused, EdgarJobStatus.cancelled):
        raise HTTPException(status_code=400, detail=f"Cannot resume job in {job.status} state")

    stuck_steps = await db.execute(
        select(EdgarJobStep)
        .where(EdgarJobStep.job_id == job.id)
        .where(EdgarJobStep.status == EdgarStepStatus.running)
    )
    for step in stuck_steps.scalars().all():
        step.status = EdgarStepStatus.pending

    job.status = EdgarJobStatus.running
    job.error = None
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()

    background_tasks.add_task(run_edgar_worker, str(job.id))
    return {"status": "running"}


@router.post("/api/admin/edgar/{job_id}/cancel")
async def cancel_edgar(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(EdgarJob).where(EdgarJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = EdgarJobStatus.cancelled
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "cancelled"}


@router.get("/api/admin/edgar/active")
async def get_active_edgar(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EdgarJob).order_by(EdgarJob.created_at.desc()).limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None

    elapsed = (datetime.now(timezone.utc) - job.created_at).total_seconds()

    return {
        "id": str(job.id),
        "scan_mode": job.scan_mode,
        "status": job.status,
        "current_phase": job.current_phase,
        "progress_summary": job.progress_summary,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "elapsed_seconds": int(elapsed),
    }


@router.get("/api/admin/edgar/{job_id}/startups")
async def get_edgar_startups(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EdgarJobStep)
        .where(EdgarJobStep.job_id == job_id)
        .where(EdgarJobStep.step_type.in_([EdgarStepType.resolve_cik, EdgarStepType.fetch_filings]))
        .order_by(EdgarJobStep.sort_order)
    )
    steps = result.scalars().all()

    items = []
    for s in steps:
        p = s.params or {}
        cik = None
        filings_found = 0

        if s.step_type == EdgarStepType.resolve_cik:
            cik = (s.result or {}).get("cik")
        elif s.step_type == EdgarStepType.fetch_filings:
            cik = p.get("cik")
            filings_found = (s.result or {}).get("filings_count", 0)

        items.append({
            "startup_name": p.get("startup_name", ""),
            "startup_id": p.get("startup_id", ""),
            "cik": cik,
            "filings_found": filings_found,
            "status": s.status,
            "step_type": s.step_type,
        })

    return {"total": len(items), "items": items}


@router.get("/api/admin/edgar/{job_id}/filings")
async def get_edgar_filings(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EdgarJobStep)
        .where(EdgarJobStep.job_id == job_id)
        .where(EdgarJobStep.step_type == EdgarStepType.process_filing)
        .order_by(EdgarJobStep.sort_order)
    )
    steps = result.scalars().all()

    items = []
    for s in steps:
        p = s.params or {}
        r = s.result or {}
        items.append({
            "startup_name": p.get("startup_name", ""),
            "filing_type": p.get("filing_type", ""),
            "filing_date": p.get("filing_date", ""),
            "action": r.get("action", ""),
            "amount": r.get("amount"),
            "rounds_extracted": r.get("rounds_extracted"),
            "valuation_added": r.get("valuation_added", False),
            "status": s.status,
            "error": s.error,
        })

    return {"total": len(items), "items": items}


@router.get("/api/admin/edgar/{job_id}/log")
async def get_edgar_log(
    job_id: str,
    page: int = 1,
    per_page: int = 100,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EdgarJobStep)
        .where(EdgarJobStep.job_id == job_id)
        .where(
            EdgarJobStep.status.in_(
                [EdgarStepStatus.completed, EdgarStepStatus.failed, EdgarStepStatus.running]
            )
        )
        .order_by(EdgarJobStep.completed_at.desc().nulls_last())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    steps = result.scalars().all()

    items = []
    for s in steps:
        p = s.params or {}
        r = s.result or {}
        name = p.get("startup_name", "")

        if s.step_type == EdgarStepType.resolve_cik:
            if s.status == EdgarStepStatus.completed:
                cik = r.get("cik")
                msg = f"Matched {name} → CIK {cik}" if cik else f"No CIK match for {name}"
            elif s.status == EdgarStepStatus.running:
                msg = f"Resolving CIK for {name}..."
            else:
                msg = f"Failed CIK resolution for {name}: {s.error or 'unknown'}"

        elif s.step_type == EdgarStepType.fetch_filings:
            if s.status == EdgarStepStatus.completed:
                count = r.get("filings_count", 0)
                msg = f"Found {count} filings for {name}"
            elif s.status == EdgarStepStatus.running:
                msg = f"Fetching filings for {name}..."
            else:
                msg = f"Failed to fetch filings for {name}: {s.error or 'unknown'}"

        elif s.step_type == EdgarStepType.process_filing:
            ftype = p.get("filing_type", "")
            if s.status == EdgarStepStatus.completed:
                action = r.get("action", "")
                amount = r.get("amount", "")
                if action == "created":
                    msg = f"Created round from {ftype} for {name}"
                    if amount:
                        msg += f" ({amount})"
                elif action == "updated":
                    msg = f"Updated round from {ftype} for {name}"
                    if amount:
                        msg += f" ({amount})"
                elif r.get("rounds_extracted"):
                    msg = f"Extracted {r['rounds_extracted']} rounds from {ftype} for {name}"
                else:
                    msg = f"Processed {ftype} for {name}"
                if r.get("valuation_added"):
                    msg += " [+valuation]"
            elif s.status == EdgarStepStatus.running:
                msg = f"Processing {ftype} for {name}..."
            else:
                msg = f"Failed to process {ftype} for {name}: {s.error or 'unknown'}"
        elif s.step_type == EdgarStepType.discover_filings:
            form_type = p.get("form_type", "D")
            form_labels = {"D": "Form D", "S-1": "S-1", "10-K": "10-K", "C": "Form C", "1-A": "Form 1-A"}
            label = form_labels.get(form_type, form_type)
            if s.status == EdgarStepStatus.completed:
                created = r.get("extract_steps_created", 0)
                date_range = r.get("date_range", "")
                msg = f"Discovered {created} {label} filings ({date_range})"
            elif s.status == EdgarStepStatus.running:
                msg = f"Searching EDGAR for {label} filings..."
            else:
                msg = f"Discovery search failed for {label}: {s.error or 'unknown'}"

        elif s.step_type == EdgarStepType.extract_company:
            entity = p.get("entity_name", "") or r.get("issuer_name", "")
            form_type = p.get("form_type", "D")
            form_labels = {"D": "Form D", "S-1": "S-1", "10-K": "10-K", "C": "Form C", "1-A": "Form 1-A"}
            label = form_labels.get(form_type, form_type)
            if s.status == EdgarStepStatus.completed:
                action = r.get("action", "")
                if action == "new_company":
                    amount = r.get("amount", 0)
                    msg = f"New ({label}): {entity}"
                    if amount:
                        msg += f" (${amount:,.0f})" if isinstance(amount, (int, float)) else f" ({amount})"
                elif action == "duplicate":
                    existing = r.get("existing_startup", "")
                    msg = f"Duplicate ({label}): {entity} → {existing}"
                else:
                    reason = r.get("reason", "filtered")
                    msg = f"Skipped ({label}): {entity} ({reason})"
            elif s.status == EdgarStepStatus.running:
                msg = f"Extracting ({label}): {entity}..."
            else:
                msg = f"Extract failed ({label}) for {entity}: {s.error or 'unknown'}"

        elif s.step_type == EdgarStepType.add_startup:
            name = p.get("issuer_name", "") or r.get("startup_name", "")
            form_type = p.get("form_type", r.get("form_type", "D"))
            form_labels = {"D": "Form D", "S-1": "S-1", "10-K": "10-K", "C": "Form C", "1-A": "Form 1-A"}
            label = form_labels.get(form_type, form_type)
            if s.status == EdgarStepStatus.completed:
                entity_type = r.get("entity_type", "startup")
                stage = r.get("stage", "")
                amount = r.get("amount", "")
                if entity_type == "fund":
                    msg = f"Fund ({label}): {name} (saved, skipping enrichment)"
                else:
                    msg = f"Created ({label}): {name} ({stage})"
                if amount:
                    msg += f" — {amount}"
            elif s.status == EdgarStepStatus.running:
                msg = f"Classifying ({label}): {name}..."
            else:
                msg = f"Failed to create ({label}) {name}: {s.error or 'unknown'}"

        elif s.step_type == EdgarStepType.enrich_startup:
            name = p.get("startup_name", "")
            if s.status == EdgarStepStatus.completed:
                action = r.get("action", "")
                if action == "enriched":
                    msg = f"Enriched: {name}"
                elif action == "filtered":
                    msg = f"Filtered: {name} (not a startup)"
                else:
                    msg = f"Enrichment failed: {name} — {r.get('error', '')}"
            elif s.status == EdgarStepStatus.running:
                msg = f"Enriching: {name}..."
            else:
                msg = f"Enrichment failed for {name}: {s.error or 'unknown'}"

        else:
            msg = f"Step {s.step_type}: {s.status}"

        items.append({
            "timestamp": (s.completed_at or s.created_at).isoformat(),
            "message": msg,
            "step_type": s.step_type,
            "status": s.status,
        })

    return {"items": items}
