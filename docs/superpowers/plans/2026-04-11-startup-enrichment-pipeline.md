# Startup Enrichment Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a startup is approved (or manually triggered), enrich it via Perplexity Sonar Pro with founders, funding, company intel, and media, then generate an AI investment memo with per-dimension scoring — all displayed on both admin and public detail pages.

**Architecture:** Two-stage background pipeline (Perplexity enrichment call → Perplexity scoring call), triggered on triage approval or via manual button. Deduplication at Scout chat, Scout add, and manual create layers. New models for founders, funding rounds, and AI reviews. Admin and public frontends updated to display enriched data.

**Tech Stack:** FastAPI (Python 3.11+), SQLAlchemy async, Alembic, Perplexity Sonar Pro API, Next.js 16, React, Tailwind CSS v4, TypeScript.

---

## File Structure

### Backend — New Files
- `backend/app/models/founder.py` — StartupFounder model
- `backend/app/models/funding_round.py` — StartupFundingRound model
- `backend/app/models/ai_review.py` — StartupAIReview model
- `backend/app/services/enrichment.py` — Enrichment pipeline logic (Perplexity calls, parsing, DB writes)
- `backend/app/services/dedup.py` — normalize_name, normalize_domain, check_duplicate helpers
- `backend/app/api/admin_enrichment.py` — Enrich/status/review endpoints
- `backend/alembic/versions/d4e5f6a7b8c9_enrichment_pipeline.py` — Migration

### Backend — Modified Files
- `backend/app/models/startup.py` — Add enrichment fields + EnrichmentStatus enum
- `backend/app/models/__init__.py` — Register new models
- `backend/app/main.py` — Register enrichment router
- `backend/app/api/admin.py` — Trigger enrichment on approval, include enrichment_status in pipeline
- `backend/app/api/admin_scout.py` — Dedup in scout chat + add
- `backend/app/api/startups.py` — Include enriched data in public detail response

### Admin Frontend — Modified Files
- `admin/lib/types.ts` — Add enrichment types
- `admin/lib/api.ts` — Add enrichment API methods
- `admin/app/startups/[id]/page.tsx` — Enrichment UI, AI review display, founders, funding, company intel
- `admin/app/scout/page.tsx` — Dedup badges on results

### Public Frontend — Modified Files
- `frontend/lib/types.ts` — Extend StartupDetail with enriched fields
- `frontend/app/startups/[slug]/page.tsx` — AI analysis, founders, funding, company intel sections

---

### Task 1: Backend Data Models

Add new models and fields for the enrichment pipeline.

**Files:**
- Modify: `backend/app/models/startup.py`
- Create: `backend/app/models/founder.py`
- Create: `backend/app/models/funding_round.py`
- Create: `backend/app/models/ai_review.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Add EnrichmentStatus enum and new fields to Startup model**

In `backend/app/models/startup.py`, add the `EnrichmentStatus` enum after `StartupStatus` and add new columns to the `Startup` class:

```python
class EnrichmentStatus(str, enum.Enum):
    none = "none"
    running = "running"
    complete = "complete"
    failed = "failed"
```

Add these fields to the `Startup` class (after `updated_at`, before `industries`):

```python
    tagline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    total_funding: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employee_count: Mapped[str | None] = mapped_column(String(50), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    twitter_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    crunchbase_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    competitors: Mapped[str | None] = mapped_column(Text, nullable=True)
    tech_stack: Mapped[str | None] = mapped_column(Text, nullable=True)
    hiring_signals: Mapped[str | None] = mapped_column(Text, nullable=True)
    patents: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_metrics: Mapped[str | None] = mapped_column(Text, nullable=True)
    enrichment_status: Mapped[EnrichmentStatus] = mapped_column(
        Enum(EnrichmentStatus), nullable=False, default=EnrichmentStatus.none, server_default="none"
    )
    enrichment_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 2: Create StartupFounder model**

Create `backend/app/models/founder.py`:

```python
import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
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
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

- [ ] **Step 3: Create StartupFundingRound model**

Create `backend/app/models/funding_round.py`:

```python
import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base


class StartupFundingRound(Base):
    __tablename__ = "startup_funding_rounds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("startups.id", ondelete="CASCADE"), nullable=False
    )
    round_name: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[str | None] = mapped_column(String(50), nullable=True)
    date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lead_investor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

- [ ] **Step 4: Create StartupAIReview model**

Create `backend/app/models/ai_review.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base


class StartupAIReview(Base):
    __tablename__ = "startup_ai_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    startup_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("startups.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    investment_thesis: Mapped[str] = mapped_column(Text, nullable=False)
    key_risks: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    dimension_scores: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 5: Register new models in `__init__.py`**

Add to `backend/app/models/__init__.py`:

```python
from app.models.founder import StartupFounder
from app.models.funding_round import StartupFundingRound
from app.models.ai_review import StartupAIReview
```

And add `"StartupFounder"`, `"StartupFundingRound"`, `"StartupAIReview"` to the `__all__` list.

- [ ] **Step 6: Create Alembic migration**

Run: `cd /Users/leemosbacker/acutal/backend && alembic revision --autogenerate -m "enrichment pipeline"`

Then review the generated migration file. It should contain:
- New columns on `startups` table (tagline, total_funding, employee_count, linkedin_url, twitter_url, crunchbase_url, competitors, tech_stack, hiring_signals, patents, key_metrics, enrichment_status, enrichment_error, enriched_at)
- New `enrichmentstatus` enum type
- New `startup_founders` table
- New `startup_funding_rounds` table
- New `startup_ai_reviews` table

If autogenerate doesn't create the enum properly, manually add:

```python
# In upgrade():
enrichment_enum = sa.Enum('none', 'running', 'complete', 'failed', name='enrichmentstatus')
enrichment_enum.create(op.get_bind(), checkfirst=True)
```

- [ ] **Step 7: Run the migration locally**

Run: `cd /Users/leemosbacker/acutal/backend && alembic upgrade head`

Expected: Migration applies without errors.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/startup.py backend/app/models/founder.py backend/app/models/funding_round.py backend/app/models/ai_review.py backend/app/models/__init__.py backend/alembic/versions/
git commit -m "feat: add enrichment data models (founders, funding rounds, AI reviews, startup enrichment fields)"
```

---

### Task 2: Deduplication Service

Shared normalization and dedup-checking logic used by Scout and the create form.

**Files:**
- Create: `backend/app/services/dedup.py`

- [ ] **Step 1: Create the dedup service**

Create `backend/app/services/dedup.py`:

```python
import re
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.startup import Startup


_STRIP_SUFFIXES = re.compile(
    r"\b(inc\.?|ltd\.?|llc|co\.?|corp\.?|corporation|gmbh|pty|limited)\b",
    re.IGNORECASE,
)


def normalize_name(name: str) -> str:
    """Normalize a startup name for dedup comparison."""
    result = name.lower().strip()
    result = _STRIP_SUFFIXES.sub("", result)
    result = re.sub(r"[^\w\s]", "", result)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def normalize_domain(url: str) -> str:
    """Extract and normalize domain from a URL for dedup comparison."""
    if not url:
        return ""
    if "://" not in url:
        url = f"https://{url}"
    try:
        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower()
        domain = re.sub(r"^www\.", "", domain)
        return domain
    except Exception:
        return ""


async def find_duplicate(
    db: AsyncSession,
    name: str,
    website_url: str | None = None,
    exclude_id: str | None = None,
) -> dict | None:
    """Check if a startup with the same normalized name or domain exists.

    Returns a dict with id, name, status if found, None otherwise.
    """
    norm_name = normalize_name(name)
    norm_domain = normalize_domain(website_url) if website_url else ""

    # Query all startups and check in Python (simple for current scale)
    result = await db.execute(select(Startup))
    startups = result.scalars().all()

    for s in startups:
        if exclude_id and str(s.id) == exclude_id:
            continue

        if normalize_name(s.name) == norm_name:
            return {"id": str(s.id), "name": s.name, "status": s.status.value}

        if norm_domain and s.website_url and normalize_domain(s.website_url) == norm_domain:
            return {"id": str(s.id), "name": s.name, "status": s.status.value}

    return None
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/dedup.py
git commit -m "feat: add dedup service with name/domain normalization"
```

---

### Task 3: Enrichment Pipeline Service

Core enrichment logic — two Perplexity API calls, parsing, and DB writes.

**Files:**
- Create: `backend/app/services/enrichment.py`

- [ ] **Step 1: Create the enrichment service**

Create `backend/app/services/enrichment.py`:

```python
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import async_session
from app.models.ai_review import StartupAIReview
from app.models.dimension import StartupDimension
from app.models.founder import StartupFounder
from app.models.funding_round import StartupFundingRound
from app.models.media import MediaType, StartupMedia
from app.models.score import ScoreType, StartupScoreHistory
from app.models.startup import EnrichmentStatus, Startup
from app.models.template import DueDiligenceTemplate, TemplateDimension

logger = logging.getLogger(__name__)

ENRICHMENT_SYSTEM_PROMPT = """You are a startup research analyst. Given a startup, research it thoroughly and return structured data.

You MUST return a JSON block wrapped in ```json fences with this exact structure:

