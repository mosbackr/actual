# Investor Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an admin batch process that uses Perplexity to find ~200 prospective investors per pre-seed/seed startup, store them deduplicated, and provide an admin UI to browse/filter results.

**Architecture:** New `investors` and `investor_batch_jobs` tables. A background service calls Perplexity for each eligible startup, deduplicates on (firm_name, partner_name), and tracks progress. Admin frontend gets a new Investors page with batch controls and a searchable DataTable.

**Tech Stack:** SQLAlchemy + Alembic (backend models/migration), FastAPI (API endpoints), httpx + Perplexity Sonar Pro (investor research), Next.js + React (admin frontend), DataTable component (list view).

---

## File Structure

### Backend — New Files
- `backend/alembic/versions/v1w2x3y4z5a6_add_investors_tables.py` — Migration
- `backend/app/models/investor.py` — Investor + InvestorBatchJob models
- `backend/app/services/investor_extraction.py` — Perplexity extraction service
- `backend/app/api/admin_investors.py` — Admin API endpoints

### Backend — Modified Files
- `backend/app/main.py` — Register investor router

### Admin Frontend — New Files
- `admin/app/investors/page.tsx` — Investors list page with batch controls

### Admin Frontend — Modified Files
- `admin/components/Sidebar.tsx` — Add "Investors" nav link
- `admin/lib/types.ts` — Add Investor and batch job types
- `admin/lib/api.ts` — Add investor API methods

---

### Task 1: Database Migration

**Files:**
- Create: `backend/alembic/versions/v1w2x3y4z5a6_add_investors_tables.py`

- [ ] **Step 1: Create migration file**

```python
"""Add investors and investor_batch_jobs tables

Revision ID: v1w2x3y4z5a6
Revises: u9v0w1x2y3z4
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "v1w2x3y4z5a6"
down_revision = "u9v0w1x2y3z4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("firm_name", sa.String(300), nullable=False),
        sa.Column("partner_name", sa.String(300), nullable=False),
        sa.Column("email", sa.String(300), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("stage_focus", sa.String(200), nullable=True),
        sa.Column("sector_focus", sa.String(500), nullable=True),
        sa.Column("location", sa.String(300), nullable=True),
        sa.Column("aum_fund_size", sa.String(100), nullable=True),
        sa.Column("recent_investments", JSON, nullable=True),
        sa.Column("fit_reason", sa.Text, nullable=True),
        sa.Column("source_startups", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("firm_name", "partner_name", name="uq_investor_firm_partner"),
    )
    op.create_index("ix_investors_firm_name", "investors", ["firm_name"])
    op.create_index("ix_investors_sector_focus", "investors", ["sector_focus"])

    op.create_table(
        "investor_batch_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("total_startups", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("processed_startups", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("current_startup_id", UUID(as_uuid=True), nullable=True),
        sa.Column("current_startup_name", sa.String(300), nullable=True),
        sa.Column("investors_found", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("investor_batch_jobs")
    op.drop_index("ix_investors_sector_focus", table_name="investors")
    op.drop_index("ix_investors_firm_name", table_name="investors")
    op.drop_table("investors")
```

- [ ] **Step 2: Commit**

```bash
git add backend/alembic/versions/v1w2x3y4z5a6_add_investors_tables.py
git commit -m "feat(investors): add investors and batch_jobs migration"
```

---

### Task 2: SQLAlchemy Models

**Files:**
- Create: `backend/app/models/investor.py`

- [ ] **Step 1: Create Investor and InvestorBatchJob models**

```python
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class BatchJobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"


class Investor(Base):
    __tablename__ = "investors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    firm_name: Mapped[str] = mapped_column(String(300), nullable=False)
    partner_name: Mapped[str] = mapped_column(String(300), nullable=False)
    email: Mapped[str | None] = mapped_column(String(300), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    stage_focus: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sector_focus: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    aum_fund_size: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recent_investments: Mapped[list | None] = mapped_column(JSON, nullable=True)
    fit_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_startups: Mapped[list] = mapped_column(
        JSON, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("firm_name", "partner_name", name="uq_investor_firm_partner"),
    )


class InvestorBatchJob(Base):
    __tablename__ = "investor_batch_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BatchJobStatus.pending.value
    )
    total_startups: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_startups: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_startup_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    current_startup_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    investors_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/investor.py
git commit -m "feat(investors): add Investor and InvestorBatchJob models"
```

