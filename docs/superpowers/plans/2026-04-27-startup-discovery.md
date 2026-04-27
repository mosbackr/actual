# Startup Discovery Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an admin batch pipeline that discovers startups from Delaware C-corp filings, enriches founders via Proxycurl, classifies real startups with Claude, and enriches qualifying companies via Perplexity.

**Architecture:** Six-step pipeline — bulk CSV import, daily scraper, heuristic filter, founder discovery + Proxycurl enrichment, Claude classification, Perplexity enrichment. Uses existing batch job pattern (pause/resume, concurrency). Extends existing `StartupFounder` model with Proxycurl fields rather than creating a new table. Adds `discovered` status to `StartupStatus` enum.

**Tech Stack:** FastAPI, SQLAlchemy async (asyncpg + PostgreSQL 16), Alembic migrations, httpx for external APIs (Proxycurl, Perplexity, Anthropic, SerpAPI), Next.js admin frontend with NextAuth.

---

## File Structure

### Backend — New Files

| File | Responsibility |
|------|----------------|
| `backend/alembic/versions/disc01_startup_discovery_schema.py` | Migration: extend startups + startup_founders tables, create discovery_batch_jobs |
| `backend/app/models/discovery.py` | `DiscoveryBatchJob` model |
| `backend/app/services/discovery_import.py` | CSV parsing + bulk import logic |
| `backend/app/services/discovery_pipeline.py` | Heuristic filter, Proxycurl enrichment, Claude classification, Perplexity enrichment |
| `backend/app/api/admin_discovery.py` | API endpoints for discovery admin |

### Backend — Modified Files

| File | Change |
|------|--------|
| `backend/app/models/startup.py` | Add `discovered` to `StartupStatus`, add `ClassificationStatus` enum, add new columns |
| `backend/app/models/founder.py` | Add Proxycurl fields to `StartupFounder` |
| `backend/app/models/__init__.py` | Add `DiscoveryBatchJob` import |
| `backend/app/config.py` | Add `proxycurl_api_key`, `serp_api_key` settings |
| `backend/app/main.py` | Register `admin_discovery` router |

### Admin Frontend — New Files

| File | Responsibility |
|------|----------------|
| `admin/app/discovery/page.tsx` | Discovery admin page |

### Admin Frontend — Modified Files

| File | Change |
|------|--------|
| `admin/lib/types.ts` | Add discovery types |
| `admin/lib/api.ts` | Add discovery API methods |
| `admin/components/Sidebar.tsx` | Add "Discovery" nav item |

---

## Task 1: Database Migration + Models

**Files:**
- Create: `backend/alembic/versions/disc01_startup_discovery_schema.py`
- Create: `backend/app/models/discovery.py`
- Modify: `backend/app/models/startup.py`
- Modify: `backend/app/models/founder.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add new config settings**

In `backend/app/config.py`, add these two lines before the `model_config` line:

```python
    # Startup discovery
    proxycurl_api_key: str = ""
    serp_api_key: str = ""
```

- [ ] **Step 2: Add `discovered` to `StartupStatus` and add classification columns to startup model**

In `backend/app/models/startup.py`, add `discovered = "discovered"` to the `StartupStatus` enum:

```python
class StartupStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    featured = "featured"
    discovered = "discovered"
```

Add a new `ClassificationStatus` enum after the `EnrichmentStatus` enum:

```python
class ClassificationStatus(str, enum.Enum):
    unclassified = "unclassified"
    startup = "startup"
    not_startup = "not_startup"
    uncertain = "uncertain"
```

Add new columns to the `Startup` class (after the `data_sources` column):

```python
    discovery_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    delaware_corp_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    delaware_file_number: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    delaware_filed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    classification_status: Mapped[ClassificationStatus] = mapped_column(
        Enum(ClassificationStatus), nullable=False, default=ClassificationStatus.unclassified, server_default="unclassified"
    )
    classification_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 3: Add Proxycurl fields to StartupFounder model**

In `backend/app/models/founder.py`, add new imports and columns. The full file should be:

```python
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base


class StartupFounder(Base):
    __tablename__ = "startup_founders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("startups.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_founder: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    prior_experience: Mapped[str | None] = mapped_column(Text, nullable=True)
    education: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Proxycurl enrichment fields
    headline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    profile_photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    work_history: Mapped[list | None] = mapped_column(JSON, nullable=True)
    education_history: Mapped[list | None] = mapped_column(JSON, nullable=True)
    proxycurl_raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 4: Create DiscoveryBatchJob model**

Create `backend/app/models/discovery.py`:

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base
from app.models.investor import BatchJobStatus


class DiscoveryBatchJob(Base):
    __tablename__ = "discovery_batch_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BatchJobStatus.pending.value
    )
    job_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_item_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    items_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
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

- [ ] **Step 5: Register model in `__init__.py`**

In `backend/app/models/__init__.py`, add after the `InvestorRanking` import line:

```python
from app.models.discovery import DiscoveryBatchJob
```

And add `"DiscoveryBatchJob"` to the `__all__` list.

- [ ] **Step 6: Create Alembic migration**

Create `backend/alembic/versions/disc01_startup_discovery_schema.py`:

```python
"""Add startup discovery schema — extend startups, startup_founders, create discovery_batch_jobs

Revision ID: disc01
Revises: zav1zoom2avail3
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "disc01"
down_revision = "zav1zoom2avail3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add 'discovered' to StartupStatus enum
    op.execute("ALTER TYPE startupstatus ADD VALUE IF NOT EXISTS 'discovered'")

    # Add ClassificationStatus enum
    op.execute(
        "CREATE TYPE classificationstatus AS ENUM ('unclassified', 'startup', 'not_startup', 'uncertain')"
    )

    # Add discovery columns to startups
    op.add_column("startups", sa.Column("discovery_source", sa.String(50), nullable=True))
    op.add_column("startups", sa.Column("delaware_corp_name", sa.String(300), nullable=True))
    op.add_column("startups", sa.Column("delaware_file_number", sa.String(50), nullable=True))
    op.add_column("startups", sa.Column("delaware_filed_at", sa.Date, nullable=True))
    op.add_column(
        "startups",
        sa.Column(
            "classification_status",
            sa.Enum("unclassified", "startup", "not_startup", "uncertain", name="classificationstatus", create_type=False),
            nullable=False,
            server_default="unclassified",
        ),
    )
    op.add_column("startups", sa.Column("classification_metadata", JSON, nullable=True))
    op.create_index("ix_startups_delaware_file_number", "startups", ["delaware_file_number"], unique=True)
    op.create_index("ix_startups_classification_status", "startups", ["classification_status"])
    op.create_index("ix_startups_discovery_source", "startups", ["discovery_source"])

    # Add Proxycurl fields to startup_founders
    op.add_column("startup_founders", sa.Column("headline", sa.String(500), nullable=True))
    op.add_column("startup_founders", sa.Column("location", sa.String(300), nullable=True))
    op.add_column("startup_founders", sa.Column("profile_photo_url", sa.String(500), nullable=True))
    op.add_column("startup_founders", sa.Column("work_history", JSON, nullable=True))
    op.add_column("startup_founders", sa.Column("education_history", JSON, nullable=True))
    op.add_column("startup_founders", sa.Column("proxycurl_raw", JSON, nullable=True))

    # Create discovery_batch_jobs table
    op.create_table(
        "discovery_batch_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("job_type", sa.String(30), nullable=False),
        sa.Column("total_items", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("processed_items", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("current_item_name", sa.String(300), nullable=True),
        sa.Column("items_created", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("discovery_batch_jobs")

    op.drop_index("ix_startups_discovery_source", table_name="startups")
    op.drop_index("ix_startups_classification_status", table_name="startups")
    op.drop_index("ix_startups_delaware_file_number", table_name="startups")
    op.drop_column("startups", "classification_metadata")
    op.drop_column("startups", "classification_status")
    op.drop_column("startups", "delaware_filed_at")
    op.drop_column("startups", "delaware_file_number")
    op.drop_column("startups", "delaware_corp_name")
    op.drop_column("startups", "discovery_source")

    op.drop_column("startup_founders", "proxycurl_raw")
    op.drop_column("startup_founders", "education_history")
    op.drop_column("startup_founders", "work_history")
    op.drop_column("startup_founders", "profile_photo_url")
    op.drop_column("startup_founders", "location")
    op.drop_column("startup_founders", "headline")

    op.execute("DROP TYPE IF EXISTS classificationstatus")
```

- [ ] **Step 7: Verify migration runs**

```bash
cd /Users/leemosbacker/acutal/backend && python -c "from app.models.discovery import DiscoveryBatchJob; print('Model import OK')"
```

- [ ] **Step 8: Commit**

```bash
git add backend/alembic/versions/disc01_startup_discovery_schema.py backend/app/models/discovery.py backend/app/models/startup.py backend/app/models/founder.py backend/app/models/__init__.py backend/app/config.py
git commit -m "feat(discovery): add schema — discovery columns, founder enrichment fields, batch jobs table"
```

---

## Task 2: CSV Bulk Import Service

**Files:**
- Create: `backend/app/services/discovery_import.py`

- [ ] **Step 1: Create the import service**

Create `backend/app/services/discovery_import.py`:

```python
import csv
import io
import logging
import re
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models.discovery import DiscoveryBatchJob
from app.models.investor import BatchJobStatus
from app.models.startup import ClassificationStatus, Startup, StartupStatus

logger = logging.getLogger(__name__)


def _generate_slug(name: str) -> str:
    """Generate a URL-safe slug from a company name with random suffix."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    suffix = uuid.uuid4().hex[:6]
    return f"{slug}-{suffix}"


