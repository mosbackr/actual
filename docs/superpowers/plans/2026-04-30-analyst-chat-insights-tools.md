# Analyst Chat Insights Tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 8 new tools to the Analyst Chat agent so it can query and act on the user's pitch analysis data, investment memos, investor FAQs, and pitch intelligence sessions.

**Architecture:** New `analyst_tools.py` file contains all tool executor functions (user-scoped DB queries). `analyst_agent.py` gets new tool definitions in TOOLS list, updated system prompt, and user context threading. `analyst.py` API layer passes user identity to the agent.

**Tech Stack:** Python, SQLAlchemy async, Claude Sonnet 4.6 tool use, existing `memo_generator` and `faq_generator` services.

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `backend/app/services/analyst_tools.py` | All 8 tool executor functions + access control helper | Create |
| `backend/app/services/analyst_agent.py` | Tool definitions, system prompt, agent loop | Modify |
| `backend/app/api/analyst.py` | Pass user_id/is_admin to run_agent | Modify |
| `backend/tests/test_analyst_tools.py` | Unit tests for tool executors | Create |

---

### Task 1: Create analyst_tools.py with access control helper and list_analyses

**Files:**
- Create: `backend/app/services/analyst_tools.py`
- Create: `backend/tests/test_analyst_tools.py`

- [ ] **Step 1: Write tests for _check_access and tool_list_analyses**

Create `backend/tests/test_analyst_tools.py`:

```python
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pitch_analysis import AnalysisStatus, PitchAnalysis
from app.models.user import AuthProvider, User, UserRole
from tests.conftest import *  # noqa — picks up fixtures


@pytest_asyncio.fixture
async def other_user(db: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="other@example.com",
        name="Other User",
        auth_provider=AuthProvider.google,
        provider_id="google-other",
        role=UserRole.user,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def sample_analysis(db: AsyncSession, test_user: User) -> PitchAnalysis:
    analysis = PitchAnalysis(
        id=uuid.uuid4(),
        user_id=test_user.id,
        company_name="Acme Corp",
        status=AnalysisStatus.complete,
        overall_score=75.0,
        fundraising_likelihood=60.0,
        executive_summary="Acme is a strong company.",
        created_at=datetime.now(timezone.utc),
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    return analysis


@pytest_asyncio.fixture
async def published_analysis(db: AsyncSession, other_user: User) -> PitchAnalysis:
    analysis = PitchAnalysis(
        id=uuid.uuid4(),
        user_id=other_user.id,
        company_name="PublicCo",
        status=AnalysisStatus.complete,
        overall_score=85.0,
        publish_consent=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    return analysis


@pytest_asyncio.fixture
async def private_analysis(db: AsyncSession, other_user: User) -> PitchAnalysis:
    analysis = PitchAnalysis(
        id=uuid.uuid4(),
        user_id=other_user.id,
        company_name="PrivateCo",
        status=AnalysisStatus.complete,
        overall_score=90.0,
        publish_consent=False,
        created_at=datetime.now(timezone.utc),
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    return analysis


# ── _check_access tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_access_owner(sample_analysis, test_user):
    from app.services.analyst_tools import _check_access
    # Should not raise — user owns this analysis
    _check_access(sample_analysis, test_user.id, is_admin=False)


@pytest.mark.asyncio
async def test_check_access_admin(private_analysis, admin_user):
    from app.services.analyst_tools import _check_access
    # Admin can access anything
    _check_access(private_analysis, admin_user.id, is_admin=True)


@pytest.mark.asyncio
async def test_check_access_published(published_analysis, test_user):
    from app.services.analyst_tools import _check_access
    # Non-owner can access published + complete analysis
    _check_access(published_analysis, test_user.id, is_admin=False)


@pytest.mark.asyncio
async def test_check_access_denied(private_analysis, test_user):
    from app.services.analyst_tools import _check_access
    with pytest.raises(ValueError, match="not found or access denied"):
        _check_access(private_analysis, test_user.id, is_admin=False)


@pytest.mark.asyncio
async def test_check_access_require_owner(published_analysis, test_user):
    from app.services.analyst_tools import _check_access
    # Even published analysis is denied when require_owner=True
    with pytest.raises(ValueError, match="not found or access denied"):
        _check_access(published_analysis, test_user.id, is_admin=False, require_owner=True)


# ── tool_list_analyses tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_analyses_own(
    db, test_user, sample_analysis, published_analysis, private_analysis
):
    from app.services.analyst_tools import tool_list_analyses
    results = await tool_list_analyses(test_user.id, is_admin=False)
    names = [r["company_name"] for r in results]
    assert "Acme Corp" in names       # own
    assert "PublicCo" in names         # published
    assert "PrivateCo" not in names    # private, not owned


@pytest.mark.asyncio
async def test_list_analyses_admin(
    db, admin_user, sample_analysis, published_analysis, private_analysis
):
    from app.services.analyst_tools import tool_list_analyses
    results = await tool_list_analyses(admin_user.id, is_admin=True)
    names = [r["company_name"] for r in results]
    assert "Acme Corp" in names
    assert "PublicCo" in names
    assert "PrivateCo" in names  # admin sees everything


@pytest.mark.asyncio
async def test_list_analyses_search(db, test_user, sample_analysis):
    from app.services.analyst_tools import tool_list_analyses
    results = await tool_list_analyses(test_user.id, is_admin=False, search="acme")
    assert len(results) == 1
    assert results[0]["company_name"] == "Acme Corp"


@pytest.mark.asyncio
async def test_list_analyses_status_filter(db, test_user, sample_analysis):
    from app.services.analyst_tools import tool_list_analyses
    results = await tool_list_analyses(test_user.id, is_admin=False, status="pending")
    assert len(results) == 0  # sample_analysis is "complete"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/leemosbacker/acutal/backend && python -m pytest tests/test_analyst_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.analyst_tools'`

