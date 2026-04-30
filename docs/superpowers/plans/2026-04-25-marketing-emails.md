# Marketing Email System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an admin-initiated marketing email system that lets admins generate branded HTML emails via Claude, send them to scored investors with pause/resume, and provide a public-facing score detail page with navbar integration.

**Architecture:** Backend-driven — admin UI sends a prompt to FastAPI, which calls Claude with brand constraints to generate email HTML. Batch sending follows the existing `InvestorRankingBatchJob` pattern with pause/resume. Frontend gets a new `/score/[id]` page behind auth and a navbar score badge for users with `investor` role.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Anthropic SDK, Resend, Next.js 16 (App Router), NextAuth, Tailwind CSS

**Spec:** `docs/superpowers/specs/2026-04-25-marketing-emails-design.md`

---

### Task 1: Add `investor` role to UserRole enum + migration

**Files:**
- Modify: `backend/app/models/user.py:19-22`
- Create: `backend/alembic/versions/a1b2c3d4e5f6_add_investor_role.py`

- [ ] **Step 1: Add `investor` to the UserRole enum**

In `backend/app/models/user.py`, add `investor` to the enum:

```python
class UserRole(str, enum.Enum):
    user = "user"
    expert = "expert"
    investor = "investor"
    superadmin = "superadmin"
```

- [ ] **Step 2: Create the Alembic migration**

Create `backend/alembic/versions/a1b2c3d4e5f6_add_investor_role.py`:

```python
"""Add investor role to userrole enum

Revision ID: a1b2c3d4e5f6
Revises: c3d4e5f6g7h8
Create Date: 2026-04-25
"""
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "c3d4e5f6g7h8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'investor'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; no-op
    pass
```

- [ ] **Step 3: Verify migration applies**

Run: `cd /Users/leemosbacker/acutal/backend && alembic upgrade head`
Expected: migration applies without error.

- [ ] **Step 4: Commit**

```bash
cd /Users/leemosbacker/acutal
git add backend/app/models/user.py backend/alembic/versions/a1b2c3d4e5f6_add_investor_role.py
git commit -m "feat: add investor role to UserRole enum with migration"
```

---

### Task 2: MarketingEmailJob model + migration

**Files:**
- Create: `backend/app/models/marketing.py`
- Create: `backend/alembic/versions/b2c3d4e5f6g7_add_marketing_email_jobs.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the MarketingEmailJob model**

Create `backend/app/models/marketing.py`:

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base
from app.models.investor import BatchJobStatus


class MarketingEmailJob(Base):
    __tablename__ = "marketing_email_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BatchJobStatus.pending.value
    )
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    html_template: Mapped[str] = mapped_column(Text, nullable=False)
    total_recipients: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_investor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    current_investor_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    from_address: Mapped[str] = mapped_column(
        String(255), nullable=False, default="updates@deepthesis.co"
    )
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

- [ ] **Step 2: Register the model in `__init__.py`**

Add to `backend/app/models/__init__.py`:

In imports section, add:
```python
from app.models.marketing import MarketingEmailJob
```

In `__all__` list, add:
```python
    "MarketingEmailJob",
```

- [ ] **Step 3: Create the Alembic migration**

Create `backend/alembic/versions/b2c3d4e5f6g7_add_marketing_email_jobs.py`:

```python
"""Add marketing_email_jobs table

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "b2c3d4e5f6g7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "marketing_email_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("html_template", sa.Text, nullable=False),
        sa.Column("total_recipients", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("sent_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("failed_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("current_investor_id", UUID(as_uuid=True), nullable=True),
        sa.Column("current_investor_name", sa.String(300), nullable=True),
        sa.Column("from_address", sa.String(255), nullable=False, server_default=sa.text("'updates@deepthesis.co'")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("marketing_email_jobs")
```

- [ ] **Step 4: Verify migration applies**

Run: `cd /Users/leemosbacker/acutal/backend && alembic upgrade head`
Expected: migration applies without error.

- [ ] **Step 5: Commit**

```bash
cd /Users/leemosbacker/acutal
git add backend/app/models/marketing.py backend/app/models/__init__.py backend/alembic/versions/b2c3d4e5f6g7_add_marketing_email_jobs.py
git commit -m "feat: add MarketingEmailJob model and migration"
```

---

### Task 3: Marketing email generation service

**Files:**
- Create: `backend/app/services/marketing_email.py`
- Create: `backend/tests/test_marketing_email.py`

- [ ] **Step 1: Write tests for email generation and rendering**

Create `backend/tests/test_marketing_email.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch

from app.services.marketing_email import generate_email_html, render_for_recipient


@pytest.mark.asyncio
async def test_generate_email_html_calls_anthropic():
    mock_response = AsyncMock()
    mock_response.content = [AsyncMock(text="<html><body>Hello {{score}}</body></html>")]

    with patch("app.services.marketing_email.anthropic_client") as mock_client:
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        result = await generate_email_html("Write a score notification email")

    assert "{{score}}" in result or "<html>" in result
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args
    assert "Deep Thesis" in call_kwargs.kwargs["system"]
    assert "{{score}}" in call_kwargs.kwargs["system"]
    assert "{{cta_url}}" in call_kwargs.kwargs["system"]


def test_render_for_recipient_replaces_placeholders():
    template = "<html><body>Score: {{score}} <a href='{{cta_url}}'>View</a></body></html>"

    class FakeRanking:
        overall_score = 87.3

    result = render_for_recipient(
        html_template=template,
        investor_ranking=FakeRanking(),
        investor_id="abc-123",
        frontend_url="https://www.deepthesis.org",
    )

    assert "87" in result
    assert "{{score}}" not in result
    assert "https://www.deepthesis.org/score/abc-123?ref=email" in result
    assert "{{cta_url}}" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/leemosbacker/acutal/backend && python -m pytest tests/test_marketing_email.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.marketing_email'`

- [ ] **Step 3: Implement the marketing email service**

Create `backend/app/services/marketing_email.py`:

```python
import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

BRAND_SYSTEM_PROMPT = """\
You are an email designer for Deep Thesis, an investor intelligence platform.
Generate a complete, standalone HTML email based on the user's prompt.