def _parse_date(date_str: str) -> date | None:
    """Parse common date formats from CSV: MM/DD/YYYY, YYYY-MM-DD, etc."""
    if not date_str or not date_str.strip():
        return None
    date_str = date_str.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


# Common CSV column name mappings (lowercase)
COLUMN_MAP = {
    # file number
    "file_number": "file_number",
    "filenumber": "file_number",
    "file number": "file_number",
    "entity_file_number": "file_number",
    "file_num": "file_number",
    # entity name
    "entity_name": "entity_name",
    "entityname": "entity_name",
    "entity name": "entity_name",
    "name": "entity_name",
    "company_name": "entity_name",
    "company name": "entity_name",
    # entity type
    "entity_type": "entity_type",
    "entitytype": "entity_type",
    "entity type": "entity_type",
    "type": "entity_type",
    # filed date
    "filed_date": "filed_date",
    "fileddate": "filed_date",
    "filed date": "filed_date",
    "file_date": "filed_date",
    "date": "filed_date",
    "incorporation_date": "filed_date",
    "formation_date": "filed_date",
    # state
    "state": "state",
    "jurisdiction": "state",
    # status
    "status": "status",
    "entity_status": "status",
}

# Entity types that are C-corps (case-insensitive matching)
C_CORP_TYPES = {
    "corporation",
    "general corporation",
    "corp",
    "c corp",
    "c-corp",
    "stock corporation",
    "domestic corporation",
    "foreign corporation",
}


def _normalize_columns(headers: list[str]) -> dict[str, str]:
    """Map CSV headers to canonical column names."""
    mapping = {}
    for header in headers:
        key = header.strip().lower()
        if key in COLUMN_MAP:
            mapping[header] = COLUMN_MAP[key]
    return mapping


async def import_csv(csv_content: str, job_id: str) -> None:
    """Parse a CSV string and import Delaware C-corp filings into the startups table."""
    db_factory = async_session

    reader = csv.DictReader(io.StringIO(csv_content))
    if not reader.fieldnames:
        async with db_factory() as db:
            job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
            if job:
                job.status = BatchJobStatus.failed.value
                job.error = "CSV has no headers"
                await db.commit()
        return

    col_map = _normalize_columns(list(reader.fieldnames))
    rows = list(reader)

    # Update job total
    async with db_factory() as db:
        job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
        if not job:
            return
        job.status = BatchJobStatus.running.value
        job.total_items = len(rows)
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    created = 0
    skipped = 0

    for idx, row in enumerate(rows):
        # Map columns
        mapped = {}
        for csv_col, canonical in col_map.items():
            mapped[canonical] = row.get(csv_col, "").strip()

        entity_name = mapped.get("entity_name", "")
        file_number = mapped.get("file_number", "")
        entity_type = mapped.get("entity_type", "").lower()
        filed_date_str = mapped.get("filed_date", "")

        if not entity_name or not file_number:
            skipped += 1
            continue

        # Filter to C-corps only
        if entity_type and entity_type not in C_CORP_TYPES:
            skipped += 1
            continue

        filed_date = _parse_date(filed_date_str)

        async with db_factory() as db:
            # Check for pause
            job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
            if job and job.status == BatchJobStatus.paused.value:
                logger.info(f"Import job {job_id} paused at row {idx}")
                return

            # Deduplicate on file_number
            existing = await db.execute(
                select(Startup).where(Startup.delaware_file_number == file_number)
            )
            if existing.scalar_one_or_none():
                skipped += 1
            else:
                startup = Startup(
                    name=entity_name,
                    slug=_generate_slug(entity_name),
                    description="",
                    stage="pre_seed",
                    status=StartupStatus.discovered,
                    location_country="US",
                    discovery_source="delaware",
                    delaware_corp_name=entity_name,
                    delaware_file_number=file_number,
                    delaware_filed_at=filed_date,
                    classification_status=ClassificationStatus.unclassified,
                )
                db.add(startup)
                await db.commit()
                created += 1

            # Update progress
            job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
            if job:
                job.processed_items = idx + 1
                job.items_created = created
                job.current_item_name = entity_name
                await db.commit()

        if (idx + 1) % 500 == 0:
            logger.info(f"Import progress: {idx + 1}/{len(rows)}, created={created}, skipped={skipped}")

    # Mark complete
    async with db_factory() as db:
        job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
        if job:
            job.status = BatchJobStatus.completed.value
            job.completed_at = datetime.now(timezone.utc)
            job.items_created = created
            await db.commit()

    logger.info(f"Import complete: {created} created, {skipped} skipped out of {len(rows)} rows")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/discovery_import.py
git commit -m "feat(discovery): add CSV bulk import service for Delaware filings"
```

---

## Task 3: Discovery Pipeline Service

**Files:**
- Create: `backend/app/services/discovery_pipeline.py`

This is the core pipeline: heuristic filter, Proxycurl enrichment, Claude classification, Perplexity enrichment.

- [ ] **Step 1: Create the pipeline service**

Create `backend/app/services/discovery_pipeline.py`:

```python
import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import async_session
from app.models.discovery import DiscoveryBatchJob
from app.models.founder import StartupFounder
from app.models.investor import BatchJobStatus
from app.models.startup import ClassificationStatus, EnrichmentStatus, Startup, StartupStatus

logger = logging.getLogger(__name__)

CONCURRENCY = 10
DB_SEMAPHORE = asyncio.Semaphore(2)

# ── Heuristic Filter ────────────────────────────────────────────────────

NOT_STARTUP_PATTERNS = [
    r"\bholdings?\b",
    r"\bholding\s+co(mpany)?\b",
    r"\breal\s+estate\b",
    r"\brealty\b",
    r"\bpropert(y|ies)\b",
    r"\bproperty\s+management\b",
    r"\btrust(ee)?\b",
    r"\binsurance\b",
    r"\bassurance\b",
    r"\bbank(ing)?\b",
    r"\bchurch\b",
    r"\bministr(y|ies)\b",
    r"\btemple\b",
    r"\bmosque\b",
    r"\bfoundation\b(?!.*\b(ai|tech|data|software|digital)\b)",
    r"\bassociation\b",
    r"\bsociety\b",
    r"\bmortgage\b",
    r"\blending\b",
    r"\bconstruction\b",
    r"\bcontract(ing|ors?)\b",
    r"\brestaurant(s)?\b",
    r"\bfood\s+service\b",
    r"\bcapital\s+llc\b",
    r"\bcapital\s+lp\b",
    r"\bmanagement\s+co(mpany)?\b",
]

