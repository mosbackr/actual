# Investor Rankings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a batch scoring pipeline that ranks every investor in the database across 7 dimensions using Perplexity research + Claude scoring, with admin UI for triggering and viewing.

**Architecture:** New `investor_rankings` and `investor_ranking_batch_jobs` tables. A batch service calls Perplexity (2 calls per investor for research), merges with internal startup/funding data, then calls Claude to produce 7 dimension scores (0-100) and a narrative. Admin panel gets a "Rankings" tab on the existing investors page.

**Tech Stack:** Python/FastAPI (backend), SQLAlchemy + Alembic (ORM/migrations), Perplexity Sonar Pro API, Anthropic Claude API (claude-sonnet-4-6), Next.js/React (admin frontend), TypeScript

---

## File Structure

**Backend — Create:**
- `backend/alembic/versions/y4z5a6b7c8d9_add_investor_ranking_tables.py` — Migration for new tables
- `backend/app/models/investor_ranking.py` — `InvestorRanking` and `InvestorRankingBatchJob` models
- `backend/app/services/investor_ranking.py` — Scoring pipeline (Perplexity calls, internal merge, Claude scoring)
- `backend/app/api/admin_investor_rankings.py` — API endpoints for batch control + ranked list

**Backend — Modify:**
- `backend/app/models/__init__.py` — Add new model exports
- `backend/app/main.py` — Register new router

**Admin Frontend — Create:**
- `admin/app/investors/rankings/page.tsx` — Rankings tab page (batch controls + ranked table)

**Admin Frontend — Modify:**
- `admin/lib/types.ts` — Add ranking types
- `admin/lib/api.ts` — Add ranking API methods
- `admin/app/investors/page.tsx` — Add tab navigation between Investors and Rankings

---

### Task 1: Database Migration

**Files:**
- Create: `backend/alembic/versions/y4z5a6b7c8d9_add_investor_ranking_tables.py`

- [ ] **Step 1: Create the migration file**

```python
"""Add investor_rankings and investor_ranking_batch_jobs tables

Revision ID: y4z5a6b7c8d9
Revises: x3y4z5a6b7c8
Create Date: 2026-04-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "y4z5a6b7c8d9"
down_revision = "x3y4z5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investor_rankings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("investor_id", UUID(as_uuid=True), sa.ForeignKey("investors.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("overall_score", sa.Float, nullable=False),
        sa.Column("portfolio_performance", sa.Float, nullable=False),
        sa.Column("deal_activity", sa.Float, nullable=False),
        sa.Column("exit_track_record", sa.Float, nullable=False),
        sa.Column("stage_expertise", sa.Float, nullable=False),
        sa.Column("sector_expertise", sa.Float, nullable=False),
        sa.Column("follow_on_rate", sa.Float, nullable=False),
        sa.Column("network_quality", sa.Float, nullable=False),
        sa.Column("narrative", sa.Text, nullable=False),
        sa.Column("perplexity_research", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("scoring_metadata", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_investor_rankings_overall_score", "investor_rankings", ["overall_score"])
    op.create_index("ix_investor_rankings_investor_id", "investor_rankings", ["investor_id"], unique=True)

    op.create_table(
        "investor_ranking_batch_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("total_investors", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("processed_investors", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("current_investor_id", UUID(as_uuid=True), nullable=True),
        sa.Column("current_investor_name", sa.String(300), nullable=True),
        sa.Column("investors_scored", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("investor_ranking_batch_jobs")
    op.drop_index("ix_investor_rankings_investor_id", table_name="investor_rankings")
    op.drop_index("ix_investor_rankings_overall_score", table_name="investor_rankings")
    op.drop_table("investor_rankings")
```

- [ ] **Step 2: Commit**

```bash
git add backend/alembic/versions/y4z5a6b7c8d9_add_investor_ranking_tables.py
git commit -m "feat(investor-rankings): add migration for ranking tables"
```

---

### Task 2: SQLAlchemy Models

**Files:**
- Create: `backend/app/models/investor_ranking.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the model file**

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base
from app.models.investor import BatchJobStatus


class InvestorRanking(Base):
    __tablename__ = "investor_rankings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    investor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investors.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    portfolio_performance: Mapped[float] = mapped_column(Float, nullable=False)
    deal_activity: Mapped[float] = mapped_column(Float, nullable=False)
    exit_track_record: Mapped[float] = mapped_column(Float, nullable=False)
    stage_expertise: Mapped[float] = mapped_column(Float, nullable=False)
    sector_expertise: Mapped[float] = mapped_column(Float, nullable=False)
    follow_on_rate: Mapped[float] = mapped_column(Float, nullable=False)
    network_quality: Mapped[float] = mapped_column(Float, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    perplexity_research: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    scoring_metadata: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class InvestorRankingBatchJob(Base):
    __tablename__ = "investor_ranking_batch_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BatchJobStatus.pending.value
    )
    total_investors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_investors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_investor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    current_investor_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    investors_scored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
```

- [ ] **Step 2: Register models in `__init__.py`**

Add these imports to `backend/app/models/__init__.py`:

```python
from app.models.investor_ranking import InvestorRanking, InvestorRankingBatchJob
```

And add to the `__all__` list:

```python
"InvestorRanking",
"InvestorRankingBatchJob",
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/investor_ranking.py backend/app/models/__init__.py
git commit -m "feat(investor-rankings): add InvestorRanking and InvestorRankingBatchJob models"
```

---

### Task 3: Scoring Pipeline Service

**Files:**
- Create: `backend/app/services/investor_ranking.py`

This is the core logic. It follows the exact same pattern as `investor_extraction.py` for Perplexity calls and batch processing.

- [ ] **Step 1: Create the scoring service**

