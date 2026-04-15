import io
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.investment_memo import InvestmentMemo, MemoStatus
from app.models.pitch_analysis import AnalysisStatus, PitchAnalysis
from app.models.user import User
from app.services import s3
from app.services.memo_generator import run_memo_generation

router = APIRouter()


async def _get_user_analysis(
    analysis_id: uuid.UUID, user: User, db: AsyncSession
) -> PitchAnalysis:
    """Load analysis and verify ownership."""
    result = await db.execute(
        select(PitchAnalysis).where(
            PitchAnalysis.id == analysis_id,
            PitchAnalysis.user_id == user.id,
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    return analysis


@router.post("/api/analyze/{analysis_id}/memo")
async def generate_memo(
    analysis_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger investment memo generation for a completed analysis."""
    analysis = await _get_user_analysis(analysis_id, user, db)

    status_val = analysis.status.value if hasattr(analysis.status, "value") else analysis.status
    if status_val != "complete":
        raise HTTPException(400, "Analysis must be complete before generating a memo")

    # Check for existing memo
    result = await db.execute(
        select(InvestmentMemo).where(InvestmentMemo.analysis_id == analysis_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing_status = existing.status.value if hasattr(existing.status, "value") else existing.status
        if existing_status in ("pending", "researching", "generating", "formatting"):
            raise HTTPException(409, "Memo generation already in progress")
        if existing_status == "complete":
            raise HTTPException(409, "Memo already exists. Use the regenerate endpoint.")
        # Failed memo — delete and recreate
        await db.delete(existing)
        await db.flush()

    memo = InvestmentMemo(analysis_id=analysis_id)
    db.add(memo)
    await db.commit()
    await db.refresh(memo)

    background_tasks.add_task(run_memo_generation, str(memo.id))

    return {"id": str(memo.id), "status": "pending"}


@router.post("/api/analyze/{analysis_id}/memo/regenerate")
async def regenerate_memo(
    analysis_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate investment memo (deletes existing, creates fresh)."""
    analysis = await _get_user_analysis(analysis_id, user, db)

    status_val = analysis.status.value if hasattr(analysis.status, "value") else analysis.status
    if status_val != "complete":
        raise HTTPException(400, "Analysis must be complete")

    # Delete existing memo and S3 files
    result = await db.execute(
        select(InvestmentMemo).where(InvestmentMemo.analysis_id == analysis_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        # Clean up S3
        keys_to_delete = [k for k in [existing.s3_key_pdf, existing.s3_key_docx] if k]
        if keys_to_delete:
            s3.delete_files(keys_to_delete)
        await db.delete(existing)
        await db.flush()

    memo = InvestmentMemo(analysis_id=analysis_id)
    db.add(memo)
    await db.commit()
    await db.refresh(memo)

    background_tasks.add_task(run_memo_generation, str(memo.id))

    return {"id": str(memo.id), "status": "pending"}


@router.get("/api/analyze/{analysis_id}/memo")
async def get_memo(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get memo status and content."""
    await _get_user_analysis(analysis_id, user, db)

    result = await db.execute(
        select(InvestmentMemo).where(InvestmentMemo.analysis_id == analysis_id)
    )
    memo = result.scalar_one_or_none()
    if not memo:
        raise HTTPException(404, "No memo exists for this analysis")

    status_val = memo.status.value if hasattr(memo.status, "value") else memo.status

    response = {
        "id": str(memo.id),
        "status": status_val,
        "content": memo.content,
        "error": memo.error,
        "created_at": memo.created_at.isoformat() if memo.created_at else None,
        "completed_at": memo.completed_at.isoformat() if memo.completed_at else None,
        "pdf_url": None,
        "docx_url": None,
    }

    if status_val == "complete":
        response["pdf_url"] = f"/api/analyze/{analysis_id}/memo/download/pdf"
        response["docx_url"] = f"/api/analyze/{analysis_id}/memo/download/docx"

    return response


@router.get("/api/analyze/{analysis_id}/memo/download/{fmt}")
async def download_memo(
    analysis_id: uuid.UUID,
    fmt: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download memo as PDF or DOCX."""
    await _get_user_analysis(analysis_id, user, db)

    if fmt not in ("pdf", "docx"):
        raise HTTPException(400, "Format must be 'pdf' or 'docx'")

    result = await db.execute(
        select(InvestmentMemo).where(InvestmentMemo.analysis_id == analysis_id)
    )
    memo = result.scalar_one_or_none()
    if not memo:
        raise HTTPException(404, "No memo exists")

    status_val = memo.status.value if hasattr(memo.status, "value") else memo.status
    if status_val != "complete":
        raise HTTPException(400, "Memo not yet complete")

    s3_key = memo.s3_key_pdf if fmt == "pdf" else memo.s3_key_docx
    if not s3_key:
        raise HTTPException(404, "File not found")

    file_data = s3.download_file(s3_key)

    content_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    return StreamingResponse(
        io.BytesIO(file_data),
        media_type=content_types[fmt],
        headers={"Content-Disposition": f"attachment; filename=investment-memo-{analysis_id}.{fmt}"},
    )