_NOT_STARTUP_RE = re.compile("|".join(NOT_STARTUP_PATTERNS), re.IGNORECASE)


def is_heuristic_not_startup(name: str) -> bool:
    """Return True if the name matches common non-startup patterns."""
    return bool(_NOT_STARTUP_RE.search(name))


# ── Proxycurl ────────────────────────────────────────────────────────────

async def _proxycurl_company_search(company_name: str) -> dict | None:
    """Search for a company's LinkedIn page via Proxycurl."""
    if not settings.proxycurl_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://nubela.co/proxycurl/api/linkedin/company/resolve",
                params={"company_name": company_name, "enrich_profile": "skip"},
                headers={"Authorization": f"Bearer {settings.proxycurl_api_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("url"):
                    return data
    except Exception as e:
        logger.warning(f"Proxycurl company search failed for {company_name}: {e}")
    return None


async def _proxycurl_person_profile(linkedin_url: str) -> dict | None:
    """Fetch a person's LinkedIn profile via Proxycurl."""
    if not settings.proxycurl_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://nubela.co/proxycurl/api/v2/linkedin",
                params={"url": linkedin_url, "skills": "exclude", "inferred_salary": "exclude"},
                headers={"Authorization": f"Bearer {settings.proxycurl_api_key}"},
            )
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.warning(f"Proxycurl person profile failed for {linkedin_url}: {e}")
    return None


async def _search_founder_linkedin(company_name: str) -> list[str]:
    """Search Google/SerpAPI for founder LinkedIn URLs."""
    if not settings.serp_api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://serpapi.com/search",
                params={
                    "q": f'"{company_name}" founder OR CEO site:linkedin.com/in',
                    "api_key": settings.serp_api_key,
                    "num": 5,
                },
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            urls = []
            for result in data.get("organic_results", []):
                link = result.get("link", "")
                if "linkedin.com/in/" in link:
                    urls.append(link)
            return urls[:3]
    except Exception as e:
        logger.warning(f"SerpAPI search failed for {company_name}: {e}")
    return []


def _extract_work_history(profile: dict) -> list[dict]:
    """Extract structured work history from Proxycurl profile."""
    experiences = profile.get("experiences") or []
    return [
        {
            "company": exp.get("company") or "",
            "title": exp.get("title") or "",
            "start_date": exp.get("starts_at", {}).get("month", "") if exp.get("starts_at") else "",
            "end_date": exp.get("ends_at", {}).get("month", "") if exp.get("ends_at") else "",
            "description": (exp.get("description") or "")[:500],
        }
        for exp in experiences[:10]
    ]


def _extract_education(profile: dict) -> list[dict]:
    """Extract structured education from Proxycurl profile."""
    education = profile.get("education") or []
    return [
        {
            "school": edu.get("school") or "",
            "degree": edu.get("degree_name") or "",
            "field": edu.get("field_of_study") or "",
            "start_year": edu.get("starts_at", {}).get("year") if edu.get("starts_at") else None,
            "end_year": edu.get("ends_at", {}).get("year") if edu.get("ends_at") else None,
        }
        for edu in education[:5]
    ]


def _detect_brand_name(founder_profile: dict, corp_name: str) -> str | None:
    """If the founder's current company differs from corp name, return the brand name."""
    experiences = founder_profile.get("experiences") or []
    if not experiences:
        return None
    current = experiences[0]
    if not current.get("ends_at"):  # currently employed
        company = current.get("company", "")
        if company and company.lower().strip() != corp_name.lower().strip():
            return company
    return None


async def _enrich_founders(db: AsyncSession, startup: Startup) -> list[StartupFounder]:
    """Find and enrich founders for a startup via Proxycurl + SerpAPI."""
    corp_name = startup.delaware_corp_name or startup.name
    brand_name = startup.name if startup.name != corp_name else None
    search_name = brand_name or corp_name

    linkedin_urls: list[str] = []

    # Method 1: Proxycurl company search
    company_data = await _proxycurl_company_search(search_name)
    if not company_data and brand_name:
        company_data = await _proxycurl_company_search(corp_name)

    # Method 2: SerpAPI fallback
    if not linkedin_urls:
        linkedin_urls = await _search_founder_linkedin(search_name)
        if not linkedin_urls and brand_name:
            linkedin_urls.extend(await _search_founder_linkedin(corp_name))

    # Deduplicate URLs
    seen = set()
    unique_urls = []
    for url in linkedin_urls:
        normalized = url.rstrip("/").lower()
        if normalized not in seen:
            seen.add(normalized)
            unique_urls.append(url)

    founders: list[StartupFounder] = []

    for url in unique_urls[:3]:
        profile = await _proxycurl_person_profile(url)
        if not profile:
            continue

        full_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        if not full_name:
            continue

        # Check for brand name mismatch
        detected_brand = _detect_brand_name(profile, corp_name)
        if detected_brand and not brand_name:
            startup.name = detected_brand
            startup.slug = re.sub(r"[^a-z0-9]+", "-", detected_brand.lower()).strip("-") + "-" + uuid.uuid4().hex[:6]

        work_history = _extract_work_history(profile)
        education_history = _extract_education(profile)

        founder = StartupFounder(
            startup_id=startup.id,
            name=full_name,
            title=profile.get("headline", "").split(" at ")[0] if profile.get("headline") else None,
            linkedin_url=url,
            is_founder=True,
            headline=profile.get("headline"),
            location=profile.get("city") or profile.get("country_full_name"),
            profile_photo_url=profile.get("profile_pic_url"),
            work_history=work_history,
            education_history=education_history,
            proxycurl_raw=profile,
        )
        db.add(founder)
        founders.append(founder)

    return founders


# ── Claude Classification ────────────────────────────────────────────────

CLASSIFICATION_PROMPT = """You are a venture capital analyst. Given a Delaware corporate filing and founder LinkedIn data, determine if this is a venture-backable technology startup.

Classify as one of:
- "startup" — This is a venture-backable technology startup
- "not_startup" — This is a traditional business, holding company, consulting firm, or non-tech entity
- "uncertain" — Not enough signal to determine

Signals that indicate STARTUP:
- Founders with tech company backgrounds (FAANG, startups, tech firms)
- CS/engineering/PhD education
- Prior startup founding experience
- Tech-sounding company name or product focus
- Location in tech hubs (but not determinative)
- Multiple technical co-founders

Signals that indicate NOT A STARTUP:
- Founders with backgrounds in law, real estate, insurance, traditional finance
- Company name suggests traditional business (consulting, services, management)
- Single founder with no tech background
- No clear technology product or innovation

Return ONLY a JSON object:
{
  "classification": "startup" | "not_startup" | "uncertain",
  "confidence": 0.0-1.0,
  "reasoning": "One paragraph explaining your decision"
}"""


async def _classify_with_claude(startup: Startup, founders: list[StartupFounder]) -> dict:
    """Use Claude to classify whether this is a real startup."""
    founder_descriptions = []
    for f in founders:
        desc = f"**{f.name}** — {f.headline or 'No headline'}\n"
        if f.location:
            desc += f"Location: {f.location}\n"
        if f.work_history:
            desc += "Recent work:\n"
            for job in (f.work_history or [])[:3]:
                desc += f"  - {job.get('title', '?')} at {job.get('company', '?')}\n"
        if f.education_history:
            desc += "Education:\n"
            for edu in (f.education_history or [])[:2]:
                desc += f"  - {edu.get('degree', '?')} in {edu.get('field', '?')} from {edu.get('school', '?')}\n"
        founder_descriptions.append(desc)

    user_msg = f"""Delaware Corporate Filing:
- Corp Name: {startup.delaware_corp_name or startup.name}
- Brand Name: {startup.name if startup.name != startup.delaware_corp_name else "Same as corp name"}
- Filed Date: {startup.delaware_filed_at or "Unknown"}

{"Founders found:" if founder_descriptions else "No founder data found."}
{"---".join(founder_descriptions) if founder_descriptions else ""}

Classify this entity."""

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "temperature": 0.1,
                "system": CLASSIFICATION_PROMPT,
                "messages": [{"role": "user", "content": user_msg}],
            },
        )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]

    # Parse JSON from response
    try:
        # Try fenced JSON
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
        if m:
            return json.loads(m.group(1))
        # Try bare JSON
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            return json.loads(content[start:end + 1])
    except json.JSONDecodeError:
        pass

    return {"classification": "uncertain", "confidence": 0.0, "reasoning": f"Failed to parse: {content[:200]}"}


