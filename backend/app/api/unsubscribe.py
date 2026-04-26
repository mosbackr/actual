import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.db.session import get_db
from app.models.investor import Investor
from app.services.email_verification import verify_unsubscribe_token

router = APIRouter()


@router.post("/api/unsubscribe/{investor_id}")
async def unsubscribe_investor(
    investor_id: uuid.UUID,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if not verify_unsubscribe_token(str(investor_id), token):
        raise HTTPException(status_code=400, detail="Invalid unsubscribe token")

    investor = await db.get(Investor, investor_id)
    if not investor:
        raise HTTPException(status_code=404, detail="Investor not found")

    investor.email_unsubscribed = True
    investor.email_unsubscribed_at = datetime.now(timezone.utc)
    await db.commit()

    return {"ok": True, "message": "Successfully unsubscribed"}
