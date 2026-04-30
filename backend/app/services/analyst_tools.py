"""Tool executor functions for the Analyst Chat agent.

These tools allow the analyst agent to query and interact with
analysis data on behalf of an authenticated user, with access
control enforced at the tool level.
"""

import asyncio
import logging
import threading
import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.investment_memo import InvestmentMemo
from app.models.pitch_analysis import AnalysisStatus, PitchAnalysis
from app.models.pitch_session import PitchAnalysisResult, PitchSession
from app.services.faq_generator import generate_investor_faq

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────


def _check_access(
    obj: Any,
    user_id: uuid.UUID,
    is_admin: bool,
    require_owner: bool = False,
) -> None:
    """Verify the caller has access to *obj*.

    Rules (evaluated in order):
    1. Admins always have access.
    2. The owner (obj.user_id == user_id) always has access.
    3. If *require_owner* is False and the object is published
       (publish_consent=True AND status is 'complete'), allow access.
    4. Otherwise raise ValueError.
    """
    if is_admin:
        return

    if obj.user_id == user_id:
        return

    if not require_owner:
        status_val = _status_str(obj)
        if getattr(obj, "publish_consent", False) and status_val == "complete":
            return

    raise ValueError("Analysis not found or access denied")


def _status_str(obj: Any) -> str:
    """Return the status value as a plain string, handling both enum and str."""
    status = obj.status
    if isinstance(status, Enum):
        return status.value
    return str(status)


def _dt_iso(dt: datetime | None) -> str | None:
    """Return an ISO-formatted string if *dt* is not None, else None."""
    if dt is None:
        return None
    return dt.isoformat()


# ── Tool functions ────────────────────────────────────────────────────


