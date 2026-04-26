import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.config import settings
from app.db.session import get_db
from app.models.investor import BatchJobStatus
from app.models.marketing import MarketingEmailJob
from app.models.user import User

router = APIRouter()


class GenerateRequest(BaseModel):
    prompt: str


class SendRequest(BaseModel):
    subject: str
    html_template: str


class TestSendRequest(BaseModel):
    email: str
    subject: str
    html_template: str


@router.post("/api/admin/marketing/generate")
async def generate_marketing_email(
    body: GenerateRequest,
    _user: User = Depends(require_role("superadmin")),
):
    from app.services.marketing_email import generate_email_html

    html = await generate_email_html(body.prompt)
    return {"html": html}


@router.post("/api/admin/marketing/send")
async def send_marketing_email(
    body: SendRequest,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MarketingEmailJob).where(
            MarketingEmailJob.status.in_([
                BatchJobStatus.running.value,
                BatchJobStatus.paused.value,
            ])
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A marketing job is already {existing.status}. Pause or wait for it to finish.",
        )

    job = MarketingEmailJob(
        subject=body.subject,
        html_template=body.html_template,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from app.services.marketing_email import run_marketing_batch

    background_tasks.add_task(run_marketing_batch, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.post("/api/admin/marketing/jobs/{job_id}/pause")
async def pause_marketing_job(
    job_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(MarketingEmailJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.running.value:
        raise HTTPException(status_code=400, detail="Job is not running")

    job.status = BatchJobStatus.paused.value
    job.paused_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": str(job.id), "status": job.status}


@router.post("/api/admin/marketing/jobs/{job_id}/resume")
async def resume_marketing_job(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(MarketingEmailJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.paused.value:
        raise HTTPException(status_code=400, detail="Job is not paused")

    job.status = BatchJobStatus.running.value
    await db.commit()

    from app.services.marketing_email import run_marketing_batch

    background_tasks.add_task(run_marketing_batch, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.get("/api/admin/marketing/jobs")
async def list_marketing_jobs(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MarketingEmailJob)
        .order_by(MarketingEmailJob.created_at.desc())
        .limit(20)
    )
    jobs = result.scalars().all()

    return [
        {
            "id": str(job.id),
            "status": job.status,
            "subject": job.subject,
            "total_recipients": job.total_recipients,
            "sent_count": job.sent_count,
            "failed_count": job.failed_count,
            "current_investor_name": job.current_investor_name,
            "error": job.error,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "paused_at": job.paused_at.isoformat() if job.paused_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        }
        for job in jobs
    ]


@router.get("/api/admin/marketing/jobs/{job_id}/emails")
async def list_job_emails(
    job_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    from app.models.marketing import MarketingEmailSent

    result = await db.execute(
        select(MarketingEmailSent)
        .where(MarketingEmailSent.job_id == job_id)
        .order_by(MarketingEmailSent.sent_at.desc())
    )
    emails = result.scalars().all()

    return [
        {
            "id": str(e.id),
            "investor_id": str(e.investor_id),
            "firm_name": e.firm_name,
            "partner_name": e.partner_name,
            "email": e.email,
            "status": e.status,
            "error": e.error,
            "sent_at": e.sent_at.isoformat() if e.sent_at else None,
        }
        for e in emails
    ]


@router.post("/api/admin/marketing/verify")
async def start_verification(
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    from app.models.marketing import EmailVerificationJob

    job = EmailVerificationJob()
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from app.services.email_verification import run_verification_batch

    background_tasks.add_task(run_verification_batch, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.get("/api/admin/marketing/verify/jobs")
async def list_verification_jobs(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    from app.models.marketing import EmailVerificationJob

    result = await db.execute(
        select(EmailVerificationJob)
        .order_by(EmailVerificationJob.created_at.desc())
        .limit(20)
    )
    jobs = result.scalars().all()

    return [
        {
            "id": str(job.id),
            "status": job.status,
            "total_recipients": job.total_recipients,
            "verified_count": job.verified_count,
            "corrected_count": job.corrected_count,
            "bounced_count": job.bounced_count,
            "skipped_count": job.skipped_count,
            "current_investor_name": job.current_investor_name,
            "error": job.error,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        }
        for job in jobs
    ]


@router.post("/api/admin/marketing/test-send")
async def send_test_email(
    body: TestSendRequest,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    import logging
    import traceback

    logger = logging.getLogger(__name__)

    try:
        from app.models.investor_ranking import InvestorRanking

        ranking = (
            await db.execute(
                select(InvestorRanking).limit(1)
            )
        ).scalar_one_or_none()

        if not ranking:
            raise HTTPException(status_code=404, detail="No ranked investors found")

        investor_id = ranking.investor_id

        from app.services.marketing_email import render_for_recipient
        import resend

        personalized_html = render_for_recipient(
            body.html_template, ranking, investor_id, settings.frontend_url
        )

        if not settings.resend_api_key:
            raise HTTPException(status_code=500, detail="Resend API key not configured")

        resend.api_key = settings.resend_api_key

        resend.Emails.send(
            {
                "from": settings.marketing_email_from,
                "to": [body.email],
                "subject": body.subject,
                "html": personalized_html,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test send failed: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to send: {e}")

    return {"ok": True, "message": f"Test email sent to {body.email}"}
