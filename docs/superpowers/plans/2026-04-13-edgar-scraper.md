# EDGAR SEC Filing Scraper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automated batch pipeline that scrapes SEC EDGAR for Form D, S-1, and 10-K filings, matches them to startups in our database, and extracts funding round data to supplement Perplexity-sourced data.

**Architecture:** Three-layer system — EDGAR Client (HTTP), EDGAR Processor (parsing + matching), EDGAR Batch Worker (orchestration). Mirrors the existing BatchJob/BatchJobStep pattern with `SELECT FOR UPDATE SKIP LOCKED` atomic claiming, 4 concurrent workers, and pause/resume. Admin UI as new "EDGAR" tab in admin panel.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, httpx, xml.etree.ElementTree, Anthropic Python SDK, Next.js 14 (admin panel), TypeScript, Tailwind CSS.

---

## File Structure

### Backend — New Files
| File | Responsibility |
|------|---------------|
| `backend/app/models/edgar_job.py` | EdgarJob + EdgarJobStep SQLAlchemy models |
| `backend/app/services/edgar.py` | EDGAR HTTP client — search, fetch filings, download documents |
| `backend/app/services/edgar_processor.py` | Parsing (Form D XML, S-1/10-K via Claude), company matching, merge logic |
| `backend/app/services/edgar_worker.py` | Batch worker — step executors, worker loop, progress tracking |
| `backend/app/api/admin_edgar.py` | Admin API endpoints — start/pause/resume/cancel, progress, logs |
| `backend/alembic/versions/f1a2b3c4d5e6_edgar_tables.py` | Migration: new tables + columns |

### Backend — Modified Files
| File | Change |
|------|--------|
| `backend/app/config.py` | Add `anthropic_api_key` and `edgar_user_agent` settings |
| `backend/app/models/startup.py` | Add `sec_cik` and `edgar_last_scanned_at` columns |
| `backend/app/models/funding_round.py` | Add `data_source` column |
| `backend/app/main.py` | Register `admin_edgar` router |

### Frontend — New Files
| File | Responsibility |
|------|---------------|
| `admin/app/edgar/page.tsx` | EDGAR admin page — controls, progress, tabs, activity log |

### Frontend — Modified Files
| File | Change |
|------|--------|
| `admin/lib/api.ts` | Add EDGAR API client methods |
| `admin/components/Sidebar.tsx` | Add "EDGAR" nav item |

---

### Task 1: Database Models & Migration

**Files:**
- Create: `backend/app/models/edgar_job.py`
- Modify: `backend/app/models/startup.py`
- Modify: `backend/app/models/funding_round.py`
- Create: `backend/alembic/versions/f1a2b3c4d5e6_edgar_tables.py`

- [ ] **Step 1: Create EdgarJob and EdgarJobStep models**

Create `backend/app/models/edgar_job.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class EdgarJobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class EdgarJobPhase(str, enum.Enum):
    resolving_ciks = "resolving_ciks"
    fetching_filings = "fetching_filings"
    processing_filings = "processing_filings"
    complete = "complete"


class EdgarStepType(str, enum.Enum):
    resolve_cik = "resolve_cik"
    fetch_filings = "fetch_filings"
    process_filing = "process_filing"


class EdgarStepStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class EdgarJob(Base):
    __tablename__ = "edgar_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_mode: Mapped[str] = mapped_column(Text, default="full")  # "full" or "new_only"
    status: Mapped[EdgarJobStatus] = mapped_column(default=EdgarJobStatus.pending)
    progress_summary: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default=text("'{}'::jsonb")
    )
    current_phase: Mapped[EdgarJobPhase] = mapped_column(
        default=EdgarJobPhase.resolving_ciks
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    steps: Mapped[list["EdgarJobStep"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class EdgarJobStep(Base):
    __tablename__ = "edgar_job_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("edgar_jobs.id", ondelete="CASCADE")
    )
    step_type: Mapped[EdgarStepType]
    status: Mapped[EdgarStepStatus] = mapped_column(default=EdgarStepStatus.pending)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped["EdgarJob"] = relationship(back_populates="steps")
```

- [ ] **Step 2: Add sec_cik and edgar_last_scanned_at to Startup model**

In `backend/app/models/startup.py`, add after line 97 (`enriched_at` field):

```python
    sec_cik: Mapped[str | None] = mapped_column(String(20), nullable=True)
    edgar_last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 3: Add data_source to StartupFundingRound model**

In `backend/app/models/funding_round.py`, add after the `sort_order` field (line 24):

```python
    data_source: Mapped[str] = mapped_column(String(20), nullable=False, default="perplexity", server_default="perplexity")
```

- [ ] **Step 4: Create Alembic migration**

Create `backend/alembic/versions/f1a2b3c4d5e6_edgar_tables.py`:

```python
"""EDGAR scraper tables and columns

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "f1a2b3c4d5e6"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add columns to startups
    op.add_column("startups", sa.Column("sec_cik", sa.String(20), nullable=True))
    op.add_column("startups", sa.Column("edgar_last_scanned_at", sa.DateTime(timezone=True), nullable=True))

    # Add data_source to startup_funding_rounds
    op.add_column(
        "startup_funding_rounds",
        sa.Column("data_source", sa.String(20), nullable=False, server_default="perplexity"),
    )

    # Create edgar_jobs table
    op.create_table(
        "edgar_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("scan_mode", sa.Text(), nullable=False, server_default="full"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("progress_summary", JSON, nullable=False, server_default="{}"),
        sa.Column("current_phase", sa.String(30), nullable=False, server_default="resolving_ciks"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create edgar_job_steps table
    op.create_table(
        "edgar_job_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("edgar_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("params", JSON, nullable=False, server_default="{}"),
        sa.Column("result", JSON, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_edgar_job_steps_job_id_status", "edgar_job_steps", ["job_id", "status"])


def downgrade() -> None:
    op.drop_table("edgar_job_steps")
    op.drop_table("edgar_jobs")
    op.drop_column("startup_funding_rounds", "data_source")
    op.drop_column("startups", "edgar_last_scanned_at")
    op.drop_column("startups", "sec_cik")
```

- [ ] **Step 5: Run migration**

```bash
cd backend && alembic upgrade head
```

Expected: Migration applies cleanly.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/edgar_job.py backend/app/models/startup.py backend/app/models/funding_round.py backend/alembic/versions/f1a2b3c4d5e6_edgar_tables.py
git commit -m "feat: add EDGAR job models, migration, sec_cik and data_source columns"
```

---

### Task 2: Config Settings

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add anthropic_api_key and edgar_user_agent to Settings**

In `backend/app/config.py`, add two new fields to the `Settings` class after `perplexity_api_key`:

```python
    anthropic_api_key: str = ""
    edgar_user_agent: str = "Acutal admin@deepthesis.org"
```

These read from `ACUTAL_ANTHROPIC_API_KEY` and `ACUTAL_EDGAR_USER_AGENT` environment variables (via the `ACUTAL_` env prefix).

- [ ] **Step 2: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: add anthropic_api_key and edgar_user_agent config settings"
```

---

### Task 3: EDGAR HTTP Client

**Files:**
- Create: `backend/app/services/edgar.py`

This is the pure HTTP layer — no business logic, no database access. Talks to SEC EDGAR APIs with rate limiting.

- [ ] **Step 1: Create EDGAR client**

Create `backend/app/services/edgar.py`:

```python
"""EDGAR HTTP client — talks to SEC EDGAR REST APIs.

