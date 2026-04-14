# Scout Batch Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automated background pipeline that sweeps geographic markets to discover investors, find their portfolio startups, add to triage, and trigger enrichment — with progress tracking, pause/resume, and rate limiting.

**Architecture:** Database-backed job queue with `batch_jobs` and `batch_job_steps` tables. A single async worker loop processes steps sequentially with rate-limiting delays. Steps dynamically generate follow-on steps (discover investors → find startups → triage → enrich). Admin UI polls API endpoints for progress.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend), Next.js + React (admin UI), Perplexity Sonar Pro API (scout calls), PostgreSQL (job state)

---

## File Structure

### New files:
| File | Responsibility |
|---|---|
| `backend/app/models/batch_job.py` | BatchJob and BatchJobStep SQLAlchemy models with enums |
| `backend/app/services/batch_locations.py` | Hardcoded BATCH_LOCATIONS list and BATCH_STAGES, stage label helper |
| `backend/app/services/scout.py` | Extracted shared scout logic: Perplexity API call, response parsing, startup creation with dedup |
| `backend/app/services/batch_worker.py` | Worker loop, step executors, follow-on step generation, progress tracking |
| `backend/app/api/admin_batch.py` | API endpoints: start, pause, resume, cancel, active, steps, investors, startups, log |
| `admin/app/batch/page.tsx` | Admin UI: control bar, tabbed progress view (locations/investors/startups), live log |

### Modified files:
| File | Change |
|---|---|
| `backend/app/models/__init__.py` | Import BatchJob, BatchJobStep |
| `backend/app/api/admin_scout.py` | Replace inline logic with imports from `services/scout.py` |
| `backend/app/main.py` | Register batch router |
| `admin/lib/api.ts` | Add batch API methods |
| `admin/components/Sidebar.tsx` | Add "Batch" nav item |

---

### Task 1: Batch Job Data Models

**Files:**
- Create: `backend/app/models/batch_job.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the batch job models file**

```python
# backend/app/models/batch_job.py
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class BatchJobType(str, enum.Enum):
    initial = "initial"
    refresh = "refresh"


class BatchJobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class BatchJobPhase(str, enum.Enum):
    discovering_investors = "discovering_investors"
    finding_startups = "finding_startups"
    enriching = "enriching"
    complete = "complete"


class BatchStepType(str, enum.Enum):
    discover_investors = "discover_investors"
    find_startups = "find_startups"
    add_to_triage = "add_to_triage"
    enrich = "enrich"


class BatchStepStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_type: Mapped[BatchJobType] = mapped_column(default=BatchJobType.initial)
    status: Mapped[BatchJobStatus] = mapped_column(default=BatchJobStatus.pending)
    refresh_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_summary: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default=text("'{}'::jsonb")
    )
    current_phase: Mapped[BatchJobPhase] = mapped_column(
        default=BatchJobPhase.discovering_investors
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    steps: Mapped[list["BatchJobStep"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class BatchJobStep(Base):
    __tablename__ = "batch_job_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("batch_jobs.id", ondelete="CASCADE")
    )
    step_type: Mapped[BatchStepType]
    status: Mapped[BatchStepStatus] = mapped_column(default=BatchStepStatus.pending)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    job: Mapped["BatchJob"] = relationship(back_populates="steps")
```

- [ ] **Step 2: Update models __init__.py**

Add to the imports in `backend/app/models/__init__.py`:

```python
from app.models.batch_job import BatchJob, BatchJobStep
```

- [ ] **Step 3: Create Alembic migration**

Run from `backend/` directory inside the backend container:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic revision --autogenerate -m "add batch_jobs and batch_job_steps tables"
```

Then apply:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

If running alembic inside Docker is not set up, create the migration manually as a SQL file and run it via psql:

```sql
CREATE TYPE batchjobtype AS ENUM ('initial', 'refresh');
CREATE TYPE batchjobstatus AS ENUM ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled');
CREATE TYPE batchjobphase AS ENUM ('discovering_investors', 'finding_startups', 'enriching', 'complete');
CREATE TYPE batchsteptype AS ENUM ('discover_investors', 'find_startups', 'add_to_triage', 'enrich');
CREATE TYPE batchstepstatus AS ENUM ('pending', 'running', 'completed', 'failed', 'skipped');

CREATE TABLE batch_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type batchjobtype NOT NULL DEFAULT 'initial',
    status batchjobstatus NOT NULL DEFAULT 'pending',
    refresh_days INTEGER,
    progress_summary JSONB NOT NULL DEFAULT '{}',
    current_phase batchjobphase NOT NULL DEFAULT 'discovering_investors',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE batch_job_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES batch_jobs(id) ON DELETE CASCADE,
    step_type batchsteptype NOT NULL,
    status batchstepstatus NOT NULL DEFAULT 'pending',
    params JSONB NOT NULL DEFAULT '{}',
    result JSONB,
    error TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX ix_batch_job_steps_job_id ON batch_job_steps(job_id);
CREATE INDEX ix_batch_job_steps_status ON batch_job_steps(status);
CREATE INDEX ix_batch_job_steps_sort_order ON batch_job_steps(sort_order);
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/batch_job.py backend/app/models/__init__.py
git commit -m "feat: add BatchJob and BatchJobStep data models"
```

---

### Task 2: Batch Locations Constants

**Files:**
- Create: `backend/app/services/batch_locations.py`

- [ ] **Step 1: Create the locations file**

```python
# backend/app/services/batch_locations.py

BATCH_LOCATIONS = [
    # US Tier 1
    {"city": "San Francisco", "state": "CA", "country": "US"},
    {"city": "New York", "state": "NY", "country": "US"},
    {"city": "Boston", "state": "MA", "country": "US"},
    {"city": "Los Angeles", "state": "CA", "country": "US"},
    {"city": "Seattle", "state": "WA", "country": "US"},
    {"city": "Austin", "state": "TX", "country": "US"},
    {"city": "Chicago", "state": "IL", "country": "US"},
    {"city": "Miami", "state": "FL", "country": "US"},
    {"city": "Denver", "state": "CO", "country": "US"},
    {"city": "Washington", "state": "DC", "country": "US"},
    # US Tier 2
    {"city": "San Diego", "state": "CA", "country": "US"},
    {"city": "Atlanta", "state": "GA", "country": "US"},
    {"city": "Dallas", "state": "TX", "country": "US"},
    {"city": "Houston", "state": "TX", "country": "US"},
    {"city": "Philadelphia", "state": "PA", "country": "US"},
    {"city": "Minneapolis", "state": "MN", "country": "US"},
    {"city": "Detroit", "state": "MI", "country": "US"},
    {"city": "Pittsburgh", "state": "PA", "country": "US"},
    {"city": "Nashville", "state": "TN", "country": "US"},
    {"city": "Raleigh-Durham", "state": "NC", "country": "US"},
    {"city": "Salt Lake City", "state": "UT", "country": "US"},
    {"city": "Portland", "state": "OR", "country": "US"},
    {"city": "Phoenix", "state": "AZ", "country": "US"},
    {"city": "Columbus", "state": "OH", "country": "US"},
    {"city": "Indianapolis", "state": "IN", "country": "US"},
    {"city": "St. Louis", "state": "MO", "country": "US"},
    {"city": "Baltimore", "state": "MD", "country": "US"},
    {"city": "Tampa", "state": "FL", "country": "US"},
    {"city": "Charlotte", "state": "NC", "country": "US"},
    {"city": "Las Vegas", "state": "NV", "country": "US"},
    {"city": "Cincinnati", "state": "OH", "country": "US"},
    {"city": "Kansas City", "state": "MO", "country": "US"},
    {"city": "Birmingham", "state": "AL", "country": "US"},
    {"city": "Madison", "state": "WI", "country": "US"},
    {"city": "Omaha", "state": "NE", "country": "US"},
    # International - North America
    {"city": "Toronto", "state": None, "country": "Canada"},
    {"city": "Vancouver", "state": None, "country": "Canada"},
    {"city": "Montreal", "state": None, "country": "Canada"},
    # International - Europe
    {"city": "London", "state": None, "country": "UK"},
    {"city": "Berlin", "state": None, "country": "Germany"},
    {"city": "Paris", "state": None, "country": "France"},
    {"city": "Amsterdam", "state": None, "country": "Netherlands"},
    {"city": "Stockholm", "state": None, "country": "Sweden"},
    # International - Asia-Pacific
    {"city": "Singapore", "state": None, "country": "Singapore"},
    {"city": "Sydney", "state": None, "country": "Australia"},
    {"city": "Bangalore", "state": None, "country": "India"},
    {"city": "Tel Aviv", "state": None, "country": "Israel"},
    # International - Latin America
    {"city": "Sao Paulo", "state": None, "country": "Brazil"},
    {"city": "Mexico City", "state": None, "country": "Mexico"},
    {"city": "Bogota", "state": None, "country": "Colombia"},
]

BATCH_STAGES = ["pre_seed", "seed", "series_a", "series_b", "series_c", "growth"]

STAGE_LABELS = {
    "pre_seed": "Pre-Seed",
    "seed": "Seed",
    "series_a": "Series A",
    "series_b": "Series B",
    "series_c": "Series C",
    "growth": "Growth",
}


def format_location(loc: dict) -> str:
    """Format a location dict as a display string like 'Austin, TX' or 'London, UK'."""
    if loc["state"]:
        return f"{loc['city']}, {loc['state']}"
    return f"{loc['city']}, {loc['country']}"
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/batch_locations.py
git commit -m "feat: add hardcoded batch locations and stages"
```

---

### Task 3: Extract Shared Scout Service

**Files:**
- Create: `backend/app/services/scout.py`
- Modify: `backend/app/api/admin_scout.py`

This extracts the Perplexity API call logic, response parsing, and startup creation into a shared module that both the admin scout endpoint and the batch worker can import.

- [ ] **Step 1: Create the shared scout service**

```python
# backend/app/services/scout.py
"""Shared scout logic: Perplexity API calls, response parsing, startup creation with dedup."""
import json
import re
import uuid
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.startup import Startup, StartupStage, StartupStatus
from app.services.dedup import find_duplicate, normalize_domain, normalize_name


SCOUT_SYSTEM_PROMPT = """You are a startup research assistant for Acutal, a startup investment intelligence platform.

When the user asks you to find startups, search the web thoroughly and return your findings.

IMPORTANT: You MUST include a JSON block in your response with structured startup data. Format it exactly like this, wrapped in ```json code fences:

```json
[
  {
    "name": "Company Name",
    "website_url": "https://example.com",
    "description": "2-3 sentence description of what the company does, their product, and their market.",
    "stage": "seed",
    "location_city": "San Francisco",
    "location_state": "CA",
    "location_country": "US",
    "founders": "Founder Name 1, Founder Name 2",
    "funding_raised": "$10M",
    "key_investors": "Sequoia, Y Combinator",
    "linkedin_url": "https://linkedin.com/company/example",
    "founded_year": "2023"
  }
]
```

Rules:
- stage must be one of: pre_seed, seed, series_a, series_b, series_c, growth
- CRITICAL: For EVERY company, you MUST research and include: website_url, founders (full names), \
funding_raised (total amount), location_city, location_state, key_investors, and founded_year. \
Search each company individually if needed. Empty fields are not acceptable when the information \
is publicly available.
- Be thorough in descriptions — include what the product does, their market, traction, and why they're notable
- If a field truly cannot be found after searching, use empty string
- Return as many startups as you can find that match the query
- After the JSON block, include a brief summary of what you found

When the user asks follow-up questions or wants to refine, update your search accordingly."""


class StartupCandidate(BaseModel):
    name: str
    website_url: str | None = None
    description: str = ""
    stage: str = "seed"
    location_city: str | None = None
    location_state: str | None = None
    location_country: str = "US"
    founders: str | None = None
    funding_raised: str | None = None
    key_investors: str | None = None
    linkedin_url: str | None = None
    founded_year: str | None = None


def extract_startups_from_response(text: str) -> list[dict]:
    """Extract structured startup data from Perplexity's response."""
    json_match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    array_match = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
    if array_match:
        try:
            data = json.loads(array_match.group(0))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    return []


def clean_reply(text: str) -> str:
    """Remove the JSON block from the reply text for display."""
    cleaned = re.sub(r"```json\s*\n.*?\n\s*```", "", text, flags=re.DOTALL)
    return cleaned.strip()


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug


async def call_perplexity(
    system_prompt: str, user_message: str, max_tokens: int = 16384
) -> dict | None:
    """Call Perplexity Sonar Pro API with retry logic.

    Returns the full API response dict on success, None on failure.
    """
    if not settings.perplexity_api_key:
        return None

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    last_error = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.perplexity_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "sonar-pro",
                        "messages": messages,
                        "temperature": 0.1,
                        "max_tokens": max_tokens,
                    },
                )
                if resp.status_code == 200:
                    return resp.json()
                last_error = f"Perplexity API error ({resp.status_code}): {resp.text[:200]}"
                if resp.status_code < 500:
                    break
        except httpx.TimeoutException:
            last_error = "Perplexity API timed out"
        except Exception as e:
            last_error = str(e)

    return None