```json
{
  "tagline": "One sentence describing what the company does",
  "description": "2-3 sentence improved description of the company, product, and market",
  "founded_date": "2023-01-01",
  "founders": [
    {"name": "Full Name", "title": "CEO & Co-founder", "linkedin_url": "https://linkedin.com/in/..."}
  ],
  "funding_rounds": [
    {"round_name": "Seed", "amount": "$5M", "date": "2023-06", "lead_investor": "Y Combinator"}
  ],
  "total_funding": "$12M",
  "employee_count": "50-100",
  "linkedin_url": "https://linkedin.com/company/...",
  "twitter_url": "https://twitter.com/...",
  "crunchbase_url": "https://crunchbase.com/organization/...",
  "competitors": "Description of competitive landscape and key competitors",
  "tech_stack": "Known technologies, infrastructure, and technical approach",
  "key_metrics": "Any publicly known metrics: ARR, users, growth rates, market share",
  "hiring_signals": "Recent hiring activity, open positions, team growth, Glassdoor info",
  "patents": "Any known patent filings or IP",
  "media": [
    {"title": "Article Title", "url": "https://...", "source": "TechCrunch", "media_type": "article", "published_at": "2024-01-15"}
  ]
}
```

Rules:
- Be thorough. Search LinkedIn, Crunchbase, news sites, the company website, and social media.
- If you can't find information for a field, set it to null or an empty array — never guess.
- For media_type, use one of: article, linkedin_post, video, podcast.
- For founded_date, use ISO format (YYYY-MM-DD) or just a year (YYYY).
- Return ONLY real, verified information from your search."""


SCORING_SYSTEM_PROMPT = """You are a senior VC analyst at a top-tier venture fund. Your job is to evaluate startups for investment potential.

Given startup research data and a set of evaluation dimensions, produce a structured investment analysis.

For EACH dimension:
- Assign a score from 0-100 (where 70+ is strong, 40-69 is moderate, below 40 is weak)
- Write 2-3 sentences of specific, evidence-based reasoning citing the research data

Then write:
- **Investment Thesis**: 2-3 sentences making the bull case for this startup
- **Key Risks**: 2-3 specific risks backed by evidence
- **Verdict**: 1-2 sentence overall recommendation

You MUST return a JSON block wrapped in ```json fences:

```json
{
  "overall_score": 72,
  "investment_thesis": "...",
  "key_risks": "...",
  "verdict": "...",
  "dimension_scores": [
    {"dimension_name": "Market Opportunity", "score": 80, "reasoning": "..."},
    {"dimension_name": "Team Strength", "score": 75, "reasoning": "..."}
  ]
}
```

Be calibrated: most startups should score 40-70. A score above 80 means exceptional evidence. Below 30 means serious concerns. Score based on available evidence — lack of data should lower the score."""


def _extract_json(text: str) -> dict | list | None:
    """Extract a JSON block from text, trying ```json fences first, then bare JSON."""
    json_match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: find first { or [ and try to parse
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue
        # Find matching end
        depth = 0
        for i in range(start, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    break
    return None


async def _call_perplexity(messages: list[dict], timeout: float = 90.0) -> str:
    """Call Perplexity Sonar Pro and return the response content."""
    async with httpx.AsyncClient(timeout=timeout) as client:
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
                "max_tokens": 4096,
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Perplexity API error ({resp.status_code}): {resp.text[:300]}")
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _enrich_data(startup_name: str, website_url: str | None, description: str) -> dict:
    """Call Perplexity to research a startup. Returns parsed enrichment data."""
    user_msg = f"Research this startup thoroughly:\n\nName: {startup_name}"
    if website_url:
        user_msg += f"\nWebsite: {website_url}"
    if description:
        user_msg += f"\nDescription: {description}"

    content = await _call_perplexity([
        {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ])

    data = _extract_json(content)
    if not isinstance(data, dict):
        raise RuntimeError("Perplexity enrichment did not return valid JSON")
    return data


async def _score_startup(enriched_data: dict, dimensions: list[dict]) -> dict:
    """Call Perplexity to score a startup. Returns parsed scoring data."""
    dim_list = "\n".join(
        f"- {d['dimension_name']} (weight: {d['weight']})" for d in dimensions
    )

    user_msg = f"""Evaluate this startup based on the research data below.

## Startup Research Data
{json.dumps(enriched_data, indent=2)}

## Dimensions to Score
{dim_list}

Score each dimension 0-100 with evidence-based reasoning."""

    content = await _call_perplexity([
        {"role": "system", "content": SCORING_SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ])

    data = _extract_json(content)
    if not isinstance(data, dict):
        raise RuntimeError("Perplexity scoring did not return valid JSON")
    return data


async def _fetch_logo_if_needed(startup: Startup, db: AsyncSession) -> None:
    """Fetch logo from Logo.dev if startup has a website but no logo."""
    if startup.logo_url or not startup.website_url or not settings.logo_dev_token:
        return
    try:
        url = startup.website_url if "://" in startup.website_url else f"https://{startup.website_url}"
        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower()
        domain = re.sub(r"^www\.", "", domain)
        if not domain:
            return
        logo_url = f"https://img.logo.dev/{domain}?token={settings.logo_dev_token}&format=png&size=128"
        async with httpx.AsyncClient(timeout=10.0) as client:
            head_resp = await client.head(logo_url, follow_redirects=True)
            if head_resp.status_code == 200:
                startup.logo_url = logo_url
    except Exception:
        pass


async def _ensure_dimensions(startup_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Ensure startup has dimensions. Auto-apply template if none exist. Returns dimension list."""
    result = await db.execute(
        select(StartupDimension)
        .where(StartupDimension.startup_id == startup_id)
        .order_by(StartupDimension.sort_order)
    )
    dims = result.scalars().all()

    if dims:
        return [{"dimension_name": d.dimension_name, "weight": d.weight} for d in dims]

    # No dimensions — try to find a matching template
    # First, check if startup has industries
    startup_result = await db.execute(
        select(Startup).where(Startup.id == startup_id)
    )
    startup = startup_result.scalar_one()

    # Try to find a template matching the startup's first industry name
    from sqlalchemy.orm import selectinload
    startup_with_industries = await db.execute(
        select(Startup).options(selectinload(Startup.industries)).where(Startup.id == startup_id)
    )
    s = startup_with_industries.scalar_one()

    template = None
    if s.industries:
        industry_name = s.industries[0].name
        tmpl_result = await db.execute(
            select(DueDiligenceTemplate)
            .options(selectinload(DueDiligenceTemplate.dimensions))
            .where(DueDiligenceTemplate.name.ilike(f"%{industry_name}%"))
        )
        template = tmpl_result.scalar_one_or_none()

    # Fall back to "Default" template
    if template is None:
        tmpl_result = await db.execute(
            select(DueDiligenceTemplate)
            .options(selectinload(DueDiligenceTemplate.dimensions))
            .where(DueDiligenceTemplate.name == "Default")
        )
        template = tmpl_result.scalar_one_or_none()

    if template is None:
        # No template at all — use hardcoded defaults
        default_dims = [
            {"dimension_name": "Market Opportunity", "weight": 1.2, "sort_order": 0},
            {"dimension_name": "Team Strength", "weight": 1.3, "sort_order": 1},
            {"dimension_name": "Product & Technology", "weight": 1.1, "sort_order": 2},
            {"dimension_name": "Traction & Metrics", "weight": 1.2, "sort_order": 3},
            {"dimension_name": "Business Model", "weight": 1.0, "sort_order": 4},
            {"dimension_name": "Competitive Moat", "weight": 1.0, "sort_order": 5},
            {"dimension_name": "Financials & Unit Economics", "weight": 0.9, "sort_order": 6},
            {"dimension_name": "Timing & Market Readiness", "weight": 0.8, "sort_order": 7},
        ]
    else:
        default_dims = [
            {
                "dimension_name": td.dimension_name,
                "weight": td.weight,
                "sort_order": td.sort_order,
            }
            for td in sorted(template.dimensions, key=lambda d: d.sort_order)
        ]
        startup.template_id = template.id

    # Create StartupDimension records
    slug_re = re.compile(r"[^\w\s-]")
    for dim_data in default_dims:
        slug = slug_re.sub("", dim_data["dimension_name"].lower())
        slug = re.sub(r"[-\s]+", "-", slug).strip("-")
        db.add(StartupDimension(
            startup_id=startup_id,
            dimension_name=dim_data["dimension_name"],
            dimension_slug=slug,
            weight=dim_data["weight"],
            sort_order=dim_data["sort_order"],
        ))

    await db.flush()
    return [{"dimension_name": d["dimension_name"], "weight": d["weight"]} for d in default_dims]