Pure HTTP, no business logic. Handles rate limiting (150ms between requests).
SEC requires User-Agent header with company name and email.
"""
import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# SEC asks for max 10 req/s; we use 150ms delay to be safe
_RATE_LIMIT_DELAY = 0.15
_last_request_time = 0.0


def _headers() -> dict[str, str]:
    return {
        "User-Agent": settings.edgar_user_agent,
        "Accept": "application/json",
    }


async def _rate_limited_get(url: str, accept: str = "application/json") -> httpx.Response:
    """GET with rate limiting. Raises on non-2xx."""
    global _last_request_time
    now = asyncio.get_event_loop().time()
    elapsed = now - _last_request_time
    if elapsed < _RATE_LIMIT_DELAY:
        await asyncio.sleep(_RATE_LIMIT_DELAY - elapsed)
    _last_request_time = asyncio.get_event_loop().time()

    headers = _headers()
    headers["Accept"] = accept

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp


@dataclass
class EdgarCompany:
    """A company result from EDGAR search."""
    name: str
    cik: str
    state: str | None
    sic: str | None
    sic_description: str | None


@dataclass
class EdgarFiling:
    """A filing from the EDGAR filing index."""
    accession_number: str
    filing_type: str
    filing_date: str
    primary_document: str
    description: str


async def search_company(name: str) -> list[EdgarCompany]:
    """Search EDGAR for companies matching the given name.

    Returns a list of EdgarCompany results with CIK numbers.
    """
    url = f"https://efts.sec.gov/LATEST/search-index?q={httpx.QueryParams({'q': name}).get('q')}&dateRange=custom&startdt=2000-01-01&enddt=2026-12-31"
    # EDGAR full-text search returns HTML; use the company search endpoint instead
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={httpx.URL('', params={'company': name}).params.get('company')}&CIK=&type=&dateb=&owner=include&count=40&search_text=&action=getcompany&output=atom"

    try:
        resp = await _rate_limited_get(url, accept="application/atom+xml")
    except httpx.HTTPStatusError as e:
        logger.warning(f"EDGAR company search failed for '{name}': {e}")
        return []

    # Parse Atom XML
    import xml.etree.ElementTree as ET
    root = ET.fromstring(resp.text)
    ns = {"atom": "http://www.w3.org/2005/Atom", "edgar": "http://www.sec.gov/cgi-bin/browse-edgar"}

    results = []
    for entry in root.findall("atom:entry", ns):
        content = entry.find("atom:content", ns)
        if content is None:
            continue

        cik_el = content.find(".//edgar:cik", ns)
        name_el = content.find(".//edgar:conformed-name", ns)
        state_el = content.find(".//edgar:state", ns)
        sic_el = content.find(".//edgar:assigned-sic", ns)
        sic_desc_el = content.find(".//edgar:assigned-sic-desc", ns)

        if cik_el is not None and name_el is not None:
            results.append(EdgarCompany(
                name=name_el.text or "",
                cik=cik_el.text or "",
                state=state_el.text if state_el is not None else None,
                sic=sic_el.text if sic_el is not None else None,
                sic_description=sic_desc_el.text if sic_desc_el is not None else None,
            ))

    return results


async def get_filings(cik: str) -> list[EdgarFiling]:
    """Get all filings for a CIK number.

    Returns filings sorted by date (newest first). Filters to Form D, S-1, 10-K.
    """
    padded_cik = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"

    try:
        resp = await _rate_limited_get(url)
    except httpx.HTTPStatusError as e:
        logger.warning(f"EDGAR filings fetch failed for CIK {cik}: {e}")
        return []

    data = resp.json()
    recent = data.get("filings", {}).get("recent", {})

    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    descriptions = recent.get("primaryDocDescription", [])

    target_forms = {"D", "D/A", "S-1", "S-1/A", "10-K", "10-K/A"}

    filings = []
    for i in range(len(forms)):
        if forms[i] in target_forms:
            filings.append(EdgarFiling(
                accession_number=accessions[i] if i < len(accessions) else "",
                filing_type=forms[i],
                filing_date=dates[i] if i < len(dates) else "",
                primary_document=primary_docs[i] if i < len(primary_docs) else "",
                description=descriptions[i] if i < len(descriptions) else "",
            ))

    return filings


async def download_filing(cik: str, accession_number: str, document: str) -> str:
    """Download a filing document (XML for Form D, HTML for S-1/10-K).

    Returns the raw document text.
    """
    # Accession numbers need dashes removed for the URL path
    accession_path = accession_number.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_path}/{document}"

    resp = await _rate_limited_get(url, accept="*/*")
    return resp.text


async def get_company_info(cik: str) -> dict:
    """Get basic company info for a CIK (name, SIC, state, recent filings summary).

    Used for Claude verification during company matching.
    """
    padded_cik = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"

    try:
        resp = await _rate_limited_get(url)
    except httpx.HTTPStatusError:
        return {}

    data = resp.json()
    recent = data.get("filings", {}).get("recent", {})
    recent_forms = recent.get("form", [])[:10]
    recent_dates = recent.get("filingDate", [])[:10]

    return {
        "name": data.get("name", ""),
        "cik": cik,
        "sic": data.get("sic", ""),
        "sic_description": data.get("sicDescription", ""),
        "state_of_incorporation": data.get("stateOfIncorporation", ""),
        "state": data.get("addresses", {}).get("business", {}).get("stateOrCountry", ""),
        "recent_filings": [
            {"form": recent_forms[i], "date": recent_dates[i]}
            for i in range(min(len(recent_forms), len(recent_dates)))
        ],
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/edgar.py
git commit -m "feat: add EDGAR HTTP client with company search, filings fetch, and document download"
```

---

### Task 4: EDGAR Processor — Form D XML Parser

**Files:**
- Create: `backend/app/services/edgar_processor.py`

- [ ] **Step 1: Create edgar_processor.py with Form D parsing**

Create `backend/app/services/edgar_processor.py`:

```python
"""EDGAR Processor — parses filings and matches companies.

Form D: Direct XML parsing (no LLM needed).
S-1/10-K: Claude API extraction (unstructured HTML).
Company matching: CIK lookup + Claude verification.
"""
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.funding_round import StartupFundingRound
from app.models.startup import Startup
from app.services import edgar

logger = logging.getLogger(__name__)


@dataclass
class FormDData:
    """Structured data extracted from a Form D filing."""
    total_amount_sold: float | None = None
    total_amount_remaining: float | None = None
    number_of_investors: int | None = None
    min_investment_accepted: float | None = None
    date_of_first_sale: str | None = None
    federal_exemptions: list[str] = field(default_factory=list)
    issuer_name: str | None = None


@dataclass
class FundingRoundData:
    """Normalized funding round data from any filing type."""
    round_name: str | None = None
    amount: str | None = None
    date: str | None = None
    pre_money_valuation: str | None = None
    post_money_valuation: str | None = None
    lead_investor: str | None = None
    other_investors: str | None = None
    filing_type: str | None = None
    accession_number: str | None = None


def parse_form_d(xml_text: str) -> FormDData:
    """Parse Form D XML and extract funding data.

    Form D is a structured XML document filed for Regulation D offerings.
    """
    root = ET.fromstring(xml_text)

    # Form D uses various namespaces; strip them for easier access
    # Remove namespace prefixes
    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]
        for key in list(elem.attrib):
            if "}" in key:
                new_key = key.split("}", 1)[1]
                elem.attrib[new_key] = elem.attrib.pop(key)

    data = FormDData()

    # Issuer name
    issuer = root.find(".//issuerName") or root.find(".//entityName") or root.find(".//nameOfIssuer")
    if issuer is not None and issuer.text:
        data.issuer_name = issuer.text.strip()

    # Total amount sold
    for tag in ["totalAmountSold", "aggregateNetAssetValue"]:
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            try:
                data.total_amount_sold = float(el.text.replace(",", "").replace("$", ""))
            except ValueError:
                pass
            break

    # Total amount remaining
    el = root.find(".//totalRemaining")
    if el is not None and el.text:
        try:
            data.total_amount_remaining = float(el.text.replace(",", "").replace("$", ""))
        except ValueError:
            pass

    # Number of investors
    el = root.find(".//totalNumberAlreadyInvested")
    if el is not None and el.text:
        try:
            data.number_of_investors = int(el.text)
        except ValueError:
            pass

    # Minimum investment accepted
    el = root.find(".//minimumInvestmentAccepted")
    if el is not None and el.text:
        try:
            data.min_investment_accepted = float(el.text.replace(",", "").replace("$", ""))
        except ValueError:
            pass

    # Date of first sale
    el = root.find(".//dateOfFirstSale")
    if el is not None:
        value_el = el.find("value") or el
        if value_el.text:
            data.date_of_first_sale = value_el.text.strip()

    # Federal exemptions
    for el in root.findall(".//federalExemptionsExclusions"):
        if el.text:
            data.federal_exemptions.append(el.text.strip())

    return data


def _format_amount(value: float) -> str:
    """Format a dollar amount as a human-readable string."""
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:.0f}"


def form_d_to_funding_round(data: FormDData, filing: edgar.EdgarFiling) -> FundingRoundData:
    """Convert Form D data into a normalized FundingRoundData."""
    amount = None
    if data.total_amount_sold is not None and data.total_amount_sold > 0:
        amount = _format_amount(data.total_amount_sold)

    return FundingRoundData(
        round_name=None,  # Form D doesn't label rounds
        amount=amount,
        date=data.date_of_first_sale or filing.filing_date,
        filing_type=filing.filing_type,
        accession_number=filing.accession_number,
    )


async def _call_claude(system_prompt: str, user_prompt: str) -> str:
    """Call Claude API and return the text response."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"]


