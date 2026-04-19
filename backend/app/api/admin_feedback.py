import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.feedback import FeedbackSession
from app.models.user import User

router = APIRouter()


def _feedback_to_dict(fs: FeedbackSession, user: User | None = None) -> dict:
    d = {
        "id": str(fs.id),
        "user_id": str(fs.user_id),
        "status": fs.status,
        "category": fs.category,
        "severity": fs.severity,
        "area": fs.area,
        "summary": fs.summary,
        "recommendations": fs.recommendations,
        "transcript": fs.transcript,
        "page_url": fs.page_url,
        "created_at": fs.created_at.isoformat() if fs.created_at else None,
        "updated_at": fs.updated_at.isoformat() if fs.updated_at else None,
    }
    if user:
        d["user_name"] = user.name
        d["user_email"] = user.email
    return d


@router.get("/api/admin/feedback")
async def list_feedback(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    area: str | None = None,
):
    query = select(FeedbackSession, User).join(User, FeedbackSession.user_id == User.id)

    if status:
        query = query.where(FeedbackSession.status == status)
    if category:
        query = query.where(FeedbackSession.category == category)
    if severity:
        query = query.where(FeedbackSession.severity == severity)
    if area:
        query = query.where(FeedbackSession.area == area)

    # Count
    count_query = select(func.count()).select_from(FeedbackSession)
    if status:
        count_query = count_query.where(FeedbackSession.status == status)
    if category:
        count_query = count_query.where(FeedbackSession.category == category)
    if severity:
        count_query = count_query.where(FeedbackSession.severity == severity)
    if area:
        count_query = count_query.where(FeedbackSession.area == area)
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.order_by(FeedbackSession.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    rows = result.all()

    items = [_feedback_to_dict(fs, user) for fs, user in rows]

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "items": items,
    }


@router.get("/api/admin/feedback/{feedback_id}")
async def get_feedback(
    feedback_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FeedbackSession, User)
        .join(User, FeedbackSession.user_id == User.id)
        .where(FeedbackSession.id == feedback_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Feedback not found")

    fs, user = row
    return _feedback_to_dict(fs, user)