BRAND GUIDE:
- Background: #FAFAF8 (off-white)
- Card/container: #FFFFFF with 1px #E8E6E3 border, 4px border-radius
- Header: border-bottom 2px solid #F28C28 (orange accent)
- Text primary: #1A1A1A, secondary: #6B6B6B, tertiary: #9B9B9B
- Accent/CTA: #F28C28 (orange), hover: #D97A1E
- Score colors: green #2D6A4F (80+), gold #B8860B (60-79), gray #6B6B6B (40-59), red #A23B3B (<40)
- Heading font: Georgia, 'Times New Roman', serif
- Body font: Arial, Helvetica, sans-serif

LOGO (place in header):
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
  <td style="vertical-align: middle; padding-right: 8px;">
    <span style="display: inline-block; width: 28px; height: 28px; line-height: 28px; text-align: center; border: 2px solid #F28C28; border-radius: 50%; font-family: Georgia, 'Times New Roman', serif; font-size: 16px; font-weight: bold; color: #F28C28;">D</span>
  </td>
  <td style="vertical-align: middle;">
    <span style="font-family: Georgia, 'Times New Roman', serif; font-size: 24px; color: #1A1A1A; font-weight: normal; letter-spacing: -0.5px;">Deep Thesis</span>
  </td>
</tr></table>

CTA BUTTON STYLE:
<a href="{{cta_url}}" style="display: inline-block; padding: 14px 28px; background-color: #F28C28; color: #FFFFFF; text-decoration: none; border-radius: 4px; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: bold;">Button Text</a>

