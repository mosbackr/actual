# Email Verification & Test Send Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Hunter.io + NeverBounce email verification, test-send capability, and CAN-SPAM/GDPR-compliant unsubscribe to the marketing email system.

**Architecture:** Pre-send verification batch job validates emails via Hunter.io (person verification, email correction) and NeverBounce (deliverability), storing status on investor records. Permanently-bounced investors are flagged and skipped forever. Every email includes an HMAC-signed unsubscribe link and physical address footer. Test-send endpoint lets admins preview real personalized emails in their inbox.

**Tech Stack:** Python/FastAPI, SQLAlchemy async, Alembic, httpx (for Hunter/NeverBounce APIs), Next.js 16 (admin + frontend)

---

## File Structure

### New files
| File | Responsibility |
|------|---------------|
| `backend/app/services/email_verification.py` | Hunter.io + NeverBounce API calls, per-investor verification logic, batch runner |
| `backend/alembic/versions/d5e6f7g8h9i0_add_email_verification_columns.py` | Migration: 4 columns on investors table |
| `backend/alembic/versions/e6f7g8h9i0j1_add_email_verification_job.py` | Migration: email_verification_jobs table |
| `backend/app/api/unsubscribe.py` | Public unsubscribe endpoint (no auth) |
| `backend/tests/test_email_verification.py` | Unit tests for verification + unsubscribe |
| `frontend/app/unsubscribe/[id]/page.tsx` | Unsubscribe landing page |

### Modified files
| File | Change |
|------|--------|
| `backend/app/models/investor.py` | Add `email_status`, `email_verified_at`, `email_unsubscribed`, `email_unsubscribed_at` columns |
| `backend/app/models/marketing.py` | Add `EmailVerificationJob` model |
| `backend/app/models/__init__.py` | Register `EmailVerificationJob` |
| `backend/app/config.py` | Add `hunter_api_key`, `neverbounce_api_key`, `company_address` |
| `backend/app/services/marketing_email.py` | Update `BRAND_SYSTEM_PROMPT`, `render_for_recipient` (new placeholders), `run_marketing_batch` (skip bounced + unsubscribed) |
| `backend/app/api/admin_marketing.py` | Add verify, verify/jobs, and test-send endpoints |
| `backend/app/main.py` | Register unsubscribe router |
| `admin/lib/types.ts` | Add `VerificationJob` interface |
| `admin/lib/api.ts` | Add verification + test-send API methods |
| `admin/app/marketing/page.tsx` | Verification section, test send section, updated send button |

---

### Task 1: Add config fields

**Files:**
- Modify: `backend/app/config.py:30-33`

- [ ] **Step 1: Add the three new config fields**

In `backend/app/config.py`, add after the `marketing_email_from` line (line 33):

```python
    # Email verification
    hunter_api_key: str = ""
    neverbounce_api_key: str = ""

    # Compliance
    company_address: str = "3965 Lewis Link, New Albany, OH 43054"
```

- [ ] **Step 2: Verify backend still imports**

Run: `.venv/bin/python -c "from app.config import settings; print(settings.hunter_api_key, settings.company_address)"`
Expected: ` 3965 Lewis Link, New Albany, OH 43054`

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: add hunter, neverbounce, and company_address config fields"
```

---

### Task 2: Add investor email columns + migration

**Files:**
- Modify: `backend/app/models/investor.py:28-29`
- Create: `backend/alembic/versions/d5e6f7g8h9i0_add_email_verification_columns.py`

- [ ] **Step 1: Add columns to Investor model**

In `backend/app/models/investor.py`, add these imports at the top (add `Boolean` to the existing sqlalchemy import):

```python
from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, text
```

Then add these four columns after the `email` column (after line 28):

```python
    email_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'unverified'")
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    email_unsubscribed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    email_unsubscribed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [ ] **Step 2: Create the migration**

Create `backend/alembic/versions/d5e6f7g8h9i0_add_email_verification_columns.py`:

```python
"""Add email verification columns to investors

Revision ID: d5e6f7g8h9i0
Revises: c4d5e6f7g8h9
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa

revision = "d5e6f7g8h9i0"
down_revision = "c4d5e6f7g8h9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("investors", sa.Column("email_status", sa.String(20), nullable=False, server_default=sa.text("'unverified'")))
    op.add_column("investors", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("investors", sa.Column("email_unsubscribed", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("investors", sa.Column("email_unsubscribed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("investors", "email_unsubscribed_at")
    op.drop_column("investors", "email_unsubscribed")
    op.drop_column("investors", "email_verified_at")
    op.drop_column("investors", "email_status")
```

- [ ] **Step 3: Verify model imports**

Run: `.venv/bin/python -c "from app.models.investor import Investor; print([c.name for c in Investor.__table__.columns if 'email' in c.name])"`
Expected: `['email', 'email_status', 'email_verified_at', 'email_unsubscribed', 'email_unsubscribed_at']`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/investor.py backend/alembic/versions/d5e6f7g8h9i0_add_email_verification_columns.py
git commit -m "feat: add email verification and unsubscribe columns to investors"
```

---

### Task 3: EmailVerificationJob model + migration

**Files:**
- Modify: `backend/app/models/marketing.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/e6f7g8h9i0j1_add_email_verification_job.py`

- [ ] **Step 1: Add EmailVerificationJob to marketing.py**

Append to the end of `backend/app/models/marketing.py`:

```python


