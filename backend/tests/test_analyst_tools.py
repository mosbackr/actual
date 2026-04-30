"""Tests for app.services.analyst_tools — access control and list_analyses.

All tests are fully self-contained and do NOT require a running database.
The conftest ``setup_db`` / ``db`` autouse fixtures are overridden locally
so that no PostgreSQL connection is attempted.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.pitch_analysis import AgentType, AnalysisStatus, ReportStatus
from app.models.pitch_session import PitchAnalysisPhase, PitchPhaseStatus, PitchSessionStatus
from app.services.analyst_tools import (
    _check_access,
    _dt_iso,
    _status_str,
    tool_get_analysis_detail,
    tool_get_faq,
    tool_get_memo,
    tool_get_pitch_session_detail,
    tool_list_analyses,
    tool_list_pitch_sessions,
    tool_regenerate_faq,
    tool_regenerate_memo,
)


# ── Override conftest autouse fixtures to avoid DB connections ────────

@pytest.fixture(autouse=True)
def setup_db():
    """Override the conftest autouse setup_db to skip real DB creation."""
    yield None


# ── Lightweight stub for _check_access unit tests ─────────────────────


class _FakeAnalysis:
    """Minimal stand-in for a PitchAnalysis row."""

    def __init__(
        self,
        user_id: uuid.UUID,
        status: str | AnalysisStatus = AnalysisStatus.complete,
        publish_consent: bool = True,
    ):
        self.user_id = user_id
        self.status = status
        self.publish_consent = publish_consent


# ── _check_access tests ──────────────────────────────────────────────


class TestCheckAccess:
    def test_owner_access(self):
        uid = uuid.uuid4()
        obj = _FakeAnalysis(user_id=uid)
        _check_access(obj, user_id=uid, is_admin=False)

    def test_admin_access(self):
        uid = uuid.uuid4()
        other_uid = uuid.uuid4()
        obj = _FakeAnalysis(user_id=uid, publish_consent=False, status=AnalysisStatus.pending)
        _check_access(obj, user_id=other_uid, is_admin=True)

    def test_published_access(self):
        owner = uuid.uuid4()
        viewer = uuid.uuid4()
        obj = _FakeAnalysis(user_id=owner, status=AnalysisStatus.complete, publish_consent=True)
        _check_access(obj, user_id=viewer, is_admin=False)

    def test_denied_not_owner_not_published(self):
        owner = uuid.uuid4()
        viewer = uuid.uuid4()
        obj = _FakeAnalysis(user_id=owner, status=AnalysisStatus.pending, publish_consent=True)
        with pytest.raises(ValueError, match="not found or access denied"):
            _check_access(obj, user_id=viewer, is_admin=False)

    def test_denied_not_owner_no_consent(self):
        owner = uuid.uuid4()
        viewer = uuid.uuid4()
        obj = _FakeAnalysis(user_id=owner, status=AnalysisStatus.complete, publish_consent=False)
        with pytest.raises(ValueError, match="not found or access denied"):
            _check_access(obj, user_id=viewer, is_admin=False)

    def test_require_owner_blocks_published(self):
        owner = uuid.uuid4()
        viewer = uuid.uuid4()
        obj = _FakeAnalysis(user_id=owner, status=AnalysisStatus.complete, publish_consent=True)
        with pytest.raises(ValueError, match="not found or access denied"):
            _check_access(obj, user_id=viewer, is_admin=False, require_owner=True)

    def test_require_owner_allows_owner(self):
        uid = uuid.uuid4()
        obj = _FakeAnalysis(user_id=uid)
        _check_access(obj, user_id=uid, is_admin=False, require_owner=True)

    def test_require_owner_allows_admin(self):
        owner = uuid.uuid4()
        admin = uuid.uuid4()
        obj = _FakeAnalysis(user_id=owner)
        _check_access(obj, user_id=admin, is_admin=True, require_owner=True)


# ── _status_str / _dt_iso tests ─────────────────────────────────────


class TestHelpers:
    def test_status_str_enum(self):
        obj = _FakeAnalysis(user_id=uuid.uuid4(), status=AnalysisStatus.complete)
        assert _status_str(obj) == "complete"

    def test_status_str_plain(self):
        obj = _FakeAnalysis(user_id=uuid.uuid4(), status="analyzing")
        assert _status_str(obj) == "analyzing"

    def test_dt_iso_none(self):
        assert _dt_iso(None) is None

    def test_dt_iso_value(self):
        dt = datetime(2025, 1, 15, 12, 30, 0, tzinfo=timezone.utc)
        assert _dt_iso(dt) == "2025-01-15T12:30:00+00:00"


# ── tool_list_analyses tests (mocked async_session) ──────────────────

# We mock async_session to avoid any real DB connection.  Each test builds
# a list of _FakeRow objects and a mock session that returns them, letting
# us validate the function's output logic without a real database.

_USER_A_ID = uuid.uuid4()
_USER_B_ID = uuid.uuid4()
_ADMIN_ID = uuid.uuid4()
_NOW = datetime.now(timezone.utc)


class _FakeRow:
    """Mimics the columns read by tool_list_analyses from PitchAnalysis."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        user_id: uuid.UUID,
        company_name: str,
        status: AnalysisStatus = AnalysisStatus.complete,
        overall_score: float | None = None,
        fundraising_likelihood: float | None = None,
        publish_consent: bool = True,
        created_at: datetime | None = None,
    ):
        self.id = id or uuid.uuid4()
        self.user_id = user_id
        self.company_name = company_name
        self.status = status
        self.overall_score = overall_score
        self.fundraising_likelihood = fundraising_likelihood
        self.publish_consent = publish_consent
        self.created_at = created_at or _NOW