async def parse_s1_html(html_text: str, company_name: str) -> list[FundingRoundData]:
    """Parse S-1 filing HTML using Claude to extract funding history.

    Extracts relevant sections first, then sends to Claude for structured parsing.
    """
    # Extract relevant sections (cap at ~50K chars to stay within context)
    sections_to_find = [
        r"use of proceeds",
        r"capitalization",
        r"dilution",
        r"principal stockholders",
        r"description of capital stock",
        r"selected financial data",
    ]

    extracted = _extract_html_sections(html_text, sections_to_find, max_chars=50000)
    if not extracted:
        # Fall back to first 30K chars
        extracted = html_text[:30000]

    system = """You are a financial document parser. Extract funding round data from SEC S-1 filings.

Return a JSON array of funding rounds. Each round should have:
- round_name: e.g. "Series A", "Series B", "IPO" (string or null)
- amount: dollar amount as string e.g. "$50M", "$120M" (string or null)
- date: YYYY-MM-DD format (string or null)
- pre_money_valuation: dollar amount as string e.g. "$200M" (string or null)
- post_money_valuation: dollar amount as string e.g. "$250M" (string or null)
- lead_investor: name of lead investor (string or null)
- other_investors: comma-separated investor names (string or null)

Return ONLY the JSON array, no other text. If no funding rounds found, return [].
Mark estimated valuations with ~ prefix (e.g. "~$200M")."""

    user = f"Company: {company_name}\n\nExtracted S-1 sections:\n\n{extracted}"

    try:
        response = await _call_claude(system, user)
        import json
        # Extract JSON from response
        json_match = re.search(r"\[.*\]", response, re.DOTALL)
        if json_match:
            rounds_raw = json.loads(json_match.group(0))
            return [
                FundingRoundData(
                    round_name=r.get("round_name"),
                    amount=r.get("amount"),
                    date=r.get("date"),
                    pre_money_valuation=r.get("pre_money_valuation"),
                    post_money_valuation=r.get("post_money_valuation"),
                    lead_investor=r.get("lead_investor"),
                    other_investors=r.get("other_investors"),
                    filing_type="S-1",
                )
                for r in rounds_raw
            ]
    except Exception as e:
        logger.error(f"Claude S-1 parsing failed for {company_name}: {e}")

    return []


async def parse_10k_html(html_text: str, company_name: str) -> dict:
    """Parse 10-K filing HTML using Claude to extract financial metrics.

    Returns dict with: revenue, operating_income, employee_count, etc.
    """
    sections_to_find = [
        r"selected financial data",
        r"results of operations",
        r"financial statements",
        r"employees",
        r"business",
    ]

    extracted = _extract_html_sections(html_text, sections_to_find, max_chars=50000)
    if not extracted:
        extracted = html_text[:30000]

    system = """You are a financial document parser. Extract key financial metrics from SEC 10-K filings.

Return a JSON object with:
- revenue: latest annual revenue as string e.g. "$1.2B" (string or null)
- operating_income: as string (string or null)
- net_income: as string (string or null)
- employee_count: as string e.g. "5,000" (string or null)
- revenue_growth_yoy: year-over-year growth as string e.g. "25%" (string or null)

Return ONLY the JSON object, no other text."""

    user = f"Company: {company_name}\n\nExtracted 10-K sections:\n\n{extracted}"

    try:
        response = await _call_claude(system, user)
        import json
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception as e:
        logger.error(f"Claude 10-K parsing failed for {company_name}: {e}")

    return {}


def _extract_html_sections(html: str, section_patterns: list[str], max_chars: int = 50000) -> str:
    """Extract named sections from HTML by heading patterns.

    Looks for headings matching the patterns and extracts content until the next heading.
    """
    import re

    # Remove script/style tags
    clean = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags but keep text
    text = re.sub(r"<[^>]+>", " ", clean)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Find sections by pattern
    extracted_parts = []
    for pattern in section_patterns:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        for match in matches:
            start = max(0, match.start() - 100)
            # Take up to 8000 chars after the heading
            end = min(len(text), match.end() + 8000)
            extracted_parts.append(text[start:end])

    combined = "\n\n---\n\n".join(extracted_parts)
    return combined[:max_chars]


async def verify_company_match(
    startup_name: str,
    startup_description: str | None,
    startup_website: str | None,
    startup_location: str | None,
    edgar_company: dict,
) -> bool:
    """Use Claude to verify if an EDGAR entity matches our startup.

    Returns True if Claude confirms the match.
    """
    system = "You are a company identity verification assistant. Determine if two company records refer to the same entity."

    user = f"""Our startup:
- Name: {startup_name}
- Description: {startup_description or 'N/A'}
- Website: {startup_website or 'N/A'}
- Location: {startup_location or 'N/A'}

SEC EDGAR entity:
- Name: {edgar_company.get('name', 'N/A')}
- State of incorporation: {edgar_company.get('state_of_incorporation', 'N/A')}
- SIC code: {edgar_company.get('sic', 'N/A')} ({edgar_company.get('sic_description', 'N/A')})
- Recent filings: {edgar_company.get('recent_filings', [])[:5]}

Are these the same company? Answer YES or NO with one sentence of reasoning."""

    try:
        response = await _call_claude(system, user)
        return response.strip().upper().startswith("YES")
    except Exception as e:
        logger.error(f"Claude verification failed for {startup_name}: {e}")
        return False


async def resolve_cik(
    db: AsyncSession,
    startup: Startup,
) -> str | None:
    """Resolve SEC CIK for a startup. Returns CIK string or None.

    1. Search EDGAR by company name
    2. Filter candidates by state/date
    3. Claude verification for uncertain matches
    4. Store CIK on match
    """
    # Search EDGAR
    candidates = await edgar.search_company(startup.name)
    if not candidates:
        return None

    # Quick filter: if only one result, verify it
    # If multiple, filter by state first
    if len(candidates) > 1 and startup.location_state:
        state_matches = [c for c in candidates if c.state and c.state.upper() == startup.location_state.upper()]
        if state_matches:
            candidates = state_matches

    # Claude verification for top candidates (max 3)
    startup_location = None
    if startup.location_city and startup.location_state:
        startup_location = f"{startup.location_city}, {startup.location_state}"
    elif startup.location_city:
        startup_location = startup.location_city

    for candidate in candidates[:3]:
        company_info = await edgar.get_company_info(candidate.cik)
        is_match = await verify_company_match(
            startup_name=startup.name,
            startup_description=startup.description,
            startup_website=startup.website_url,
            startup_location=startup_location,
            edgar_company=company_info,
        )
        if is_match:
            return candidate.cik

    return None


def _parse_amount_to_float(amount_str: str | None) -> float | None:
    """Parse a dollar amount string like '$50M' or '$1.2B' to float."""
    if not amount_str:
        return None
    clean = amount_str.replace("~", "").replace("$", "").replace(",", "").strip()
    multiplier = 1
    if clean.upper().endswith("B"):
        multiplier = 1_000_000_000
        clean = clean[:-1]
    elif clean.upper().endswith("M"):
        multiplier = 1_000_000
        clean = clean[:-1]
    elif clean.upper().endswith("K"):
        multiplier = 1_000
        clean = clean[:-1]
    try:
        return float(clean) * multiplier
    except ValueError:
        return None


def _dates_within_days(date1: str | None, date2: str | None, days: int = 90) -> bool:
    """Check if two date strings (YYYY-MM-DD) are within N days of each other."""
    if not date1 or not date2:
        return False
    try:
        d1 = datetime.strptime(date1[:10], "%Y-%m-%d")
        d2 = datetime.strptime(date2[:10], "%Y-%m-%d")
        return abs((d1 - d2).days) <= days
    except ValueError:
        return False


def _amounts_within_tolerance(a1: float | None, a2: float | None, tolerance: float = 0.2) -> bool:
    """Check if two amounts are within tolerance % of each other."""
    if a1 is None or a2 is None or a1 == 0:
        return False
    return abs(a1 - a2) / max(a1, a2) <= tolerance