```python
import json
import logging
import re
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import async_session
from app.models.funding_round import StartupFundingRound
from app.models.investor import BatchJobStatus, Investor
from app.models.investor_ranking import InvestorRanking, InvestorRankingBatchJob
from app.models.startup import CompanyStatus, Startup

logger = logging.getLogger(__name__)

DIMENSION_NAMES = [
    "portfolio_performance",
    "deal_activity",
    "exit_track_record",
    "stage_expertise",
    "sector_expertise",
    "follow_on_rate",
    "network_quality",
]


# ── Perplexity helpers ────────────────────────────────────────────────


async def _call_perplexity(messages: list[dict], timeout: int = 120) -> str:
    if not settings.perplexity_api_key:
        raise RuntimeError("ACUTAL_PERPLEXITY_API_KEY is not configured")

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.perplexity_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar-pro",
                "temperature": 0.1,
                "max_tokens": 8000,
                "messages": messages,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _build_portfolio_prompt(investor: Investor) -> list[dict]:
    """Perplexity call 1: portfolio & performance research."""
    recent = ", ".join(investor.recent_investments or [])
    system_msg = (
        "You are a venture capital research analyst. Return structured, factual data about "
        "investors. Include numbers, dates, and specific company names. Return ONLY valid JSON."
    )
    user_msg = f"""Research the investment track record of {investor.partner_name} at {investor.firm_name}.

Known details:
- Stage focus: {investor.stage_focus or "Unknown"}
- Sector focus: {investor.sector_focus or "Unknown"}
- Location: {investor.location or "Unknown"}
- AUM/Fund size: {investor.aum_fund_size or "Unknown"}
- Recent investments: {recent or "Unknown"}

Return a JSON object with these fields:
{{
  "portfolio_companies": [
    {{"name": "Company Name", "stage_invested": "Seed/A/B", "year": 2023, "status": "active|acquired|ipo|defunct", "outcome_details": "acquired by X for $Y" or null}}
  ],
  "total_investments_count": number or null,
  "notable_exits": [
    {{"company": "Name", "exit_type": "acquisition|ipo", "exit_year": 2023, "return_multiple": "10x" or null, "acquirer_or_listing": "Google" or null}}
  ],
  "fund_details": {{
    "fund_size": "$100M" or null,
    "fund_vintage": "2020" or null,
    "fund_performance": "top quartile" or null
  }},
  "investment_pace": {{
    "deals_last_2_years": number or null,
    "deals_last_5_years": number or null,
    "avg_check_size": "$500K" or null
  }}
}}

Return ONLY the JSON object, no other text."""

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _build_network_prompt(investor: Investor) -> list[dict]:
    """Perplexity call 2: network & follow-on research."""
    system_msg = (
        "You are a venture capital research analyst. Return structured, factual data about "
        "investors. Include numbers, dates, and specific names. Return ONLY valid JSON."
    )
    user_msg = f"""Research the co-investment network and follow-on patterns for {investor.partner_name} at {investor.firm_name}.

Return a JSON object with these fields:
{{
  "co_investors": [
    {{"firm": "Sequoia", "deals_together": 5, "tier": "top_tier|mid_tier|emerging"}}
  ],
  "follow_on_data": {{
    "companies_with_follow_on": number or null,
    "total_portfolio_size": number or null,
    "notable_follow_on_investors": ["Firm A", "Firm B"],
    "avg_time_to_next_round_months": number or null
  }},
  "stage_pattern": {{
    "primary_stage": "seed|series_a|series_b|growth",
    "stage_distribution": {{"pre_seed": 10, "seed": 50, "series_a": 30, "series_b": 10}}
  }},
  "sector_pattern": {{
    "primary_sectors": ["AI/ML", "Fintech"],
    "sector_distribution": {{"AI/ML": 40, "Fintech": 30, "SaaS": 20, "Other": 10}}
  }},
  "reputation_signals": {{
    "board_seats": number or null,
    "thought_leadership": "description or null",
    "notable_roles": "description or null"
  }}
}}

Return ONLY the JSON object, no other text."""

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _extract_json_object(text: str) -> dict:
    """Extract a JSON object from fenced or bare text."""
    # Try fenced JSON first
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        return json.loads(m.group(1))

    # Try bare JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = text[start : end + 1]
        raw = re.sub(r",\s*([}\]])", r"\1", raw)
        return json.loads(raw)

    raise ValueError("No JSON object found in response")


# ── Internal data merge ───────────────────────────────────────────────


async def _get_internal_data(db: AsyncSession, investor: Investor) -> dict:
    """Cross-reference investor with our startup/funding data."""
    firm_lower = investor.firm_name.lower()
    partner_lower = investor.partner_name.lower()

    # Find funding rounds where this investor appears
    result = await db.execute(
        select(StartupFundingRound, Startup)
        .join(Startup, StartupFundingRound.startup_id == Startup.id)
        .where(
            func.lower(StartupFundingRound.lead_investor).contains(firm_lower)
            | func.lower(StartupFundingRound.other_investors).contains(firm_lower)
            | func.lower(StartupFundingRound.lead_investor).contains(partner_lower)
            | func.lower(StartupFundingRound.other_investors).contains(partner_lower)
        )
    )
    rows = result.all()

    matched_startups = []
    lead_count = 0
    for funding_round, startup in rows:
        is_lead = funding_round.lead_investor and (
            firm_lower in funding_round.lead_investor.lower()
            or partner_lower in funding_round.lead_investor.lower()
        )
        if is_lead:
            lead_count += 1
        matched_startups.append({
            "name": startup.name,
            "stage": startup.stage.value if startup.stage else None,
            "ai_score": startup.ai_score,
            "company_status": startup.company_status.value if startup.company_status else None,
            "round_name": funding_round.round_name,
            "amount": funding_round.amount,
            "is_lead": is_lead,
        })

    # Count outcomes
    statuses = [s["company_status"] for s in matched_startups]
    exits = statuses.count("acquired") + statuses.count("ipo")
    active = statuses.count("active")
    defunct = statuses.count("defunct")
    avg_ai_score = None
    scores = [s["ai_score"] for s in matched_startups if s["ai_score"] is not None]
    if scores:
        avg_ai_score = round(sum(scores) / len(scores), 1)

    # Also check source_startups from the investor record itself
    source_count = len(investor.source_startups or [])

    return {
        "matched_funding_rounds": len(rows),
        "matched_startups": matched_startups,
        "lead_deals": lead_count,
        "exits_in_db": exits,
        "active_in_db": active,
        "defunct_in_db": defunct,
        "avg_ai_score_of_portfolio": avg_ai_score,
        "source_startups_count": source_count,
    }


# ── Claude scoring ────────────────────────────────────────────────────


SCORING_SYSTEM_PROMPT = """You are a venture capital analyst scoring investors across 7 dimensions.

Score each dimension from 0 to 100 based on the research data provided. Use these rubrics:

**Portfolio Performance (0-100):**
- Quality of portfolio companies (active vs defunct, known metrics)
- Funding trajectory (up-rounds, growing valuations)
- Weight toward recent investments (last 3 years)
- If internal DB data exists, factor in ai_scores and company_status

**Deal Activity (0-100):**
- Volume of investments (more = higher, diminishing returns above ~50/yr)
- Recency — heavily weight last 2 years
- Consistency — steady pace vs sporadic bursts

**Exit Track Record (0-100):**
- Number of exits (acquisitions + IPOs)
- Quality (IPO > major acquisition > acqui-hire)
- Known return multiples
- Exit rate as % of total portfolio

**Stage Expertise (0-100):**
- Concentration/depth at specific stages
- Track record at those stages
- Bonus for clear thesis/specialization

**Sector Expertise (0-100):**
- Concentration in specific verticals
- Track record within those verticals
- Domain signals (board seats, speaking, thought leadership)

**Follow-on Rate (0-100):**
- % of portfolio companies that raised subsequent rounds
- Quality of follow-on investors attracted
- Time between rounds (faster = stronger signal)

**Network / Co-investor Quality (0-100):**
- Quality tier of co-investors (top-tier VCs vs unknown angels)
- Diversity of co-investor network
- Repeat syndicate partnerships

For investors with limited data, score conservatively (40-60 range). Do not inflate scores.

Return ONLY a JSON object with this exact structure:
{
  "portfolio_performance": <int 0-100>,
  "deal_activity": <int 0-100>,
  "exit_track_record": <int 0-100>,
  "stage_expertise": <int 0-100>,
  "sector_expertise": <int 0-100>,
  "follow_on_rate": <int 0-100>,
  "network_quality": <int 0-100>,
  "narrative": "<2-3 paragraph analyst note about this investor's strengths, weaknesses, and notable deals. Professional tone, data-grounded.>"
}"""


async def _score_with_claude(
    investor: Investor,
    portfolio_research: dict,
    network_research: dict,
    internal_data: dict,
) -> dict:
    """Call Claude to score the investor across 7 dimensions + generate narrative."""
    if not settings.anthropic_api_key:
        raise RuntimeError("ACUTAL_ANTHROPIC_API_KEY is not configured")

    user_msg = f"""Score this investor:

**Investor:** {investor.partner_name} at {investor.firm_name}
**Stage Focus:** {investor.stage_focus or "Unknown"}
**Sector Focus:** {investor.sector_focus or "Unknown"}
**Location:** {investor.location or "Unknown"}
**AUM/Fund Size:** {investor.aum_fund_size or "Unknown"}

---

**Perplexity Research — Portfolio & Performance:**
{json.dumps(portfolio_research, indent=2, default=str)}

---

**Perplexity Research — Network & Follow-on:**
{json.dumps(network_research, indent=2, default=str)}

---

**Internal Database Matches:**
- Funding rounds matched: {internal_data['matched_funding_rounds']}
- Lead deals in our DB: {internal_data['lead_deals']}
- Exits in our DB: {internal_data['exits_in_db']}
- Active companies in our DB: {internal_data['active_in_db']}
- Defunct companies in our DB: {internal_data['defunct_in_db']}
- Avg AI score of portfolio companies: {internal_data['avg_ai_score_of_portfolio'] or 'N/A'}
- Source startups count: {internal_data['source_startups_count']}
- Matched startups detail: {json.dumps(internal_data['matched_startups'][:20], default=str)}

Score this investor now."""

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 4096,
                "system": SCORING_SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_msg}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["content"][0]["text"]
        return _extract_json_object(content)


# ── Single investor scoring ───────────────────────────────────────────


async def _score_single_investor(db: AsyncSession, investor: Investor) -> InvestorRanking:
    """Run the full 3-step pipeline for one investor and upsert the ranking."""
    # Step 1: Perplexity research
    portfolio_research = {}
    network_research = {}

    for attempt in range(2):
        try:
            messages = _build_portfolio_prompt(investor)
            raw = await _call_perplexity(messages)
            portfolio_research = _extract_json_object(raw)
            break
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == 0:
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": "Your response was not valid JSON. Return ONLY a JSON object, no other text.",
                })
            else:
                logger.warning(f"Portfolio research JSON parse failed for {investor.firm_name}: {e}")

    for attempt in range(2):
        try:
            messages = _build_network_prompt(investor)
            raw = await _call_perplexity(messages)
            network_research = _extract_json_object(raw)
            break
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == 0:
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": "Your response was not valid JSON. Return ONLY a JSON object, no other text.",
                })
            else:
                logger.warning(f"Network research JSON parse failed for {investor.firm_name}: {e}")

    # Step 2: Internal data merge
    internal_data = await _get_internal_data(db, investor)

    # Step 3: Claude scoring
    scores = await _score_with_claude(investor, portfolio_research, network_research, internal_data)

    # Validate and clamp scores
    dimension_scores = {}
    for dim in DIMENSION_NAMES:
        val = scores.get(dim, 50)
        if not isinstance(val, (int, float)):
            val = 50
        dimension_scores[dim] = max(0.0, min(100.0, float(val)))

    overall = round(sum(dimension_scores.values()) / len(DIMENSION_NAMES), 1)
    narrative = scores.get("narrative", "No narrative generated.")

    # Upsert ranking
    result = await db.execute(
        select(InvestorRanking).where(InvestorRanking.investor_id == investor.id)
    )
    existing = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing:
        existing.overall_score = overall
        existing.portfolio_performance = dimension_scores["portfolio_performance"]
        existing.deal_activity = dimension_scores["deal_activity"]
        existing.exit_track_record = dimension_scores["exit_track_record"]
        existing.stage_expertise = dimension_scores["stage_expertise"]
        existing.sector_expertise = dimension_scores["sector_expertise"]
        existing.follow_on_rate = dimension_scores["follow_on_rate"]
        existing.network_quality = dimension_scores["network_quality"]
        existing.narrative = narrative
        existing.perplexity_research = {
            "portfolio": portfolio_research,
            "network": network_research,
        }
        existing.scoring_metadata = {
            "internal_data": internal_data,
            "raw_scores": scores,
        }
        existing.scored_at = now
        existing.updated_at = now
        ranking = existing
    else:
        ranking = InvestorRanking(
            investor_id=investor.id,
            overall_score=overall,
            portfolio_performance=dimension_scores["portfolio_performance"],
            deal_activity=dimension_scores["deal_activity"],
            exit_track_record=dimension_scores["exit_track_record"],
            stage_expertise=dimension_scores["stage_expertise"],
            sector_expertise=dimension_scores["sector_expertise"],
            follow_on_rate=dimension_scores["follow_on_rate"],
            network_quality=dimension_scores["network_quality"],
            narrative=narrative,
            perplexity_research={
                "portfolio": portfolio_research,
                "network": network_research,
            },
            scoring_metadata={
                "internal_data": internal_data,
                "raw_scores": scores,
            },
            scored_at=now,
        )
        db.add(ranking)

    await db.commit()
    return ranking


# ── Batch runner ──────────────────────────────────────────────────────


async def run_ranking_batch(job_id: str) -> None:
    """Main batch loop. Score all investors, checking for pause between each."""
    db_factory = async_session

    # Mark running
    async with db_factory() as db:
        job = await db.get(InvestorRankingBatchJob, uuid.UUID(job_id))
        if not job:
            logger.error(f"Ranking batch job {job_id} not found")
            return
        job.status = BatchJobStatus.running.value
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # Load all investors
    async with db_factory() as db:
        result = await db.execute(
            select(Investor).order_by(Investor.firm_name.asc(), Investor.partner_name.asc())
        )
        all_investors = result.scalars().all()
        investor_data = [
            {
                "id": inv.id,
                "firm_name": inv.firm_name,
                "partner_name": inv.partner_name,
            }
            for inv in all_investors
        ]

    # Update total
    async with db_factory() as db:
        job = await db.get(InvestorRankingBatchJob, uuid.UUID(job_id))
        job.total_investors = len(investor_data)
        await db.commit()

    # Process each investor
    for idx, inv_data in enumerate(investor_data):
        # Check for pause
        async with db_factory() as db:
            job = await db.get(InvestorRankingBatchJob, uuid.UUID(job_id))
            if job.status == BatchJobStatus.paused.value:
                logger.info(f"Ranking batch {job_id} paused at investor {idx}")
                return
            if idx < job.processed_investors:
                continue

        # Update current
        async with db_factory() as db:
            job = await db.get(InvestorRankingBatchJob, uuid.UUID(job_id))
            job.current_investor_id = inv_data["id"]
            job.current_investor_name = f"{inv_data['firm_name']} ({inv_data['partner_name']})"
            await db.commit()

        scored = 0
        try:
            async with db_factory() as db:
                investor = await db.get(Investor, inv_data["id"])
                if investor:
                    await _score_single_investor(db, investor)
                    scored = 1
        except Exception as e:
            logger.error(f"Failed scoring {inv_data['firm_name']}: {e}")
            async with db_factory() as db:
                job = await db.get(InvestorRankingBatchJob, uuid.UUID(job_id))
                errors = job.error or ""
                job.error = f"{errors}\n{inv_data['firm_name']}: {e}".strip()
                await db.commit()

        # Update progress
        async with db_factory() as db:
            job = await db.get(InvestorRankingBatchJob, uuid.UUID(job_id))
            job.processed_investors = idx + 1
            job.investors_scored = (job.investors_scored or 0) + scored
            await db.commit()

        logger.info(
            f"Scored {idx + 1}/{len(investor_data)}: {inv_data['firm_name']} ({inv_data['partner_name']})"
        )

    # Mark complete
    async with db_factory() as db:
        job = await db.get(InvestorRankingBatchJob, uuid.UUID(job_id))
        job.status = BatchJobStatus.completed.value
        job.current_investor_id = None
        job.current_investor_name = None
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()

    logger.info(f"Ranking batch {job_id} complete")


async def rescore_single(investor_id: str) -> InvestorRanking:
    """Re-score a single investor outside of a batch."""
    async with async_session() as db:
        investor = await db.get(Investor, uuid.UUID(investor_id))
        if not investor:
            raise ValueError(f"Investor {investor_id} not found")
        return await _score_single_investor(db, investor)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/investor_ranking.py
git commit -m "feat(investor-rankings): add scoring pipeline service with Perplexity + Claude"
```

