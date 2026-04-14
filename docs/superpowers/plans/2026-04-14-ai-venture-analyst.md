# AI Venture Analyst Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Insights page with a Perplexity sonar-pro-powered conversational AI venture analyst with access to all internal startup data, streaming responses, inline Recharts visualizations, downloadable Word/Excel reports, conversation persistence, and shareable links.

**Architecture:** FastAPI backend streams Perplexity sonar-pro responses via SSE. Portfolio context (pre-aggregated summaries + per-company profiles) is injected into each Perplexity call. Backend extracts chart JSON blocks from completed responses. Frontend renders streaming text and Recharts visualizations. Reports generated server-side via python-docx/openpyxl with matplotlib chart images, uploaded to S3.

**Tech Stack:** Perplexity sonar-pro, FastAPI StreamingResponse (SSE), SQLAlchemy 2.0 async, Recharts 3.8.1, python-docx, openpyxl, matplotlib, react-markdown + remark-gfm

---

## File Structure

### Backend — Create

| File | Responsibility |
|------|---------------|
| `backend/app/models/analyst.py` | SQLAlchemy models: AnalystConversation, AnalystMessage, AnalystReport + enums |
| `backend/alembic/versions/<rev>_add_analyst_tables.py` | Migration for 3 new tables + 3 new enum types |
| `backend/app/services/analyst_context.py` | Portfolio summary queries, company matching, system prompt construction |
| `backend/app/services/analyst_chat.py` | Perplexity streaming API, chart extraction from response |
| `backend/app/services/analyst_reports.py` | Word/Excel report generation + S3 upload |
| `backend/app/api/analyst.py` | All analyst API endpoints (conversations, messages SSE, reports, sharing) |

### Backend — Modify

| File | Change |
|------|--------|
| `backend/app/main.py:59` | Add analyst router import + include_router |
| `backend/pyproject.toml:5-24` | Add `matplotlib>=3.9.0` dependency |

### Frontend — Create

| File | Responsibility |
|------|---------------|
| `frontend/components/analyst/AnalystChart.tsx` | Recharts wrapper — renders bar/line/pie/scatter/area from JSON config |
| `frontend/components/analyst/AnalystMessage.tsx` | Message bubble — renders markdown text + inline charts + citations |
| `frontend/components/analyst/AnalystSidebar.tsx` | Conversation history list + new conversation button + suggested analyses |
| `frontend/components/analyst/AnalystChat.tsx` | Chat container — message list, auto-scroll, streaming state |
| `frontend/components/analyst/AnalystInput.tsx` | Text input + send button + report generation dropdown |
| `frontend/components/analyst/ShareModal.tsx` | Share link dialog with copy button |
| `frontend/app/insights/shared/[token]/page.tsx` | Public read-only shared conversation view |

### Frontend — Modify

| File | Change |
|------|--------|
| `frontend/lib/types.ts` | Add analyst type interfaces |
| `frontend/lib/api.ts` | Add analyst API methods + SSE stream helper |
| `frontend/app/insights/page.tsx` | Replace with analyst page |
| `frontend/package.json` | Add `react-markdown`, `remark-gfm` |

---

### Task 1: Add Dependencies

**Files:**
- Modify: `backend/pyproject.toml:5-24`
- Modify: `frontend/package.json`

- [ ] **Step 1: Add matplotlib to backend dependencies**

In `backend/pyproject.toml`, add `matplotlib` to the dependencies list. Insert after the `openpyxl` line:

```toml
    "openpyxl>=3.1.0",
    "matplotlib>=3.9.0",
    "xlrd>=2.0.0",
```

- [ ] **Step 2: Add react-markdown and remark-gfm to frontend**

Run from the `frontend/` directory:

```bash
cd frontend && npm install react-markdown remark-gfm
```

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml frontend/package.json frontend/package-lock.json
git commit -m "deps: add matplotlib, react-markdown, remark-gfm for analyst feature"
```

---

### Task 2: Database Models

**Files:**
- Create: `backend/app/models/analyst.py`

- [ ] **Step 1: Create the analyst models file**

Create `backend/app/models/analyst.py`:

```python
import enum
import uuid as _uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM, JSON, UUID
from sqlalchemy.orm import relationship

from app.models.industry import Base


class MessageRole(enum.Enum):
    user = "user"
    assistant = "assistant"


class ReportFormat(enum.Enum):
    docx = "docx"
    xlsx = "xlsx"


class ReportGenStatus(enum.Enum):
    pending = "pending"
    generating = "generating"
    complete = "complete"
    failed = "failed"


messagerole_enum = ENUM("user", "assistant", name="messagerole", create_type=False)
reportformat_enum = ENUM("docx", "xlsx", name="reportformat", create_type=False)
reportgenstatus_enum = ENUM(
    "pending", "generating", "complete", "failed", name="reportgenstatus", create_type=False
)