async def merge_funding_round(
    db: AsyncSession,
    startup_id: str,
    edgar_round: FundingRoundData,
) -> dict:
    """Merge an EDGAR-extracted funding round into existing startup data.

    Match by: date within 90 days + amount within 20%.
    EDGAR wins for: amount, pre/post_money_valuation, date.
    Perplexity wins for: lead_investor, other_investors, round_name.

    Returns dict with action taken: "updated", "created", or "skipped".
    """
    result = await db.execute(
        select(StartupFundingRound)
        .where(StartupFundingRound.startup_id == startup_id)
    )
    existing_rounds = result.scalars().all()

    edgar_amount = _parse_amount_to_float(edgar_round.amount)

    # Try to match existing round
    best_match = None
    for existing in existing_rounds:
        existing_amount = _parse_amount_to_float(existing.amount)

        date_match = _dates_within_days(edgar_round.date, existing.date)
        amount_match = _amounts_within_tolerance(edgar_amount, existing_amount)

        if date_match and amount_match:
            best_match = existing
            break
        # Looser match: just date if amounts are both present
        if date_match and edgar_amount and existing_amount:
            best_match = existing

    if best_match:
        # Update existing round — EDGAR wins for financials
        if edgar_round.amount:
            best_match.amount = edgar_round.amount
        if edgar_round.date:
            best_match.date = edgar_round.date
        if edgar_round.pre_money_valuation:
            best_match.pre_money_valuation = edgar_round.pre_money_valuation
        if edgar_round.post_money_valuation:
            best_match.post_money_valuation = edgar_round.post_money_valuation
        # Don't overwrite round_name, lead_investor, other_investors from Perplexity
        if not best_match.round_name and edgar_round.round_name:
            best_match.round_name = edgar_round.round_name
        if not best_match.lead_investor and edgar_round.lead_investor:
            best_match.lead_investor = edgar_round.lead_investor
        if not best_match.other_investors and edgar_round.other_investors:
            best_match.other_investors = edgar_round.other_investors
        best_match.data_source = "edgar"
        return {"action": "updated", "round_name": best_match.round_name}

    # No match — create new round
    if edgar_round.amount:
        # Determine sort order
        max_order = max((r.sort_order for r in existing_rounds), default=-1)
        new_round = StartupFundingRound(
            startup_id=startup_id,
            round_name=edgar_round.round_name or f"Form D ({edgar_round.date or 'undated'})",
            amount=edgar_round.amount,
            date=edgar_round.date,
            pre_money_valuation=edgar_round.pre_money_valuation,
            post_money_valuation=edgar_round.post_money_valuation,
            lead_investor=edgar_round.lead_investor,
            other_investors=edgar_round.other_investors,
            sort_order=max_order + 1,
            data_source="edgar",
        )
        db.add(new_round)
        return {"action": "created", "round_name": new_round.round_name}

    return {"action": "skipped", "reason": "no amount"}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/edgar_processor.py
git commit -m "feat: add EDGAR processor with Form D parser, S-1/10-K Claude parser, company matching, and merge logic"
```

---

### Task 5: EDGAR Batch Worker

**Files:**
- Create: `backend/app/services/edgar_worker.py`

Follows the exact same pattern as `batch_worker.py`: concurrent workers, `SELECT FOR UPDATE SKIP LOCKED`, step executors, pause/resume, progress tracking.

- [ ] **Step 1: Create edgar_worker.py**

Create `backend/app/services/edgar_worker.py`:

```python
"""EDGAR batch worker: processes EDGAR job steps concurrently with rate limiting.

Same architecture as batch_worker.py:
- 4 concurrent workers (lower than batch's 6 — SEC rate limit is the bottleneck)
- Atomic step claiming with SELECT FOR UPDATE SKIP LOCKED
- Step chaining: resolve_cik → fetch_filings → process_filing
- Pause/resume support
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models.edgar_job import (
    EdgarJob,
    EdgarJobPhase,
    EdgarJobStatus,
    EdgarJobStep,
    EdgarStepStatus,
    EdgarStepType,
)
from app.models.startup import Startup
from app.services import edgar
from app.services.edgar_processor import (
    form_d_to_funding_round,
    merge_funding_round,
    parse_form_d,
    parse_s1_html,
    parse_10k_html,
    resolve_cik,
)

logger = logging.getLogger(__name__)

CONCURRENCY = 4

STEP_DELAYS = {
    EdgarStepType.resolve_cik: 1.0,     # Claude API + EDGAR search
    EdgarStepType.fetch_filings: 0.5,    # Single EDGAR API call
    EdgarStepType.process_filing: 1.0,   # EDGAR download + optional Claude
}


async def _get_next_sort_order(db: AsyncSession, job_id) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(EdgarJobStep.sort_order), 0))
        .where(EdgarJobStep.job_id == job_id)
    )
    return (result.scalar() or 0) + 1


async def _update_progress(db: AsyncSession, job: EdgarJob):
    """Recalculate job progress_summary from step data."""
    steps_result = await db.execute(
        select(EdgarJobStep).where(EdgarJobStep.job_id == job.id)
    )
    all_steps = steps_result.scalars().all()

    startups_scanned = 0
    ciks_matched = 0
    filings_found = 0
    filings_processed = 0
    rounds_updated = 0
    rounds_created = 0
    valuations_added = 0

    for step in all_steps:
        if step.step_type == EdgarStepType.resolve_cik and step.status == EdgarStepStatus.completed:
            startups_scanned += 1
            if step.result and step.result.get("cik"):
                ciks_matched += 1
        elif step.step_type == EdgarStepType.fetch_filings and step.status == EdgarStepStatus.completed:
            if step.result:
                filings_found += step.result.get("filings_count", 0)
        elif step.step_type == EdgarStepType.process_filing and step.status == EdgarStepStatus.completed:
            filings_processed += 1
            if step.result:
                if step.result.get("action") == "updated":
                    rounds_updated += 1
                elif step.result.get("action") == "created":
                    rounds_created += 1
                if step.result.get("valuation_added"):
                    valuations_added += 1

    # Count totals by type
    total_resolve = len([s for s in all_steps if s.step_type == EdgarStepType.resolve_cik])
    total_process = len([s for s in all_steps if s.step_type == EdgarStepType.process_filing])

    # Find current step
    current_startup = None
    current_filing = None
    for step in all_steps:
        if step.status == EdgarStepStatus.running:
            if step.params.get("startup_name"):
                current_startup = step.params["startup_name"]
            if step.params.get("filing_type"):
                current_filing = step.params["filing_type"]
            break

    summary = {
        "startups_total": total_resolve,
        "startups_scanned": startups_scanned,
        "ciks_matched": ciks_matched,
        "filings_found": filings_found,
        "filings_total": total_process,
        "filings_processed": filings_processed,
        "rounds_updated": rounds_updated,
        "rounds_created": rounds_created,
        "valuations_added": valuations_added,
    }
    if current_startup:
        summary["current_startup"] = current_startup
    if current_filing:
        summary["current_filing"] = current_filing

    job.progress_summary = summary
    job.updated_at = datetime.now(timezone.utc)

    # Update phase
    has_pending_resolve = any(
        s.step_type == EdgarStepType.resolve_cik and s.status == EdgarStepStatus.pending
        for s in all_steps
    )
    has_pending_fetch = any(
        s.step_type == EdgarStepType.fetch_filings and s.status == EdgarStepStatus.pending
        for s in all_steps
    )
    has_pending_process = any(
        s.step_type == EdgarStepType.process_filing and s.status == EdgarStepStatus.pending
        for s in all_steps
    )

    if has_pending_resolve:
        job.current_phase = EdgarJobPhase.resolving_ciks
    elif has_pending_fetch:
        job.current_phase = EdgarJobPhase.fetching_filings
    elif has_pending_process:
        job.current_phase = EdgarJobPhase.processing_filings
    else:
        job.current_phase = EdgarJobPhase.complete

    await db.commit()


async def _execute_resolve_cik(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute resolve_cik step: search EDGAR + Claude verification."""
    startup_id = step.params["startup_id"]

    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    startup = result.scalar_one_or_none()
    if startup is None:
        step.result = {"error": "Startup not found"}
        raise Exception(f"Startup {startup_id} not found")

    cik = await resolve_cik(db, startup)

    if cik:
        startup.sec_cik = cik
        startup.edgar_last_scanned_at = datetime.now(timezone.utc)
        step.result = {"cik": cik, "startup_name": startup.name}

        # Chain: generate fetch_filings step
        next_order = await _get_next_sort_order(db, job.id)
        fetch_step = EdgarJobStep(
            job_id=job.id,
            step_type=EdgarStepType.fetch_filings,
            params={
                "startup_id": str(startup_id),
                "startup_name": startup.name,
                "cik": cik,
            },
            sort_order=next_order,
        )
        db.add(fetch_step)
        logger.info(f"Resolved CIK {cik} for {startup.name}")
    else:
        startup.edgar_last_scanned_at = datetime.now(timezone.utc)
        step.result = {"cik": None, "startup_name": startup.name}
        logger.info(f"No CIK match for {startup.name}")