- [ ] **Step 3: Create analyst_tools.py with _check_access and tool_list_analyses**

Create `backend/app/services/analyst_tools.py`:

```python
"""Tool executors for the Analyst Chat agent.

Each function queries the database with user-scoped access control
and returns JSON-serializable dicts for Claude tool results.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.db.session import async_session
from app.models.investment_memo import InvestmentMemo
from app.models.pitch_analysis import AnalysisReport, PitchAnalysis
from app.models.pitch_session import PitchAnalysisResult, PitchSession

logger = logging.getLogger(__name__)


def _check_access(
    obj, user_id: uuid.UUID, is_admin: bool, require_owner: bool = False
) -> None:
    """Raise ValueError if user cannot access this object."""
    if is_admin:
        return
    if obj.user_id == user_id:
        return
    if (
        not require_owner
        and hasattr(obj, "publish_consent")
        and obj.publish_consent
        and _status_str(obj) == "complete"
    ):
        return
    raise ValueError("Analysis not found or access denied")


def _status_str(obj) -> str:
    """Get status as a plain string regardless of enum vs string storage."""
    s = obj.status
    return s.value if hasattr(s, "value") else s


def _dt_iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# ── Query Tools ──────────────────────────────────────────────────────


async def tool_list_analyses(
    user_id: uuid.UUID,
    is_admin: bool,
    status: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """List pitch analyses the user can access."""
    async with async_session() as db:
        query = select(PitchAnalysis)

        if not is_admin:
            query = query.where(
                or_(
                    PitchAnalysis.user_id == user_id,
                    (PitchAnalysis.publish_consent == True) & (PitchAnalysis.status == "complete"),
                )
            )

        if status:
            query = query.where(PitchAnalysis.status == status)
        if search:
            query = query.where(PitchAnalysis.company_name.ilike(f"%{search}%"))

        query = query.order_by(PitchAnalysis.created_at.desc()).limit(50)
        result = await db.execute(query)
        analyses = result.scalars().all()

    return [
        {
            "id": str(a.id),
            "company_name": a.company_name,
            "status": _status_str(a),
            "overall_score": a.overall_score,
            "fundraising_likelihood": a.fundraising_likelihood,
            "created_at": _dt_iso(a.created_at),
            "is_owner": a.user_id == user_id,
        }
        for a in analyses
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/leemosbacker/acutal/backend && python -m pytest tests/test_analyst_tools.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/leemosbacker/acutal/backend
git add app/services/analyst_tools.py tests/test_analyst_tools.py
git commit -m "feat: add analyst_tools.py with access control and list_analyses tool"
```

---

### Task 2: Add get_analysis_detail and get_memo tools

**Files:**
- Modify: `backend/app/services/analyst_tools.py`
- Modify: `backend/tests/test_analyst_tools.py`

- [ ] **Step 1: Write tests for tool_get_analysis_detail and tool_get_memo**

Append to `backend/tests/test_analyst_tools.py`:

