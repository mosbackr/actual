# Analysis Agent Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign pitch analysis agents so each of the 8 parallel Claude agents uses Anthropic's tool-use API to invoke Perplexity web search and DeepThesis database lookups dynamically, with every tool call persisted in real-time and displayed in a unified collapsible activity log on the frontend.

**Architecture:** 8 parallel Claude agents, each in a tool-use loop (Perplexity search + DB lookups). Tool calls persisted to a new `tool_calls` table as they execute. Frontend polls a new endpoint and renders a unified collapsible activity log. No hard cap on tool call iterations.

**Tech Stack:** Anthropic tool-use API, Perplexity sonar-pro, SQLAlchemy async, FastAPI, Next.js/React, PostgreSQL

---

## File Structure

**Create:**
- `backend/alembic/versions/s7t8u9v0w1x2_add_tool_calls_table.py` — Migration for `tool_calls` table
- `backend/app/models/tool_call.py` — SQLAlchemy model for tool calls
- `backend/app/services/agent_tools.py` — Tool execution functions (Perplexity, DB lookups) + tool call persistence
- `backend/app/api/tool_calls.py` — GET endpoint for polling tool calls

**Modify:**
- `backend/app/services/analysis_agents.py` — Replace pre-fetched Perplexity with tool-use loop
- `backend/app/services/analysis_worker.py` — Pass DB session factory to agents for tool call persistence
- `backend/app/api/analyze.py` — Register tool_calls router (if needed)
- `backend/app/main.py` — Register tool_calls router
- `frontend/lib/types.ts` — Add ToolCall type
- `frontend/lib/api.ts` — Add getToolCalls method
- `frontend/app/analyze/[id]/page.tsx` — Add collapsible activity log component

---

### Task 1: Database Migration — `tool_calls` Table

**Files:**
- Create: `backend/alembic/versions/s7t8u9v0w1x2_add_tool_calls_table.py`

- [ ] **Step 1: Create the migration file**

```python
"""Add tool_calls table

Revision ID: s7t8u9v0w1x2
Revises: r6s7t8u9v0w1
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "s7t8u9v0w1x2"
down_revision = "r6s7t8u9v0w1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS tool_calls (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analysis_id UUID NOT NULL REFERENCES pitch_analyses(id) ON DELETE CASCADE,
            agent_type VARCHAR(100) NOT NULL,
            tool_name VARCHAR(100) NOT NULL,
            input JSONB NOT NULL DEFAULT '{}',
            output JSONB,
            duration_ms INTEGER,
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tool_calls_analysis_id
        ON tool_calls (analysis_id)
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tool_calls_created_at
        ON tool_calls (analysis_id, created_at)
    """)


def downgrade() -> None:
    op.drop_index("ix_tool_calls_created_at", table_name="tool_calls")
    op.drop_index("ix_tool_calls_analysis_id", table_name="tool_calls")
    op.drop_table("tool_calls")
```

- [ ] **Step 2: Verify migration file is valid**

Run: `cd /Users/leemosbacker/acutal/backend && python -c "import alembic; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/s7t8u9v0w1x2_add_tool_calls_table.py
git commit -m "feat(analysis): add tool_calls migration for agent tool-use tracking"
```

---

### Task 2: ToolCall SQLAlchemy Model

**Files:**
- Create: `backend/app/models/tool_call.py`

- [ ] **Step 1: Create the model file**

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pitch_analyses.id", ondelete="CASCADE"), nullable=False
    )
    agent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    input: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 2: Verify model imports cleanly**

Run: `cd /Users/leemosbacker/acutal/backend && python -c "from app.models.tool_call import ToolCall; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/tool_call.py
git commit -m "feat(analysis): add ToolCall SQLAlchemy model"
```

---

### Task 3: Agent Tools — Execution & Persistence

**Files:**
- Create: `backend/app/services/agent_tools.py`

This file contains:
1. Tool definitions for the Anthropic API (the JSON schema Claude sees)
2. Tool execution functions (Perplexity, DB queries)
3. A `persist_tool_call` helper that saves each call to the database

- [ ] **Step 1: Create agent_tools.py with tool definitions and execution**

