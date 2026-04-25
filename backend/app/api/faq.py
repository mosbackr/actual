import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.pitch_analysis import AnalysisReport, PitchAnalysis
from app.models.pitch_session import PitchSession
from app.models.user import User
from app.services.faq_generator import generate_investor_faq

router = APIRouter()


# ── Pitch Deck Analysis FAQ ──────────────────────────────────────────


@router.post("/api/analyze/{analysis_id}/faq")
async def generate_analysis_faq(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate investor FAQ for a completed pitch deck analysis."""
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    status_val = analysis.status.value if hasattr(analysis.status, "value") else analysis.status
    if status_val != "complete":
        raise HTTPException(400, "Analysis must be complete before generating FAQ")

    # Build analysis data dict
    analysis_data = {
        "company_name": analysis.company_name,
        "overall_score": analysis.overall_score,
        "fundraising_likelihood": analysis.fundraising_likelihood,
        "recommended_raise": analysis.recommended_raise,
        "estimated_valuation": analysis.estimated_valuation,
        "valuation_justification": analysis.valuation_justification,
        "executive_summary": analysis.executive_summary,
        "exit_likelihood": analysis.exit_likelihood,
        "expected_exit_value": analysis.expected_exit_value,
        "expected_exit_timeline": analysis.expected_exit_timeline,
        "technical_expert_review": analysis.technical_expert_review,
        "reports": [],
    }

    # Load full reports for richer context
    report_result = await db.execute(
        select(AnalysisReport).where(AnalysisReport.analysis_id == analysis_id)
    )
    reports = report_result.scalars().all()
    for r in reports:
        analysis_data["reports"].append({
            "agent_type": r.agent_type.value if hasattr(r.agent_type, "value") else r.agent_type,
            "score": r.score,
            "summary": r.summary,
            "key_findings": r.key_findings,
        })

    faq = await generate_investor_faq(analysis_data, "pitch_analysis")
    analysis.investor_faq = faq
    await db.commit()

    return faq


@router.get("/api/analyze/{analysis_id}/faq")
async def get_analysis_faq(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get stored investor FAQ for an analysis."""
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    if not analysis.investor_faq:
        raise HTTPException(404, "No FAQ generated yet")

    return analysis.investor_faq


# ── Pitch Intelligence FAQ ───────────────────────────────────────────


@router.post("/api/pitch-intelligence/{session_id}/faq")
async def generate_pitch_faq(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate investor FAQ for a completed pitch intelligence session."""
    result = await db.execute(
        select(PitchSession)
        .where(PitchSession.id == session_id, PitchSession.user_id == user.id)
        .options(selectinload(PitchSession.results))
    )
    ps = result.scalar_one_or_none()
    if not ps:
        raise HTTPException(404, "Session not found")

    status_val = ps.status.value if hasattr(ps.status, "value") else ps.status
    if status_val != "complete":
        raise HTTPException(400, "Session must be complete before generating FAQ")

    session_data = {
        "title": ps.title,
        "scores": ps.scores,
        "results": [
            {
                "phase": r.phase.value if hasattr(r.phase, "value") else r.phase,
                "result": r.result,
            }
            for r in (ps.results or [])
        ],
    }

    faq = await generate_investor_faq(session_data, "pitch_intelligence")
    ps.investor_faq = faq
    await db.commit()

    return faq


@router.get("/api/pitch-intelligence/{session_id}/faq")
async def get_pitch_faq(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get stored investor FAQ for a pitch session."""
    result = await db.execute(
        select(PitchSession)
        .where(PitchSession.id == session_id, PitchSession.user_id == user.id)
    )
    ps = result.scalar_one_or_none()
    if not ps:
        raise HTTPException(404, "Session not found")
    if not ps.investor_faq:
        raise HTTPException(404, "No FAQ generated yet")

    return ps.investor_faq