async def run_enrichment_pipeline(startup_id: str) -> None:
    """Run the full enrichment pipeline for a startup. Designed to run as a background task."""
    async with async_session() as db:
        try:
            # Load startup
            result = await db.execute(select(Startup).where(Startup.id == uuid.UUID(startup_id)))
            startup = result.scalar_one_or_none()
            if startup is None:
                logger.error(f"Enrichment: startup {startup_id} not found")
                return

            # Step 1: Set status to running
            startup.enrichment_status = EnrichmentStatus.running
            startup.enrichment_error = None
            await db.commit()

            # Step 2: Perplexity enrichment call
            enriched = await _enrich_data(startup.name, startup.website_url, startup.description)

            # Update startup fields
            if enriched.get("tagline"):
                startup.tagline = enriched["tagline"]
            if enriched.get("description"):
                startup.description = enriched["description"]
            if enriched.get("total_funding"):
                startup.total_funding = enriched["total_funding"]
            if enriched.get("employee_count"):
                startup.employee_count = enriched["employee_count"]
            if enriched.get("linkedin_url"):
                startup.linkedin_url = enriched["linkedin_url"]
            if enriched.get("twitter_url"):
                startup.twitter_url = enriched["twitter_url"]
            if enriched.get("crunchbase_url"):
                startup.crunchbase_url = enriched["crunchbase_url"]
            if enriched.get("competitors"):
                startup.competitors = enriched["competitors"]
            if enriched.get("tech_stack"):
                startup.tech_stack = enriched["tech_stack"]
            if enriched.get("key_metrics"):
                startup.key_metrics = enriched["key_metrics"]
            if enriched.get("hiring_signals"):
                startup.hiring_signals = enriched["hiring_signals"]
            if enriched.get("patents"):
                startup.patents = enriched["patents"]
            if enriched.get("founded_date"):
                try:
                    from datetime import date as date_type
                    fd = enriched["founded_date"]
                    if len(fd) == 4:  # Just a year
                        startup.founded_date = date_type(int(fd), 1, 1)
                    else:
                        startup.founded_date = date_type.fromisoformat(fd)
                except (ValueError, TypeError):
                    pass
            if enriched.get("website_url") and not startup.website_url:
                startup.website_url = enriched["website_url"]

            # Clear and re-insert founders
            await db.execute(
                delete(StartupFounder).where(StartupFounder.startup_id == startup.id)
            )
            for i, f in enumerate(enriched.get("founders") or []):
                if isinstance(f, dict) and f.get("name"):
                    db.add(StartupFounder(
                        startup_id=startup.id,
                        name=f["name"],
                        title=f.get("title"),
                        linkedin_url=f.get("linkedin_url"),
                        sort_order=i,
                    ))

            # Clear and re-insert funding rounds
            await db.execute(
                delete(StartupFundingRound).where(StartupFundingRound.startup_id == startup.id)
            )
            for i, fr in enumerate(enriched.get("funding_rounds") or []):
                if isinstance(fr, dict) and fr.get("round_name"):
                    db.add(StartupFundingRound(
                        startup_id=startup.id,
                        round_name=fr["round_name"],
                        amount=fr.get("amount"),
                        date=fr.get("date"),
                        lead_investor=fr.get("lead_investor"),
                        sort_order=i,
                    ))

            # Clear and re-insert media
            await db.execute(
                delete(StartupMedia).where(StartupMedia.startup_id == startup.id)
            )
            for m in enriched.get("media") or []:
                if isinstance(m, dict) and m.get("url") and m.get("title"):
                    media_type_str = m.get("media_type", "article")
                    try:
                        mt = MediaType(media_type_str)
                    except ValueError:
                        mt = MediaType.article
                    published = None
                    if m.get("published_at"):
                        try:
                            published = datetime.fromisoformat(m["published_at"]).replace(
                                tzinfo=timezone.utc
                            )
                        except (ValueError, TypeError):
                            pass
                    db.add(StartupMedia(
                        startup_id=startup.id,
                        url=m["url"],
                        title=m["title"],
                        source=m.get("source", "Unknown"),
                        media_type=mt,
                        published_at=published,
                    ))

            # Fetch logo if needed
            await _fetch_logo_if_needed(startup, db)

            await db.flush()

            # Step 3: Perplexity scoring call
            dimensions = await _ensure_dimensions(startup.id, db)

            # Build enriched data summary for scoring
            enriched_summary = {
                "name": startup.name,
                "tagline": startup.tagline,
                "description": startup.description,
                "website_url": startup.website_url,
                "stage": startup.stage.value,
                "total_funding": startup.total_funding,
                "employee_count": startup.employee_count,
                "competitors": startup.competitors,
                "tech_stack": startup.tech_stack,
                "key_metrics": startup.key_metrics,
                "hiring_signals": startup.hiring_signals,
                "patents": startup.patents,
                "location": f"{startup.location_city or ''}, {startup.location_state or ''}, {startup.location_country}".strip(", "),
                "founders": [
                    {"name": f.get("name"), "title": f.get("title")}
                    for f in (enriched.get("founders") or [])
                    if isinstance(f, dict)
                ],
                "funding_rounds": enriched.get("funding_rounds") or [],
                "media_coverage": [
                    m.get("title") for m in (enriched.get("media") or []) if isinstance(m, dict)
                ],
            }

            scoring = await _score_startup(enriched_summary, dimensions)

            # Upsert AI review
            await db.execute(
                delete(StartupAIReview).where(StartupAIReview.startup_id == startup.id)
            )
            overall_score = float(scoring.get("overall_score", 50))
            db.add(StartupAIReview(
                startup_id=startup.id,
                overall_score=overall_score,
                investment_thesis=scoring.get("investment_thesis", ""),
                key_risks=scoring.get("key_risks", ""),
                verdict=scoring.get("verdict", ""),
                dimension_scores=scoring.get("dimension_scores", []),
            ))

            # Update startup.ai_score with weighted overall
            dim_scores = scoring.get("dimension_scores", [])
            if dim_scores and dimensions:
                weight_map = {d["dimension_name"]: d["weight"] for d in dimensions}
                total_weight = 0.0
                weighted_sum = 0.0
                for ds in dim_scores:
                    w = weight_map.get(ds.get("dimension_name", ""), 1.0)
                    weighted_sum += float(ds.get("score", 50)) * w
                    total_weight += w
                if total_weight > 0:
                    startup.ai_score = round(weighted_sum / total_weight, 1)
            else:
                startup.ai_score = overall_score

            # Add score history record
            dimensions_json = {}
            for ds in dim_scores:
                if ds.get("dimension_name") and ds.get("score") is not None:
                    dimensions_json[ds["dimension_name"]] = float(ds["score"])

            db.add(StartupScoreHistory(
                startup_id=startup.id,
                score_type=ScoreType.ai,
                score_value=startup.ai_score,
                dimensions_json=dimensions_json if dimensions_json else None,
            ))

            # Step 4: Finalize
            startup.enrichment_status = EnrichmentStatus.complete
            startup.enriched_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(f"Enrichment complete for startup {startup.name} (score: {startup.ai_score})")

        except Exception as e:
            logger.exception(f"Enrichment failed for startup {startup_id}: {e}")
            try:
                # Re-fetch startup in case session is dirty
                result = await db.execute(select(Startup).where(Startup.id == uuid.UUID(startup_id)))
                startup = result.scalar_one_or_none()
                if startup:
                    startup.enrichment_status = EnrichmentStatus.failed
                    startup.enrichment_error = str(e)[:500]
                    await db.commit()
            except Exception:
                logger.exception("Failed to update enrichment error status")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/enrichment.py
git commit -m "feat: add enrichment pipeline service (Perplexity enrichment + scoring)"
```

---

### Task 4: Enrichment API Endpoints

New endpoints for triggering enrichment, checking status, and reading AI reviews.

**Files:**
- Create: `backend/app/api/admin_enrichment.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the enrichment router**

Create `backend/app/api/admin_enrichment.py`:

```python
import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.ai_review import StartupAIReview
from app.models.founder import StartupFounder
from app.models.funding_round import StartupFundingRound
from app.models.startup import EnrichmentStatus, Startup
from app.models.user import User
from app.services.enrichment import run_enrichment_pipeline

router = APIRouter()


@router.post("/api/admin/startups/{startup_id}/enrich")
async def trigger_enrichment(
    startup_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    startup = result.scalar_one_or_none()
    if startup is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    if startup.enrichment_status == EnrichmentStatus.running:
        raise HTTPException(status_code=409, detail="Enrichment already in progress")

    background_tasks.add_task(run_enrichment_pipeline, str(startup_id))
    return {"status": "running"}


@router.get("/api/admin/startups/{startup_id}/enrichment-status")
async def get_enrichment_status(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    startup = result.scalar_one_or_none()
    if startup is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    return {
        "enrichment_status": startup.enrichment_status.value,
        "enrichment_error": startup.enrichment_error,
        "enriched_at": startup.enriched_at.isoformat() if startup.enriched_at else None,
    }


@router.get("/api/admin/startups/{startup_id}/ai-review")
async def get_ai_review(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StartupAIReview).where(StartupAIReview.startup_id == startup_id)
    )
    review = result.scalar_one_or_none()
    if review is None:
        raise HTTPException(status_code=404, detail="No AI review found")

    return {
        "id": str(review.id),
        "startup_id": str(review.startup_id),
        "overall_score": review.overall_score,
        "investment_thesis": review.investment_thesis,
        "key_risks": review.key_risks,
        "verdict": review.verdict,
        "dimension_scores": review.dimension_scores,
        "created_at": review.created_at.isoformat(),
    }


@router.get("/api/admin/startups/{startup_id}/full-detail")
async def get_startup_full_detail(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    """Full startup detail including enriched data, founders, funding, and AI review."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Startup).options(selectinload(Startup.industries)).where(Startup.id == startup_id)
    )
    startup = result.scalar_one_or_none()
    if startup is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    # Founders
    founders_result = await db.execute(
        select(StartupFounder)
        .where(StartupFounder.startup_id == startup_id)
        .order_by(StartupFounder.sort_order)
    )
    founders = founders_result.scalars().all()

    # Funding rounds
    funding_result = await db.execute(
        select(StartupFundingRound)
        .where(StartupFundingRound.startup_id == startup_id)
        .order_by(StartupFundingRound.sort_order)
    )
    funding_rounds = funding_result.scalars().all()

    # AI review
    review_result = await db.execute(
        select(StartupAIReview).where(StartupAIReview.startup_id == startup_id)
    )
    review = review_result.scalar_one_or_none()

    return {
        "id": str(startup.id),
        "name": startup.name,
        "slug": startup.slug,
        "description": startup.description,
        "tagline": startup.tagline,
        "website_url": startup.website_url,
        "logo_url": startup.logo_url,
        "stage": startup.stage.value,
        "status": startup.status.value,
        "location_city": startup.location_city,
        "location_state": startup.location_state,
        "location_country": startup.location_country,
        "founded_date": startup.founded_date.isoformat() if startup.founded_date else None,
        "total_funding": startup.total_funding,
        "employee_count": startup.employee_count,
        "linkedin_url": startup.linkedin_url,
        "twitter_url": startup.twitter_url,
        "crunchbase_url": startup.crunchbase_url,
        "competitors": startup.competitors,
        "tech_stack": startup.tech_stack,
        "key_metrics": startup.key_metrics,
        "hiring_signals": startup.hiring_signals,
        "patents": startup.patents,
        "enrichment_status": startup.enrichment_status.value,
        "enrichment_error": startup.enrichment_error,
        "enriched_at": startup.enriched_at.isoformat() if startup.enriched_at else None,
        "ai_score": startup.ai_score,
        "industries": [{"id": str(i.id), "name": i.name, "slug": i.slug} for i in startup.industries],
        "founders": [
            {"id": str(f.id), "name": f.name, "title": f.title, "linkedin_url": f.linkedin_url}
            for f in founders
        ],
        "funding_rounds": [
            {"id": str(fr.id), "round_name": fr.round_name, "amount": fr.amount, "date": fr.date, "lead_investor": fr.lead_investor}
            for fr in funding_rounds
        ],
        "ai_review": {
            "overall_score": review.overall_score,
            "investment_thesis": review.investment_thesis,
            "key_risks": review.key_risks,
            "verdict": review.verdict,
            "dimension_scores": review.dimension_scores,
            "created_at": review.created_at.isoformat(),
        } if review else None,
    }
```