class EmailVerificationJob(Base):
    __tablename__ = "email_verification_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BatchJobStatus.pending.value
    )
    total_recipients: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verified_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    corrected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bounced_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_investor_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
```

- [ ] **Step 2: Register in __init__.py**

In `backend/app/models/__init__.py`, change the marketing import line from:

```python
from app.models.marketing import MarketingEmailJob
```

to:

```python
from app.models.marketing import MarketingEmailJob, EmailVerificationJob
```

And add `"EmailVerificationJob"` to the `__all__` list after `"MarketingEmailJob"`.

- [ ] **Step 3: Create the migration**

Create `backend/alembic/versions/e6f7g8h9i0j1_add_email_verification_job.py`:

```python
"""Add email_verification_jobs table

Revision ID: e6f7g8h9i0j1
Revises: d5e6f7g8h9i0
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "e6f7g8h9i0j1"
down_revision = "d5e6f7g8h9i0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_verification_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("total_recipients", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("verified_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("corrected_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("bounced_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("current_investor_name", sa.String(300), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("email_verification_jobs")
```

- [ ] **Step 4: Verify model imports**

Run: `.venv/bin/python -c "from app.models.marketing import EmailVerificationJob; print(EmailVerificationJob.__tablename__)"`
Expected: `email_verification_jobs`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/marketing.py backend/app/models/__init__.py backend/alembic/versions/e6f7g8h9i0j1_add_email_verification_job.py
git commit -m "feat: add EmailVerificationJob model and migration"
```

---

### Task 4: Email verification service

**Files:**
- Create: `backend/app/services/email_verification.py`
- Create: `backend/tests/test_email_verification.py`

- [ ] **Step 1: Write the tests**

Create `backend/tests/test_email_verification.py`:

```python
import hashlib
import hmac
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.config import settings


@pytest.mark.asyncio
async def test_verify_with_hunter_returns_status_and_suggestion():
    """Hunter.io returns verification result with optional suggested email."""
    from app.services.email_verification import verify_with_hunter

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "status": "valid",
            "result": "deliverable",
            "email": "john@acme.com",
        }
    }

    with patch("app.services.email_verification.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.get = AsyncMock(return_value=mock_response)
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = client_instance

        result = await verify_with_hunter("john@acme.com", "John", "Doe", "Acme Inc")

    assert result["status"] == "valid"
    assert result["suggested_email"] is None  # same email, no suggestion


@pytest.mark.asyncio
async def test_verify_with_hunter_returns_corrected_email():
    """Hunter.io returns a different email than what was submitted."""
    from app.services.email_verification import verify_with_hunter

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "status": "valid",
            "result": "deliverable",
            "email": "j.doe@acme.com",
        }
    }

    with patch("app.services.email_verification.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.get = AsyncMock(return_value=mock_response)
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = client_instance

        result = await verify_with_hunter("john@acme.com", "John", "Doe", "Acme Inc")

    assert result["status"] == "valid"
    assert result["suggested_email"] == "j.doe@acme.com"


@pytest.mark.asyncio
async def test_verify_with_neverbounce_returns_result():
    """NeverBounce returns validation result."""
    from app.services.email_verification import verify_with_neverbounce

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": "valid",
        "flags": ["has_dns", "has_dns_mx"],
    }

    with patch("app.services.email_verification.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        client_instance.get = AsyncMock(return_value=mock_response)
        client_instance.__aenter__ = AsyncMock(return_value=client_instance)
        client_instance.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = client_instance

        result = await verify_with_neverbounce("john@acme.com")

    assert result["result"] == "valid"


def test_generate_unsubscribe_url():
    """Unsubscribe URL contains investor_id and valid HMAC token."""
    from app.services.email_verification import generate_unsubscribe_url

    investor_id = "550e8400-e29b-41d4-a716-446655440000"
    url = generate_unsubscribe_url(investor_id, "https://www.deepthesis.org")

    assert f"/unsubscribe/{investor_id}" in url
    assert "token=" in url

    # Verify the token is valid
    token = url.split("token=")[1]
    expected = hmac.new(
        settings.jwt_secret.encode(), investor_id.encode(), hashlib.sha256
    ).hexdigest()
    assert token == expected


def test_verify_unsubscribe_token_valid():
    """Valid HMAC token passes verification."""
    from app.services.email_verification import verify_unsubscribe_token

    investor_id = "550e8400-e29b-41d4-a716-446655440000"
    token = hmac.new(
        settings.jwt_secret.encode(), investor_id.encode(), hashlib.sha256
    ).hexdigest()

    assert verify_unsubscribe_token(investor_id, token) is True


def test_verify_unsubscribe_token_invalid():
    """Invalid HMAC token fails verification."""
    from app.services.email_verification import verify_unsubscribe_token

    assert verify_unsubscribe_token("some-id", "bad-token") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_email_verification.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.email_verification'`

- [ ] **Step 3: Create the email verification service**

Create `backend/app/services/email_verification.py`:

```python
import hashlib
import hmac as hmac_module
import logging
import uuid
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy import select

from app.config import settings
from app.db.session import async_session
from app.models.investor import Investor
from app.models.investor_ranking import InvestorRanking
from app.models.marketing import EmailVerificationJob
from app.models.investor import BatchJobStatus

logger = logging.getLogger(__name__)

HUNTER_API_URL = "https://api.hunter.io/v2/email-verifier"
NEVERBOUNCE_API_URL = "https://api.neverbounce.com/v4/single/check"


async def verify_with_hunter(
    email: str, first_name: str, last_name: str, company: str
) -> dict:
    """Call Hunter.io Email Verifier API.

    Returns {"status": str, "suggested_email": str|None}.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            HUNTER_API_URL,
            params={
                "email": email,
                "api_key": settings.hunter_api_key,
            },
            timeout=30.0,
        )
    data = resp.json().get("data", {})
    returned_email = data.get("email", "").lower().strip()
    original_email = email.lower().strip()

    return {
        "status": data.get("status", "unknown"),
        "suggested_email": returned_email if returned_email != original_email else None,
    }