async def add_startups_to_triage(
    db: AsyncSession, candidates: list[StartupCandidate]
) -> dict:
    """Add startup candidates to the database with dedup.

    Returns {"created": [...], "skipped": [...]}.
    """
    created = []
    skipped = []

    for candidate in candidates:
        dup = await find_duplicate(db, candidate.name, candidate.website_url)
        if dup is not None:
            skipped.append(candidate.name)
            continue

        slug = slugify(candidate.name)
        slug_check = await db.execute(select(Startup).where(Startup.slug == slug))
        if slug_check.scalar_one_or_none() is not None:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        stage = candidate.stage
        valid_stages = [s.value for s in StartupStage]
        if stage not in valid_stages:
            stage = "seed"

        startup = Startup(
            name=candidate.name,
            slug=slug,
            description=candidate.description or f"{candidate.name} startup",
            website_url=candidate.website_url,
            stage=StartupStage(stage),
            status=StartupStatus.pending,
            location_city=candidate.location_city,
            location_state=candidate.location_state,
            location_country=candidate.location_country or "US",
        )
        db.add(startup)
        await db.flush()

        # Try to fetch logo
        if candidate.website_url and settings.logo_dev_token:
            try:
                parsed = urlparse(
                    candidate.website_url
                    if "://" in candidate.website_url
                    else f"https://{candidate.website_url}"
                )
                domain = parsed.hostname or ""
                domain = re.sub(r"^www\.", "", domain)
                if domain:
                    logo_url = f"https://img.logo.dev/{domain}?token={settings.logo_dev_token}&format=png&size=128"
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        logo_resp = await client.get(logo_url, follow_redirects=True)
                        if logo_resp.status_code == 200 and "image" in (
                            logo_resp.headers.get("content-type") or ""
                        ):
                            startup.logo_url = logo_url
            except Exception:
                pass

        created.append(
            {
                "id": str(startup.id),
                "name": startup.name,
                "slug": startup.slug,
                "status": startup.status.value,
            }
        )

    await db.commit()
    return {"created": created, "skipped": skipped}
```

- [ ] **Step 2: Update admin_scout.py to import from shared service**

Replace the entire file `backend/app/api/admin_scout.py` with:

```python
# backend/app/api/admin_scout.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.config import settings
from app.db.session import get_db
from app.models.startup import Startup
from app.models.user import User
from app.services.dedup import normalize_domain, normalize_name
from app.services.scout import (
    SCOUT_SYSTEM_PROMPT,
    StartupCandidate,
    add_startups_to_triage,
    call_perplexity,
    clean_reply,
    extract_startups_from_response,
)

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ScoutChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ScoutAddRequest(BaseModel):
    startups: list[StartupCandidate]