```python
import json
import logging
import time
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.pitch_analysis import AgentType, AnalysisReport, PitchAnalysis
from app.models.startup import Startup
from app.models.expert import ExpertProfile, ApplicationStatus
from app.models.tool_call import ToolCall

logger = logging.getLogger(__name__)

# ── Tool definitions for Anthropic API ────────────────────────────────

AGENT_TOOLS = [
    {
        "name": "perplexity_search",
        "description": (
            "Web search powered by Perplexity (sonar-pro). Has access to Crunchbase, "
            "PitchBook, and the broader web. Use for: funding history, valuations, "
            "competitor analysis, market sizing, regulatory research, recent news, "
            "team background checks, industry trends — anything that benefits from "
            "up-to-date external data. Use this aggressively to validate claims in "
            "the pitch deck."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "db_search_startups",
        "description": (
            "Search the DeepThesis startup database by name, industry, or keyword. "
            "Returns matching company profiles. Use to find comparable companies that "
            "have been previously analyzed on the platform."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term (company name, industry, or keyword)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default 10)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "db_get_analysis",
        "description": (
            "Get full analysis results (scores and report summaries) for a previously "
            "analyzed startup by its ID. Use after db_search_startups to compare the "
            "current pitch against similar companies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "startup_id": {
                    "type": "string",
                    "description": "UUID of the startup to look up",
                },
            },
            "required": ["startup_id"],
        },
    },
    {
        "name": "db_list_experts",
        "description": (
            "List approved domain experts on the DeepThesis platform with their public "
            "profile information. Use to reference relevant expert perspectives."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "industry": {
                    "type": "string",
                    "description": "Optional industry filter",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default 10)",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
]


# ── Tool execution ────────────────────────────────────────────────────

async def execute_perplexity_search(query: str) -> str:
    """Call Perplexity sonar-pro with the given query. Returns text results."""
    if not settings.perplexity_api_key:
        return "Perplexity API key not configured — web search unavailable."
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.perplexity_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar-pro",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Provide factual research data. Include specific numbers, "
                                "dates, and sources where available. You have access to "
                                "Crunchbase and PitchBook data."
                            ),
                        },
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4096,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("Perplexity search failed: %s", e)
        return f"Search failed: {e}"


async def execute_db_search_startups(query: str, limit: int, db: AsyncSession) -> str:
    """Search startups by name/description using ILIKE."""
    try:
        search_term = f"%{query}%"
        result = await db.execute(
            select(Startup)
            .where(
                (Startup.name.ilike(search_term))
                | (Startup.description.ilike(search_term))
            )
            .limit(min(limit, 20))
        )
        startups = result.scalars().all()
        if not startups:
            return "No matching startups found in the DeepThesis database."
        items = []
        for s in startups:
            items.append({
                "id": str(s.id),
                "name": s.name,
                "description": s.description[:300] if s.description else None,
                "stage": s.stage.value if hasattr(s.stage, "value") else s.stage,
                "location_city": s.location_city,
                "location_state": s.location_state,
                "location_country": s.location_country,
                "founded_date": str(s.founded_date) if s.founded_date else None,
                "ai_score": s.ai_score,
                "total_funding": s.total_funding,
                "business_model": s.business_model,
            })
        return json.dumps(items, indent=2)
    except Exception as e:
        logger.warning("DB search startups failed: %s", e)
        return f"Database search failed: {e}"


async def execute_db_get_analysis(startup_id: str, db: AsyncSession) -> str:
    """Get analysis results for a startup by its ID."""
    try:
        sid = uuid.UUID(startup_id)
    except ValueError:
        return f"Invalid startup ID: {startup_id}"
    try:
        result = await db.execute(
            select(PitchAnalysis).where(PitchAnalysis.startup_id == sid)
        )
        analysis = result.scalar_one_or_none()
        if not analysis:
            return f"No analysis found for startup {startup_id}."

        # Get reports
        report_result = await db.execute(
            select(AnalysisReport).where(AnalysisReport.analysis_id == analysis.id)
        )
        reports = report_result.scalars().all()

        data = {
            "overall_score": analysis.overall_score,
            "fundraising_likelihood": analysis.fundraising_likelihood,
            "recommended_raise": analysis.recommended_raise,
            "exit_likelihood": analysis.exit_likelihood,
            "expected_exit_value": analysis.expected_exit_value,
            "executive_summary": analysis.executive_summary,
            "reports": [
                {
                    "agent_type": r.agent_type.value if hasattr(r.agent_type, "value") else r.agent_type,
                    "score": r.score,
                    "summary": r.summary,
                }
                for r in reports
                if r.status.value == "complete" if hasattr(r.status, "value") else r.status == "complete"
            ],
        }
        return json.dumps(data, indent=2)
    except Exception as e:
        logger.warning("DB get analysis failed: %s", e)
        return f"Database lookup failed: {e}"


async def execute_db_list_experts(industry: str | None, limit: int, db: AsyncSession) -> str:
    """List approved experts, optionally filtered by industry."""
    try:
        query = select(ExpertProfile).where(
            ExpertProfile.application_status == ApplicationStatus.approved
        )
        result = await db.execute(query.limit(min(limit, 20)))
        experts = result.scalars().all()
        if not experts:
            return "No approved experts found."
        items = []
        for e in experts:
            user = e.user
            items.append({
                "name": user.name if user else "Unknown",
                "bio": e.bio[:300] if e.bio else None,
                "years_experience": e.years_experience,
                "industries": [ind.name for ind in e.industries] if e.industries else [],
                "skills": [sk.name for sk in e.skills] if e.skills else [],
            })
        return json.dumps(items, indent=2)
    except Exception as e:
        logger.warning("DB list experts failed: %s", e)
        return f"Database lookup failed: {e}"


# ── Tool dispatch ─────────────────────────────────────────────────────

async def execute_tool(
    tool_name: str,
    tool_input: dict,
    analysis_id: uuid.UUID,
    agent_type: str,
    db: AsyncSession,
) -> str:
    """Execute a tool call, persist it to the database, and return the result string."""
    start = time.monotonic()

    if tool_name == "perplexity_search":
        result_text = await execute_perplexity_search(tool_input["query"])
    elif tool_name == "db_search_startups":
        result_text = await execute_db_search_startups(
            tool_input["query"], tool_input.get("limit", 10), db
        )
    elif tool_name == "db_get_analysis":
        result_text = await execute_db_get_analysis(tool_input["startup_id"], db)
    elif tool_name == "db_list_experts":
        result_text = await execute_db_list_experts(
            tool_input.get("industry"), tool_input.get("limit", 10), db
        )
    else:
        result_text = f"Unknown tool: {tool_name}"

    duration_ms = int((time.monotonic() - start) * 1000)

    # Persist the tool call
    tool_call = ToolCall(
        analysis_id=analysis_id,
        agent_type=agent_type,
        tool_name=tool_name,
        input=tool_input,
        output={"result": result_text[:10000]},  # cap storage at 10k chars
        duration_ms=duration_ms,
    )
    db.add(tool_call)
    await db.commit()

    return result_text
```