# ── Perplexity Enrichment ────────────────────────────────────────────────

async def _enrich_with_perplexity(startup: Startup, founders: list[StartupFounder]) -> dict:
    """Use Perplexity to research the startup and populate enrichment fields."""
    founder_names = ", ".join(f.name for f in founders) if founders else "Unknown"
    company_name = startup.name

    messages = [
        {
            "role": "system",
            "content": (
                "You are a startup research analyst. Given a company name and its founders, research the company and return structured data. "
                "Return ONLY a JSON object with these fields. Use null for unknown values."
            ),
        },
        {
            "role": "user",
            "content": f"""Research this startup:
Company: {company_name}
Founders: {founder_names}
Delaware filing name: {startup.delaware_corp_name or company_name}
Filed: {startup.delaware_filed_at or "Unknown"}

Return a JSON object with:
- "description": string — What the company does (2-3 sentences)
- "tagline": string or null — One-line pitch
- "website_url": string or null — Company website
- "linkedin_url": string or null — Company LinkedIn page
- "twitter_url": string or null — Company Twitter/X
- "crunchbase_url": string or null — Crunchbase profile
- "stage": "pre_seed" | "seed" | "series_a" | "series_b" | "series_c" | "growth" — Best guess at current stage
- "total_funding": string or null — e.g. "$2.5M"
- "employee_count": string or null — e.g. "5-10"
- "industries": array of strings — e.g. ["AI", "Healthcare"]
- "location_city": string or null
- "location_state": string or null
- "location_country": string — Default "US"
- "business_model": string or null — e.g. "B2B SaaS"
- "competitors": string or null — Comma-separated competitor names
- "hiring_signals": string or null — Any hiring activity""",
        },
    ]

    async with httpx.AsyncClient(timeout=120) as client:
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
        content = resp.json()["choices"][0]["message"]["content"]

    # Parse JSON
    try:
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
        if m:
            return json.loads(m.group(1))
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            raw = content[start:end + 1]
            raw = re.sub(r",\s*([}\]])", r"\1", raw)
            return json.loads(raw)
    except json.JSONDecodeError:
        pass

    return {}


def _apply_enrichment(startup: Startup, data: dict) -> None:
    """Apply Perplexity enrichment data to startup fields."""
    if data.get("description"):
        startup.description = data["description"]
    if data.get("tagline"):
        startup.tagline = data["tagline"]
    if data.get("website_url"):
        startup.website_url = data["website_url"]
    if data.get("linkedin_url"):
        startup.linkedin_url = data["linkedin_url"]
    if data.get("twitter_url"):
        startup.twitter_url = data["twitter_url"]
    if data.get("crunchbase_url"):
        startup.crunchbase_url = data["crunchbase_url"]
    if data.get("total_funding"):
        startup.total_funding = data["total_funding"]
    if data.get("employee_count"):
        startup.employee_count = data["employee_count"]
    if data.get("location_city"):
        startup.location_city = data["location_city"]
    if data.get("location_state"):
        startup.location_state = data["location_state"]
    if data.get("location_country"):
        startup.location_country = data["location_country"]
    if data.get("business_model"):
        startup.business_model = data["business_model"]
    if data.get("competitors"):
        startup.competitors = data["competitors"]
    if data.get("hiring_signals"):
        startup.hiring_signals = data["hiring_signals"]

    # Map stage string to enum if valid
    stage_str = data.get("stage")
    if stage_str:
        from app.models.startup import StartupStage
        try:
            startup.stage = StartupStage(stage_str)
        except ValueError:
            pass

    startup.enrichment_status = EnrichmentStatus.complete
    startup.enriched_at = datetime.now(timezone.utc)


# ── Main Pipeline ────────────────────────────────────────────────────────

async def _process_single_startup(startup_id: uuid.UUID) -> str:
    """Process a single startup through the full pipeline. Returns status string."""
    async with DB_SEMAPHORE:
        async with async_session() as db:
            startup = await db.get(Startup, startup_id)
            if not startup:
                return "not_found"

            name = startup.delaware_corp_name or startup.name

            # Step 1: Heuristic filter
            if is_heuristic_not_startup(name):
                startup.classification_status = ClassificationStatus.not_startup
                startup.classification_metadata = {"method": "heuristic", "pattern_matched": True}
                await db.commit()
                return "filtered"

            # Step 2: Founder discovery + enrichment
            founders = await _enrich_founders(db, startup)
            await db.commit()

            # Step 3: Claude classification
            try:
                classification = await _classify_with_claude(startup, founders)
                status_str = classification.get("classification", "uncertain")
                try:
                    startup.classification_status = ClassificationStatus(status_str)
                except ValueError:
                    startup.classification_status = ClassificationStatus.uncertain
                startup.classification_metadata = classification
                await db.commit()
            except Exception as e:
                logger.error(f"Classification failed for {name}: {e}")
                startup.classification_status = ClassificationStatus.uncertain
                startup.classification_metadata = {"error": str(e)}
                await db.commit()
                return "classification_error"

            # Step 4: Perplexity enrichment (only for startups)
            if startup.classification_status == ClassificationStatus.startup:
                try:
                    enrichment_data = await _enrich_with_perplexity(startup, founders)
                    _apply_enrichment(startup, enrichment_data)
                    startup.data_sources = {**(startup.data_sources or {}), "perplexity_discovery": True}
                    await db.commit()
                except Exception as e:
                    logger.error(f"Perplexity enrichment failed for {name}: {e}")
                    startup.enrichment_status = EnrichmentStatus.failed
                    startup.enrichment_error = str(e)
                    await db.commit()
                    return "enrichment_error"

            return startup.classification_status.value


async def run_discovery_pipeline(job_id: str) -> None:
    """Main batch loop. Process all unclassified discovered startups."""
    db_factory = async_session

    # Mark job running
    async with db_factory() as db:
        job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
        if not job:
            logger.error(f"Discovery job {job_id} not found")
            return
        job.status = BatchJobStatus.running.value
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # Load unclassified discovered startups
    async with db_factory() as db:
        result = await db.execute(
            select(Startup.id, Startup.name)
            .where(
                Startup.status == StartupStatus.discovered,
                Startup.classification_status == ClassificationStatus.unclassified,
            )
            .order_by(Startup.delaware_filed_at.desc().nullslast())
        )
        startup_rows = result.all()

    # Update total
    async with db_factory() as db:
        job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
        if job:
            job.total_items = len(startup_rows)
            await db.commit()

    processed = 0
    created = 0
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def _worker(startup_id: uuid.UUID, startup_name: str, index: int):
        nonlocal processed, created
        async with semaphore:
            # Check for pause
            async with db_factory() as db:
                job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
                if job and job.status == BatchJobStatus.paused.value:
                    return

            try:
                result = await _process_single_startup(startup_id)
                if result == "startup":
                    created += 1
            except Exception as e:
                logger.error(f"Pipeline failed for {startup_name}: {e}")
                async with db_factory() as db:
                    job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
                    if job:
                        errors = job.error or ""
                        job.error = f"{errors}\n{startup_name}: {e}".strip()
                        await db.commit()

            processed += 1

            # Update progress
            async with db_factory() as db:
                job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
                if job:
                    job.processed_items = processed
                    job.items_created = created
                    job.current_item_name = startup_name
                    await db.commit()

    # Process in batches
    batch_size = CONCURRENCY
    for i in range(0, len(startup_rows), batch_size):
        # Check for pause before each batch
        async with db_factory() as db:
            job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
            if job and job.status == BatchJobStatus.paused.value:
                logger.info(f"Discovery job {job_id} paused")
                return

        batch = startup_rows[i:i + batch_size]
        tasks = [_worker(row[0], row[1], i + j) for j, row in enumerate(batch)]
        await asyncio.gather(*tasks)

    # Mark complete
    async with db_factory() as db:
        job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
        if job:
            job.status = BatchJobStatus.completed.value
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

    logger.info(f"Discovery pipeline job {job_id} complete: {created} startups identified out of {processed} processed")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/discovery_pipeline.py