- [ ] **Step 2: Register the router in main.py**

In `backend/app/main.py`, add:

```python
from app.api.admin_enrichment import router as admin_enrichment_router
```

And:

```python
app.include_router(admin_enrichment_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin_enrichment.py backend/app/main.py
git commit -m "feat: add enrichment API endpoints (trigger, status, AI review, full detail)"
```

---

### Task 5: Modify Existing Backend Endpoints

Wire enrichment into approval flow, add dedup to scout, extend public detail response.

**Files:**
- Modify: `backend/app/api/admin.py`
- Modify: `backend/app/api/admin_scout.py`
- Modify: `backend/app/api/startups.py`

- [ ] **Step 1: Trigger enrichment on approval in admin.py**

In `backend/app/api/admin.py`, add import at top:

```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
```

(Add `BackgroundTasks` to the existing import.)

Update the `update_startup` function signature to include `background_tasks: BackgroundTasks`:

```python
@router.put("/api/admin/startups/{startup_id}")
async def update_startup(
    startup_id: uuid.UUID,
    body: StartupUpdateIn,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
```

After `await db.commit()` and before `await db.refresh(startup)`, add:

```python
    # Trigger enrichment if status changed to approved
    if body.status == "approved":
        from app.services.enrichment import run_enrichment_pipeline
        background_tasks.add_task(run_enrichment_pipeline, str(startup_id))
```

Also update the `startup_pipeline` response to include `enrichment_status`:

In the `response.append(...)` block, add after `"dimensions_configured"`:

```python
            "enrichment_status": s.enrichment_status.value if hasattr(s, 'enrichment_status') else "none",
```

- [ ] **Step 2: Add dedup to scout chat in admin_scout.py**

In `backend/app/api/admin_scout.py`, add import at top:

```python
from app.services.dedup import normalize_name, normalize_domain
```

Update `scout_chat` endpoint. After parsing startups from the response and before the return, add dedup checking:

After the existing `startups` list is built (around line 170), add:

```python
    # Check for duplicates against existing startups
    existing_result = await db.execute(select(Startup))
    existing_startups = existing_result.scalars().all()

    existing_names = {normalize_name(s.name) for s in existing_startups}
    existing_domains = {normalize_domain(s.website_url) for s in existing_startups if s.website_url}
    existing_lookup = {}
    for s in existing_startups:
        existing_lookup[normalize_name(s.name)] = {"id": str(s.id), "name": s.name, "status": s.status.value}
        if s.website_url:
            existing_lookup[normalize_domain(s.website_url)] = {"id": str(s.id), "name": s.name, "status": s.status.value}

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
```

This requires `scout_chat` to also get `db`. Update its signature:

```python
@router.post("/api/admin/scout/chat")
async def scout_chat(
    body: ScoutChatRequest,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
```

Also update the `scout_add_startups` function to use domain-based dedup. Replace the existing duplicate check:

```python
    for candidate in body.startups:
        # Check for duplicate by name or domain
        existing = await db.execute(
            select(Startup).where(Startup.name == candidate.name)
        )
```

With:

```python
    for candidate in body.startups:
        # Check for duplicate by normalized name or domain
        from app.services.dedup import find_duplicate
        dup = await find_duplicate(db, candidate.name, candidate.website_url)
        if dup is not None:
            skipped.append(candidate.name)
            continue

        # Remove the old duplicate check (was: existing = await db.execute...)
```

Delete the old `if existing.scalar_one_or_none() is not None:` block since `find_duplicate` now handles it.

- [ ] **Step 3: Extend public startup detail response**

In `backend/app/api/startups.py`, add imports at top:

```python
from app.models.ai_review import StartupAIReview
from app.models.founder import StartupFounder
from app.models.funding_round import StartupFundingRound
```

In the `get_startup` function, after fetching scores, add:

```python
    # Fetch founders
    founders_result = await db.execute(
        select(StartupFounder)
        .where(StartupFounder.startup_id == startup.id)
        .order_by(StartupFounder.sort_order)
    )
    founders = founders_result.scalars().all()

    # Fetch funding rounds
    funding_result = await db.execute(
        select(StartupFundingRound)
        .where(StartupFundingRound.startup_id == startup.id)
        .order_by(StartupFundingRound.sort_order)
    )
    funding_rounds = funding_result.scalars().all()

    # Fetch AI review
    review_result = await db.execute(
        select(StartupAIReview).where(StartupAIReview.startup_id == startup.id)
    )
    ai_review = review_result.scalar_one_or_none()
```

Add these fields to the return dict (after `"industries":`):

```python
        "tagline": startup.tagline,
        "total_funding": startup.total_funding,
        "employee_count": startup.employee_count,
        "linkedin_url": startup.linkedin_url,
        "twitter_url": startup.twitter_url,
        "crunchbase_url": startup.crunchbase_url,
        "competitors": startup.competitors,
        "tech_stack": startup.tech_stack,
        "key_metrics": startup.key_metrics,
        "founders": [
            {"name": f.name, "title": f.title, "linkedin_url": f.linkedin_url}
            for f in founders
        ],
        "funding_rounds": [
            {"round_name": fr.round_name, "amount": fr.amount, "date": fr.date, "lead_investor": fr.lead_investor}
            for fr in funding_rounds
        ],
        "ai_review": {
            "overall_score": ai_review.overall_score,
            "investment_thesis": ai_review.investment_thesis,
            "key_risks": ai_review.key_risks,
            "verdict": ai_review.verdict,
            "dimension_scores": ai_review.dimension_scores,
            "created_at": ai_review.created_at.isoformat(),
        } if ai_review else None,
```

Also add `tagline` to the list endpoint items (in `list_startups` return):

```python
                "tagline": s.tagline,
```

(Add after `"user_score"` line.)

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/admin.py backend/app/api/admin_scout.py backend/app/api/startups.py
git commit -m "feat: wire enrichment into approval, add scout dedup, extend public API"
```

---

### Task 6: Admin Frontend — Types and API Client

Add TypeScript types and API methods for enrichment.

**Files:**
- Modify: `admin/lib/types.ts`
- Modify: `admin/lib/api.ts`

- [ ] **Step 1: Add enrichment types**

In `admin/lib/types.ts`, add these types:

```typescript
export interface Founder {
  id: string;
  name: string;
  title: string | null;
  linkedin_url: string | null;
}

export interface FundingRound {
  id: string;
  round_name: string;
  amount: string | null;
  date: string | null;
  lead_investor: string | null;
}

export interface DimensionScore {
  dimension_name: string;
  score: number;
  reasoning: string;
}

export interface AIReview {
  overall_score: number;
  investment_thesis: string;
  key_risks: string;
  verdict: string;
  dimension_scores: DimensionScore[];
  created_at: string;
}

export interface EnrichmentStatus {
  enrichment_status: "none" | "running" | "complete" | "failed";
  enrichment_error: string | null;
  enriched_at: string | null;
}