- [ ] **Step 2: Verify imports**

Run: `cd /Users/leemosbacker/acutal/backend && python -c "from app.services.agent_tools import AGENT_TOOLS, execute_tool; print(len(AGENT_TOOLS), 'tools defined')"`
Expected: `4 tools defined`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/agent_tools.py
git commit -m "feat(analysis): add agent tool definitions and execution functions"
```

---

### Task 4: Rewrite `analysis_agents.py` — Tool-Use Loop

**Files:**
- Modify: `backend/app/services/analysis_agents.py`

This replaces the entire file. The key changes:
- Remove `PERPLEXITY_QUERIES` and `_research_with_perplexity()`
- Replace `run_agent()` with a tool-use conversation loop
- Update system prompts to reference tools instead of "provided research context"
- `run_final_scoring()` stays almost identical

- [ ] **Step 1: Rewrite analysis_agents.py**

Replace the entire file with:

```python
import json
import logging
import uuid
from datetime import datetime

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.pitch_analysis import AgentType
from app.services.agent_tools import AGENT_TOOLS, execute_tool

logger = logging.getLogger(__name__)

AGENT_LABELS = {
    AgentType.problem_solution: "Problem & Solution",
    AgentType.market_tam: "Market & TAM",
    AgentType.traction: "Traction",
    AgentType.technology_ip: "Technology & IP",
    AgentType.competition_moat: "Competition & Moat",
    AgentType.team: "Team",
    AgentType.gtm_business_model: "GTM & Business Model",
    AgentType.financials_fundraising: "Financials & Fundraising",
}