---

### Task 3: Investor Extraction Service

**Files:**
- Create: `backend/app/services/investor_extraction.py`

- [ ] **Step 1: Create the extraction service**

This service handles calling Perplexity, parsing results, deduplicating, and managing batch job state. It reuses the `_call_perplexity` and `_extract_json` helpers from `enrichment.py`.

```python
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import async_session
from app.models.investor import BatchJobStatus, Investor, InvestorBatchJob
from app.models.startup import EnrichmentStatus, Startup, StartupStage, StartupStatus

logger = logging.getLogger(__name__)


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
                "max_tokens": 16000,
                "messages": messages,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _extract_json_array(text: str) -> list[dict]:
    """Extract a JSON array from fenced or bare text."""
    import re

    # Try fenced JSON first
    m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    if m:
        return json.loads(m.group(1))

    # Try bare JSON array
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        raw = text[start : end + 1]
        # Fix trailing commas
        raw = re.sub(r",\s*([}\]])", r"\1", raw)
        return json.loads(raw)

    raise ValueError("No JSON array found in response")


def _build_prompt(startup: Startup, industries: list[str], batch_num: int) -> list[dict]:
    stage_label = startup.stage.value.replace("_", "-")
    industry_str = ", ".join(industries) if industries else "Technology"
    location_parts = [p for p in [startup.location_city, startup.location_state, startup.location_country] if p]
    location_str = ", ".join(location_parts) if location_parts else "United States"

    avoid_clause = ""
    if batch_num == 2:
        avoid_clause = (
            "\n\nIMPORTANT: This is batch 2. Return DIFFERENT investors than you would normally "
            "list first. Focus on emerging managers, smaller funds, solo GPs, angel syndicates, "
            "and less obvious but still active investors in this space. Avoid the most well-known "
            "firms — those were covered in batch 1."
        )

    system_msg = (
        "You are a venture capital research analyst with deep knowledge of the investor landscape. "
        "Your job is to identify investors who would be interested in a specific startup. "
        "Return ONLY a JSON array of investor objects. No commentary, no markdown — just the JSON array."
    )

    user_msg = f"""Find 100 venture capital firms and angel investors that would be interested in investing in this company:

Company: {startup.name}
Description: {startup.description or 'N/A'}
Stage: {stage_label}
Industry: {industry_str}
Location: {location_str}
Website: {startup.website_url or 'N/A'}
Total Funding: {startup.total_funding or 'N/A'}

For each investor, return a JSON object with these exact keys:
- "firm_name": string — The VC firm or angel investor organization name
- "partner_name": string — The specific partner or person who leads deals at this stage
- "email": string or null — Their professional email if publicly available
- "website": string or null — Firm website URL
- "stage_focus": string — What stages they typically invest in (e.g. "Pre-Seed, Seed")
- "sector_focus": string — What sectors/industries they focus on
- "location": string — Where the firm is based
- "aum_fund_size": string or null — Approximate fund size or AUM if known
- "recent_investments": array of strings — 3-5 recent notable investments
- "fit_reason": string — One sentence on why this investor would be interested in this specific company

Return exactly 100 investor objects in a JSON array.
Focus on investors who actively invest in {stage_label} stage companies in the {industry_str} space.
Include a mix of well-known firms and emerging/smaller funds.{avoid_clause}"""

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


async def _upsert_investors(
    db: AsyncSession,
    investors_data: list[dict],
    startup_id: str,
    startup_name: str,
) -> int:
    """Insert or update investors. Returns count of new investors inserted."""
    new_count = 0
    source_entry = {"id": startup_id, "name": startup_name}

    for inv in investors_data:
        firm = (inv.get("firm_name") or "").strip()
        partner = (inv.get("partner_name") or "").strip()
        if not firm or not partner:
            continue

        # Check for existing
        result = await db.execute(
            select(Investor).where(
                Investor.firm_name == firm,
                Investor.partner_name == partner,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Append source startup if not already there
            sources = existing.source_startups or []
            if not any(s.get("id") == startup_id for s in sources):
                sources.append(source_entry)
                existing.source_startups = sources
            # Update fields if current data is richer
            if inv.get("email") and not existing.email:
                existing.email = inv["email"]
            if inv.get("website") and not existing.website:
                existing.website = inv["website"]
            if inv.get("aum_fund_size") and not existing.aum_fund_size:
                existing.aum_fund_size = inv["aum_fund_size"]
            existing.updated_at = datetime.now(timezone.utc)
        else:
            investor = Investor(
                firm_name=firm,
                partner_name=partner,
                email=inv.get("email"),
                website=inv.get("website"),
                stage_focus=inv.get("stage_focus"),
                sector_focus=inv.get("sector_focus"),
                location=inv.get("location"),
                aum_fund_size=inv.get("aum_fund_size"),
                recent_investments=inv.get("recent_investments"),
                fit_reason=inv.get("fit_reason"),
                source_startups=[source_entry],
            )
            db.add(investor)
            new_count += 1

    await db.commit()
    return new_count


async def _process_startup(
    db: AsyncSession,
    startup: Startup,
    industries: list[str],
) -> int:
    """Run 2 Perplexity calls for a startup, return total investors upserted."""
    total = 0
    startup_id = str(startup.id)

    for batch_num in (1, 2):
        messages = _build_prompt(startup, industries, batch_num)

        for attempt in range(2):
            try:
                raw = await _call_perplexity(messages, timeout=120)
                investors_data = _extract_json_array(raw)
                count = await _upsert_investors(db, investors_data, startup_id, startup.name)
                total += count
                logger.info(
                    f"Batch {batch_num} for {startup.name}: {len(investors_data)} returned, {count} new"
                )
                break
            except (json.JSONDecodeError, ValueError) as e:
                if attempt == 0:
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({
                        "role": "user",
                        "content": "Your response was not valid JSON. Return ONLY a JSON array of investor objects, no other text.",
                    })
                else:
                    logger.error(f"Batch {batch_num} JSON parse failed for {startup.name}: {e}")
            except Exception as e:
                logger.error(f"Batch {batch_num} failed for {startup.name}: {e}")
                break

    return total


async def run_investor_batch(job_id: str) -> None:
    """Main batch loop. Processes all eligible startups, checking for pause between each."""
    db_factory = async_session

    # Load job
    async with db_factory() as db:
        job = await db.get(InvestorBatchJob, uuid.UUID(job_id))
        if not job:
            logger.error(f"Batch job {job_id} not found")
            return
        job.status = BatchJobStatus.running.value
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # Load eligible startups
    async with db_factory() as db:
        from sqlalchemy.orm import selectinload

        result = await db.execute(
            select(Startup)
            .options(selectinload(Startup.industries))
            .where(
                Startup.stage.in_([StartupStage.pre_seed, StartupStage.seed]),
                Startup.status.in_([StartupStatus.approved, StartupStatus.featured]),
                Startup.enrichment_status == EnrichmentStatus.complete,
            )
            .order_by(Startup.created_at.asc())
        )
        startups = result.scalars().all()
        # Detach data we need so we can use it outside this session
        startup_data = [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "stage": s.stage,
                "website_url": s.website_url,
                "location_city": s.location_city,
                "location_state": s.location_state,
                "location_country": s.location_country,
                "total_funding": s.total_funding,
                "industries": [i.name for i in s.industries],
            }
            for s in startups
        ]

    # Update total count
    async with db_factory() as db:
        job = await db.get(InvestorBatchJob, uuid.UUID(job_id))
        job.total_startups = len(startup_data)
        await db.commit()

    # Process each startup
    for idx, sd in enumerate(startup_data):
        # Check for pause
        async with db_factory() as db:
            job = await db.get(InvestorBatchJob, uuid.UUID(job_id))
            if job.status == BatchJobStatus.paused.value:
                logger.info(f"Batch job {job_id} paused at startup {idx}")
                return

        # Skip already-processed startups (for resume)
        if idx < job.processed_startups:
            continue

        # Update current startup
        async with db_factory() as db:
            job = await db.get(InvestorBatchJob, uuid.UUID(job_id))
            job.current_startup_id = sd["id"]
            job.current_startup_name = sd["name"]
            await db.commit()

        # Build a lightweight Startup-like object for the prompt builder
        class _StartupProxy:
            pass

        proxy = _StartupProxy()
        proxy.name = sd["name"]
        proxy.description = sd["description"]
        proxy.stage = sd["stage"]
        proxy.website_url = sd["website_url"]
        proxy.location_city = sd["location_city"]
        proxy.location_state = sd["location_state"]
        proxy.location_country = sd["location_country"]
        proxy.total_funding = sd["total_funding"]

        try:
            async with db_factory() as db:
                count = await _process_startup(db, proxy, sd["industries"])
        except Exception as e:
            logger.error(f"Failed processing {sd['name']}: {e}")
            async with db_factory() as db:
                job = await db.get(InvestorBatchJob, uuid.UUID(job_id))
                errors = job.error or ""
                job.error = f"{errors}\n{sd['name']}: {e}".strip()
                await db.commit()
            count = 0

        # Update progress
        async with db_factory() as db:
            job = await db.get(InvestorBatchJob, uuid.UUID(job_id))
            job.processed_startups = idx + 1
            job.investors_found = (job.investors_found or 0) + count
            await db.commit()

        logger.info(f"Processed {idx + 1}/{len(startup_data)}: {sd['name']} (+{count} investors)")

    # Mark complete
    async with db_factory() as db:
        job = await db.get(InvestorBatchJob, uuid.UUID(job_id))
        job.status = BatchJobStatus.completed.value
        job.current_startup_id = None
        job.current_startup_name = None
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()

    logger.info(f"Batch job {job_id} complete")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/investor_extraction.py
git commit -m "feat(investors): add Perplexity investor extraction service"
```

