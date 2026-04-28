import json
import secrets
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.dataroom import DataroomDocument, DataroomRequest, DataroomSectionReview, DataroomStatus
from app.models.notification import Notification, NotificationType
from app.models.user import SubscriptionStatus, SubscriptionTier, User
from app.services import email_service

router = APIRouter(tags=["datarooms"])

ALLOWED_FILE_TYPES = {
    "pdf", "docx", "doc", "pptx", "ppt", "xlsx", "xls", "csv",
    "png", "jpg", "jpeg", "gif", "webp", "md", "txt",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
VALID_SECTIONS = {"corporate", "financials", "fundraising", "product", "legal", "team"}

TIER_LIMITS = {
    SubscriptionTier.starter: 3,
    SubscriptionTier.professional: 10,
    SubscriptionTier.unlimited: None,
}


def _get_file_type(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


# ── Investor Endpoints ──────────────────────────────────────────────────


@router.post("/api/datarooms")
async def create_dataroom_request(
    founder_email: str = Form(...),
    founder_name: str | None = Form(None),
    company_name: str | None = Form(None),
    personal_message: str | None = Form(None),
    custom_criteria: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a dataroom request and email the founder."""
    if user.subscription_status != SubscriptionStatus.active:
        raise HTTPException(403, "Active subscription required")

    limit = TIER_LIMITS.get(user.subscription_tier)
    if limit is not None:
        active_count = await db.scalar(
            select(func.count(DataroomRequest.id)).where(
                DataroomRequest.investor_id == user.id,
                DataroomRequest.status.notin_([DataroomStatus.complete, DataroomStatus.expired]),
            )
        )
        if active_count >= limit:
            raise HTTPException(
                403,
                f"You have reached your limit of {limit} active dataroom requests. "
                f"Upgrade your plan or wait for existing requests to complete.",
            )

    criteria = None
    if custom_criteria:
        try:
            criteria = json.loads(custom_criteria)
        except json.JSONDecodeError:
            raise HTTPException(400, "Invalid custom_criteria JSON")

    share_token = secrets.token_urlsafe(32)

    request = DataroomRequest(
        investor_id=user.id,
        founder_email=founder_email,
        founder_name=founder_name,
        company_name=company_name,
        personal_message=personal_message,
        share_token=share_token,
        status=DataroomStatus.pending,
        custom_criteria=criteria,
    )
    db.add(request)
    await db.commit()
    await db.refresh(request)

    email_service.send_dataroom_request(
        founder_email=founder_email,
        founder_name=founder_name,
        investor_name=user.name,
        company_name=company_name,
        personal_message=personal_message,
        share_token=share_token,
    )

    return {
        "id": str(request.id),
        "share_token": share_token,
        "status": request.status.value,
    }


@router.get("/api/datarooms")
async def list_dataroom_requests(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all dataroom requests for the current investor."""
    result = await db.execute(
        select(DataroomRequest)
        .where(DataroomRequest.investor_id == user.id)
        .order_by(DataroomRequest.created_at.desc())
    )
    requests = result.scalars().all()

    items = []
    for r in requests:
        doc_count = await db.scalar(
            select(func.count(DataroomDocument.id)).where(
                DataroomDocument.dataroom_request_id == r.id
            )
        )
        items.append({
            "id": str(r.id),
            "founder_email": r.founder_email,
            "founder_name": r.founder_name,
            "company_name": r.company_name,
            "status": r.status.value,
            "document_count": doc_count,
            "analysis_id": str(r.analysis_id) if r.analysis_id else None,
            "created_at": r.created_at.isoformat(),
        })

    return {"items": items}


@router.get("/api/datarooms/{dataroom_id}")
async def get_dataroom_request(
    dataroom_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single dataroom request with documents and section reviews."""
    request = await db.get(DataroomRequest, uuid.UUID(dataroom_id))
    if not request or request.investor_id != user.id:
        raise HTTPException(404, "Dataroom request not found")

    doc_result = await db.execute(
        select(DataroomDocument)
        .where(DataroomDocument.dataroom_request_id == request.id)
        .order_by(DataroomDocument.section, DataroomDocument.created_at)
    )
    documents = doc_result.scalars().all()

    review_result = await db.execute(
        select(DataroomSectionReview)
        .where(DataroomSectionReview.dataroom_request_id == request.id)
        .order_by(DataroomSectionReview.section)
    )
    reviews = review_result.scalars().all()

    return {
        "id": str(request.id),
        "investor_id": str(request.investor_id),
        "founder_id": str(request.founder_id) if request.founder_id else None,
        "founder_email": request.founder_email,
        "founder_name": request.founder_name,
        "company_name": request.company_name,
        "personal_message": request.personal_message,
        "status": request.status.value,
        "analysis_id": str(request.analysis_id) if request.analysis_id else None,
        "custom_criteria": request.custom_criteria,
        "created_at": request.created_at.isoformat(),
        "documents": [
            {
                "id": str(d.id),
                "section": d.section,
                "original_filename": d.original_filename,
                "file_type": d.file_type,
                "file_size_bytes": d.file_size_bytes,
                "created_at": d.created_at.isoformat(),
            }
            for d in documents
        ],
        "section_reviews": [
            {
                "id": str(rv.id),
                "section": rv.section,
                "criteria_description": rv.criteria_description,
                "score": rv.score,
                "summary": rv.summary,
                "findings": rv.findings,
                "status": rv.status,
            }
            for rv in reviews
        ],
    }


@router.delete("/api/datarooms/{dataroom_id}")
async def delete_dataroom_request(
    dataroom_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete/cancel a dataroom request and its S3 files."""
    from app.services import s3

    request = await db.get(DataroomRequest, uuid.UUID(dataroom_id))
    if not request or request.investor_id != user.id:
        raise HTTPException(404, "Dataroom request not found")

    if request.status == DataroomStatus.analyzing:
        raise HTTPException(400, "Cannot delete a dataroom that is currently being analyzed")

    doc_result = await db.execute(
        select(DataroomDocument.s3_key).where(
            DataroomDocument.dataroom_request_id == request.id
        )
    )
    s3_keys = [row[0] for row in doc_result.all()]
    if s3_keys:
        s3.delete_files(s3_keys)

    await db.delete(request)
    await db.commit()

    return {"deleted": True}


# ── Founder Endpoints ───────────────────────────────────────────────────


@router.get("/api/datarooms/request/{share_token}")
async def get_dataroom_by_token(
    share_token: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Founder: get dataroom request info by share token."""
    result = await db.execute(
        select(DataroomRequest).where(DataroomRequest.share_token == share_token)
    )
    request = result.scalar_one_or_none()
    if not request:
        raise HTTPException(404, "Dataroom request not found")

    if request.status == DataroomStatus.expired:
        raise HTTPException(410, "This dataroom link has expired")

    if request.status in (DataroomStatus.submitted, DataroomStatus.analyzing, DataroomStatus.complete):
        raise HTTPException(400, "This dataroom has already been submitted")

    if request.founder_id is None:
        request.founder_id = user.id
        await db.commit()
    elif request.founder_id != user.id:
        raise HTTPException(403, "This dataroom request belongs to another user")

    doc_result = await db.execute(
        select(DataroomDocument)
        .where(DataroomDocument.dataroom_request_id == request.id)
        .order_by(DataroomDocument.section, DataroomDocument.created_at)
    )
    documents = doc_result.scalars().all()

    investor = await db.get(User, request.investor_id)

    return {
        "id": str(request.id),
        "investor_name": investor.name if investor else "An investor",
        "company_name": request.company_name,
        "personal_message": request.personal_message,
        "status": request.status.value,
        "documents": [
            {
                "id": str(d.id),
                "section": d.section,
                "original_filename": d.original_filename,
                "file_type": d.file_type,
                "file_size_bytes": d.file_size_bytes,
            }
            for d in documents
        ],
    }


@router.post("/api/datarooms/request/{share_token}/upload")
async def upload_dataroom_file(
    share_token: str,
    section: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Founder: upload a file to a dataroom section."""
    from app.services import s3

    result = await db.execute(
        select(DataroomRequest).where(DataroomRequest.share_token == share_token)
    )
    request = result.scalar_one_or_none()
    if not request:
        raise HTTPException(404, "Dataroom request not found")

    if request.founder_id != user.id:
        raise HTTPException(403, "Not authorized")

    if request.status in (DataroomStatus.submitted, DataroomStatus.analyzing, DataroomStatus.complete):
        raise HTTPException(400, "This dataroom has already been submitted")

    if section not in VALID_SECTIONS:
        raise HTTPException(400, f"Invalid section. Must be one of: {', '.join(sorted(VALID_SECTIONS))}")

    file_type = _get_file_type(file.filename or "")
    if file_type not in ALLOWED_FILE_TYPES:
        raise HTTPException(400, f"File type '{file_type}' not allowed")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(400, "File exceeds 50MB limit")

    s3_key = f"datarooms/{request.id}/{section}/{uuid.uuid4()}/{file.filename}"
    s3.upload_file(data, s3_key)

    doc = DataroomDocument(
        dataroom_request_id=request.id,
        section=section,
        original_filename=file.filename or "unnamed",
        s3_key=s3_key,
        file_type=file_type,
        file_size_bytes=len(data),
    )
    db.add(doc)

    if request.status == DataroomStatus.pending:
        request.status = DataroomStatus.uploading

    await db.commit()
    await db.refresh(doc)

    return {
        "id": str(doc.id),
        "section": doc.section,
        "original_filename": doc.original_filename,
        "file_type": doc.file_type,
        "file_size_bytes": doc.file_size_bytes,
    }


@router.get("/api/datarooms/request/{share_token}/documents")
async def list_dataroom_documents(
    share_token: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Founder: list uploaded documents by section."""
    result = await db.execute(
        select(DataroomRequest).where(DataroomRequest.share_token == share_token)
    )
    request = result.scalar_one_or_none()
    if not request:
        raise HTTPException(404, "Dataroom request not found")

    if request.founder_id and request.founder_id != user.id:
        raise HTTPException(403, "Not authorized")

    doc_result = await db.execute(
        select(DataroomDocument)
        .where(DataroomDocument.dataroom_request_id == request.id)
        .order_by(DataroomDocument.section, DataroomDocument.created_at)
    )
    documents = doc_result.scalars().all()

    return {
        "documents": [
            {
                "id": str(d.id),
                "section": d.section,
                "original_filename": d.original_filename,
                "file_type": d.file_type,
                "file_size_bytes": d.file_size_bytes,
            }
            for d in documents
        ]
    }


@router.delete("/api/datarooms/request/{share_token}/documents/{doc_id}")
async def delete_dataroom_document(
    share_token: str,
    doc_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Founder: remove an uploaded file."""
    from app.services import s3

    result = await db.execute(
        select(DataroomRequest).where(DataroomRequest.share_token == share_token)
    )
    request = result.scalar_one_or_none()
    if not request:
        raise HTTPException(404, "Dataroom request not found")

    if request.founder_id != user.id:
        raise HTTPException(403, "Not authorized")

    if request.status in (DataroomStatus.submitted, DataroomStatus.analyzing, DataroomStatus.complete):
        raise HTTPException(400, "Cannot modify a submitted dataroom")

    doc = await db.get(DataroomDocument, uuid.UUID(doc_id))
    if not doc or doc.dataroom_request_id != request.id:
        raise HTTPException(404, "Document not found")

    s3.delete_file(doc.s3_key)
    await db.delete(doc)
    await db.commit()

    return {"deleted": True}


@router.post("/api/datarooms/request/{share_token}/submit")
async def submit_dataroom(
    share_token: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Founder: submit the dataroom, triggering analysis."""
    import asyncio
    from app.services.dataroom_analysis import run_dataroom_analysis

    result = await db.execute(
        select(DataroomRequest).where(DataroomRequest.share_token == share_token)
    )
    request = result.scalar_one_or_none()
    if not request:
        raise HTTPException(404, "Dataroom request not found")

    if request.founder_id != user.id:
        raise HTTPException(403, "Not authorized")

    if request.status in (DataroomStatus.submitted, DataroomStatus.analyzing, DataroomStatus.complete):
        raise HTTPException(400, "This dataroom has already been submitted")

    doc_count = await db.scalar(
        select(func.count(DataroomDocument.id)).where(
            DataroomDocument.dataroom_request_id == request.id
        )
    )
    if doc_count == 0:
        raise HTTPException(400, "Upload at least one document before submitting")

    request.status = DataroomStatus.submitted
    await db.commit()

    investor = await db.get(User, request.investor_id)

    notification = Notification(
        user_id=request.investor_id,
        type=NotificationType.dataroom_submitted,
        title="Dataroom received",
        message=f"{user.name} has submitted their dataroom{' for ' + request.company_name if request.company_name else ''}",
        link=f"/datarooms/{request.id}",
    )
    db.add(notification)
    await db.commit()

    if investor:
        email_service.send_dataroom_submitted(
            investor_email=investor.email,
            investor_name=investor.name,
            founder_name=user.name,
            company_name=request.company_name,
            dataroom_id=str(request.id),
        )

    asyncio.create_task(run_dataroom_analysis(str(request.id)))

    return {
        "submitted": True,
        "investor_name": investor.name if investor else "the investor",
    }