git commit -m "feat(discovery): add pipeline service — heuristic filter, Proxycurl, Claude classification, Perplexity enrichment"
```

---

## Task 4: Admin API Endpoints

**Files:**
- Create: `backend/app/api/admin_discovery.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the admin discovery API**

Create `backend/app/api/admin_discovery.py`:

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.discovery import DiscoveryBatchJob
from app.models.founder import StartupFounder
from app.models.investor import BatchJobStatus
from app.models.startup import ClassificationStatus, Startup, StartupStatus
from app.models.user import User

router = APIRouter()


@router.post("/api/admin/discovery/import")
async def import_bulk_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    """Upload a bulk Delaware CSV and start import."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()
    csv_text = content.decode("utf-8", errors="replace")

    # Check no import already running
    result = await db.execute(
        select(DiscoveryBatchJob).where(
            DiscoveryBatchJob.job_type == "bulk_import",
            DiscoveryBatchJob.status.in_([BatchJobStatus.running.value, BatchJobStatus.paused.value]),
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An import job is already running")

    job = DiscoveryBatchJob(job_type="bulk_import")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from app.services.discovery_import import import_csv
    background_tasks.add_task(import_csv, csv_text, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.post("/api/admin/discovery/batch")
async def start_discovery_batch(
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    """Start the classification + enrichment pipeline on unprocessed discovered startups."""
    result = await db.execute(
        select(DiscoveryBatchJob).where(
            DiscoveryBatchJob.job_type == "enrich",
            DiscoveryBatchJob.status.in_([BatchJobStatus.running.value, BatchJobStatus.paused.value]),
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A pipeline batch is already running")

    job = DiscoveryBatchJob(job_type="enrich")
    db.add(job)
    await db.commit()
    await db.refresh(job)

    from app.services.discovery_pipeline import run_discovery_pipeline
    background_tasks.add_task(run_discovery_pipeline, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.put("/api/admin/discovery/batch/{job_id}/pause")
async def pause_discovery_batch(
    job_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(DiscoveryBatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.running.value:
        raise HTTPException(status_code=400, detail="Job is not running")

    job.status = BatchJobStatus.paused.value
    job.paused_at = datetime.now(timezone.utc)
    await db.commit()
    return {"id": str(job.id), "status": job.status}


@router.put("/api/admin/discovery/batch/{job_id}/resume")
async def resume_discovery_batch(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(DiscoveryBatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.paused.value:
        raise HTTPException(status_code=400, detail="Job is not paused")

    job.status = BatchJobStatus.running.value
    await db.commit()

    if job.job_type == "bulk_import":
        from app.services.discovery_import import import_csv
        background_tasks.add_task(import_csv, "", str(job.id))
    else:
        from app.services.discovery_pipeline import run_discovery_pipeline
        background_tasks.add_task(run_discovery_pipeline, str(job.id))

    return {"id": str(job.id), "status": job.status}


@router.get("/api/admin/discovery/batch/status")
async def get_discovery_batch_status(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    """Get status of most recent import and pipeline jobs."""
    # Most recent import job
    import_result = await db.execute(
        select(DiscoveryBatchJob)
        .where(DiscoveryBatchJob.job_type == "bulk_import")
        .order_by(DiscoveryBatchJob.created_at.desc())
        .limit(1)
    )
    import_job = import_result.scalar_one_or_none()

    # Most recent pipeline job
    pipeline_result = await db.execute(
        select(DiscoveryBatchJob)
        .where(DiscoveryBatchJob.job_type == "enrich")
        .order_by(DiscoveryBatchJob.created_at.desc())
        .limit(1)
    )
    pipeline_job = pipeline_result.scalar_one_or_none()

    def _job_dict(job):
        if not job:
            return None
        return {
            "id": str(job.id),
            "status": job.status,
            "job_type": job.job_type,
            "total_items": job.total_items,
            "processed_items": job.processed_items,
            "current_item_name": job.current_item_name,
            "items_created": job.items_created,
            "error": job.error,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "paused_at": job.paused_at.isoformat() if job.paused_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    # Stats
    total_imported = await db.execute(
        select(func.count()).select_from(Startup).where(Startup.discovery_source == "delaware")
    )
    classified_startup = await db.execute(
        select(func.count()).select_from(Startup).where(
            Startup.discovery_source == "delaware",
            Startup.classification_status == ClassificationStatus.startup,
        )
    )
    enriched = await db.execute(
        select(func.count()).select_from(Startup).where(
            Startup.discovery_source == "delaware",
            Startup.enrichment_status == "complete",
        )
    )
    promoted = await db.execute(
        select(func.count()).select_from(Startup).where(
            Startup.discovery_source == "delaware",
            Startup.status == StartupStatus.approved,
        )
    )

    return {
        "import_job": _job_dict(import_job),
        "pipeline_job": _job_dict(pipeline_job),
        "stats": {
            "total_imported": total_imported.scalar() or 0,
            "classified_startup": classified_startup.scalar() or 0,
            "enriched": enriched.scalar() or 0,
            "promoted": promoted.scalar() or 0,
        },
    }


@router.get("/api/admin/discovery/startups")
async def list_discovered_startups(
    classification: str = "all",
    enrichment: str = "all",
    q: str | None = None,
    sort: str = "delaware_filed_at",
    order: str = "desc",
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    query = select(Startup).where(Startup.discovery_source == "delaware")

    if classification != "all":
        try:
            cs = ClassificationStatus(classification)
            query = query.where(Startup.classification_status == cs)
        except ValueError:
            pass

    if enrichment != "all":
        query = query.where(Startup.enrichment_status == enrichment)

    if q:
        like = f"%{q}%"
        query = query.where(
            Startup.name.ilike(like) | Startup.delaware_corp_name.ilike(like)
        )

    # Count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # Sort
    sort_map = {
        "delaware_filed_at": Startup.delaware_filed_at,
        "name": Startup.name,
        "created_at": Startup.created_at,
        "classification_status": Startup.classification_status,
    }
    sort_col = sort_map.get(sort, Startup.delaware_filed_at)
    if order == "asc":
        query = query.order_by(sort_col.asc().nullslast())
    else:
        query = query.order_by(sort_col.desc().nullslast())

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    startups = result.scalars().all()

    # Load founders for these startups
    startup_ids = [s.id for s in startups]
    founders_result = await db.execute(
        select(StartupFounder).where(StartupFounder.startup_id.in_(startup_ids))
    )
    all_founders = founders_result.scalars().all()
    founders_by_startup = {}
    for f in all_founders:
        founders_by_startup.setdefault(str(f.startup_id), []).append(f)

    pages = max(1, (total + per_page - 1) // per_page)

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "items": [
            {
                "id": str(s.id),
                "name": s.name,
                "delaware_corp_name": s.delaware_corp_name,
                "delaware_file_number": s.delaware_file_number,
                "delaware_filed_at": s.delaware_filed_at.isoformat() if s.delaware_filed_at else None,
                "status": s.status.value if hasattr(s.status, 'value') else s.status,
                "classification_status": s.classification_status.value if hasattr(s.classification_status, 'value') else s.classification_status,
                "classification_metadata": s.classification_metadata,
                "enrichment_status": s.enrichment_status.value if hasattr(s.enrichment_status, 'value') else s.enrichment_status,
                "description": s.description if s.description else None,
                "tagline": s.tagline,
                "website_url": s.website_url,
                "stage": s.stage.value if hasattr(s.stage, 'value') else s.stage,
                "total_funding": s.total_funding,
                "employee_count": s.employee_count,
                "location_city": s.location_city,
                "location_state": s.location_state,
                "founders": [
                    {
                        "id": str(f.id),
                        "name": f.name,
                        "title": f.title,
                        "headline": f.headline,
                        "location": f.location,
                        "linkedin_url": f.linkedin_url,
                        "profile_photo_url": f.profile_photo_url,
                        "work_history": f.work_history,
                        "education_history": f.education_history,
                    }
                    for f in founders_by_startup.get(str(s.id), [])
                ],
                "created_at": s.created_at.isoformat(),
            }
            for s in startups
        ],
    }


@router.put("/api/admin/discovery/startups/{startup_id}/promote")
async def promote_startup(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    startup = await db.get(Startup, startup_id)
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")
    if startup.discovery_source != "delaware":
        raise HTTPException(status_code=400, detail="Not a discovered startup")

    startup.status = StartupStatus.approved
    await db.commit()
    return {"ok": True, "message": f"Promoted {startup.name} to approved"}


@router.put("/api/admin/discovery/startups/{startup_id}/reject")
async def reject_startup(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    startup = await db.get(Startup, startup_id)
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")

    startup.classification_status = ClassificationStatus.not_startup
    await db.commit()
    return {"ok": True, "message": f"Rejected {startup.name}"}
```

- [ ] **Step 2: Register the router in main.py**

In `backend/app/main.py`, add after the `investor_portfolio` import:

```python
from app.api.admin_discovery import router as admin_discovery_router
```

And add after the `investor_portfolio_router` include:

```python
app.include_router(admin_discovery_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin_discovery.py backend/app/main.py
git commit -m "feat(discovery): add admin API endpoints for import, pipeline, listing, promote/reject"
```

---

## Task 5: Admin Frontend — Types and API

**Files:**
- Modify: `admin/lib/types.ts`
- Modify: `admin/lib/api.ts`

- [ ] **Step 1: Add discovery types**

In `admin/lib/types.ts`, add at the end of the file:

```typescript
// ── Discovery ─────────────────────────────────────────────────────────

export interface DiscoveryFounder {
  id: string;
  name: string;
  title: string | null;
  headline: string | null;
  location: string | null;
  linkedin_url: string | null;
  profile_photo_url: string | null;
  work_history: { company: string; title: string; start_date: string; end_date: string; description: string }[] | null;
  education_history: { school: string; degree: string; field: string; start_year: number | null; end_year: number | null }[] | null;
}

export interface DiscoveredStartupItem {
  id: string;
  name: string;
  delaware_corp_name: string | null;
  delaware_file_number: string | null;
  delaware_filed_at: string | null;
  status: string;
  classification_status: string;
  classification_metadata: { classification?: string; confidence?: number; reasoning?: string } | null;
  enrichment_status: string;
  description: string | null;
  tagline: string | null;
  website_url: string | null;
  stage: string;
  total_funding: string | null;
  employee_count: string | null;
  location_city: string | null;
  location_state: string | null;
  founders: DiscoveryFounder[];
  created_at: string;
}

export interface DiscoveredStartupListResponse {
  total: number;
  page: number;
  per_page: number;
  pages: number;
  items: DiscoveredStartupItem[];
}

export interface DiscoveryBatchJob {
  id: string;
  status: "pending" | "running" | "paused" | "completed" | "failed";
  job_type: string;
  total_items: number;
  processed_items: number;
  current_item_name: string | null;
  items_created: number;
  error: string | null;
  started_at: string | null;
  paused_at: string | null;
  completed_at: string | null;
}

export interface DiscoveryStatusResponse {
  import_job: DiscoveryBatchJob | null;
  pipeline_job: DiscoveryBatchJob | null;
  stats: {
    total_imported: number;
    classified_startup: number;
    enriched: number;
    promoted: number;
  };
}
```

- [ ] **Step 2: Add discovery API methods**

In `admin/lib/api.ts`, first add the new types to the import at the top:

```typescript
import type {
  // ... existing imports ...
  DiscoveredStartupListResponse,
  DiscoveryStatusResponse,
} from "./types";
```

Then add these methods to the `adminApi` object (before the closing `};`):

```typescript
  // Discovery
  importDiscoveryCSV: async (token: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_URL}/api/admin/discovery/import`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    if (!res.ok) throw new Error(`API error: ${res.status} ${res.statusText}`);
    return res.json();
  },

  startDiscoveryPipeline: (token: string) =>
    apiFetch<{ id: string; status: string }>("/api/admin/discovery/batch", token, { method: "POST" }),

  pauseDiscoveryBatch: (token: string, jobId: string) =>
    apiFetch<{ id: string; status: string }>(`/api/admin/discovery/batch/${jobId}/pause`, token, { method: "PUT" }),

  resumeDiscoveryBatch: (token: string, jobId: string) =>
    apiFetch<{ id: string; status: string }>(`/api/admin/discovery/batch/${jobId}/resume`, token, { method: "PUT" }),

  getDiscoveryStatus: (token: string) =>
    apiFetch<DiscoveryStatusResponse>("/api/admin/discovery/batch/status", token),

  getDiscoveredStartups: (token: string, params: {
    classification?: string;
    enrichment?: string;
    q?: string;
    sort?: string;
    order?: string;
    page?: number;
    per_page?: number;
  }) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined) qs.set(k, String(v)); });
    return apiFetch<DiscoveredStartupListResponse>(`/api/admin/discovery/startups?${qs}`, token);
  },

  promoteStartup: (token: string, startupId: string) =>
    apiFetch<{ ok: boolean }>(`/api/admin/discovery/startups/${startupId}/promote`, token, { method: "PUT" }),

  rejectStartup: (token: string, startupId: string) =>
    apiFetch<{ ok: boolean }>(`/api/admin/discovery/startups/${startupId}/reject`, token, { method: "PUT" }),
```

- [ ] **Step 3: Commit**

```bash
git add admin/lib/types.ts admin/lib/api.ts
git commit -m "feat(discovery): add frontend types and API methods"
```

---

## Task 6: Admin Frontend — Discovery Page

**Files:**
- Create: `admin/app/discovery/page.tsx`
- Modify: `admin/components/Sidebar.tsx`

- [ ] **Step 1: Add Discovery to sidebar**

In `admin/components/Sidebar.tsx`, add to the `NAV_ITEMS` array after the Marketing entry:

```typescript
  { href: "/discovery", label: "Discovery" },
```

- [ ] **Step 2: Create the discovery page**

Create `admin/app/discovery/page.tsx`:

```tsx
"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useSession } from "next-auth/react";
import { adminApi } from "@/lib/api";
import { Sidebar } from "@/components/Sidebar";
import { AccessDenied } from "@/components/AccessDenied";
import type {
  DiscoveredStartupItem,
  DiscoveryStatusResponse,
} from "@/lib/types";

const CLASSIFICATION_TABS = [
  { key: "all", label: "All" },
  { key: "startup", label: "Startups" },
  { key: "not_startup", label: "Not Startup" },
  { key: "uncertain", label: "Uncertain" },
  { key: "unclassified", label: "Unclassified" },
];

function classificationBadge(status: string) {
  switch (status) {
    case "startup":
      return "bg-green-500/10 text-green-400 border-green-500/20";
    case "not_startup":
      return "bg-red-500/10 text-red-400 border-red-500/20";
    case "uncertain":
      return "bg-yellow-500/10 text-yellow-400 border-yellow-500/20";
    default:
      return "bg-gray-500/10 text-gray-400 border-gray-500/20";
  }
}

export default function DiscoveryPage() {
  const { data: session, status: authStatus } = useSession();
  const token = session?.backendToken;

  const [discoveryStatus, setDiscoveryStatus] = useState<DiscoveryStatusResponse | null>(null);
  const [startups, setStartups] = useState<DiscoveredStartupItem[]>([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [classification, setClassification] = useState("all");
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchStatus = useCallback(async () => {
    if (!token) return;
    try {
      const s = await adminApi.getDiscoveryStatus(token);
      setDiscoveryStatus(s);
    } catch {}
  }, [token]);

  const fetchStartups = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await adminApi.getDiscoveredStartups(token, {
        classification,
        q: search || undefined,
        page,
        per_page: 50,
      });
      setStartups(data.items);
      setTotal(data.total);
      setPages(data.pages);
    } catch {}
    setLoading(false);
  }, [token, classification, search, page]);

  useEffect(() => {
    fetchStatus();
    fetchStartups();
  }, [fetchStatus, fetchStartups]);

  // Poll while jobs are running
  useEffect(() => {
    const importRunning = discoveryStatus?.import_job?.status === "running";
    const pipelineRunning = discoveryStatus?.pipeline_job?.status === "running";
    if (!importRunning && !pipelineRunning) return;
    const interval = setInterval(() => {
      fetchStatus();
    }, 5000);
    return () => clearInterval(interval);
  }, [discoveryStatus?.import_job?.status, discoveryStatus?.pipeline_job?.status, fetchStatus]);

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !token) return;
    setBatchLoading(true);
    try {
      await adminApi.importDiscoveryCSV(token, file);
      await fetchStatus();
    } catch (err: any) {
      alert(err.message || "Import failed");
    }
    setBatchLoading(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function startPipeline() {
    if (!token) return;
    setBatchLoading(true);
    try {
      await adminApi.startDiscoveryPipeline(token);
      await fetchStatus();
    } catch (err: any) {
      alert(err.message || "Failed to start pipeline");
    }
    setBatchLoading(false);
  }

  async function pauseJob(jobId: string) {
    if (!token) return;
    setBatchLoading(true);
    try {
      await adminApi.pauseDiscoveryBatch(token, jobId);
      await fetchStatus();
    } catch (err: any) {
      alert(err.message || "Failed to pause");
    }
    setBatchLoading(false);
  }

  async function resumeJob(jobId: string) {
    if (!token) return;
    setBatchLoading(true);
    try {
      await adminApi.resumeDiscoveryBatch(token, jobId);
      await fetchStatus();
    } catch (err: any) {
      alert(err.message || "Failed to resume");
    }
    setBatchLoading(false);
  }

  async function handlePromote(id: string) {
    if (!token) return;
    try {
      await adminApi.promoteStartup(token, id);
      fetchStartups();
    } catch (err: any) {
      alert(err.message || "Failed to promote");
    }
  }

  async function handleReject(id: string) {
    if (!token) return;
    try {
      await adminApi.rejectStartup(token, id);
      fetchStartups();
    } catch (err: any) {
      alert(err.message || "Failed to reject");
    }
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setPage(1);
    setSearch(searchInput);
  }

  const importJob = discoveryStatus?.import_job;
  const pipelineJob = discoveryStatus?.pipeline_job;
  const stats = discoveryStatus?.stats;

  if (authStatus === "loading") return null;
  if (!session || (session as any).role !== "superadmin") return <AccessDenied />;

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold text-text-primary">Startup Discovery</h1>
          <p className="text-sm text-text-secondary mt-1">
            Delaware C-corp filings → Founder enrichment → AI classification → Perplexity research
          </p>
        </div>

        {/* Stats Bar */}
        {stats && (
          <div className="grid grid-cols-4 gap-4 mb-6">
            {[
              { label: "Imported", value: stats.total_imported },
              { label: "Classified as Startup", value: stats.classified_startup },
              { label: "Enriched", value: stats.enriched },
              { label: "Promoted", value: stats.promoted },
            ].map((stat) => (
              <div key={stat.label} className="border border-border rounded-lg p-3 bg-surface">
                <p className="text-xs text-text-tertiary">{stat.label}</p>
                <p className="text-xl font-semibold text-text-primary mt-1">
                  {stat.value.toLocaleString()}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* Batch Controls */}
        <div className="border border-border rounded-lg p-4 mb-6 bg-surface">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-medium text-text-primary">Pipeline Controls</h2>
              <p className="text-xs text-text-tertiary mt-0.5">
                Import Delaware CSVs, then run the classification + enrichment pipeline
              </p>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="file"
                accept=".csv"
                ref={fileInputRef}
                onChange={handleFileUpload}
                className="hidden"
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={batchLoading || importJob?.status === "running"}
                className="px-4 py-2 border border-border text-text-secondary text-sm rounded hover:border-text-tertiary transition disabled:opacity-50"
              >
                Import CSV
              </button>

              {(!pipelineJob || !["running", "paused"].includes(pipelineJob.status)) && (
                <button
                  onClick={startPipeline}
                  disabled={batchLoading}
                  className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
                >
                  Run Pipeline
                </button>
              )}

              {pipelineJob?.status === "running" && (
                <button
                  onClick={() => pauseJob(pipelineJob.id)}
                  disabled={batchLoading}
                  className="px-4 py-2 border border-border text-text-secondary text-sm rounded hover:border-text-tertiary transition disabled:opacity-50"
                >
                  Pause
                </button>
              )}

              {pipelineJob?.status === "paused" && (
                <button
                  onClick={() => resumeJob(pipelineJob.id)}
                  disabled={batchLoading}
                  className="px-4 py-2 bg-accent text-white text-sm rounded hover:bg-accent/90 transition disabled:opacity-50"
                >
                  Resume
                </button>
              )}
            </div>
          </div>

          {/* Import progress */}
          {importJob && importJob.status === "running" && (
            <div className="mt-3">
              <div className="flex items-center justify-between text-xs text-text-secondary mb-1">
                <span>
                  Importing: {importJob.processed_items}/{importJob.total_items}
                  {importJob.current_item_name && (
                    <> — <strong>{importJob.current_item_name}</strong></>
                  )}
                </span>
                <span>{importJob.items_created.toLocaleString()} created</span>
              </div>
              <div className="w-full bg-background rounded-full h-2">
                <div
                  className="h-2 rounded-full bg-accent transition-all"
                  style={{ width: `${importJob.total_items ? Math.round((importJob.processed_items / importJob.total_items) * 100) : 0}%` }}
                />
              </div>
            </div>
          )}

          {/* Pipeline progress */}
          {pipelineJob && ["running", "paused"].includes(pipelineJob.status) && (
            <div className="mt-3">
              <div className="flex items-center justify-between text-xs text-text-secondary mb-1">
                <span>
                  Pipeline: {pipelineJob.processed_items}/{pipelineJob.total_items}
                  {pipelineJob.current_item_name && pipelineJob.status === "running" && (
                    <> — <strong>{pipelineJob.current_item_name}</strong></>
                  )}
                  {pipelineJob.status === "paused" && " — paused"}
                </span>
                <span>{pipelineJob.items_created.toLocaleString()} startups found</span>
              </div>
              <div className="w-full bg-background rounded-full h-2">
                <div
                  className={`h-2 rounded-full transition-all ${pipelineJob.status === "paused" ? "bg-text-tertiary" : "bg-accent"}`}
                  style={{ width: `${pipelineJob.total_items ? Math.round((pipelineJob.processed_items / pipelineJob.total_items) * 100) : 0}%` }}
                />
              </div>
            </div>
          )}

          {pipelineJob?.status === "completed" && (
            <p className="text-xs text-text-tertiary mt-2">
              Pipeline complete — {pipelineJob.items_created.toLocaleString()} startups identified
              out of {pipelineJob.total_items.toLocaleString()} processed
            </p>
          )}
        </div>

        {/* Classification Tabs */}
        <div className="flex gap-1 mb-4">
          {CLASSIFICATION_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => { setClassification(tab.key); setPage(1); }}
              className={`px-3 py-1.5 text-sm rounded transition ${
                classification === tab.key
                  ? "bg-accent text-white"
                  : "text-text-secondary hover:text-text-primary hover:bg-hover-row"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex gap-2 mb-4">
          <input
            type="text"
            placeholder="Search company name..."
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
              onClick={() => { setSearchInput(""); setSearch(""); setPage(1); }}
              className="px-3 py-2 text-xs text-text-tertiary hover:text-text-secondary transition"
            >
              Clear
            </button>
          )}
        </form>

        {/* Results */}
        {loading ? (
          <p className="text-text-tertiary text-sm py-10 text-center">Loading...</p>
        ) : (
          <>
            <p className="text-xs text-text-tertiary mb-3">{total.toLocaleString()} results</p>
            <div className="space-y-2">
              {startups.map((s) => (
                <div key={s.id} className="border border-border rounded-lg bg-surface">
                  <div
                    className="flex items-center justify-between p-3 cursor-pointer hover:bg-hover-row transition"
                    onClick={() => setExpandedId(expandedId === s.id ? null : s.id)}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-text-primary text-sm truncate">
                          {s.name}
                        </span>
                        {s.delaware_corp_name && s.delaware_corp_name !== s.name && (
                          <span className="text-xs text-text-tertiary truncate">
                            (filed as: {s.delaware_corp_name})
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-text-tertiary">
                        {s.delaware_filed_at && (
                          <span>Filed: {new Date(s.delaware_filed_at).toLocaleDateString()}</span>
                        )}
                        <span>{s.founders.length} founder{s.founders.length !== 1 ? "s" : ""}</span>
                        {s.location_city && <span>{s.location_city}, {s.location_state}</span>}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                      <span
                        className={`px-2 py-0.5 text-xs rounded border ${classificationBadge(s.classification_status)}`}
                      >
                        {s.classification_status}
                      </span>
                      {s.enrichment_status === "complete" && (
                        <span className="px-2 py-0.5 text-xs rounded border bg-blue-500/10 text-blue-400 border-blue-500/20">
                          enriched
                        </span>
                      )}
                      {s.status === "approved" && (
                        <span className="px-2 py-0.5 text-xs rounded border bg-green-500/10 text-green-400 border-green-500/20">
                          promoted
                        </span>
                      )}
                    </div>
                  </div>

                  {expandedId === s.id && (
                    <div className="border-t border-border p-4">
                      {/* Actions */}
                      <div className="flex gap-2 mb-4">
                        {s.status !== "approved" && s.classification_status === "startup" && (
                          <button
                            onClick={(e) => { e.stopPropagation(); handlePromote(s.id); }}
                            className="px-3 py-1 text-xs bg-accent text-white rounded hover:bg-accent/90 transition"
                          >
                            Promote to Approved
                          </button>
                        )}
                        {s.classification_status !== "not_startup" && (
                          <button
                            onClick={(e) => { e.stopPropagation(); handleReject(s.id); }}
                            className="px-3 py-1 text-xs border border-border text-text-secondary rounded hover:border-red-500 hover:text-red-400 transition"
                          >
                            Reject
                          </button>
                        )}
                      </div>

                      {/* Classification reasoning */}
                      {s.classification_metadata?.reasoning && (
                        <div className="mb-4">
                          <h4 className="text-xs font-medium text-text-secondary mb-1">Classification Reasoning</h4>
                          <p className="text-sm text-text-primary leading-relaxed">
                            {s.classification_metadata.reasoning}
                          </p>
                          {s.classification_metadata.confidence !== undefined && (
                            <p className="text-xs text-text-tertiary mt-1">
                              Confidence: {Math.round(s.classification_metadata.confidence * 100)}%
                            </p>
                          )}
                        </div>
                      )}

                      {/* Company details (if enriched) */}
                      {s.enrichment_status === "complete" && s.description && (
                        <div className="mb-4">
                          <h4 className="text-xs font-medium text-text-secondary mb-1">Company Details</h4>
                          <p className="text-sm text-text-primary">{s.description}</p>
                          <div className="flex gap-4 mt-2 text-xs text-text-tertiary">
                            {s.stage && <span>Stage: {s.stage}</span>}
                            {s.total_funding && <span>Funding: {s.total_funding}</span>}
                            {s.employee_count && <span>Team: {s.employee_count}</span>}
                            {s.website_url && (
                              <a href={s.website_url} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
                                Website
                              </a>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Founders */}
                      {s.founders.length > 0 && (
                        <div>
                          <h4 className="text-xs font-medium text-text-secondary mb-2">Founders</h4>
                          <div className="space-y-3">
                            {s.founders.map((f) => (
                              <div key={f.id} className="border border-border rounded p-3 bg-background">
                                <div className="flex items-center gap-3">
                                  {f.profile_photo_url && (
                                    <img
                                      src={f.profile_photo_url}
                                      alt={f.name}
                                      className="w-10 h-10 rounded-full object-cover"
                                    />
                                  )}
                                  <div>
                                    <div className="flex items-center gap-2">
                                      <span className="font-medium text-sm text-text-primary">{f.name}</span>
                                      {f.linkedin_url && (
                                        <a
                                          href={f.linkedin_url}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="text-xs text-accent hover:underline"
                                        >
                                          LinkedIn
                                        </a>
                                      )}
                                    </div>
                                    {f.headline && (
                                      <p className="text-xs text-text-tertiary">{f.headline}</p>
                                    )}
                                    {f.location && (
                                      <p className="text-xs text-text-tertiary">{f.location}</p>
                                    )}
                                  </div>
                                </div>

                                {f.work_history && f.work_history.length > 0 && (
                                  <div className="mt-2">
                                    <p className="text-xs text-text-secondary font-medium mb-1">Work History</p>
                                    {f.work_history.slice(0, 3).map((job, i) => (
                                      <p key={i} className="text-xs text-text-tertiary">
                                        {job.title} at {job.company}
                                      </p>
                                    ))}
                                  </div>
                                )}

                                {f.education_history && f.education_history.length > 0 && (
                                  <div className="mt-2">
                                    <p className="text-xs text-text-secondary font-medium mb-1">Education</p>
                                    {f.education_history.slice(0, 2).map((edu, i) => (
                                      <p key={i} className="text-xs text-text-tertiary">
                                        {edu.degree} {edu.field ? `in ${edu.field}` : ""} — {edu.school}
                                      </p>
                                    ))}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {startups.length === 0 && (
                <p className="text-center text-text-tertiary py-8">
                  No discovered startups yet. Import a Delaware CSV to get started.
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

- [ ] **Step 3: Commit**

```bash
git add admin/app/discovery/page.tsx admin/components/Sidebar.tsx
git commit -m "feat(discovery): add admin discovery page with batch controls, stats, and startup listing"
```

---

## Self-Review

**Spec coverage check:**
- Bulk import (Step 1) → Task 2
- Daily scraper (Step 2) → Out of scope per spec ("manual trigger first, automate later")
- Heuristic filter (Step 3) → Task 3 (`is_heuristic_not_startup`)
- Founder discovery + Proxycurl (Step 4) → Task 3 (`_enrich_founders`, `_proxycurl_company_search`, `_proxycurl_person_profile`, `_search_founder_linkedin`)
- Brand name resolution (Step 4c) → Task 3 (`_detect_brand_name`)
- Claude classification (Step 5) → Task 3 (`_classify_with_claude`)
- Perplexity enrichment (Step 6) → Task 3 (`_enrich_with_perplexity`, `_apply_enrichment`)
- Batch execution with pause/resume → Task 3 (`run_discovery_pipeline`)
- API endpoints → Task 4 (all 8 endpoints from spec)
- Admin UI → Task 6 (stats bar, batch controls, classification tabs, expandable rows, promote/reject)
- Data model → Task 1 (migration, models, config)
- Proxycurl + SerpAPI config → Task 1 (`config.py`)

**Placeholder scan:** No TBDs, TODOs, or "implement later" found.

**Type consistency:**
- `ClassificationStatus` enum values match across model, migration, pipeline, API, and frontend
- `DiscoveryBatchJob` fields match across model, migration, API serialization, and frontend types
- `StartupFounder` Proxycurl fields match across model, migration, pipeline enrichment, API serialization, and frontend types
- `BatchJobStatus` reused from existing `investor.py` — consistent