---

### Task 4: API Endpoints

**Files:**
- Create: `backend/app/api/admin_investor_rankings.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the API router**

```python
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.investor import BatchJobStatus, Investor
from app.models.investor_ranking import InvestorRanking, InvestorRankingBatchJob
from app.models.user import User

router = APIRouter()


@router.post("/api/admin/investors/rankings/batch")
async def start_ranking_batch(
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Check no job already running/paused
    result = await db.execute(
        select(InvestorRankingBatchJob).where(
            InvestorRankingBatchJob.status.in_([
                BatchJobStatus.running.value,
                BatchJobStatus.paused.value,
            ])
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A ranking batch is already {existing.status}. Pause or wait for it to finish.",
        )

    job = InvestorRankingBatchJob()
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from app.services.investor_ranking import run_ranking_batch

    background_tasks.add_task(run_ranking_batch, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.put("/api/admin/investors/rankings/batch/{job_id}/pause")
async def pause_ranking_batch(
    job_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(InvestorRankingBatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.running.value:
        raise HTTPException(status_code=400, detail="Job is not running")

    from datetime import datetime, timezone

    job.status = BatchJobStatus.paused.value
    job.paused_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": str(job.id), "status": job.status}


@router.put("/api/admin/investors/rankings/batch/{job_id}/resume")
async def resume_ranking_batch(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(InvestorRankingBatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.paused.value:
        raise HTTPException(status_code=400, detail="Job is not paused")

    job.status = BatchJobStatus.running.value
    await db.commit()

    from app.services.investor_ranking import run_ranking_batch

    background_tasks.add_task(run_ranking_batch, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.get("/api/admin/investors/rankings/batch/status")
async def get_ranking_batch_status(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InvestorRankingBatchJob)
        .order_by(InvestorRankingBatchJob.created_at.desc())
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if not job:
        return None

    return {
        "id": str(job.id),
        "status": job.status,
        "total_investors": job.total_investors,
        "processed_investors": job.processed_investors,
        "current_investor_name": job.current_investor_name,
        "investors_scored": job.investors_scored,
        "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "paused_at": job.paused_at.isoformat() if job.paused_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


SORT_COLUMNS = {
    "overall_score": InvestorRanking.overall_score,
    "portfolio_performance": InvestorRanking.portfolio_performance,
    "deal_activity": InvestorRanking.deal_activity,
    "exit_track_record": InvestorRanking.exit_track_record,
    "stage_expertise": InvestorRanking.stage_expertise,
    "sector_expertise": InvestorRanking.sector_expertise,
    "follow_on_rate": InvestorRanking.follow_on_rate,
    "network_quality": InvestorRanking.network_quality,
    "firm_name": Investor.firm_name,
}


@router.get("/api/admin/investors/rankings")
async def list_ranked_investors(
    sort: str = "overall_score",
    order: str = "desc",
    q: str | None = None,
    min_score: float | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(InvestorRanking, Investor)
        .join(Investor, InvestorRanking.investor_id == Investor.id)
    )

    if q:
        like = f"%{q}%"
        query = query.where(
            Investor.firm_name.ilike(like) | Investor.partner_name.ilike(like)
        )
    if min_score is not None:
        query = query.where(InvestorRanking.overall_score >= min_score)

    # Count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # Sort
    sort_col = SORT_COLUMNS.get(sort, InvestorRanking.overall_score)
    if order == "asc":
        query = query.order_by(sort_col.asc())
    else:
        query = query.order_by(sort_col.desc())

    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    rows = result.all()

    pages = max(1, (total + per_page - 1) // per_page)

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "items": [
            {
                "id": str(ranking.id),
                "investor_id": str(investor.id),
                "firm_name": investor.firm_name,
                "partner_name": investor.partner_name,
                "location": investor.location,
                "stage_focus": investor.stage_focus,
                "sector_focus": investor.sector_focus,
                "overall_score": ranking.overall_score,
                "portfolio_performance": ranking.portfolio_performance,
                "deal_activity": ranking.deal_activity,
                "exit_track_record": ranking.exit_track_record,
                "stage_expertise": ranking.stage_expertise,
                "sector_expertise": ranking.sector_expertise,
                "follow_on_rate": ranking.follow_on_rate,
                "network_quality": ranking.network_quality,
                "narrative": ranking.narrative,
                "scored_at": ranking.scored_at.isoformat(),
            }
            for ranking, investor in rows
        ],
    }


@router.post("/api/admin/investors/rankings/{investor_id}/rescore")
async def rescore_investor(
    investor_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    investor = await db.get(Investor, investor_id)
    if not investor:
        raise HTTPException(status_code=404, detail="Investor not found")

    from app.services.investor_ranking import rescore_single

    background_tasks.add_task(rescore_single, str(investor_id))

    return {"ok": True, "message": f"Re-scoring {investor.firm_name} ({investor.partner_name})"}
```

- [ ] **Step 2: Register the router in `main.py`**

Add to the imports section of `backend/app/main.py` (after the `admin_feedback_router` import, around line 71):

```python
from app.api.admin_investor_rankings import router as admin_investor_rankings_router
```

Add to the router includes (after `app.include_router(admin_feedback_router)`, around line 127):

```python
app.include_router(admin_investor_rankings_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin_investor_rankings.py backend/app/main.py
git commit -m "feat(investor-rankings): add admin API endpoints for ranking batch and list"
```

---

### Task 5: Admin Frontend Types and API Client

**Files:**
- Modify: `admin/lib/types.ts`
- Modify: `admin/lib/api.ts`

- [ ] **Step 1: Add ranking types to `admin/lib/types.ts`**

Append after the `FeedbackListResponse` interface (end of file):

```typescript
// ── Investor Rankings ────────────────────────────────────────────────

export interface RankedInvestorItem {
  id: string;
  investor_id: string;
  firm_name: string;
  partner_name: string;
  location: string | null;
  stage_focus: string | null;
  sector_focus: string | null;
  overall_score: number;
  portfolio_performance: number;
  deal_activity: number;
  exit_track_record: number;
  stage_expertise: number;
  sector_expertise: number;
  follow_on_rate: number;
  network_quality: number;
  narrative: string;
  scored_at: string;
}

export interface RankedInvestorListResponse {
  total: number;
  page: number;
  per_page: number;
  pages: number;
  items: RankedInvestorItem[];
}

export interface RankingBatchStatus {
  id: string;
  status: "pending" | "running" | "paused" | "completed" | "failed";
  total_investors: number;
  processed_investors: number;
  current_investor_name: string | null;
  investors_scored: number;
  error: string | null;
  started_at: string | null;
  paused_at: string | null;
  completed_at: string | null;
}
```

- [ ] **Step 2: Add ranking API methods to `admin/lib/api.ts`**

Add the import of the new types to the existing import statement at the top of `admin/lib/api.ts`:

Add `RankedInvestorListResponse`, `RankingBatchStatus` to the import list from `"./types"`.

Then append these methods inside the `adminApi` object (after `getFeedbackDetail`):

```typescript
  // Investor Rankings
  startRankingBatch: (token: string) =>
    apiFetch<{ id: string; status: string }>("/api/admin/investors/rankings/batch", token, {
      method: "POST",
    }),

  pauseRankingBatch: (token: string, jobId: string) =>
    apiFetch<{ id: string; status: string }>(`/api/admin/investors/rankings/batch/${jobId}/pause`, token, {
      method: "PUT",
    }),

  resumeRankingBatch: (token: string, jobId: string) =>
    apiFetch<{ id: string; status: string }>(`/api/admin/investors/rankings/batch/${jobId}/resume`, token, {
      method: "PUT",
    }),

  getRankingBatchStatus: (token: string) =>
    apiFetch<RankingBatchStatus | null>("/api/admin/investors/rankings/batch/status", token),

  getRankedInvestors: (token: string, params?: {
    sort?: string;
    order?: string;
    q?: string;
    min_score?: number;
    page?: number;
    per_page?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params?.sort) sp.set("sort", params.sort);
    if (params?.order) sp.set("order", params.order);
    if (params?.q) sp.set("q", params.q);
    if (params?.min_score !== undefined) sp.set("min_score", String(params.min_score));
    if (params?.page) sp.set("page", String(params.page));
    if (params?.per_page) sp.set("per_page", String(params.per_page));
    const qs = sp.toString();
    return apiFetch<RankedInvestorListResponse>(`/api/admin/investors/rankings${qs ? `?${qs}` : ""}`, token);
  },

  rescoreInvestor: (token: string, investorId: string) =>
    apiFetch<{ ok: boolean; message: string }>(`/api/admin/investors/rankings/${investorId}/rescore`, token, {
      method: "POST",
    }),
```

- [ ] **Step 3: Commit**

```bash
git add admin/lib/types.ts admin/lib/api.ts
git commit -m "feat(investor-rankings): add admin frontend types and API client methods"
```

---

### Task 6: Admin Rankings Page

**Files:**
- Create: `admin/app/investors/rankings/page.tsx`

- [ ] **Step 1: Create the rankings page**

```tsx
"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { adminApi } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { AccessDenied } from "@/components/AccessDenied";
import Link from "next/link";
import type { RankedInvestorItem, RankingBatchStatus } from "@/lib/types";

const SCORE_COLUMNS = [
  { key: "overall_score", label: "Overall" },
  { key: "portfolio_performance", label: "Portfolio" },
  { key: "deal_activity", label: "Activity" },
  { key: "exit_track_record", label: "Exits" },
  { key: "stage_expertise", label: "Stage" },
  { key: "sector_expertise", label: "Sector" },
  { key: "follow_on_rate", label: "Follow-on" },
  { key: "network_quality", label: "Network" },
] as const;

function scoreColor(score: number): string {
  if (score >= 80) return "text-green-400";
  if (score >= 60) return "text-yellow-400";
  if (score >= 40) return "text-text-secondary";
  return "text-red-400";
}

export default function InvestorRankingsPage() {
  const { data: session, status } = useSession();
  const token = session?.backendToken;

  // Batch state
  const [batchStatus, setBatchStatus] = useState<RankingBatchStatus | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);

  // List state
  const [investors, setInvestors] = useState<RankedInvestorItem[]>([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("overall_score");
  const [order, setOrder] = useState("desc");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [rescoring, setRescoring] = useState<string | null>(null);

  const fetchBatchStatus = useCallback(async () => {
    if (!token) return;
    try {
      const s = await adminApi.getRankingBatchStatus(token);
      setBatchStatus(s);
    } catch {}
  }, [token]);

  const fetchRankings = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await adminApi.getRankedInvestors(token, {
        sort,
        order,
        q: search || undefined,
        page,
        per_page: 50,
      });
      setInvestors(data.items);
      setTotal(data.total);
      setPages(data.pages);
    } catch {}
    setLoading(false);
  }, [token, sort, order, search, page]);

  useEffect(() => {
    fetchBatchStatus();
    fetchRankings();
  }, [fetchBatchStatus, fetchRankings]);

  // Poll while running
  useEffect(() => {
    if (!batchStatus || batchStatus.status !== "running") return;
    const interval = setInterval(() => {
      fetchBatchStatus();
    }, 5000);
    return () => clearInterval(interval);
  }, [batchStatus?.status, fetchBatchStatus]);

  async function startBatch() {
    if (!token) return;
    setBatchLoading(true);
    try {
      await adminApi.startRankingBatch(token);
      await fetchBatchStatus();
    } catch (e: any) {
      alert(e.message || "Failed to start ranking batch");
    }
    setBatchLoading(false);
  }

  async function pauseBatch() {
    if (!token || !batchStatus) return;
    setBatchLoading(true);
    try {
      await adminApi.pauseRankingBatch(token, batchStatus.id);
      await fetchBatchStatus();
    } catch (e: any) {
      alert(e.message || "Failed to pause");
    }
    setBatchLoading(false);
  }

  async function resumeBatch() {
    if (!token || !batchStatus) return;
    setBatchLoading(true);
    try {
      await adminApi.resumeRankingBatch(token, batchStatus.id);
      await fetchBatchStatus();
    } catch (e: any) {
      alert(e.message || "Failed to resume");
    }
    setBatchLoading(false);
  }

  async function handleRescore(investorId: string) {
    if (!token) return;
    setRescoring(investorId);
    try {
      await adminApi.rescoreInvestor(token, investorId);
      // Refresh after a short delay to allow background task to complete
      setTimeout(() => fetchRankings(), 3000);
    } catch (e: any) {
      alert(e.message || "Failed to rescore");
    }
    setRescoring(null);
  }

  function handleSort(key: string) {
    if (sort === key) {
      setOrder(order === "desc" ? "asc" : "desc");
    } else {
      setSort(key);
      setOrder("desc");
    }
    setPage(1);
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setPage(1);
    setSearch(searchInput);
  }

  const isRunning = batchStatus?.status === "running";
  const isPaused = batchStatus?.status === "paused";
  const progressPct =
    batchStatus && batchStatus.total_investors > 0
      ? Math.round((batchStatus.processed_investors / batchStatus.total_investors) * 100)
      : 0;

  if (status === "loading") return null;
  if (!session || (session as any).role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        {/* Header with tab nav */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold text-text-primary">Investor Rankings</h1>
            <p className="text-sm text-text-secondary mt-1">
              {total.toLocaleString()} ranked investors
            </p>
          </div>
          <div className="flex gap-2">
            <Link
              href="/investors"
              className="px-4 py-2 text-sm border border-border rounded text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
            >
              Investors
            </Link>
            <span className="px-4 py-2 text-sm bg-accent text-white rounded">
              Rankings
            </span>
          </div>
        </div>

        {/* Batch Controls */}
        <div className="border border-border rounded-lg p-4 mb-6 bg-surface">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-medium text-text-primary">Investor Scoring</h2>
              <p className="text-xs text-text-tertiary mt-0.5">
                Uses Perplexity research + Claude scoring across 7 dimensions
              </p>
            </div>
            <div className="flex items-center gap-2">
              {!isRunning && !isPaused && (
                <button
                  onClick={startBatch}
                  disabled={batchLoading}
                  className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
                >
                  {batchLoading ? "Starting..." : "Score All Investors"}
                </button>
              )}
              {isRunning && (
                <button
                  onClick={pauseBatch}
                  disabled={batchLoading}
                  className="px-4 py-2 border border-border text-text-secondary text-sm rounded hover:border-text-tertiary transition disabled:opacity-50"
                >
                  Pause
                </button>
              )}
              {isPaused && (
                <button
                  onClick={resumeBatch}
                  disabled={batchLoading}
                  className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
                >
                  Resume
                </button>
              )}
            </div>
          </div>

          {(isRunning || isPaused) && batchStatus && (
            <div className="mt-3">
              <div className="flex items-center justify-between text-xs text-text-secondary mb-1">
                <span>
                  {batchStatus.processed_investors}/{batchStatus.total_investors} investors
                  {batchStatus.current_investor_name && isRunning && (
                    <> — scoring <strong>{batchStatus.current_investor_name}</strong></>
                  )}
                  {isPaused && " — paused"}
                </span>
                <span>{batchStatus.investors_scored.toLocaleString()} scored</span>
              </div>
              <div className="w-full bg-background rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all ${isPaused ? "bg-text-tertiary" : "bg-accent"}`}
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>
          )}

          {batchStatus?.status === "completed" && (
            <p className="text-xs text-text-tertiary mt-2">
              Last batch completed — {batchStatus.investors_scored.toLocaleString()} investors scored
              out of {batchStatus.total_investors}
            </p>
          )}
          {batchStatus?.status === "failed" && (
            <p className="text-xs text-red-500 mt-2">
              Batch failed: {batchStatus.error}
            </p>
          )}
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex gap-2 mb-4">
          <input
            type="text"
            placeholder="Search firm or partner..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="flex-1 px-3 py-2 border border-border rounded bg-background text-text-primary text-sm placeholder:text-text-tertiary focus:outline-none focus:border-accent"
          />
          <button
            type="submit"
            className="px-4 py-2 border border-border rounded text-sm text-text-secondary hover:border-text-tertiary transition"
          >
            Search
          </button>
          {search && (
            <button
              type="button"
              onClick={() => {
                setSearchInput("");
                setSearch("");
                setPage(1);
              }}
              className="px-3 py-2 text-xs text-text-tertiary hover:text-text-secondary transition"
            >
              Clear
            </button>
          )}
        </form>

        {/* Table */}
        {loading ? (
          <p className="text-text-tertiary text-sm py-10 text-center">Loading...</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left px-2 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium w-10">
                      #
                    </th>
                    <th className="text-left px-2 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">
                      <button onClick={() => handleSort("firm_name")} className="hover:text-text-primary transition">
                        Investor {sort === "firm_name" && (order === "asc" ? "↑" : "↓")}
                      </button>
                    </th>
                    {SCORE_COLUMNS.map((col) => (
                      <th key={col.key} className="text-center px-2 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">
                        <button onClick={() => handleSort(col.key)} className="hover:text-text-primary transition">
                          {col.label} {sort === col.key && (order === "asc" ? "↑" : "↓")}
                        </button>
                      </th>
                    ))}
                    <th className="text-left px-2 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">
                      Scored
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {investors.map((row, idx) => (
                    <>
                      <tr
                        key={row.id}
                        onClick={() => setExpandedId(expandedId === row.id ? null : row.id)}
                        className="border-b border-border hover:bg-hover-row transition-colors cursor-pointer"
                      >
                        <td className="px-2 py-3 text-text-tertiary tabular-nums">
                          {(page - 1) * 50 + idx + 1}
                        </td>
                        <td className="px-2 py-3">
                          <div className="font-medium text-text-primary">{row.firm_name}</div>
                          <div className="text-xs text-text-tertiary">{row.partner_name}</div>
                        </td>
                        {SCORE_COLUMNS.map((col) => (
                          <td key={col.key} className="px-2 py-3 text-center tabular-nums">
                            <span className={`font-medium ${col.key === "overall_score" ? "text-lg " : "text-sm "}${scoreColor(row[col.key as keyof RankedInvestorItem] as number)}`}>
                              {Math.round(row[col.key as keyof RankedInvestorItem] as number)}
                            </span>
                          </td>
                        ))}
                        <td className="px-2 py-3 text-xs text-text-tertiary">
                          {new Date(row.scored_at).toLocaleDateString()}
                        </td>
                      </tr>
                      {expandedId === row.id && (
                        <tr key={`${row.id}-detail`}>
                          <td colSpan={11} className="px-2 pb-4">
                            <div className="border border-border rounded-lg p-4 bg-surface">
                              <div className="flex items-center justify-between mb-3">
                                <h3 className="text-sm font-medium text-text-primary">
                                  {row.firm_name} — {row.partner_name}
                                </h3>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleRescore(row.investor_id);
                                  }}
                                  disabled={rescoring === row.investor_id}
                                  className="px-3 py-1 text-xs border border-border rounded text-text-secondary hover:border-text-tertiary transition disabled:opacity-50"
                                >
                                  {rescoring === row.investor_id ? "Re-scoring..." : "Re-score"}
                                </button>
                              </div>
                              {row.stage_focus && (
                                <p className="text-xs text-text-tertiary mb-1">
                                  <span className="text-text-secondary">Stage:</span> {row.stage_focus}
                                </p>
                              )}
                              {row.sector_focus && (
                                <p className="text-xs text-text-tertiary mb-1">
                                  <span className="text-text-secondary">Sector:</span> {row.sector_focus}
                                </p>
                              )}
                              {row.location && (
                                <p className="text-xs text-text-tertiary mb-3">
                                  <span className="text-text-secondary">Location:</span> {row.location}
                                </p>
                              )}
                              <div className="border-t border-border pt-3">
                                <h4 className="text-xs font-medium text-text-secondary mb-2">Analyst Note</h4>
                                <div className="text-sm text-text-primary leading-relaxed whitespace-pre-line">
                                  {row.narrative}
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
              {investors.length === 0 && (
                <p className="text-center text-text-tertiary py-8">
                  No ranked investors yet. Click "Score All Investors" to start.
                </p>
              )}
            </div>

            {/* Pagination */}
            {pages > 1 && (
              <div className="flex items-center justify-center gap-2 mt-6">
                {page > 1 && (
                  <button
                    onClick={() => setPage(page - 1)}
                    className="px-4 py-2 text-sm border border-border rounded text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
                  >
                    Previous
                  </button>
                )}
                <span className="text-sm text-text-tertiary px-3">
                  Page {page} of {pages}
                </span>
                {page < pages && (
                  <button
                    onClick={() => setPage(page + 1)}
                    className="px-4 py-2 text-sm border border-border rounded text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
                  >
                    Next
                  </button>
                )}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add admin/app/investors/rankings/page.tsx
git commit -m "feat(investor-rankings): add admin rankings page with batch controls and sortable table"
```

---

### Task 7: Add Tab Navigation to Existing Investors Page

**Files:**
- Modify: `admin/app/investors/page.tsx`

- [ ] **Step 1: Add tab navigation links to the investors page header**

In `admin/app/investors/page.tsx`, add `import Link from "next/link";` to the imports.

Then replace the header `<div>` block (the one containing the `<h1>` and total count) with a version that includes tab navigation. Find this block around lines 125-132:

```tsx
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Investors</h1>
          <p className="text-sm text-text-secondary mt-1">
            {total.toLocaleString()} investors in database
          </p>
        </div>
      </div>
```

Replace with:

```tsx
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Investors</h1>
          <p className="text-sm text-text-secondary mt-1">
            {total.toLocaleString()} investors in database
          </p>
        </div>
        <div className="flex gap-2">
          <span className="px-4 py-2 text-sm bg-accent text-white rounded">
            Investors
          </span>
          <Link
            href="/investors/rankings"
            className="px-4 py-2 text-sm border border-border rounded text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
          >
            Rankings
          </Link>
        </div>
      </div>
```

- [ ] **Step 2: Commit**

```bash
git add admin/app/investors/page.tsx
git commit -m "feat(investor-rankings): add tab navigation between investors and rankings pages"
```

---

### Task 8: Deploy and Run Migration

**Files:** None (deployment commands only)

- [ ] **Step 1: Deploy to EC2**

```bash
bash deploy-ec2.sh
```

- [ ] **Step 2: Run the migration on the server**

SSH into EC2 and run:

```bash
docker compose exec backend alembic upgrade head
```

- [ ] **Step 3: Verify the admin rankings page loads**

Navigate to `https://admin.deepthesis.org/investors/rankings` and confirm:
- The "Rankings" tab is active
- The "Score All Investors" button is visible
- Tab navigation between Investors and Rankings works
- The table shows "No ranked investors yet" (expected — no batch has been run)

- [ ] **Step 4: Trigger a test batch (optional)**

Click "Score All Investors" and verify:
- The progress bar appears
- Status polls every 5 seconds
- Pause/resume works
- After a few investors score, the table populates with scores and narratives