async def verify_with_neverbounce(email: str) -> dict:
    """Call NeverBounce Single Verification API.

    Returns {"result": "valid"|"invalid"|"disposable"|"catchall"|"unknown"}.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            NEVERBOUNCE_API_URL,
            params={
                "key": settings.neverbounce_api_key,
                "email": email,
            },
            timeout=30.0,
        )
    data = resp.json()
    return {"result": data.get("result", "unknown")}


def generate_unsubscribe_url(investor_id: str, frontend_url: str) -> str:
    """Generate an HMAC-signed unsubscribe URL for an investor."""
    token = hmac_module.new(
        settings.jwt_secret.encode(), investor_id.encode(), hashlib.sha256
    ).hexdigest()
    return f"{frontend_url}/unsubscribe/{investor_id}?token={token}"


def verify_unsubscribe_token(investor_id: str, token: str) -> bool:
    """Verify an HMAC unsubscribe token."""
    expected = hmac_module.new(
        settings.jwt_secret.encode(), investor_id.encode(), hashlib.sha256
    ).hexdigest()
    return hmac_module.compare_digest(token, expected)


async def run_verification_batch(job_id: str) -> None:
    """Verify emails for all scored investors via Hunter.io + NeverBounce.

    Follows the same separate-session-per-DB-operation pattern as
    marketing_email.run_marketing_batch.
    """
    db_factory = async_session

    # ── 1. Mark job as running ──────────────────────────────────────────
    async with db_factory() as db:
        job = await db.get(EmailVerificationJob, uuid.UUID(job_id))
        if not job:
            logger.error(f"Verification job {job_id} not found")
            return
        job.status = BatchJobStatus.running.value
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # ── 2. Load all scored investors with non-null emails ───────────────
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    async with db_factory() as db:
        result = await db.execute(
            select(Investor)
            .join(InvestorRanking, InvestorRanking.investor_id == Investor.id)
            .where(Investor.email.isnot(None))
            .where(Investor.email_status != "bounced")
            .order_by(Investor.firm_name.asc(), Investor.partner_name.asc())
        )
        all_investors = result.scalars().all()
        recipients = []
        skip_count = 0
        for inv in all_investors:
            # Skip recently verified investors
            if (
                inv.email_status in ("valid", "corrected")
                and inv.email_verified_at
                and inv.email_verified_at > thirty_days_ago
            ):
                skip_count += 1
                continue
            recipients.append({
                "id": inv.id,
                "firm_name": inv.firm_name,
                "partner_name": inv.partner_name,
                "email": inv.email,
            })

    # ── 3. Update job totals ────────────────────────────────────────────
    async with db_factory() as db:
        job = await db.get(EmailVerificationJob, uuid.UUID(job_id))
        job.total_recipients = len(recipients) + skip_count
        job.skipped_count = skip_count
        await db.commit()

    # ── 4. Check API keys ───────────────────────────────────────────────
    if not settings.hunter_api_key or not settings.neverbounce_api_key:
        logger.error("Hunter or NeverBounce API key not configured")
        async with db_factory() as db:
            job = await db.get(EmailVerificationJob, uuid.UUID(job_id))
            job.status = BatchJobStatus.failed.value
            job.error = "Hunter or NeverBounce API key is not configured"
            await db.commit()
        return

    # ── 5. Verify each investor ─────────────────────────────────────────
    for idx, recipient in enumerate(recipients):
        # Update progress
        async with db_factory() as db:
            job = await db.get(EmailVerificationJob, uuid.UUID(job_id))
            job.current_investor_name = (
                f"{recipient['firm_name']} ({recipient['partner_name']})"
            )
            await db.commit()

        email = recipient["email"]
        name_parts = recipient["partner_name"].strip().split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""
        was_corrected = False

        try:
            # Step A: Hunter.io verification
            hunter_result = await verify_with_hunter(
                email, first_name, last_name, recipient["firm_name"]
            )

            if hunter_result["suggested_email"]:
                email = hunter_result["suggested_email"]
                was_corrected = True
                logger.info(
                    f"Hunter corrected {recipient['email']} -> {email} "
                    f"({recipient['firm_name']})"
                )

            # Step B: NeverBounce verification
            nb_result = await verify_with_neverbounce(email)
            nb_status = nb_result["result"]

            # Step C: Update investor record
            async with db_factory() as db:
                investor = await db.get(Investor, recipient["id"])

                if nb_status in ("invalid", "disposable"):
                    investor.email_status = "bounced"
                    investor.email_verified_at = datetime.now(timezone.utc)
                    await db.commit()

                    async with db_factory() as db2:
                        job = await db2.get(EmailVerificationJob, uuid.UUID(job_id))
                        job.bounced_count += 1
                        await db2.commit()

                    logger.info(
                        f"Bounced: {email} ({recipient['firm_name']}) - {nb_status}"
                    )
                else:
                    # valid, catchall, or unknown — treat as deliverable
                    if was_corrected:
                        investor.email = email
                        investor.email_status = "corrected"
                    else:
                        investor.email_status = "valid"
                    investor.email_verified_at = datetime.now(timezone.utc)
                    await db.commit()

                    async with db_factory() as db2:
                        job = await db2.get(EmailVerificationJob, uuid.UUID(job_id))
                        if was_corrected:
                            job.corrected_count += 1
                        job.verified_count += 1
                        await db2.commit()

                    if nb_status == "unknown":
                        logger.warning(
                            f"Unknown deliverability for {email} "
                            f"({recipient['firm_name']}) - proceeding anyway"
                        )

        except Exception as e:
            logger.error(
                f"Verification failed for {email} "
                f"({recipient['firm_name']}): {e}"
            )
            # Don't fail the whole batch — skip this investor
            async with db_factory() as db:
                job = await db.get(EmailVerificationJob, uuid.UUID(job_id))
                job.skipped_count += 1
                errors = job.error or ""
                job.error = f"{errors}\n{recipient['firm_name']}: {e}".strip()
                await db.commit()

        logger.info(f"Verified {idx + 1}/{len(recipients)}: {email}")

    # ── 6. Mark job as completed ────────────────────────────────────────
    async with db_factory() as db:
        job = await db.get(EmailVerificationJob, uuid.UUID(job_id))
        job.status = BatchJobStatus.completed.value
        job.current_investor_name = None
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()

    logger.info(f"Verification batch {job_id} complete")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_email_verification.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/email_verification.py backend/tests/test_email_verification.py
git commit -m "feat: add email verification service with Hunter.io + NeverBounce"
```

---

### Task 5: Update marketing email service for compliance

**Files:**
- Modify: `backend/app/services/marketing_email.py`

- [ ] **Step 1: Update BRAND_SYSTEM_PROMPT**

In `backend/app/services/marketing_email.py`, replace the `BRAND_SYSTEM_PROMPT` string (lines 19-51) with:

```python
BRAND_SYSTEM_PROMPT = """\
You are an expert email designer for Deep Thesis, a venture-capital analytics platform.