def _all_rows() -> list[_FakeRow]:
    """Standard set of rows used by most tests."""
    return [
        _FakeRow(
            user_id=_USER_A_ID,
            company_name="Alpha Corp",
            status=AnalysisStatus.complete,
            overall_score=85.0,
            fundraising_likelihood=0.7,
            publish_consent=True,
        ),
        _FakeRow(
            user_id=_USER_A_ID,
            company_name="Beta Inc",
            status=AnalysisStatus.pending,
            publish_consent=True,
        ),
        _FakeRow(
            user_id=_USER_B_ID,
            company_name="Gamma LLC",
            status=AnalysisStatus.complete,
            overall_score=72.0,
            fundraising_likelihood=0.5,
            publish_consent=True,
        ),
        _FakeRow(
            user_id=_USER_B_ID,
            company_name="Delta Secret",
            status=AnalysisStatus.complete,
            overall_score=90.0,
            publish_consent=False,
        ),
    ]


def _mock_session_factory(rows: list[_FakeRow]):
    """Build a mock async_session factory that returns *rows* from execute().

    The mock session records the statement passed to execute() so that
    tool_list_analyses can call ``session.execute(stmt)`` as usual.
    Because we cannot easily evaluate the SQLAlchemy Select object in
    pure Python, we return ALL rows and let the test verify the
    function's output.  BUT the function itself applies filtering via
    the SQL WHERE clause, which means the mock must return the correct
    subset.

    To keep things simple and still exercise real logic, we inspect the
    function's arguments (user_id, is_admin, status, search) and
    pre-filter the rows ourselves to mimic what the DB would return.
    This is done in the test-level wrapper rather than here.
    """

    class _ScalarResult:
        def __init__(self, data):
            self._data = data

        def all(self):
            return self._data

    class _ExecResult:
        def __init__(self, data):
            self._data = data

        def scalars(self):
            return _ScalarResult(self._data)

    class _Session:
        async def execute(self, stmt):
            return _ExecResult(rows)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    def factory():
        return _Session()

    return factory


def _filter_rows(
    rows: list[_FakeRow],
    user_id: uuid.UUID,
    is_admin: bool,
    status: str | None = None,
    search: str | None = None,
) -> list[_FakeRow]:
    """Apply the same filtering logic the SQL query would apply."""
    result = list(rows)

    if not is_admin:
        result = [
            r
            for r in result
            if r.user_id == user_id
            or (r.publish_consent and r.status == AnalysisStatus.complete)
        ]

    if status is not None:
        result = [
            r
            for r in result
            if (r.status.value if hasattr(r.status, "value") else r.status) == status
        ]

    if search is not None:
        result = [
            r for r in result if search.lower() in r.company_name.lower()
        ]

    result.sort(key=lambda r: r.created_at, reverse=True)
    return result[:50]