class AnalystConversation(Base):
    __tablename__ = "analyst_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(500), nullable=False, server_default="New Conversation")
    share_token = Column(String(64), unique=True, nullable=True)
    is_free_conversation = Column(Boolean, nullable=False, server_default="false")
    message_count = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    messages = relationship(
        "AnalystMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AnalystMessage.created_at",
    )
    reports = relationship(
        "AnalystReport",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    user = relationship("User")


class AnalystMessage(Base):
    __tablename__ = "analyst_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("analyst_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(messagerole_enum, nullable=False)
    content = Column(Text, nullable=False)
    charts = Column(JSON, nullable=True)
    citations = Column(JSON, nullable=True)
    context_startups = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("AnalystConversation", back_populates="messages")


class AnalystReport(Base):
    __tablename__ = "analyst_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("analyst_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(500), nullable=False)
    format = Column(reportformat_enum, nullable=False)
    status = Column(reportgenstatus_enum, nullable=False, server_default="pending")
    s3_key = Column(String(1000), nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("AnalystConversation", back_populates="reports")
    user = relationship("User")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/analyst.py
git commit -m "feat(analyst): add SQLAlchemy models for conversations, messages, reports"
```

---

### Task 3: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/n2o3p4q5r6s7_add_analyst_tables.py`

- [ ] **Step 1: Check current Alembic head**

Run from the `backend/` directory:

```bash
cd backend && python -m alembic heads
```

The output should show the current head revision. Use that as `down_revision` below. If it shows `m1n2o3p4q5r6`, use that. If different, substitute accordingly.

- [ ] **Step 2: Create the migration file**

Create `backend/alembic/versions/n2o3p4q5r6s7_add_analyst_tables.py`:

```python
"""Add analyst tables

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON, ENUM

revision = "n2o3p4q5r6s7"
down_revision = "m1n2o3p4q5r6"
branch_labels = None
depends_on = None

messagerole = ENUM("user", "assistant", name="messagerole", create_type=False)
reportformat = ENUM("docx", "xlsx", name="reportformat", create_type=False)
reportgenstatus = ENUM(
    "pending", "generating", "complete", "failed", name="reportgenstatus", create_type=False
)


def upgrade() -> None:
    # Create enum types explicitly
    op.execute(
        "DO $$ BEGIN CREATE TYPE messagerole AS ENUM ('user', 'assistant'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE reportformat AS ENUM ('docx', 'xlsx'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE reportgenstatus AS ENUM ('pending', 'generating', 'complete', 'failed'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    op.create_table(
        "analyst_conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False, server_default="New Conversation"),
        sa.Column("share_token", sa.String(64), unique=True, nullable=True),
        sa.Column("is_free_conversation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "analyst_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("analyst_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", messagerole, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("charts", JSON, nullable=True),
        sa.Column("citations", JSON, nullable=True),
        sa.Column("context_startups", JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "analyst_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("analyst_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("format", reportformat, nullable=False),
        sa.Column("status", reportgenstatus, nullable=False, server_default="pending"),
        sa.Column("s3_key", sa.String(1000), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("analyst_reports")
    op.drop_table("analyst_messages")
    op.drop_table("analyst_conversations")

    op.execute("DROP TYPE IF EXISTS reportgenstatus")
    op.execute("DROP TYPE IF EXISTS reportformat")
    op.execute("DROP TYPE IF EXISTS messagerole")
```

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/n2o3p4q5r6s7_add_analyst_tables.py
git commit -m "feat(analyst): add Alembic migration for analyst tables"
```

---

### Task 4: Portfolio Context Service

**Files:**
- Create: `backend/app/services/analyst_context.py`

- [ ] **Step 1: Create the context service**

Create `backend/app/services/analyst_context.py`:

```python
"""Portfolio context injection for the AI analyst.

Provides pre-aggregated portfolio summaries and per-company profiles
to include in Perplexity system prompts.
"""

import logging
import time
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.industry import Industry
from app.models.startup import Startup, StartupStage, startup_industries

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 minutes

_portfolio_cache: dict | None = None
_portfolio_cache_time: float = 0


def _parse_funding(raw: str | None) -> float:
    """Parse a funding string like '$10M' or '$1.5B' to a float in dollars."""
    if not raw:
        return 0.0
    cleaned = raw.strip().replace(",", "").replace("$", "").upper()
    multiplier = 1.0
    if cleaned.endswith("B"):
        multiplier = 1_000_000_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith("M"):
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith("K"):
        multiplier = 1_000
        cleaned = cleaned[:-1]
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return 0.0


async def get_portfolio_summary(db: AsyncSession) -> dict:
    """Return pre-aggregated portfolio summary. Cached for 5 minutes."""
    global _portfolio_cache, _portfolio_cache_time

    now = time.time()
    if _portfolio_cache and (now - _portfolio_cache_time) < CACHE_TTL:
        return _portfolio_cache

    # Total startups
    total_result = await db.execute(select(func.count(Startup.id)))
    total = total_result.scalar() or 0

    # Stage distribution
    stage_result = await db.execute(
        select(Startup.stage, func.count(Startup.id)).group_by(Startup.stage)
    )
    stage_dist = {
        (row[0].value if hasattr(row[0], "value") else str(row[0])): row[1]
        for row in stage_result.all()
        if row[0]
    }

    # Average AI score
    avg_result = await db.execute(
        select(func.avg(Startup.ai_score)).where(Startup.ai_score.isnot(None))
    )
    avg_score = avg_result.scalar()
    avg_score = round(avg_score, 1) if avg_score else 0

    # Total funding
    all_funding = await db.execute(select(Startup.total_funding))
    total_funding = sum(_parse_funding(row[0]) for row in all_funding.all())
    if total_funding >= 1_000_000_000:
        total_funding_str = f"${total_funding / 1_000_000_000:.1f}B"
    elif total_funding >= 1_000_000:
        total_funding_str = f"${total_funding / 1_000_000:.1f}M"
    else:
        total_funding_str = f"${total_funding:,.0f}"

    # Top industries by count
    industry_result = await db.execute(
        select(Industry.name, func.count(startup_industries.c.startup_id))
        .join(startup_industries, Industry.id == startup_industries.c.industry_id)
        .group_by(Industry.name)
        .order_by(func.count(startup_industries.c.startup_id).desc())
        .limit(10)
    )
    top_industries = [{"name": row[0], "count": row[1]} for row in industry_result.all()]

    # Score distribution (buckets of 10)
    score_result = await db.execute(
        select(Startup.ai_score).where(Startup.ai_score.isnot(None))
    )
    scores = [row[0] for row in score_result.all()]
    score_buckets = defaultdict(int)
    for s in scores:
        bucket = int(s // 10) * 10
        score_buckets[f"{bucket}-{bucket + 9}"] += 1

    summary = {
        "total_startups": total,
        "stage_distribution": stage_dist,
        "avg_ai_score": avg_score,
        "total_funding": total_funding_str,
        "top_industries": top_industries,
        "score_distribution": dict(sorted(score_buckets.items())),
    }

    _portfolio_cache = summary
    _portfolio_cache_time = now
    return summary


async def find_matching_startups(
    db: AsyncSession, message: str, limit: int = 5
) -> list[dict]:
    """Find startups whose names appear in the user message."""
    result = await db.execute(select(Startup.id, Startup.name))
    all_startups = result.all()

    message_lower = message.lower()
    matched_ids = []
    for sid, name in all_startups:
        if name and len(name) > 2 and name.lower() in message_lower:
            matched_ids.append(sid)

    if not matched_ids:
        return []

    result = await db.execute(
        select(Startup)
        .where(Startup.id.in_(matched_ids))
        .options(selectinload(Startup.industries))
        .limit(limit)
    )
    startups = result.scalars().all()
    return [_startup_to_context(s) for s in startups]


async def find_startups_by_filter(
    db: AsyncSession, message: str, limit: int = 20
) -> list[dict]:
    """Find startups matching sector or stage keywords in the message."""
    message_lower = message.lower()

    # Check for stage keywords
    stage_map = {
        "pre-seed": "pre_seed", "pre seed": "pre_seed", "preseed": "pre_seed",
        "seed": "seed",
        "series a": "series_a",
        "series b": "series_b",
        "series c": "series_c",
        "growth": "growth",
        "public": "public", "ipo": "public",
    }
    matched_stage = None
    for keyword, stage_val in stage_map.items():
        if keyword in message_lower:
            matched_stage = stage_val
            break

    # Check for industry keywords
    industry_result = await db.execute(select(Industry.id, Industry.name))
    all_industries = industry_result.all()
    matched_industry_id = None
    for ind_id, ind_name in all_industries:
        if ind_name and ind_name.lower() in message_lower:
            matched_industry_id = ind_id
            break

    if not matched_stage and not matched_industry_id:
        return []

    query = select(Startup).options(selectinload(Startup.industries))
    if matched_stage:
        query = query.where(Startup.stage == matched_stage)
    if matched_industry_id:
        query = query.where(
            Startup.id.in_(
                select(startup_industries.c.startup_id).where(
                    startup_industries.c.industry_id == matched_industry_id
                )
            )
        )
    query = query.order_by(Startup.ai_score.desc().nulls_last()).limit(limit)

    result = await db.execute(query)
    startups = result.scalars().all()
    return [_startup_to_context(s) for s in startups]


def _startup_to_context(s: Startup) -> dict:
    """Convert a Startup ORM object to a context dict for the system prompt."""
    return {
        "id": str(s.id),
        "name": s.name,
        "tagline": s.tagline,
        "description": s.description,
        "stage": s.stage.value if s.stage else None,
        "ai_score": s.ai_score,
        "total_funding": s.total_funding,
        "employee_count": s.employee_count,
        "business_model": s.business_model,
        "revenue_estimate": s.revenue_estimate,
        "competitors": s.competitors,
        "tech_stack": s.tech_stack,
        "key_metrics": s.key_metrics,
        "website_url": s.website_url,
        "industries": [ind.name for ind in s.industries] if s.industries else [],
    }


def build_system_prompt(summary: dict, startup_profiles: list[dict] | None = None) -> str:
    """Build the Perplexity system prompt with injected portfolio context."""
    stage_lines = ", ".join(
        f"{stage}: {count}" for stage, count in summary["stage_distribution"].items()
    )
    industry_lines = ", ".join(
        f"{ind['name']} ({ind['count']})" for ind in summary["top_industries"][:7]
    )
    score_lines = ", ".join(
        f"{bucket}: {count}" for bucket, count in summary["score_distribution"].items()
    )

    prompt = f"""You are a senior venture analyst at Deep Thesis with a data science background.
You have access to a proprietary database of {summary['total_startups']} startups and external market intelligence via Crunchbase and PitchBook.

PORTFOLIO SUMMARY:
- {summary['total_startups']} total startups
- Stage distribution: {stage_lines}
- Average AI score: {summary['avg_ai_score']}/100
- Total tracked funding: {summary['total_funding']}
- Top sectors by count: {industry_lines}
- Score distribution: {score_lines}
"""

    if startup_profiles:
        prompt += "\nSTARTUP PROFILES (from our database):\n"
        for sp in startup_profiles:
            prompt += f"\n--- {sp['name']} ---\n"
            for key, val in sp.items():
                if key == "id" or val is None:
                    continue
                prompt += f"  {key}: {val}\n"

    prompt += """
When the user asks about specific companies in our database, their full profiles are provided above. For external companies, use your web access to research Crunchbase, PitchBook, and other sources.

Respond with analysis, not just data. Interpret trends, flag risks, compare to benchmarks. When data supports it, include a chart using this exact JSON format:

:::chart
{"type": "bar", "title": "Chart Title", "data": [{"name": "A", "value": 10}], "xKey": "name", "yKeys": ["value"], "colors": ["#6366f1"]}
:::

Valid chart types: bar, line, pie, scatter, area.
You may include multiple charts per response. Always explain what the chart shows before or after it.
For pie charts, use "nameKey" instead of "xKey" and "dataKey" instead of "yKeys".
Keep chart data arrays reasonable (under 30 items).
"""
    return prompt
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/analyst_context.py
git commit -m "feat(analyst): add portfolio context service with caching and company matching"
```

---

### Task 5: Perplexity Streaming + Chart Extraction

**Files:**
- Create: `backend/app/services/analyst_chat.py`

- [ ] **Step 1: Create the chat service**

Create `backend/app/services/analyst_chat.py`:

```python
"""Perplexity streaming chat service with chart extraction.

Streams Perplexity sonar-pro responses and extracts :::chart::: blocks
from the completed response.
"""

import json
import logging
import re
from collections.abc import AsyncGenerator

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

CHART_PATTERN = re.compile(r":::chart\s*\n?(.*?)\n?:::", re.DOTALL)

REQUIRED_CHART_KEYS = {"type", "data"}


def extract_charts(text: str) -> tuple[str, list[dict]]:
    """Extract :::chart JSON::: blocks from text.

    Returns (cleaned_text, list_of_chart_configs).
    Invalid chart JSON is silently skipped.
    """
    charts = []
    for match in CHART_PATTERN.finditer(text):
        raw = match.group(1).strip()
        try:
            chart = json.loads(raw)
            if REQUIRED_CHART_KEYS.issubset(chart.keys()):
                charts.append(chart)
            else:
                logger.warning("Chart missing required keys: %s", chart.keys())
        except json.JSONDecodeError as e:
            logger.warning("Invalid chart JSON: %s", e)

    cleaned = CHART_PATTERN.sub("", text).strip()
    # Remove double blank lines left by chart removal
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, charts


async def stream_perplexity(
    messages: list[dict],
    system_prompt: str,
) -> AsyncGenerator[dict, None]:
    """Stream a Perplexity sonar-pro response.

    Yields dicts with one of:
      {"type": "text", "chunk": str}
      {"type": "citations", "citations": list}
      {"type": "done", "full_text": str}
      {"type": "error", "message": str}
    """
    if not settings.perplexity_api_key:
        yield {"type": "error", "message": "Perplexity API key not configured"}
        return

    api_messages = [{"role": "system", "content": system_prompt}] + messages

    full_text = ""
    citations = []

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.perplexity_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar-pro",
                    "temperature": 0.3,
                    "max_tokens": 4096,
                    "stream": True,
                    "messages": api_messages,
                },
            ) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    yield {"type": "error", "message": f"Perplexity API error: {response.status_code}"}
                    return

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue

                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break

                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    # Extract text delta
                    choices = data.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            full_text += content
                            yield {"type": "text", "chunk": content}

                    # Extract citations from response metadata
                    if "citations" in data:
                        citations = data["citations"]

    except httpx.ReadTimeout:
        yield {"type": "error", "message": "Perplexity response timed out"}
        return
    except Exception as e:
        logger.error("Perplexity streaming error: %s", e)
        yield {"type": "error", "message": f"Streaming error: {str(e)}"}
        return

    # Post-processing: extract charts from full text
    cleaned_text, charts = extract_charts(full_text)

    if citations:
        formatted = []
        for c in citations:
            if isinstance(c, str):
                formatted.append({"url": c, "title": c})
            elif isinstance(c, dict):
                formatted.append({"url": c.get("url", ""), "title": c.get("title", c.get("url", ""))})
        yield {"type": "citations", "citations": formatted}

    yield {
        "type": "done",
        "full_text": cleaned_text,
        "charts": charts,
        "raw_text": full_text,
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/analyst_chat.py
git commit -m "feat(analyst): add Perplexity streaming service with chart extraction"
```

---

### Task 6: Report Generation Service

**Files:**
- Create: `backend/app/services/analyst_reports.py`

- [ ] **Step 1: Create the report generation service**

Create `backend/app/services/analyst_reports.py`:

```python
"""Report generation for the AI analyst.

Generates Word (.docx) and Excel (.xlsx) reports from conversation data.
Charts are rendered as images via matplotlib.
"""

import io
import logging
import uuid
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import async_session
from app.models.analyst import AnalystConversation, AnalystMessage, AnalystReport, ReportGenStatus
from app.services import s3

logger = logging.getLogger(__name__)

CHART_COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16"]


def _render_chart_image(chart_config: dict) -> bytes | None:
    """Render a chart config dict to a PNG image using matplotlib."""
    try:
        chart_type = chart_config.get("type", "bar")
        data = chart_config.get("data", [])
        title = chart_config.get("title", "")
        x_key = chart_config.get("xKey", chart_config.get("nameKey", "name"))
        y_keys = chart_config.get("yKeys", [chart_config.get("dataKey", "value")])
        colors = chart_config.get("colors", CHART_COLORS)

        if not data:
            return None

        fig, ax = plt.subplots(figsize=(8, 5))
        fig.patch.set_facecolor("#1a1a2e")
        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors="#a0a0b0")
        ax.xaxis.label.set_color("#a0a0b0")
        ax.yaxis.label.set_color("#a0a0b0")
        ax.title.set_color("#e0e0e8")
        for spine in ax.spines.values():
            spine.set_color("#2a2a3e")

        labels = [str(d.get(x_key, "")) for d in data]

        if chart_type == "pie":
            data_key = y_keys[0] if y_keys else "value"
            values = [d.get(data_key, 0) for d in data]
            ax.pie(values, labels=labels, colors=colors[:len(values)], autopct="%1.1f%%",
                   textprops={"color": "#e0e0e8"})
        elif chart_type == "scatter":
            for i, yk in enumerate(y_keys):
                x_vals = [d.get(x_key, 0) for d in data]
                y_vals = [d.get(yk, 0) for d in data]
                ax.scatter(x_vals, y_vals, color=colors[i % len(colors)], label=yk, alpha=0.7)
            ax.legend(facecolor="#1a1a2e", edgecolor="#2a2a3e", labelcolor="#a0a0b0")
        else:
            x = range(len(labels))
            width = 0.8 / len(y_keys) if chart_type == "bar" else 0

            for i, yk in enumerate(y_keys):
                values = [d.get(yk, 0) for d in data]
                color = colors[i % len(colors)]

                if chart_type == "bar":
                    offset = (i - len(y_keys) / 2 + 0.5) * width
                    ax.bar([xi + offset for xi in x], values, width=width, color=color, label=yk)
                elif chart_type == "line":
                    ax.plot(x, values, color=color, label=yk, marker="o", markersize=4)
                elif chart_type == "area":
                    ax.fill_between(x, values, color=color, alpha=0.3, label=yk)
                    ax.plot(x, values, color=color)

            ax.set_xticks(list(x))
            ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
            if len(y_keys) > 1:
                ax.legend(facecolor="#1a1a2e", edgecolor="#2a2a3e", labelcolor="#a0a0b0")

        ax.set_title(title, fontsize=12, pad=10)
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, facecolor=fig.get_facecolor())
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    except Exception as e:
        logger.warning("Chart rendering failed: %s", e)
        plt.close("all")
        return None


