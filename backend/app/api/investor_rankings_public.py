import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.investor import Investor
from app.models.investor_ranking import InvestorRanking
from app.models.user import User

router = APIRouter()


def _ranking_response(ranking: InvestorRanking, investor: Investor) -> dict:
    return {
        "investor_id": str(investor.id),
        "firm_name": investor.firm_name,
        "partner_name": investor.partner_name,
        "overall_score": ranking.overall_score,
        "portfolio_performance": ranking.portfolio_performance,
        "deal_activity": ranking.deal_activity,
        "exit_track_record": ranking.exit_track_record,
        "stage_expertise": ranking.stage_expertise,
        "sector_expertise": ranking.sector_expertise,
        "follow_on_rate": ranking.follow_on_rate,
        "network_quality": ranking.network_quality,
        "dimension_scores": {
            "portfolio_performance": ranking.portfolio_performance,
            "deal_activity": ranking.deal_activity,
            "exit_track_record": ranking.exit_track_record,
            "stage_expertise": ranking.stage_expertise,
            "sector_expertise": ranking.sector_expertise,
            "follow_on_rate": ranking.follow_on_rate,
            "network_quality": ranking.network_quality,
        },
        "narrative": ranking.narrative,
        "scored_at": ranking.scored_at.isoformat(),
    }


# IMPORTANT: /me/ranking must be defined BEFORE /{investor_id}/ranking
# otherwise FastAPI will try to parse "me" as a UUID and fail.
@router.get("/api/investors/me/ranking")
async def get_my_ranking(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InvestorRanking, Investor)
        .join(Investor, InvestorRanking.investor_id == Investor.id)
        .where(func.lower(Investor.email) == user.email.lower())
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="No ranking found for your account")

    ranking, investor = row
    return _ranking_response(ranking, investor)


@router.get("/api/investors/{investor_id}/ranking")
async def get_investor_ranking(
    investor_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InvestorRanking, Investor)
        .join(Investor, InvestorRanking.investor_id == Investor.id)
        .where(InvestorRanking.investor_id == investor_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="No ranking found for this investor")

    ranking, investor = row

    # Allow superadmin or matching email
    is_superadmin = user.role.value == "superadmin"
    email_matches = (
        investor.email
        and user.email.lower() == investor.email.lower()
    )
    if not is_superadmin and not email_matches:
        raise HTTPException(status_code=403, detail="You do not have access to this ranking")

    return _ranking_response(ranking, investor)