CONSTRAINTS:
- Use inline CSS only (no <style> blocks)
- Use HTML tables for layout (email-client compatibility)
- Max width 600px, centered
- Include footer: "© 2026 Deep Thesis · deepthesis.org"
- You MUST include these exact placeholders in the output: {{score}} for the investor's overall score, {{cta_url}} for the call-to-action link
- Output ONLY the HTML — no markdown fences, no commentary
"""


async def generate_email_html(prompt: str) -> str:
    """Generate branded HTML email from a free-form prompt using Claude."""
    response = await anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=BRAND_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def render_for_recipient(
    html_template: str,
    investor_ranking,
    investor_id: str,
    frontend_url: str,
) -> str:
    """Replace placeholders with actual investor data."""
    score = str(round(investor_ranking.overall_score))
    cta_url = f"{frontend_url}/score/{investor_id}?ref=email"
    return html_template.replace("{{score}}", score).replace("{{cta_url}}", cta_url)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/leemosbacker/acutal/backend && python -m pytest tests/test_marketing_email.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd /Users/leemosbacker/acutal
git add backend/app/services/marketing_email.py backend/tests/test_marketing_email.py
git commit -m "feat: add marketing email generation service with Claude integration"
```

---

### Task 4: Marketing batch send service

**Files:**
- Modify: `backend/app/services/marketing_email.py`

- [ ] **Step 1: Add the batch send function**

Append to `backend/app/services/marketing_email.py`:

```python
import uuid
from datetime import datetime, timezone

import resend
from sqlalchemy import select

from app.db.session import async_session
from app.models.investor import BatchJobStatus, Investor
from app.models.investor_ranking import InvestorRanking
from app.models.marketing import MarketingEmailJob


async def run_marketing_batch(job_id: str) -> None:
    """Send marketing emails to all scored investors with pause/resume support."""
    async with async_session() as db:
        job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
        if not job:
            logger.error(f"Marketing job {job_id} not found")
            return
        job.status = BatchJobStatus.running.value
        job.started_at = datetime.now(timezone.utc)
        await db.commit()
        # Cache job fields before session closes
        html_template = job.html_template
        job_subject = job.subject
        job_from = job.from_address

    # Load all scored investors with emails
    async with async_session() as db:
        result = await db.execute(
            select(Investor, InvestorRanking)
            .join(InvestorRanking, InvestorRanking.investor_id == Investor.id)
            .where(Investor.email.isnot(None))
            .where(Investor.email != "")
        )
        rows = result.all()

    investor_data = [
        {"investor": inv, "ranking": ranking, "idx": i}
        for i, (inv, ranking) in enumerate(rows)
    ]

    # Update total
    async with async_session() as db:
        job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
        job.total_recipients = len(investor_data)
        await db.commit()

    if not settings.resend_api_key:
        logger.warning("Resend API key not configured — skipping marketing send")
        async with async_session() as db:
            job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
            job.status = BatchJobStatus.failed.value
            job.error = "Resend API key not configured"
            await db.commit()
        return

    resend.api_key = settings.resend_api_key

    for item in investor_data:
        inv = item["investor"]
        ranking = item["ranking"]
        idx = item["idx"]

        # Check for pause
        async with async_session() as db:
            job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
            if job.status == BatchJobStatus.paused.value:
                logger.info(f"Marketing batch {job_id} paused at investor {idx}")
                return
            if idx < job.sent_count + job.failed_count:
                continue  # Skip already processed

        # Update current investor
        async with async_session() as db:
            job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
            job.current_investor_id = inv.id
            job.current_investor_name = f"{inv.firm_name} ({inv.partner_name})"
            await db.commit()

        # Render and send
        sent = 0
        failed = 0
        try:
            html = render_for_recipient(
                html_template=html_template,
                investor_ranking=ranking,
                investor_id=str(inv.id),
                frontend_url=settings.frontend_url,
            )
            resend.Emails.send({
                "from": job_from,
                "to": [inv.email],
                "subject": job_subject,
                "html": html,
            })
            sent = 1
            logger.info(f"Marketing email sent to {inv.email}")
        except Exception as e:
            failed = 1
            logger.error(f"Failed sending to {inv.email}: {e}")
            async with async_session() as db:
                job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
                errors = job.error or ""
                job.error = f"{errors}\n{inv.email}: {e}".strip()
                await db.commit()

        # Update progress
        async with async_session() as db:
            job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
            job.sent_count += sent
            job.failed_count += failed
            await db.commit()

    # Complete
    async with async_session() as db:
        job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
        job.status = BatchJobStatus.completed.value
        job.current_investor_id = None
        job.current_investor_name = None
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()

    logger.info(f"Marketing batch {job_id} completed")
```

- [ ] **Step 2: Verify imports compile**

Run: `cd /Users/leemosbacker/acutal/backend && python -c "from app.services.marketing_email import run_marketing_batch; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /Users/leemosbacker/acutal
git add backend/app/services/marketing_email.py
git commit -m "feat: add marketing batch send with pause/resume support"
```

---

### Task 5: Backend marketing API routes

**Files:**
- Create: `backend/app/api/admin_marketing.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the marketing routes**

Create `backend/app/api/admin_marketing.py`:

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.investor import BatchJobStatus
from app.models.marketing import MarketingEmailJob
from app.models.user import User

router = APIRouter()


class GenerateIn(BaseModel):
    prompt: str


class SendIn(BaseModel):
    subject: str
    html_template: str


@router.post("/api/admin/marketing/generate")
async def generate_marketing_email(
    body: GenerateIn,
    _user: User = Depends(require_role("superadmin")),
):
    from app.services.marketing_email import generate_email_html

    html = await generate_email_html(body.prompt)
    return {"html": html}


@router.post("/api/admin/marketing/send")
async def start_marketing_send(
    body: SendIn,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Check for existing running/paused job
    result = await db.execute(
        select(MarketingEmailJob).where(
            MarketingEmailJob.status.in_([
                BatchJobStatus.running.value,
                BatchJobStatus.paused.value,
            ])
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A marketing send is already {existing.status}. Pause or wait for it to finish.",
        )

    job = MarketingEmailJob(
        subject=body.subject,
        html_template=body.html_template,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from app.services.marketing_email import run_marketing_batch

    background_tasks.add_task(run_marketing_batch, str(job.id))

    return {
        "id": str(job.id),
        "status": job.status,
        "subject": job.subject,
    }


@router.post("/api/admin/marketing/jobs/{job_id}/pause")
async def pause_marketing_job(
    job_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(MarketingEmailJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.running.value:
        raise HTTPException(status_code=400, detail="Job is not running")

    job.status = BatchJobStatus.paused.value
    job.paused_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": str(job.id), "status": job.status}


@router.post("/api/admin/marketing/jobs/{job_id}/resume")
async def resume_marketing_job(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(MarketingEmailJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.paused.value:
        raise HTTPException(status_code=400, detail="Job is not paused")

    job.status = BatchJobStatus.running.value
    await db.commit()

    from app.services.marketing_email import run_marketing_batch

    background_tasks.add_task(run_marketing_batch, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.get("/api/admin/marketing/jobs")
async def list_marketing_jobs(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MarketingEmailJob).order_by(MarketingEmailJob.created_at.desc()).limit(20)
    )
    jobs = result.scalars().all()

    return [
        {
            "id": str(j.id),
            "status": j.status,
            "subject": j.subject,
            "total_recipients": j.total_recipients,
            "sent_count": j.sent_count,
            "failed_count": j.failed_count,
            "current_investor_name": j.current_investor_name,
            "from_address": j.from_address,
            "error": j.error,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "paused_at": j.paused_at.isoformat() if j.paused_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]
```

- [ ] **Step 2: Register the router in main.py**

Add to `backend/app/main.py`, after the `admin_investor_rankings_router` import:

```python
from app.api.admin_marketing import router as admin_marketing_router
```

And after the last `app.include_router(...)` line:

```python
app.include_router(admin_marketing_router)
```

- [ ] **Step 3: Verify the app starts**

Run: `cd /Users/leemosbacker/acutal/backend && python -c "from app.main import app; print('Routes OK')"`
Expected: `Routes OK`

- [ ] **Step 4: Commit**

```bash
cd /Users/leemosbacker/acutal
git add backend/app/api/admin_marketing.py backend/app/main.py
git commit -m "feat: add admin marketing API routes (generate, send, pause, resume, list)"
```

---

### Task 6: Public investor ranking endpoints

**Files:**
- Create: `backend/app/api/investor_rankings_public.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the public ranking endpoints**

Create `backend/app/api/investor_rankings_public.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
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
        "narrative": ranking.narrative,
        "scored_at": ranking.scored_at.isoformat(),
    }


@router.get("/api/investors/{investor_id}/ranking")
async def get_investor_ranking(
    investor_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get ranking for a specific investor. User must own the investor record (email match) or be superadmin."""
    investor = await db.get(Investor, investor_id)
    if not investor:
        raise HTTPException(status_code=404, detail="Investor not found")

    # Auth check: email match (case-insensitive) or superadmin
    if user.role.value != "superadmin":
        if not investor.email or investor.email.lower() != user.email.lower():
            raise HTTPException(status_code=403, detail="Not authorized to view this score")

    result = await db.execute(
        select(InvestorRanking).where(InvestorRanking.investor_id == investor_id)
    )
    ranking = result.scalar_one_or_none()
    if not ranking:
        raise HTTPException(status_code=404, detail="No ranking found for this investor")

    return _ranking_response(ranking, investor)