def _generate_docx(conversation: AnalystConversation, messages: list[AnalystMessage], title: str) -> bytes:
    """Generate a Word document from conversation data."""
    doc = Document()

    # Cover page
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Deep Thesis Analyst Report")
    run.font.size = Pt(28)
    run.font.color.rgb = RGBColor(99, 102, 241)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(title)
    run.font.size = Pt(18)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(datetime.now(timezone.utc).strftime("%B %d, %Y"))
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(128, 128, 128)

    doc.add_page_break()

    # Conversation content
    for msg in messages:
        if msg.role == "user" or (hasattr(msg.role, "value") and msg.role.value == "user"):
            doc.add_heading(msg.content[:100], level=2)
        else:
            # Assistant response as body text
            for paragraph_text in msg.content.split("\n\n"):
                paragraph_text = paragraph_text.strip()
                if not paragraph_text:
                    continue
                if paragraph_text.startswith("# "):
                    doc.add_heading(paragraph_text[2:], level=2)
                elif paragraph_text.startswith("## "):
                    doc.add_heading(paragraph_text[3:], level=3)
                elif paragraph_text.startswith("- "):
                    for line in paragraph_text.split("\n"):
                        if line.strip().startswith("- "):
                            doc.add_paragraph(line.strip()[2:], style="List Bullet")
                else:
                    doc.add_paragraph(paragraph_text)

            # Render charts as images
            if msg.charts:
                for chart_config in msg.charts:
                    img_bytes = _render_chart_image(chart_config)
                    if img_bytes:
                        buf = io.BytesIO(img_bytes)
                        doc.add_picture(buf, width=Inches(6))
                        cap = doc.add_paragraph(chart_config.get("title", ""))
                        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        cap.style = doc.styles["Caption"] if "Caption" in [s.name for s in doc.styles] else None

    # Citations
    all_citations = []
    for msg in messages:
        if msg.citations:
            all_citations.extend(msg.citations)

    if all_citations:
        doc.add_page_break()
        doc.add_heading("Sources", level=1)
        for i, cite in enumerate(all_citations, 1):
            url = cite.get("url", "") if isinstance(cite, dict) else str(cite)
            title_text = cite.get("title", url) if isinstance(cite, dict) else str(cite)
            doc.add_paragraph(f"{i}. {title_text}\n   {url}", style="List Number")

    # Footer
    section = doc.sections[0]
    footer = section.footer
    footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer_para.add_run("Generated by Deep Thesis AI Analyst")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(128, 128, 128)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _generate_xlsx(conversation: AnalystConversation, messages: list[AnalystMessage], title: str) -> bytes:
    """Generate an Excel workbook from conversation data."""
    wb = Workbook()

    # Summary sheet
    ws = wb.active
    ws.title = "Summary"
    ws.append(["Deep Thesis Analyst Report"])
    ws.append([title])
    ws.append([datetime.now(timezone.utc).strftime("%B %d, %Y")])
    ws.append([])
    ws.append(["Question", "Response Summary"])

    for msg in messages:
        role = msg.role.value if hasattr(msg.role, "value") else msg.role
        if role == "user":
            ws.append([msg.content[:200]])
        elif role == "assistant":
            ws.append(["", msg.content[:500]])

    # Data sheets — one per chart
    chart_num = 0
    for msg in messages:
        if not msg.charts:
            continue
        for chart_config in msg.charts:
            chart_num += 1
            chart_title = chart_config.get("title", f"Chart {chart_num}")
            sheet_name = f"Data {chart_num}"[:31]  # Excel 31-char limit
            ws_data = wb.create_sheet(title=sheet_name)

            data = chart_config.get("data", [])
            if not data:
                continue

            # Headers
            headers = list(data[0].keys())
            ws_data.append(headers)

            # Rows
            for row in data:
                ws_data.append([row.get(h) for h in headers])

            # Add chart
            x_key = chart_config.get("xKey", chart_config.get("nameKey", headers[0]))
            y_keys = chart_config.get("yKeys", [chart_config.get("dataKey")])
            chart_type = chart_config.get("type", "bar")

            try:
                x_col = headers.index(x_key) + 1 if x_key in headers else 1
                chart_obj = None

                if chart_type == "pie":
                    chart_obj = PieChart()
                    data_col = headers.index(y_keys[0]) + 1 if y_keys and y_keys[0] in headers else 2
                    chart_obj.add_data(
                        Reference(ws_data, min_col=data_col, min_row=1, max_row=len(data) + 1),
                        titles_from_data=True,
                    )
                    chart_obj.set_categories(
                        Reference(ws_data, min_col=x_col, min_row=2, max_row=len(data) + 1)
                    )
                elif chart_type in ("line", "area"):
                    chart_obj = LineChart()
                    for yk in y_keys:
                        if yk in headers:
                            col = headers.index(yk) + 1
                            chart_obj.add_data(
                                Reference(ws_data, min_col=col, min_row=1, max_row=len(data) + 1),
                                titles_from_data=True,
                            )
                    chart_obj.set_categories(
                        Reference(ws_data, min_col=x_col, min_row=2, max_row=len(data) + 1)
                    )
                else:
                    chart_obj = BarChart()
                    for yk in y_keys:
                        if yk in headers:
                            col = headers.index(yk) + 1
                            chart_obj.add_data(
                                Reference(ws_data, min_col=col, min_row=1, max_row=len(data) + 1),
                                titles_from_data=True,
                            )
                    chart_obj.set_categories(
                        Reference(ws_data, min_col=x_col, min_row=2, max_row=len(data) + 1)
                    )

                if chart_obj:
                    chart_obj.title = chart_title
                    chart_obj.width = 20
                    chart_obj.height = 12
                    ws_data.add_chart(chart_obj, f"A{len(data) + 4}")
            except Exception as e:
                logger.warning("Excel chart creation failed: %s", e)

    # Sources sheet
    all_citations = []
    for msg in messages:
        if msg.citations:
            all_citations.extend(msg.citations)

    if all_citations:
        ws_sources = wb.create_sheet(title="Sources")
        ws_sources.append(["#", "Title", "URL"])
        for i, cite in enumerate(all_citations, 1):
            url = cite.get("url", "") if isinstance(cite, dict) else str(cite)
            cite_title = cite.get("title", url) if isinstance(cite, dict) else str(cite)
            ws_sources.append([i, cite_title, url])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