@router.post("/api/admin/scout/chat")
async def scout_chat(
    body: ScoutChatRequest,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    if not settings.perplexity_api_key:
        raise HTTPException(
            status_code=500, detail="ACUTAL_PERPLEXITY_API_KEY not configured"
        )

    data = await call_perplexity(SCOUT_SYSTEM_PROMPT, body.message)
    if data is None:
        raise HTTPException(status_code=502, detail="Perplexity API failed")

    raw_content = data["choices"][0]["message"]["content"]
    citations = data.get("citations", [])

    startups_raw = extract_startups_from_response(raw_content)
    startups = []
    for s in startups_raw:
        try:
            startups.append(StartupCandidate(**s).model_dump())
        except Exception:
            continue

    # Check for duplicates against existing startups
    existing_result = await db.execute(select(Startup))
    existing_startups = existing_result.scalars().all()

    existing_lookup = {}
    for es in existing_startups:
        existing_lookup[normalize_name(es.name)] = {
            "id": str(es.id),
            "name": es.name,
            "status": es.status.value,
        }
        if es.website_url:
            existing_lookup[normalize_domain(es.website_url)] = {
                "id": str(es.id),
                "name": es.name,
                "status": es.status.value,
            }

    for startup_dict in startups:
        n = normalize_name(startup_dict.get("name", ""))
        d = normalize_domain(startup_dict.get("website_url", ""))
        match = existing_lookup.get(n) or (existing_lookup.get(d) if d else None)
        if match:
            startup_dict["already_on_platform"] = True
            startup_dict["existing_status"] = match["status"]
            startup_dict["existing_id"] = match["id"]
        else:
            startup_dict["already_on_platform"] = False

    reply = clean_reply(raw_content)
    if not reply:
        reply = f"Found {len(startups)} startups."

    return {
        "reply": reply,
        "startups": startups,
        "citations": citations,
    }


@router.post("/api/admin/scout/add")
async def scout_add_startups(
    body: ScoutAddRequest,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await add_startups_to_triage(db, body.startups)
    created = result["created"]
    skipped = result["skipped"]
    return {
        "created": created,
        "skipped": skipped,
        "message": f"Added {len(created)} startups to triage. {f'Skipped {len(skipped)} duplicates.' if skipped else ''}",
    }
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/scout.py backend/app/api/admin_scout.py
git commit -m "refactor: extract shared scout logic into services/scout.py"
```

---

### Task 4: Batch Worker Service

**Files:**
- Create: `backend/app/services/batch_worker.py`

This is the core of the batch pipeline — the async worker loop that processes steps sequentially.

- [ ] **Step 1: Create the batch worker**

```python
# backend/app/services/batch_worker.py
"""Batch worker: processes batch job steps sequentially with rate limiting."""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models.batch_job import (
    BatchJob,
    BatchJobPhase,
    BatchJobStatus,
    BatchJobStep,
    BatchStepStatus,
    BatchStepType,
)
from app.models.startup import Startup, StartupStatus
from app.services.batch_locations import STAGE_LABELS, format_location
from app.services.dedup import normalize_name
from app.services.enrichment import run_enrichment_pipeline
from app.services.scout import (
    SCOUT_SYSTEM_PROMPT,
    StartupCandidate,
    add_startups_to_triage,
    call_perplexity,
    clean_reply,
    extract_startups_from_response,
)

logger = logging.getLogger(__name__)

# Delays in seconds after each step type
STEP_DELAYS = {
    BatchStepType.discover_investors: 90,
    BatchStepType.find_startups: 90,
    BatchStepType.add_to_triage: 2,
    BatchStepType.enrich: 10,
}

# System prompt for investor discovery (no startup JSON needed)
INVESTOR_DISCOVERY_PROMPT = """You are a venture capital research assistant.

When asked to find investors in a location, search thoroughly and return a JSON block with investor data.

IMPORTANT: You MUST include a JSON block in your response wrapped in ```json code fences:

```json
[
  {
    "name": "Fund or Group Name",
    "type": "vc|angel_group|accelerator",
    "focus": "Brief description of investment focus",
    "notable_partners": "Partner names if known",
    "deal_count": "Approximate number of deals if known"
  }
]
```

Rules:
- Be EXHAUSTIVE — find every firm, angel group, and accelerator you can
- Search multiple sources: Crunchbase, PitchBook, LinkedIn, AngelList, local startup ecosystem sites
- Include both well-known and smaller/newer firms
- If you're unsure about a field, use empty string
- After the JSON block, include a brief summary"""


def _extract_investors_from_response(text: str) -> list[str]:
    """Extract investor names from Perplexity's response."""
    json_match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if isinstance(data, list):
                return [item["name"] for item in data if isinstance(item, dict) and item.get("name")]
        except (json.JSONDecodeError, KeyError):
            pass

    array_match = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
    if array_match:
        try:
            data = json.loads(array_match.group(0))
            if isinstance(data, list):
                return [item["name"] for item in data if isinstance(item, dict) and item.get("name")]
        except (json.JSONDecodeError, KeyError):
            pass

    return []


async def _get_next_sort_order(db: AsyncSession, job_id) -> int:
    """Get the next available sort_order for a job."""
    result = await db.execute(
        select(func.coalesce(func.max(BatchJobStep.sort_order), 0))
        .where(BatchJobStep.job_id == job_id)
    )
    return (result.scalar() or 0) + 1


async def _update_progress(db: AsyncSession, job: BatchJob):
    """Recalculate and update the job's progress_summary from step data."""
    steps = await db.execute(
        select(BatchJobStep).where(BatchJobStep.job_id == job.id)
    )
    all_steps = steps.scalars().all()

    locations_completed = 0
    investors_found = 0
    startups_found = 0
    startups_added = 0
    startups_skipped = 0
    startups_enriched = 0
    startups_enrich_failed = 0

    for step in all_steps:
        if step.step_type == BatchStepType.discover_investors and step.status == BatchStepStatus.completed:
            locations_completed += 1
            if step.result and "investors" in step.result:
                investors_found += len(step.result["investors"])
        elif step.step_type == BatchStepType.find_startups and step.status == BatchStepStatus.completed:
            if step.result and "startups" in step.result:
                startups_found += len(step.result["startups"])
        elif step.step_type == BatchStepType.add_to_triage and step.status == BatchStepStatus.completed:
            if step.result:
                startups_added += len(step.result.get("created", []))
                startups_skipped += len(step.result.get("skipped", []))
        elif step.step_type == BatchStepType.enrich:
            if step.status == BatchStepStatus.completed:
                startups_enriched += 1
            elif step.status == BatchStepStatus.failed:
                startups_enrich_failed += 1

    # Find current step info
    current_step = None
    for step in all_steps:
        if step.status == BatchStepStatus.running:
            current_step = step
            break

    summary = {
        "locations_total": len([s for s in all_steps if s.step_type == BatchStepType.discover_investors]),
        "locations_completed": locations_completed,
        "investors_found": investors_found,
        "startups_found": startups_found,
        "startups_added": startups_added,
        "startups_skipped_duplicate": startups_skipped,
        "startups_enriched": startups_enriched,
        "startups_enrich_failed": startups_enrich_failed,
    }

    if current_step and current_step.params:
        p = current_step.params
        if p.get("city"):
            loc_str = f"{p['city']}, {p.get('state') or p.get('country', '')}"
            summary["current_location"] = loc_str
        if p.get("stage"):
            summary["current_stage"] = p["stage"]
        if p.get("investor"):
            summary["current_investor"] = p["investor"]
        if p.get("startup_name"):
            summary["current_startup"] = p["startup_name"]

    job.progress_summary = summary
    job.updated_at = datetime.now(timezone.utc)

    # Update current_phase based on what's running
    has_pending_discover = any(
        s.step_type == BatchStepType.discover_investors and s.status == BatchStepStatus.pending
        for s in all_steps
    )
    has_pending_find = any(
        s.step_type == BatchStepType.find_startups and s.status == BatchStepStatus.pending
        for s in all_steps
    )
    has_pending_enrich = any(
        s.step_type == BatchStepType.enrich and s.status == BatchStepStatus.pending
        for s in all_steps
    )

    if has_pending_discover:
        job.current_phase = BatchJobPhase.discovering_investors
    elif has_pending_find:
        job.current_phase = BatchJobPhase.finding_startups
    elif has_pending_enrich:
        job.current_phase = BatchJobPhase.enriching
    else:
        job.current_phase = BatchJobPhase.complete

    await db.commit()


async def _execute_discover_investors(
    db: AsyncSession, step: BatchJobStep, job: BatchJob
) -> None:
    """Execute a discover_investors step: call Perplexity to find investors in a location+stage."""
    params = step.params
    city = params["city"]
    state = params.get("state")
    country = params["country"]
    stage = params["stage"]
    stage_label = STAGE_LABELS.get(stage, stage)
    location_str = f"{city}, {state}" if state else f"{city}, {country}"

    refresh_days = job.refresh_days
    if refresh_days:
        prompt = (
            f"Find all {stage_label} venture capital firms, angel investor groups, and startup accelerators "
            f"that have made investments in {location_str} in the last {refresh_days} days.\n\n"
            f"Return EVERY firm you can find — include fund name, notable partners, investment focus, "
            f"and approximate deal count. Be thorough and search multiple sources."
        )
    else:
        prompt = (
            f"Find all {stage_label} venture capital firms, angel investor groups, and startup accelerators "
            f"that are actively investing in {location_str}.\n\n"
            f"Return EVERY firm you can find — include fund name, notable partners, investment focus, "
            f"and approximate deal count. Be thorough and search multiple sources."
        )

    data = await call_perplexity(INVESTOR_DISCOVERY_PROMPT, prompt)
    if data is None:
        raise Exception(f"Perplexity API failed for {location_str} / {stage_label}")

    raw_content = data["choices"][0]["message"]["content"]
    investors = _extract_investors_from_response(raw_content)
    reply = clean_reply(raw_content)

    step.result = {
        "investors": investors,
        "scout_reply": reply[:2000],
    }

    # Generate find_startups steps for each investor
    if investors:
        # Check which investors already have find_startups steps in this job
        existing_steps = await db.execute(
            select(BatchJobStep)
            .where(BatchJobStep.job_id == job.id)
            .where(BatchJobStep.step_type == BatchStepType.find_startups)
        )
        existing_investors = set()
        for s in existing_steps.scalars().all():
            if s.params.get("investor"):
                existing_investors.add(normalize_name(s.params["investor"]))

        # For refresh runs, also check previous batch jobs
        if job.job_type.value == "refresh":
            prev_steps = await db.execute(
                select(BatchJobStep)
                .where(BatchJobStep.job_id != job.id)
                .where(BatchJobStep.step_type == BatchStepType.find_startups)
                .where(BatchJobStep.status == BatchStepStatus.completed)
            )
            for s in prev_steps.scalars().all():
                if s.params.get("investor"):
                    existing_investors.add(normalize_name(s.params["investor"]))

        next_order = await _get_next_sort_order(db, job.id)
        for inv_name in investors:
            if normalize_name(inv_name) in existing_investors:
                continue
            new_step = BatchJobStep(
                job_id=job.id,
                step_type=BatchStepType.find_startups,
                params={
                    "investor": inv_name,
                    "stage": stage,
                    "city": city,
                    "state": state,
                    "country": country,
                },
                sort_order=next_order,
            )
            db.add(new_step)
            next_order += 1

    logger.info(f"Discovered {len(investors)} investors in {location_str} ({stage_label})")


async def _execute_find_startups(
    db: AsyncSession, step: BatchJobStep, job: BatchJob
) -> None:
    """Execute a find_startups step: call Perplexity to find portfolio companies for an investor."""
    params = step.params
    investor = params["investor"]
    stage = params["stage"]
    stage_label = STAGE_LABELS.get(stage, stage)

    refresh_days = job.refresh_days
    if refresh_days:
        prompt = (
            f"Find all startup investments made by {investor} at the {stage_label} stage "
            f"in the last {refresh_days} days. List every new portfolio company you can find with their details."
        )
    else:
        prompt = (
            f"Find all startup investments made by {investor} at the {stage_label} stage. "
            f"List every portfolio company you can find with their details."
        )

    data = await call_perplexity(SCOUT_SYSTEM_PROMPT, prompt)
    if data is None:
        raise Exception(f"Perplexity API failed for investor {investor}")

    raw_content = data["choices"][0]["message"]["content"]
    startups_raw = extract_startups_from_response(raw_content)
    reply = clean_reply(raw_content)

    # Validate candidates
    valid_candidates = []
    for s in startups_raw:
        try:
            candidate = StartupCandidate(**s)
            valid_candidates.append(candidate.model_dump())
        except Exception:
            continue

    step.result = {
        "startups": valid_candidates,
        "scout_reply": reply[:2000],
    }

    # Generate add_to_triage step if we found startups
    if valid_candidates:
        next_order = await _get_next_sort_order(db, job.id)
        triage_step = BatchJobStep(
            job_id=job.id,
            step_type=BatchStepType.add_to_triage,
            params={
                "startup_candidates": valid_candidates,
                "source_investor": investor,
            },
            sort_order=next_order,
        )
        db.add(triage_step)

    logger.info(f"Found {len(valid_candidates)} startups from {investor} ({stage_label})")


async def _execute_add_to_triage(
    db: AsyncSession, step: BatchJobStep, job: BatchJob
) -> None:
    """Execute an add_to_triage step: add startup candidates to DB with dedup."""
    params = step.params
    candidates_data = params.get("startup_candidates", [])
    source_investor = params.get("source_investor", "")

    candidates = []
    for c in candidates_data:
        try:
            candidates.append(StartupCandidate(**c))
        except Exception:
            continue

    if not candidates:
        step.result = {"created": [], "skipped": []}
        return

    result = await add_startups_to_triage(db, candidates)

    step.result = result

    # Generate enrich steps for each created startup
    if result["created"]:
        next_order = await _get_next_sort_order(db, job.id)
        for startup_info in result["created"]:
            enrich_step = BatchJobStep(
                job_id=job.id,
                step_type=BatchStepType.enrich,
                params={
                    "startup_id": startup_info["id"],
                    "startup_name": startup_info["name"],
                    "source_investor": source_investor,
                },
                sort_order=next_order,
            )
            db.add(enrich_step)
            next_order += 1

    logger.info(
        f"Triage: added {len(result['created'])}, skipped {len(result['skipped'])} from {source_investor}"
    )


async def _execute_enrich(
    db: AsyncSession, step: BatchJobStep, job: BatchJob
) -> None:
    """Execute an enrich step: approve startup and run enrichment pipeline."""
    params = step.params
    startup_id = params["startup_id"]

    # Load startup and set to approved
    result = await db.execute(
        select(Startup).where(Startup.id == startup_id)
    )
    startup = result.scalar_one_or_none()

    if startup is None:
        step.result = {"error": "Startup not found"}
        raise Exception(f"Startup {startup_id} not found")

    if startup.enrichment_status and startup.enrichment_status.value == "complete":
        step.result = {"ai_score": startup.ai_score, "enrichment_status": "already_complete"}
        logger.info(f"Skipping enrichment for {startup.name} — already complete")
        return

    # Set to approved so enrichment can run
    startup.status = StartupStatus.approved
    await db.commit()

    # Run enrichment synchronously (it creates its own DB session)
    await run_enrichment_pipeline(startup_id)

    # Re-fetch to get updated data
    await db.refresh(startup)
    step.result = {
        "ai_score": startup.ai_score,
        "enrichment_status": startup.enrichment_status.value if startup.enrichment_status else "unknown",
    }

    logger.info(f"Enriched {startup.name} — AI score: {startup.ai_score}")


# Map step types to executor functions
STEP_EXECUTORS = {
    BatchStepType.discover_investors: _execute_discover_investors,
    BatchStepType.find_startups: _execute_find_startups,
    BatchStepType.add_to_triage: _execute_add_to_triage,
    BatchStepType.enrich: _execute_enrich,
}


async def run_batch_worker(job_id: str) -> None:
    """Main worker loop. Processes batch job steps sequentially with rate limiting.

    This runs as a background task, creating its own DB sessions.
    """
    consecutive_failures = 0

    while True:
        async with async_session() as db:
            # 1. Check job status
            job_result = await db.execute(
                select(BatchJob).where(BatchJob.id == job_id)
            )
            job = job_result.scalar_one_or_none()
            if job is None:
                logger.error(f"Batch job {job_id} not found, exiting worker")
                return

            if job.status in (BatchJobStatus.paused, BatchJobStatus.cancelled):
                logger.info(f"Batch job {job_id} is {job.status.value}, exiting worker")
                return

            # 2. Get next pending step
            step_result = await db.execute(
                select(BatchJobStep)
                .where(BatchJobStep.job_id == job.id)
                .where(BatchJobStep.status == BatchStepStatus.pending)
                .order_by(BatchJobStep.sort_order)
                .limit(1)
            )
            step = step_result.scalar_one_or_none()

            if step is None:
                # No more steps — job is complete
                job.status = BatchJobStatus.completed
                job.current_phase = BatchJobPhase.complete
                job.completed_at = datetime.now(timezone.utc)
                job.updated_at = datetime.now(timezone.utc)
                await _update_progress(db, job)
                await db.commit()
                logger.info(f"Batch job {job_id} completed")
                return

            # 3. Mark step as running
            step.status = BatchStepStatus.running
            await db.commit()

            # 4. Execute step
            step_type = step.step_type
            executor = STEP_EXECUTORS.get(step_type)
            if executor is None:
                step.status = BatchStepStatus.failed
                step.error = f"Unknown step type: {step_type}"
                step.completed_at = datetime.now(timezone.utc)
                await db.commit()
                continue

            try:
                await executor(db, step, job)
                step.status = BatchStepStatus.completed
                step.completed_at = datetime.now(timezone.utc)
                consecutive_failures = 0
            except Exception as e:
                logger.exception(f"Step {step.id} failed: {e}")
                step.status = BatchStepStatus.failed
                step.error = str(e)[:500]
                step.completed_at = datetime.now(timezone.utc)
                consecutive_failures += 1

            # 5. Update progress
            await _update_progress(db, job)
            await db.commit()

            # 6. Check consecutive failures
            if consecutive_failures >= 3:
                job.status = BatchJobStatus.paused
                job.error = "Paused after 3 consecutive failures — check API key/limits"
                job.updated_at = datetime.now(timezone.utc)
                await db.commit()
                logger.warning(f"Batch job {job_id} paused after 3 consecutive failures")
                return

        # 7. Rate limiting delay
        delay = STEP_DELAYS.get(step_type, 5)
        await asyncio.sleep(delay)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/batch_worker.py
git commit -m "feat: add batch worker service with step executors and rate limiting"
```

---

### Task 5: Batch API Endpoints

**Files:**
- Create: `backend/app/api/admin_batch.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the batch API endpoints**

```python
# backend/app/api/admin_batch.py
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.batch_job import (
    BatchJob,
    BatchJobPhase,
    BatchJobStatus,
    BatchJobStep,
    BatchJobType,
    BatchStepStatus,
    BatchStepType,
)
from app.models.startup import Startup
from app.models.user import User
from app.services.batch_locations import BATCH_LOCATIONS, BATCH_STAGES, format_location
from app.services.batch_worker import run_batch_worker

router = APIRouter()


class BatchStartRequest(BaseModel):
    job_type: str = "initial"
    refresh_days: int = 30


@router.post("/api/admin/batch/start")
async def start_batch(
    body: BatchStartRequest,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Check no job is already running
    existing = await db.execute(
        select(BatchJob).where(
            BatchJob.status.in_([BatchJobStatus.running, BatchJobStatus.pending])
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="A batch job is already running")

    # Create job
    job_type = BatchJobType.refresh if body.job_type == "refresh" else BatchJobType.initial
    job = BatchJob(
        job_type=job_type,
        status=BatchJobStatus.running,
        refresh_days=body.refresh_days if job_type == BatchJobType.refresh else None,
        current_phase=BatchJobPhase.discovering_investors,
    )
    db.add(job)
    await db.flush()

    # Generate initial discover_investors steps
    sort_order = 0
    for loc in BATCH_LOCATIONS:
        for stage in BATCH_STAGES:
            step = BatchJobStep(
                job_id=job.id,
                step_type=BatchStepType.discover_investors,
                params={
                    "city": loc["city"],
                    "state": loc["state"],
                    "country": loc["country"],
                    "stage": stage,
                },
                sort_order=sort_order,
            )
            db.add(step)
            sort_order += 1

    job.progress_summary = {
        "locations_total": sort_order,
        "locations_completed": 0,
        "investors_found": 0,
        "startups_found": 0,
        "startups_added": 0,
        "startups_skipped_duplicate": 0,
        "startups_enriched": 0,
        "startups_enrich_failed": 0,
    }

    await db.commit()

    # Launch worker
    background_tasks.add_task(run_batch_worker, str(job.id))

    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "total_steps": sort_order,
    }


@router.post("/api/admin/batch/{job_id}/pause")
async def pause_batch(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BatchJob).where(BatchJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != BatchJobStatus.running:
        raise HTTPException(status_code=400, detail=f"Cannot pause job in {job.status.value} state")

    job.status = BatchJobStatus.paused
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "paused"}


@router.post("/api/admin/batch/{job_id}/resume")
async def resume_batch(
    job_id: str,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BatchJob).where(BatchJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in (BatchJobStatus.paused, BatchJobStatus.cancelled):
        raise HTTPException(
            status_code=400, detail=f"Cannot resume job in {job.status.value} state"
        )

    # Reset any steps stuck in "running" state (from a crashed worker)
    stuck_steps = await db.execute(
        select(BatchJobStep)
        .where(BatchJobStep.job_id == job.id)
        .where(BatchJobStep.status == BatchStepStatus.running)
    )
    for step in stuck_steps.scalars().all():
        step.status = BatchStepStatus.pending

    job.status = BatchJobStatus.running
    job.error = None
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()

    background_tasks.add_task(run_batch_worker, str(job.id))
    return {"status": "running"}


@router.post("/api/admin/batch/{job_id}/cancel")
async def cancel_batch(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(BatchJob).where(BatchJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = BatchJobStatus.cancelled
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "cancelled"}


@router.get("/api/admin/batch/active")
async def get_active_batch(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BatchJob).order_by(BatchJob.created_at.desc()).limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None

    elapsed = (datetime.now(timezone.utc) - job.created_at).total_seconds()

    return {
        "id": str(job.id),
        "job_type": job.job_type.value,
        "status": job.status.value,
        "current_phase": job.current_phase.value,
        "progress_summary": job.progress_summary,
        "error": job.error,
        "refresh_days": job.refresh_days,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "elapsed_seconds": int(elapsed),
    }


@router.get("/api/admin/batch/{job_id}/steps")
async def get_batch_steps(
    job_id: str,
    step_type: str | None = None,
    status: str | None = None,
    page: int = 1,
    per_page: int = 50,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    query = select(BatchJobStep).where(BatchJobStep.job_id == job_id)

    if step_type:
        query = query.where(BatchJobStep.step_type == step_type)
    if status:
        query = query.where(BatchJobStep.status == status)

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate
    offset = (page - 1) * per_page
    result = await db.execute(
        query.order_by(BatchJobStep.sort_order).offset(offset).limit(per_page)
    )
    steps = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": [
            {
                "id": str(s.id),
                "step_type": s.step_type.value,
                "status": s.status.value,
                "params": s.params,
                "result": s.result,
                "error": s.error,
                "sort_order": s.sort_order,
                "created_at": s.created_at.isoformat(),
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for s in steps
        ],
    }


@router.get("/api/admin/batch/{job_id}/investors")
async def get_batch_investors(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Get all find_startups steps for this job
    result = await db.execute(
        select(BatchJobStep)
        .where(BatchJobStep.job_id == job_id)
        .where(BatchJobStep.step_type == BatchStepType.find_startups)
        .order_by(BatchJobStep.sort_order)
    )
    steps = result.scalars().all()

    items = []
    for s in steps:
        p = s.params
        startups_found = 0
        if s.result and "startups" in s.result:
            startups_found = len(s.result["startups"])
        items.append(
            {
                "name": p.get("investor", ""),
                "city": p.get("city", ""),
                "state": p.get("state"),
                "country": p.get("country", ""),
                "stage": p.get("stage", ""),
                "startups_found": startups_found,
                "status": s.status.value,
            }
        )

    return {"total": len(items), "items": items}


@router.get("/api/admin/batch/{job_id}/startups")
async def get_batch_startups(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Get all add_to_triage and enrich steps
    triage_result = await db.execute(
        select(BatchJobStep)
        .where(BatchJobStep.job_id == job_id)
        .where(BatchJobStep.step_type == BatchStepType.add_to_triage)
        .where(BatchJobStep.status == BatchStepStatus.completed)
    )
    triage_steps = triage_result.scalars().all()

    # Collect all created startup IDs
    startup_ids = []
    startup_sources = {}
    for ts in triage_steps:
        source = ts.params.get("source_investor", "")
        for created in (ts.result or {}).get("created", []):
            sid = created["id"]
            startup_ids.append(sid)
            startup_sources[sid] = source

    if not startup_ids:
        return {"total": 0, "items": []}

    # Fetch actual startup records
    startups_result = await db.execute(
        select(Startup).where(Startup.id.in_(startup_ids))
    )
    startups = {str(s.id): s for s in startups_result.scalars().all()}

    # Get enrich step status for each startup
    enrich_result = await db.execute(
        select(BatchJobStep)
        .where(BatchJobStep.job_id == job_id)
        .where(BatchJobStep.step_type == BatchStepType.enrich)
    )
    enrich_status = {}
    for es in enrich_result.scalars().all():
        sid = es.params.get("startup_id")
        if sid:
            enrich_status[sid] = {
                "status": es.status.value,
                "error": es.error,
                "ai_score": (es.result or {}).get("ai_score"),
            }

    items = []
    for sid in startup_ids:
        s = startups.get(sid)
        if s is None:
            continue
        es = enrich_status.get(sid, {})
        items.append(
            {
                "id": sid,
                "name": s.name,
                "source_investor": startup_sources.get(sid, ""),
                "stage": s.stage.value,
                "location_city": s.location_city,
                "location_state": s.location_state,
                "triage_status": s.status.value,
                "enrichment_status": s.enrichment_status.value if s.enrichment_status else "none",
                "ai_score": s.ai_score,
                "enrich_error": es.get("error"),
            }
        )

    return {"total": len(items), "items": items}


@router.get("/api/admin/batch/{job_id}/log")
async def get_batch_log(
    job_id: str,
    page: int = 1,
    per_page: int = 100,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Get completed/failed steps, most recent first
    result = await db.execute(
        select(BatchJobStep)
        .where(BatchJobStep.job_id == job_id)
        .where(
            BatchJobStep.status.in_(
                [BatchStepStatus.completed, BatchStepStatus.failed, BatchStepStatus.running]
            )
        )
        .order_by(BatchJobStep.completed_at.desc().nulls_last())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    steps = result.scalars().all()

    items = []
    for s in steps:
        p = s.params or {}
        # Build human-readable message
        if s.step_type == BatchStepType.discover_investors:
            loc = f"{p.get('city', '')}, {p.get('state') or p.get('country', '')}"
            stage = p.get("stage", "")
            if s.status == BatchStepStatus.completed:
                count = len((s.result or {}).get("investors", []))
                msg = f"Found {count} {stage} investors in {loc}"
            elif s.status == BatchStepStatus.running:
                msg = f"Searching for {stage} investors in {loc}..."
            else:
                msg = f"Failed to find investors in {loc}: {s.error or 'unknown error'}"
        elif s.step_type == BatchStepType.find_startups:
            inv = p.get("investor", "")
            stage = p.get("stage", "")
            if s.status == BatchStepStatus.completed:
                count = len((s.result or {}).get("startups", []))
                msg = f"Found {count} startups from {inv} ({stage})"
            elif s.status == BatchStepStatus.running:
                msg = f"Finding startups from {inv} ({stage})..."
            else:
                msg = f"Failed to find startups from {inv}: {s.error or 'unknown error'}"
        elif s.step_type == BatchStepType.add_to_triage:
            inv = p.get("source_investor", "")
            if s.status == BatchStepStatus.completed:
                created = len((s.result or {}).get("created", []))
                skipped = len((s.result or {}).get("skipped", []))
                msg = f"Added {created} startups to triage from {inv}"
                if skipped:
                    msg += f" ({skipped} duplicates skipped)"
            else:
                msg = f"Failed to add startups from {inv}: {s.error or 'unknown error'}"
        elif s.step_type == BatchStepType.enrich:
            name = p.get("startup_name", "")
            if s.status == BatchStepStatus.completed:
                score = (s.result or {}).get("ai_score")
                msg = f"Enriched {name}"
                if score is not None:
                    msg += f" — AI score: {score:.0f}"
            elif s.status == BatchStepStatus.running:
                msg = f"Enriching {name}..."
            else:
                msg = f"Failed to enrich {name}: {s.error or 'unknown error'}"
        else:
            msg = f"Step {s.step_type.value}: {s.status.value}"

        items.append(
            {
                "timestamp": (s.completed_at or s.created_at).isoformat(),
                "message": msg,
                "step_type": s.step_type.value,
                "status": s.status.value,
            }
        )

    return {"items": items}
```

- [ ] **Step 2: Register router in main.py**

Add to `backend/app/main.py`:

```python
from app.api.admin_batch import router as admin_batch_router
```

And in the router registration section:

```python
app.include_router(admin_batch_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin_batch.py backend/app/main.py
git commit -m "feat: add batch pipeline API endpoints"
```

---

### Task 6: Admin API Client Updates

**Files:**
- Modify: `admin/lib/api.ts`

- [ ] **Step 1: Add batch API methods**

Add these methods to the `adminApi` object in `admin/lib/api.ts`:

```typescript
  // Batch pipeline
  async startBatch(token: string, jobType: string, refreshDays?: number) {
    return apiFetch<{ job_id: string; status: string; total_steps: number }>(
      "/api/admin/batch/start",
      token,
      { method: "POST", body: JSON.stringify({ job_type: jobType, refresh_days: refreshDays || 30 }) }
    );
  },
  async pauseBatch(token: string, jobId: string) {
    return apiFetch<{ status: string }>(`/api/admin/batch/${jobId}/pause`, token, { method: "POST" });
  },
  async resumeBatch(token: string, jobId: string) {
    return apiFetch<{ status: string }>(`/api/admin/batch/${jobId}/resume`, token, { method: "POST" });
  },
  async cancelBatch(token: string, jobId: string) {
    return apiFetch<{ status: string }>(`/api/admin/batch/${jobId}/cancel`, token, { method: "POST" });
  },
  async getActiveBatch(token: string) {
    return apiFetch<any>("/api/admin/batch/active", token);
  },
  async getBatchSteps(token: string, jobId: string, params?: string) {
    const qs = params ? `?${params}` : "";
    return apiFetch<any>(`/api/admin/batch/${jobId}/steps${qs}`, token);
  },
  async getBatchInvestors(token: string, jobId: string) {
    return apiFetch<any>(`/api/admin/batch/${jobId}/investors`, token);
  },
  async getBatchStartups(token: string, jobId: string) {
    return apiFetch<any>(`/api/admin/batch/${jobId}/startups`, token);
  },
  async getBatchLog(token: string, jobId: string, page?: number) {
    const qs = page ? `?page=${page}` : "";
    return apiFetch<any>(`/api/admin/batch/${jobId}/log${qs}`, token);
  },
```

- [ ] **Step 2: Commit**

```bash
git add admin/lib/api.ts
git commit -m "feat: add batch pipeline API methods to admin client"
```

---

### Task 7: Admin Batch Page

**Files:**
- Create: `admin/app/batch/page.tsx`
- Modify: `admin/components/Sidebar.tsx`

- [ ] **Step 1: Create the batch admin page**

```tsx
// admin/app/batch/page.tsx
"use client";

import { useSession } from "next-auth/react";
import { useCallback, useEffect, useState } from "react";
import { adminApi } from "@/lib/api";

type Tab = "locations" | "investors" | "startups";

const STAGE_LABELS: Record<string, string> = {
  pre_seed: "Pre-Seed",
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  series_c: "Series C",
  growth: "Growth",
};

const STATUS_COLORS: Record<string, string> = {
  running: "bg-yellow-100 text-yellow-800",
  paused: "bg-orange-100 text-orange-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  cancelled: "bg-gray-100 text-gray-600",
  pending: "bg-gray-100 text-gray-600",
};

const PIPELINE_COLORS: Record<string, string> = {
  pending: "bg-gray-100 text-gray-600",
  none: "bg-gray-100 text-gray-600",
  running: "bg-yellow-100 text-yellow-800",
  complete: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

function Badge({ status }: { status: string }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[status] || "bg-gray-100 text-gray-600"}`}>
      {status}
    </span>
  );
}

