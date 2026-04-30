import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.startup import Startup, startup_industries
from app.models.industry import Industry
from app.models.user import User
from app.models.watchlist import UserWatchlist

router = APIRouter()


@router.get("/api/watchlist")
async def list_watchlist(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * per_page

    count_result = await db.execute(
        select(func.count()).select_from(UserWatchlist).where(UserWatchlist.user_id == user.id)
    )
    total = count_result.scalar() or 0
    pages = (total + per_page - 1) // per_page if total > 0 else 0

    result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == user.id)
        .order_by(UserWatchlist.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    entries = result.scalars().all()

    startup_ids = [e.startup_id for e in entries]
    if startup_ids:
        startup_result = await db.execute(
            select(Startup)
            .where(Startup.id.in_(startup_ids))
            .options(selectinload(Startup.industries))
        )
        startups_by_id = {s.id: s for s in startup_result.scalars().all()}
    else:
        startups_by_id = {}

    items = []
    for entry in entries:
        s = startups_by_id.get(entry.startup_id)
        if not s:
            continue
        items.append({
            "startup_id": str(s.id),
            "watched_at": entry.created_at.isoformat() if entry.created_at else None,
            "startup": {
                "id": str(s.id),
                "name": s.name,
                "slug": s.slug,
                "tagline": s.tagline,
                "description": s.description[:300] if s.description else None,
                "stage": s.stage.value if hasattr(s.stage, "value") else s.stage,
                "ai_score": s.ai_score,
                "logo_url": s.logo_url,
                "industries": [{"id": str(ind.id), "name": ind.name, "slug": ind.slug} for ind in (s.industries or [])],
                "form_sources": s.form_sources or [],
            },
        })

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "items": items,
    }


@router.get("/api/watchlist/ids")
async def get_watchlist_ids(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserWatchlist.startup_id).where(UserWatchlist.user_id == user.id)
    )
    ids = [str(row[0]) for row in result.all()]
    return {"ids": ids}


@router.post("/api/watchlist")
async def add_to_watchlist(
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    startup_id_str = body.get("startup_id")
    if not startup_id_str:
        raise HTTPException(400, "startup_id is required")

    try:
        startup_id = uuid.UUID(startup_id_str)
    except ValueError:
        raise HTTPException(400, "Invalid startup_id")

    # Check startup exists
    startup = await db.get(Startup, startup_id)
    if not startup:
        raise HTTPException(404, "Startup not found")

    # Check not already watching
    existing = await db.execute(
        select(UserWatchlist).where(
            UserWatchlist.user_id == user.id,
            UserWatchlist.startup_id == startup_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Already watching this startup")

    entry = UserWatchlist(user_id=user.id, startup_id=startup_id)
    db.add(entry)
    await db.commit()
    return {"success": True}


@router.delete("/api/watchlist/{startup_id}")
async def remove_from_watchlist(
    startup_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserWatchlist).where(
            UserWatchlist.user_id == user.id,
            UserWatchlist.startup_id == startup_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Not in watchlist")

    await db.delete(entry)
    await db.commit()
    return {"success": True}