async def generate_report(report_id: str) -> None:
    """Generate a report (background task). Updates status in DB and uploads to S3."""
    rid = uuid.UUID(report_id)

    async with async_session() as db:
        try:
            # Load report with conversation and messages
            result = await db.execute(
                select(AnalystReport).where(AnalystReport.id == rid)
            )
            report = result.scalar_one_or_none()
            if not report:
                logger.error("Report %s not found", report_id)
                return

            report.status = ReportGenStatus.generating
            await db.commit()

            # Load conversation with messages
            result = await db.execute(
                select(AnalystConversation)
                .where(AnalystConversation.id == report.conversation_id)
                .options(selectinload(AnalystConversation.messages))
            )
            conversation = result.scalar_one()
            messages = list(conversation.messages)

            # Generate document
            fmt = report.format.value if hasattr(report.format, "value") else report.format
            if fmt == "docx":
                file_bytes = _generate_docx(conversation, messages, report.title)
                ext = "docx"
                content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            else:
                file_bytes = _generate_xlsx(conversation, messages, report.title)
                ext = "xlsx"
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

            # Upload to S3
            s3_key = f"analyst-reports/{conversation.id}/{report.id}/report.{ext}"
            s3.upload_file(file_bytes, s3_key)

            report.s3_key = s3_key
            report.file_size_bytes = len(file_bytes)
            report.status = ReportGenStatus.complete
            await db.commit()

            logger.info("Report %s generated: %s (%d bytes)", report_id, s3_key, len(file_bytes))

        except Exception as e:
            logger.error("Report generation failed for %s: %s", report_id, e)
            try:
                report.status = ReportGenStatus.failed
                report.error = str(e)[:500]
                await db.commit()
            except Exception:
                logger.error("Failed to update report status for %s", report_id)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/analyst_reports.py
git commit -m "feat(analyst): add Word/Excel report generation with matplotlib charts"
```

---

### Task 7: API Endpoints — Conversation CRUD

**Files:**
- Create: `backend/app/api/analyst.py`

- [ ] **Step 1: Create the analyst API with conversation endpoints**

Create `backend/app/api/analyst.py`:

```python
import asyncio
import json
import logging
import secrets
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_current_user_or_none, get_db
from app.config import settings
from app.models.analyst import (
    AnalystConversation,
    AnalystMessage,
    AnalystReport,
    MessageRole,
    ReportFormat,
    ReportGenStatus,
)
from app.models.user import SubscriptionStatus, User
from app.services.analyst_chat import stream_perplexity, extract_charts
from app.services.analyst_context import (
    build_system_prompt,
    find_matching_startups,
    find_startups_by_filter,
    get_portfolio_summary,
)
from app.services.analyst_reports import generate_report
from app.services import s3

logger = logging.getLogger(__name__)

router = APIRouter()

FREE_MESSAGE_LIMIT = 20
SUBSCRIBER_MESSAGE_LIMIT = 100
SUBSCRIBER_WARNING_AT = 80


# ── helpers ──────────────────────────────────────────────────────────

def _sub_status_value(user: User) -> str:
    s = user.subscription_status
    return s.value if hasattr(s, "value") else s