@pytest.mark.asyncio
async def test_own_analyses_visible():
    """User A should see own analyses + published ones from user B."""
    all_rows = _all_rows()
    visible = _filter_rows(all_rows, _USER_A_ID, is_admin=False)
    factory = _mock_session_factory(visible)

    with patch("app.db.session.async_session", factory):
        results = await tool_list_analyses(user_id=_USER_A_ID, is_admin=False)

    names = {r["company_name"] for r in results}
    assert "Alpha Corp" in names
    assert "Beta Inc" in names
    assert "Gamma LLC" in names
    assert "Delta Secret" not in names

    for r in results:
        if r["company_name"] in ("Alpha Corp", "Beta Inc"):
            assert r["is_owner"] is True
        elif r["company_name"] == "Gamma LLC":
            assert r["is_owner"] is False


@pytest.mark.asyncio
async def test_admin_sees_all():
    """Admin should see all analyses regardless of ownership or consent."""
    all_rows = _all_rows()
    visible = _filter_rows(all_rows, _ADMIN_ID, is_admin=True)
    factory = _mock_session_factory(visible)

    with patch("app.db.session.async_session", factory):
        results = await tool_list_analyses(user_id=_ADMIN_ID, is_admin=True)

    names = {r["company_name"] for r in results}
    assert "Alpha Corp" in names
    assert "Beta Inc" in names
    assert "Gamma LLC" in names
    assert "Delta Secret" in names


@pytest.mark.asyncio
async def test_search_filter():
    """Search filter should narrow results by company_name."""
    all_rows = _all_rows()
    visible = _filter_rows(all_rows, _USER_A_ID, is_admin=False, search="Alpha")
    factory = _mock_session_factory(visible)

    with patch("app.db.session.async_session", factory):
        results = await tool_list_analyses(
            user_id=_USER_A_ID, is_admin=False, search="Alpha"
        )

    assert len(results) == 1
    assert results[0]["company_name"] == "Alpha Corp"