export interface StartupFullDetail {
  id: string;
  name: string;
  slug: string;
  description: string;
  tagline: string | null;
  website_url: string | null;
  logo_url: string | null;
  stage: string;
  status: string;
  location_city: string | null;
  location_state: string | null;
  location_country: string;
  founded_date: string | null;
  total_funding: string | null;
  employee_count: string | null;
  linkedin_url: string | null;
  twitter_url: string | null;
  crunchbase_url: string | null;
  competitors: string | null;
  tech_stack: string | null;
  key_metrics: string | null;
  hiring_signals: string | null;
  patents: string | null;
  enrichment_status: "none" | "running" | "complete" | "failed";
  enrichment_error: string | null;
  enriched_at: string | null;
  ai_score: number | null;
  industries: { id: string; name: string; slug: string }[];
  founders: Founder[];
  funding_rounds: FundingRound[];
  ai_review: AIReview | null;
}
```

Also update the `StartupCandidate` type to include dedup fields:

```typescript
export interface StartupCandidate {
  name: string;
  website_url: string | null;
  description: string;
  stage: string;
  location_city: string | null;
  location_state: string | null;
  founders: string | null;
  funding_raised: string | null;
  key_investors: string | null;
  linkedin_url: string | null;
  founded_year: string | null;
  already_on_platform?: boolean;
  existing_status?: string;
  existing_id?: string;
}
```

- [ ] **Step 2: Add enrichment API methods**

In `admin/lib/api.ts`, add these methods to the `adminApi` object:

```typescript
  // Enrichment
  triggerEnrichment: (token: string, startupId: string) =>
    apiFetch<{ status: string }>(`/api/admin/startups/${startupId}/enrich`, token, {
      method: "POST",
    }),

  getEnrichmentStatus: (token: string, startupId: string) =>
    apiFetch<EnrichmentStatus>(`/api/admin/startups/${startupId}/enrichment-status`, token),

  getAIReview: (token: string, startupId: string) =>
    apiFetch<AIReview>(`/api/admin/startups/${startupId}/ai-review`, token),

  getStartupFullDetail: (token: string, startupId: string) =>
    apiFetch<StartupFullDetail>(`/api/admin/startups/${startupId}/full-detail`, token),
```

Add the new types to the import at the top of the file:

```typescript
import type {
  // ... existing imports ...
  AIReview,
  EnrichmentStatus,
  StartupFullDetail,
} from "./types";
```

- [ ] **Step 3: Commit**

```bash
git add admin/lib/types.ts admin/lib/api.ts
git commit -m "feat: add enrichment types and API methods to admin frontend"
```

---

### Task 7: Admin Startup Detail Page — Enrichment UI

Add enrichment status, trigger button, and display enriched data + AI review on the admin startup detail page.

**Files:**
- Modify: `admin/app/startups/[id]/page.tsx`

- [ ] **Step 1: Rewrite the admin startup detail page**

Replace the entire content of `admin/app/startups/[id]/page.tsx` with the enriched version. The new page:

- Uses `adminApi.getStartupFullDetail()` instead of finding the startup in `getAllStartups()`
- Shows enrichment status badge + trigger/re-run button in the header
- Polls enrichment status every 3 seconds while running
- Displays Founders section (name, title, LinkedIn link)
- Displays Funding Rounds table
- Displays AI Investment Memo (overall score, thesis, dimension scores with bars, risks, verdict)
- Displays Company Intel grid (tagline, employee count, metrics, competitors, tech stack, hiring, patents, social links)
- Keeps existing StartupEditor, DimensionManager, ExpertPicker sections

```tsx
"use client";

import { useEffect, useState, use, useRef } from "react";
import { useSession } from "next-auth/react";
import { AccessDenied } from "@/components/AccessDenied";
import { Sidebar } from "@/components/Sidebar";
import { StartupEditor } from "@/components/StartupEditor";
import { DimensionManager } from "@/components/DimensionManager";
import { ExpertPicker } from "@/components/ExpertPicker";
import { adminApi } from "@/lib/api";
import type { StartupFullDetail, DDTemplate, Dimension, ApprovedExpert, Assignment } from "@/lib/types";

function ScoreBar({ score, label }: { score: number; label: string }) {
  const color = score >= 70 ? "bg-score-high" : score >= 40 ? "bg-score-mid" : "bg-score-low";
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-text-tertiary w-40 shrink-0">{label}</span>
      <div className="flex-1 h-2 bg-hover-row rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-xs font-medium text-text-primary w-8 text-right">{score}</span>
    </div>
  );
}