def _conversation_to_dict(c: AnalystConversation, include_messages: bool = False) -> dict:
    d = {
        "id": str(c.id),
        "title": c.title,
        "is_free_conversation": c.is_free_conversation,
        "message_count": c.message_count,
        "share_token": c.share_token,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
    if include_messages and c.messages:
        d["messages"] = [
            {
                "id": str(m.id),
                "role": m.role.value if hasattr(m.role, "value") else m.role,
                "content": m.content,
                "charts": m.charts,
                "citations": m.citations,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in c.messages
        ]
    if c.reports:
        d["reports"] = [
            {
                "id": str(r.id),
                "title": r.title,
                "format": r.format.value if hasattr(r.format, "value") else r.format,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "file_size_bytes": r.file_size_bytes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in c.reports
        ]
    return d


# ── conversation CRUD ────────────────────────────────────────────────

@router.post("/api/analyst/conversations")
async def create_conversation(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Gating: count existing conversations
    count_result = await db.execute(
        select(func.count(AnalystConversation.id)).where(
            AnalystConversation.user_id == user.id
        )
    )
    count = count_result.scalar() or 0

    if count >= 1 and _sub_status_value(user) != "active":
        raise HTTPException(
            status_code=402,
            detail="Subscribe for $19.99/mo for unlimited analyst access.",
        )

    is_free = count == 0
    conversation = AnalystConversation(
        user_id=user.id,
        is_free_conversation=is_free,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "is_free_conversation": is_free,
    }


@router.get("/api/analyst/conversations")
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystConversation)
        .where(AnalystConversation.user_id == user.id)
        .order_by(AnalystConversation.updated_at.desc())
    )
    conversations = result.scalars().all()
    return {
        "items": [
            {
                "id": str(c.id),
                "title": c.title,
                "message_count": c.message_count,
                "is_free_conversation": c.is_free_conversation,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in conversations
        ]
    }


@router.get("/api/analyst/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystConversation)
        .where(
            AnalystConversation.id == conversation_id,
            AnalystConversation.user_id == user.id,
        )
        .options(
            selectinload(AnalystConversation.messages),
            selectinload(AnalystConversation.reports),
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    return _conversation_to_dict(conversation, include_messages=True)


class UpdateConversationBody(BaseModel):
    title: str


@router.patch("/api/analyst/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: uuid.UUID,
    body: UpdateConversationBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystConversation).where(
            AnalystConversation.id == conversation_id,
            AnalystConversation.user_id == user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    conversation.title = body.title
    await db.commit()
    return {"ok": True}


@router.delete("/api/analyst/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystConversation)
        .where(
            AnalystConversation.id == conversation_id,
            AnalystConversation.user_id == user.id,
        )
        .options(selectinload(AnalystConversation.reports))
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    # Clean up S3 report files
    for report in conversation.reports:
        if report.s3_key:
            s3.delete_file(report.s3_key)

    await db.delete(conversation)
    await db.commit()
    return {"ok": True}


# ── SSE chat ─────────────────────────────────────────────────────────

class SendMessageBody(BaseModel):
    content: str


@router.post("/api/analyst/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    body: SendMessageBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Load conversation
    result = await db.execute(
        select(AnalystConversation)
        .where(
            AnalystConversation.id == conversation_id,
            AnalystConversation.user_id == user.id,
        )
        .options(selectinload(AnalystConversation.messages))
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    # Message limit check
    is_sub = _sub_status_value(user) == "active"
    limit = SUBSCRIBER_MESSAGE_LIMIT if is_sub else FREE_MESSAGE_LIMIT
    if conversation.message_count >= limit:
        raise HTTPException(
            400,
            f"Message limit reached ({limit}). {'Start a new conversation.' if is_sub else 'Subscribe for more.'}",
        )

    # Save user message
    user_msg = AnalystMessage(
        conversation_id=conversation.id,
        role=MessageRole.user,
        content=body.content,
    )
    db.add(user_msg)
    conversation.message_count = (conversation.message_count or 0) + 1

    # Update title from first message
    if conversation.message_count == 1:
        conversation.title = body.content[:100]

    await db.commit()

    # Build context
    summary = await get_portfolio_summary(db)
    matched_startups = await find_matching_startups(db, body.content)
    if not matched_startups:
        matched_startups = await find_startups_by_filter(db, body.content)

    matched_ids = [s["id"] for s in matched_startups] if matched_startups else None
    system_prompt = build_system_prompt(summary, matched_startups or None)

    # Build message history (last 20)
    history = []
    for msg in conversation.messages[-20:]:
        role = msg.role.value if hasattr(msg.role, "value") else msg.role
        history.append({"role": role, "content": msg.content})

    # Add the current user message (already in DB but make sure it's in history)
    if not history or history[-1]["content"] != body.content:
        history.append({"role": "user", "content": body.content})

    # Capture IDs needed for the streaming closure
    conv_id = conversation.id
    user_id = user.id

    async def event_stream():
        full_text = ""
        charts = []
        citations = []
        error_msg = None

        try:
            async for event in stream_perplexity(history, system_prompt):
                if event["type"] == "text":
                    full_text += event["chunk"]
                    yield f"event: text\ndata: {json.dumps({'chunk': event['chunk']})}\n\n"

                elif event["type"] == "citations":
                    citations = event["citations"]
                    yield f"event: citations\ndata: {json.dumps({'citations': citations})}\n\n"

                elif event["type"] == "done":
                    full_text = event.get("full_text", full_text)
                    charts = event.get("charts", [])
                    if charts:
                        yield f"event: charts\ndata: {json.dumps({'charts': charts})}\n\n"

                elif event["type"] == "error":
                    error_msg = event["message"]
                    yield f"event: error\ndata: {json.dumps({'message': error_msg})}\n\n"

        except Exception as e:
            error_msg = str(e)
            yield f"event: error\ndata: {json.dumps({'message': error_msg})}\n\n"

        # Save assistant message to DB
        if full_text:
            from app.db.session import async_session
            async with async_session() as save_db:
                assistant_msg = AnalystMessage(
                    conversation_id=conv_id,
                    role=MessageRole.assistant,
                    content=full_text,
                    charts=charts if charts else None,
                    citations=citations if citations else None,
                    context_startups=matched_ids,
                )
                save_db.add(assistant_msg)

                await save_db.execute(
                    update(AnalystConversation)
                    .where(AnalystConversation.id == conv_id)
                    .values(message_count=AnalystConversation.message_count + 1)
                )
                await save_db.commit()

        # Warning at 80 messages for subscribers
        msg_count = (conversation.message_count or 0) + 1  # +1 for assistant
        if is_sub and msg_count >= SUBSCRIBER_WARNING_AT:
            yield f"event: warning\ndata: {json.dumps({'message': f'{SUBSCRIBER_MESSAGE_LIMIT - msg_count} messages remaining in this conversation.'})}\n\n"

        yield f"event: done\ndata: {json.dumps({})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── reports ──────────────────────────────────────────────────────────

class CreateReportBody(BaseModel):
    format: str  # "docx" or "xlsx"
    title: str | None = None


@router.post("/api/analyst/conversations/{conversation_id}/reports")
async def create_report(
    conversation_id: uuid.UUID,
    body: CreateReportBody,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Gating: subscription required for reports
    if _sub_status_value(user) != "active":
        raise HTTPException(402, "Subscription required for report generation.")

    result = await db.execute(
        select(AnalystConversation).where(
            AnalystConversation.id == conversation_id,
            AnalystConversation.user_id == user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    if body.format not in ("docx", "xlsx"):
        raise HTTPException(400, "Format must be 'docx' or 'xlsx'")

    report = AnalystReport(
        conversation_id=conversation.id,
        user_id=user.id,
        title=body.title or conversation.title,
        format=ReportFormat(body.format),
        status=ReportGenStatus.pending,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    background_tasks.add_task(generate_report, str(report.id))

    return {"id": str(report.id), "status": "pending"}


@router.get("/api/analyst/reports")
async def list_reports(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystReport)
        .where(AnalystReport.user_id == user.id)
        .order_by(AnalystReport.created_at.desc())
    )
    reports = result.scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "conversation_id": str(r.conversation_id),
                "title": r.title,
                "format": r.format.value if hasattr(r.format, "value") else r.format,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "file_size_bytes": r.file_size_bytes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ]
    }


@router.get("/api/analyst/reports/{report_id}")
async def get_report_status(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystReport).where(
            AnalystReport.id == report_id,
            AnalystReport.user_id == user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")

    return {
        "id": str(report.id),
        "status": report.status.value if hasattr(report.status, "value") else report.status,
        "file_size_bytes": report.file_size_bytes,
        "error": report.error,
    }


@router.get("/api/analyst/reports/{report_id}/download")
async def download_report(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystReport).where(
            AnalystReport.id == report_id,
            AnalystReport.user_id == user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")

    status_val = report.status.value if hasattr(report.status, "value") else report.status
    if status_val != "complete" or not report.s3_key:
        raise HTTPException(400, "Report not ready for download")

    file_data = s3.download_file(report.s3_key)
    fmt = report.format.value if hasattr(report.format, "value") else report.format
    if fmt == "docx":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"{report.title}.docx"
    else:
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{report.title}.xlsx"

    from fastapi.responses import Response
    return Response(
        content=file_data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── sharing ──────────────────────────────────────────────────────────

@router.post("/api/analyst/conversations/{conversation_id}/share")
async def share_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystConversation).where(
            AnalystConversation.id == conversation_id,
            AnalystConversation.user_id == user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    if not conversation.share_token:
        conversation.share_token = secrets.token_urlsafe(32)
        await db.commit()

    return {
        "share_token": conversation.share_token,
        "url": f"/insights/shared/{conversation.share_token}",
    }


@router.get("/api/analyst/shared/{share_token}")
async def get_shared_conversation(
    share_token: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystConversation)
        .where(AnalystConversation.share_token == share_token)
        .options(selectinload(AnalystConversation.messages))
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Shared conversation not found")

    return {
        "title": conversation.title,
        "message_count": conversation.message_count,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role.value if hasattr(m.role, "value") else m.role,
                "content": m.content,
                "charts": m.charts,
                "citations": m.citations,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in conversation.messages
        ],
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/analyst.py
git commit -m "feat(analyst): add all API endpoints — CRUD, SSE chat, reports, sharing"
```

---

### Task 8: Register Router in Main

**Files:**
- Modify: `backend/app/main.py:59,89`

- [ ] **Step 1: Add router import and registration**

In `backend/app/main.py`, add the import after line 59 (the analyze_router import):

```python
from app.api.analyst import router as analyst_router
```

Then add the include_router call after line 89 (the last include_router):

```python
app.include_router(analyst_router)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(analyst): register analyst router in FastAPI app"
```

---

### Task 9: Frontend Types + API Client

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add analyst types to types.ts**

Add the following interfaces to the end of `frontend/lib/types.ts`:

```typescript
// ── Analyst types ────────────────────────────────────────────────────

export interface AnalystConversationSummary {
  id: string;
  title: string;
  message_count: number;
  is_free_conversation: boolean;
  updated_at: string | null;
}

export interface AnalystMessageData {
  id: string;
  role: "user" | "assistant";
  content: string;
  charts: AnalystChartConfig[] | null;
  citations: AnalystCitation[] | null;
  created_at: string | null;
}

export interface AnalystChartConfig {
  type: "bar" | "line" | "pie" | "scatter" | "area";
  title: string;
  data: Record<string, unknown>[];
  xKey?: string;
  yKeys?: string[];
  nameKey?: string;
  dataKey?: string;
  colors?: string[];
}

export interface AnalystCitation {
  url: string;
  title: string;
}

export interface AnalystReportSummary {
  id: string;
  title: string;
  format: "docx" | "xlsx";
  status: "pending" | "generating" | "complete" | "failed";
  file_size_bytes: number | null;
  created_at: string | null;
}

export interface AnalystConversationDetail {
  id: string;
  title: string;
  is_free_conversation: boolean;
  message_count: number;
  share_token: string | null;
  created_at: string | null;
  updated_at: string | null;
  messages: AnalystMessageData[];
  reports?: AnalystReportSummary[];
}

export interface AnalystSharedConversation {
  title: string;
  message_count: number;
  messages: AnalystMessageData[];
}
```

- [ ] **Step 2: Add analyst API methods to api.ts**

Add the following to the end of `frontend/lib/api.ts`:

```typescript
  // ── Analyst ──────────────────────────────────────────────────────────

  async createConversation(token: string) {
    return apiFetch<{ id: string; title: string; is_free_conversation: boolean }>(
      "/api/analyst/conversations",
      { method: "POST", headers: authHeaders(token) }
    );
  },

  async listConversations(token: string) {
    return apiFetch<{ items: AnalystConversationSummary[] }>(
      "/api/analyst/conversations",
      { headers: authHeaders(token) }
    );
  },

  async getConversation(token: string, id: string) {
    return apiFetch<AnalystConversationDetail>(
      `/api/analyst/conversations/${id}`,
      { headers: authHeaders(token) }
    );
  },

  async updateConversationTitle(token: string, id: string, title: string) {
    return apiFetch<{ ok: boolean }>(
      `/api/analyst/conversations/${id}`,
      {
        method: "PATCH",
        headers: { ...authHeaders(token), "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      }
    );
  },

  async deleteConversation(token: string, id: string) {
    return apiFetch<{ ok: boolean }>(
      `/api/analyst/conversations/${id}`,
      { method: "DELETE", headers: authHeaders(token) }
    );
  },

  streamMessage(token: string, conversationId: string, content: string) {
    const url = `${API_BASE}/api/analyst/conversations/${conversationId}/messages`;
    return fetch(url, {
      method: "POST",
      headers: {
        ...authHeaders(token),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ content }),
    });
  },

  async createReport(token: string, conversationId: string, format: "docx" | "xlsx", title?: string) {
    return apiFetch<{ id: string; status: string }>(
      `/api/analyst/conversations/${conversationId}/reports`,
      {
        method: "POST",
        headers: { ...authHeaders(token), "Content-Type": "application/json" },
        body: JSON.stringify({ format, title }),
      }
    );
  },

  async listReports(token: string) {
    return apiFetch<{ items: AnalystReportSummary[] }>(
      "/api/analyst/reports",
      { headers: authHeaders(token) }
    );
  },

  async getReportStatus(token: string, reportId: string) {
    return apiFetch<{ id: string; status: string; file_size_bytes: number | null; error: string | null }>(
      `/api/analyst/reports/${reportId}`,
      { headers: authHeaders(token) }
    );
  },

  getReportDownloadUrl(reportId: string) {
    return `${API_BASE}/api/analyst/reports/${reportId}/download`;
  },

  async shareConversation(token: string, conversationId: string) {
    return apiFetch<{ share_token: string; url: string }>(
      `/api/analyst/conversations/${conversationId}/share`,
      { method: "POST", headers: authHeaders(token) }
    );
  },

  async getSharedConversation(token: string) {
    return apiFetch<AnalystSharedConversation>(
      `/api/analyst/shared/${token}`,
      {}
    );
  },
```

Also add the type imports at the top of `api.ts` where types are imported:

```typescript
import type {
  AnalystConversationSummary,
  AnalystConversationDetail,
  AnalystReportSummary,
  AnalystSharedConversation,
} from "./types";
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat(analyst): add frontend types and API client methods"
```

---

### Task 10: AnalystChart Component

**Files:**
- Create: `frontend/components/analyst/AnalystChart.tsx`

- [ ] **Step 1: Create the Recharts wrapper component**

Create the directory and file:

```bash
mkdir -p frontend/components/analyst
```

Create `frontend/components/analyst/AnalystChart.tsx`:

```tsx
"use client";

import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  ScatterChart, Scatter, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import type { AnalystChartConfig } from "@/lib/types";

const DEFAULT_COLORS = [
  "#6366f1", "#f59e0b", "#10b981", "#ef4444",
  "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16",
];

export function AnalystChart({ config }: { config: AnalystChartConfig }) {
  const { type, title, data, colors } = config;
  const palette = colors || DEFAULT_COLORS;
  const xKey = config.xKey || config.nameKey || "name";
  const yKeys = config.yKeys || (config.dataKey ? [config.dataKey] : ["value"]);

  if (!data || data.length === 0) return null;

  return (
    <div className="my-4 rounded border border-border bg-surface-alt p-4">
      {title && <p className="text-xs font-medium text-text-secondary mb-3">{title}</p>}
      <ResponsiveContainer width="100%" height={300}>
        {type === "pie" ? (
          <PieChart>
            <Pie
              data={data}
              dataKey={yKeys[0]}
              nameKey={xKey}
              cx="50%"
              cy="50%"
              outerRadius={100}
              label={({ name, percent }: { name: string; percent: number }) =>
                `${name} ${(percent * 100).toFixed(0)}%`
              }
            >
              {data.map((_, i) => (
                <Cell key={i} fill={palette[i % palette.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        ) : type === "scatter" ? (
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis dataKey={xKey} stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <YAxis stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <Tooltip />
            {yKeys.map((yk, i) => (
              <Scatter key={yk} name={yk} data={data} fill={palette[i % palette.length]} />
            ))}
            <Legend />
          </ScatterChart>
        ) : type === "area" ? (
          <AreaChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis dataKey={xKey} stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <YAxis stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <Tooltip />
            {yKeys.map((yk, i) => (
              <Area
                key={yk}
                type="monotone"
                dataKey={yk}
                fill={palette[i % palette.length]}
                fillOpacity={0.3}
                stroke={palette[i % palette.length]}
              />
            ))}
            <Legend />
          </AreaChart>
        ) : type === "line" ? (
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis dataKey={xKey} stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <YAxis stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <Tooltip />
            {yKeys.map((yk, i) => (
              <Line
                key={yk}
                type="monotone"
                dataKey={yk}
                stroke={palette[i % palette.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            ))}
            <Legend />
          </LineChart>
        ) : (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis dataKey={xKey} stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <YAxis stroke="var(--color-text-tertiary)" tick={{ fontSize: 11 }} />
            <Tooltip />
            {yKeys.map((yk, i) => (
              <Bar key={yk} dataKey={yk} fill={palette[i % palette.length]} radius={[4, 4, 0, 0]} />
            ))}
            <Legend />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/analyst/AnalystChart.tsx
git commit -m "feat(analyst): add AnalystChart Recharts wrapper component"
```

---

### Task 11: AnalystMessage Component

**Files:**
- Create: `frontend/components/analyst/AnalystMessage.tsx`

- [ ] **Step 1: Create the message component**

Create `frontend/components/analyst/AnalystMessage.tsx`:

```tsx
"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AnalystChart } from "./AnalystChart";
import type { AnalystChartConfig, AnalystCitation } from "@/lib/types";

interface Props {
  role: "user" | "assistant";
  content: string;
  charts?: AnalystChartConfig[] | null;
  citations?: AnalystCitation[] | null;
  isStreaming?: boolean;
}

export function AnalystMessage({ role, content, charts, citations, isStreaming }: Props) {
  const isUser = role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-accent/10 text-accent flex items-center justify-center text-xs font-medium mt-1">
          DT
        </div>
      )}
      <div
        className={`max-w-[85%] rounded-lg px-4 py-3 ${
          isUser
            ? "bg-accent text-white"
            : "bg-surface border border-border text-text-primary"
        }`}
      >
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{content}</p>
        ) : (
          <div className="text-sm prose-sm prose-invert max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => <p className="mb-2 leading-relaxed text-text-primary">{children}</p>,
                h1: ({ children }) => <h3 className="text-base font-medium text-text-primary mt-4 mb-2">{children}</h3>,
                h2: ({ children }) => <h4 className="text-sm font-medium text-text-primary mt-3 mb-1">{children}</h4>,
                h3: ({ children }) => <h5 className="text-sm font-medium text-text-secondary mt-2 mb-1">{children}</h5>,
                ul: ({ children }) => <ul className="list-disc ml-4 mb-2 space-y-1">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal ml-4 mb-2 space-y-1">{children}</ol>,
                li: ({ children }) => <li className="text-text-primary">{children}</li>,
                strong: ({ children }) => <strong className="font-medium text-text-primary">{children}</strong>,
                code: ({ children, className }) => {
                  const isBlock = className?.includes("language-");
                  return isBlock ? (
                    <pre className="bg-background rounded p-3 overflow-x-auto text-xs my-2">
                      <code>{children}</code>
                    </pre>
                  ) : (
                    <code className="bg-background px-1 py-0.5 rounded text-xs">{children}</code>
                  );
                },
                table: ({ children }) => (
                  <div className="overflow-x-auto my-2">
                    <table className="min-w-full text-xs border border-border">{children}</table>
                  </div>
                ),
                th: ({ children }) => <th className="border border-border bg-surface-alt px-2 py-1 text-left font-medium">{children}</th>,
                td: ({ children }) => <td className="border border-border px-2 py-1">{children}</td>,
              }}
            >
              {content}
            </ReactMarkdown>

            {isStreaming && (
              <span className="inline-block w-2 h-4 bg-accent/60 animate-pulse ml-0.5" />
            )}
          </div>
        )}

        {/* Charts */}
        {charts && charts.length > 0 && (
          <div className="mt-2">
            {charts.map((chart, i) => (
              <AnalystChart key={i} config={chart} />
            ))}
          </div>
        )}

        {/* Citations */}
        {citations && citations.length > 0 && (
          <div className="mt-3 pt-2 border-t border-border/50">
            <p className="text-[10px] text-text-tertiary mb-1">Sources</p>
            <div className="flex flex-wrap gap-1">
              {citations.map((cite, i) => (
                <a
                  key={i}
                  href={cite.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[10px] text-accent/70 hover:text-accent bg-accent/5 px-1.5 py-0.5 rounded"
                  title={cite.url}
                >
                  {cite.title || new URL(cite.url).hostname}
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
      {isUser && (
        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-accent text-white flex items-center justify-center text-xs font-medium mt-1">
          U
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/analyst/AnalystMessage.tsx
git commit -m "feat(analyst): add AnalystMessage component with markdown + charts + citations"
```

---

### Task 12: AnalystSidebar Component

**Files:**
- Create: `frontend/components/analyst/AnalystSidebar.tsx`

- [ ] **Step 1: Create the sidebar component**

Create `frontend/components/analyst/AnalystSidebar.tsx`:

```tsx
"use client";

import type { AnalystConversationSummary } from "@/lib/types";

const SUGGESTED_ANALYSES = [
  "Portfolio sector breakdown",
  "Score distribution analysis",
  "Funding stage pipeline",
  "Top performers deep dive",
  "Market trend comparison",
  "Competitive landscape overview",
  "Due diligence checklist template",
];

interface Props {
  conversations: AnalystConversationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onSuggestion: (prompt: string) => void;
  isOpen: boolean;
  onToggle: () => void;
}

export function AnalystSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onSuggestion,
  isOpen,
  onToggle,
}: Props) {
  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={onToggle}
        className="md:hidden fixed top-20 left-3 z-30 p-2 rounded bg-surface border border-border text-text-secondary hover:text-text-primary"
        aria-label="Toggle sidebar"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Overlay for mobile */}
      {isOpen && (
        <div className="md:hidden fixed inset-0 bg-black/30 z-30" onClick={onToggle} />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed md:relative z-40 md:z-auto top-0 left-0 h-full w-64 bg-surface border-r border-border flex flex-col transition-transform md:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* New button */}
        <div className="p-3 border-b border-border">
          <button
            onClick={onNew}
            className="w-full px-3 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover transition"
          >
            + New Conversation
          </button>
        </div>

        {/* History */}
        <div className="flex-1 overflow-y-auto">
          {conversations.length > 0 && (
            <div className="p-3">
              <p className="text-[10px] uppercase tracking-wider text-text-tertiary mb-2">History</p>
              <div className="space-y-0.5">
                {conversations.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => onSelect(c.id)}
                    className={`w-full text-left px-2 py-1.5 rounded text-sm truncate transition ${
                      activeId === c.id
                        ? "bg-accent/10 text-accent"
                        : "text-text-secondary hover:text-text-primary hover:bg-surface-alt"
                    }`}
                    title={c.title}
                  >
                    {c.title}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Suggestions */}
          <div className="p-3 border-t border-border">
            <p className="text-[10px] uppercase tracking-wider text-text-tertiary mb-2">Suggested</p>
            <div className="space-y-0.5">
              {SUGGESTED_ANALYSES.map((s) => (
                <button
                  key={s}
                  onClick={() => onSuggestion(s)}
                  className="w-full text-left px-2 py-1.5 rounded text-xs text-text-tertiary hover:text-text-secondary hover:bg-surface-alt transition truncate"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/analyst/AnalystSidebar.tsx
git commit -m "feat(analyst): add AnalystSidebar with history list and suggested analyses"
```

---

### Task 13: AnalystChat + AnalystInput Components

**Files:**
- Create: `frontend/components/analyst/AnalystChat.tsx`
- Create: `frontend/components/analyst/AnalystInput.tsx`

- [ ] **Step 1: Create the chat container component**

Create `frontend/components/analyst/AnalystChat.tsx`:

```tsx
"use client";

import { useEffect, useRef } from "react";
import { AnalystMessage } from "./AnalystMessage";
import type { AnalystMessageData } from "@/lib/types";

interface Props {
  messages: AnalystMessageData[];
  streamingContent: string;
  isStreaming: boolean;
}

export function AnalystChat({ messages, streamingContent, isStreaming }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streamingContent]);

  if (messages.length === 0 && !isStreaming) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center max-w-md">
          <p className="text-2xl font-serif text-text-primary mb-2">AI Venture Analyst</p>
          <p className="text-sm text-text-tertiary mb-6">
            Ask me anything about your portfolio, market trends, competitor analysis, or due diligence.
            I have access to your startup database and external market intelligence.
          </p>
          <div className="grid grid-cols-2 gap-2 text-xs">
            {[
              "What's our strongest sector?",
              "Compare top 5 by AI score",
              "Fintech funding trends",
              "Which startups need attention?",
            ].map((q) => (
              <div
                key={q}
                className="px-3 py-2 rounded border border-border text-text-tertiary bg-surface"
              >
                {q}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
      {messages.map((msg) => (
        <AnalystMessage
          key={msg.id}
          role={msg.role}
          content={msg.content}
          charts={msg.charts}
          citations={msg.citations}
        />
      ))}

      {/* Streaming assistant message */}
      {isStreaming && streamingContent && (
        <AnalystMessage
          role="assistant"
          content={streamingContent}
          isStreaming={true}
        />
      )}

      {/* Typing indicator when streaming hasn't produced text yet */}
      {isStreaming && !streamingContent && (
        <div className="flex gap-3">
          <div className="w-7 h-7 rounded-full bg-accent/10 text-accent flex items-center justify-center text-xs font-medium">
            DT
          </div>
          <div className="bg-surface border border-border rounded-lg px-4 py-3">
            <div className="flex gap-1">
              <span className="w-2 h-2 bg-text-tertiary rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-2 h-2 bg-text-tertiary rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-2 h-2 bg-text-tertiary rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
```

- [ ] **Step 2: Create the input component**

Create `frontend/components/analyst/AnalystInput.tsx`:

```tsx
"use client";

import { useRef, useState } from "react";

interface Props {
  onSend: (message: string) => void;
  onGenerateReport: (format: "docx" | "xlsx") => void;
  isStreaming: boolean;
  hasMessages: boolean;
  isSubscriber: boolean;
}

export function AnalystInput({ onSend, onGenerateReport, isStreaming, hasMessages, isSubscriber }: Props) {
  const [input, setInput] = useState("");
  const [showReportMenu, setShowReportMenu] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    onSend(trimmed);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    // Auto-resize
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 150) + "px";
  };

  return (
    <div className="border-t border-border bg-surface px-4 py-3">
      <div className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your portfolio, market trends, competitor analysis..."
          rows={1}
          disabled={isStreaming}
          className="flex-1 resize-none rounded border border-border bg-background px-3 py-2 text-sm text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent disabled:opacity-50"
        />

        <button
          onClick={handleSubmit}
          disabled={!input.trim() || isStreaming}
          className="px-4 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition"
        >
          {isStreaming ? "..." : "Send"}
        </button>

        {hasMessages && (
          <div className="relative">
            <button
              onClick={() => setShowReportMenu(!showReportMenu)}
              disabled={isStreaming}
              className="px-3 py-2 text-xs rounded border border-border text-text-secondary hover:text-text-primary hover:border-accent/50 disabled:opacity-50 transition whitespace-nowrap"
              title={isSubscriber ? "Generate report" : "Subscribe to generate reports"}
            >
              Report
            </button>
            {showReportMenu && (
              <div className="absolute bottom-full right-0 mb-1 bg-surface border border-border rounded shadow-lg py-1 z-10">
                <button
                  onClick={() => { onGenerateReport("docx"); setShowReportMenu(false); }}
                  className="block w-full text-left px-4 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-alt"
                >
                  Word (.docx)
                </button>
                <button
                  onClick={() => { onGenerateReport("xlsx"); setShowReportMenu(false); }}
                  className="block w-full text-left px-4 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-alt"
                >
                  Excel (.xlsx)
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/analyst/AnalystChat.tsx frontend/components/analyst/AnalystInput.tsx
git commit -m "feat(analyst): add AnalystChat container and AnalystInput components"
```

---

### Task 14: Main Insights Page

**Files:**
- Modify: `frontend/app/insights/page.tsx` (full replacement)

- [ ] **Step 1: Replace the insights page**

Replace the entire contents of `frontend/app/insights/page.tsx`:

```tsx
"use client";

import { useSession } from "next-auth/react";
import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type {
  AnalystConversationSummary,
  AnalystMessageData,
  AnalystChartConfig,
  AnalystCitation,
} from "@/lib/types";
import { AnalystSidebar } from "@/components/analyst/AnalystSidebar";
import { AnalystChat } from "@/components/analyst/AnalystChat";
import { AnalystInput } from "@/components/analyst/AnalystInput";

export default function InsightsPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const router = useRouter();
  const searchParams = useSearchParams();

  const [conversations, setConversations] = useState<AnalystConversationSummary[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AnalystMessageData[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  // Subscription check
  const isSubscriber = (session as any)?.subscriptionStatus === "active";

  // Load conversations list
  const loadConversations = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.listConversations(token);
      setConversations(data.items);
    } catch {
      // silent
    }
  }, [token]);

  // Load a specific conversation
  const loadConversation = useCallback(
    async (id: string) => {
      if (!token) return;
      try {
        const data = await api.getConversation(token, id);
        setMessages(data.messages);
        setActiveConvId(id);
      } catch {
        // silent
      }
    },
    [token]
  );

  // Initial load
  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    loadConversations().then(() => setLoading(false));
  }, [token, loadConversations]);

  // Load conversation from URL param
  useEffect(() => {
    const convId = searchParams.get("c");
    if (convId && token) {
      loadConversation(convId);
    }
  }, [searchParams, token, loadConversation]);

  // Create new conversation
  const handleNew = async () => {
    if (!token) return;
    try {
      const data = await api.createConversation(token);
      setActiveConvId(data.id);
      setMessages([]);
      await loadConversations();
      setSidebarOpen(false);
    } catch (err: any) {
      if (err?.status === 402) {
        alert(err.message || "Subscribe for unlimited analyst access.");
      }
    }
  };

  // Select existing conversation
  const handleSelect = (id: string) => {
    loadConversation(id);
    setSidebarOpen(false);
  };

  // Handle suggestion click
  const handleSuggestion = async (prompt: string) => {
    // Create new conversation and send the suggestion
    if (!token) return;
    try {
      const data = await api.createConversation(token);
      setActiveConvId(data.id);
      setMessages([]);
      await loadConversations();
      setSidebarOpen(false);
      // Send the suggestion as first message after a tick
      setTimeout(() => sendMessage(prompt, data.id), 100);
    } catch (err: any) {
      if (err?.status === 402) {
        alert(err.message || "Subscribe for unlimited analyst access.");
      }
    }
  };

  // Send message and handle SSE stream
  const sendMessage = async (content: string, overrideConvId?: string) => {
    const convId = overrideConvId || activeConvId;
    if (!token || !convId || isStreaming) return;

    // Create conversation if none active
    let targetConvId = convId;
    if (!targetConvId) {
      try {
        const data = await api.createConversation(token);
        targetConvId = data.id;
        setActiveConvId(data.id);
        await loadConversations();
      } catch (err: any) {
        if (err?.status === 402) {
          alert(err.message || "Subscribe for unlimited analyst access.");
        }
        return;
      }
    }

    // Add user message optimistically
    const userMsg: AnalystMessageData = {
      id: `temp-${Date.now()}`,
      role: "user",
      content,
      charts: null,
      citations: null,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsStreaming(true);
    setStreamingContent("");

    try {
      const response = await api.streamMessage(token, targetConvId, content);
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: "Request failed" }));
        throw new Error(err.detail || `Error ${response.status}`);
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullText = "";
      let charts: AnalystChartConfig[] = [];
      let citations: AnalystCitation[] = [];
      let currentEvent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event: ")) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const dataStr = line.slice(6);
            try {
              const data = JSON.parse(dataStr);

              if (currentEvent === "text") {
                fullText += data.chunk;
                setStreamingContent(fullText);
              } else if (currentEvent === "charts") {
                charts = data.charts || [];
              } else if (currentEvent === "citations") {
                citations = data.citations || [];
              } else if (currentEvent === "error") {
                throw new Error(data.message);
              }
            } catch (parseErr) {
              if (currentEvent === "error") throw parseErr;
            }
          }
        }
      }

      // Add completed assistant message
      const assistantMsg: AnalystMessageData = {
        id: `msg-${Date.now()}`,
        role: "assistant",
        content: fullText,
        charts: charts.length > 0 ? charts : null,
        citations: citations.length > 0 ? citations : null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setStreamingContent("");
      await loadConversations();
    } catch (err: any) {
      // Show error as assistant message
      const errMsg: AnalystMessageData = {
        id: `err-${Date.now()}`,
        role: "assistant",
        content: `Error: ${err.message || "Something went wrong. Please try again."}`,
        charts: null,
        citations: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errMsg]);
      setStreamingContent("");
    } finally {
      setIsStreaming(false);
    }
  };

  // Generate report
  const handleGenerateReport = async (format: "docx" | "xlsx") => {
    if (!token || !activeConvId) return;

    if (!isSubscriber) {
      alert("Subscribe to generate reports.");
      return;
    }

    try {
      const result = await api.createReport(token, activeConvId, format);

      // Poll for completion
      const poll = async () => {
        const status = await api.getReportStatus(token, result.id);
        if (status.status === "complete") {
          // Trigger download
          const url = api.getReportDownloadUrl(result.id);
          const a = document.createElement("a");
          a.href = url;
          a.download = "";
          // Add auth header via fetch + blob
          const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
          const blob = await resp.blob();
          const blobUrl = URL.createObjectURL(blob);
          a.href = blobUrl;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(blobUrl);
        } else if (status.status === "failed") {
          alert(`Report generation failed: ${status.error || "Unknown error"}`);
        } else {
          setTimeout(poll, 2000);
        }
      };
      setTimeout(poll, 2000);
      alert("Generating report... It will download automatically when ready.");
    } catch (err: any) {
      alert(err.message || "Failed to generate report.");
    }
  };

  // Auth gate
  if (!session) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <p className="text-xl font-serif text-text-primary mb-2">AI Venture Analyst</p>
          <p className="text-sm text-text-tertiary mb-4">Sign in to access the analyst.</p>
        </div>
      </div>
    );
  }

  if (loading) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      <AnalystSidebar
        conversations={conversations}
        activeId={activeConvId}
        onSelect={handleSelect}
        onNew={handleNew}
        onSuggestion={handleSuggestion}
        isOpen={sidebarOpen}
        onToggle={() => setSidebarOpen(!sidebarOpen)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        {activeConvId && (
          <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-surface">
            <p className="text-sm font-medium text-text-primary truncate">
              {conversations.find((c) => c.id === activeConvId)?.title || "New Conversation"}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={async () => {
                  if (!token || !activeConvId) return;
                  const result = await api.shareConversation(token, activeConvId);
                  const fullUrl = `${window.location.origin}${result.url}`;
                  navigator.clipboard.writeText(fullUrl);
                  alert("Share link copied to clipboard!");
                }}
                className="text-xs text-text-tertiary hover:text-text-secondary"
              >
                Share
              </button>
              <button
                onClick={async () => {
                  if (!token || !activeConvId) return;
                  if (confirm("Delete this conversation?")) {
                    await api.deleteConversation(token, activeConvId);
                    setActiveConvId(null);
                    setMessages([]);
                    await loadConversations();
                  }
                }}
                className="text-xs text-red-500 hover:text-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        )}

        {/* Chat area */}
        <AnalystChat
          messages={messages}
          streamingContent={streamingContent}
          isStreaming={isStreaming}
        />

        {/* Input */}
        <AnalystInput
          onSend={(msg) => sendMessage(msg)}
          onGenerateReport={handleGenerateReport}
          isStreaming={isStreaming}
          hasMessages={messages.length > 0}
          isSubscriber={isSubscriber}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/insights/page.tsx
git commit -m "feat(analyst): replace insights page with AI venture analyst chat interface"
```

---

### Task 15: Shared Conversation Page

**Files:**
- Create: `frontend/app/insights/shared/[token]/page.tsx`

- [ ] **Step 1: Create shared conversation page**

Create the directory structure:

```bash
mkdir -p frontend/app/insights/shared/\[token\]
```

Create `frontend/app/insights/shared/[token]/page.tsx`:

```tsx
"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { AnalystMessage } from "@/components/analyst/AnalystMessage";
import type { AnalystSharedConversation } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SharedConversationPage() {
  const params = useParams();
  const shareToken = params.token as string;

  const [conversation, setConversation] = useState<AnalystSharedConversation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!shareToken) return;
    fetch(`${API_BASE}/api/analyst/shared/${shareToken}`)
      .then(async (res) => {
        if (!res.ok) throw new Error("Conversation not found");
        return res.json();
      })
      .then(setConversation)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [shareToken]);

  if (loading) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  if (error || !conversation) {
    return (
      <div className="text-center py-20">
        <p className="text-text-primary text-lg mb-2">Not Found</p>
        <p className="text-text-tertiary text-sm">{error || "This shared conversation doesn't exist."}</p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto py-8 px-4">
      <div className="mb-6">
        <p className="text-xs text-text-tertiary uppercase tracking-wider mb-1">Shared Conversation</p>
        <h1 className="font-serif text-2xl text-text-primary">{conversation.title}</h1>
        <p className="text-xs text-text-tertiary mt-1">
          {conversation.message_count} messages
        </p>
      </div>

      <div className="space-y-4">
        {conversation.messages.map((msg) => (
          <AnalystMessage
            key={msg.id}
            role={msg.role}
            content={msg.content}
            charts={msg.charts}
            citations={msg.citations}
          />
        ))}
      </div>

      <div className="mt-8 text-center">
        <p className="text-xs text-text-tertiary">
          Powered by Deep Thesis AI Analyst
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/insights/shared/
git commit -m "feat(analyst): add shared conversation public page"
```

---

### Task 16: ShareModal Component

**Files:**
- Create: `frontend/components/analyst/ShareModal.tsx`

- [ ] **Step 1: Create the share modal**

Create `frontend/components/analyst/ShareModal.tsx`:

```tsx
"use client";

import { useState } from "react";

interface Props {
  shareUrl: string;
  onClose: () => void;
}

export function ShareModal({ shareUrl, onClose }: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-surface border border-border rounded-lg p-6 w-full max-w-md mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-medium text-text-primary mb-3">Share Conversation</h3>
        <p className="text-xs text-text-tertiary mb-4">
          Anyone with this link can view the conversation (read-only).
        </p>

        <div className="flex gap-2">
          <input
            type="text"
            value={shareUrl}
            readOnly
            className="flex-1 px-3 py-2 text-xs bg-background border border-border rounded text-text-primary"
          />
          <button
            onClick={handleCopy}
            className="px-4 py-2 text-xs rounded bg-accent text-white hover:bg-accent-hover transition"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>

        <button
          onClick={onClose}
          className="mt-4 w-full text-center text-xs text-text-tertiary hover:text-text-secondary"
        >
          Close
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/analyst/ShareModal.tsx
git commit -m "feat(analyst): add ShareModal component"
```

---

## Self-Review

**1. Spec coverage check:**
- Architecture overview (SSE streaming + Recharts + Perplexity) → Tasks 4-5, 7, 10, 14 ✅
- Database schema (3 tables, 3 enums) → Tasks 2-3 ✅
- Conversation CRUD endpoints → Task 7 ✅
- SSE chat endpoint → Task 7 ✅
- Report endpoints → Task 7 ✅
- Share endpoints → Task 7 ✅
- Perplexity system prompt + context injection → Task 4 ✅
- Chart extraction → Task 5 ✅
- Report generation (docx + xlsx) → Task 6 ✅
- Frontend components (sidebar, chat, message, chart, input, share) → Tasks 10-13, 15-16 ✅
- Shared conversation page → Task 15 ✅
- Subscription gating → Tasks 7 (create_conversation, create_report, send_message) ✅
- Message limits (20 free / 100 subscribed, warning at 80) → Task 7 ✅
- Rate limiting (200/day) → Not implemented (deferred — can add per-day counter later)
- Error handling (Perplexity failure, invalid chart, report failure) → Tasks 5, 6, 7 ✅

**2. Placeholder scan:** No TBD, TODO, or "implement later" found. All code complete.

**3. Type consistency check:**
- `AnalystConversation` / `AnalystConversationSummary` / `AnalystConversationDetail` — consistent
- `AnalystMessage` / `AnalystMessageData` — consistent (backend model vs frontend type)
- `AnalystReport` / `AnalystReportSummary` — consistent
- `MessageRole` enum values match between model, migration, and frontend
- `ReportFormat` / `ReportGenStatus` — consistent across model, migration, API
- `stream_perplexity` yield types match what `event_stream` in API expects
- `extract_charts` return type matches usage in `stream_perplexity`
- `build_system_prompt` signature matches call in API endpoint
- `generate_report` signature matches `background_tasks.add_task` call
- Frontend `api.streamMessage` returns raw fetch Response (correct for SSE)
- Chart config shape (`type, title, data, xKey, yKeys, colors`) consistent everywhere