---

### Task 4: Admin API Endpoints

**Files:**
- Create: `backend/app/api/admin_investors.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the admin investors API**

```python
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.investor import BatchJobStatus, Investor, InvestorBatchJob
from app.models.user import User

router = APIRouter()


@router.post("/api/admin/investors/batch")
async def start_investor_batch(
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Check no job is already running or paused
    result = await db.execute(
        select(InvestorBatchJob).where(
            InvestorBatchJob.status.in_([
                BatchJobStatus.running.value,
                BatchJobStatus.paused.value,
            ])
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A batch job is already {existing.status}. Pause or wait for it to finish.",
        )

    job = InvestorBatchJob()
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from app.services.investor_extraction import run_investor_batch

    background_tasks.add_task(run_investor_batch, str(job.id))

    return {
        "id": str(job.id),
        "status": job.status,
    }


@router.put("/api/admin/investors/batch/{job_id}/pause")
async def pause_investor_batch(
    job_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(InvestorBatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.running.value:
        raise HTTPException(status_code=400, detail="Job is not running")

    from datetime import datetime, timezone

    job.status = BatchJobStatus.paused.value
    job.paused_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": str(job.id), "status": job.status}


@router.put("/api/admin/investors/batch/{job_id}/resume")
async def resume_investor_batch(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(InvestorBatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.paused.value:
        raise HTTPException(status_code=400, detail="Job is not paused")

    job.status = BatchJobStatus.running.value
    await db.commit()

    from app.services.investor_extraction import run_investor_batch

    background_tasks.add_task(run_investor_batch, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.get("/api/admin/investors/batch/status")
async def get_batch_status(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InvestorBatchJob).order_by(InvestorBatchJob.created_at.desc()).limit(1)
    )
    job = result.scalar_one_or_none()
    if not job:
        return None

    return {
        "id": str(job.id),
        "status": job.status,
        "total_startups": job.total_startups,
        "processed_startups": job.processed_startups,
        "current_startup_name": job.current_startup_name,
        "investors_found": job.investors_found,
        "error": job.error,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "paused_at": job.paused_at.isoformat() if job.paused_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/api/admin/investors")
async def list_investors(
    q: str | None = None,
    stage_focus: str | None = None,
    sector_focus: str | None = None,
    location: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort: str = "firm_name",
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Investor)

    if q:
        like = f"%{q}%"
        query = query.where(
            Investor.firm_name.ilike(like)
            | Investor.partner_name.ilike(like)
            | Investor.email.ilike(like)
        )
    if stage_focus:
        query = query.where(Investor.stage_focus.ilike(f"%{stage_focus}%"))
    if sector_focus:
        query = query.where(Investor.sector_focus.ilike(f"%{sector_focus}%"))
    if location:
        query = query.where(Investor.location.ilike(f"%{location}%"))

    # Count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # Sort
    sort_col = {
        "firm_name": Investor.firm_name,
        "partner_name": Investor.partner_name,
        "created_at": Investor.created_at.desc(),
    }.get(sort, Investor.firm_name)
    if sort == "created_at":
        query = query.order_by(Investor.created_at.desc())
    else:
        query = query.order_by(sort_col)

    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    investors = result.scalars().all()

    pages = max(1, (total + per_page - 1) // per_page)

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "items": [
            {
                "id": str(inv.id),
                "firm_name": inv.firm_name,
                "partner_name": inv.partner_name,
                "email": inv.email,
                "website": inv.website,
                "stage_focus": inv.stage_focus,
                "sector_focus": inv.sector_focus,
                "location": inv.location,
                "aum_fund_size": inv.aum_fund_size,
                "recent_investments": inv.recent_investments,
                "fit_reason": inv.fit_reason,
                "source_startups": inv.source_startups,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in investors
        ],
    }


@router.delete("/api/admin/investors/{investor_id}")
async def delete_investor(
    investor_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    inv = await db.get(Investor, investor_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Investor not found")
    await db.delete(inv)
    await db.commit()
    return {"ok": True}
```

- [ ] **Step 2: Register the router in main.py**

In `backend/app/main.py`, add these two lines following the existing router registration pattern:

```python
from app.api.admin_investors import router as admin_investors_router
```

And in the router registration section:

```python
app.include_router(admin_investors_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin_investors.py backend/app/main.py
git commit -m "feat(investors): add admin API endpoints for investor batch + CRUD"
```

---

### Task 5: Admin Frontend Types and API Client

**Files:**
- Modify: `admin/lib/types.ts`
- Modify: `admin/lib/api.ts`

- [ ] **Step 1: Add TypeScript types to `admin/lib/types.ts`**

Add at the bottom of the file:

```typescript
export interface InvestorItem {
  id: string;
  firm_name: string;
  partner_name: string;
  email: string | null;
  website: string | null;
  stage_focus: string | null;
  sector_focus: string | null;
  location: string | null;
  aum_fund_size: string | null;
  recent_investments: string[] | null;
  fit_reason: string | null;
  source_startups: { id: string; name: string }[];
  created_at: string;
}

export interface InvestorListResponse {
  total: number;
  page: number;
  per_page: number;
  pages: number;
  items: InvestorItem[];
}

export interface InvestorBatchStatus {
  id: string;
  status: "pending" | "running" | "paused" | "completed" | "failed";
  total_startups: number;
  processed_startups: number;
  current_startup_name: string | null;
  investors_found: number;
  error: string | null;
  started_at: string | null;
  paused_at: string | null;
  completed_at: string | null;
}
```

- [ ] **Step 2: Add API methods to `admin/lib/api.ts`**

Add inside the `adminApi` object (before the closing `}`):

```typescript
  // Investors
  startInvestorBatch: (token: string) =>
    apiFetch<{ id: string; status: string }>("/api/admin/investors/batch", token, {
      method: "POST",
    }),

  pauseInvestorBatch: (token: string, jobId: string) =>
    apiFetch<{ id: string; status: string }>(`/api/admin/investors/batch/${jobId}/pause`, token, {
      method: "PUT",
    }),

  resumeInvestorBatch: (token: string, jobId: string) =>
    apiFetch<{ id: string; status: string }>(`/api/admin/investors/batch/${jobId}/resume`, token, {
      method: "PUT",
    }),

  getInvestorBatchStatus: (token: string) =>
    apiFetch<InvestorBatchStatus | null>("/api/admin/investors/batch/status", token),

  getInvestors: (token: string, params?: {
    q?: string;
    stage_focus?: string;
    sector_focus?: string;
    location?: string;
    page?: number;
    per_page?: number;
    sort?: string;
  }) => {
    const sp = new URLSearchParams();
    if (params?.q) sp.set("q", params.q);
    if (params?.stage_focus) sp.set("stage_focus", params.stage_focus);
    if (params?.sector_focus) sp.set("sector_focus", params.sector_focus);
    if (params?.location) sp.set("location", params.location);
    if (params?.page) sp.set("page", String(params.page));
    if (params?.per_page) sp.set("per_page", String(params.per_page));
    if (params?.sort) sp.set("sort", params.sort);
    const qs = sp.toString();
    return apiFetch<InvestorListResponse>(`/api/admin/investors${qs ? `?${qs}` : ""}`, token);
  },

  deleteInvestor: (token: string, investorId: string) =>
    apiFetch<{ ok: boolean }>(`/api/admin/investors/${investorId}`, token, {
      method: "DELETE",
    }),
```

Also add the import at the top of `api.ts` if types are imported from `types.ts`:

```typescript
import type { InvestorBatchStatus, InvestorListResponse } from "./types";
```

(If types.ts isn't currently imported in api.ts, check — the existing pattern may use inline types. Match whichever pattern is used.)

- [ ] **Step 3: Commit**

```bash
git add admin/lib/types.ts admin/lib/api.ts
git commit -m "feat(investors): add frontend types and API client methods"
```

---

### Task 6: Admin Sidebar Update

**Files:**
- Modify: `admin/components/Sidebar.tsx`

- [ ] **Step 1: Add "Investors" to NAV_ITEMS**

In `admin/components/Sidebar.tsx`, find the `NAV_ITEMS` array and add the Investors entry after "Startups":

```typescript
const NAV_ITEMS = [
  { href: "/", label: "Triage" },
  { href: "/scout", label: "Scout" },
  { href: "/batch", label: "Batch" },
  { href: "/edgar", label: "EDGAR" },
  { href: "/startups", label: "Startups" },
  { href: "/investors", label: "Investors" },
  { href: "/experts", label: "Experts" },
  { href: "/templates", label: "Templates" },
  { href: "/users", label: "Users" },
];
```

- [ ] **Step 2: Commit**

```bash
git add admin/components/Sidebar.tsx
git commit -m "feat(investors): add Investors link to admin sidebar"
```

---

### Task 7: Admin Investors Page

**Files:**
- Create: `admin/app/investors/page.tsx`

- [ ] **Step 1: Create the investors page**

```tsx
"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { adminApi } from "@/lib/api";
import DataTable from "@/components/DataTable";
import type { InvestorItem, InvestorBatchStatus } from "@/lib/types";

export default function InvestorsPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;

  // Batch state
  const [batchStatus, setBatchStatus] = useState<InvestorBatchStatus | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);

  // List state
  const [investors, setInvestors] = useState<InvestorItem[]>([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading, setLoading] = useState(true);

  // Expanded row
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchBatchStatus = useCallback(async () => {
    if (!token) return;
    try {
      const status = await adminApi.getInvestorBatchStatus(token);
      setBatchStatus(status);
    } catch {}
  }, [token]);

  const fetchInvestors = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await adminApi.getInvestors(token, {
        q: search || undefined,
        page,
        per_page: 50,
      });
      setInvestors(data.items);
      setTotal(data.total);
      setPages(data.pages);
    } catch {}
    setLoading(false);
  }, [token, search, page]);

  useEffect(() => {
    fetchBatchStatus();
    fetchInvestors();
  }, [fetchBatchStatus, fetchInvestors]);

  // Poll batch status while running
  useEffect(() => {
    if (!batchStatus || batchStatus.status !== "running") return;
    const interval = setInterval(() => {
      fetchBatchStatus();
      fetchInvestors();
    }, 5000);
    return () => clearInterval(interval);
  }, [batchStatus?.status, fetchBatchStatus, fetchInvestors]);

  async function startBatch() {
    if (!token) return;
    setBatchLoading(true);
    try {
      await adminApi.startInvestorBatch(token);
      await fetchBatchStatus();
    } catch (e: any) {
      alert(e.message || "Failed to start batch");
    }
    setBatchLoading(false);
  }

  async function pauseBatch() {
    if (!token || !batchStatus) return;
    setBatchLoading(true);
    try {
      await adminApi.pauseInvestorBatch(token, batchStatus.id);
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
      await adminApi.resumeInvestorBatch(token, batchStatus.id);
      await fetchBatchStatus();
    } catch (e: any) {
      alert(e.message || "Failed to resume");
    }
    setBatchLoading(false);
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setPage(1);
    setSearch(searchInput);
  }

  const isRunning = batchStatus?.status === "running";
  const isPaused = batchStatus?.status === "paused";
  const progressPct =
    batchStatus && batchStatus.total_startups > 0
      ? Math.round((batchStatus.processed_startups / batchStatus.total_startups) * 100)
      : 0;

  const columns = [
    {
      key: "firm_name",
      label: "Firm",
      sortable: true,
      render: (row: InvestorItem) => (
        <div>
          <div className="font-medium text-text-primary">{row.firm_name}</div>
          {row.website && (
            <a
              href={row.website.startsWith("http") ? row.website : `https://${row.website}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-accent hover:underline"
            >
              {row.website.replace(/^https?:\/\//, "")}
            </a>
          )}
        </div>
      ),
    },
    { key: "partner_name", label: "Partner", sortable: true },
    {
      key: "email",
      label: "Email",
      render: (row: InvestorItem) =>
        row.email ? (
          <a href={`mailto:${row.email}`} className="text-accent hover:underline text-sm">
            {row.email}
          </a>
        ) : (
          <span className="text-text-tertiary">—</span>
        ),
    },
    { key: "stage_focus", label: "Stage Focus" },
    {
      key: "sector_focus",
      label: "Sector",
      render: (row: InvestorItem) => (
        <span className="text-sm truncate max-w-[200px] block" title={row.sector_focus || ""}>
          {row.sector_focus || "—"}
        </span>
      ),
    },
    { key: "location", label: "Location" },
    {
      key: "source_startups",
      label: "Sources",
      render: (row: InvestorItem) => (
        <span className="inline-flex items-center justify-center px-2 py-0.5 rounded bg-accent/10 text-accent text-xs font-medium">
          {row.source_startups?.length || 0}
        </span>
      ),
    },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary">Investors</h1>
          <p className="text-sm text-text-secondary mt-1">
            {total.toLocaleString()} investors in database
          </p>
        </div>
      </div>

      {/* Batch Controls */}
      <div className="border border-border rounded-lg p-4 mb-6 bg-surface">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-medium text-text-primary">Investor Extraction</h2>
            <p className="text-xs text-text-tertiary mt-0.5">
              Uses Perplexity to find ~200 investors per pre-seed/seed startup
            </p>
          </div>
          <div className="flex items-center gap-2">
            {!isRunning && !isPaused && (
              <button
                onClick={startBatch}
                disabled={batchLoading}
                className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
              >
                {batchLoading ? "Starting..." : "Extract Investors"}
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
                {batchStatus.processed_startups}/{batchStatus.total_startups} startups
                {batchStatus.current_startup_name && isRunning && (
                  <> — processing <strong>{batchStatus.current_startup_name}</strong></>
                )}
                {isPaused && " — paused"}
              </span>
              <span>{batchStatus.investors_found.toLocaleString()} investors found</span>
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
            Last batch completed — {batchStatus.investors_found.toLocaleString()} investors found
            from {batchStatus.total_startups} startups
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
          placeholder="Search firm, partner, or email..."
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
          <DataTable
            columns={columns}
            data={investors}
            keyField="id"
            onRowClick={(row: InvestorItem) =>
              setExpandedId(expandedId === row.id ? null : row.id)
            }
          />

          {/* Expanded detail */}
          {expandedId && (() => {
            const inv = investors.find((i) => i.id === expandedId);
            if (!inv) return null;
            return (
              <div className="border border-border rounded-lg p-4 mt-2 mb-4 bg-surface">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-text-tertiary">AUM / Fund Size:</span>{" "}
                    <span className="text-text-primary">{inv.aum_fund_size || "—"}</span>
                  </div>
                  <div>
                    <span className="text-text-tertiary">Location:</span>{" "}
                    <span className="text-text-primary">{inv.location || "—"}</span>
                  </div>
                </div>
                {inv.fit_reason && (
                  <div className="mt-3">
                    <span className="text-xs text-text-tertiary">Fit Reason:</span>
                    <p className="text-sm text-text-primary mt-0.5">{inv.fit_reason}</p>
                  </div>
                )}
                {inv.recent_investments && inv.recent_investments.length > 0 && (
                  <div className="mt-3">
                    <span className="text-xs text-text-tertiary">Recent Investments:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {inv.recent_investments.map((ri, i) => (
                        <span
                          key={i}
                          className="px-2 py-0.5 text-xs rounded bg-background border border-border text-text-secondary"
                        >
                          {ri}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {inv.source_startups && inv.source_startups.length > 0 && (
                  <div className="mt-3">
                    <span className="text-xs text-text-tertiary">Source Startups:</span>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {inv.source_startups.map((s) => (
                        <span
                          key={s.id}
                          className="px-2 py-0.5 text-xs rounded bg-accent/10 text-accent"
                        >
                          {s.name}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })()}

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
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add admin/app/investors/page.tsx
git commit -m "feat(investors): add admin investors page with batch controls and table"
```

---

### Task 8: Deploy

- [ ] **Step 1: Rsync to EC2**

```bash
rsync -avz \
  --exclude=node_modules --exclude=.git --exclude=__pycache__ \
  --exclude=.next --exclude=.worktrees --exclude=.superpowers \
  -e "ssh -i ~/.ssh/acutal-deploy.pem" \
  /Users/leemosbacker/acutal/ ec2-user@98.89.232.52:~/acutal/
```

- [ ] **Step 2: Rebuild backend and admin containers**

```bash
ssh -i ~/.ssh/acutal-deploy.pem ec2-user@98.89.232.52 \
  "cd ~/acutal && DOCKER_BUILDKIT=0 docker compose -f docker-compose.prod.yml up -d --build backend admin"
```

- [ ] **Step 3: Run migration**

```bash
ssh -i ~/.ssh/acutal-deploy.pem ec2-user@98.89.232.52 \
  "cd ~/acutal && docker compose -f docker-compose.prod.yml exec backend alembic upgrade head"
```

- [ ] **Step 4: Verify**

- Check admin sidebar shows "Investors" link
- Click Investors page, verify it loads with empty table
- Click "Extract Investors", verify batch starts and progress shows
- Verify pause/resume works