async def tool_list_analyses(
    user_id: uuid.UUID,
    is_admin: bool,
    status: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """List analyses visible to the caller.

    Non-admins see their own analyses plus published (consent + complete) ones.
    Admins see everything.  Optional *status* and *search* filters narrow results.
    """
    from app.db.session import async_session

    async with async_session() as session:
        stmt = select(PitchAnalysis)

        # ── Visibility filter ─────────────────────────────────────
        if not is_admin:
            stmt = stmt.where(
                (PitchAnalysis.user_id == user_id)
                | (
                    (PitchAnalysis.publish_consent == True)  # noqa: E712
                    & (PitchAnalysis.status == AnalysisStatus.complete)
                )
            )

        # ── Optional filters ──────────────────────────────────────
        if status is not None:
            stmt = stmt.where(PitchAnalysis.status == status)

        if search is not None:
            stmt = stmt.where(PitchAnalysis.company_name.ilike(f"%{search}%"))

        stmt = stmt.order_by(PitchAnalysis.created_at.desc()).limit(50)

        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [
        {
            "id": str(row.id),
            "company_name": row.company_name,
            "status": _status_str(row),
            "overall_score": row.overall_score,
            "fundraising_likelihood": row.fundraising_likelihood,
            "created_at": _dt_iso(row.created_at),
            "is_owner": row.user_id == user_id,
        }
        for row in rows
    ]


async def tool_get_analysis_detail(
    user_id: uuid.UUID,
    is_admin: bool,
    analysis_id: str,
) -> dict:
    """Return full details of a single analysis including its reports.

    Raises ``ValueError`` if the analysis is not found or the caller
    lacks access.
    """
    from app.db.session import async_session

    aid = uuid.UUID(analysis_id)

    async with async_session() as session:
        stmt = (
            select(PitchAnalysis)
            .options(selectinload(PitchAnalysis.reports))
            .where(PitchAnalysis.id == aid)
        )
        result = await session.execute(stmt)
        analysis = result.scalars().first()

    if analysis is None:
        raise ValueError("Analysis not found or access denied")

    _check_access(analysis, user_id, is_admin)

    return {
        "id": str(analysis.id),
        "company_name": analysis.company_name,
        "status": _status_str(analysis),
        "overall_score": analysis.overall_score,
        "fundraising_likelihood": analysis.fundraising_likelihood,
        "recommended_raise": analysis.recommended_raise,
        "exit_likelihood": analysis.exit_likelihood,
        "expected_exit_value": analysis.expected_exit_value,
        "expected_exit_timeline": analysis.expected_exit_timeline,
        "executive_summary": analysis.executive_summary,
        "estimated_valuation": analysis.estimated_valuation,
        "valuation_justification": analysis.valuation_justification,
        "technical_expert_review": analysis.technical_expert_review,
        "created_at": _dt_iso(analysis.created_at),
        "completed_at": _dt_iso(analysis.completed_at),
        "is_owner": analysis.user_id == user_id,
        "reports": [
            {
                "agent_type": r.agent_type.value if isinstance(r.agent_type, Enum) else str(r.agent_type),
                "status": r.status.value if isinstance(r.status, Enum) else str(r.status),
                "score": r.score,
                "summary": r.summary,
                "key_findings": r.key_findings,
                "report": r.report,
            }
            for r in analysis.reports
        ],
    }


async def tool_get_memo(
    user_id: uuid.UUID,
    is_admin: bool,
    analysis_id: str,
) -> dict:
    """Return the investment memo for an analysis.

    Returns a dict whose ``status`` field indicates whether the memo
    exists and is complete.  Raises ``ValueError`` if the parent
    analysis is not found or the caller lacks access.
    """
    from app.db.session import async_session

    aid = uuid.UUID(analysis_id)

    async with async_session() as session:
        # Load the analysis first to check access
        stmt = select(PitchAnalysis).where(PitchAnalysis.id == aid)
        result = await session.execute(stmt)
        analysis = result.scalars().first()

        if analysis is None:
            raise ValueError("Analysis not found or access denied")

        _check_access(analysis, user_id, is_admin)

        # Now load the memo
        memo_stmt = select(InvestmentMemo).where(InvestmentMemo.analysis_id == aid)
        memo_result = await session.execute(memo_stmt)
        memo = memo_result.scalars().first()

    if memo is None:
        return {
            "status": "not_found",
            "message": "No memo has been generated for this analysis yet.",
        }

    memo_status = memo.status.value if isinstance(memo.status, Enum) else str(memo.status)

    if memo_status != "complete":
        return {
            "status": memo_status,
            "message": f"Memo is currently {memo_status}.",
        }

    return {
        "status": "complete",
        "content": memo.content,
        "created_at": _dt_iso(memo.created_at),
        "completed_at": _dt_iso(memo.completed_at),
    }


async def tool_get_faq(
    user_id: uuid.UUID,
    is_admin: bool,
    analysis_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Return the investor FAQ for an analysis or pitch session.

    Exactly one of *analysis_id* or *session_id* must be provided.
    Raises ``ValueError`` when neither is given, or when the caller
    lacks access.
    """
    if (analysis_id is None) == (session_id is None):
        raise ValueError("Exactly one of analysis_id or session_id must be provided")

    from app.db.session import async_session

    if analysis_id is not None:
        aid = uuid.UUID(analysis_id)
        async with async_session() as session:
            stmt = select(PitchAnalysis).where(PitchAnalysis.id == aid)
            result = await session.execute(stmt)
            analysis = result.scalars().first()

        if analysis is None:
            raise ValueError("Analysis not found or access denied")

        _check_access(analysis, user_id, is_admin)

        if not analysis.investor_faq:
            return {
                "status": "not_found",
                "message": "No FAQ generated yet for this analysis.",
            }
        return analysis.investor_faq

    # session_id path
    sid = uuid.UUID(session_id)  # type: ignore[arg-type]
    async with async_session() as session:
        stmt = select(PitchSession).where(PitchSession.id == sid)
        result = await session.execute(stmt)
        pitch = result.scalars().first()

    if pitch is None:
        raise ValueError("Pitch session not found or access denied")

    if not is_admin and pitch.user_id != user_id:
        raise ValueError("Pitch session not found or access denied")

    if not pitch.investor_faq:
        return {
            "status": "not_found",
            "message": "No FAQ generated yet for this session.",
        }
    return pitch.investor_faq


async def tool_list_pitch_sessions(
    user_id: uuid.UUID,
    is_admin: bool,
    status: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """List pitch sessions visible to the caller.

    Non-admins see only their own sessions.  Admins see all.
    Optional *status* and *search* filters narrow results.
    """
    from app.db.session import async_session

    async with async_session() as session:
        stmt = select(PitchSession)

        # ── Visibility filter ─────────────────────────────────────
        if not is_admin:
            stmt = stmt.where(PitchSession.user_id == user_id)

        # ── Optional filters ──────────────────────────────────────
        if status is not None:
            stmt = stmt.where(PitchSession.status == status)

        if search is not None:
            stmt = stmt.where(PitchSession.title.ilike(f"%{search}%"))

        stmt = stmt.order_by(PitchSession.created_at.desc()).limit(50)

        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [
        {
            "id": str(row.id),
            "title": row.title,
            "status": _status_str(row),
            "scores": row.scores,
            "created_at": _dt_iso(row.created_at),
        }
        for row in rows
    ]


async def tool_get_pitch_session_detail(
    user_id: uuid.UUID,
    is_admin: bool,
    session_id: str,
) -> dict:
    """Return full details of a single pitch session including phase results.

    Raises ``ValueError`` if the session is not found or the caller
    lacks access.
    """
    from app.db.session import async_session

    sid = uuid.UUID(session_id)

    async with async_session() as session:
        stmt = (
            select(PitchSession)
            .options(selectinload(PitchSession.results))
            .where(PitchSession.id == sid)
        )
        result = await session.execute(stmt)
        pitch = result.scalars().first()

    if pitch is None:
        raise ValueError("Pitch session not found or access denied")

    if not is_admin and pitch.user_id != user_id:
        raise ValueError("Pitch session not found or access denied")

    return {
        "id": str(pitch.id),
        "title": pitch.title,
        "status": _status_str(pitch),
        "scores": pitch.scores,
        "benchmark_percentiles": pitch.benchmark_percentiles,
        "investor_faq": pitch.investor_faq,
        "created_at": _dt_iso(pitch.created_at),
        "results": [
            {
                "phase": r.phase.value if isinstance(r.phase, Enum) else str(r.phase),
                "status": r.status.value if isinstance(r.status, Enum) else str(r.status),
                "result": r.result,
            }
            for r in pitch.results
        ],
    }


# ── Action tools ─────────────────────────────────────────────────────


def _start_memo_background(memo_id: str) -> None:
    """Launch memo generation in a daemon thread.

    Imports ``run_memo_generation`` inside the thread function to avoid
    circular imports at module level.
    """

    def _run():
        from app.services.memo_generator import run_memo_generation

        asyncio.run(run_memo_generation(memo_id))

    t = threading.Thread(target=_run, daemon=True)
    t.start()


async def tool_regenerate_memo(
    user_id: uuid.UUID,
    is_admin: bool,
    analysis_id: str,
) -> dict:
    """Regenerate the investment memo for a completed analysis.

    Only the owner or an admin may trigger regeneration.  If a memo
    already exists it is reset to ``pending``; otherwise a new one is
    created.  Background generation is kicked off via a daemon thread.

    Raises ``ValueError`` if the analysis is not found, access is
    denied, or the analysis is not yet complete.
    """
    from app.db.session import async_session

    aid = uuid.UUID(analysis_id)

    async with async_session() as session:
        # Load the analysis
        stmt = select(PitchAnalysis).where(PitchAnalysis.id == aid)
        result = await session.execute(stmt)
        analysis = result.scalars().first()

        if analysis is None:
            raise ValueError("Analysis not found or access denied")

        _check_access(analysis, user_id, is_admin, require_owner=True)

        status_val = _status_str(analysis)
        if status_val != "complete":
            raise ValueError("Analysis must be complete before generating a memo")

        company_name = analysis.company_name

        # Check for existing memo
        memo_stmt = select(InvestmentMemo).where(InvestmentMemo.analysis_id == aid)
        memo_result = await session.execute(memo_stmt)
        memo = memo_result.scalars().first()

        if memo is not None:
            # Reset existing memo
            memo.status = "pending"
            memo.content = None
            memo.s3_key_pdf = None
            memo.s3_key_docx = None
            memo.error = None
            memo.completed_at = None
        else:
            # Create new memo
            memo = InvestmentMemo(analysis_id=aid, status="pending")
            session.add(memo)

        await session.commit()
        memo_id = str(memo.id)

    _start_memo_background(memo_id)

    return {
        "status": "started",
        "memo_id": memo_id,
        "message": f"Memo regeneration started for '{company_name}'. This takes 1-2 minutes.",
    }


async def tool_regenerate_faq(
    user_id: uuid.UUID,
    is_admin: bool,
    analysis_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Regenerate the investor FAQ for an analysis or pitch session.

    Exactly one of *analysis_id* or *session_id* must be provided.
    Only the owner or an admin may trigger regeneration.

    Raises ``ValueError`` when neither/both IDs are given, when the
    caller lacks access, or when the analysis/session is not complete.
    """
    if (analysis_id is None) == (session_id is None):
        raise ValueError("Exactly one of analysis_id or session_id must be provided")

    from app.db.session import async_session

    if analysis_id is not None:
        aid = uuid.UUID(analysis_id)

        async with async_session() as session:
            stmt = (
                select(PitchAnalysis)
                .options(selectinload(PitchAnalysis.reports))
                .where(PitchAnalysis.id == aid)
            )
            result = await session.execute(stmt)
            analysis = result.scalars().first()

            if analysis is None:
                raise ValueError("Analysis not found or access denied")

            _check_access(analysis, user_id, is_admin, require_owner=True)

            status_val = _status_str(analysis)
            if status_val != "complete":
                raise ValueError("Analysis must be complete before generating FAQ")

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
                "reports": [
                    {
                        "agent_type": r.agent_type.value if hasattr(r.agent_type, "value") else r.agent_type,
                        "score": r.score,
                        "summary": r.summary,
                        "key_findings": r.key_findings,
                    }
                    for r in analysis.reports
                ],
            }

            faq = await generate_investor_faq(analysis_data, "pitch_analysis")
            analysis.investor_faq = faq
            await session.commit()

        return faq

    # session_id path
    sid = uuid.UUID(session_id)  # type: ignore[arg-type]

    async with async_session() as session:
        stmt = (
            select(PitchSession)
            .options(selectinload(PitchSession.results))
            .where(PitchSession.id == sid)
        )
        result = await session.execute(stmt)
        pitch = result.scalars().first()

        if pitch is None:
            raise ValueError("Pitch session not found or access denied")

        if not is_admin and pitch.user_id != user_id:
            raise ValueError("Pitch session not found or access denied")

        status_val = _status_str(pitch)
        if status_val != "complete":
            raise ValueError("Session must be complete before generating FAQ")

        session_data = {
            "title": pitch.title,
            "scores": pitch.scores,
            "results": [
                {"phase": r.phase.value if hasattr(r.phase, "value") else r.phase, "result": r.result}
                for r in (pitch.results or [])
            ],
        }

        faq = await generate_investor_faq(session_data, "pitch_intelligence")
        pitch.investor_faq = faq
        await session.commit()

    return faq