AGENT_PROMPTS: dict[AgentType, str] = {
    AgentType.problem_solution: """You are a venture capital analyst evaluating a startup's Problem & Solution.

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools aggressively to validate claims in the pitch deck, find comparable companies, and research market conditions.

EVALUATION RUBRIC (score 0-100):

**Problem Clarity (25 points)**
- Is the problem clearly articulated with specific examples?
- Is it a real pain point or a manufactured one?
- Who suffers from this problem and how severely?
- Is this a "vitamin" (nice to have) or "painkiller" (must have)?

**Problem Validation (25 points)**
- Is there evidence the problem exists at scale (data, surveys, market research)?
- Are existing solutions inadequate? Why?
- Is the timing right — why now?

**Solution Fit (25 points)**
- Does the solution directly address the stated problem?
- Is it 10x better than alternatives, or just incrementally better?
- Is the solution technically feasible with current technology?
- Is it a solution looking for a problem?

**Differentiation (25 points)**
- What makes this solution unique?
- Could a competitor replicate this in 6 months?
- Is there a novel insight or approach?

Be skeptical. Flag vague problem statements, solutions that don't match the problem, and claims without evidence. Cite specific passages from the documents.""",

    AgentType.market_tam: """You are a venture capital analyst evaluating Market Size & TAM.

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools to independently research and verify market size claims.

EVALUATION RUBRIC (score 0-100):

**Market Size Accuracy (30 points)**
- Are TAM/SAM/SOM figures cited with credible sources?
- Is the methodology bottom-up (preferred) or top-down?
- Are the numbers realistic or aspirationally inflated?
- Cross-check: does independent research support their claims?

**Market Growth (20 points)**
- Is this a growing market? What's the CAGR?
- Are there secular tailwinds driving growth?
- Could regulatory changes affect the market?

**Market Timing (25 points)**
- Why is now the right time for this product?
- Are there recent catalysts (regulatory, technological, behavioral)?
- Is the market too early or too late?

**Addressable Reality (25 points)**
- Is the SAM realistic given their go-to-market strategy?
- Can they actually reach their claimed customers?
- Are there geographic, regulatory, or structural barriers?

You MUST independently research market size using your Perplexity search tool. Compare their claims against third-party data. Flag markets that are smaller than claimed or markets with declining growth.""",

    AgentType.traction: """You are a venture capital analyst evaluating Traction & Metrics.

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools to verify claims and find comparable benchmarks.

EVALUATION RUBRIC (score 0-100):

**Revenue & Users (30 points)**
- What is current ARR/MRR? Revenue run rate?
- User count — DAU/MAU/total? Engagement depth?
- Are these paying customers or free users?
- For pre-revenue: what validation exists (LOIs, pilots, waitlists)?

**Growth Rate (25 points)**
- Month-over-month or year-over-year growth rate?
- Is growth accelerating or decelerating?
- How does growth compare to stage-appropriate benchmarks?
  - Pre-seed: any validated interest
  - Seed: 15-30% MoM growth or strong pilot results
  - Series A: $1-2M ARR with consistent growth

**Retention & Engagement (25 points)**
- What are retention/churn metrics?
- Net revenue retention for SaaS?
- Are users coming back organically?
- Cohort analysis signals?

**Vanity Metrics Check (20 points)**
- Flag: downloads without engagement, GMV without revenue, "users" without activity
- Flag: cherry-picked time periods, misleading charts
- Flag: one-time spikes presented as trends

Be tough on vanity metrics. If they report downloads, ask about active users. If they report GMV, ask about take rate. Score pre-revenue startups on validation quality, not zero.""",

    AgentType.technology_ip: """You are a skeptical technical analyst evaluating Technology & IP.

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools to verify technical claims, check patents, and assess feasibility.

EVALUATION RUBRIC (score 0-100):

**Technical Feasibility (30 points)**
- Are the technical claims achievable with current technology?
- Does the approach align with scientific consensus?
- Are there fundamental physics/math/CS limitations they're ignoring?
- Flag pseudoscience, perpetual motion, and "quantum" buzzword abuse

**Technical Depth (20 points)**
- Does the team demonstrate genuine technical understanding?
- Is the architecture described in sufficient detail?
- Are they using appropriate technologies for the problem?

**Defensibility (25 points)**
- Any patents filed or granted?
- Is the technology easily replicable by well-funded competitors?
- Is there a proprietary dataset, algorithm, or process?
- How long would it take a competent team to rebuild this?

**Technical Risk (25 points)**
- What are the key technical risks?
- Has the core technology been proven (even at small scale)?
- Are there dependencies on unproven technologies?
- Infrastructure and scaling considerations?

Be scientifically rigorous. If they claim AI/ML, ask what's novel vs. fine-tuning an existing model. If they claim blockchain, ask why a database won't work. Flag any claims that contradict established science.""",

    AgentType.competition_moat: """You are a venture capital analyst evaluating Competition & Moat.

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools aggressively to identify ALL competitors — especially ones the startup may have omitted.

EVALUATION RUBRIC (score 0-100):

**Competitive Landscape (30 points)**
- Who are the direct competitors? Indirect competitors?
- What are competitors' strengths and weaknesses?
- Are there competitors the startup didn't mention?
- Market share distribution — is this winner-take-all or fragmented?

**Competitive Advantage (25 points)**
- What is genuinely different about this startup vs. competitors?
- Is the advantage sustainable or temporary?
- Could a competitor with 10x resources replicate this in 12 months?

**Moat Analysis (25 points)**
- Network effects: does the product get better with more users?
- Switching costs: how hard is it for customers to leave?
- Data moat: do they accumulate proprietary data over time?
- Brand moat: is there meaningful brand loyalty?
- Regulatory moat: are there licensing/compliance barriers?

**Incumbent Threat (20 points)**
- Could Google/Amazon/Microsoft/Apple enter this space?
- Are there well-funded startups already ahead?
- What's the risk of a fast-follower with better distribution?

You MUST independently research competitors using your Perplexity search tool. Identify competitors the startup may have omitted. Be especially skeptical of claims like "no direct competitors" — there are always alternatives.""",

    AgentType.team: """You are a venture capital analyst evaluating the founding Team.

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools to research founders' backgrounds, previous companies, and track records.

EVALUATION RUBRIC (score 0-100):

**Founder-Market Fit (30 points)**
- Do the founders have domain expertise in this market?
- Have they experienced the problem they're solving?
- Is there a credible "why us" story?

**Track Record (25 points)**
- Previous startup experience? Exits?
- Relevant industry experience and tenure?
- Technical depth appropriate for the product?
- Notable achievements or recognition?

**Team Composition (25 points)**
- Is there a balanced team (technical + business)?
- Are key roles filled (CEO, CTO, sales/marketing)?
- What critical gaps exist in the team?
- Quality and relevance of advisors/board?

**Execution Signals (20 points)**
- Speed of progress relative to funding and team size?
- Quality of materials and communication?
- Evidence of ability to recruit talent?
- References or endorsements from credible people?

You MUST research founders' backgrounds using your Perplexity search tool. Look up LinkedIn profiles, previous companies, and any public information. Be skeptical of inflated titles and vague experience claims. Flag single-founder risk and teams with no industry experience.""",

    AgentType.gtm_business_model: """You are a venture capital analyst evaluating GTM Strategy & Business Model.

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools to verify pricing, benchmark unit economics, and assess GTM viability.

EVALUATION RUBRIC (score 0-100):

**Business Model Viability (25 points)**
- Is the revenue model clear (SaaS, marketplace, transactional, etc.)?
- What is the pricing strategy? Is it market-appropriate?
- What are gross margins? Are they improving over time?
- Is the business model proven in this category?

**Unit Economics (25 points)**
- What is CAC (Customer Acquisition Cost)?
- What is LTV (Lifetime Value)?
- LTV:CAC ratio (benchmark: >3x for SaaS)?
- Payback period on customer acquisition?
- If pre-revenue: are projected unit economics realistic?

**Go-to-Market Strategy (25 points)**
- What are the primary customer acquisition channels?
- Is the GTM strategy appropriate for the target customer?
- Is there a clear sales motion (self-serve, inside sales, enterprise)?
- What is the current pipeline or funnel?

**Scalability (25 points)**
- Can customer acquisition scale without proportional cost increase?
- Are there channel partnerships or distribution advantages?
- Is there a viral or organic growth component?
- What are the key bottlenecks to scaling?

Be skeptical of "we'll go viral" as a GTM strategy. Flag unrealistic unit economics (e.g., $5 CAC for enterprise SaaS). Check if the GTM matches the target customer (don't sell enterprise via Instagram ads).""",

    AgentType.financials_fundraising: """You are a venture capital analyst evaluating Financials & Fundraising Viability.

You have access to Perplexity web search (which can query Crunchbase, PitchBook, and the open web) and the DeepThesis startup database. Use your tools to benchmark fundraising, check comparable deals, and verify financial claims.

EVALUATION RUBRIC (score 0-100):

**Financial Projections (25 points)**
- Are revenue projections grounded in realistic assumptions?
- Is the growth rate achievable given the GTM strategy?
- Are cost projections reasonable (especially hiring plan)?
- How does burn rate relate to milestones?

**Fundraising Assessment (25 points)**
- How much are they raising? Is it appropriate for the stage?
- What milestones will the raise fund?
- Is the implied valuation reasonable for the stage and traction?
- Use of funds breakdown — is it sensible?

**Regional Fundraising Reality (25 points)**
- How does their location affect fundraising prospects?
- Is there a strong local VC ecosystem for their vertical?
- Remote-friendly or location-dependent business?
- State-specific considerations (regulatory, tax, talent pool)?

**Exit Potential (25 points)**
- Who are potential acquirers?
- What are comparable exits in this space (companies, multiples)?
- Is this a venture-scale outcome ($100M+ exit potential)?
- What is a realistic exit timeline?
- IPO path or acquisition path?

Benchmark their raise against stage norms: Pre-seed ($250K-$2M), Seed ($1-5M), Series A ($5-20M). Flag unrealistic valuations. For exit analysis, cite specific comparable transactions where possible.""",
}

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 100},
        "summary": {"type": "string"},
        "report": {"type": "string"},
        "key_findings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "summary", "report", "key_findings"],
}