function formatElapsed(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

export default function BatchPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;

  const [job, setJob] = useState<any>(null);
  const [tab, setTab] = useState<Tab>("locations");
  const [locations, setLocations] = useState<any[]>([]);
  const [investors, setInvestors] = useState<any[]>([]);
  const [startups, setStartups] = useState<any[]>([]);
  const [log, setLog] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshDays, setRefreshDays] = useState(30);
  const [elapsed, setElapsed] = useState(0);

  const fetchData = useCallback(async () => {
    if (!token) return;
    try {
      const activeJob = await adminApi.getActiveBatch(token);
      setJob(activeJob);
      if (activeJob?.id) {
        setElapsed(activeJob.elapsed_seconds || 0);

        // Fetch tab data
        if (tab === "locations") {
          const steps = await adminApi.getBatchSteps(token, activeJob.id, "step_type=discover_investors&per_page=500");
          setLocations(steps.items || []);
        } else if (tab === "investors") {
          const inv = await adminApi.getBatchInvestors(token, activeJob.id);
          setInvestors(inv.items || []);
        } else if (tab === "startups") {
          const st = await adminApi.getBatchStartups(token, activeJob.id);
          setStartups(st.items || []);
        }

        // Always fetch log
        const logData = await adminApi.getBatchLog(token, activeJob.id);
        setLog(logData.items || []);
      }
    } catch {
      // silent
    }
  }, [token, tab]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Polling
  useEffect(() => {
    const interval = job?.status === "running" ? 5000 : 30000;
    const timer = setInterval(fetchData, interval);
    return () => clearInterval(timer);
  }, [fetchData, job?.status]);

  // Elapsed time counter
  useEffect(() => {
    if (job?.status !== "running") return;
    const timer = setInterval(() => setElapsed((e) => e + 1), 1000);
    return () => clearInterval(timer);
  }, [job?.status]);

  async function handleStart(jobType: string) {
    if (!token) return;
    setLoading(true);
    try {
      await adminApi.startBatch(token, jobType, jobType === "refresh" ? refreshDays : undefined);
      await fetchData();
    } catch (e: any) {
      alert(e.message || "Failed to start batch");
    }
    setLoading(false);
  }

  async function handlePause() {
    if (!token || !job) return;
    await adminApi.pauseBatch(token, job.id);
    await fetchData();
  }

  async function handleResume() {
    if (!token || !job) return;
    await adminApi.resumeBatch(token, job.id);
    await fetchData();
  }

  async function handleCancel() {
    if (!token || !job) return;
    if (!confirm("Cancel this batch job?")) return;
    await adminApi.cancelBatch(token, job.id);
    await fetchData();
  }

  const summary = job?.progress_summary || {};
  const isActive = job?.status === "running" || job?.status === "paused";
  const canStart = !isActive && job?.status !== "pending";

  return (
    <div className="ml-56 p-8">
      <h1 className="font-serif text-2xl text-text-primary mb-6">Batch Pipeline</h1>

      {/* Control Bar */}
      <div className="rounded border border-border bg-surface p-5 mb-6">
        <div className="flex items-center gap-3 mb-4">
          {canStart && (
            <>
              <button
                onClick={() => handleStart("initial")}
                disabled={loading}
                className="px-4 py-2 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover disabled:opacity-50 transition"
              >
                Start Initial Batch
              </button>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleStart("refresh")}
                  disabled={loading}
                  className="px-4 py-2 text-sm font-medium rounded border border-accent text-accent hover:bg-accent/5 disabled:opacity-50 transition"
                >
                  Start Refresh
                </button>
                <input
                  type="number"
                  value={refreshDays}
                  onChange={(e) => setRefreshDays(parseInt(e.target.value) || 30)}
                  className="w-16 px-2 py-2 text-sm rounded border border-border bg-surface text-text-primary"
                  min={1}
                  max={90}
                />
                <span className="text-xs text-text-tertiary">days</span>
              </div>
            </>
          )}
          {job?.status === "running" && (
            <button onClick={handlePause} className="px-4 py-2 text-sm font-medium rounded border border-border text-text-secondary hover:text-text-primary transition">
              Pause
            </button>
          )}
          {(job?.status === "paused" || job?.status === "cancelled") && (
            <button onClick={handleResume} className="px-4 py-2 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover transition">
              Resume
            </button>
          )}
          {isActive && (
            <button onClick={handleCancel} className="px-4 py-2 text-sm font-medium rounded border border-red-300 text-red-600 hover:bg-red-50 transition">
              Cancel
            </button>
          )}
          {job && <Badge status={job.status} />}
          {job?.error && <span className="text-xs text-red-600 ml-2">{job.error}</span>}
          {isActive && (
            <span className="text-xs text-text-tertiary ml-auto tabular-nums">{formatElapsed(elapsed)}</span>
          )}
        </div>

        {/* Summary stats */}
        {job && (
          <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
            <div>
              <p className="text-xs text-text-tertiary">Locations</p>
              <p className="text-sm font-medium text-text-primary tabular-nums">
                {summary.locations_completed || 0} / {summary.locations_total || 0}
              </p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">Investors</p>
              <p className="text-sm font-medium text-text-primary tabular-nums">{summary.investors_found || 0}</p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">Startups Found</p>
              <p className="text-sm font-medium text-text-primary tabular-nums">{summary.startups_found || 0}</p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">Added</p>
              <p className="text-sm font-medium text-text-primary tabular-nums">{summary.startups_added || 0}</p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">Enriched</p>
              <p className="text-sm font-medium text-score-high tabular-nums">{summary.startups_enriched || 0}</p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">Duplicates</p>
              <p className="text-sm font-medium text-text-tertiary tabular-nums">{summary.startups_skipped_duplicate || 0}</p>
            </div>
          </div>
        )}

        {job && summary.current_location && (
          <p className="text-xs text-text-tertiary mt-3">
            Currently: {summary.current_location}
            {summary.current_stage && ` / ${STAGE_LABELS[summary.current_stage] || summary.current_stage}`}
            {summary.current_investor && ` / ${summary.current_investor}`}
            {summary.current_startup && ` / ${summary.current_startup}`}
          </p>
        )}
      </div>

      {job && (
        <>
          {/* Tabs */}
          <div className="flex items-center gap-1 mb-4 border-b border-border">
            {(["locations", "investors", "startups"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition -mb-px ${
                  tab === t
                    ? "border-accent text-accent"
                    : "border-transparent text-text-tertiary hover:text-text-secondary"
                }`}
              >
                {t === "locations" ? "Locations" : t === "investors" ? "Investors" : "Startups"}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="rounded border border-border bg-surface overflow-x-auto mb-6">
            {tab === "locations" && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-background">
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Location</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Stage</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Status</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary">Investors</th>
                  </tr>
                </thead>
                <tbody>
                  {locations.map((s, i) => {
                    const loc = `${s.params?.city || ""}, ${s.params?.state || s.params?.country || ""}`;
                    const investorCount = (s.result?.investors || []).length;
                    return (
                      <tr
                        key={i}
                        className={`border-b border-border last:border-b-0 ${
                          s.status === "running" ? "bg-accent/5" : "hover:bg-hover-row"
                        }`}
                      >
                        <td className="px-4 py-2 text-text-primary">{loc}</td>
                        <td className="px-4 py-2 text-text-secondary">{STAGE_LABELS[s.params?.stage] || s.params?.stage}</td>
                        <td className="px-4 py-2"><Badge status={s.status} /></td>
                        <td className="px-4 py-2 text-right text-text-secondary tabular-nums">
                          {s.status === "completed" ? investorCount : "—"}
                        </td>
                      </tr>
                    );
                  })}
                  {locations.length === 0 && (
                    <tr><td colSpan={4} className="px-4 py-8 text-center text-text-tertiary text-sm">No location steps yet</td></tr>
                  )}
                </tbody>
              </table>
            )}

            {tab === "investors" && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-background">
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Investor</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Location</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Stage</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary">Startups</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {investors.map((inv, i) => (
                    <tr key={i} className={`border-b border-border last:border-b-0 ${inv.status === "running" ? "bg-accent/5" : "hover:bg-hover-row"}`}>
                      <td className="px-4 py-2 text-text-primary font-medium">{inv.name}</td>
                      <td className="px-4 py-2 text-text-secondary">{inv.city}, {inv.state || inv.country}</td>
                      <td className="px-4 py-2 text-text-secondary">{STAGE_LABELS[inv.stage] || inv.stage}</td>
                      <td className="px-4 py-2 text-right text-text-secondary tabular-nums">{inv.startups_found}</td>
                      <td className="px-4 py-2"><Badge status={inv.status} /></td>
                    </tr>
                  ))}
                  {investors.length === 0 && (
                    <tr><td colSpan={5} className="px-4 py-8 text-center text-text-tertiary text-sm">No investors discovered yet</td></tr>
                  )}
                </tbody>
              </table>
            )}

            {tab === "startups" && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-background">
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Startup</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Source Investor</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Stage</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Pipeline</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary">AI Score</th>
                  </tr>
                </thead>
                <tbody>
                  {startups.map((s, i) => (
                    <tr key={i} className="border-b border-border last:border-b-0 hover:bg-hover-row">
                      <td className="px-4 py-2 text-text-primary font-medium">{s.name}</td>
                      <td className="px-4 py-2 text-text-secondary">{s.source_investor}</td>
                      <td className="px-4 py-2 text-text-secondary">{STAGE_LABELS[s.stage] || s.stage}</td>
                      <td className="px-4 py-2">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${PIPELINE_COLORS[s.enrichment_status] || "bg-gray-100 text-gray-600"}`}>
                          {s.enrichment_status === "complete" ? "Enriched" : s.enrichment_status === "running" ? "Enriching" : s.enrichment_status === "failed" ? "Failed" : "Triage"}
                        </span>
                        {s.enrich_error && (
                          <span className="text-xs text-red-500 ml-1" title={s.enrich_error}>(!)</span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right tabular-nums">
                        {s.ai_score != null ? (
                          <span className={s.ai_score >= 70 ? "text-score-high" : s.ai_score >= 40 ? "text-score-mid" : "text-score-low"}>
                            {s.ai_score.toFixed(0)}
                          </span>
                        ) : "—"}
                      </td>
                    </tr>
                  ))}
                  {startups.length === 0 && (
                    <tr><td colSpan={5} className="px-4 py-8 text-center text-text-tertiary text-sm">No startups added yet</td></tr>
                  )}
                </tbody>
              </table>
            )}
          </div>

          {/* Live Log */}
          <div className="rounded border border-border bg-surface">
            <div className="px-4 py-2.5 border-b border-border bg-background">
              <h3 className="text-xs font-medium text-text-tertiary">Activity Log</h3>
            </div>
            <div className="max-h-80 overflow-y-auto">
              {log.map((entry, i) => (
                <div key={i} className="px-4 py-2 border-b border-border last:border-b-0 flex items-start gap-3">
                  <span className="text-xs text-text-tertiary tabular-nums whitespace-nowrap mt-0.5">
                    {new Date(entry.timestamp).toLocaleTimeString()}
                  </span>
                  <span className={`text-sm ${entry.status === "failed" ? "text-red-600" : "text-text-primary"}`}>
                    {entry.message}
                  </span>
                </div>
              ))}
              {log.length === 0 && (
                <div className="px-4 py-8 text-center text-text-tertiary text-sm">No activity yet</div>
              )}
            </div>
          </div>
        </>
      )}

      {!job && (
        <div className="text-center py-20 text-text-tertiary text-sm">
          No batch jobs yet. Start an initial batch to begin discovering investors and startups.
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add Batch to admin sidebar**

In `admin/components/Sidebar.tsx`, update the NAV_ITEMS array:

```typescript
const NAV_ITEMS = [
  { href: "/", label: "Triage" },
  { href: "/scout", label: "Scout" },
  { href: "/batch", label: "Batch" },
  { href: "/startups", label: "Startups" },
  { href: "/experts", label: "Experts" },
  { href: "/templates", label: "Templates" },
  { href: "/users", label: "Users" },
];
```

- [ ] **Step 3: Commit**

```bash
git add admin/app/batch/page.tsx admin/components/Sidebar.tsx
git commit -m "feat: add batch pipeline admin page with progress tracking"
```

---

### Task 8: Database Migration & Deployment

- [ ] **Step 1: Sync files to EC2**

```bash
rsync -azP --exclude='node_modules' --exclude='.next' --exclude='__pycache__' --exclude='.git' --exclude='venv' -e "ssh -i ~/.ssh/acutal-deploy.pem" ./ ec2-user@98.89.232.52:~/acutal/
```

- [ ] **Step 2: Run the migration SQL**

Connect to the database and run the SQL from Task 1 Step 3:

```bash
ssh -i ~/.ssh/acutal-deploy.pem ec2-user@98.89.232.52 "cd ~/acutal && docker compose -f docker-compose.prod.yml exec db psql -U acutal -d acutal" <<'SQL'
CREATE TYPE batchjobtype AS ENUM ('initial', 'refresh');
CREATE TYPE batchjobstatus AS ENUM ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled');
CREATE TYPE batchjobphase AS ENUM ('discovering_investors', 'finding_startups', 'enriching', 'complete');
CREATE TYPE batchsteptype AS ENUM ('discover_investors', 'find_startups', 'add_to_triage', 'enrich');
CREATE TYPE batchstepstatus AS ENUM ('pending', 'running', 'completed', 'failed', 'skipped');

CREATE TABLE batch_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type batchjobtype NOT NULL DEFAULT 'initial',
    status batchjobstatus NOT NULL DEFAULT 'pending',
    refresh_days INTEGER,
    progress_summary JSONB NOT NULL DEFAULT '{}',
    current_phase batchjobphase NOT NULL DEFAULT 'discovering_investors',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE batch_job_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES batch_jobs(id) ON DELETE CASCADE,
    step_type batchsteptype NOT NULL,
    status batchstepstatus NOT NULL DEFAULT 'pending',
    params JSONB NOT NULL DEFAULT '{}',
    result JSONB,
    error TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX ix_batch_job_steps_job_id ON batch_job_steps(job_id);
CREATE INDEX ix_batch_job_steps_status ON batch_job_steps(status);
CREATE INDEX ix_batch_job_steps_sort_order ON batch_job_steps(sort_order);
SQL
```

- [ ] **Step 3: Rebuild and restart containers**

```bash
ssh -i ~/.ssh/acutal-deploy.pem ec2-user@98.89.232.52 "cd ~/acutal && docker compose -f docker-compose.prod.yml up -d --build backend admin"
```

- [ ] **Step 4: Verify deployment**

Check backend starts without errors:

```bash
ssh -i ~/.ssh/acutal-deploy.pem ec2-user@98.89.232.52 "cd ~/acutal && docker compose -f docker-compose.prod.yml logs --tail=20 backend"
```

Check admin builds successfully:

```bash
ssh -i ~/.ssh/acutal-deploy.pem ec2-user@98.89.232.52 "cd ~/acutal && docker compose -f docker-compose.prod.yml logs --tail=20 admin"
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: scout batch pipeline — complete implementation with models, worker, API, and admin UI"
```