export default function StartupDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: session, status } = useSession();
  const [startup, setStartup] = useState<StartupFullDetail | null>(null);
  const [dimensions, setDimensions] = useState<Dimension[]>([]);
  const [templates, setTemplates] = useState<DDTemplate[]>([]);
  const [experts, setExperts] = useState<ApprovedExpert[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchingLogo, setFetchingLogo] = useState(false);
  const [logoError, setLogoError] = useState<string | null>(null);
  const [enriching, setEnriching] = useState(false);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (session?.backendToken) loadAll();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [session?.backendToken, id]);

  async function loadAll() {
    if (!session?.backendToken) return;
    setLoading(true);
    try {
      const [detail, dims, tmpls, exps, assigns] = await Promise.all([
        adminApi.getStartupFullDetail(session.backendToken, id),
        adminApi.getDimensions(session.backendToken, id),
        adminApi.getTemplates(session.backendToken),
        adminApi.getApprovedExperts(session.backendToken),
        adminApi.getAssignments(session.backendToken, id),
      ]);
      setStartup(detail);
      setDimensions(dims);
      setTemplates(tmpls);
      setExperts(exps);
      setAssignments(assigns);
      if (detail.enrichment_status === "running") startPolling();
    } finally {
      setLoading(false);
    }
  }

  function startPolling() {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      if (!session?.backendToken) return;
      try {
        const st = await adminApi.getEnrichmentStatus(session.backendToken, id);
        if (st.enrichment_status !== "running") {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setEnriching(false);
          loadAll();
        }
      } catch {}
    }, 3000);
  }

  async function handleEnrich() {
    if (!session?.backendToken) return;
    setEnriching(true);
    try {
      await adminApi.triggerEnrichment(session.backendToken, id);
      setStartup((prev) => prev ? { ...prev, enrichment_status: "running", enrichment_error: null } : prev);
      startPolling();
    } catch (err) {
      setEnriching(false);
    }
  }

  async function handleFetchLogo() {
    if (!session?.backendToken) return;
    setFetchingLogo(true);
    setLogoError(null);
    try {
      await adminApi.fetchLogo(session.backendToken, id);
      await loadAll();
    } catch (err) {
      setLogoError(err instanceof Error ? err.message : "Failed to fetch logo");
    } finally {
      setFetchingLogo(false);
    }
  }

  if (status === "loading") return null;
  if (!session || session.role !== "superadmin") return <AccessDenied />;

  const isRunning = startup?.enrichment_status === "running" || enriching;

  return (
    <div className="flex">
      <Sidebar />
      <main className="ml-56 flex-1 p-6">
        {loading || !startup ? (
          <p className="text-text-tertiary">Loading...</p>
        ) : (
          <div className="space-y-8">
            {/* Header */}
            <div className="flex items-center gap-4">
              {startup.logo_url ? (
                <img src={startup.logo_url} alt={startup.name} className="w-12 h-12 rounded border border-border object-contain bg-white" />
              ) : (
                <div className="w-12 h-12 rounded border border-border bg-hover-row flex items-center justify-center text-text-tertiary text-lg font-serif">
                  {startup.name.charAt(0)}
                </div>
              )}
              <div>
                <h2 className="font-serif text-xl text-text-primary">{startup.name}</h2>
                {startup.tagline && <p className="text-sm text-text-secondary">{startup.tagline}</p>}
                {startup.website_url && (
                  <a href={startup.website_url.startsWith("http") ? startup.website_url : `https://${startup.website_url}`}
                    target="_blank" rel="noopener noreferrer" className="text-sm text-text-tertiary hover:text-accent transition">
                    {startup.website_url}
                  </a>
                )}
              </div>
              <div className="ml-auto flex items-center gap-3">
                {/* Enrichment status */}
                {isRunning && (
                  <span className="text-xs text-accent animate-pulse">Enriching...</span>
                )}
                {startup.enrichment_status === "complete" && (
                  <span className="text-xs text-score-high">Enriched</span>
                )}
                {startup.enrichment_status === "failed" && (
                  <span className="text-xs text-score-low" title={startup.enrichment_error || ""}>Failed</span>
                )}
                <button onClick={handleEnrich} disabled={isRunning}
                  className="px-3 py-1.5 text-sm border border-border rounded text-text-secondary hover:text-accent hover:border-accent disabled:opacity-40 transition">
                  {isRunning ? "Enriching..." : startup.enrichment_status === "complete" ? "Re-run Enrichment" : "Run AI Enrichment"}
                </button>
                {startup.website_url && (
                  <button onClick={handleFetchLogo} disabled={fetchingLogo}
                    className="px-3 py-1.5 text-sm border border-border rounded text-text-secondary hover:text-accent hover:border-accent disabled:opacity-40 transition">
                    {fetchingLogo ? "Fetching..." : startup.logo_url ? "Refresh Logo" : "Fetch Logo"}
                  </button>
                )}
              </div>
            </div>
            {logoError && <p className="text-sm text-score-low">{logoError}</p>}
            {startup.enrichment_status === "failed" && startup.enrichment_error && (
              <p className="text-sm text-score-low bg-score-low/5 rounded p-3">{startup.enrichment_error}</p>
            )}

            {/* AI Investment Memo */}
            {startup.ai_review && (
              <section className="rounded border border-border bg-surface p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-medium text-text-primary">AI Investment Memo</h3>
                  <div className={`text-2xl font-bold ${startup.ai_review.overall_score >= 70 ? "text-score-high" : startup.ai_review.overall_score >= 40 ? "text-score-mid" : "text-score-low"}`}>
                    {Math.round(startup.ai_review.overall_score)}
                  </div>
                </div>

                <div className="space-y-6">
                  <div>
                    <h4 className="text-sm font-medium text-text-primary mb-1">Investment Thesis</h4>
                    <p className="text-sm text-text-secondary">{startup.ai_review.investment_thesis}</p>
                  </div>

                  <div>
                    <h4 className="text-sm font-medium text-text-primary mb-3">Dimension Scores</h4>
                    <div className="space-y-3">
                      {startup.ai_review.dimension_scores.map((ds) => (
                        <div key={ds.dimension_name}>
                          <ScoreBar score={ds.score} label={ds.dimension_name} />
                          <p className="text-xs text-text-tertiary mt-1 ml-43">{ds.reasoning}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div>
                    <h4 className="text-sm font-medium text-text-primary mb-1">Key Risks</h4>
                    <p className="text-sm text-text-secondary">{startup.ai_review.key_risks}</p>
                  </div>

                  <div>
                    <h4 className="text-sm font-medium text-text-primary mb-1">Verdict</h4>
                    <p className="text-sm text-text-secondary font-medium">{startup.ai_review.verdict}</p>
                  </div>

                  <p className="text-xs text-text-tertiary">Generated on {new Date(startup.ai_review.created_at).toLocaleDateString()}</p>
                </div>
              </section>
            )}

            {/* Founders */}
            {startup.founders.length > 0 && (
              <section>
                <h3 className="text-lg font-medium text-text-primary mb-3">Founders</h3>
                <div className="grid grid-cols-2 gap-3">
                  {startup.founders.map((f) => (
                    <div key={f.id} className="rounded border border-border p-3 flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-hover-row flex items-center justify-center text-text-tertiary text-sm font-serif">
                        {f.name.charAt(0)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-text-primary truncate">{f.name}</p>
                        {f.title && <p className="text-xs text-text-tertiary truncate">{f.title}</p>}
                      </div>
                      {f.linkedin_url && (
                        <a href={f.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-xs text-accent hover:text-accent-hover transition shrink-0">
                          LinkedIn
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* Funding Rounds */}
            {startup.funding_rounds.length > 0 && (
              <section>
                <h3 className="text-lg font-medium text-text-primary mb-3">Funding History</h3>
                <div className="rounded border border-border overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-hover-row">
                      <tr>
                        <th className="text-left px-4 py-2 text-text-tertiary font-medium">Round</th>
                        <th className="text-left px-4 py-2 text-text-tertiary font-medium">Amount</th>
                        <th className="text-left px-4 py-2 text-text-tertiary font-medium">Date</th>
                        <th className="text-left px-4 py-2 text-text-tertiary font-medium">Lead Investor</th>
                      </tr>
                    </thead>
                    <tbody>
                      {startup.funding_rounds.map((fr) => (
                        <tr key={fr.id} className="border-t border-border">
                          <td className="px-4 py-2 text-text-primary">{fr.round_name}</td>
                          <td className="px-4 py-2 text-text-secondary">{fr.amount || "—"}</td>
                          <td className="px-4 py-2 text-text-secondary">{fr.date || "—"}</td>
                          <td className="px-4 py-2 text-text-secondary">{fr.lead_investor || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {startup.total_funding && (
                  <p className="text-sm text-text-tertiary mt-2">Total raised: {startup.total_funding}</p>
                )}
              </section>
            )}

            {/* Company Intel */}
            {startup.enrichment_status === "complete" && (
              <section>
                <h3 className="text-lg font-medium text-text-primary mb-3">Company Intel</h3>
                <div className="grid grid-cols-2 gap-4">
                  {startup.employee_count && (
                    <div className="rounded border border-border p-3">
                      <p className="text-xs text-text-tertiary mb-1">Employees</p>
                      <p className="text-sm text-text-primary">{startup.employee_count}</p>
                    </div>
                  )}
                  {startup.key_metrics && (
                    <div className="rounded border border-border p-3">
                      <p className="text-xs text-text-tertiary mb-1">Key Metrics</p>
                      <p className="text-sm text-text-primary">{startup.key_metrics}</p>
                    </div>
                  )}
                  {startup.competitors && (
                    <div className="rounded border border-border p-3 col-span-2">
                      <p className="text-xs text-text-tertiary mb-1">Competitors</p>
                      <p className="text-sm text-text-primary">{startup.competitors}</p>
                    </div>
                  )}
                  {startup.tech_stack && (
                    <div className="rounded border border-border p-3 col-span-2">
                      <p className="text-xs text-text-tertiary mb-1">Tech Stack</p>
                      <p className="text-sm text-text-primary">{startup.tech_stack}</p>
                    </div>
                  )}
                  {startup.hiring_signals && (
                    <div className="rounded border border-border p-3 col-span-2">
                      <p className="text-xs text-text-tertiary mb-1">Hiring Signals</p>
                      <p className="text-sm text-text-primary">{startup.hiring_signals}</p>
                    </div>
                  )}
                  {startup.patents && (
                    <div className="rounded border border-border p-3 col-span-2">
                      <p className="text-xs text-text-tertiary mb-1">Patents</p>
                      <p className="text-sm text-text-primary">{startup.patents}</p>
                    </div>
                  )}
                </div>
                {/* Social Links */}
                <div className="flex gap-3 mt-3">
                  {startup.linkedin_url && (
                    <a href={startup.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-xs text-accent hover:text-accent-hover transition">LinkedIn</a>
                  )}
                  {startup.twitter_url && (
                    <a href={startup.twitter_url} target="_blank" rel="noopener noreferrer" className="text-xs text-accent hover:text-accent-hover transition">Twitter/X</a>
                  )}
                  {startup.crunchbase_url && (
                    <a href={startup.crunchbase_url} target="_blank" rel="noopener noreferrer" className="text-xs text-accent hover:text-accent-hover transition">Crunchbase</a>
                  )}
                </div>
              </section>
            )}

            <hr className="border-border" />

            {/* Edit Startup */}
            <section>
              <h3 className="text-lg font-medium text-text-primary mb-3">Edit Startup</h3>
              <StartupEditor
                initial={{
                  name: startup.name,
                  description: startup.description,
                  website_url: startup.website_url,
                  stage: startup.stage,
                  status: startup.status,
                  location_city: startup.location_city,
                  location_state: startup.location_state,
                  location_country: startup.location_country || "US",
                }}
                onSave={async (data) => {
                  await adminApi.updateStartup(session.backendToken!, id, data);
                  loadAll();
                }}
              />
            </section>

            <hr className="border-border" />

            {/* Dimensions */}
            <section>
              <DimensionManager
                dimensions={dimensions}
                templates={templates}
                onApplyTemplate={async (templateId) => {
                  const result = await adminApi.applyTemplate(session.backendToken!, id, templateId);
                  setDimensions(result.dimensions);
                }}
                onSaveDimensions={async (dims) => {
                  const result = await adminApi.updateDimensions(session.backendToken!, id, dims);
                  setDimensions(result);
                }}
              />
            </section>

            <hr className="border-border" />

            {/* Expert Assignments */}
            <section>
              <ExpertPicker
                experts={experts}
                assignments={assignments}
                onAssign={async (expertId) => {
                  await adminApi.assignExpert(session.backendToken!, id, expertId);
                  loadAll();
                }}
                onRemoveAssignment={async (assignmentId) => {
                  await adminApi.deleteAssignment(session.backendToken!, assignmentId);
                  loadAll();
                }}
              />
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add admin/app/startups/[id]/page.tsx
git commit -m "feat: admin startup detail with enrichment status, AI memo, founders, funding, company intel"
```

---

### Task 8: Admin Scout — Dedup UI

Show "Already on platform" badges on scout results that match existing startups.

**Files:**
- Modify: `admin/app/scout/page.tsx`

- [ ] **Step 1: Update the StartupCard to handle dedup**

In `admin/app/scout/page.tsx`, update the `StartupCard` component. Add after the existing component props check — wrap the entire card with a dedup overlay:

In the `StartupCard` function, change the outer div's `onClick` to be conditional:

```tsx
function StartupCard({
  startup,
  selected,
  onToggle,
  index,
}: {
  startup: StartupCandidate;
  selected: boolean;
  onToggle: () => void;
  index: number;
}) {
  const isDuplicate = startup.already_on_platform;

  return (
    <div
      onClick={isDuplicate ? undefined : onToggle}
      className={`rounded border p-3 transition ${
        isDuplicate
          ? "border-border bg-hover-row opacity-60 cursor-not-allowed"
          : selected
            ? "border-accent bg-accent/5 cursor-pointer"
            : "border-border bg-surface hover:border-text-tertiary cursor-pointer"
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 shrink-0">
          {isDuplicate ? (
            <div className="w-5 h-5 rounded border-2 border-border flex items-center justify-center text-xs text-text-tertiary">
              —
            </div>
          ) : (
            <div
              className={`w-5 h-5 rounded border-2 flex items-center justify-center text-xs transition ${
                selected
                  ? "border-accent bg-accent text-white"
                  : "border-border"
              }`}
            >
              {selected && "\u2713"}
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-tertiary">#{index + 1}</span>
            <h4 className="font-medium text-text-primary text-sm truncate">{startup.name}</h4>
            <span className="shrink-0 text-xs px-1.5 py-0.5 rounded border border-border text-text-tertiary">
              {STAGE_LABELS[startup.stage] || startup.stage}
            </span>
            {isDuplicate && (
              <span className="shrink-0 text-xs px-1.5 py-0.5 rounded bg-text-tertiary/10 text-text-tertiary">
                Already {startup.existing_status || "on platform"}
              </span>
            )}
          </div>
          <p className="text-xs text-text-secondary mt-1 line-clamp-2">{startup.description}</p>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 text-xs text-text-tertiary">
            {startup.website_url && (
              <a
                href={startup.website_url.startsWith("http") ? startup.website_url : `https://${startup.website_url}`}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="hover:text-accent transition"
              >
                {startup.website_url.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}
              </a>
            )}
            {startup.location_city && (
              <span>{startup.location_city}{startup.location_state ? `, ${startup.location_state}` : ""}</span>
            )}
            {startup.founders && <span>Founded by {startup.founders}</span>}
            {startup.funding_raised && <span>{startup.funding_raised} raised</span>}
            {startup.key_investors && <span>Investors: {startup.key_investors}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Filter duplicates from selection**

In the `handleSend` function, when auto-selecting all startups, exclude duplicates:

Change the auto-select block from:

```tsx
      if (result.startups.length > 0) {
        const newMsgIndex = messages.length + 1;
        setSelectedByMessage((prev) => ({
          ...prev,
          [newMsgIndex]: new Set(Array.from({ length: result.startups.length }, (_, i) => i)),
        }));
      }
```

To:

```tsx
      if (result.startups.length > 0) {
        const newMsgIndex = messages.length + 1;
        const selectableIndices = result.startups
          .map((s: StartupCandidate, i: number) => (!s.already_on_platform ? i : -1))
          .filter((i: number) => i >= 0);
        setSelectedByMessage((prev) => ({
          ...prev,
          [newMsgIndex]: new Set(selectableIndices),
        }));
      }
```

Also update `toggleSelectAll` to exclude duplicates — in the `StartupResults` component, pass the startups array and update the select all logic:

In `toggleSelectAll`, change to accept startups as a parameter:

```tsx
  function toggleSelectAll(msgIndex: number, total: number, startups?: StartupCandidate[]) {
    setSelectedByMessage((prev) => {
      const current = prev[msgIndex] || new Set();
      if (current.size > 0 && current.size === [...current].length) {
        return { ...prev, [msgIndex]: new Set() };
      }
      const selectable = startups
        ? Array.from({ length: total }, (_, i) => i).filter((i) => !startups[i]?.already_on_platform)
        : Array.from({ length: total }, (_, i) => i);
      return { ...prev, [msgIndex]: new Set(selectable) };
    });
  }
```

And update the call in the JSX to pass startups:

```tsx
onSelectAll={() => toggleSelectAll(i, msg.startups!.length, msg.startups)}
```

- [ ] **Step 3: Commit**

```bash
git add admin/app/scout/page.tsx
git commit -m "feat: scout dedup UI — gray out startups already on platform"
```

---

### Task 9: Public Frontend — Types and Detail Page

Extend the public startup detail page with AI analysis, founders, funding, and company intel.

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/app/startups/[slug]/page.tsx`

- [ ] **Step 1: Extend public frontend types**

In `frontend/lib/types.ts`, add after the existing `StartupDetail` interface:

```typescript
export interface Founder {
  name: string;
  title: string | null;
  linkedin_url: string | null;
}

export interface FundingRound {
  round_name: string;
  amount: string | null;
  date: string | null;
  lead_investor: string | null;
}

export interface DimensionScore {
  dimension_name: string;
  score: number;
  reasoning: string;
}

export interface AIReview {
  overall_score: number;
  investment_thesis: string;
  key_risks: string;
  verdict: string;
  dimension_scores: DimensionScore[];
  created_at: string;
}
```

Update `StartupCard` to include `tagline`:

```typescript
export interface StartupCard {
  // ... existing fields ...
  tagline: string | null;
}
```

Update `StartupDetail` to include enriched fields:

```typescript
export interface StartupDetail extends StartupCard {
  founded_date: string | null;
  media: MediaItem[];
  score_history: ScoreHistory[];
  tagline: string | null;
  total_funding: string | null;
  employee_count: string | null;
  linkedin_url: string | null;
  twitter_url: string | null;
  crunchbase_url: string | null;
  competitors: string | null;
  tech_stack: string | null;
  key_metrics: string | null;
  founders: Founder[];
  funding_rounds: FundingRound[];
  ai_review: AIReview | null;
}
```

- [ ] **Step 2: Rewrite the public startup detail page**

Replace `frontend/app/startups/[slug]/page.tsx` with the enriched version:

```tsx
import { notFound } from "next/navigation";
import type { StartupDetail } from "@/lib/types";
import { ScoreComparison } from "@/components/ScoreComparison";
import { ScoreTimeline } from "@/components/ScoreTimeline";
import { DimensionRadar } from "@/components/DimensionRadar";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const stageLabels: Record<string, string> = {
  pre_seed: "Pre-Seed", seed: "Seed", series_a: "Series A",
  series_b: "Series B", series_c: "Series C", growth: "Growth",
};

async function getStartup(slug: string): Promise<StartupDetail | null> {
  const res = await fetch(`${API_URL}/api/startups/${slug}`, { cache: "no-store" });
  if (!res.ok) return null;
  return res.json();
}

function ScoreBar({ score, label }: { score: number; label: string }) {
  const color = score >= 70 ? "bg-score-high" : score >= 40 ? "bg-score-mid" : "bg-score-low";
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-text-secondary w-48 shrink-0">{label}</span>
      <div className="flex-1 h-2.5 bg-background rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${score}%` }} />
      </div>
      <span className="text-sm font-medium text-text-primary w-8 text-right tabular-nums">{score}</span>
    </div>
  );
}

export default async function StartupPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const startup = await getStartup(slug);
  if (!startup) notFound();

  return (
    <div className="max-w-4xl mx-auto">
      {/* Hero */}
      <div className="flex items-start gap-6 mb-12">
        {startup.logo_url ? (
          <img src={startup.logo_url} alt={startup.name} className="h-20 w-20 rounded object-cover" />
        ) : (
          <div className="h-20 w-20 rounded bg-background border border-border flex items-center justify-center font-serif text-2xl text-text-tertiary">
            {startup.name[0]}
          </div>
        )}
        <div className="flex-1">
          <h1 className="font-serif text-3xl text-text-primary">{startup.name}</h1>
          {startup.tagline && <p className="text-text-secondary mt-1">{startup.tagline}</p>}
          <p className="text-text-secondary mt-2">{startup.description}</p>
          <div className="flex flex-wrap gap-2 mt-3">
            <span className="rounded border border-border px-3 py-1 text-xs font-medium text-text-secondary">
              {stageLabels[startup.stage] || startup.stage}
            </span>
            {startup.industries.map((ind) => (
              <span key={ind.id} className="rounded px-3 py-1 text-xs text-text-tertiary">{ind.name}</span>
            ))}
            {startup.total_funding && (
              <span className="rounded border border-border px-3 py-1 text-xs text-text-secondary">{startup.total_funding} raised</span>
            )}
            {startup.employee_count && (
              <span className="rounded border border-border px-3 py-1 text-xs text-text-secondary">{startup.employee_count} employees</span>
            )}
          </div>
          <div className="flex gap-3 mt-3">
            {startup.website_url && (
              <a href={startup.website_url} target="_blank" rel="noopener noreferrer" className="text-xs text-accent hover:text-accent-hover transition">Website &rarr;</a>
            )}
            {startup.linkedin_url && (
              <a href={startup.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-xs text-accent hover:text-accent-hover transition">LinkedIn</a>
            )}
            {startup.twitter_url && (
              <a href={startup.twitter_url} target="_blank" rel="noopener noreferrer" className="text-xs text-accent hover:text-accent-hover transition">Twitter/X</a>
            )}
            {startup.crunchbase_url && (
              <a href={startup.crunchbase_url} target="_blank" rel="noopener noreferrer" className="text-xs text-accent hover:text-accent-hover transition">Crunchbase</a>
            )}
          </div>
        </div>
      </div>

      {/* Scores Overview */}
      <section className="mb-12">
        <h2 className="font-serif text-xl text-text-primary mb-6">Scores Overview</h2>
        <ScoreComparison aiScore={startup.ai_score} expertScore={startup.expert_score} userScore={startup.user_score} />
      </section>

      {/* AI Analysis */}
      {startup.ai_review && (
        <section className="mb-12">
          <h2 className="font-serif text-xl text-text-primary mb-6">AI Analysis</h2>
          <div className="rounded border border-border bg-surface p-6 space-y-6">
            <div>
              <h3 className="text-sm font-medium text-text-primary mb-2">Investment Thesis</h3>
              <p className="text-sm text-text-secondary leading-relaxed">{startup.ai_review.investment_thesis}</p>
            </div>

            <div>
              <h3 className="text-sm font-medium text-text-primary mb-4">Dimension Breakdown</h3>
              <div className="space-y-4">
                {startup.ai_review.dimension_scores.map((ds) => (
                  <div key={ds.dimension_name}>
                    <ScoreBar score={ds.score} label={ds.dimension_name} />
                    <p className="text-xs text-text-tertiary mt-1 ml-51 leading-relaxed">{ds.reasoning}</p>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h3 className="text-sm font-medium text-text-primary mb-2">Key Risks</h3>
              <p className="text-sm text-text-secondary leading-relaxed">{startup.ai_review.key_risks}</p>
            </div>

            <div>
              <h3 className="text-sm font-medium text-text-primary mb-2">Verdict</h3>
              <p className="text-sm text-text-primary font-medium leading-relaxed">{startup.ai_review.verdict}</p>
            </div>

            <p className="text-xs text-text-tertiary">AI analysis generated {new Date(startup.ai_review.created_at).toLocaleDateString()}</p>
          </div>
        </section>
      )}

      {/* Score Timeline */}
      {startup.score_history.length > 0 && (
        <section className="mb-12">
          <h2 className="font-serif text-xl text-text-primary mb-6">Score History</h2>
          <div className="rounded border border-border bg-surface p-6">
            <ScoreTimeline history={startup.score_history} />
          </div>
        </section>
      )}

      {/* Dimension Radar */}
      {startup.score_history.some((h) => h.dimensions_json) && (
        <section className="mb-12">
          <h2 className="font-serif text-xl text-text-primary mb-6">Dimension Comparison</h2>
          <div className="rounded border border-border bg-surface p-6">
            <DimensionRadar history={startup.score_history} />
          </div>
        </section>
      )}

      {/* Founders */}
      {startup.founders && startup.founders.length > 0 && (
        <section className="mb-12">
          <h2 className="font-serif text-xl text-text-primary mb-6">Founders</h2>
          <div className="grid grid-cols-2 gap-4">
            {startup.founders.map((f, i) => (
              <div key={i} className="rounded border border-border p-4 flex items-center gap-4">
                <div className="w-10 h-10 rounded-full bg-background border border-border flex items-center justify-center text-text-tertiary font-serif">
                  {f.name.charAt(0)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-text-primary">{f.name}</p>
                  {f.title && <p className="text-xs text-text-tertiary">{f.title}</p>}
                </div>
                {f.linkedin_url && (
                  <a href={f.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-xs text-accent hover:text-accent-hover transition shrink-0">
                    LinkedIn &rarr;
                  </a>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Funding History */}
      {startup.funding_rounds && startup.funding_rounds.length > 0 && (
        <section className="mb-12">
          <h2 className="font-serif text-xl text-text-primary mb-6">Funding History</h2>
          <div className="rounded border border-border overflow-hidden bg-surface">
            <table className="w-full text-sm">
              <thead className="bg-background">
                <tr>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium text-xs">Round</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium text-xs">Amount</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium text-xs">Date</th>
                  <th className="text-left px-4 py-3 text-text-tertiary font-medium text-xs">Lead Investor</th>
                </tr>
              </thead>
              <tbody>
                {startup.funding_rounds.map((fr, i) => (
                  <tr key={i} className="border-t border-border">
                    <td className="px-4 py-3 text-text-primary">{fr.round_name}</td>
                    <td className="px-4 py-3 text-text-secondary">{fr.amount || "—"}</td>
                    <td className="px-4 py-3 text-text-secondary">{fr.date || "—"}</td>
                    <td className="px-4 py-3 text-text-secondary">{fr.lead_investor || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Company Intel */}
      {(startup.competitors || startup.tech_stack || startup.key_metrics) && (
        <section className="mb-12">
          <h2 className="font-serif text-xl text-text-primary mb-6">Company Intel</h2>
          <div className="space-y-4">
            {startup.key_metrics && (
              <div className="rounded border border-border bg-surface p-4">
                <h3 className="text-xs font-medium text-text-tertiary mb-2">Key Metrics</h3>
                <p className="text-sm text-text-secondary">{startup.key_metrics}</p>
              </div>
            )}
            {startup.competitors && (
              <div className="rounded border border-border bg-surface p-4">
                <h3 className="text-xs font-medium text-text-tertiary mb-2">Competitive Landscape</h3>
                <p className="text-sm text-text-secondary">{startup.competitors}</p>
              </div>
            )}
            {startup.tech_stack && (
              <div className="rounded border border-border bg-surface p-4">
                <h3 className="text-xs font-medium text-text-tertiary mb-2">Technology</h3>
                <p className="text-sm text-text-secondary">{startup.tech_stack}</p>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Media Coverage */}
      {startup.media.length > 0 && (
        <section className="mb-12">
          <h2 className="font-serif text-xl text-text-primary mb-6">Media Coverage</h2>
          <div className="space-y-3">
            {startup.media.map((m) => (
              <a key={m.id} href={m.url} target="_blank" rel="noopener noreferrer"
                className="block rounded border border-border bg-surface p-4 hover:border-text-tertiary transition">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-text-primary">{m.title}</p>
                    <p className="text-xs text-text-tertiary mt-1">{m.source} &middot; {m.media_type.replace("_", " ")}</p>
                  </div>
                  {m.published_at && (
                    <span className="text-xs text-text-tertiary">{new Date(m.published_at).toLocaleDateString()}</span>
                  )}
                </div>
              </a>
            ))}
          </div>
        </section>
      )}

      {/* Reviews */}
      <section className="mb-12">
        <h2 className="font-serif text-xl text-text-primary mb-6">Expert Reviews</h2>
        <p className="text-text-tertiary text-sm">No expert reviews yet.</p>
      </section>
      <section className="mb-12">
        <h2 className="font-serif text-xl text-text-primary mb-6">Community Reviews</h2>
        <p className="text-text-tertiary text-sm">No community reviews yet.</p>
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts frontend/app/startups/[slug]/page.tsx
git commit -m "feat: public startup detail with AI analysis, founders, funding, company intel"
```

---

### Task 10: Default Template Seed + Scout Chat Persistence Fix

Seed the default DD template and fix the remaining scout chat bugs.

**Files:**
- Modify: `backend/app/db/seed.py` (or wherever seeding happens — check if it exists)
- Modify: `admin/app/scout/page.tsx`

- [ ] **Step 1: Check if seed script exists and add default template**

Run: `ls /Users/leemosbacker/acutal/backend/app/db/`

If a seed file exists, add the default template to it. If not, create a migration or a seed endpoint.

The simplest approach: add a startup endpoint or put it in the migration. Add to the Alembic migration's `upgrade()` function (or create a new migration):

```python
# In the enrichment migration file, add to upgrade():
    # Seed default DD template
    op.execute("""
        INSERT INTO due_diligence_templates (id, name, slug, description)
        VALUES (
            'a0000000-0000-0000-0000-000000000001',
            'Default',
            'default',
            'Standard VC due diligence template for evaluating startups across key dimensions'
        )
        ON CONFLICT (name) DO NOTHING;
    """)

    op.execute("""
        INSERT INTO template_dimensions (id, template_id, dimension_name, dimension_slug, weight, sort_order)
        VALUES
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Market Opportunity', 'market-opportunity', 1.2, 0),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Team Strength', 'team-strength', 1.3, 1),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Product & Technology', 'product-technology', 1.1, 2),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Traction & Metrics', 'traction-metrics', 1.2, 3),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Business Model', 'business-model', 1.0, 4),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Competitive Moat', 'competitive-moat', 1.0, 5),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Financials & Unit Economics', 'financials-unit-economics', 0.9, 6),
            (gen_random_uuid(), 'a0000000-0000-0000-0000-000000000001', 'Timing & Market Readiness', 'timing-market-readiness', 0.8, 7)
        ON CONFLICT DO NOTHING;
    """)
```

- [ ] **Step 2: Fix scout chat localStorage persistence**

In `admin/app/scout/page.tsx`, the localStorage persistence code was being added (from the earlier session). Ensure these changes are in place:

Add `STORAGE_KEY` constant, `useEffect` for loading from localStorage on mount, and `useEffect` for saving to localStorage whenever `messages` or `addedMessages` change. Also add a "Clear chat" button in the header. (See the edits from earlier in this session that were staged but not committed — verify they're in the file.)

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/ admin/app/scout/page.tsx
git commit -m "feat: seed default DD template, fix scout chat persistence"
```

---

### Task 11: Verify and Deploy

Build, run migrations, and test the full pipeline.

- [ ] **Step 1: Run migrations on EC2**

```bash
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i /Users/leemosbacker/.ssh/acutal-deploy.pem ec2-user@18.212.88.189
cd ~/acutal
git pull
cd backend
source .venv/bin/activate  # or however the venv is set up
alembic upgrade head
```

- [ ] **Step 2: Rebuild and deploy services sequentially**

```bash
# On EC2, build one at a time to avoid OOM
docker compose build backend
docker compose up -d backend
docker compose build admin
docker compose up -d admin
docker compose build frontend
docker compose up -d frontend
```

- [ ] **Step 3: Test the enrichment pipeline end-to-end**

1. Go to http://18.212.88.189:3001 (admin panel)
2. Use Scout to find startups (e.g., "Find YC W25 AI startups")
3. Verify duplicates show as grayed out
4. Select and add new startups to triage
5. Go to Triage, approve a startup
6. Go to that startup's detail page — should show "Enriching..."
7. Wait 30-60 seconds, refresh — should show "Enriched" with full AI memo, founders, funding, company intel
8. Go to the public frontend (http://18.212.88.189:3000) and view the startup — should show AI Analysis section

- [ ] **Step 4: Test manual enrichment trigger**

1. Go to any existing startup in admin
2. Click "Run AI Enrichment"
3. Should show "Enriching..." and poll automatically
4. After completion, all sections should populate

- [ ] **Step 5: Commit final state**

```bash
git add -A
git commit -m "feat: startup enrichment pipeline — complete implementation"
```