async def run_agent(
    agent_type: AgentType,
    consolidated_text: str,
    company_name: str,
    analysis_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """Run a single agent in a tool-use loop until it produces a final report."""
    system_prompt = AGENT_PROMPTS[agent_type]

    user_message = f"""# Company: {company_name}

## Uploaded Documents
{consolidated_text}

---

First, use your tools to research this company — validate their claims, find competitors, check market data, look up founders, etc. Be thorough.

Then, once you have enough information, provide your final evaluation as JSON with these fields:
- "score": number 0-100 based on the rubric
- "summary": one paragraph verdict (2-3 sentences)
- "report": detailed markdown report (500-1500 words) with sections matching the rubric
- "key_findings": array of 3-5 key findings as short strings

Return ONLY valid JSON when you're ready to submit your final evaluation, no markdown fencing."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    messages = [{"role": "user", "content": user_message}]

    for attempt in range(2):
        try:
            # Tool-use conversation loop
            while True:
                response = await client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=4096,
                    system=system_prompt,
                    messages=messages,
                    tools=AGENT_TOOLS,
                )

                # Check if Claude wants to use tools
                if response.stop_reason == "tool_use":
                    # Process all tool calls in this response
                    assistant_content = response.content
                    tool_results = []

                    for block in assistant_content:
                        if block.type == "tool_use":
                            result_text = await execute_tool(
                                tool_name=block.name,
                                tool_input=block.input,
                                analysis_id=analysis_id,
                                agent_type=agent_type.value,
                                db=db,
                            )
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_text,
                            })

                    # Add assistant message and tool results to conversation
                    messages.append({"role": "assistant", "content": assistant_content})
                    messages.append({"role": "user", "content": tool_results})
                    continue

                # Claude is done — extract the final text response
                text_content = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text_content += block.text

                text_content = text_content.strip()
                if text_content.startswith("```"):
                    text_content = text_content.split("\n", 1)[1]
                    if text_content.endswith("```"):
                        text_content = text_content[:-3]
                    text_content = text_content.strip()

                result = json.loads(text_content)
                return {
                    "score": max(0, min(100, float(result["score"]))),
                    "summary": str(result["summary"]),
                    "report": str(result["report"]),
                    "key_findings": [str(f) for f in result.get("key_findings", [])],
                }

        except Exception as e:
            if attempt == 0:
                logger.warning("Agent %s attempt 1 failed: %s, retrying...", agent_type.value, e)
                messages = [{"role": "user", "content": user_message}]
                continue
            raise

    raise RuntimeError(f"Agent {agent_type.value} failed after 2 attempts")


async def run_final_scoring(reports: list[dict], company_name: str) -> dict:
    """Synthesize all agent reports into a final score. No tools needed."""
    reports_text = ""
    for r in reports:
        reports_text += f"\n\n## {AGENT_LABELS.get(AgentType(r['agent_type']), r['agent_type'])}\n"
        reports_text += f"**Score:** {r['score']}/100\n"
        reports_text += f"**Summary:** {r['summary']}\n"
        reports_text += f"**Key Findings:** {', '.join(r.get('key_findings', []))}\n"

    system_prompt = """You are a senior venture capital partner synthesizing multiple analyst reports into a final investment assessment.

Your job is to weigh all 8 analyst evaluations and produce:
1. An overall score (weighted average, but use judgment — a critical failure in one area can override high scores elsewhere)
2. Fundraising likelihood — realistic probability this company can successfully raise their next round
3. Recommended raise amount based on stage, traction, and market
4. Exit likelihood — probability of a meaningful exit (acquisition or IPO)
5. Expected exit value — realistic range based on comparable transactions
6. Expected exit timeline — years to exit based on market and stage
7. Executive summary — one paragraph capturing the investment thesis or key concerns

Be calibrated: most startups score 30-60. Only exceptional startups score above 75. Below 25 indicates fundamental problems."""

    user_message = f"""# Company: {company_name}

## Analyst Reports
{reports_text}

---

Synthesize these reports and return JSON with these fields:
- "overall_score": number 0-100
- "fundraising_likelihood": number 0-100 (probability of successful raise)
- "recommended_raise": string like "$2-3M" or "$500K-1M"
- "exit_likelihood": number 0-100
- "expected_exit_value": string like "$50-100M" or "$500M-1B"
- "expected_exit_timeline": string like "5-7 years" or "3-5 years"
- "executive_summary": one paragraph (3-5 sentences)

Return ONLY valid JSON, no markdown fencing."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    content = response.content[0].text.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    result = json.loads(content)
    return {
        "overall_score": max(0, min(100, float(result["overall_score"]))),
        "fundraising_likelihood": max(0, min(100, float(result["fundraising_likelihood"]))),
        "recommended_raise": str(result["recommended_raise"]),
        "exit_likelihood": max(0, min(100, float(result["exit_likelihood"]))),
        "expected_exit_value": str(result["expected_exit_value"]),
        "expected_exit_timeline": str(result["expected_exit_timeline"]),
        "executive_summary": str(result["executive_summary"]),
    }
```

- [ ] **Step 2: Verify imports**

Run: `cd /Users/leemosbacker/acutal/backend && python -c "from app.services.analysis_agents import run_agent, run_final_scoring, AGENT_LABELS; print(len(AGENT_LABELS), 'agents')"`
Expected: `8 agents`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/analysis_agents.py
git commit -m "feat(analysis): rewrite agents with Anthropic tool-use loop"
```

---

### Task 5: Update `analysis_worker.py` — Pass DB Session to Agents

**Files:**
- Modify: `backend/app/services/analysis_worker.py:78-142`

The worker's `_run_single_agent` function needs to pass a DB session to `run_agent()` so agents can execute DB tool calls and persist tool calls.

- [ ] **Step 1: Update the import**

In `backend/app/services/analysis_worker.py`, the import on line 22 already imports `run_agent`. No change needed there. But we need to update `_run_single_agent` to pass `analysis_id` and a DB session to `run_agent`.

Replace lines 78-142 (the `_run_single_agent` function) with:

```python
async def _run_single_agent(
    db_factory,
    analysis_id: uuid.UUID,
    agent_type: AgentType,
    consolidated_text: str,
    company_name: str,
) -> dict | None:
    async with db_factory() as db:
        # Mark report as running
        result = await db.execute(
            select(AnalysisReport).where(
                AnalysisReport.analysis_id == analysis_id,
                AnalysisReport.agent_type == agent_type,
            )
        )
        report = result.scalar_one()
        report.status = ReportStatus.running
        report.started_at = datetime.now(timezone.utc)
        await db.commit()

        # Update current_agent on analysis
        await db.execute(
            update(PitchAnalysis)
            .where(PitchAnalysis.id == analysis_id)
            .values(current_agent=agent_type.value)
        )
        await db.commit()

    try:
        # Run agent with its own DB session for tool call persistence
        async with db_factory() as db:
            agent_result = await run_agent(
                agent_type, consolidated_text, company_name, analysis_id, db
            )

        async with db_factory() as db:
            result = await db.execute(
                select(AnalysisReport).where(
                    AnalysisReport.analysis_id == analysis_id,
                    AnalysisReport.agent_type == agent_type,
                )
            )
            report = result.scalar_one()
            report.status = ReportStatus.complete
            report.score = agent_result["score"]
            report.summary = agent_result["summary"]
            report.report = agent_result["report"]
            report.key_findings = agent_result["key_findings"]
            report.completed_at = datetime.now(timezone.utc)
            await db.commit()

        logger.info(f"Agent {agent_type.value} complete: score={agent_result['score']}")
        return {"agent_type": agent_type.value, **agent_result}

    except Exception as e:
        logger.error(f"Agent {agent_type.value} failed: {e}")
        async with db_factory() as db:
            result = await db.execute(
                select(AnalysisReport).where(
                    AnalysisReport.analysis_id == analysis_id,
                    AnalysisReport.agent_type == agent_type,
                )
            )
            report = result.scalar_one()
            report.status = ReportStatus.failed
            report.error = str(e)
            report.completed_at = datetime.now(timezone.utc)
            await db.commit()
        return None
```

- [ ] **Step 2: Verify the worker module loads**

Run: `cd /Users/leemosbacker/acutal/backend && python -c "from app.services.analysis_worker import _run_single_agent; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/analysis_worker.py
git commit -m "feat(analysis): pass DB session to agents for tool-use persistence"
```

---

### Task 6: Tool Calls API Endpoint

**Files:**
- Create: `backend/app/api/tool_calls.py`
- Modify: `backend/app/main.py` (add router)

- [ ] **Step 1: Create the tool calls API endpoint**

```python
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.pitch_analysis import PitchAnalysis
from app.models.tool_call import ToolCall
from app.models.user import User

router = APIRouter()


@router.get("/api/analyze/{analysis_id}/tool-calls")
async def get_tool_calls(
    analysis_id: uuid.UUID,
    since: datetime | None = Query(None, description="Only return tool calls after this timestamp"),
    include_output: bool = Query(False, description="Include full output in response"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify user owns this analysis
    result = await db.execute(
        select(PitchAnalysis).where(
            PitchAnalysis.id == analysis_id,
            PitchAnalysis.user_id == user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Analysis not found")

    query = select(ToolCall).where(
        ToolCall.analysis_id == analysis_id
    ).order_by(ToolCall.created_at.asc())

    if since:
        query = query.where(ToolCall.created_at > since)

    result = await db.execute(query)
    tool_calls = result.scalars().all()

    items = []
    for tc in tool_calls:
        item = {
            "id": str(tc.id),
            "agent_type": tc.agent_type,
            "tool_name": tc.tool_name,
            "input": tc.input,
            "created_at": tc.created_at.isoformat() if tc.created_at else None,
            "duration_ms": tc.duration_ms,
        }
        if include_output:
            item["output"] = tc.output
        items.append(item)

    return {"tool_calls": items}
```

- [ ] **Step 2: Register the router in main.py**

Find the section in `backend/app/main.py` where routers are included (look for `app.include_router` lines) and add:

```python
from app.api.tool_calls import router as tool_calls_router
app.include_router(tool_calls_router)
```

- [ ] **Step 3: Verify the endpoint registers**

Run: `cd /Users/leemosbacker/acutal/backend && python -c "from app.api.tool_calls import router; print(len(router.routes), 'routes')"`
Expected: `1 routes`

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/tool_calls.py backend/app/main.py
git commit -m "feat(analysis): add GET /api/analyze/{id}/tool-calls endpoint"
```

---

### Task 7: Frontend Types & API Method

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add ToolCall type to types.ts**

Add after the `AnalysisReportFull` interface (after line 178):

```typescript
export interface ToolCallItem {
  id: string;
  agent_type: string;
  tool_name: string;
  input: Record<string, unknown>;
  output?: Record<string, unknown>;
  created_at: string | null;
  duration_ms: number | null;
}
```

- [ ] **Step 2: Add getToolCalls method to api.ts**

Add in the analysis methods section (after the `resubmitAnalysis` method, around line 163):

```typescript
  getToolCalls: (token: string, id: string, since?: string) => {
    const params = new URLSearchParams();
    if (since) params.set("since", since);
    const qs = params.toString();
    return apiFetch<{ tool_calls: import("./types").ToolCallItem[] }>(
      `/api/analyze/${id}/tool-calls${qs ? `?${qs}` : ""}`,
      { headers: authHeaders(token) }
    );
  },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat(analysis): add ToolCall type and getToolCalls API method"
```

---

### Task 8: Frontend — Collapsible Activity Log

**Files:**
- Modify: `frontend/app/analyze/[id]/page.tsx`

This adds:
1. State for tool calls + polling
2. A collapsible `ActivityLog` component
3. The log rendered on the page (both during running and after completion)

- [ ] **Step 1: Add imports and state**

Add `useRef` to the React imports on line 5:

```typescript
import { useCallback, useEffect, useRef, useState } from "react";
```

Add the `ToolCallItem` import to the existing type imports on line 9:

```typescript
import type { AnalysisDetail, AnalysisReportFull, InvestmentMemo, ToolCallItem } from "@/lib/types";
```

- [ ] **Step 2: Add tool call state and polling**

Inside the `AnalysisResultPage` component, after the `memoLoading` state (line 54), add:

```typescript
  const [toolCalls, setToolCalls] = useState<ToolCallItem[]>([]);
  const [logOpen, setLogOpen] = useState(false);
```

After the `fetchMemo` callback (after line 81), add:

```typescript
  const lastToolCallTs = useRef<string | undefined>(undefined);

  const fetchToolCalls = useCallback(async () => {
    if (!token || !id) return;
    try {
      const data = await api.getToolCalls(token, id, lastToolCallTs.current);
      if (data.tool_calls.length > 0) {
        const newest = data.tool_calls[data.tool_calls.length - 1];
        if (newest.created_at) lastToolCallTs.current = newest.created_at;
        setToolCalls((prev) => {
          const existingIds = new Set(prev.map((tc) => tc.id));
          const newCalls = data.tool_calls.filter((tc) => !existingIds.has(tc.id));
          return [...prev, ...newCalls];
        });
      }
    } catch {
      // silent
    }
  }, [token, id]);
```

Add the `fetchToolCalls` to the initial load effect (the `useEffect` on line 83-86) by adding `fetchToolCalls();` inside it.

Add a polling effect for tool calls after the memo polling effect (after line 101):

```typescript
  // Poll tool calls while analysis is running
  useEffect(() => {
    if (!analysis) return;
    if (analysis.status === "complete" || analysis.status === "failed") {
      // Fetch one last time to get any remaining tool calls
      fetchToolCalls();
      return;
    }
    const timer = setInterval(fetchToolCalls, 3000);
    return () => clearInterval(timer);
  }, [analysis?.status, fetchToolCalls]);
```

- [ ] **Step 3: Create the ActivityLog component**

Add this component before the `AnalysisResultPage` function (after `StatusIcon`, around line 39):

```typescript
const TOOL_LABELS: Record<string, string> = {
  perplexity_search: "Perplexity Search",
  db_search_startups: "DB: Startups",
  db_get_analysis: "DB: Analysis",
  db_list_experts: "DB: Experts",
};

const AGENT_COLORS: Record<string, string> = {
  problem_solution: "bg-blue-100 text-blue-700",
  market_tam: "bg-emerald-100 text-emerald-700",
  traction: "bg-amber-100 text-amber-700",
  technology_ip: "bg-purple-100 text-purple-700",
  competition_moat: "bg-red-100 text-red-700",
  team: "bg-cyan-100 text-cyan-700",
  gtm_business_model: "bg-orange-100 text-orange-700",
  financials_fundraising: "bg-pink-100 text-pink-700",
};

function ActivityLog({ toolCalls, open, onToggle }: { toolCalls: ToolCallItem[]; open: boolean; onToggle: () => void }) {
  if (toolCalls.length === 0) return null;

  return (
    <div className="mt-6 rounded border border-border bg-surface">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-text-primary hover:bg-bg-secondary/50 transition"
      >
        <span>Activity Log ({toolCalls.length} tool calls)</span>
        <span className="text-text-tertiary text-xs">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="border-t border-border max-h-96 overflow-y-auto divide-y divide-border">
          {toolCalls.map((tc) => (
            <ToolCallEntry key={tc.id} tc={tc} />
          ))}
        </div>
      )}
    </div>
  );
}

