import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.pitch_analysis import (
    AgentType,
    AnalysisDocument,
    AnalysisReport,
    AnalysisStatus,
    PitchAnalysis,
)
from app.models.startup import Startup, StartupStatus
from app.models.user import SubscriptionStatus, User
from app.services import s3

router = APIRouter()

ALLOWED_TYPES = {"pdf", "docx", "doc", "pptx", "ppt", "xlsx", "xls", "csv", "md", "txt"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
MAX_TOTAL_SIZE = 50 * 1024 * 1024  # 50MB
MAX_FILES = 10


def _get_file_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext


def _analysis_to_dict(analysis: PitchAnalysis, include_reports: bool = False) -> dict:
    d = {
        "id": str(analysis.id),
        "company_name": analysis.company_name,
        "status": analysis.status.value if hasattr(analysis.status, "value") else analysis.status,
        "current_agent": analysis.current_agent,
        "overall_score": analysis.overall_score,
        "fundraising_likelihood": analysis.fundraising_likelihood,
        "recommended_raise": analysis.recommended_raise,
        "exit_likelihood": analysis.exit_likelihood,
        "expected_exit_value": analysis.expected_exit_value,
        "expected_exit_timeline": analysis.expected_exit_timeline,
        "executive_summary": analysis.executive_summary,
        "publish_consent": analysis.publish_consent,
        "is_free_analysis": analysis.is_free_analysis,
        "startup_id": str(analysis.startup_id) if analysis.startup_id else None,
        "error": analysis.error,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None,
    }
    if include_reports and analysis.reports:
        d["reports"] = [
            {
                "id": str(r.id),
                "agent_type": r.agent_type.value if hasattr(r.agent_type, "value") else r.agent_type,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "score": r.score,
                "summary": r.summary,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in analysis.reports
        ]
    if analysis.documents:
        d["documents"] = [
            {
                "id": str(doc.id),
                "filename": doc.filename,
                "file_type": doc.file_type,
                "file_size_bytes": doc.file_size_bytes,
            }
            for doc in analysis.documents
        ]
    return d


@router.post("/api/analyze")
async def create_analysis(
    files: list[UploadFile] = File(...),
    company_name: str = Form(...),
    publish_consent: bool = Form(True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check subscription
    count_result = await db.execute(
        select(func.count(PitchAnalysis.id)).where(
            PitchAnalysis.user_id == user.id,
            PitchAnalysis.status == AnalysisStatus.complete,
        )
    )
    completed_count = count_result.scalar() or 0

    sub_status = user.subscription_status
    if hasattr(sub_status, "value"):
        sub_status = sub_status.value

    if completed_count >= 1 and sub_status != "active":
        raise HTTPException(
            status_code=402,
            detail="Free analysis used. Subscribe for $19.99/mo for unlimited analyses.",
        )

    # Validate files
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Maximum {MAX_FILES} files allowed")
    if not files:
        raise HTTPException(400, "At least one file is required")

    total_size = 0
    for f in files:
        file_type = _get_file_type(f.filename or "")
        if file_type not in ALLOWED_TYPES:
            raise HTTPException(400, f"Unsupported file type: .{file_type}")

    is_free = completed_count == 0

    # Create analysis record
    analysis = PitchAnalysis(
        user_id=user.id,
        company_name=company_name,
        publish_consent=publish_consent,
        is_free_analysis=is_free,
        status=AnalysisStatus.pending,
    )
    db.add(analysis)
    await db.flush()

    # Upload files to S3 and create document records
    for f in files:
        data = await f.read()
        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(400, f"File {f.filename} exceeds 20MB limit")
        total_size += len(data)
        if total_size > MAX_TOTAL_SIZE:
            raise HTTPException(400, "Total upload size exceeds 50MB limit")

        file_type = _get_file_type(f.filename or "")
        s3_key = f"analyses/{analysis.id}/{uuid.uuid4()}/{f.filename}"

        s3.upload_file(data, s3_key)

        doc = AnalysisDocument(
            analysis_id=analysis.id,
            filename=f.filename or "unnamed",
            file_type=file_type,
            s3_key=s3_key,
            file_size_bytes=len(data),
        )
        db.add(doc)

    await db.commit()
    return {"id": str(analysis.id), "status": "pending"}


@router.get("/api/analyze")
async def list_analyses(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.user_id == user.id)
        .order_by(PitchAnalysis.created_at.desc())
    )
    analyses = result.scalars().all()
    return {
        "items": [
            {
                "id": str(a.id),
                "company_name": a.company_name,
                "status": a.status.value if hasattr(a.status, "value") else a.status,
                "overall_score": a.overall_score,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "completed_at": a.completed_at.isoformat() if a.completed_at else None,
            }
            for a in analyses
        ]
    }


@router.get("/api/analyze/{analysis_id}")
async def get_analysis(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
        .options(selectinload(PitchAnalysis.reports), selectinload(PitchAnalysis.documents))
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    return _analysis_to_dict(analysis, include_reports=True)


@router.get("/api/analyze/{analysis_id}/reports")
async def get_all_reports(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    result = await db.execute(
        select(AnalysisReport).where(AnalysisReport.analysis_id == analysis_id)
    )
    reports = result.scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "agent_type": r.agent_type.value if hasattr(r.agent_type, "value") else r.agent_type,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "score": r.score,
                "summary": r.summary,
                "report": r.report,
                "key_findings": r.key_findings,
                "error": r.error,
            }
            for r in reports
        ]
    }


@router.get("/api/analyze/{analysis_id}/reports/{agent_type}")
async def get_single_report(
    analysis_id: uuid.UUID,
    agent_type: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Analysis not found")

    result = await db.execute(
        select(AnalysisReport).where(
            AnalysisReport.analysis_id == analysis_id,
            AnalysisReport.agent_type == agent_type,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")

    return {
        "id": str(report.id),
        "agent_type": report.agent_type.value if hasattr(report.agent_type, "value") else report.agent_type,
        "status": report.status.value if hasattr(report.status, "value") else report.status,
        "score": report.score,
        "summary": report.summary,
        "report": report.report,
        "key_findings": report.key_findings,
        "error": report.error,
    }


@router.delete("/api/analyze/{analysis_id}")
async def delete_analysis(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
        .options(selectinload(PitchAnalysis.documents))
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    s3_keys = [doc.s3_key for doc in analysis.documents]
    if s3_keys:
        s3.delete_files(s3_keys)

    await db.delete(analysis)
    await db.commit()
    return {"ok": True}


@router.patch("/api/analyze/{analysis_id}")
async def update_analysis(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    publish_consent: Optional[bool] = None,
):
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    if publish_consent is not None:
        analysis.publish_consent = publish_consent
        if analysis.startup_id:
            result = await db.execute(
                select(Startup).where(Startup.id == analysis.startup_id)
            )
            startup = result.scalar_one_or_none()
            if startup:
                startup.status = StartupStatus.approved if publish_consent else StartupStatus.rejected

    await db.commit()
    return {"ok": True}


@router.post("/api/analyze/{analysis_id}/resubmit")
async def resubmit_analysis(
    analysis_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub_status = user.subscription_status
    if hasattr(sub_status, "value"):
        sub_status = sub_status.value
    if sub_status != "active":
        raise HTTPException(402, "Subscription required for re-evaluation")

    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
        .options(
            selectinload(PitchAnalysis.documents),
            selectinload(PitchAnalysis.reports),
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    # Clean up old S3 files
    old_keys = [doc.s3_key for doc in analysis.documents]
    if old_keys:
        s3.delete_files(old_keys)

    # Delete old documents and reports
    for doc in analysis.documents:
        await db.delete(doc)
    for report in analysis.reports:
        await db.delete(report)

    # Upload new files
    if not files:
        raise HTTPException(400, "At least one file is required")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Maximum {MAX_FILES} files allowed")

    total_size = 0
    for f in files:
        file_type = _get_file_type(f.filename or "")
        if file_type not in ALLOWED_TYPES:
            raise HTTPException(400, f"Unsupported file type: .{file_type}")

        data = await f.read()
        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(400, f"File {f.filename} exceeds 20MB limit")
        total_size += len(data)
        if total_size > MAX_TOTAL_SIZE:
            raise HTTPException(400, "Total upload size exceeds 50MB limit")

        s3_key = f"analyses/{analysis.id}/{uuid.uuid4()}/{f.filename}"
        s3.upload_file(data, s3_key)

        doc = AnalysisDocument(
            analysis_id=analysis.id,
            filename=f.filename or "unnamed",
            file_type=file_type,
            s3_key=s3_key,
            file_size_bytes=len(data),
        )
        db.add(doc)

    # Reset analysis
    analysis.status = AnalysisStatus.pending
    analysis.current_agent = None
    analysis.overall_score = None
    analysis.fundraising_likelihood = None
    analysis.recommended_raise = None
    analysis.exit_likelihood = None
    analysis.expected_exit_value = None
    analysis.expected_exit_timeline = None
    analysis.executive_summary = None
    analysis.error = None
    analysis.claimed_at = None
    analysis.completed_at = None
    analysis.is_free_analysis = False

    await db.commit()
    return {"id": str(analysis.id), "status": "pending"}