```python
from app.models.pitch_analysis import AgentType, AnalysisReport, ReportStatus
from app.models.investment_memo import InvestmentMemo


@pytest_asyncio.fixture
async def analysis_with_reports(db: AsyncSession, sample_analysis: PitchAnalysis) -> PitchAnalysis:
    for agent in [AgentType.problem_solution, AgentType.market_tam, AgentType.traction]:
        report = AnalysisReport(
            analysis_id=sample_analysis.id,
            agent_type=agent,
            status=ReportStatus.complete,
            score=70.0 + hash(agent.value) % 20,
            summary=f"Summary for {agent.value}",
            report=f"Full report for {agent.value}",
            key_findings=[f"Finding 1 for {agent.value}"],
        )
        db.add(report)
    await db.commit()
    return sample_analysis


@pytest_asyncio.fixture
async def analysis_with_memo(db: AsyncSession, sample_analysis: PitchAnalysis) -> InvestmentMemo:
    memo = InvestmentMemo(
        analysis_id=sample_analysis.id,
        status="complete",
        content="# Investment Memo\n\nThis is the memo content.",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(memo)
    await db.commit()
    await db.refresh(memo)
    return memo


# ── tool_get_analysis_detail tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_get_analysis_detail(db, test_user, analysis_with_reports):
    from app.services.analyst_tools import tool_get_analysis_detail
    result = await tool_get_analysis_detail(test_user.id, is_admin=False, analysis_id=str(analysis_with_reports.id))
    assert result["company_name"] == "Acme Corp"
    assert result["overall_score"] == 75.0
    assert len(result["reports"]) == 3
    assert all("score" in r for r in result["reports"])
    assert all("summary" in r for r in result["reports"])
    assert all("key_findings" in r for r in result["reports"])


@pytest.mark.asyncio
async def test_get_analysis_detail_denied(db, test_user, private_analysis):
    from app.services.analyst_tools import tool_get_analysis_detail
    with pytest.raises(ValueError, match="not found or access denied"):
        await tool_get_analysis_detail(test_user.id, is_admin=False, analysis_id=str(private_analysis.id))


# ── tool_get_memo tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_memo(db, test_user, sample_analysis, analysis_with_memo):
    from app.services.analyst_tools import tool_get_memo
    result = await tool_get_memo(test_user.id, is_admin=False, analysis_id=str(sample_analysis.id))
    assert result["status"] == "complete"
    assert "Investment Memo" in result["content"]


@pytest.mark.asyncio
async def test_get_memo_not_found(db, test_user, sample_analysis):
    from app.services.analyst_tools import tool_get_memo
    result = await tool_get_memo(test_user.id, is_admin=False, analysis_id=str(sample_analysis.id))
    assert result["status"] == "not_found"
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `cd /Users/leemosbacker/acutal/backend && python -m pytest tests/test_analyst_tools.py::test_get_analysis_detail tests/test_analyst_tools.py::test_get_memo -v`
Expected: FAIL — `AttributeError: module 'app.services.analyst_tools' has no attribute 'tool_get_analysis_detail'`

- [ ] **Step 3: Implement tool_get_analysis_detail and tool_get_memo**

Append to `backend/app/services/analyst_tools.py`:

```python
async def tool_get_analysis_detail(
    user_id: uuid.UUID, is_admin: bool, analysis_id: str
) -> dict:
    """Get full analysis detail with all agent reports."""
    async with async_session() as db:
        result = await db.execute(
            select(PitchAnalysis)
            .where(PitchAnalysis.id == uuid.UUID(analysis_id))
            .options(selectinload(PitchAnalysis.reports))
        )
        analysis = result.scalar_one_or_none()
        if not analysis:
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
                    "agent_type": r.agent_type.value if hasattr(r.agent_type, "value") else r.agent_type,
                    "status": _status_str(r),
                    "score": r.score,
                    "summary": r.summary,
                    "key_findings": r.key_findings,
                    "report": r.report,
                }
                for r in analysis.reports
            ],
        }