async def _execute_fetch_filings(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute fetch_filings step: pull filing index for a CIK."""
    cik = step.params["cik"]
    startup_id = step.params["startup_id"]
    startup_name = step.params["startup_name"]

    filings = await edgar.get_filings(cik)

    # Filter to filings we haven't processed yet
    # Check edgar_last_scanned_at on the startup
    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    startup = result.scalar_one_or_none()

    # For initial scan, process all filings
    # For subsequent scans, we could filter by date — for now, process all
    step.result = {
        "filings_count": len(filings),
        "filing_types": list(set(f.filing_type for f in filings)),
    }

    # Chain: generate process_filing steps
    if filings:
        next_order = await _get_next_sort_order(db, job.id)
        for filing in filings:
            process_step = EdgarJobStep(
                job_id=job.id,
                step_type=EdgarStepType.process_filing,
                params={
                    "startup_id": str(startup_id),
                    "startup_name": startup_name,
                    "cik": cik,
                    "accession_number": filing.accession_number,
                    "filing_type": filing.filing_type,
                    "filing_date": filing.filing_date,
                    "primary_document": filing.primary_document,
                },
                sort_order=next_order,
            )
            db.add(process_step)
            next_order += 1

    logger.info(f"Found {len(filings)} filings for {startup_name} (CIK {cik})")


async def _execute_process_filing(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute process_filing step: download and parse one filing."""
    cik = step.params["cik"]
    startup_id = step.params["startup_id"]
    startup_name = step.params["startup_name"]
    accession = step.params["accession_number"]
    filing_type = step.params["filing_type"]
    filing_date = step.params["filing_date"]
    primary_doc = step.params["primary_document"]

    # Download the filing document
    doc_text = await edgar.download_filing(cik, accession, primary_doc)

    filing_obj = edgar.EdgarFiling(
        accession_number=accession,
        filing_type=filing_type,
        filing_date=filing_date,
        primary_document=primary_doc,
        description="",
    )

    if filing_type in ("D", "D/A"):
        # Form D — XML parse
        form_d_data = parse_form_d(doc_text)
        round_data = form_d_to_funding_round(form_d_data, filing_obj)
        merge_result = await merge_funding_round(db, startup_id, round_data)
        step.result = {
            **merge_result,
            "filing_type": filing_type,
            "amount": round_data.amount,
            "date": round_data.date,
            "valuation_added": bool(round_data.pre_money_valuation or round_data.post_money_valuation),
        }
        logger.info(f"Processed Form D for {startup_name}: {merge_result['action']}")

    elif filing_type in ("S-1", "S-1/A"):
        # S-1 — Claude parse
        rounds = await parse_s1_html(doc_text, startup_name)
        actions = []
        valuations = 0
        for round_data in rounds:
            round_data.accession_number = accession
            merge_result = await merge_funding_round(db, startup_id, round_data)
            actions.append(merge_result)
            if round_data.pre_money_valuation or round_data.post_money_valuation:
                valuations += 1
        step.result = {
            "filing_type": filing_type,
            "rounds_extracted": len(rounds),
            "actions": actions,
            "valuation_added": valuations > 0,
        }
        logger.info(f"Processed S-1 for {startup_name}: {len(rounds)} rounds extracted")

    elif filing_type in ("10-K", "10-K/A"):
        # 10-K — Claude parse for financial metrics
        metrics = await parse_10k_html(doc_text, startup_name)

        # Update startup with extracted metrics if available
        if metrics:
            result = await db.execute(select(Startup).where(Startup.id == startup_id))
            startup = result.scalar_one_or_none()
            if startup:
                if metrics.get("revenue") and not startup.revenue_estimate:
                    startup.revenue_estimate = metrics["revenue"]
                if metrics.get("employee_count") and not startup.employee_count:
                    startup.employee_count = metrics["employee_count"]

        step.result = {
            "filing_type": filing_type,
            "metrics": metrics,
            "valuation_added": False,
        }
        logger.info(f"Processed 10-K for {startup_name}: {metrics}")

    else:
        step.result = {"filing_type": filing_type, "action": "skipped", "reason": f"Unsupported type: {filing_type}"}


STEP_EXECUTORS = {
    EdgarStepType.resolve_cik: _execute_resolve_cik,
    EdgarStepType.fetch_filings: _execute_fetch_filings,
    EdgarStepType.process_filing: _execute_process_filing,
}

# Workers 0-1 prefer resolve_cik, workers 2-3 prefer process_filing
WORKER_PREFERENCES = {
    0: EdgarStepType.resolve_cik,
    1: EdgarStepType.resolve_cik,
    2: EdgarStepType.process_filing,
    3: EdgarStepType.process_filing,
}


async def _claim_next_step(db: AsyncSession, job_id: str, preferred_type: EdgarStepType | None = None) -> EdgarJobStep | None:
    """Atomically claim the next pending step using FOR UPDATE SKIP LOCKED."""
    if preferred_type is not None:
        result = await db.execute(
            select(EdgarJobStep)
            .where(EdgarJobStep.job_id == job_id)
            .where(EdgarJobStep.status == EdgarStepStatus.pending)
            .where(EdgarJobStep.step_type == preferred_type)
            .order_by(EdgarJobStep.sort_order)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        step = result.scalar_one_or_none()
        if step is not None:
            step.status = EdgarStepStatus.running
            await db.commit()
            return step

    # Fallback: any pending step
    result = await db.execute(
        select(EdgarJobStep)
        .where(EdgarJobStep.job_id == job_id)
        .where(EdgarJobStep.status == EdgarStepStatus.pending)
        .order_by(EdgarJobStep.sort_order)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    step = result.scalar_one_or_none()
    if step is not None:
        step.status = EdgarStepStatus.running
        await db.commit()
    return step


async def _worker_loop(job_id: str, worker_id: int, failure_event: asyncio.Event) -> None:
    """Single worker coroutine."""
    consecutive_failures = 0

    while not failure_event.is_set():
        async with async_session() as db:
            # Check job status
            job_result = await db.execute(
                select(EdgarJob).where(EdgarJob.id == job_id)
            )
            job = job_result.scalar_one_or_none()
            if job is None:
                logger.error(f"[edgar-worker-{worker_id}] Job {job_id} not found, exiting")
                return

            if job.status in (EdgarJobStatus.paused, EdgarJobStatus.cancelled):
                logger.info(f"[edgar-worker-{worker_id}] Job {job_id} is {job.status.value}, exiting")
                return

            # Claim next step
            preferred = WORKER_PREFERENCES.get(worker_id)
            step = await _claim_next_step(db, job_id, preferred)

            if step is None:
                running_result = await db.execute(
                    select(func.count())
                    .select_from(EdgarJobStep)
                    .where(EdgarJobStep.job_id == job_id)
                    .where(EdgarJobStep.status == EdgarStepStatus.running)
                )
                running_count = running_result.scalar() or 0
                if running_count == 0:
                    return
                await asyncio.sleep(2)
                continue

            # Execute step
            step_type = step.step_type
            executor = STEP_EXECUTORS.get(step_type)
            if executor is None:
                step.status = EdgarStepStatus.failed
                step.error = f"Unknown step type: {step_type}"
                step.completed_at = datetime.now(timezone.utc)
                await db.commit()
                continue

            try:
                await executor(db, step, job)
                step.status = EdgarStepStatus.completed
                step.completed_at = datetime.now(timezone.utc)
                consecutive_failures = 0
            except Exception as e:
                logger.exception(f"[edgar-worker-{worker_id}] Step {step.id} failed: {e}")
                step.status = EdgarStepStatus.failed
                step.error = str(e)[:500]
                step.completed_at = datetime.now(timezone.utc)
                consecutive_failures += 1

            await _update_progress(db, job)
            await db.commit()

            if consecutive_failures >= 3:
                failure_event.set()
                job.status = EdgarJobStatus.paused
                job.error = f"Worker {worker_id} paused job after 3 consecutive failures"
                job.updated_at = datetime.now(timezone.utc)
                await db.commit()
                logger.warning(f"[edgar-worker-{worker_id}] Paused job {job_id} after 3 consecutive failures")
                return

        # Rate limiting delay
        delay = STEP_DELAYS.get(step_type, 1.0)
        await asyncio.sleep(delay)


async def run_edgar_worker(job_id: str) -> None:
    """Main entry point. Spawns 4 concurrent workers."""
    failure_event = asyncio.Event()

    workers = [
        asyncio.create_task(_worker_loop(job_id, i, failure_event))
        for i in range(CONCURRENCY)
    ]

    await asyncio.gather(*workers)

    # Mark job complete if not paused/cancelled
    async with async_session() as db:
        job_result = await db.execute(
            select(EdgarJob).where(EdgarJob.id == job_id)
        )
        job = job_result.scalar_one_or_none()
        if job and job.status == EdgarJobStatus.running:
            job.status = EdgarJobStatus.completed
            job.current_phase = EdgarJobPhase.complete
            job.completed_at = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            await _update_progress(db, job)
            await db.commit()
            logger.info(f"EDGAR job {job_id} completed")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/edgar_worker.py
git commit -m "feat: add EDGAR batch worker with 4 concurrent workers, atomic claiming, and step chaining"
```

---

### Task 6: Admin API Endpoints

**Files:**
- Create: `backend/app/api/admin_edgar.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create admin_edgar.py API routes**

Create `backend/app/api/admin_edgar.py`:

```python
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.edgar_job import (
    EdgarJob,
    EdgarJobPhase,
    EdgarJobStatus,
    EdgarJobStep,
    EdgarStepStatus,
    EdgarStepType,
)
from app.models.startup import Startup
from app.models.user import User
from app.services.edgar_worker import run_edgar_worker

router = APIRouter()


class EdgarStartRequest(BaseModel):
    scan_mode: str = "full"  # "full" or "new_only"


@router.post("/api/admin/edgar/start")
async def start_edgar_scan(
    body: EdgarStartRequest,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Check no EDGAR job is already running
    existing = await db.execute(
        select(EdgarJob).where(
            EdgarJob.status.in_([EdgarJobStatus.running, EdgarJobStatus.pending])
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="An EDGAR scan is already running")

    # Create job
    job = EdgarJob(
        scan_mode=body.scan_mode,
        status=EdgarJobStatus.running,
        current_phase=EdgarJobPhase.resolving_ciks,
    )
    db.add(job)
    await db.flush()

    sort_order = 0

    # Generate resolve_cik steps for US startups without a CIK
    cik_query = (
        select(Startup.id, Startup.name)
        .where(Startup.location_country == "US")
        .where(Startup.sec_cik.is_(None))
    )
    if body.scan_mode == "new_only":
        cik_query = cik_query.where(Startup.edgar_last_scanned_at.is_(None))

    cik_result = await db.execute(cik_query)
    for startup_id, startup_name in cik_result.all():
        step = EdgarJobStep(
            job_id=job.id,
            step_type=EdgarStepType.resolve_cik,
            params={"startup_id": str(startup_id), "startup_name": startup_name},
            sort_order=sort_order,
        )
        db.add(step)
        sort_order += 1

    # Generate fetch_filings steps for startups that already have a CIK
    fetch_query = (
        select(Startup.id, Startup.name, Startup.sec_cik)
        .where(Startup.sec_cik.is_not(None))
    )
    fetch_result = await db.execute(fetch_query)
    for startup_id, startup_name, sec_cik in fetch_result.all():
        step = EdgarJobStep(
            job_id=job.id,
            step_type=EdgarStepType.fetch_filings,
            params={
                "startup_id": str(startup_id),
                "startup_name": startup_name,
                "cik": sec_cik,
            },
            sort_order=sort_order,
        )
        db.add(step)
        sort_order += 1

    job.progress_summary = {
        "startups_total": sort_order,
        "startups_scanned": 0,
        "ciks_matched": 0,
        "filings_found": 0,
        "filings_total": 0,
        "filings_processed": 0,
        "rounds_updated": 0,
        "rounds_created": 0,
        "valuations_added": 0,
    }

    await db.commit()

    background_tasks.add_task(run_edgar_worker, str(job.id))

    return {
        "job_id": str(job.id),
        "status": job.status.value,
        "total_steps": sort_order,
    }


@router.post("/api/admin/edgar/{job_id}/pause")
async def pause_edgar(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(EdgarJob).where(EdgarJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != EdgarJobStatus.running:
        raise HTTPException(status_code=400, detail=f"Cannot pause job in {job.status.value} state")

    job.status = EdgarJobStatus.paused
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "paused"}


@router.post("/api/admin/edgar/{job_id}/resume")
async def resume_edgar(
    job_id: str,
    background_tasks: BackgroundTasks,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(EdgarJob).where(EdgarJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in (EdgarJobStatus.paused, EdgarJobStatus.cancelled):
        raise HTTPException(status_code=400, detail=f"Cannot resume job in {job.status.value} state")

    # Reset stuck running steps
    stuck_steps = await db.execute(
        select(EdgarJobStep)
        .where(EdgarJobStep.job_id == job.id)
        .where(EdgarJobStep.status == EdgarStepStatus.running)
    )
    for step in stuck_steps.scalars().all():
        step.status = EdgarStepStatus.pending

    job.status = EdgarJobStatus.running
    job.error = None
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()

    background_tasks.add_task(run_edgar_worker, str(job.id))
    return {"status": "running"}


@router.post("/api/admin/edgar/{job_id}/cancel")
async def cancel_edgar(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(EdgarJob).where(EdgarJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    job.status = EdgarJobStatus.cancelled
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "cancelled"}


@router.get("/api/admin/edgar/active")
async def get_active_edgar(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(EdgarJob).order_by(EdgarJob.created_at.desc()).limit(1)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None

    elapsed = (datetime.now(timezone.utc) - job.created_at).total_seconds()

    return {
        "id": str(job.id),
        "scan_mode": job.scan_mode,
        "status": job.status.value,
        "current_phase": job.current_phase.value,
        "progress_summary": job.progress_summary,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "elapsed_seconds": int(elapsed),
    }


@router.get("/api/admin/edgar/{job_id}/startups")
async def get_edgar_startups(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    """Get startup-level EDGAR status for this job."""
    # Get all resolve_cik and fetch_filings steps
    result = await db.execute(
        select(EdgarJobStep)
        .where(EdgarJobStep.job_id == job_id)
        .where(EdgarJobStep.step_type.in_([EdgarStepType.resolve_cik, EdgarStepType.fetch_filings]))
        .order_by(EdgarJobStep.sort_order)
    )
    steps = result.scalars().all()

    items = []
    for s in steps:
        p = s.params or {}
        cik = None
        filings_found = 0

        if s.step_type == EdgarStepType.resolve_cik:
            cik = (s.result or {}).get("cik")
        elif s.step_type == EdgarStepType.fetch_filings:
            cik = p.get("cik")
            filings_found = (s.result or {}).get("filings_count", 0)

        items.append({
            "startup_name": p.get("startup_name", ""),
            "startup_id": p.get("startup_id", ""),
            "cik": cik,
            "filings_found": filings_found,
            "status": s.status.value,
            "step_type": s.step_type.value,
        })

    return {"total": len(items), "items": items}


@router.get("/api/admin/edgar/{job_id}/filings")
async def get_edgar_filings(
    job_id: str,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    """Get filing-level data for this job."""
    result = await db.execute(
        select(EdgarJobStep)
        .where(EdgarJobStep.job_id == job_id)
        .where(EdgarJobStep.step_type == EdgarStepType.process_filing)
        .order_by(EdgarJobStep.sort_order)
    )
    steps = result.scalars().all()

    items = []
    for s in steps:
        p = s.params or {}
        r = s.result or {}
        items.append({
            "startup_name": p.get("startup_name", ""),
            "filing_type": p.get("filing_type", ""),
            "filing_date": p.get("filing_date", ""),
            "action": r.get("action", ""),
            "amount": r.get("amount"),
            "rounds_extracted": r.get("rounds_extracted"),
            "valuation_added": r.get("valuation_added", False),
            "status": s.status.value,
            "error": s.error,
        })

    return {"total": len(items), "items": items}


@router.get("/api/admin/edgar/{job_id}/log")
async def get_edgar_log(
    job_id: str,
    page: int = 1,
    per_page: int = 100,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    """Activity log for EDGAR job — same pattern as batch log."""
    result = await db.execute(
        select(EdgarJobStep)
        .where(EdgarJobStep.job_id == job_id)
        .where(
            EdgarJobStep.status.in_(
                [EdgarStepStatus.completed, EdgarStepStatus.failed, EdgarStepStatus.running]
            )
        )
        .order_by(EdgarJobStep.completed_at.desc().nulls_last())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    steps = result.scalars().all()

    items = []
    for s in steps:
        p = s.params or {}
        r = s.result or {}
        name = p.get("startup_name", "")

        if s.step_type == EdgarStepType.resolve_cik:
            if s.status == EdgarStepStatus.completed:
                cik = r.get("cik")
                msg = f"Matched {name} → CIK {cik}" if cik else f"No CIK match for {name}"
            elif s.status == EdgarStepStatus.running:
                msg = f"Resolving CIK for {name}..."
            else:
                msg = f"Failed CIK resolution for {name}: {s.error or 'unknown'}"

        elif s.step_type == EdgarStepType.fetch_filings:
            if s.status == EdgarStepStatus.completed:
                count = r.get("filings_count", 0)
                msg = f"Found {count} filings for {name}"
            elif s.status == EdgarStepStatus.running:
                msg = f"Fetching filings for {name}..."
            else:
                msg = f"Failed to fetch filings for {name}: {s.error or 'unknown'}"

        elif s.step_type == EdgarStepType.process_filing:
            ftype = p.get("filing_type", "")
            if s.status == EdgarStepStatus.completed:
                action = r.get("action", "")
                amount = r.get("amount", "")
                if action == "created":
                    msg = f"Created round from {ftype} for {name}"
                    if amount:
                        msg += f" ({amount})"
                elif action == "updated":
                    msg = f"Updated round from {ftype} for {name}"
                    if amount:
                        msg += f" ({amount})"
                elif r.get("rounds_extracted"):
                    msg = f"Extracted {r['rounds_extracted']} rounds from {ftype} for {name}"
                else:
                    msg = f"Processed {ftype} for {name}"
                if r.get("valuation_added"):
                    msg += " [+valuation]"
            elif s.status == EdgarStepStatus.running:
                msg = f"Processing {ftype} for {name}..."
            else:
                msg = f"Failed to process {ftype} for {name}: {s.error or 'unknown'}"
        else:
            msg = f"Step {s.step_type.value}: {s.status.value}"

        items.append({
            "timestamp": (s.completed_at or s.created_at).isoformat(),
            "message": msg,
            "step_type": s.step_type.value,
            "status": s.status.value,
        })

    return {"items": items}
```

- [ ] **Step 2: Register router in main.py**

In `backend/app/main.py`, add after line 21 (the `admin_batch` import):

```python
from app.api.admin_edgar import router as admin_edgar_router
```

And add after line 49 (the `admin_batch_router` include):

```python
app.include_router(admin_edgar_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin_edgar.py backend/app/main.py
git commit -m "feat: add EDGAR admin API endpoints with start/pause/resume/cancel, progress, and logs"
```

---

### Task 7: Admin Frontend — API Client Methods

**Files:**
- Modify: `admin/lib/api.ts`

- [ ] **Step 1: Add EDGAR API methods to adminApi**

In `admin/lib/api.ts`, add after the `getBatchLog` method (before the closing `};`):

```typescript
  // EDGAR pipeline
  async startEdgar(token: string, scanMode: string) {
    return apiFetch<{ job_id: string; status: string; total_steps: number }>(
      "/api/admin/edgar/start",
      token,
      { method: "POST", body: JSON.stringify({ scan_mode: scanMode }) }
    );
  },
  async pauseEdgar(token: string, jobId: string) {
    return apiFetch<{ status: string }>(`/api/admin/edgar/${jobId}/pause`, token, { method: "POST" });
  },
  async resumeEdgar(token: string, jobId: string) {
    return apiFetch<{ status: string }>(`/api/admin/edgar/${jobId}/resume`, token, { method: "POST" });
  },
  async cancelEdgar(token: string, jobId: string) {
    return apiFetch<{ status: string }>(`/api/admin/edgar/${jobId}/cancel`, token, { method: "POST" });
  },
  async getActiveEdgar(token: string) {
    return apiFetch<any>("/api/admin/edgar/active", token);
  },
  async getEdgarStartups(token: string, jobId: string) {
    return apiFetch<any>(`/api/admin/edgar/${jobId}/startups`, token);
  },
  async getEdgarFilings(token: string, jobId: string) {
    return apiFetch<any>(`/api/admin/edgar/${jobId}/filings`, token);
  },
  async getEdgarLog(token: string, jobId: string, page?: number) {
    const qs = page ? `?page=${page}` : "";
    return apiFetch<any>(`/api/admin/edgar/${jobId}/log${qs}`, token);
  },
```

- [ ] **Step 2: Commit**

```bash
git add admin/lib/api.ts
git commit -m "feat: add EDGAR API client methods to admin frontend"
```

---

### Task 8: Admin Frontend — Sidebar Nav

**Files:**
- Modify: `admin/components/Sidebar.tsx`

- [ ] **Step 1: Add EDGAR nav item**

In `admin/components/Sidebar.tsx`, add a new entry to `NAV_ITEMS` after the "Batch" entry (line 11):

```typescript
  { href: "/edgar", label: "EDGAR" },
```

- [ ] **Step 2: Commit**

```bash
git add admin/components/Sidebar.tsx
git commit -m "feat: add EDGAR nav item to admin sidebar"
```

---

### Task 9: Admin Frontend — EDGAR Page

**Files:**
- Create: `admin/app/edgar/page.tsx`

- [ ] **Step 1: Create the EDGAR admin page**

Create `admin/app/edgar/page.tsx`:

```tsx
"use client";

import { useSession } from "next-auth/react";
import { useCallback, useEffect, useState } from "react";
import { adminApi } from "@/lib/api";

type Tab = "startups" | "filings";

const PHASE_LABELS: Record<string, string> = {
  resolving_ciks: "Resolving CIKs",
  fetching_filings: "Fetching Filings",
  processing_filings: "Processing Filings",
  complete: "Complete",
};

const STATUS_COLORS: Record<string, string> = {
  running: "bg-yellow-100 text-yellow-800",
  paused: "bg-orange-100 text-orange-800",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  cancelled: "bg-gray-100 text-gray-600",
  pending: "bg-gray-100 text-gray-600",
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

export default function EdgarPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;

  const [job, setJob] = useState<any>(null);
  const [tab, setTab] = useState<Tab>("startups");
  const [startups, setStartups] = useState<any[]>([]);
  const [filings, setFilings] = useState<any[]>([]);
  const [log, setLog] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  const fetchData = useCallback(async () => {
    if (!token) return;
    try {
      const activeJob = await adminApi.getActiveEdgar(token);
      setJob(activeJob);
      if (activeJob?.id) {
        setElapsed(activeJob.elapsed_seconds || 0);

        if (tab === "startups") {
          const data = await adminApi.getEdgarStartups(token, activeJob.id);
          setStartups(data.items || []);
        } else if (tab === "filings") {
          const data = await adminApi.getEdgarFilings(token, activeJob.id);
          setFilings(data.items || []);
        }

        const logData = await adminApi.getEdgarLog(token, activeJob.id);
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

  async function handleStart(scanMode: string) {
    if (!token) return;
    setLoading(true);
    try {
      await adminApi.startEdgar(token, scanMode);
      await fetchData();
    } catch (e: any) {
      alert(e.message || "Failed to start EDGAR scan");
    }
    setLoading(false);
  }

  async function handlePause() {
    if (!token || !job) return;
    await adminApi.pauseEdgar(token, job.id);
    await fetchData();
  }

  async function handleResume() {
    if (!token || !job) return;
    await adminApi.resumeEdgar(token, job.id);
    await fetchData();
  }

  async function handleCancel() {
    if (!token || !job) return;
    if (!confirm("Cancel this EDGAR scan?")) return;
    await adminApi.cancelEdgar(token, job.id);
    await fetchData();
  }

  const summary = job?.progress_summary || {};
  const isActive = job?.status === "running" || job?.status === "paused";
  const canStart = !isActive && job?.status !== "pending";
  const matchRate = summary.startups_scanned > 0
    ? Math.round((summary.ciks_matched / summary.startups_scanned) * 100)
    : 0;

  return (
    <div className="ml-56 p-8">
      <h1 className="font-serif text-2xl text-text-primary mb-6">EDGAR SEC Filings</h1>

      {/* Control Bar */}
      <div className="rounded border border-border bg-surface p-5 mb-6">
        <div className="flex items-center gap-3 mb-4">
          {canStart && (
            <>
              <button
                onClick={() => handleStart("full")}
                disabled={loading}
                className="px-4 py-2 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover disabled:opacity-50 transition"
              >
                Run EDGAR Scan
              </button>
              <button
                onClick={() => handleStart("new_only")}
                disabled={loading}
                className="px-4 py-2 text-sm font-medium rounded border border-accent text-accent hover:bg-accent/5 disabled:opacity-50 transition"
              >
                Scan New Only
              </button>
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
          {job?.current_phase && job.status === "running" && (
            <span className="text-xs text-text-tertiary">{PHASE_LABELS[job.current_phase] || job.current_phase}</span>
          )}
          {job?.error && <span className="text-xs text-red-600 ml-2">{job.error}</span>}
          {isActive && (
            <span className="text-xs text-text-tertiary ml-auto tabular-nums">{formatElapsed(elapsed)}</span>
          )}
        </div>

        {/* Progress summary — 6 cards */}
        {job && (
          <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
            <div>
              <p className="text-xs text-text-tertiary">Startups Scanned</p>
              <p className="text-sm font-medium text-text-primary tabular-nums">
                {summary.startups_scanned || 0} / {summary.startups_total || 0}
              </p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">CIKs Matched</p>
              <p className="text-sm font-medium text-text-primary tabular-nums">
                {summary.ciks_matched || 0}
                {summary.startups_scanned > 0 && (
                  <span className="text-text-tertiary text-xs ml-1">({matchRate}%)</span>
                )}
              </p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">Filings Found</p>
              <p className="text-sm font-medium text-text-primary tabular-nums">{summary.filings_found || 0}</p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">Filings Processed</p>
              <p className="text-sm font-medium text-text-primary tabular-nums">
                {summary.filings_processed || 0} / {summary.filings_total || 0}
              </p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">Rounds Updated</p>
              <p className="text-sm font-medium text-score-high tabular-nums">
                {(summary.rounds_updated || 0) + (summary.rounds_created || 0)}
              </p>
            </div>
            <div>
              <p className="text-xs text-text-tertiary">Valuations Added</p>
              <p className="text-sm font-medium text-score-high tabular-nums">{summary.valuations_added || 0}</p>
            </div>
          </div>
        )}

        {job && summary.current_startup && (
          <p className="text-xs text-text-tertiary mt-3">
            Currently: {summary.current_startup}
            {summary.current_filing && ` / ${summary.current_filing}`}
          </p>
        )}
      </div>

      {job && (
        <>
          {/* Tabs */}
          <div className="flex items-center gap-1 mb-4 border-b border-border">
            {(["startups", "filings"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition -mb-px ${
                  tab === t
                    ? "border-accent text-accent"
                    : "border-transparent text-text-tertiary hover:text-text-secondary"
                }`}
              >
                {t === "startups" ? "Startups" : "Filings"}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="rounded border border-border bg-surface overflow-x-auto mb-6">
            {tab === "startups" && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-background">
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Startup</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">CIK</th>
                    <th className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary">Filings</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {startups.map((s, i) => (
                    <tr
                      key={i}
                      className={`border-b border-border last:border-b-0 ${
                        s.status === "running" ? "bg-accent/5" : "hover:bg-hover-row"
                      }`}
                    >
                      <td className="px-4 py-2 text-text-primary font-medium">{s.startup_name}</td>
                      <td className="px-4 py-2 text-text-secondary tabular-nums">
                        {s.cik || <span className="text-text-tertiary">{s.status === "completed" ? "No match" : "\u2014"}</span>}
                      </td>
                      <td className="px-4 py-2 text-right text-text-secondary tabular-nums">
                        {s.filings_found > 0 ? s.filings_found : "\u2014"}
                      </td>
                      <td className="px-4 py-2"><Badge status={s.status} /></td>
                    </tr>
                  ))}
                  {startups.length === 0 && (
                    <tr><td colSpan={4} className="px-4 py-8 text-center text-text-tertiary text-sm">No startups scanned yet</td></tr>
                  )}
                </tbody>
              </table>
            )}

            {tab === "filings" && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-background">
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Startup</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Filing</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Date</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Result</th>
                    <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {filings.map((f, i) => (
                    <tr
                      key={i}
                      className={`border-b border-border last:border-b-0 ${
                        f.status === "running" ? "bg-accent/5" : "hover:bg-hover-row"
                      }`}
                    >
                      <td className="px-4 py-2 text-text-primary font-medium">{f.startup_name}</td>
                      <td className="px-4 py-2">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                          f.filing_type?.startsWith("D") ? "bg-blue-100 text-blue-800" :
                          f.filing_type?.startsWith("S") ? "bg-purple-100 text-purple-800" :
                          "bg-amber-100 text-amber-800"
                        }`}>
                          {f.filing_type}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-text-secondary tabular-nums">{f.filing_date}</td>
                      <td className="px-4 py-2 text-text-secondary text-xs">
                        {f.status === "completed" ? (
                          <>
                            {f.action === "created" && <span className="text-score-high">New round</span>}
                            {f.action === "updated" && <span className="text-blue-600">Updated</span>}
                            {f.action === "skipped" && <span className="text-text-tertiary">Skipped</span>}
                            {f.rounds_extracted != null && <span>{f.rounds_extracted} rounds</span>}
                            {f.amount && <span className="ml-1">({f.amount})</span>}
                            {f.valuation_added && <span className="ml-1 text-score-high">[+val]</span>}
                          </>
                        ) : f.error ? (
                          <span className="text-red-600" title={f.error}>Error</span>
                        ) : "\u2014"}
                      </td>
                      <td className="px-4 py-2"><Badge status={f.status} /></td>
                    </tr>
                  ))}
                  {filings.length === 0 && (
                    <tr><td colSpan={5} className="px-4 py-8 text-center text-text-tertiary text-sm">No filings processed yet</td></tr>
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
          No EDGAR scans yet. Run a scan to match startups with SEC filings and extract funding data.
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add admin/app/edgar/page.tsx
git commit -m "feat: add EDGAR admin page with controls, progress, startups/filings tabs, and activity log"
```

---

### Task 10: Install httpx Dependency

**Files:**
- Modify: `backend/requirements.txt` (or `pyproject.toml`)

- [ ] **Step 1: Check current dependencies and add httpx**

```bash
cd backend && cat requirements.txt 2>/dev/null || cat pyproject.toml
```

Add `httpx` to the dependency list (if not already present). The EDGAR client uses `httpx.AsyncClient` for async HTTP requests.

```
httpx>=0.27.0
```

- [ ] **Step 2: Install dependency**

```bash
cd backend && pip install httpx
```

- [ ] **Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat: add httpx dependency for EDGAR HTTP client"
```

---

### Task 11: Integration Smoke Test

- [ ] **Step 1: Verify backend starts without import errors**

```bash
cd backend && python -c "from app.models.edgar_job import EdgarJob, EdgarJobStep; from app.services.edgar import search_company; from app.services.edgar_processor import parse_form_d; from app.services.edgar_worker import run_edgar_worker; from app.api.admin_edgar import router; print('All imports OK')"
```

Expected: `All imports OK`

- [ ] **Step 2: Verify migration applies**

```bash
cd backend && alembic upgrade head
```

Expected: Migration applies cleanly (or reports already at head).

- [ ] **Step 3: Verify admin frontend builds**

```bash
cd admin && npm run build 2>&1 | tail -20
```

Expected: Build succeeds with no errors on the new EDGAR page.

- [ ] **Step 4: Final commit with all remaining changes**

```bash
git add -A
git status
```

If there are any unstaged changes, commit them:

```bash
git commit -m "feat: EDGAR SEC filing scraper — complete implementation"
```

---

## Spec Coverage Verification

| Spec Requirement | Task |
|-----------------|------|
| EdgarJob/EdgarJobStep models | Task 1 |
| sec_cik, edgar_last_scanned_at on Startup | Task 1 |
| data_source on StartupFundingRound | Task 1 |
| Alembic migration | Task 1 |
| anthropic_api_key, edgar_user_agent config | Task 2 |
| EDGAR company search API | Task 3 |
| EDGAR filing index API | Task 3 |
| EDGAR document download API | Task 3 |
| 150ms rate limiting | Task 3 |
| Form D XML parsing | Task 4 |
| S-1 HTML Claude parsing | Task 4 |
| 10-K HTML Claude parsing | Task 4 |
| Company matching + Claude verification | Task 4 |
| Merge logic (EDGAR wins financials) | Task 4 |
| 4 concurrent workers | Task 5 |
| SELECT FOR UPDATE SKIP LOCKED | Task 5 |
| Step chaining (resolve→fetch→process) | Task 5 |
| Worker preferences | Task 5 |
| Pause/resume/cancel | Task 5 + Task 6 |
| Start full scan / scan new only | Task 6 |
| Progress summary (6 metrics) | Task 6 + Task 9 |
| Activity log | Task 6 + Task 9 |
| Startups tab | Task 6 + Task 9 |
| Filings tab | Task 6 + Task 9 |
| Admin sidebar nav | Task 8 |
| Admin API client methods | Task 7 |
| httpx dependency | Task 10 |