Generate a COMPLETE, self-contained HTML email using ONLY inline CSS and table-based layout.
The email must be max-width 600px, centered, and render correctly in all major email clients
(Gmail, Outlook, Apple Mail).

Brand guidelines:
- Accent color: #F28C28 (orange)
- Background color: #FAFAF8 (warm off-white)
- Text color: #1A1A1A (near-black)
- Border color: #E8E6E3 (light warm gray)
- Font stack: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif

Logo HTML (place at the top of the email):
<table role="presentation" width="100%"><tr><td align="center" style="padding:24px 0;">
  <span style="display:inline-block;width:36px;height:36px;border-radius:50%;background:#F28C28;color:#fff;font-weight:700;font-size:18px;line-height:36px;text-align:center;vertical-align:middle;">D</span>
  <span style="font-size:20px;font-weight:700;color:#1A1A1A;vertical-align:middle;margin-left:8px;">Deep Thesis</span>
</td></tr></table>

CTA button style (orange pill):
<table role="presentation" align="center" style="margin:24px auto;"><tr><td style="background:#F28C28;border-radius:9999px;padding:12px 32px;">
  <a href="{{cta_url}}" style="color:#fff;text-decoration:none;font-weight:600;font-size:16px;">View Your Score</a>
</td></tr></table>

REQUIRED FOOTER (must appear at the bottom of EVERY email):
<table role="presentation" width="100%" style="margin-top:32px;border-top:1px solid #E8E6E3;padding-top:16px;">
<tr><td align="center" style="font-size:12px;color:#999;line-height:1.5;">
  <p>You're receiving this because you were scored on the Deep Thesis platform.</p>
  <p>{{company_address}}</p>
  <p><a href="{{unsubscribe_url}}" style="color:#999;text-decoration:underline;">Unsubscribe</a></p>
</td></tr></table>