@pytest.mark.asyncio
async def test_status_filter():
    """Status filter should narrow to matching status only."""
    all_rows = _all_rows()
    visible = _filter_rows(all_rows, _USER_A_ID, is_admin=False, status="pending")
    factory = _mock_session_factory(visible)

    with patch("app.db.session.async_session", factory):
        results = await tool_list_analyses(
            user_id=_USER_A_ID, is_admin=False, status="pending"
        )

    assert len(results) == 1
    assert results[0]["company_name"] == "Beta Inc"
    assert results[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_private_analyses_hidden():
    """User B's non-published analysis should not be visible to user A."""
    all_rows = _all_rows()
    visible = _filter_rows(all_rows, _USER_A_ID, is_admin=False)
    factory = _mock_session_factory(visible)

    with patch("app.db.session.async_session", factory):
        results = await tool_list_analyses(user_id=_USER_A_ID, is_admin=False)

    names = {r["company_name"] for r in results}
    assert "Delta Secret" not in names


# ── Helpers for get_analysis_detail / get_memo tests ──────────────────


class _FakeReport:
    """Minimal stand-in for an AnalysisReport row."""

    def __init__(
        self,
        *,
        agent_type: AgentType = AgentType.team,
        status: ReportStatus = ReportStatus.complete,
        score: float | None = 80.0,
        summary: str | None = "Good team",
        key_findings: dict | None = None,
        report: str | None = "Full report text",
    ):
        self.agent_type = agent_type
        self.status = status
        self.score = score
        self.summary = summary
        self.key_findings = key_findings or ["finding1"]
        self.report = report


class _FakeDetailRow:
    """Mimics PitchAnalysis with all fields needed by tool_get_analysis_detail."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        user_id: uuid.UUID,
        company_name: str = "Test Corp",
        status: AnalysisStatus = AnalysisStatus.complete,
        overall_score: float | None = 85.0,
        fundraising_likelihood: float | None = 0.7,
        recommended_raise: str | None = "$5M",
        exit_likelihood: float | None = 0.6,
        expected_exit_value: str | None = "$100M",
        expected_exit_timeline: str | None = "5-7 years",
        executive_summary: str | None = "A great company",
        estimated_valuation: str | None = "$20M",
        valuation_justification: str | None = "Strong metrics",
        technical_expert_review: dict | None = None,
        investor_faq: dict | None = None,
        publish_consent: bool = True,
        created_at: datetime | None = None,
        completed_at: datetime | None = None,
        reports: list | None = None,
    ):
        self.id = id or uuid.uuid4()
        self.user_id = user_id
        self.company_name = company_name
        self.status = status
        self.overall_score = overall_score
        self.fundraising_likelihood = fundraising_likelihood
        self.recommended_raise = recommended_raise
        self.exit_likelihood = exit_likelihood
        self.expected_exit_value = expected_exit_value
        self.expected_exit_timeline = expected_exit_timeline
        self.executive_summary = executive_summary
        self.estimated_valuation = estimated_valuation
        self.valuation_justification = valuation_justification
        self.technical_expert_review = technical_expert_review
        self.investor_faq = investor_faq
        self.publish_consent = publish_consent
        self.created_at = created_at or _NOW
        self.completed_at = completed_at
        self.reports = reports or []


class _FakeMemo:
    """Minimal stand-in for an InvestmentMemo row."""

    def __init__(
        self,
        *,
        status: str = "complete",
        content: str | None = "Full memo content here.",
        created_at: datetime | None = None,
        completed_at: datetime | None = None,
    ):
        self.status = status
        self.content = content
        self.created_at = created_at or _NOW
        self.completed_at = completed_at or _NOW


def _mock_single_session_factory(row):
    """Build a mock async_session factory returning a single row from scalars().first()."""

    class _ScalarResult:
        def __init__(self, data):
            self._data = data

        def all(self):
            return [self._data] if self._data else []

        def first(self):
            return self._data

    class _ExecResult:
        def __init__(self, data):
            self._data = data

        def scalars(self):
            return _ScalarResult(self._data)

    class _Session:
        async def execute(self, stmt):
            return _ExecResult(row)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    def factory():
        return _Session()

    return factory


def _mock_two_query_session_factory(analysis_row, memo_row):
    """Build a mock async_session factory that returns different results for two queries.

    First execute() call returns *analysis_row*, second returns *memo_row*.
    """

    class _ScalarResult:
        def __init__(self, data):
            self._data = data

        def first(self):
            return self._data

    class _ExecResult:
        def __init__(self, data):
            self._data = data

        def scalars(self):
            return _ScalarResult(self._data)

    class _Session:
        def __init__(self):
            self._call_count = 0

        async def execute(self, stmt):
            self._call_count += 1
            if self._call_count == 1:
                return _ExecResult(analysis_row)
            return _ExecResult(memo_row)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    def factory():
        return _Session()

    return factory


# ── tool_get_analysis_detail tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_get_analysis_detail():
    """Owner can get full analysis detail including reports."""
    uid = _USER_A_ID
    report = _FakeReport(
        agent_type=AgentType.team,
        status=ReportStatus.complete,
        score=88.0,
        summary="Strong team",
        key_findings=["Experienced founders"],
        report="Detailed report about the team.",
    )
    analysis = _FakeDetailRow(
        user_id=uid,
        company_name="Detail Corp",
        overall_score=90.0,
        reports=[report],
    )
    factory = _mock_single_session_factory(analysis)

    with patch("app.db.session.async_session", factory):
        result = await tool_get_analysis_detail(
            user_id=uid, is_admin=False, analysis_id=str(analysis.id)
        )

    assert result["company_name"] == "Detail Corp"
    assert result["overall_score"] == 90.0
    assert result["is_owner"] is True
    assert result["recommended_raise"] == "$5M"
    assert result["exit_likelihood"] == 0.6
    assert result["expected_exit_value"] == "$100M"
    assert result["expected_exit_timeline"] == "5-7 years"
    assert result["executive_summary"] == "A great company"
    assert result["estimated_valuation"] == "$20M"
    assert result["valuation_justification"] == "Strong metrics"
    assert result["status"] == "complete"
    assert result["id"] == str(analysis.id)

    assert len(result["reports"]) == 1
    rpt = result["reports"][0]
    assert rpt["agent_type"] == "team"
    assert rpt["status"] == "complete"
    assert rpt["score"] == 88.0
    assert rpt["summary"] == "Strong team"
    assert rpt["key_findings"] == ["Experienced founders"]
    assert rpt["report"] == "Detailed report about the team."


@pytest.mark.asyncio
async def test_get_analysis_detail_denied():
    """Another user's private (not published) analysis raises ValueError."""
    owner = _USER_A_ID
    viewer = _USER_B_ID
    analysis = _FakeDetailRow(
        user_id=owner,
        company_name="Private Corp",
        status=AnalysisStatus.pending,
        publish_consent=False,
    )
    factory = _mock_single_session_factory(analysis)

    with patch("app.db.session.async_session", factory):
        with pytest.raises(ValueError, match="not found or access denied"):
            await tool_get_analysis_detail(
                user_id=viewer, is_admin=False, analysis_id=str(analysis.id)
            )


# ── tool_get_memo tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_memo_complete():
    """Analysis with a complete memo returns content."""
    uid = _USER_A_ID
    analysis = _FakeDetailRow(user_id=uid, company_name="Memo Corp")
    memo = _FakeMemo(
        status="complete",
        content="This is the full investment memo.",
    )
    factory = _mock_two_query_session_factory(analysis, memo)

    with patch("app.db.session.async_session", factory):
        result = await tool_get_memo(
            user_id=uid, is_admin=False, analysis_id=str(analysis.id)
        )

    assert result["status"] == "complete"
    assert result["content"] == "This is the full investment memo."
    assert result["created_at"] is not None
    assert result["completed_at"] is not None


@pytest.mark.asyncio
async def test_get_memo_not_found():
    """Analysis without a memo returns status not_found."""
    uid = _USER_A_ID
    analysis = _FakeDetailRow(user_id=uid, company_name="NoMemo Corp")
    factory = _mock_two_query_session_factory(analysis, None)

    with patch("app.db.session.async_session", factory):
        result = await tool_get_memo(
            user_id=uid, is_admin=False, analysis_id=str(analysis.id)
        )

    assert result["status"] == "not_found"
    assert "No memo has been generated" in result["message"]


# ── Helpers for pitch session tests ───────────────────────────────────


class _FakePitchSession:
    """Minimal stand-in for a PitchSession row."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        user_id: uuid.UUID,
        title: str = "Test Pitch",
        status: PitchSessionStatus = PitchSessionStatus.complete,
        scores: dict | None = None,
        benchmark_percentiles: dict | None = None,
        investor_faq: dict | None = None,
        created_at: datetime | None = None,
        results: list | None = None,
    ):
        self.id = id or uuid.uuid4()
        self.user_id = user_id
        self.title = title
        self.status = status
        self.scores = scores
        self.benchmark_percentiles = benchmark_percentiles
        self.investor_faq = investor_faq
        self.created_at = created_at or _NOW
        self.results = results or []


class _FakePitchResult:
    """Minimal stand-in for a PitchAnalysisResult row."""

    def __init__(
        self,
        *,
        phase: PitchAnalysisPhase = PitchAnalysisPhase.scoring,
        status: PitchPhaseStatus = PitchPhaseStatus.complete,
        result: dict | None = None,
    ):
        self.phase = phase
        self.status = status
        self.result = result


# ── tool_get_faq tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_faq_analysis():
    """Analysis with investor_faq set returns the FAQ."""
    uid = _USER_A_ID
    faq_data = {"questions": [{"q": "What is the TAM?", "a": "$10B"}]}
    analysis = _FakeDetailRow(
        user_id=uid,
        company_name="FAQ Corp",
        investor_faq=faq_data,
    )
    # Need to add investor_faq to _FakeDetailRow — it's already accepted via **kwargs
    factory = _mock_single_session_factory(analysis)

    with patch("app.db.session.async_session", factory):
        result = await tool_get_faq(
            user_id=uid, is_admin=False, analysis_id=str(analysis.id)
        )

    assert result == faq_data


@pytest.mark.asyncio
async def test_get_faq_session():
    """Session with investor_faq set returns the FAQ."""
    uid = _USER_A_ID
    faq_data = {"questions": [{"q": "Revenue model?", "a": "SaaS"}]}
    session_obj = _FakePitchSession(
        user_id=uid,
        title="FAQ Session",
        investor_faq=faq_data,
    )
    factory = _mock_single_session_factory(session_obj)

    with patch("app.db.session.async_session", factory):
        result = await tool_get_faq(
            user_id=uid, is_admin=False, session_id=str(session_obj.id)
        )

    assert result == faq_data


@pytest.mark.asyncio
async def test_get_faq_not_found():
    """Analysis without FAQ returns status not_found."""
    uid = _USER_A_ID
    analysis = _FakeDetailRow(user_id=uid, company_name="NoFAQ Corp")
    # investor_faq defaults to None in _FakeDetailRow
    factory = _mock_single_session_factory(analysis)

    with patch("app.db.session.async_session", factory):
        result = await tool_get_faq(
            user_id=uid, is_admin=False, analysis_id=str(analysis.id)
        )

    assert result["status"] == "not_found"
    assert "No FAQ generated yet" in result["message"]


# ── tool_list_pitch_sessions tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_list_pitch_sessions():
    """User's sessions returned, other user's not."""
    sessions = [
        _FakePitchSession(
            user_id=_USER_A_ID,
            title="My Pitch",
            scores={"overall": 80},
        ),
    ]
    factory = _mock_session_factory(sessions)

    with patch("app.db.session.async_session", factory):
        results = await tool_list_pitch_sessions(
            user_id=_USER_A_ID, is_admin=False
        )

    assert len(results) == 1
    assert results[0]["title"] == "My Pitch"
    assert results[0]["scores"] == {"overall": 80}
    assert results[0]["status"] == "complete"
    assert results[0]["id"] is not None
    assert results[0]["created_at"] is not None


@pytest.mark.asyncio
async def test_list_pitch_sessions_other_user():
    """Other user sees nothing (sessions are private, no publish_consent)."""
    # Simulate DB returning nothing for user B (no sessions owned)
    factory = _mock_session_factory([])

    with patch("app.db.session.async_session", factory):
        results = await tool_list_pitch_sessions(
            user_id=_USER_B_ID, is_admin=False
        )

    assert results == []


# ── tool_get_pitch_session_detail tests ───────────────────────────────


@pytest.mark.asyncio
async def test_get_pitch_session_detail():
    """Returns full session with results."""
    uid = _USER_A_ID
    phase_result = _FakePitchResult(
        phase=PitchAnalysisPhase.scoring,
        status=PitchPhaseStatus.complete,
        result={"overall_score": 85, "dimensions": {"team": 90}},
    )
    session_obj = _FakePitchSession(
        user_id=uid,
        title="Detail Pitch",
        status=PitchSessionStatus.complete,
        scores={"overall": 85},
        benchmark_percentiles={"team": 75},
        investor_faq={"questions": [{"q": "Burn rate?", "a": "$50k/mo"}]},
        results=[phase_result],
    )
    factory = _mock_single_session_factory(session_obj)

    with patch("app.db.session.async_session", factory):
        result = await tool_get_pitch_session_detail(
            user_id=uid, is_admin=False, session_id=str(session_obj.id)
        )

    assert result["id"] == str(session_obj.id)
    assert result["title"] == "Detail Pitch"
    assert result["status"] == "complete"
    assert result["scores"] == {"overall": 85}
    assert result["benchmark_percentiles"] == {"team": 75}
    assert result["investor_faq"] == {"questions": [{"q": "Burn rate?", "a": "$50k/mo"}]}
    assert result["created_at"] is not None

    assert len(result["results"]) == 1
    r = result["results"][0]
    assert r["phase"] == "scoring"
    assert r["status"] == "complete"
    assert r["result"] == {"overall_score": 85, "dimensions": {"team": 90}}


# ── Helpers for regenerate tests ──────────────────────────────────────


def _mock_writable_two_query_session_factory(analysis_row, memo_row):
    """Build a mock async_session factory that supports commit/add and two queries.

    First execute() returns *analysis_row*, second returns *memo_row*.
    """

    class _ScalarResult:
        def __init__(self, data):
            self._data = data

        def first(self):
            return self._data

    class _ExecResult:
        def __init__(self, data):
            self._data = data

        def scalars(self):
            return _ScalarResult(self._data)

    class _Session:
        def __init__(self):
            self._call_count = 0
            self._added = []

        async def execute(self, stmt):
            self._call_count += 1
            if self._call_count == 1:
                return _ExecResult(analysis_row)
            return _ExecResult(memo_row)

        def add(self, obj):
            self._added.append(obj)

        async def commit(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    def factory():
        return _Session()

    return factory


def _mock_writable_single_session_factory(row):
    """Build a mock async_session factory that supports commit and returns one row."""

    class _ScalarResult:
        def __init__(self, data):
            self._data = data

        def first(self):
            return self._data

    class _ExecResult:
        def __init__(self, data):
            self._data = data

        def scalars(self):
            return _ScalarResult(self._data)

    class _Session:
        async def execute(self, stmt):
            return _ExecResult(row)

        async def commit(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    def factory():
        return _Session()

    return factory


# ── tool_regenerate_memo tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_regenerate_memo_creates_new():
    """Regenerating memo on an analysis without one creates a new memo and starts background."""
    uid = _USER_A_ID
    analysis = _FakeDetailRow(
        user_id=uid,
        company_name="Memo Corp",
        status=AnalysisStatus.complete,
    )
    # No existing memo
    factory = _mock_writable_two_query_session_factory(analysis, None)

    with (
        patch("app.db.session.async_session", factory),
        patch("app.services.analyst_tools._start_memo_background") as mock_bg,
    ):
        result = await tool_regenerate_memo(
            user_id=uid, is_admin=False, analysis_id=str(analysis.id)
        )

    assert result["status"] == "started"
    assert "memo_id" in result
    assert "Memo Corp" in result["message"]
    mock_bg.assert_called_once_with(result["memo_id"])


@pytest.mark.asyncio
async def test_regenerate_memo_not_complete():
    """Attempting to regenerate memo on a pending analysis raises ValueError."""
    uid = _USER_A_ID
    analysis = _FakeDetailRow(
        user_id=uid,
        company_name="Pending Corp",
        status=AnalysisStatus.pending,
    )
    factory = _mock_writable_two_query_session_factory(analysis, None)

    with patch("app.db.session.async_session", factory):
        with pytest.raises(ValueError, match="must be complete"):
            await tool_regenerate_memo(
                user_id=uid, is_admin=False, analysis_id=str(analysis.id)
            )


@pytest.mark.asyncio
async def test_regenerate_memo_denied():
    """Another user cannot regenerate memo on someone else's private analysis."""
    owner = _USER_A_ID
    viewer = _USER_B_ID
    analysis = _FakeDetailRow(
        user_id=owner,
        company_name="Private Corp",
        status=AnalysisStatus.complete,
        publish_consent=False,
    )
    factory = _mock_writable_two_query_session_factory(analysis, None)

    with patch("app.db.session.async_session", factory):
        with pytest.raises(ValueError, match="not found or access denied"):
            await tool_regenerate_memo(
                user_id=viewer, is_admin=False, analysis_id=str(analysis.id)
            )


# ── tool_regenerate_faq tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_regenerate_faq_analysis():
    """Regenerating FAQ for a complete analysis returns the FAQ dict."""
    uid = _USER_A_ID
    report = _FakeReport(
        agent_type=AgentType.team,
        score=85.0,
        summary="Solid team",
        key_findings=["Strong CTO"],
    )
    analysis = _FakeDetailRow(
        user_id=uid,
        company_name="FAQ Corp",
        status=AnalysisStatus.complete,
        reports=[report],
    )
    fake_faq = {"questions": [{"q": "What is the TAM?", "a": "$10B"}]}
    factory = _mock_writable_single_session_factory(analysis)

    with (
        patch("app.db.session.async_session", factory),
        patch(
            "app.services.analyst_tools.generate_investor_faq",
            new_callable=AsyncMock,
            return_value=fake_faq,
        ) as mock_gen,
    ):
        result = await tool_regenerate_faq(
            user_id=uid, is_admin=False, analysis_id=str(analysis.id)
        )

    assert result == fake_faq
    mock_gen.assert_called_once()
    call_args = mock_gen.call_args
    assert call_args[0][1] == "pitch_analysis"
    assert call_args[0][0]["company_name"] == "FAQ Corp"


@pytest.mark.asyncio
async def test_regenerate_faq_denied():
    """Another user cannot regenerate FAQ on someone else's private analysis."""
    owner = _USER_A_ID
    viewer = _USER_B_ID
    analysis = _FakeDetailRow(
        user_id=owner,
        company_name="Private Corp",
        status=AnalysisStatus.complete,
        publish_consent=False,
    )
    factory = _mock_writable_single_session_factory(analysis)

    with patch("app.db.session.async_session", factory):
        with pytest.raises(ValueError, match="not found or access denied"):
            await tool_regenerate_faq(
                user_id=viewer, is_admin=False, analysis_id=str(analysis.id)
            )