@router.get("/api/investors/me/ranking")
async def get_my_ranking(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get ranking for the currently authenticated user's linked investor record."""
    result = await db.execute(
        select(InvestorRanking, Investor)
        .join(Investor, InvestorRanking.investor_id == Investor.id)
        .where(func.lower(Investor.email) == user.email.lower())
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="No investor ranking found for your account")

    ranking, investor = row
    return _ranking_response(ranking, investor)
```

- [ ] **Step 2: Register the router in main.py**

Add to `backend/app/main.py`, after the `admin_marketing_router` import:

```python
from app.api.investor_rankings_public import router as investor_rankings_public_router
```

And after the last `app.include_router(...)` line:

```python
app.include_router(investor_rankings_public_router)
```

- [ ] **Step 3: Verify the app starts**

Run: `cd /Users/leemosbacker/acutal/backend && python -c "from app.main import app; print('Routes OK')"`
Expected: `Routes OK`

- [ ] **Step 4: Commit**

```bash
cd /Users/leemosbacker/acutal
git add backend/app/api/investor_rankings_public.py backend/app/main.py
git commit -m "feat: add public investor ranking endpoints (by ID and /me)"
```

---

### Task 7: Investor role assignment on signup and login

**Files:**
- Modify: `backend/app/api/public_auth.py`

- [ ] **Step 1: Add investor role check helper**

Add after the `verify_password` function in `backend/app/api/public_auth.py`:

```python
from app.models.investor import Investor

async def _maybe_assign_investor_role(user: User, db: AsyncSession) -> None:
    """Upgrade user to investor role if their email matches a scored investor."""
    if user.role not in (UserRole.user, UserRole.investor):
        return  # Don't downgrade expert/admin/superadmin
    result = await db.execute(
        select(Investor).where(func.lower(Investor.email) == user.email.lower())
    )
    investor = result.scalar_one_or_none()
    if investor and user.role == UserRole.user:
        user.role = UserRole.investor
        await db.commit()
```

Also add `func` to the sqlalchemy import:
```python
from sqlalchemy import func, select
```

- [ ] **Step 2: Call the helper on register**

In the `register` endpoint, after `await db.refresh(user)` and before the `send_welcome` call, add:

```python
    await _maybe_assign_investor_role(user, db)
```

- [ ] **Step 3: Call the helper on login**

In the `login` endpoint, after the password verification succeeds and before the return, add:

```python
    await _maybe_assign_investor_role(user, db)
```

- [ ] **Step 4: Add the UserRole import if not already present**

Ensure `UserRole` is imported. Currently `User` and `UserRole` should both be available via the existing import: `from app.models.user import AuthProvider, SubscriptionStatus, SubscriptionTier, User`. Add `UserRole`:

```python
from app.models.user import AuthProvider, SubscriptionStatus, SubscriptionTier, User, UserRole
```

- [ ] **Step 5: Verify the app starts**

Run: `cd /Users/leemosbacker/acutal/backend && python -c "from app.api.public_auth import router; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
cd /Users/leemosbacker/acutal
git add backend/app/api/public_auth.py
git commit -m "feat: auto-assign investor role on signup/login when email matches investor record"
```

---

### Task 8: Add `marketing_email_from` to backend config

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add marketing email config**

Add to `backend/app/config.py` in the `Settings` class, after the `email_from` line:

```python
    marketing_email_from: str = "updates@deepthesis.co"
```

- [ ] **Step 2: Update the batch send service to use the config**

In `backend/app/services/marketing_email.py`, update the `MarketingEmailJob` default from_address. The model already defaults to `updates@deepthesis.co`, so this config is for the batch sender to reference. In `run_marketing_batch`, the `job.from_address` is already used. No change needed — the config is for future flexibility.

- [ ] **Step 3: Commit**

```bash
cd /Users/leemosbacker/acutal
git add backend/app/config.py
git commit -m "feat: add marketing_email_from config setting"
```

---

### Task 9: Admin types and API client for marketing

**Files:**
- Modify: `admin/lib/types.ts`
- Modify: `admin/lib/api.ts`

- [ ] **Step 1: Add marketing types to `admin/lib/types.ts`**

Append to `admin/lib/types.ts`:

```typescript
// ── Marketing ─────────────────────────────────────────────────────────

export interface MarketingJob {
  id: string;
  status: "pending" | "running" | "paused" | "completed" | "failed";
  subject: string;
  total_recipients: number;
  sent_count: number;
  failed_count: number;
  current_investor_name: string | null;
  from_address: string;
  error: string | null;
  started_at: string | null;
  paused_at: string | null;
  completed_at: string | null;
  created_at: string | null;
}
```

- [ ] **Step 2: Add marketing API methods to `admin/lib/api.ts`**

Add the `MarketingJob` import to the imports at the top of the file:

```typescript
import type {
  // ... existing imports ...
  MarketingJob,
} from "./types";
```

Add these methods to the `adminApi` object, after the `rescoreInvestor` method:

```typescript
  // Marketing
  generateMarketingEmail: (token: string, prompt: string) =>
    apiFetch<{ html: string }>("/api/admin/marketing/generate", token, {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),

  startMarketingSend: (token: string, subject: string, htmlTemplate: string) =>
    apiFetch<{ id: string; status: string; subject: string }>("/api/admin/marketing/send", token, {
      method: "POST",
      body: JSON.stringify({ subject, html_template: htmlTemplate }),
    }),

  pauseMarketingJob: (token: string, jobId: string) =>
    apiFetch<{ id: string; status: string }>(`/api/admin/marketing/jobs/${jobId}/pause`, token, {
      method: "POST",
    }),

  resumeMarketingJob: (token: string, jobId: string) =>
    apiFetch<{ id: string; status: string }>(`/api/admin/marketing/jobs/${jobId}/resume`, token, {
      method: "POST",
    }),

  getMarketingJobs: (token: string) =>
    apiFetch<MarketingJob[]>("/api/admin/marketing/jobs", token),
```

- [ ] **Step 3: Commit**

```bash
cd /Users/leemosbacker/acutal
git add admin/lib/types.ts admin/lib/api.ts
git commit -m "feat: add marketing types and API client methods to admin"
```

---

### Task 10: Admin marketing page

**Files:**
- Create: `admin/app/marketing/page.tsx`

**Note:** Check `node_modules/next/dist/docs/` for any Next.js 16 API changes before writing the page. Follow the same patterns as `admin/app/investors/rankings/page.tsx`.

- [ ] **Step 1: Create the marketing page**

Create `admin/app/marketing/page.tsx`:

```tsx
"use client";

import { useEffect, useState, useCallback } from "react";
import { useSession } from "next-auth/react";
import { adminApi } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { AccessDenied } from "@/components/AccessDenied";
import type { MarketingJob } from "@/lib/types";

export default function MarketingPage() {
  const { data: session, status } = useSession();
  const token = session?.backendToken;

  const [prompt, setPrompt] = useState("");
  const [subject, setSubject] = useState("Someone has scored you as an investor");
  const [generatedHtml, setGeneratedHtml] = useState("");
  const [generating, setGenerating] = useState(false);

  const [jobs, setJobs] = useState<MarketingJob[]>([]);
  const [sendLoading, setSendLoading] = useState(false);
  const [jobActionLoading, setJobActionLoading] = useState(false);

  const fetchJobs = useCallback(async () => {
    if (!token) return;
    try {
      const data = await adminApi.getMarketingJobs(token);
      setJobs(data);
    } catch {}
  }, [token]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  // Poll running jobs
  const activeJob = jobs.find((j) => j.status === "running");
  useEffect(() => {
    if (!activeJob) return;
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, [activeJob, fetchJobs]);

  async function handleGenerate() {
    if (!token || !prompt.trim()) return;
    setGenerating(true);
    try {
      const { html } = await adminApi.generateMarketingEmail(token, prompt);
      setGeneratedHtml(html);
    } catch (e: any) {
      alert(e.message || "Generation failed");
    }
    setGenerating(false);
  }

  async function handleSend() {
    if (!token || !generatedHtml || !subject.trim()) return;
    if (!confirm("Send this email to ALL scored investors?")) return;
    setSendLoading(true);
    try {
      await adminApi.startMarketingSend(token, subject, generatedHtml);
      await fetchJobs();
    } catch (e: any) {
      alert(e.message || "Failed to start send");
    }
    setSendLoading(false);
  }

  async function handlePause(jobId: string) {
    if (!token) return;
    setJobActionLoading(true);
    try {
      await adminApi.pauseMarketingJob(token, jobId);
      await fetchJobs();
    } catch (e: any) {
      alert(e.message || "Failed to pause");
    }
    setJobActionLoading(false);
  }

  async function handleResume(jobId: string) {
    if (!token) return;
    setJobActionLoading(true);
    try {
      await adminApi.resumeMarketingJob(token, jobId);
      await fetchJobs();
    } catch (e: any) {
      alert(e.message || "Failed to resume");
    }
    setJobActionLoading(false);
  }

  if (status === "loading") return null;
  if (!session || (session as any).role !== "superadmin") return <AccessDenied />;

  const previewHtml = generatedHtml
    .replace(/\{\{score\}\}/g, "85")
    .replace(/\{\{cta_url\}\}/g, "https://www.deepthesis.org/score/example");

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <h1 className="text-2xl font-semibold text-text-primary mb-6">Marketing Emails</h1>

        {/* Composer + Preview */}
        <div className="grid grid-cols-2 gap-6 mb-6">
          {/* Left: Composer */}
          <div className="border border-border rounded-lg p-4 bg-surface">
            <h2 className="text-sm font-medium text-text-primary mb-3">Email Composer</h2>
            <label className="block text-xs text-text-secondary mb-1">Subject Line</label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full px-3 py-2 border border-border rounded bg-background text-text-primary text-sm placeholder:text-text-tertiary focus:outline-none focus:border-accent mb-3"
            />
            <label className="block text-xs text-text-secondary mb-1">Prompt</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Write an email telling investors they've been scored. Professional tone, emphasize their overall score..."
              rows={6}
              className="w-full px-3 py-2 border border-border rounded bg-background text-text-primary text-sm placeholder:text-text-tertiary focus:outline-none focus:border-accent resize-none"
            />
            <button
              onClick={handleGenerate}
              disabled={generating || !prompt.trim()}
              className="mt-3 px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
            >
              {generating ? "Generating..." : "Generate Email"}
            </button>
          </div>

          {/* Right: Preview */}
          <div className="border border-border rounded-lg bg-surface flex flex-col">
            <div className="px-4 py-3 border-b border-border">
              <h2 className="text-sm font-medium text-text-primary">Preview</h2>
              <p className="text-xs text-text-tertiary">Sample data: score=85</p>
            </div>
            <div className="flex-1 p-1">
              {generatedHtml ? (
                <iframe
                  srcDoc={previewHtml}
                  sandbox=""
                  className="w-full h-full min-h-[400px] border-0 rounded"
                  title="Email preview"
                />
              ) : (
                <div className="flex items-center justify-center h-full min-h-[400px] text-text-tertiary text-sm">
                  Generate an email to see the preview
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Send Controls */}
        {generatedHtml && (
          <div className="border border-border rounded-lg p-4 bg-surface mb-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-medium text-text-primary">Send</h2>
                <p className="text-xs text-text-tertiary mt-0.5">
                  From: updates@deepthesis.co
                </p>
              </div>
              <button
                onClick={handleSend}
                disabled={sendLoading || !!activeJob}
                className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
              >
                {sendLoading ? "Starting..." : "Send to All Scored Investors"}
              </button>
            </div>
          </div>
        )}

        {/* Active Job Progress */}
        {jobs.filter((j) => j.status === "running" || j.status === "paused").map((job) => {
          const progressPct =
            job.total_recipients > 0
              ? Math.round(((job.sent_count + job.failed_count) / job.total_recipients) * 100)
              : 0;
          const isRunning = job.status === "running";
          const isPaused = job.status === "paused";

          return (
            <div key={job.id} className="border border-border rounded-lg p-4 bg-surface mb-6">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h2 className="text-sm font-medium text-text-primary">{job.subject}</h2>
                  <p className="text-xs text-text-tertiary mt-0.5">
                    {job.sent_count} sent, {job.failed_count} failed of {job.total_recipients}
                    {job.current_investor_name && isRunning && (
                      <> — sending to <strong>{job.current_investor_name}</strong></>
                    )}
                    {isPaused && " — paused"}
                  </p>
                </div>
                <div className="flex gap-2">
                  {isRunning && (
                    <button
                      onClick={() => handlePause(job.id)}
                      disabled={jobActionLoading}
                      className="px-4 py-2 border border-border text-text-secondary text-sm rounded hover:border-text-tertiary transition disabled:opacity-50"
                    >
                      Pause
                    </button>
                  )}
                  {isPaused && (
                    <button
                      onClick={() => handleResume(job.id)}
                      disabled={jobActionLoading}
                      className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
                    >
                      Resume
                    </button>
                  )}
                </div>
              </div>
              <div className="w-full bg-background rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all ${isPaused ? "bg-text-tertiary" : "bg-accent"}`}
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>
          );
        })}

        {/* Job History */}
        <div className="border border-border rounded-lg bg-surface">
          <div className="px-4 py-3 border-b border-border">
            <h2 className="text-sm font-medium text-text-primary">Send History</h2>
          </div>
          {jobs.length === 0 ? (
            <p className="px-4 py-8 text-center text-text-tertiary text-sm">
              No marketing emails sent yet.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-4 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Subject</th>
                  <th className="text-left px-4 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Status</th>
                  <th className="text-center px-4 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Sent</th>
                  <th className="text-center px-4 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Failed</th>
                  <th className="text-center px-4 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Total</th>
                  <th className="text-left px-4 py-3 text-xs uppercase tracking-wider text-text-secondary font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id} className="border-b border-border hover:bg-hover-row transition-colors">
                    <td className="px-4 py-3 text-text-primary">{job.subject}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`text-xs px-2 py-1 rounded ${
                          job.status === "completed"
                            ? "bg-green-50 text-green-700"
                            : job.status === "running"
                            ? "bg-orange-50 text-orange-700"
                            : job.status === "paused"
                            ? "bg-gray-100 text-gray-600"
                            : job.status === "failed"
                            ? "bg-red-50 text-red-700"
                            : "bg-gray-50 text-gray-500"
                        }`}
                      >
                        {job.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center text-text-primary tabular-nums">{job.sent_count}</td>
                    <td className="px-4 py-3 text-center text-red-400 tabular-nums">{job.failed_count}</td>
                    <td className="px-4 py-3 text-center text-text-tertiary tabular-nums">{job.total_recipients}</td>
                    <td className="px-4 py-3 text-xs text-text-tertiary">
                      {job.created_at ? new Date(job.created_at).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Verify the page compiles**

Run: `cd /Users/leemosbacker/acutal/admin && npx next build --no-lint 2>&1 | head -30` (or just check for TypeScript errors: `npx tsc --noEmit 2>&1 | head -20`)

- [ ] **Step 3: Commit**

```bash
cd /Users/leemosbacker/acutal
git add admin/app/marketing/page.tsx
git commit -m "feat: add admin marketing email page with composer, preview, and send controls"
```

---

### Task 11: Add Marketing to admin sidebar

**Files:**
- Modify: `admin/components/Sidebar.tsx:8-19`

- [ ] **Step 1: Add the Marketing nav item**

In `admin/components/Sidebar.tsx`, add `{ href: "/marketing", label: "Marketing" }` to the `NAV_ITEMS` array. Place it after `Feedback`:

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
  { href: "/feedback", label: "Feedback" },
  { href: "/marketing", label: "Marketing" },
];
```

- [ ] **Step 2: Commit**

```bash
cd /Users/leemosbacker/acutal
git add admin/components/Sidebar.tsx
git commit -m "feat: add Marketing link to admin sidebar"
```

---

### Task 12: Frontend score detail page

**Files:**
- Create: `frontend/app/score/[id]/page.tsx`

**Note:** Check `node_modules/next/dist/docs/` for Next.js 16 dynamic route and auth patterns before writing the page. Follow existing patterns from the frontend app.

- [ ] **Step 1: Create the score detail page**

Create `frontend/app/score/[id]/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useParams, useRouter } from "next/navigation";
import { Navbar } from "@/components/Navbar";
import { api, authHeaders } from "@/lib/api";

const DIMENSIONS = [
  { key: "portfolio_performance", label: "Portfolio Performance" },
  { key: "deal_activity", label: "Deal Activity" },
  { key: "exit_track_record", label: "Exit Track Record" },
  { key: "stage_expertise", label: "Stage Expertise" },
  { key: "sector_expertise", label: "Sector Expertise" },
  { key: "follow_on_rate", label: "Follow-on Rate" },
  { key: "network_quality", label: "Network Quality" },
] as const;

function scoreColor(score: number): string {
  if (score >= 80) return "text-[#2D6A4F]";
  if (score >= 60) return "text-[#B8860B]";
  if (score >= 40) return "text-[#6B6B6B]";
  return "text-[#A23B3B]";
}

function scoreBgColor(score: number): string {
  if (score >= 80) return "bg-[#2D6A4F]";
  if (score >= 60) return "bg-[#B8860B]";
  if (score >= 40) return "bg-[#6B6B6B]";
  return "bg-[#A23B3B]";
}

interface RankingData {
  investor_id: string;
  firm_name: string;
  partner_name: string;
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

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

export default function ScoreDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: session, status } = useSession();
  const router = useRouter();
  const [ranking, setRanking] = useState<RankingData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (status === "loading") return;
    if (!session) {
      router.push(`/auth/signin?callbackUrl=/score/${id}`);
      return;
    }

    const token = (session as any).backendToken;
    if (!token) return;

    fetch(`${API_URL}/api/investors/${id}/ranking`, {
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || `Error: ${res.status}`);
        }
        return res.json();
      })
      .then((data) => {
        setRanking(data);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [session, status, id, router]);

  if (status === "loading" || loading) {
    return (
      <>
        <Navbar />
        <div className="flex items-center justify-center min-h-[60vh]">
          <p className="text-text-tertiary text-sm">Loading...</p>
        </div>
      </>
    );
  }

  if (error) {
    return (
      <>
        <Navbar />
        <div className="flex items-center justify-center min-h-[60vh]">
          <p className="text-red-500 text-sm">{error}</p>
        </div>
      </>
    );
  }

  if (!ranking) return null;

  return (
    <>
      <Navbar />
      <div className="mx-auto max-w-4xl px-6 lg:px-8 py-10">
        {/* Header */}
        <div className="text-center mb-10">
          <p className="text-sm text-text-secondary mb-2">Investor Score</p>
          <h1 className="font-serif text-3xl text-text-primary mb-1">
            {ranking.firm_name}
          </h1>
          <p className="text-text-secondary">{ranking.partner_name}</p>
          <div className="mt-6">
            <span className={`text-6xl font-semibold tabular-nums ${scoreColor(ranking.overall_score)}`}>
              {Math.round(ranking.overall_score)}
            </span>
            <p className="text-sm text-text-tertiary mt-2">Overall Score</p>
          </div>
        </div>

        {/* Dimension Grid */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-10">
          {DIMENSIONS.map((dim) => {
            const score = ranking[dim.key] as number;
            return (
              <div
                key={dim.key}
                className="border border-border rounded-lg p-4 bg-surface"
              >
                <p className="text-xs text-text-secondary mb-2">{dim.label}</p>
                <div className="flex items-end gap-2">
                  <span className={`text-2xl font-semibold tabular-nums ${scoreColor(score)}`}>
                    {Math.round(score)}
                  </span>
                  <span className="text-xs text-text-tertiary mb-1">/ 100</span>
                </div>
                <div className="mt-2 w-full bg-background rounded-full h-1.5">
                  <div
                    className={`h-1.5 rounded-full ${scoreBgColor(score)}`}
                    style={{ width: `${Math.min(score, 100)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>

        {/* Narrative */}
        <div className="border border-border rounded-lg p-6 bg-surface">
          <h2 className="font-serif text-lg text-text-primary mb-4">Analyst Note</h2>
          <div className="text-sm text-text-primary leading-relaxed whitespace-pre-line">
            {ranking.narrative}
          </div>
          <p className="text-xs text-text-tertiary mt-4">
            Scored {new Date(ranking.scored_at).toLocaleDateString()}
          </p>
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 2: Verify the page compiles**

Run: `cd /Users/leemosbacker/acutal/frontend && npx tsc --noEmit 2>&1 | head -20`

- [ ] **Step 3: Commit**

```bash
cd /Users/leemosbacker/acutal
git add frontend/app/score/\[id\]/page.tsx
git commit -m "feat: add investor score detail page with dimension grid and narrative"
```

---

### Task 13: Frontend navbar score indicator

**Files:**
- Modify: `frontend/components/Navbar.tsx`

- [ ] **Step 1: Add score badge to the navbar**

Replace the contents of `frontend/components/Navbar.tsx` with:

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { AuthButton } from "./AuthButton";
import { NotificationBell } from "./NotificationBell";
import { WatchlistIcon } from "./WatchlistIcon";
import { LogoIcon } from "./LogoIcon";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

function scoreColor(score: number): string {
  if (score >= 80) return "text-[#2D6A4F] border-[#2D6A4F]/30 bg-[#2D6A4F]/5";
  if (score >= 60) return "text-[#B8860B] border-[#B8860B]/30 bg-[#B8860B]/5";
  if (score >= 40) return "text-[#6B6B6B] border-[#6B6B6B]/30 bg-[#6B6B6B]/5";
  return "text-[#A23B3B] border-[#A23B3B]/30 bg-[#A23B3B]/5";
}

export function Navbar() {
  const { data: session } = useSession();
  const [score, setScore] = useState<{ overall_score: number; investor_id: string } | null>(null);

  useEffect(() => {
    if (!session || (session as any).role !== "investor") return;
    const token = (session as any).backendToken;
    if (!token) return;

    fetch(`${API_URL}/api/investors/me/ranking`, {
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setScore({ overall_score: data.overall_score, investor_id: data.investor_id });
      })
      .catch(() => {});
  }, [session]);

  return (
    <nav className="border-b border-border bg-surface">
      <div className="mx-auto max-w-6xl px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-8">
            <Link href="/" className="flex items-center gap-2 font-serif text-xl text-text-primary">
              <LogoIcon size={28} />
              Deep Thesis
            </Link>
            {session && (
              <div className="hidden md:flex items-center gap-6">
                <Link href="/startups" className="text-sm text-text-secondary hover:text-text-primary transition">
                  Companies
                </Link>
                <Link href="/analyze" className="text-sm text-text-secondary hover:text-text-primary transition">
                  Analyze
                </Link>
                <Link href="/insights" className="text-sm text-text-secondary hover:text-text-primary transition">
                  Insights
                </Link>
                <Link href="/pitch-intelligence" className="text-sm text-text-secondary hover:text-text-primary transition">
                  Pitch Intel
                </Link>
                <Link
                  href="/experts/apply"
                  className="text-sm px-3 py-1 rounded border border-accent text-accent hover:bg-accent/5 transition"
                >
                  Contribute
                </Link>
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            {score && (
              <Link
                href={`/score/${score.investor_id}`}
                className={`hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium tabular-nums transition hover:opacity-80 ${scoreColor(score.overall_score)}`}
                title="Your Investor Score"
              >
                <span className="text-[10px] opacity-70">Score</span>
                {Math.round(score.overall_score)}
              </Link>
            )}
            {session && <WatchlistIcon />}
            {session && <NotificationBell />}
            <AuthButton />
          </div>
        </div>
      </div>
    </nav>
  );
}
```

- [ ] **Step 2: Verify the page compiles**

Run: `cd /Users/leemosbacker/acutal/frontend && npx tsc --noEmit 2>&1 | head -20`

- [ ] **Step 3: Commit**

```bash
cd /Users/leemosbacker/acutal
git add frontend/components/Navbar.tsx
git commit -m "feat: add investor score badge to navbar for users with investor role"
```

---

### Task 14: Final integration check

- [ ] **Step 1: Run backend tests**

Run: `cd /Users/leemosbacker/acutal/backend && python -m pytest tests/ -v --timeout=30 2>&1 | tail -20`
Expected: All tests pass

- [ ] **Step 2: Verify backend starts**

Run: `cd /Users/leemosbacker/acutal/backend && python -c "from app.main import app; print(f'{len(app.routes)} routes registered')"`
Expected: Route count increased by the new endpoints

- [ ] **Step 3: Verify admin compiles**

Run: `cd /Users/leemosbacker/acutal/admin && npx tsc --noEmit 2>&1 | head -10`
Expected: No errors

- [ ] **Step 4: Verify frontend compiles**

Run: `cd /Users/leemosbacker/acutal/frontend && npx tsc --noEmit 2>&1 | head -10`
Expected: No errors

- [ ] **Step 5: Commit any remaining fixes**

If any compilation or test issues are found, fix them and commit.