Constraints:
- Use ONLY inline CSS (no <style> blocks)
- Use table-based layout throughout
- Max-width 600px, centered with margin: 0 auto
- Include the placeholder {{score}} where the investor's overall score should appear
- Include the placeholder {{cta_url}} where the link to the score page should appear
- Include the REQUIRED FOOTER exactly as shown above — do not omit or modify it
- Output ONLY the raw HTML, no markdown fences or explanation
"""
```

- [ ] **Step 2: Update render_for_recipient**

Replace the `render_for_recipient` function (lines 66-77) with:

```python
def render_for_recipient(
    html_template: str,
    investor_ranking: InvestorRanking,
    investor_id: uuid.UUID,
    frontend_url: str,
) -> str:
    """Replace {{score}}, {{cta_url}}, {{unsubscribe_url}}, and {{company_address}}
    placeholders with investor-specific values."""
    from app.services.email_verification import generate_unsubscribe_url

    score = str(round(investor_ranking.overall_score))
    cta_url = f"{frontend_url}/score/{investor_id}"
    unsubscribe_url = generate_unsubscribe_url(str(investor_id), frontend_url)

    html = html_template.replace("{{score}}", score)
    html = html.replace("{{cta_url}}", cta_url)
    html = html.replace("{{unsubscribe_url}}", unsubscribe_url)
    html = html.replace("{{company_address}}", settings.company_address)
    return html
```

- [ ] **Step 3: Update run_marketing_batch query to skip bounced and unsubscribed investors**

In `run_marketing_batch`, find the query that loads investors (around line 106-111):

```python
        result = await db.execute(
            select(Investor, InvestorRanking)
            .join(InvestorRanking, InvestorRanking.investor_id == Investor.id)
            .where(Investor.email.isnot(None))
            .order_by(Investor.firm_name.asc(), Investor.partner_name.asc())
        )
```

Replace with:

```python
        result = await db.execute(
            select(Investor, InvestorRanking)
            .join(InvestorRanking, InvestorRanking.investor_id == Investor.id)
            .where(Investor.email.isnot(None))
            .where(Investor.email_status != "bounced")
            .where(Investor.email_unsubscribed != True)
            .order_by(Investor.firm_name.asc(), Investor.partner_name.asc())
        )
```

- [ ] **Step 4: Update existing tests**

In `backend/tests/test_marketing_email.py`, update `test_render_for_recipient_replaces_placeholders` to account for the new placeholders. Find the test and replace it:

```python
def test_render_for_recipient_replaces_placeholders():
    from app.services.marketing_email import render_for_recipient

    class FakeRanking:
        overall_score = 82.7

    html = render_for_recipient(
        "<p>Score: {{score}}</p><a href='{{cta_url}}'>CTA</a>"
        "<a href='{{unsubscribe_url}}'>Unsub</a><p>{{company_address}}</p>",
        FakeRanking(),
        uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
        "https://example.com",
    )
    assert "Score: 83" in html
    assert "https://example.com/score/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in html
    assert "/unsubscribe/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee?token=" in html
    assert "3965 Lewis Link" in html
```

Add `import uuid` at the top of the test file if not already present.

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_marketing_email.py tests/test_email_verification.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/marketing_email.py backend/tests/test_marketing_email.py
git commit -m "feat: add compliance footer and unsubscribe URL to marketing emails"
```

---

### Task 6: Backend verification + test-send endpoints

**Files:**
- Modify: `backend/app/api/admin_marketing.py`

- [ ] **Step 1: Add test-send request model**

In `backend/app/api/admin_marketing.py`, add after the `SendRequest` class (after line 24):

```python
class TestSendRequest(BaseModel):
    email: str
    subject: str
    html_template: str
    investor_id: str
```

- [ ] **Step 2: Add verification endpoints**

Add these two endpoints at the end of `backend/app/api/admin_marketing.py`:

```python
@router.post("/api/admin/marketing/verify")
async def start_verification(
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    from app.models.marketing import EmailVerificationJob

    job = EmailVerificationJob()
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from app.services.email_verification import run_verification_batch

    background_tasks.add_task(run_verification_batch, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.get("/api/admin/marketing/verify/jobs")
async def list_verification_jobs(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    from app.models.marketing import EmailVerificationJob

    result = await db.execute(
        select(EmailVerificationJob)
        .order_by(EmailVerificationJob.created_at.desc())
        .limit(20)
    )
    jobs = result.scalars().all()

    return [
        {
            "id": str(job.id),
            "status": job.status,
            "total_recipients": job.total_recipients,
            "verified_count": job.verified_count,
            "corrected_count": job.corrected_count,
            "bounced_count": job.bounced_count,
            "skipped_count": job.skipped_count,
            "current_investor_name": job.current_investor_name,
            "error": job.error,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        }
        for job in jobs
    ]
```

- [ ] **Step 3: Add test-send endpoint**

Add this endpoint at the end of the file:

```python
@router.post("/api/admin/marketing/test-send")
async def send_test_email(
    body: TestSendRequest,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    from app.models.investor_ranking import InvestorRanking

    investor_id = uuid.UUID(body.investor_id)

    ranking = (
        await db.execute(
            select(InvestorRanking).where(InvestorRanking.investor_id == investor_id)
        )
    ).scalar_one_or_none()

    if not ranking:
        raise HTTPException(status_code=404, detail="No ranking found for this investor")

    from app.services.marketing_email import render_for_recipient
    import resend

    personalized_html = render_for_recipient(
        body.html_template, ranking, investor_id, settings.frontend_url
    )

    if not settings.resend_api_key:
        raise HTTPException(status_code=500, detail="Resend API key not configured")

    resend.api_key = settings.resend_api_key

    try:
        resend.Emails.send(
            {
                "from": settings.marketing_email_from,
                "to": [body.email],
                "subject": body.subject,
                "html": personalized_html,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send: {e}")

    return {"ok": True, "message": f"Test email sent to {body.email}"}
```

Also add `from app.config import settings` to the imports at the top of the file.

- [ ] **Step 4: Verify backend imports**

Run: `.venv/bin/python -c "from app.api.admin_marketing import router; print(len(router.routes))"`
Expected: a number (should be 8 routes now)

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/admin_marketing.py
git commit -m "feat: add email verification and test-send API endpoints"
```

---

### Task 7: Unsubscribe backend endpoint

**Files:**
- Create: `backend/app/api/unsubscribe.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the unsubscribe endpoint**

Create `backend/app/api/unsubscribe.py`:

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.db.session import get_db
from app.models.investor import Investor
from app.services.email_verification import verify_unsubscribe_token

router = APIRouter()


@router.post("/api/unsubscribe/{investor_id}")
async def unsubscribe_investor(
    investor_id: uuid.UUID,
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    if not verify_unsubscribe_token(str(investor_id), token):
        raise HTTPException(status_code=400, detail="Invalid unsubscribe token")

    investor = await db.get(Investor, investor_id)
    if not investor:
        raise HTTPException(status_code=404, detail="Investor not found")

    investor.email_unsubscribed = True
    investor.email_unsubscribed_at = datetime.now(timezone.utc)
    await db.commit()

    return {"ok": True, "message": "Successfully unsubscribed"}
```

- [ ] **Step 2: Register the router in main.py**

In `backend/app/main.py`, add after the `investor_rankings_public` import (line 75):

```python
from app.api.unsubscribe import router as unsubscribe_router
```

And add after the last `include_router` call (line 135):

```python
app.include_router(unsubscribe_router)
```

- [ ] **Step 3: Verify backend imports**

Run: `.venv/bin/python -c "from app.main import app; print(len(app.routes))"`
Expected: a number (previous was ~148, should be ~150 now)

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/unsubscribe.py backend/app/main.py
git commit -m "feat: add public unsubscribe endpoint"
```

---

### Task 8: Frontend unsubscribe page

**Files:**
- Create: `frontend/app/unsubscribe/[id]/page.tsx`

- [ ] **Step 1: Create the unsubscribe page**

Create `frontend/app/unsubscribe/[id]/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

export default function UnsubscribePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const investorId = params.id as string;
  const token = searchParams.get("token") || "";

  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (!investorId || !token) {
      setStatus("error");
      setErrorMsg("Invalid unsubscribe link.");
      return;
    }

    fetch(`${API_URL}/api/unsubscribe/${investorId}?token=${encodeURIComponent(token)}`, {
      method: "POST",
    })
      .then((res) => {
        if (res.ok) {
          setStatus("success");
        } else {
          setStatus("error");
          setErrorMsg("This unsubscribe link is invalid or has expired.");
        }
      })
      .catch(() => {
        setStatus("error");
        setErrorMsg("Something went wrong. Please try again later.");
      });
  }, [investorId, token]);

  return (
    <div className="min-h-screen bg-[#FAFAF8] flex items-center justify-center px-4">
      <div className="max-w-md w-full text-center">
        {/* Logo */}
        <div className="mb-8">
          <span
            className="inline-flex items-center justify-center w-10 h-10 rounded-full text-white font-bold text-lg"
            style={{ backgroundColor: "#F28C28" }}
          >
            D
          </span>
          <span className="ml-2 text-xl font-bold text-[#1A1A1A] align-middle">
            Deep Thesis
          </span>
        </div>

        {status === "loading" && (
          <p className="text-[#6B6B6B] text-sm">Processing your request...</p>
        )}

        {status === "success" && (
          <>
            <h1 className="text-2xl font-semibold text-[#1A1A1A] mb-3">
              You&apos;ve been unsubscribed
            </h1>
            <p className="text-[#6B6B6B] text-sm">
              You will no longer receive marketing emails from Deep Thesis.
            </p>
          </>
        )}

        {status === "error" && (
          <>
            <h1 className="text-2xl font-semibold text-[#1A1A1A] mb-3">
              Something went wrong
            </h1>
            <p className="text-[#6B6B6B] text-sm">{errorMsg}</p>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify frontend compiles**

Run: `cd /Users/leemosbacker/acutal/frontend && npx tsc --noEmit 2>&1 | grep unsubscribe`
Expected: No output (no errors from our file)

- [ ] **Step 3: Commit**

```bash
git add frontend/app/unsubscribe/[id]/page.tsx
git commit -m "feat: add unsubscribe landing page"
```

---

### Task 9: Admin types and API client additions

**Files:**
- Modify: `admin/lib/types.ts`
- Modify: `admin/lib/api.ts`

- [ ] **Step 1: Add VerificationJob type**

In `admin/lib/types.ts`, add at the end of the file:

```typescript

// ── Email Verification ──────────────────────────────────────────────

export interface VerificationJob {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  total_recipients: number;
  verified_count: number;
  corrected_count: number;
  bounced_count: number;
  skipped_count: number;
  current_investor_name: string | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
}
```

- [ ] **Step 2: Add VerificationJob to api.ts imports**

In `admin/lib/api.ts`, add `VerificationJob` to the import list:

```typescript
import type {
  AdminStartup,
  AdminUser,
  AIReview,
  ApprovedExpert,
  Assignment,
  CreateStartupInput,
  DDTemplate,
  Dimension,
  EnrichmentStatusResponse,
  ExpertApplication,
  FeedbackItem,
  FeedbackListResponse,
  InvestorBatchStatus,
  InvestorListResponse,
  MarketingJob,
  PipelineStartup,
  RankedInvestorListResponse,
  RankingBatchStatus,
  ScoutAddResponse,
  ScoutChatResponse,
  StartupCandidate,
  StartupDetail,
  StartupFullDetail,
  VerificationJob,
} from "./types";
```

- [ ] **Step 3: Add API methods**

In `admin/lib/api.ts`, add these methods inside the `adminApi` object, after the `getMarketingJobs` method:

```typescript
  startVerification: (token: string) =>
    apiFetch<{ id: string; status: string }>("/api/admin/marketing/verify", token, {
      method: "POST",
    }),

  getVerificationJobs: (token: string) =>
    apiFetch<VerificationJob[]>("/api/admin/marketing/verify/jobs", token),

  sendTestEmail: (token: string, email: string, subject: string, htmlTemplate: string, investorId: string) =>
    apiFetch<{ ok: boolean; message: string }>("/api/admin/marketing/test-send", token, {
      method: "POST",
      body: JSON.stringify({ email, subject, html_template: htmlTemplate, investor_id: investorId }),
    }),
```

- [ ] **Step 4: Verify admin compiles**

Run: `cd /Users/leemosbacker/acutal/admin && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add admin/lib/types.ts admin/lib/api.ts
git commit -m "feat: add verification and test-send types and API methods to admin"
```

---

### Task 10: Admin marketing page — verification section

**Files:**
- Modify: `admin/app/marketing/page.tsx`

- [ ] **Step 1: Add verification state and fetch logic**

In `admin/app/marketing/page.tsx`, add to the imports at the top:

```typescript
import type { MarketingJob, VerificationJob } from "@/lib/types";
```

(Replace the existing `import type { MarketingJob } from "@/lib/types";` line.)

Add verification state after the jobs state (after line 41):

```typescript
  // Verification state
  const [verificationJobs, setVerificationJobs] = useState<VerificationJob[]>([]);
  const [verifying, setVerifying] = useState(false);
```

Add a `fetchVerificationJobs` callback after `fetchJobs`:

```typescript
  const fetchVerificationJobs = useCallback(async () => {
    if (!token) return;
    try {
      const data = await adminApi.getVerificationJobs(token);
      setVerificationJobs(data);
    } catch (e) {
      console.error("Failed to load verification jobs", e);
    }
  }, [token]);
```

Add a useEffect to fetch verification jobs (after the fetchJobs useEffect):

```typescript
  useEffect(() => {
    fetchVerificationJobs();
  }, [fetchVerificationJobs]);
```

Add polling for running verification jobs (after the marketing job polling useEffect):

```typescript
  // Poll running verification jobs every 5 seconds
  useEffect(() => {
    const hasActive = verificationJobs.some((j) => j.status === "running");
    if (!hasActive) return;
    const interval = setInterval(() => {
      fetchVerificationJobs();
    }, 5000);
    return () => clearInterval(interval);
  }, [verificationJobs, fetchVerificationJobs]);
```

Add the verify handler:

```typescript
  async function handleVerify() {
    if (!token) return;
    setVerifying(true);
    try {
      await adminApi.startVerification(token);
      await fetchVerificationJobs();
    } catch (e: any) {
      alert(e.message || "Failed to start verification");
    }
    setVerifying(false);
  }
```

- [ ] **Step 2: Add verification UI section**

In the JSX, add this block after the two-panel grid `</div>` (after line 193) and before the send controls section:

```tsx
        {/* Verification section */}
        <div className="border border-border rounded-lg p-4 mb-6 bg-surface">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-sm font-medium text-text-primary">Email Verification</h2>
              <p className="text-xs text-text-tertiary mt-0.5">
                Verify recipient emails via Hunter.io + NeverBounce before sending
              </p>
            </div>
            <button
              onClick={handleVerify}
              disabled={verifying}
              className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
            >
              {verifying ? "Starting..." : "Verify Recipients"}
            </button>
          </div>
          {verificationJobs.length > 0 && (() => {
            const latest = verificationJobs[0];
            const isRunning = latest.status === "running";
            const totalProcessed = latest.verified_count + latest.bounced_count + latest.skipped_count;
            const progressPct = latest.total_recipients > 0
              ? Math.round((totalProcessed / latest.total_recipients) * 100)
              : 0;
            return (
              <div>
                {isRunning && (
                  <>
                    <div className="flex items-center justify-between text-xs text-text-secondary mb-1">
                      <span>
                        {totalProcessed} / {latest.total_recipients} processed
                        {latest.current_investor_name && (
                          <> &mdash; verifying <strong>{latest.current_investor_name}</strong></>
                        )}
                      </span>
                      <span>{progressPct}%</span>
                    </div>
                    <div className="w-full bg-background rounded-full h-2">
                      <div
                        className="h-2 rounded-full bg-accent transition-all"
                        style={{ width: `${progressPct}%` }}
                      />
                    </div>
                  </>
                )}
                {latest.status === "completed" && (
                  <p className="text-xs text-text-secondary">
                    <span className="text-green-600 font-medium">{latest.verified_count} valid</span>
                    {latest.corrected_count > 0 && (
                      <>, <span className="text-blue-600 font-medium">{latest.corrected_count} corrected</span></>
                    )}
                    {latest.bounced_count > 0 && (
                      <>, <span className="text-red-600 font-medium">{latest.bounced_count} bounced</span></>
                    )}
                    {latest.skipped_count > 0 && (
                      <>, <span className="text-text-tertiary">{latest.skipped_count} skipped</span></>
                    )}
                  </p>
                )}
                {latest.status === "failed" && (
                  <p className="text-xs text-red-500">Verification failed: {latest.error}</p>
                )}
              </div>
            );
          })()}
        </div>
```

- [ ] **Step 3: Update send button to say "Verified Investors" and require verification**

Find the send button text (line 209):

```tsx
              Send to All Scored Investors
```

Replace with:

```tsx
              Send to All Verified Investors
```

Find the send button disabled condition:

```tsx
              disabled={!generatedHtml.trim() || !subject.trim() || sending}
```

Replace with:

```tsx
              disabled={!generatedHtml.trim() || !subject.trim() || sending || !verificationJobs.some((j) => j.status === "completed")}
```

Also update the description text from "Send the generated email to all scored investors" to "Send the generated email to all verified investors".

- [ ] **Step 4: Verify admin compiles**

Run: `cd /Users/leemosbacker/acutal/admin && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add admin/app/marketing/page.tsx
git commit -m "feat: add email verification section to admin marketing page"
```

---

### Task 11: Admin marketing page — test send section

**Files:**
- Modify: `admin/app/marketing/page.tsx`

- [ ] **Step 1: Add test send state**

Add these state variables after the verification state:

```typescript
  // Test send state
  const [testEmail, setTestEmail] = useState("");
  const [testInvestorId, setTestInvestorId] = useState("");
  const [testSending, setTestSending] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [scoredInvestors, setScoredInvestors] = useState<{ id: string; firm_name: string; partner_name: string }[]>([]);
```

Add a useEffect to load scored investors for the dropdown (after the verification jobs fetch):

```typescript
  useEffect(() => {
    if (!token) return;
    adminApi.getRankedInvestors(token, { per_page: 500 }).then((data) => {
      setScoredInvestors(
        data.items.map((inv) => ({
          id: inv.investor_id,
          firm_name: inv.firm_name,
          partner_name: inv.partner_name,
        }))
      );
    }).catch(() => {});
  }, [token]);
```

Add the test send handler:

```typescript
  async function handleTestSend() {
    if (!token || !testEmail.trim() || !testInvestorId || !generatedHtml.trim() || !subject.trim()) return;
    setTestSending(true);
    setTestResult(null);
    try {
      const result = await adminApi.sendTestEmail(token, testEmail, subject, generatedHtml, testInvestorId);
      setTestResult(result.message);
    } catch (e: any) {
      setTestResult(`Error: ${e.message || "Failed to send test email"}`);
    }
    setTestSending(false);
  }
```

- [ ] **Step 2: Add test send UI section**

Add this block in the JSX after the preview panel `</div>` but before the closing `</div>` of the two-panel grid. Alternatively, place it right after the two-panel grid and before the verification section:

Insert after the two-panel grid closing `</div>` and before the verification section:

```tsx
        {/* Test Send */}
        <div className="border border-border rounded-lg p-4 mb-6 bg-surface">
          <h2 className="text-sm font-medium text-text-primary mb-3">Send Test Email</h2>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-text-secondary mb-1">Your Email</label>
              <input
                type="email"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                placeholder="admin@example.com"
                className="w-full px-3 py-2 border border-border rounded bg-background text-text-primary text-sm placeholder:text-text-tertiary focus:outline-none focus:border-accent"
              />
            </div>
            <div>
              <label className="block text-xs text-text-secondary mb-1">Investor</label>
              <select
                value={testInvestorId}
                onChange={(e) => setTestInvestorId(e.target.value)}
                className="w-full px-3 py-2 border border-border rounded bg-background text-text-primary text-sm focus:outline-none focus:border-accent"
              >
                <option value="">Select an investor...</option>
                {scoredInvestors.map((inv) => (
                  <option key={inv.id} value={inv.id}>
                    {inv.firm_name} — {inv.partner_name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-end">
              <button
                onClick={handleTestSend}
                disabled={testSending || !testEmail.trim() || !testInvestorId || !generatedHtml.trim() || !subject.trim()}
                className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
              >
                {testSending ? "Sending..." : "Send Test"}
              </button>
            </div>
          </div>
          {testResult && (
            <p className={`text-xs mt-2 ${testResult.startsWith("Error") ? "text-red-500" : "text-green-600"}`}>
              {testResult}
            </p>
          )}
        </div>
```

- [ ] **Step 3: Add RankedInvestorListResponse to the api.ts import if not already present**

Verify `RankedInvestorListResponse` is already imported in `admin/lib/api.ts` — it should be from Task 9. If the `getRankedInvestors` method is already in `adminApi` (it is, from the investor rankings feature), no changes needed here.

- [ ] **Step 4: Verify admin compiles**

Run: `cd /Users/leemosbacker/acutal/admin && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add admin/app/marketing/page.tsx
git commit -m "feat: add test email send section to admin marketing page"
```

---

### Task 12: Final integration check

**Files:** None (verification only)

- [ ] **Step 1: Run all backend tests**

Run: `.venv/bin/python -m pytest tests/test_marketing_email.py tests/test_email_verification.py -v`
Expected: All pass

- [ ] **Step 2: Verify backend starts**

Run: `.venv/bin/python -c "from app.main import app; print('OK', len(app.routes))"`
Expected: `OK <number>` with no import errors

- [ ] **Step 3: Verify admin compiles**

Run: `cd /Users/leemosbacker/acutal/admin && npx tsc --noEmit`
Expected: No errors (or only pre-existing errors unrelated to our changes)

- [ ] **Step 4: Verify frontend compiles**

Run: `cd /Users/leemosbacker/acutal/frontend && npx tsc --noEmit 2>&1 | grep -v AnalystMessage`
Expected: No errors (AnalystMessage errors are pre-existing)

- [ ] **Step 5: Verify new route count**

Run: `.venv/bin/python -c "from app.main import app; routes = [r for r in app.routes if hasattr(r, 'path')]; print(len(routes), 'routes'); [print(r.path) for r in routes if 'unsub' in r.path or 'verify' in r.path or 'test-send' in r.path]"`
Expected: Should list `/api/unsubscribe/{investor_id}`, `/api/admin/marketing/verify`, `/api/admin/marketing/verify/jobs`, `/api/admin/marketing/test-send`