function ToolCallEntry({ tc }: { tc: ToolCallItem }) {
  const [expanded, setExpanded] = useState(false);
  const agentLabel = AGENT_LABELS[tc.agent_type] || tc.agent_type;
  const toolLabel = TOOL_LABELS[tc.tool_name] || tc.tool_name;
  const agentColor = AGENT_COLORS[tc.agent_type] || "bg-gray-100 text-gray-700";
  const queryText = tc.input?.query as string || JSON.stringify(tc.input);

  return (
    <div className="px-4 py-2.5">
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${agentColor}`}>
          {agentLabel}
        </span>
        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-border text-text-secondary">
          {toolLabel}
        </span>
        <span className="text-xs text-text-tertiary font-mono truncate max-w-xs" title={queryText}>
          {queryText}
        </span>
        <span className="ml-auto text-[10px] text-text-tertiary tabular-nums">
          {tc.duration_ms != null ? `${(tc.duration_ms / 1000).toFixed(1)}s` : ""}
        </span>
      </div>
      {tc.output && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-[10px] text-accent hover:text-accent-hover mt-1"
        >
          {expanded ? "Hide output" : "Show output"}
        </button>
      )}
      {expanded && tc.output && (
        <pre className="mt-1 text-[10px] text-text-tertiary bg-bg-secondary rounded p-2 max-h-40 overflow-y-auto whitespace-pre-wrap">
          {typeof tc.output === "object" ? JSON.stringify(tc.output, null, 2) : String(tc.output)}
        </pre>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Add ActivityLog to the running view**

In the running/progress view (around line 188, before the closing `</div>` of the `isRunning` block), add:

```tsx
        <ActivityLog toolCalls={toolCalls} open={logOpen} onToggle={() => setLogOpen(!logOpen)} />
```

- [ ] **Step 5: Add ActivityLog to the results view**

In the results/complete view, add the ActivityLog at the end of the component (before the final closing `</div>` of the return, around line 442):

```tsx
      {/* Activity Log */}
      <ActivityLog toolCalls={toolCalls} open={logOpen} onToggle={() => setLogOpen(!logOpen)} />
```

- [ ] **Step 6: Commit**

```bash
git add frontend/app/analyze/[id]/page.tsx
git commit -m "feat(analysis): add collapsible activity log for real-time tool calls"
```

---

### Task 9: Register ToolCall Model in Imports

**Files:**
- Check: `backend/app/models/__init__.py` or wherever models are imported for Alembic

- [ ] **Step 1: Check how models are imported**

Look at `backend/app/models/__init__.py` to see if models need to be explicitly imported. If there's an `__init__.py` that imports all models, add the ToolCall import there. If models are discovered via Base.metadata, the import in `agent_tools.py` handles it.

If `__init__.py` has imports like:
```python
from app.models.pitch_analysis import *
from app.models.investment_memo import *
```

Then add:
```python
from app.models.tool_call import *
```

- [ ] **Step 2: Verify all models load**

Run: `cd /Users/leemosbacker/acutal/backend && python -c "from app.models.tool_call import ToolCall; print(ToolCall.__tablename__)"`
Expected: `tool_calls`

- [ ] **Step 3: Commit (if changes were made)**

```bash
git add backend/app/models/__init__.py
git commit -m "feat(analysis): register ToolCall model in models init"
```

---

### Task 10: Integration Testing — End to End

**Files:**
- No new files — manual verification

- [ ] **Step 1: Verify migration runs**

On the deployment target (EC2), run:
```bash
cd /path/to/backend && python -m alembic upgrade head
```
Expected: Migration applies, `tool_calls` table created.

- [ ] **Step 2: Verify backend starts without errors**

```bash
docker compose -f docker-compose.prod.yml up backend --build
```
Check logs for import errors or startup failures.

- [ ] **Step 3: Verify analysis worker starts**

```bash
docker compose -f docker-compose.prod.yml up analysis_worker --build
```
Check logs for import errors.

- [ ] **Step 4: Run a test analysis**

Upload a pitch deck through the frontend and verify:
1. Analysis starts (status changes from pending → extracting → analyzing)
2. Tool calls appear in the activity log during analysis
3. Agent reports complete with scores
4. Final scoring produces results
5. Activity log shows all tool calls after completion

- [ ] **Step 5: Verify tool calls API**

```bash
curl -H "Authorization: Bearer $TOKEN" https://deepthesis.org/api/analyze/$ANALYSIS_ID/tool-calls
```
Expected: JSON with `tool_calls` array containing entries with `agent_type`, `tool_name`, `input`, `duration_ms`.

- [ ] **Step 6: Commit any fixes**

```bash
git add -A
git commit -m "fix(analysis): integration fixes for tool-use agent redesign"
```