async def tool_get_memo(
    user_id: uuid.UUID, is_admin: bool, analysis_id: str
) -> dict:
    """Get investment memo content for an analysis."""
    async with async_session() as db:
        # First check access on the analysis
        analysis = await db.get(PitchAnalysis, uuid.UUID(analysis_id))
        if not analysis:
            raise ValueError("Analysis not found or access denied")
        _check_access(analysis, user_id, is_admin)

        # Load memo
        result = await db.execute(
            select(InvestmentMemo).where(InvestmentMemo.analysis_id == uuid.UUID(analysis_id))
        )
        memo = result.scalar_one_or_none()
        if not memo:
            return {"status": "not_found", "message": "No memo has been generated for this analysis yet."}

        memo_status = memo.status.value if hasattr(memo.status, "value") else memo.status
        if memo_status != "complete":
            return {"status": memo_status, "message": f"Memo is currently {memo_status}."}

        return {
            "status": "complete",
            "content": memo.content,
            "created_at": _dt_iso(memo.created_at),
            "completed_at": _dt_iso(memo.completed_at),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/leemosbacker/acutal/backend && python -m pytest tests/test_analyst_tools.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/leemosbacker/acutal/backend
git add app/services/analyst_tools.py tests/test_analyst_tools.py
git commit -m "feat: add get_analysis_detail and get_memo tools"
```

---

### Task 3: Add get_faq, list_pitch_sessions, and get_pitch_session_detail tools

**Files:**
- Modify: `backend/app/services/analyst_tools.py`
- Modify: `backend/tests/test_analyst_tools.py`

- [ ] **Step 1: Write tests**

Append to `backend/tests/test_analyst_tools.py`:

```python
from app.models.pitch_session import PitchSession, PitchSessionStatus, PitchAnalysisResult, PitchAnalysisPhase, PitchPhaseStatus


@pytest_asyncio.fixture
async def analysis_with_faq(db: AsyncSession, sample_analysis: PitchAnalysis) -> PitchAnalysis:
    sample_analysis.investor_faq = {
        "generated_at": "2026-04-30T00:00:00Z",
        "questions": [
            {"category": "market", "question": "How big is the market?", "answer": "Very big.", "priority": "high"},
        ],
    }
    await db.commit()
    await db.refresh(sample_analysis)
    return sample_analysis


@pytest_asyncio.fixture
async def sample_session(db: AsyncSession, test_user: User) -> PitchSession:
    session = PitchSession(
        id=uuid.uuid4(),
        user_id=test_user.id,
        title="Sequoia Pitch",
        status=PitchSessionStatus.complete,
        scores={"presentation_quality": 80, "meeting_dynamics": 70, "strategic_read": 90},
        benchmark_percentiles={"presentation_quality": 75},
        investor_faq={"generated_at": "2026-04-30T00:00:00Z", "questions": []},
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@pytest_asyncio.fixture
async def session_with_results(db: AsyncSession, sample_session: PitchSession) -> PitchSession:
    result = PitchAnalysisResult(
        session_id=sample_session.id,
        phase=PitchAnalysisPhase.scoring,
        status=PitchPhaseStatus.complete,
        result={"executive_summary": "Good pitch overall."},
    )
    db.add(result)
    await db.commit()
    return sample_session


# ── tool_get_faq tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_faq_analysis(db, test_user, analysis_with_faq):
    from app.services.analyst_tools import tool_get_faq
    result = await tool_get_faq(test_user.id, is_admin=False, analysis_id=str(analysis_with_faq.id))
    assert len(result["questions"]) == 1
    assert result["questions"][0]["category"] == "market"


@pytest.mark.asyncio
async def test_get_faq_session(db, test_user, sample_session):
    from app.services.analyst_tools import tool_get_faq
    result = await tool_get_faq(test_user.id, is_admin=False, session_id=str(sample_session.id))
    assert "questions" in result


@pytest.mark.asyncio
async def test_get_faq_no_faq(db, test_user, sample_analysis):
    from app.services.analyst_tools import tool_get_faq
    result = await tool_get_faq(test_user.id, is_admin=False, analysis_id=str(sample_analysis.id))
    assert result["status"] == "not_found"


# ── tool_list_pitch_sessions tests ───────────────────────────────────


@pytest.mark.asyncio
async def test_list_pitch_sessions(db, test_user, sample_session):
    from app.services.analyst_tools import tool_list_pitch_sessions
    results = await tool_list_pitch_sessions(test_user.id, is_admin=False)
    assert len(results) == 1
    assert results[0]["title"] == "Sequoia Pitch"
    assert results[0]["scores"]["presentation_quality"] == 80


@pytest.mark.asyncio
async def test_list_pitch_sessions_other_user(db, other_user, sample_session):
    from app.services.analyst_tools import tool_list_pitch_sessions
    results = await tool_list_pitch_sessions(other_user.id, is_admin=False)
    assert len(results) == 0  # not their session


# ── tool_get_pitch_session_detail tests ──────────────────────────────


@pytest.mark.asyncio
async def test_get_pitch_session_detail(db, test_user, session_with_results):
    from app.services.analyst_tools import tool_get_pitch_session_detail
    result = await tool_get_pitch_session_detail(test_user.id, is_admin=False, session_id=str(session_with_results.id))
    assert result["title"] == "Sequoia Pitch"
    assert result["scores"]["presentation_quality"] == 80
    assert len(result["results"]) == 1
    assert result["results"][0]["phase"] == "scoring"
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `cd /Users/leemosbacker/acutal/backend && python -m pytest tests/test_analyst_tools.py::test_get_faq_analysis tests/test_analyst_tools.py::test_list_pitch_sessions tests/test_analyst_tools.py::test_get_pitch_session_detail -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 3: Implement the three tools**

Append to `backend/app/services/analyst_tools.py`:

```python
async def tool_get_faq(
    user_id: uuid.UUID,
    is_admin: bool,
    analysis_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Get investor FAQ for an analysis or pitch session."""
    if not analysis_id and not session_id:
        raise ValueError("Provide either analysis_id or session_id")

    async with async_session() as db:
        if analysis_id:
            analysis = await db.get(PitchAnalysis, uuid.UUID(analysis_id))
            if not analysis:
                raise ValueError("Analysis not found or access denied")
            _check_access(analysis, user_id, is_admin)
            if not analysis.investor_faq:
                return {"status": "not_found", "message": "No FAQ generated yet for this analysis."}
            return analysis.investor_faq
        else:
            session = await db.get(PitchSession, uuid.UUID(session_id))
            if not session:
                raise ValueError("Session not found or access denied")
            if not is_admin and session.user_id != user_id:
                raise ValueError("Session not found or access denied")
            if not session.investor_faq:
                return {"status": "not_found", "message": "No FAQ generated yet for this session."}
            return session.investor_faq


async def tool_list_pitch_sessions(
    user_id: uuid.UUID,
    is_admin: bool,
    status: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """List pitch intelligence sessions the user can access."""
    async with async_session() as db:
        query = select(PitchSession)

        if not is_admin:
            query = query.where(PitchSession.user_id == user_id)

        if status:
            query = query.where(PitchSession.status == status)
        if search:
            query = query.where(PitchSession.title.ilike(f"%{search}%"))

        query = query.order_by(PitchSession.created_at.desc()).limit(50)
        result = await db.execute(query)
        sessions = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "title": s.title,
            "status": _status_str(s),
            "scores": s.scores,
            "created_at": _dt_iso(s.created_at),
        }
        for s in sessions
    ]


async def tool_get_pitch_session_detail(
    user_id: uuid.UUID, is_admin: bool, session_id: str
) -> dict:
    """Get full pitch session detail with phase results."""
    async with async_session() as db:
        result = await db.execute(
            select(PitchSession)
            .where(PitchSession.id == uuid.UUID(session_id))
            .options(selectinload(PitchSession.results))
        )
        session = result.scalar_one_or_none()
        if not session:
            raise ValueError("Session not found or access denied")
        if not is_admin and session.user_id != user_id:
            raise ValueError("Session not found or access denied")

        return {
            "id": str(session.id),
            "title": session.title,
            "status": _status_str(session),
            "scores": session.scores,
            "benchmark_percentiles": session.benchmark_percentiles,
            "investor_faq": session.investor_faq,
            "created_at": _dt_iso(session.created_at),
            "results": [
                {
                    "phase": r.phase.value if hasattr(r.phase, "value") else r.phase,
                    "status": _status_str(r),
                    "result": r.result,
                }
                for r in (session.results or [])
            ],
        }
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/leemosbacker/acutal/backend && python -m pytest tests/test_analyst_tools.py -v`
Expected: All 18 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/leemosbacker/acutal/backend
git add app/services/analyst_tools.py tests/test_analyst_tools.py
git commit -m "feat: add get_faq, list_pitch_sessions, get_pitch_session_detail tools"
```

---

### Task 4: Add regenerate_memo and regenerate_faq action tools

**Files:**
- Modify: `backend/app/services/analyst_tools.py`
- Modify: `backend/tests/test_analyst_tools.py`

- [ ] **Step 1: Write tests**

Append to `backend/tests/test_analyst_tools.py`:

```python
from unittest.mock import AsyncMock, patch


# ── tool_regenerate_memo tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_regenerate_memo_creates_new(db, test_user, sample_analysis):
    from app.services.analyst_tools import tool_regenerate_memo
    with patch("app.services.analyst_tools._start_memo_background") as mock_bg:
        result = await tool_regenerate_memo(test_user.id, is_admin=False, analysis_id=str(sample_analysis.id))
    assert result["status"] == "started"
    assert "memo_id" in result
    mock_bg.assert_called_once()


@pytest.mark.asyncio
async def test_regenerate_memo_not_complete(db, test_user):
    # Create a pending analysis
    pending = PitchAnalysis(
        id=uuid.uuid4(),
        user_id=test_user.id,
        company_name="Pending Corp",
        status=AnalysisStatus.pending,
    )
    db.add(pending)
    await db.commit()

    from app.services.analyst_tools import tool_regenerate_memo
    with pytest.raises(ValueError, match="must be complete"):
        await tool_regenerate_memo(test_user.id, is_admin=False, analysis_id=str(pending.id))


@pytest.mark.asyncio
async def test_regenerate_memo_denied(db, test_user, private_analysis):
    from app.services.analyst_tools import tool_regenerate_memo
    with pytest.raises(ValueError, match="not found or access denied"):
        await tool_regenerate_memo(test_user.id, is_admin=False, analysis_id=str(private_analysis.id))


# ── tool_regenerate_faq tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_regenerate_faq_analysis(db, test_user, analysis_with_reports):
    from app.services.analyst_tools import tool_regenerate_faq
    mock_faq = {"generated_at": "2026-04-30T00:00:00Z", "questions": [{"category": "market", "question": "Q?", "answer": "A.", "priority": "high"}]}
    with patch("app.services.analyst_tools.generate_investor_faq", new_callable=AsyncMock, return_value=mock_faq):
        result = await tool_regenerate_faq(test_user.id, is_admin=False, analysis_id=str(analysis_with_reports.id))
    assert len(result["questions"]) == 1


@pytest.mark.asyncio
async def test_regenerate_faq_denied(db, test_user, private_analysis):
    from app.services.analyst_tools import tool_regenerate_faq
    with pytest.raises(ValueError, match="not found or access denied"):
        await tool_regenerate_faq(test_user.id, is_admin=False, analysis_id=str(private_analysis.id))
```

- [ ] **Step 2: Run new tests to verify they fail**

Run: `cd /Users/leemosbacker/acutal/backend && python -m pytest tests/test_analyst_tools.py::test_regenerate_memo_creates_new tests/test_analyst_tools.py::test_regenerate_faq_analysis -v`
Expected: FAIL — `AttributeError`

- [ ] **Step 3: Implement the action tools**

Append to `backend/app/services/analyst_tools.py`:

```python
from app.services.faq_generator import generate_investor_faq


def _start_memo_background(memo_id: str) -> None:
    """Start memo generation in a background thread.

    Uses asyncio.run since this is called from within an async context
    that we don't want to block.
    """
    import asyncio
    import threading

    def _run():
        from app.services.memo_generator import run_memo_generation
        asyncio.run(run_memo_generation(memo_id))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


async def tool_regenerate_memo(
    user_id: uuid.UUID, is_admin: bool, analysis_id: str
) -> dict:
    """Regenerate investment memo for an analysis. Requires ownership."""
    async with async_session() as db:
        analysis = await db.get(PitchAnalysis, uuid.UUID(analysis_id))
        if not analysis:
            raise ValueError("Analysis not found or access denied")
        _check_access(analysis, user_id, is_admin, require_owner=True)

        if _status_str(analysis) != "complete":
            raise ValueError("Analysis must be complete before generating a memo")

        # Check for existing memo and reset it, or create new
        result = await db.execute(
            select(InvestmentMemo).where(InvestmentMemo.analysis_id == uuid.UUID(analysis_id))
        )
        memo = result.scalar_one_or_none()
        if memo:
            memo.status = "pending"
            memo.content = None
            memo.s3_key_pdf = None
            memo.s3_key_docx = None
            memo.error = None
            memo.completed_at = None
        else:
            memo = InvestmentMemo(
                analysis_id=uuid.UUID(analysis_id),
                status="pending",
            )
            db.add(memo)

        await db.commit()
        await db.refresh(memo)
        memo_id = str(memo.id)

    _start_memo_background(memo_id)

    return {
        "status": "started",
        "memo_id": memo_id,
        "message": f"Memo regeneration started for '{analysis.company_name}'. This takes 1-2 minutes.",
    }


async def tool_regenerate_faq(
    user_id: uuid.UUID,
    is_admin: bool,
    analysis_id: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Regenerate investor FAQ. Runs inline (single Claude call)."""
    if not analysis_id and not session_id:
        raise ValueError("Provide either analysis_id or session_id")

    async with async_session() as db:
        if analysis_id:
            result = await db.execute(
                select(PitchAnalysis)
                .where(PitchAnalysis.id == uuid.UUID(analysis_id))
                .options(selectinload(PitchAnalysis.reports))
            )
            analysis = result.scalar_one_or_none()
            if not analysis:
                raise ValueError("Analysis not found or access denied")
            _check_access(analysis, user_id, is_admin, require_owner=True)

            if _status_str(analysis) != "complete":
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
            await db.commit()
            return faq

        else:
            result = await db.execute(
                select(PitchSession)
                .where(PitchSession.id == uuid.UUID(session_id))
                .options(selectinload(PitchSession.results))
            )
            session = result.scalar_one_or_none()
            if not session:
                raise ValueError("Session not found or access denied")
            if not is_admin and session.user_id != user_id:
                raise ValueError("Session not found or access denied")

            if _status_str(session) != "complete":
                raise ValueError("Session must be complete before generating FAQ")

            session_data = {
                "title": session.title,
                "scores": session.scores,
                "results": [
                    {
                        "phase": r.phase.value if hasattr(r.phase, "value") else r.phase,
                        "result": r.result,
                    }
                    for r in (session.results or [])
                ],
            }

            faq = await generate_investor_faq(session_data, "pitch_intelligence")
            session.investor_faq = faq
            await db.commit()
            return faq
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/leemosbacker/acutal/backend && python -m pytest tests/test_analyst_tools.py -v`
Expected: All 23 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/leemosbacker/acutal/backend
git add app/services/analyst_tools.py tests/test_analyst_tools.py
git commit -m "feat: add regenerate_memo and regenerate_faq action tools"
```

---

### Task 5: Wire tools into analyst_agent.py

**Files:**
- Modify: `backend/app/services/analyst_agent.py:26-137` (TOOLS list and SYSTEM_PROMPT)
- Modify: `backend/app/services/analyst_agent.py:251-398` (run_agent signature and tool execution)

- [ ] **Step 1: Add tool definitions to TOOLS list**

In `backend/app/services/analyst_agent.py`, after the existing `create_chart` tool definition (after line 110), append these 8 tool definitions:

```python
    {
        "name": "list_analyses",
        "description": (
            "List the user's pitch deck analyses. Returns id, company_name, status, "
            "overall_score, fundraising_likelihood, created_at for each analysis. "
            "Use this to find analyses before fetching details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status: pending, extracting, analyzing, enriching, complete, failed"},
                "search": {"type": "string", "description": "Search by company name (case-insensitive)"},
                "description": {"type": "string", "description": "Brief description shown to user as status"},
            },
        },
    },
    {
        "name": "get_analysis_detail",
        "description": (
            "Get full details of a pitch deck analysis including all 8 agent reports. "
            "Returns scores, executive_summary, valuation, technical_expert_review, "
            "and each agent's score, summary, key_findings, and full report text. "
            "Agent types: problem_solution, market_tam, traction, technology_ip, "
            "competition_moat, team, gtm_business_model, financials_fundraising."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "analysis_id": {"type": "string", "description": "UUID of the analysis"},
                "description": {"type": "string", "description": "Brief description shown to user as status"},
            },
            "required": ["analysis_id"],
        },
    },
    {
        "name": "get_memo",
        "description": (
            "Get the investment memo content for a pitch analysis. "
            "Returns the full markdown memo with sections: Executive Summary, "
            "Company Overview, Market Opportunity, Product & Technology, "
            "Competitive Landscape, Team Assessment, Traction & Financials, "
            "Valuation & Investment Terms, Technical Expert Review, Risk Factors, "
            "and Recommendation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "analysis_id": {"type": "string", "description": "UUID of the analysis"},
                "description": {"type": "string", "description": "Brief description shown to user as status"},
            },
            "required": ["analysis_id"],
        },
    },
    {
        "name": "get_faq",
        "description": (
            "Get the investor FAQ for a pitch analysis or pitch intelligence session. "
            "Returns categorized Q&A pairs with priority levels. "
            "Provide exactly one of analysis_id or session_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "analysis_id": {"type": "string", "description": "UUID of the pitch analysis"},
                "session_id": {"type": "string", "description": "UUID of the pitch intelligence session"},
                "description": {"type": "string", "description": "Brief description shown to user as status"},
            },
        },
    },
    {
        "name": "list_pitch_sessions",
        "description": (
            "List the user's pitch intelligence sessions (video/audio pitch analyses). "
            "Returns id, title, status, scores, created_at for each session."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status: uploading, transcribing, labeling, analyzing, complete, failed"},
                "search": {"type": "string", "description": "Search by session title (case-insensitive)"},
                "description": {"type": "string", "description": "Brief description shown to user as status"},
            },
        },
    },
    {
        "name": "get_pitch_session_detail",
        "description": (
            "Get full details of a pitch intelligence session including phase results "
            "(claim_extraction, fact_check_founders, fact_check_investors, "
            "conversation_analysis, scoring, benchmark), scores, and benchmark percentiles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "UUID of the pitch session"},
                "description": {"type": "string", "description": "Brief description shown to user as status"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "regenerate_memo",
        "description": (
            "Re-generate the investment memo for a completed pitch analysis. "
            "This runs in the background and takes 1-2 minutes. "
            "Only the analysis owner can trigger this."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "analysis_id": {"type": "string", "description": "UUID of the analysis"},
                "description": {"type": "string", "description": "Brief description shown to user as status"},
            },
            "required": ["analysis_id"],
        },
    },
    {
        "name": "regenerate_faq",
        "description": (
            "Re-generate the investor FAQ for a completed analysis or pitch session. "
            "Runs inline and returns the new FAQ. "
            "Provide exactly one of analysis_id or session_id. "
            "Only the owner can trigger this."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "analysis_id": {"type": "string", "description": "UUID of the pitch analysis"},
                "session_id": {"type": "string", "description": "UUID of the pitch intelligence session"},
                "description": {"type": "string", "description": "Brief description shown to user as status"},
            },
        },
    },
```

- [ ] **Step 2: Update SYSTEM_PROMPT**

In `backend/app/services/analyst_agent.py`, append to the end of the `SYSTEM_PROMPT` string (before the closing `"""`):

```python
ANALYSIS TOOLS:
You also have tools to access the user's pitch analysis data:
- list_analyses — List the user's pitch deck analyses (search by name, filter by status)
- get_analysis_detail — Get full analysis with all 8 agent reports, scores, and findings
- get_memo — Get the investment memo content for an analysis
- get_faq — Get the investor FAQ for an analysis or pitch session
- list_pitch_sessions — List the user's pitch intelligence sessions
- get_pitch_session_detail — Get full pitch session results with fact-checks and benchmarks

Action tools:
- regenerate_memo — Re-generate an investment memo (runs in background, 1-2 min)
- regenerate_faq — Re-generate the investor FAQ (runs inline, returns new FAQ)

WHEN TO USE:
- User asks about their analyses, scores, reports, memos, or FAQs → use analysis tools
- User asks to compare their analyzed companies → list_analyses + get_analysis_detail
- User asks about weak points or strong areas → get_analysis_detail (check agent report scores)
- User asks about valuation → get_memo (check Valuation & Investment Terms section) or get_analysis_detail
- User asks to regenerate/redo memo or FAQ → use action tools
- For startup market/database queries → continue using run_sql and web_research
```

- [ ] **Step 3: Update run_agent signature and add tool executor routing**

In `backend/app/services/analyst_agent.py`, update the `run_agent` function signature to accept user context:

```python
async def run_agent(
    messages: list[dict],
    system_prompt: str | None = None,
    image_blocks: list[dict] | None = None,
    user_id: uuid.UUID | None = None,
    is_admin: bool = False,
) -> AsyncGenerator[dict, None]:
```

Then in the tool execution loop (the `for tb in tool_blocks:` section), add these cases after the existing `create_chart` elif block and before the `else` block:

```python
                    elif tb.name in (
                        "list_analyses", "get_analysis_detail", "get_memo",
                        "get_faq", "list_pitch_sessions", "get_pitch_session_detail",
                        "regenerate_memo", "regenerate_faq",
                    ):
                        from app.services.analyst_tools import (
                            tool_list_analyses, tool_get_analysis_detail,
                            tool_get_memo, tool_get_faq,
                            tool_list_pitch_sessions, tool_get_pitch_session_detail,
                            tool_regenerate_memo, tool_regenerate_faq,
                        )

                        desc = tb.input.get("description", f"Running {tb.name}")
                        yield {"type": "status", "message": desc}

                        if not user_id:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tb.id,
                                "content": "Error: User context not available for analysis tools.",
                                "is_error": True,
                            })
                            continue

                        tool_map = {
                            "list_analyses": lambda: tool_list_analyses(
                                user_id, is_admin,
                                status=tb.input.get("status"),
                                search=tb.input.get("search"),
                            ),
                            "get_analysis_detail": lambda: tool_get_analysis_detail(
                                user_id, is_admin, analysis_id=tb.input["analysis_id"],
                            ),
                            "get_memo": lambda: tool_get_memo(
                                user_id, is_admin, analysis_id=tb.input["analysis_id"],
                            ),
                            "get_faq": lambda: tool_get_faq(
                                user_id, is_admin,
                                analysis_id=tb.input.get("analysis_id"),
                                session_id=tb.input.get("session_id"),
                            ),
                            "list_pitch_sessions": lambda: tool_list_pitch_sessions(
                                user_id, is_admin,
                                status=tb.input.get("status"),
                                search=tb.input.get("search"),
                            ),
                            "get_pitch_session_detail": lambda: tool_get_pitch_session_detail(
                                user_id, is_admin, session_id=tb.input["session_id"],
                            ),
                            "regenerate_memo": lambda: tool_regenerate_memo(
                                user_id, is_admin, analysis_id=tb.input["analysis_id"],
                            ),
                            "regenerate_faq": lambda: tool_regenerate_faq(
                                user_id, is_admin,
                                analysis_id=tb.input.get("analysis_id"),
                                session_id=tb.input.get("session_id"),
                            ),
                        }

                        result_data = await tool_map[tb.name]()
                        payload = json.dumps(result_data, default=str)
                        if len(payload) > 50_000:
                            payload = payload[:50_000] + "\n... (truncated)"
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tb.id,
                            "content": payload,
                        })
```

Also add `import uuid` at the top of the file if not already present.

- [ ] **Step 4: Commit**

```bash
cd /Users/leemosbacker/acutal/backend
git add app/services/analyst_agent.py
git commit -m "feat: wire 8 analysis tools into analyst agent with tool definitions and routing"
```

---

### Task 6: Pass user context from API layer

**Files:**
- Modify: `backend/app/api/analyst.py:422` (inside `event_stream` closure)

- [ ] **Step 1: Update send_message to pass user context to run_agent**

In `backend/app/api/analyst.py`, in the `send_message` endpoint, capture the user info before the `event_stream` closure. Find this line around line 414:

```python
    conv_id = conversation.id
```

Add after it:

```python
    agent_user_id = user.id
    agent_is_admin = user.role == UserRole.superadmin
```

Then update the `run_agent` call inside `event_stream()` (around line 422). Change:

```python
            async for event in run_agent(history, image_blocks=image_blocks if image_blocks else None):
```

To:

```python
            async for event in run_agent(
                history,
                image_blocks=image_blocks if image_blocks else None,
                user_id=agent_user_id,
                is_admin=agent_is_admin,
            ):
```

Also add `UserRole` to the imports at the top if not already imported (it's already imported via `from app.models.user import ... User, UserRole`).

- [ ] **Step 2: Verify the import exists**

Check that `UserRole` is already imported in `analyst.py`. The existing import on line 16 is:
```python
from app.models.user import SubscriptionStatus, User
```

Update it to:
```python
from app.models.user import SubscriptionStatus, User, UserRole
```

- [ ] **Step 3: Commit**

```bash
cd /Users/leemosbacker/acutal/backend
git add app/api/analyst.py
git commit -m "feat: pass user_id and is_admin to analyst agent for analysis tools"
```

---

### Task 7: Manual integration test

- [ ] **Step 1: Run full test suite to check nothing is broken**

Run: `cd /Users/leemosbacker/acutal/backend && python -m pytest tests/ -v --timeout=30`
Expected: All tests PASS (existing + new)

- [ ] **Step 2: Verify imports work end-to-end**

Run: `cd /Users/leemosbacker/acutal/backend && python -c "from app.services.analyst_agent import run_agent, TOOLS; print(f'{len(TOOLS)} tools registered'); print([t['name'] for t in TOOLS])"`

Expected output:
```
11 tools registered
['run_sql', 'web_research', 'create_chart', 'list_analyses', 'get_analysis_detail', 'get_memo', 'get_faq', 'list_pitch_sessions', 'get_pitch_session_detail', 'regenerate_memo', 'regenerate_faq']
```

- [ ] **Step 3: Verify analyst_tools imports cleanly**

Run: `cd /Users/leemosbacker/acutal/backend && python -c "from app.services.analyst_tools import tool_list_analyses, tool_get_analysis_detail, tool_get_memo, tool_get_faq, tool_list_pitch_sessions, tool_get_pitch_session_detail, tool_regenerate_memo, tool_regenerate_faq; print('All 8 tools imported successfully')"`

Expected: `All 8 tools imported successfully`

- [ ] **Step 4: Commit all changes**

```bash
cd /Users/leemosbacker/acutal/backend
git add -A
git commit -m "feat: analyst chat insights tools — complete implementation"
```
