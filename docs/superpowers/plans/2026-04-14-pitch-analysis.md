# Pitch Analysis System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public-facing pitch analysis tool with multi-agent Claude evaluation, S3 document storage, and optional public startup listing.

**Architecture:** New analysis worker container polls for jobs, extracts document text, runs 8 Claude agents in parallel via asyncio.gather(), synthesizes with Opus scoring agent, optionally creates public startup records via existing Perplexity enrichment. Frontend adds /analyze routes with upload, progress polling, and tabbed results dashboard.

**Tech Stack:** Python/FastAPI, SQLAlchemy async, Alembic, PostgreSQL, boto3/S3, anthropic SDK, pymupdf, python-docx, python-pptx, openpyxl, xlrd, Next.js 16/React 19, TypeScript, Tailwind CSS 4

---

## File Structure

### New Backend Files
- `backend/app/models/pitch_analysis.py` — PitchAnalysis, AnalysisDocument, AnalysisReport models
- `backend/app/services/s3.py` — S3 client (upload, download, delete)
- `backend/app/services/document_extractor.py` — Text extraction from all file formats
- `backend/app/services/analysis_agents.py` — 8 agent prompts + runner + final scoring
- `backend/app/services/analysis_worker.py` — Worker job loop
- `backend/app/api/analyze.py` — API router for /api/analyze endpoints
- `backend/alembic/versions/m1n2o3p4q5r6_add_pitch_analysis_tables.py` — Migration
- `backend/Dockerfile.worker` — Worker container with libreoffice

### Modified Backend Files
- `backend/app/models/user.py` — Add SubscriptionStatus enum + subscription_status column
- `backend/app/models/__init__.py` — Export new models
- `backend/app/main.py` — Register analyze router
- `backend/app/config.py` — Add S3 + Anthropic settings
- `backend/pyproject.toml` — Add dependencies

### New Frontend Files
- `frontend/app/analyze/page.tsx` — Upload page with auth gate
- `frontend/app/analyze/[id]/page.tsx` — Progress + results dashboard
- `frontend/app/analyze/history/page.tsx` — Past analyses list

### Modified Frontend Files
- `frontend/lib/types.ts` — Add analysis types
- `frontend/lib/api.ts` — Add analysis API methods
- `frontend/components/Navbar.tsx` — Add Analyze link

### Infrastructure
- `docker-compose.prod.yml` — Add analysis_worker service

---

## Task 1: Database Models + Migration

**Files:**
- Create: `backend/app/models/pitch_analysis.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/m1n2o3p4q5r6_add_pitch_analysis_tables.py`

- [ ] **Step 1: Create the pitch analysis models file**

Create `backend/app/models/pitch_analysis.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class AnalysisStatus(str, enum.Enum):
    pending = "pending"
    extracting = "extracting"
    analyzing = "analyzing"
    enriching = "enriching"
    complete = "complete"
    failed = "failed"


class AgentType(str, enum.Enum):
    problem_solution = "problem_solution"
    market_tam = "market_tam"
    traction = "traction"
    technology_ip = "technology_ip"
    competition_moat = "competition_moat"
    team = "team"
    gtm_business_model = "gtm_business_model"
    financials_fundraising = "financials_fundraising"


class ReportStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    failed = "failed"


class PitchAnalysis(Base):
    __tablename__ = "pitch_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    company_name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(AnalysisStatus, name="analysisstatus"), nullable=False, default=AnalysisStatus.pending
    )
    current_agent: Mapped[str | None] = mapped_column(String(100), nullable=True)
    overall_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fundraising_likelihood: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommended_raise: Mapped[str | None] = mapped_column(String(100), nullable=True)
    exit_likelihood: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_exit_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_exit_timeline: Mapped[str | None] = mapped_column(String(100), nullable=True)
    executive_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    startup_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("startups.id"), nullable=True
    )
    publish_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_free_analysis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    documents: Mapped[list["AnalysisDocument"]] = relationship(
        "AnalysisDocument", back_populates="analysis", cascade="all, delete-orphan"
    )
    reports: Mapped[list["AnalysisReport"]] = relationship(
        "AnalysisReport", back_populates="analysis", cascade="all, delete-orphan"
    )


class AnalysisDocument(Base):
    __tablename__ = "analysis_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pitch_analyses.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    analysis: Mapped["PitchAnalysis"] = relationship("PitchAnalysis", back_populates="documents")


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pitch_analyses.id", ondelete="CASCADE"), nullable=False
    )
    agent_type: Mapped[str] = mapped_column(Enum(AgentType, name="agenttype"), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(ReportStatus, name="reportstatus"), nullable=False, default=ReportStatus.pending
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    report: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_findings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    analysis: Mapped["PitchAnalysis"] = relationship("PitchAnalysis", back_populates="reports")
```

- [ ] **Step 2: Add SubscriptionStatus to User model**

In `backend/app/models/user.py`, add the enum and column. Add this enum class before the User class:

```python
class SubscriptionStatus(str, enum.Enum):
    none = "none"
    active = "active"
    cancelled = "cancelled"
```

Add this column to the User class after the `region` field:

```python
    subscription_status: Mapped[str] = mapped_column(
        Enum(SubscriptionStatus, name="subscriptionstatus"),
        nullable=False, default=SubscriptionStatus.none, server_default="none"
    )
```

- [ ] **Step 3: Export new models in __init__.py**

Add to `backend/app/models/__init__.py`:

```python
from app.models.pitch_analysis import PitchAnalysis, AnalysisDocument, AnalysisReport
```

- [ ] **Step 4: Create the Alembic migration**

Create `backend/alembic/versions/m1n2o3p4q5r6_add_pitch_analysis_tables.py`:

```python
"""add pitch analysis tables and subscription status

Revision ID: m1n2o3p4q5r6
Revises: g7h8i9j0k1l2
Create Date: 2026-04-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision: str = "m1n2o3p4q5r6"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Subscription status enum and column on users
    op.execute("CREATE TYPE subscriptionstatus AS ENUM ('none', 'active', 'cancelled')")
    op.add_column("users", sa.Column(
        "subscription_status",
        sa.Enum("none", "active", "cancelled", name="subscriptionstatus"),
        nullable=False, server_default="none"
    ))

    # Analysis status enum
    op.execute(
        "CREATE TYPE analysisstatus AS ENUM "
        "('pending', 'extracting', 'analyzing', 'enriching', 'complete', 'failed')"
    )

    # Agent type enum
    op.execute(
        "CREATE TYPE agenttype AS ENUM "
        "('problem_solution', 'market_tam', 'traction', 'technology_ip', "
        "'competition_moat', 'team', 'gtm_business_model', 'financials_fundraising')"
    )

    # Report status enum
    op.execute("CREATE TYPE reportstatus AS ENUM ('pending', 'running', 'complete', 'failed')")

    # pitch_analyses table
    op.create_table(
        "pitch_analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("company_name", sa.String(500), nullable=False),
        sa.Column("status", sa.Enum("pending", "extracting", "analyzing", "enriching", "complete", "failed", name="analysisstatus"), nullable=False, server_default="pending"),
        sa.Column("current_agent", sa.String(100), nullable=True),
        sa.Column("overall_score", sa.Float, nullable=True),
        sa.Column("fundraising_likelihood", sa.Float, nullable=True),
        sa.Column("recommended_raise", sa.String(100), nullable=True),
        sa.Column("exit_likelihood", sa.Float, nullable=True),
        sa.Column("expected_exit_value", sa.String(100), nullable=True),
        sa.Column("expected_exit_timeline", sa.String(100), nullable=True),
        sa.Column("executive_summary", sa.Text, nullable=True),
        sa.Column("startup_id", UUID(as_uuid=True), sa.ForeignKey("startups.id"), nullable=True),
        sa.Column("publish_consent", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("is_free_analysis", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # analysis_documents table
    op.create_table(
        "analysis_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("pitch_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("s3_key", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False),
        sa.Column("extracted_text", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # analysis_reports table
    op.create_table(
        "analysis_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("pitch_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_type", sa.Enum("problem_solution", "market_tam", "traction", "technology_ip", "competition_moat", "team", "gtm_business_model", "financials_fundraising", name="agenttype"), nullable=False),
        sa.Column("status", sa.Enum("pending", "running", "complete", "failed", name="reportstatus"), nullable=False, server_default="pending"),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("report", sa.Text, nullable=True),
        sa.Column("key_findings", JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("analysis_reports")
    op.drop_table("analysis_documents")
    op.drop_table("pitch_analyses")
    op.drop_column("users", "subscription_status")
    op.execute("DROP TYPE reportstatus")
    op.execute("DROP TYPE agenttype")
    op.execute("DROP TYPE analysisstatus")
    op.execute("DROP TYPE subscriptionstatus")
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/pitch_analysis.py backend/app/models/user.py backend/app/models/__init__.py backend/alembic/versions/m1n2o3p4q5r6_add_pitch_analysis_tables.py
git commit -m "feat: add pitch analysis database models and migration"
```

---

## Task 2: S3 Client + Config Updates

**Files:**
- Create: `backend/app/services/s3.py`
- Modify: `backend/app/config.py`
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add S3 settings to config**

In `backend/app/config.py`, add these fields to the `Settings` class:

```python
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "deepthesis-pitch-documents"
```

- [ ] **Step 2: Add dependencies to pyproject.toml**

Add to the `dependencies` list in `backend/pyproject.toml`:

```
"boto3>=1.35.0",
"anthropic>=0.40.0",
"pymupdf>=1.24.0",
"python-docx>=1.1.0",
"python-pptx>=1.0.0",
"openpyxl>=3.1.0",
"xlrd>=2.0.0",
"python-multipart>=0.0.9",
```

- [ ] **Step 3: Create S3 client**

Create `backend/app/services/s3.py`:

```python
import boto3
from botocore.exceptions import ClientError

from app.config import settings


def _get_client():
    return boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )


def upload_file(file_data: bytes, s3_key: str) -> str:
    client = _get_client()
    client.put_object(Bucket=settings.s3_bucket_name, Key=s3_key, Body=file_data)
    return s3_key


def download_file(s3_key: str) -> bytes:
    client = _get_client()
    response = client.get_object(Bucket=settings.s3_bucket_name, Key=s3_key)
    return response["Body"].read()


def delete_file(s3_key: str) -> None:
    client = _get_client()
    try:
        client.delete_object(Bucket=settings.s3_bucket_name, Key=s3_key)
    except ClientError:
        pass


def delete_files(s3_keys: list[str]) -> None:
    if not s3_keys:
        return
    client = _get_client()
    objects = [{"Key": key} for key in s3_keys]
    client.delete_objects(Bucket=settings.s3_bucket_name, Delete={"Objects": objects})
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/s3.py backend/app/config.py backend/pyproject.toml
git commit -m "feat: add S3 client and pitch analysis dependencies"
```

---

## Task 3: Document Text Extraction Service

**Files:**
- Create: `backend/app/services/document_extractor.py`

- [ ] **Step 1: Create the document extractor**

Create `backend/app/services/document_extractor.py`:

```python
import csv
import io
import subprocess
import tempfile
from pathlib import Path


def extract_text(file_data: bytes, filename: str, file_type: str) -> str:
    extractors = {
        "pdf": _extract_pdf,
        "docx": _extract_docx,
        "doc": _extract_doc,
        "pptx": _extract_pptx,
        "ppt": _extract_ppt,
        "xlsx": _extract_xlsx,
        "xls": _extract_xls,
        "csv": _extract_csv,
        "md": _extract_text,
        "txt": _extract_text,
    }
    extractor = extractors.get(file_type)
    if not extractor:
        return f"[Unsupported file type: {file_type}]"
    try:
        return extractor(file_data, filename)
    except Exception as e:
        return f"[Error extracting {filename}: {e}]"


def _extract_pdf(data: bytes, filename: str) -> str:
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        text = page.get_text()
        if text.strip():
            pages.append(f"--- Page {i + 1} ---\n{text.strip()}")
    doc.close()
    return "\n\n".join(pages) if pages else "[No readable text found in PDF]"


def _extract_docx(data: bytes, filename: str) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs) if paragraphs else "[Empty document]"


def _extract_doc(data: bytes, filename: str) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        doc_path = Path(tmpdir) / filename
        doc_path.write_bytes(data)
        subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "docx", "--outdir", tmpdir, str(doc_path)],
            capture_output=True,
            timeout=30,
        )
        docx_path = doc_path.with_suffix(".docx")
        if docx_path.exists():
            return _extract_docx(docx_path.read_bytes(), docx_path.name)
    return "[Failed to convert .doc file]"


def _extract_pptx(data: bytes, filename: str) -> str:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    slides = []
    for i, slide in enumerate(prs.slides):
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    text = paragraph.text.strip()
                    if text:
                        texts.append(text)
        if texts:
            slides.append(f"--- Slide {i + 1} ---\n" + "\n".join(texts))
    return "\n\n".join(slides) if slides else "[Empty presentation]"


def _extract_ppt(data: bytes, filename: str) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        ppt_path = Path(tmpdir) / filename
        ppt_path.write_bytes(data)
        subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pptx", "--outdir", tmpdir, str(ppt_path)],
            capture_output=True,
            timeout=30,
        )
        pptx_path = ppt_path.with_suffix(".pptx")
        if pptx_path.exists():
            return _extract_pptx(pptx_path.read_bytes(), pptx_path.name)
    return "[Failed to convert .ppt file]"


def _extract_xlsx(data: bytes, filename: str) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheets = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) if c is not None else "" for c in row]
            if any(c.strip() for c in cells):
                rows.append(" | ".join(cells))
        if rows:
            header = rows[0]
            sep = " | ".join(["---"] * len(header.split(" | ")))
            table = f"### Sheet: {sheet_name}\n\n{header}\n{sep}\n" + "\n".join(rows[1:])
            sheets.append(table)
    wb.close()
    return "\n\n".join(sheets) if sheets else "[Empty spreadsheet]"


def _extract_xls(data: bytes, filename: str) -> str:
    import xlrd

    wb = xlrd.open_workbook(file_contents=data)
    sheets = []
    for sheet in wb.sheets():
        rows = []
        for row_idx in range(sheet.nrows):
            cells = [str(sheet.cell_value(row_idx, col)) for col in range(sheet.ncols)]
            if any(c.strip() for c in cells):
                rows.append(" | ".join(cells))
        if rows:
            header = rows[0]
            sep = " | ".join(["---"] * len(header.split(" | ")))
            table = f"### Sheet: {sheet.name}\n\n{header}\n{sep}\n" + "\n".join(rows[1:])
            sheets.append(table)
    return "\n\n".join(sheets) if sheets else "[Empty spreadsheet]"


def _extract_csv(data: bytes, filename: str) -> str:
    text = data.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = []
    for row in reader:
        if any(c.strip() for c in row):
            rows.append(" | ".join(row))
    if rows:
        header = rows[0]
        sep = " | ".join(["---"] * len(header.split(" | ")))
        return f"{header}\n{sep}\n" + "\n".join(rows[1:])
    return "[Empty CSV]"


def _extract_text(data: bytes, filename: str) -> str:
    return data.decode("utf-8", errors="replace")


def consolidate_documents(documents: list[dict]) -> str:
    type_labels = {
        "pdf": "document",
        "docx": "document",
        "doc": "document",
        "pptx": "slides",
        "ppt": "slides",
        "xlsx": "spreadsheet",
        "xls": "spreadsheet",
        "csv": "spreadsheet",
        "md": "markdown",
        "txt": "text",
    }
    sections = []
    for doc in documents:
        label = type_labels.get(doc["file_type"], "file")
        sections.append(f"=== DOCUMENT: {doc['filename']} ({label}) ===\n\n{doc['text']}")
    return "\n\n".join(sections)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/document_extractor.py
git commit -m "feat: add document text extraction for all supported formats"
```

---

## Task 4: Analysis Agents + Final Scoring

**Files:**
- Create: `backend/app/services/analysis_agents.py`

- [ ] **Step 1: Create the analysis agents module**

Create `backend/app/services/analysis_agents.py`:

```python
import json
import logging
from datetime import datetime

import anthropic
import httpx

from app.config import settings
from app.models.pitch_analysis import AgentType

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

You MUST independently research market size using the provided research context. Compare their claims against third-party data. Flag markets that are smaller than claimed or markets with declining growth.""",

    AgentType.traction: """You are a venture capital analyst evaluating Traction & Metrics.

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

You MUST independently research competitors using the provided research context. Identify competitors the startup may have omitted. Be especially skeptical of claims like "no direct competitors" — there are always alternatives.""",

    AgentType.team: """You are a venture capital analyst evaluating the founding Team.

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

You MUST research founders' backgrounds using the provided research context. Look up LinkedIn profiles, previous companies, and any public information. Be skeptical of inflated titles and vague experience claims. Flag single-founder risk and teams with no industry experience.""",

    AgentType.gtm_business_model: """You are a venture capital analyst evaluating GTM Strategy & Business Model.

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

PERPLEXITY_QUERIES: dict[AgentType, str] = {
    AgentType.problem_solution: "{company} problem they solve market need validation",
    AgentType.market_tam: "{company} market size TAM total addressable market industry growth rate 2024 2025",
    AgentType.traction: "{company} revenue users growth metrics traction funding",
    AgentType.technology_ip: "{company} technology stack patents intellectual property technical approach",
    AgentType.competition_moat: "{company} competitors competitive landscape alternatives market share",
    AgentType.team: "{company} founders team background experience LinkedIn previous companies",
    AgentType.gtm_business_model: "{company} business model pricing go to market strategy customers",
    AgentType.financials_fundraising: "{company} funding raised valuation investors fundraising round",
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


async def _research_with_perplexity(query: str) -> str:
    if not settings.perplexity_api_key:
        return "[No Perplexity API key configured — skipping web research]"
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
                        {"role": "system", "content": "Provide factual research data. Include specific numbers, dates, and sources where available."},
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
        logger.warning(f"Perplexity research failed: {e}")
        return f"[Web research unavailable: {e}]"


async def run_agent(
    agent_type: AgentType,
    consolidated_text: str,
    company_name: str,
) -> dict:
    system_prompt = AGENT_PROMPTS[agent_type]
    query = PERPLEXITY_QUERIES[agent_type].format(company=company_name)
    research = await _research_with_perplexity(query)

    user_message = f"""# Company: {company_name}

## Web Research Context
{research}

## Uploaded Documents
{consolidated_text}

---

Analyze this startup and return your evaluation as JSON with these fields:
- "score": number 0-100 based on the rubric
- "summary": one paragraph verdict (2-3 sentences)
- "report": detailed markdown report (500-1500 words) with sections matching the rubric
- "key_findings": array of 3-5 key findings as short strings

Return ONLY valid JSON, no markdown fencing."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    for attempt in range(2):
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            content = response.content[0].text
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

            result = json.loads(content)
            return {
                "score": max(0, min(100, float(result["score"]))),
                "summary": str(result["summary"]),
                "report": str(result["report"]),
                "key_findings": [str(f) for f in result.get("key_findings", [])],
            }
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Agent {agent_type.value} attempt 1 failed: {e}, retrying...")
                continue
            raise

    raise RuntimeError(f"Agent {agent_type.value} failed after 2 attempts")


async def run_final_scoring(reports: list[dict], company_name: str) -> dict:
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

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/analysis_agents.py
git commit -m "feat: add 8 analysis agents with rubrics and final scoring agent"
```

---

## Task 5: Analysis Worker

**Files:**
- Create: `backend/app/services/analysis_worker.py`

- [ ] **Step 1: Create the analysis worker**

Create `backend/app/services/analysis_worker.py`:

```python
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import async_session
from app.models.pitch_analysis import (
    AgentType,
    AnalysisDocument,
    AnalysisReport,
    AnalysisStatus,
    PitchAnalysis,
    ReportStatus,
)
from app.models.startup import EnrichmentStatus, Startup, StartupStatus
from app.services import s3
from app.services.analysis_agents import run_agent, run_final_scoring
from app.services.document_extractor import consolidate_documents, extract_text

logger = logging.getLogger(__name__)

STALE_CLAIM_MINUTES = 15


async def _claim_job(db: AsyncSession) -> PitchAnalysis | None:
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_CLAIM_MINUTES)

    # Reset stale claimed jobs
    await db.execute(
        update(PitchAnalysis)
        .where(
            PitchAnalysis.status.in_([AnalysisStatus.extracting, AnalysisStatus.analyzing]),
            PitchAnalysis.claimed_at < stale_cutoff,
        )
        .values(status=AnalysisStatus.pending, claimed_at=None, current_agent=None)
    )

    # Claim a pending job
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.status == AnalysisStatus.pending)
        .order_by(PitchAnalysis.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if job:
        job.status = AnalysisStatus.extracting
        job.claimed_at = datetime.now(timezone.utc)
        await db.commit()
    return job


async def _extract_documents(db: AsyncSession, analysis_id: uuid.UUID) -> str:
    result = await db.execute(
        select(AnalysisDocument).where(AnalysisDocument.analysis_id == analysis_id)
    )
    docs = result.scalars().all()

    extracted = []
    for doc in docs:
        logger.info(f"Extracting: {doc.filename} ({doc.file_type})")
        file_data = s3.download_file(doc.s3_key)
        text = extract_text(file_data, doc.filename, doc.file_type)
        doc.extracted_text = text
        extracted.append({"filename": doc.filename, "file_type": doc.file_type, "text": text})

    await db.commit()
    return consolidate_documents(extracted)


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
        agent_result = await run_agent(agent_type, consolidated_text, company_name)

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


async def _create_startup_from_analysis(
    db: AsyncSession, analysis: PitchAnalysis, consolidated_text: str
) -> None:
    from app.services.enrichment import run_enrichment_pipeline

    slug_base = analysis.company_name.lower().replace(" ", "-")
    slug_base = "".join(c for c in slug_base if c.isalnum() or c == "-")
    slug = f"{slug_base}-{str(uuid.uuid4())[:6]}"

    startup = Startup(
        name=analysis.company_name,
        slug=slug,
        description=f"Submitted for analysis on Deep Thesis",
        status=StartupStatus.approved,
        ai_score=analysis.overall_score,
        form_sources=["pitch_analysis"],
        enrichment_status=EnrichmentStatus.running,
    )
    db.add(startup)
    await db.flush()

    analysis.startup_id = startup.id
    await db.commit()

    try:
        await run_enrichment_pipeline(db, startup)
    except Exception as e:
        logger.error(f"Enrichment failed for {analysis.company_name}: {e}")
        startup.enrichment_status = EnrichmentStatus.failed
        startup.enrichment_error = str(e)
        await db.commit()


async def _process_job(analysis_id: uuid.UUID) -> None:
    db_factory = async_session

    # Phase 1: Extract documents
    async with db_factory() as db:
        result = await db.execute(
            select(PitchAnalysis).where(PitchAnalysis.id == analysis_id)
        )
        analysis = result.scalar_one()
        company_name = analysis.company_name
        publish_consent = analysis.publish_consent

    async with db_factory() as db:
        try:
            consolidated_text = await _extract_documents(db, analysis_id)
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            result = await db.execute(
                select(PitchAnalysis).where(PitchAnalysis.id == analysis_id)
            )
            analysis = result.scalar_one()
            analysis.status = AnalysisStatus.failed
            analysis.error = f"Document extraction failed: {e}"
            await db.commit()
            return

    # Phase 2: Create report records and run agents
    async with db_factory() as db:
        result = await db.execute(
            select(PitchAnalysis).where(PitchAnalysis.id == analysis_id)
        )
        analysis = result.scalar_one()
        analysis.status = AnalysisStatus.analyzing
        await db.commit()

        for agent_type in AgentType:
            report = AnalysisReport(
                analysis_id=analysis_id,
                agent_type=agent_type,
                status=ReportStatus.pending,
            )
            db.add(report)
        await db.commit()

    # Run all 8 agents in parallel
    tasks = [
        _run_single_agent(db_factory, analysis_id, agent_type, consolidated_text, company_name)
        for agent_type in AgentType
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect successful results for scoring
    completed_reports = [r for r in results if isinstance(r, dict)]

    if not completed_reports:
        async with db_factory() as db:
            result = await db.execute(
                select(PitchAnalysis).where(PitchAnalysis.id == analysis_id)
            )
            analysis = result.scalar_one()
            analysis.status = AnalysisStatus.failed
            analysis.error = "All agents failed"
            await db.commit()
        return

    # Phase 3: Final scoring
    try:
        scoring = await run_final_scoring(completed_reports, company_name)
    except Exception as e:
        logger.error(f"Final scoring failed: {e}")
        scoring = {
            "overall_score": sum(r["score"] for r in completed_reports) / len(completed_reports),
            "fundraising_likelihood": None,
            "recommended_raise": None,
            "exit_likelihood": None,
            "expected_exit_value": None,
            "expected_exit_timeline": None,
            "executive_summary": "Final scoring agent failed. Scores shown are raw averages.",
        }

    async with db_factory() as db:
        result = await db.execute(
            select(PitchAnalysis).where(PitchAnalysis.id == analysis_id)
        )
        analysis = result.scalar_one()
        analysis.overall_score = scoring["overall_score"]
        analysis.fundraising_likelihood = scoring.get("fundraising_likelihood")
        analysis.recommended_raise = scoring.get("recommended_raise")
        analysis.exit_likelihood = scoring.get("exit_likelihood")
        analysis.expected_exit_value = scoring.get("expected_exit_value")
        analysis.expected_exit_timeline = scoring.get("expected_exit_timeline")
        analysis.executive_summary = scoring.get("executive_summary")
        analysis.current_agent = None

        # Phase 4: Publish if consented
        if publish_consent:
            analysis.status = AnalysisStatus.enriching
            await db.commit()
            await _create_startup_from_analysis(db, analysis, consolidated_text)

        analysis.status = AnalysisStatus.complete
        analysis.completed_at = datetime.now(timezone.utc)
        await db.commit()

    logger.info(f"Analysis complete for {company_name}: score={scoring['overall_score']}")


async def run_analysis_worker() -> None:
    logger.info("Analysis worker started")
    while True:
        try:
            async with async_session() as db:
                job = await _claim_job(db)

            if job:
                logger.info(f"Processing analysis: {job.company_name} ({job.id})")
                await _process_job(job.id)
            else:
                await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Worker error: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_analysis_worker())
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/analysis_worker.py
git commit -m "feat: add analysis worker with parallel agent execution"
```

---

## Task 6: Backend API Router

**Files:**
- Create: `backend/app/api/analyze.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the analyze API router**

Create `backend/app/api/analyze.py`:

```python
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.models.pitch_analysis import (
    AgentType,
    AnalysisDocument,
    AnalysisReport,
    AnalysisStatus,
    PitchAnalysis,
)
from app.models.startup import Startup, StartupStatus
from app.models.user import SubscriptionStatus, User
from app.services import s3

router = APIRouter()

ALLOWED_TYPES = {"pdf", "docx", "doc", "pptx", "ppt", "xlsx", "xls", "csv", "md", "txt"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
MAX_TOTAL_SIZE = 50 * 1024 * 1024  # 50MB
MAX_FILES = 10


def _get_file_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext


def _analysis_to_dict(analysis: PitchAnalysis, include_reports: bool = False) -> dict:
    d = {
        "id": str(analysis.id),
        "company_name": analysis.company_name,
        "status": analysis.status.value if hasattr(analysis.status, "value") else analysis.status,
        "current_agent": analysis.current_agent,
        "overall_score": analysis.overall_score,
        "fundraising_likelihood": analysis.fundraising_likelihood,
        "recommended_raise": analysis.recommended_raise,
        "exit_likelihood": analysis.exit_likelihood,
        "expected_exit_value": analysis.expected_exit_value,
        "expected_exit_timeline": analysis.expected_exit_timeline,
        "executive_summary": analysis.executive_summary,
        "publish_consent": analysis.publish_consent,
        "is_free_analysis": analysis.is_free_analysis,
        "startup_id": str(analysis.startup_id) if analysis.startup_id else None,
        "error": analysis.error,
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
        "completed_at": analysis.completed_at.isoformat() if analysis.completed_at else None,
    }
    if include_reports and analysis.reports:
        d["reports"] = [
            {
                "id": str(r.id),
                "agent_type": r.agent_type.value if hasattr(r.agent_type, "value") else r.agent_type,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "score": r.score,
                "summary": r.summary,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in analysis.reports
        ]
    if analysis.documents:
        d["documents"] = [
            {
                "id": str(doc.id),
                "filename": doc.filename,
                "file_type": doc.file_type,
                "file_size_bytes": doc.file_size_bytes,
            }
            for doc in analysis.documents
        ]
    return d


@router.post("/api/analyze")
async def create_analysis(
    files: list[UploadFile] = File(...),
    company_name: str = Form(...),
    publish_consent: bool = Form(True),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check subscription
    count_result = await db.execute(
        select(func.count(PitchAnalysis.id)).where(
            PitchAnalysis.user_id == user.id,
            PitchAnalysis.status == AnalysisStatus.complete,
        )
    )
    completed_count = count_result.scalar() or 0

    sub_status = user.subscription_status
    if hasattr(sub_status, "value"):
        sub_status = sub_status.value

    if completed_count >= 1 and sub_status != "active":
        raise HTTPException(
            status_code=402,
            detail="Free analysis used. Subscribe for $19.99/mo for unlimited analyses.",
        )

    # Validate files
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Maximum {MAX_FILES} files allowed")
    if not files:
        raise HTTPException(400, "At least one file is required")

    total_size = 0
    for f in files:
        file_type = _get_file_type(f.filename or "")
        if file_type not in ALLOWED_TYPES:
            raise HTTPException(400, f"Unsupported file type: .{file_type}")

    is_free = completed_count == 0

    # Create analysis record
    analysis = PitchAnalysis(
        user_id=user.id,
        company_name=company_name,
        publish_consent=publish_consent,
        is_free_analysis=is_free,
        status=AnalysisStatus.pending,
    )
    db.add(analysis)
    await db.flush()

    # Upload files to S3 and create document records
    for f in files:
        data = await f.read()
        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(400, f"File {f.filename} exceeds 20MB limit")
        total_size += len(data)
        if total_size > MAX_TOTAL_SIZE:
            raise HTTPException(400, "Total upload size exceeds 50MB limit")

        file_type = _get_file_type(f.filename or "")
        s3_key = f"analyses/{analysis.id}/{uuid.uuid4()}/{f.filename}"

        s3.upload_file(data, s3_key)

        doc = AnalysisDocument(
            analysis_id=analysis.id,
            filename=f.filename or "unnamed",
            file_type=file_type,
            s3_key=s3_key,
            file_size_bytes=len(data),
        )
        db.add(doc)

    await db.commit()
    return {"id": str(analysis.id), "status": "pending"}


@router.get("/api/analyze")
async def list_analyses(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.user_id == user.id)
        .order_by(PitchAnalysis.created_at.desc())
    )
    analyses = result.scalars().all()
    return {
        "items": [
            {
                "id": str(a.id),
                "company_name": a.company_name,
                "status": a.status.value if hasattr(a.status, "value") else a.status,
                "overall_score": a.overall_score,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "completed_at": a.completed_at.isoformat() if a.completed_at else None,
            }
            for a in analyses
        ]
    }


@router.get("/api/analyze/{analysis_id}")
async def get_analysis(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
        .options(selectinload(PitchAnalysis.reports), selectinload(PitchAnalysis.documents))
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    return _analysis_to_dict(analysis, include_reports=True)


@router.get("/api/analyze/{analysis_id}/reports")
async def get_all_reports(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    result = await db.execute(
        select(AnalysisReport).where(AnalysisReport.analysis_id == analysis_id)
    )
    reports = result.scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "agent_type": r.agent_type.value if hasattr(r.agent_type, "value") else r.agent_type,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "score": r.score,
                "summary": r.summary,
                "report": r.report,
                "key_findings": r.key_findings,
                "error": r.error,
            }
            for r in reports
        ]
    }


@router.get("/api/analyze/{analysis_id}/reports/{agent_type}")
async def get_single_report(
    analysis_id: uuid.UUID,
    agent_type: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Analysis not found")

    result = await db.execute(
        select(AnalysisReport).where(
            AnalysisReport.analysis_id == analysis_id,
            AnalysisReport.agent_type == agent_type,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")

    return {
        "id": str(report.id),
        "agent_type": report.agent_type.value if hasattr(report.agent_type, "value") else report.agent_type,
        "status": report.status.value if hasattr(report.status, "value") else report.status,
        "score": report.score,
        "summary": report.summary,
        "report": report.report,
        "key_findings": report.key_findings,
        "error": report.error,
    }


@router.delete("/api/analyze/{analysis_id}")
async def delete_analysis(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
        .options(selectinload(PitchAnalysis.documents))
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    s3_keys = [doc.s3_key for doc in analysis.documents]
    if s3_keys:
        s3.delete_files(s3_keys)

    await db.delete(analysis)
    await db.commit()
    return {"ok": True}


@router.patch("/api/analyze/{analysis_id}")
async def update_analysis(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    publish_consent: Optional[bool] = None,
):
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    if publish_consent is not None:
        analysis.publish_consent = publish_consent
        if analysis.startup_id:
            result = await db.execute(
                select(Startup).where(Startup.id == analysis.startup_id)
            )
            startup = result.scalar_one_or_none()
            if startup:
                startup.status = StartupStatus.approved if publish_consent else StartupStatus.rejected

    await db.commit()
    return {"ok": True}


@router.post("/api/analyze/{analysis_id}/resubmit")
async def resubmit_analysis(
    analysis_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sub_status = user.subscription_status
    if hasattr(sub_status, "value"):
        sub_status = sub_status.value
    if sub_status != "active":
        raise HTTPException(402, "Subscription required for re-evaluation")

    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
        .options(
            selectinload(PitchAnalysis.documents),
            selectinload(PitchAnalysis.reports),
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    # Clean up old S3 files
    old_keys = [doc.s3_key for doc in analysis.documents]
    if old_keys:
        s3.delete_files(old_keys)

    # Delete old documents and reports
    for doc in analysis.documents:
        await db.delete(doc)
    for report in analysis.reports:
        await db.delete(report)

    # Upload new files
    if not files:
        raise HTTPException(400, "At least one file is required")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Maximum {MAX_FILES} files allowed")

    total_size = 0
    for f in files:
        file_type = _get_file_type(f.filename or "")
        if file_type not in ALLOWED_TYPES:
            raise HTTPException(400, f"Unsupported file type: .{file_type}")

        data = await f.read()
        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(400, f"File {f.filename} exceeds 20MB limit")
        total_size += len(data)
        if total_size > MAX_TOTAL_SIZE:
            raise HTTPException(400, "Total upload size exceeds 50MB limit")

        s3_key = f"analyses/{analysis.id}/{uuid.uuid4()}/{f.filename}"
        s3.upload_file(data, s3_key)

        doc = AnalysisDocument(
            analysis_id=analysis.id,
            filename=f.filename or "unnamed",
            file_type=file_type,
            s3_key=s3_key,
            file_size_bytes=len(data),
        )
        db.add(doc)

    # Reset analysis
    analysis.status = AnalysisStatus.pending
    analysis.current_agent = None
    analysis.overall_score = None
    analysis.fundraising_likelihood = None
    analysis.recommended_raise = None
    analysis.exit_likelihood = None
    analysis.expected_exit_value = None
    analysis.expected_exit_timeline = None
    analysis.executive_summary = None
    analysis.error = None
    analysis.claimed_at = None
    analysis.completed_at = None
    analysis.is_free_analysis = False

    await db.commit()
    return {"id": str(analysis.id), "status": "pending"}
```

- [ ] **Step 2: Register the router in main.py**

Add to `backend/app/main.py` imports:

```python
from app.api.analyze import router as analyze_router
```

Add to the router registrations:

```python
app.include_router(analyze_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/analyze.py backend/app/main.py
git commit -m "feat: add analyze API endpoints for pitch analysis"
```

---

## Task 7: Worker Dockerfile + Docker Compose

**Files:**
- Create: `backend/Dockerfile.worker`
- Modify: `docker-compose.prod.yml`

- [ ] **Step 1: Create the worker Dockerfile**

Create `backend/Dockerfile.worker`:

```dockerfile
FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends libreoffice-core libreoffice-writer libreoffice-impress && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/pyproject.toml backend/README.md* ./
RUN pip install --no-cache-dir .

COPY backend/ .

CMD ["python", "-m", "app.services.analysis_worker"]
```

- [ ] **Step 2: Add analysis_worker service to docker-compose.prod.yml**

Add this service block to `docker-compose.prod.yml`:

```yaml
  analysis_worker:
    build:
      context: .
      dockerfile: backend/Dockerfile.worker
    environment:
      - ACUTAL_DATABASE_URL=postgresql+asyncpg://postgres:${DB_PASSWORD}@db:5432/acutal
      - ACUTAL_PERPLEXITY_API_KEY=${ACUTAL_PERPLEXITY_API_KEY}
      - ACUTAL_ANTHROPIC_API_KEY=${ACUTAL_ANTHROPIC_API_KEY}
      - ACUTAL_AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - ACUTAL_AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
      - ACUTAL_S3_BUCKET_NAME=${S3_BUCKET_NAME:-deepthesis-pitch-documents}
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped
```

- [ ] **Step 3: Commit**

```bash
git add backend/Dockerfile.worker docker-compose.prod.yml
git commit -m "feat: add analysis worker Dockerfile and docker-compose service"
```

---

## Task 8: Frontend Types + API Client

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add analysis types**

Add to `frontend/lib/types.ts`:

```typescript
export interface AnalysisListItem {
  id: string;
  company_name: string;
  status: string;
  overall_score: number | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface AnalysisDocument {
  id: string;
  filename: string;
  file_type: string;
  file_size_bytes: number;
}

export interface AnalysisReportSummary {
  id: string;
  agent_type: string;
  status: string;
  score: number | null;
  summary: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface AnalysisReportFull {
  id: string;
  agent_type: string;
  status: string;
  score: number | null;
  summary: string | null;
  report: string | null;
  key_findings: string[] | null;
  error: string | null;
}

export interface AnalysisDetail {
  id: string;
  company_name: string;
  status: string;
  current_agent: string | null;
  overall_score: number | null;
  fundraising_likelihood: number | null;
  recommended_raise: string | null;
  exit_likelihood: number | null;
  expected_exit_value: string | null;
  expected_exit_timeline: string | null;
  executive_summary: string | null;
  publish_consent: boolean;
  is_free_analysis: boolean;
  startup_id: string | null;
  error: string | null;
  created_at: string | null;
  completed_at: string | null;
  reports: AnalysisReportSummary[];
  documents: AnalysisDocument[];
}
```

- [ ] **Step 2: Add analysis API methods**

Add to `frontend/lib/api.ts`:

```typescript
async createAnalysis(token: string, formData: FormData): Promise<{ id: string; status: string }> {
  const res = await fetch(`${API_URL}/api/analyze`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
},

async listAnalyses(token: string): Promise<{ items: AnalysisListItem[] }> {
  return apiFetch<{ items: AnalysisListItem[] }>(`/api/analyze`, { headers: authHeaders(token) });
},

async getAnalysis(token: string, id: string): Promise<AnalysisDetail> {
  return apiFetch<AnalysisDetail>(`/api/analyze/${id}`, { headers: authHeaders(token) });
},

async getAnalysisReports(token: string, id: string): Promise<{ items: AnalysisReportFull[] }> {
  return apiFetch<{ items: AnalysisReportFull[] }>(`/api/analyze/${id}/reports`, { headers: authHeaders(token) });
},

async deleteAnalysis(token: string, id: string): Promise<void> {
  await apiFetch(`/api/analyze/${id}`, { method: "DELETE", headers: authHeaders(token) });
},

async updateAnalysisConsent(token: string, id: string, publish_consent: boolean): Promise<void> {
  await apiFetch(`/api/analyze/${id}`, {
    method: "PATCH",
    headers: { ...authHeaders(token), "Content-Type": "application/json" },
    body: JSON.stringify({ publish_consent }),
  });
},

async resubmitAnalysis(token: string, id: string, formData: FormData): Promise<{ id: string; status: string }> {
  const res = await fetch(`${API_URL}/api/analyze/${id}/resubmit`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Resubmit failed: ${res.status}`);
  }
  return res.json();
},
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat: add analysis types and API client methods"
```

---

## Task 9: Frontend — Upload Page (`/analyze`)

**Files:**
- Create: `frontend/app/analyze/page.tsx`

- [ ] **Step 1: Create the upload page**

Create `frontend/app/analyze/page.tsx`:

```tsx
"use client";

import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";

const ALLOWED_EXTENSIONS = ["pdf", "docx", "doc", "pptx", "ppt", "xlsx", "xls", "csv", "md", "txt"];
const MAX_FILE_SIZE = 20 * 1024 * 1024;
const MAX_TOTAL_SIZE = 50 * 1024 * 1024;
const MAX_FILES = 10;

export default function AnalyzePage() {
  const { data: session, status: sessionStatus } = useSession();
  const token = (session as any)?.backendToken;
  const router = useRouter();

  const [files, setFiles] = useState<File[]>([]);
  const [companyName, setCompanyName] = useState("");
  const [publishConsent, setPublishConsent] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const validateFile = (file: File): string | null => {
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    if (!ALLOWED_EXTENSIONS.includes(ext)) return `Unsupported file type: .${ext}`;
    if (file.size > MAX_FILE_SIZE) return `${file.name} exceeds 20MB limit`;
    return null;
  };

  const addFiles = useCallback((newFiles: FileList | File[]) => {
    const arr = Array.from(newFiles);
    const errors: string[] = [];
    const valid: File[] = [];

    for (const f of arr) {
      const err = validateFile(f);
      if (err) errors.push(err);
      else valid.push(f);
    }

    setFiles((prev) => {
      const combined = [...prev, ...valid];
      if (combined.length > MAX_FILES) {
        errors.push(`Maximum ${MAX_FILES} files allowed`);
        return prev;
      }
      const totalSize = combined.reduce((s, f) => s + f.size, 0);
      if (totalSize > MAX_TOTAL_SIZE) {
        errors.push("Total size exceeds 50MB limit");
        return prev;
      }
      return combined;
    });

    if (errors.length) setError(errors.join(". "));
    else setError(null);
  }, []);

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setError(null);
  };

  const handleSubmit = async () => {
    if (!token || !companyName.trim() || files.length === 0) return;
    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("company_name", companyName.trim());
      formData.append("publish_consent", String(publishConsent));
      for (const f of files) {
        formData.append("files", f);
      }
      const result = await api.createAnalysis(token, formData);
      router.push(`/analyze/${result.id}`);
    } catch (e: any) {
      setError(e.message || "Upload failed");
      setUploading(false);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`;
    return `${(bytes / 1e3).toFixed(0)} KB`;
  };

  // Not logged in
  if (sessionStatus === "loading") {
    return (
      <div className="max-w-2xl mx-auto py-20 text-center text-text-tertiary">Loading...</div>
    );
  }

  if (!session) {
    return (
      <div className="max-w-2xl mx-auto py-20 text-center">
        <h1 className="font-serif text-3xl text-text-primary mb-4">Free Pitch Analysis</h1>
        <p className="text-text-secondary mb-2">
          Upload your pitch deck and documents. Our AI evaluates your startup across 8 critical
          factors and produces detailed reports with fundraising projections.
        </p>
        <p className="text-text-tertiary text-sm mb-8">First analysis is free. No credit card required.</p>
        <div className="flex gap-3 justify-center">
          <Link
            href="/auth/signup"
            className="px-6 py-2.5 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover transition"
          >
            Sign Up
          </Link>
          <Link
            href="/auth/signin"
            className="px-6 py-2.5 text-sm font-medium rounded border border-accent text-accent hover:bg-accent/5 transition"
          >
            Sign In
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-serif text-2xl text-text-primary">Analyze Your Pitch</h1>
        <Link href="/analyze/history" className="text-sm text-accent hover:text-accent-hover transition">
          View History
        </Link>
      </div>

      {/* Company name */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-text-primary mb-1.5">Company Name</label>
        <input
          type="text"
          value={companyName}
          onChange={(e) => setCompanyName(e.target.value)}
          placeholder="e.g. Acme Corp"
          className="w-full px-3 py-2 text-sm rounded border border-border bg-surface text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-1 focus:ring-accent"
        />
      </div>

      {/* Drop zone */}
      <div
        className={`rounded border-2 border-dashed p-8 text-center transition cursor-pointer ${
          dragOver ? "border-accent bg-accent/5" : "border-border bg-surface hover:border-accent/50"
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); addFiles(e.dataTransfer.files); }}
        onClick={() => document.getElementById("file-input")?.click()}
      >
        <input
          id="file-input"
          type="file"
          multiple
          accept={ALLOWED_EXTENSIONS.map((e) => `.${e}`).join(",")}
          className="hidden"
          onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }}
        />
        <p className="text-text-secondary text-sm mb-1">Drop files here or click to browse</p>
        <p className="text-text-tertiary text-xs">
          PDF, DOCX, DOC, PPTX, PPT, XLSX, XLS, CSV, MD, TXT — max 10 files, 20MB each
        </p>
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {files.map((f, i) => (
            <div key={i} className="flex items-center justify-between px-3 py-2 rounded border border-border bg-surface text-sm">
              <div className="flex items-center gap-2 min-w-0">
                <span className="px-1.5 py-0.5 text-xs rounded bg-accent/10 text-accent font-medium uppercase">
                  {f.name.split(".").pop()}
                </span>
                <span className="text-text-primary truncate">{f.name}</span>
                <span className="text-text-tertiary text-xs">{formatSize(f.size)}</span>
              </div>
              <button onClick={() => removeFile(i)} className="text-text-tertiary hover:text-red-500 text-xs ml-2">
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Publish consent */}
      <label className="flex items-start gap-2.5 mt-4 cursor-pointer">
        <input
          type="checkbox"
          checked={publishConsent}
          onChange={(e) => setPublishConsent(e.target.checked)}
          className="mt-0.5 rounded border-border bg-surface text-accent focus:ring-accent/20"
        />
        <span className="text-xs text-text-secondary leading-relaxed">
          Allow Deep Thesis to display your company on our public startup directory. Only your
          company name, industry, stage, and description are shown — reports, documents, and scores
          remain private.
        </span>
      </label>

      {/* Error */}
      {error && (
        <div className="mt-3 px-3 py-2 rounded bg-red-50 border border-red-200 text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Submit */}
      <button
        onClick={handleSubmit}
        disabled={uploading || !companyName.trim() || files.length === 0}
        className="mt-5 w-full py-2.5 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover disabled:opacity-50 transition"
      >
        {uploading ? "Uploading..." : "Analyze My Pitch"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/analyze/page.tsx
git commit -m "feat: add pitch analysis upload page"
```

---

## Task 10: Frontend — Results Page (`/analyze/[id]`)

**Files:**
- Create: `frontend/app/analyze/[id]/page.tsx`

- [ ] **Step 1: Create the results page**

Create `frontend/app/analyze/[id]/page.tsx`:

```tsx
"use client";

import { useSession } from "next-auth/react";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { AnalysisDetail, AnalysisReportFull } from "@/lib/types";

const AGENT_LABELS: Record<string, string> = {
  problem_solution: "Problem & Solution",
  market_tam: "Market & TAM",
  traction: "Traction",
  technology_ip: "Technology & IP",
  competition_moat: "Competition & Moat",
  team: "Team",
  gtm_business_model: "GTM & Business Model",
  financials_fundraising: "Financials & Fundraising",
};

function ScoreBadge({ score, size = "sm" }: { score: number | null; size?: "sm" | "lg" }) {
  if (score === null) return null;
  const color = score >= 70 ? "text-score-high" : score >= 40 ? "text-score-mid" : "text-score-low";
  const bg = score >= 70 ? "bg-score-high/10" : score >= 40 ? "bg-score-mid/10" : "bg-score-low/10";
  const textSize = size === "lg" ? "text-3xl" : "text-sm";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded font-medium tabular-nums ${bg} ${color} ${textSize}`}>
      {Math.round(score)}
    </span>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === "complete") return <span className="text-score-high">&#10003;</span>;
  if (status === "running") return <span className="animate-spin inline-block w-4 h-4 border-2 border-accent/30 border-t-accent rounded-full" />;
  if (status === "failed") return <span className="text-score-low">&times;</span>;
  return <span className="text-text-tertiary">&mdash;</span>;
}

export default function AnalysisResultPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();

  const [analysis, setAnalysis] = useState<AnalysisDetail | null>(null);
  const [reports, setReports] = useState<AnalysisReportFull[]>([]);
  const [activeTab, setActiveTab] = useState("overview");
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    if (!token || !id) return;
    try {
      const data = await api.getAnalysis(token, id);
      setAnalysis(data);

      if (data.status === "complete" || data.status === "failed") {
        const rData = await api.getAnalysisReports(token, id);
        setReports(rData.items || []);
      }
    } catch {
      // silent
    }
    setLoading(false);
  }, [token, id]);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    if (!analysis) return;
    if (analysis.status === "complete" || analysis.status === "failed") return;
    const timer = setInterval(fetchData, 3000);
    return () => clearInterval(timer);
  }, [analysis?.status, fetchData]);

  if (loading || !analysis) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  const isRunning = !["complete", "failed"].includes(analysis.status);
  const completedReports = analysis.reports?.filter((r) => r.status === "complete") || [];
  const progress = analysis.reports ? completedReports.length : 0;

  // PROGRESS VIEW
  if (isRunning) {
    return (
      <div className="max-w-2xl mx-auto">
        <h1 className="font-serif text-2xl text-text-primary mb-2">{analysis.company_name}</h1>
        <p className="text-text-tertiary text-sm mb-6">
          {analysis.status === "extracting" ? "Extracting text from documents..." :
           analysis.status === "enriching" ? "Creating public profile..." :
           "Running analysis agents..."}
        </p>

        {/* Progress bar */}
        <div className="w-full h-2 bg-border rounded-full mb-6 overflow-hidden">
          <div
            className="h-full bg-accent rounded-full transition-all duration-500"
            style={{ width: `${(progress / 8) * 100}%` }}
          />
        </div>

        {/* Agent status list */}
        <div className="rounded border border-border bg-surface divide-y divide-border">
          {Object.entries(AGENT_LABELS).map(([key, label]) => {
            const report = analysis.reports?.find((r) => r.agent_type === key);
            const status = report?.status || "pending";
            return (
              <div key={key} className="flex items-center justify-between px-4 py-3">
                <span className={`text-sm ${status === "running" ? "text-accent font-medium" : status === "complete" ? "text-text-primary" : "text-text-tertiary"}`}>
                  {label}
                </span>
                <div className="flex items-center gap-2">
                  {report?.score !== null && report?.score !== undefined && (
                    <ScoreBadge score={report.score} />
                  )}
                  <StatusIcon status={status} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // FAILED VIEW
  if (analysis.status === "failed") {
    return (
      <div className="max-w-2xl mx-auto text-center py-20">
        <h1 className="font-serif text-2xl text-text-primary mb-2">{analysis.company_name}</h1>
        <p className="text-score-low mb-4">Analysis failed</p>
        <p className="text-text-tertiary text-sm">{analysis.error || "An unexpected error occurred"}</p>
        <Link href="/analyze" className="inline-block mt-6 px-4 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover transition">
          Try Again
        </Link>
      </div>
    );
  }

  // RESULTS VIEW
  const tabs = ["overview", ...Object.keys(AGENT_LABELS)];
  const activeReport = reports.find((r) => r.agent_type === activeTab);

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-serif text-2xl text-text-primary">{analysis.company_name}</h1>
          <p className="text-text-tertiary text-xs mt-1">
            Analyzed {analysis.completed_at ? new Date(analysis.completed_at).toLocaleDateString() : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/analyze/history" className="text-xs text-text-tertiary hover:text-text-secondary">
            History
          </Link>
          <button
            onClick={async () => { if (confirm("Delete this analysis?")) { await api.deleteAnalysis(token, id); router.push("/analyze/history"); } }}
            className="text-xs text-red-500 hover:text-red-700"
          >
            Delete
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-0.5 overflow-x-auto border-b border-border mb-6">
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setActiveTab(t)}
            className={`px-3 py-2 text-xs font-medium whitespace-nowrap border-b-2 transition -mb-px ${
              activeTab === t
                ? "border-accent text-accent"
                : "border-transparent text-text-tertiary hover:text-text-secondary"
            }`}
          >
            {t === "overview" ? "Overview" : AGENT_LABELS[t]}
          </button>
        ))}
      </div>

      {/* Overview tab */}
      {activeTab === "overview" && (
        <div>
          {/* Score + metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div className="rounded border border-border bg-surface p-4 text-center">
              <p className="text-xs text-text-tertiary mb-1">Overall Score</p>
              <ScoreBadge score={analysis.overall_score} size="lg" />
            </div>
            <div className="rounded border border-border bg-surface p-4 text-center">
              <p className="text-xs text-text-tertiary mb-1">Fundraising Likelihood</p>
              <p className="text-xl font-medium text-text-primary tabular-nums">
                {analysis.fundraising_likelihood != null ? `${Math.round(analysis.fundraising_likelihood)}%` : "—"}
              </p>
            </div>
            <div className="rounded border border-border bg-surface p-4 text-center">
              <p className="text-xs text-text-tertiary mb-1">Recommended Raise</p>
              <p className="text-lg font-medium text-text-primary">{analysis.recommended_raise || "—"}</p>
            </div>
            <div className="rounded border border-border bg-surface p-4 text-center">
              <p className="text-xs text-text-tertiary mb-1">Exit Likelihood</p>
              <p className="text-xl font-medium text-text-primary tabular-nums">
                {analysis.exit_likelihood != null ? `${Math.round(analysis.exit_likelihood)}%` : "—"}
              </p>
            </div>
          </div>

          {/* Exit projections */}
          {(analysis.expected_exit_value || analysis.expected_exit_timeline) && (
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div className="rounded border border-border bg-surface p-4 text-center">
                <p className="text-xs text-text-tertiary mb-1">Expected Exit Value</p>
                <p className="text-lg font-medium text-text-primary">{analysis.expected_exit_value || "—"}</p>
              </div>
              <div className="rounded border border-border bg-surface p-4 text-center">
                <p className="text-xs text-text-tertiary mb-1">Expected Timeline</p>
                <p className="text-lg font-medium text-text-primary">{analysis.expected_exit_timeline || "—"}</p>
              </div>
            </div>
          )}

          {/* Executive summary */}
          {analysis.executive_summary && (
            <div className="rounded border border-border bg-surface p-4 mb-6">
              <h3 className="text-sm font-medium text-text-primary mb-2">Executive Summary</h3>
              <p className="text-sm text-text-secondary leading-relaxed">{analysis.executive_summary}</p>
            </div>
          )}

          {/* Score cards grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Object.entries(AGENT_LABELS).map(([key, label]) => {
              const report = reports.find((r) => r.agent_type === key);
              return (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  className="rounded border border-border bg-surface p-4 text-left hover:border-accent/50 transition"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-text-primary">{label}</span>
                    <ScoreBadge score={report?.score ?? null} />
                  </div>
                  <p className="text-xs text-text-secondary line-clamp-2">{report?.summary || "—"}</p>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Agent report tabs */}
      {activeTab !== "overview" && activeReport && (
        <div>
          <div className="flex items-center gap-3 mb-4">
            <ScoreBadge score={activeReport.score} size="lg" />
            <p className="text-sm text-text-secondary">{activeReport.summary}</p>
          </div>

          {activeReport.key_findings && activeReport.key_findings.length > 0 && (
            <div className="rounded border border-border bg-surface p-4 mb-4">
              <h3 className="text-sm font-medium text-text-primary mb-2">Key Findings</h3>
              <ul className="space-y-1">
                {activeReport.key_findings.map((f, i) => (
                  <li key={i} className="text-sm text-text-secondary flex gap-2">
                    <span className="text-accent">&#x2022;</span>
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {activeReport.report && (
            <div className="rounded border border-border bg-surface p-4 prose prose-sm max-w-none text-text-primary">
              <div dangerouslySetInnerHTML={{ __html: activeReport.report.replace(/\n/g, "<br />") }} />
            </div>
          )}

          {activeReport.status === "failed" && (
            <div className="rounded border border-red-200 bg-red-50 p-4 text-red-700 text-sm">
              Agent failed: {activeReport.error || "Unknown error"}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/analyze/\[id\]/page.tsx
git commit -m "feat: add pitch analysis results page with progress and tabs"
```

---

## Task 11: Frontend — History Page (`/analyze/history`)

**Files:**
- Create: `frontend/app/analyze/history/page.tsx`

- [ ] **Step 1: Create the history page**

Create `frontend/app/analyze/history/page.tsx`:

```tsx
"use client";

import { useSession } from "next-auth/react";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { AnalysisListItem } from "@/lib/types";

const STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  extracting: "Extracting",
  analyzing: "Analyzing",
  enriching: "Publishing",
  complete: "Complete",
  failed: "Failed",
};

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-zinc-100 text-zinc-600",
  extracting: "bg-yellow-100 text-yellow-800",
  analyzing: "bg-blue-100 text-blue-800",
  enriching: "bg-purple-100 text-purple-800",
  complete: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

export default function AnalysisHistoryPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const [analyses, setAnalyses] = useState<AnalysisListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    api.listAnalyses(token).then((data) => {
      setAnalyses(data.items || []);
      setLoading(false);
    });
  }, [token]);

  if (loading) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-serif text-2xl text-text-primary">Analysis History</h1>
        <Link
          href="/analyze"
          className="px-4 py-2 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover transition"
        >
          New Analysis
        </Link>
      </div>

      {analyses.length === 0 ? (
        <div className="text-center py-20 text-text-tertiary text-sm">
          No analyses yet.{" "}
          <Link href="/analyze" className="text-accent hover:text-accent-hover">
            Submit your first pitch
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {analyses.map((a) => {
            const scoreColor =
              a.overall_score !== null
                ? a.overall_score >= 70
                  ? "text-score-high"
                  : a.overall_score >= 40
                    ? "text-score-mid"
                    : "text-score-low"
                : "text-text-tertiary";

            return (
              <Link
                key={a.id}
                href={`/analyze/${a.id}`}
                className="block rounded border border-border bg-surface p-4 hover:border-accent/50 transition"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-medium text-text-primary">{a.company_name}</h3>
                    <p className="text-xs text-text-tertiary mt-0.5">
                      {a.created_at ? new Date(a.created_at).toLocaleDateString() : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    {a.overall_score !== null && (
                      <span className={`text-lg font-medium tabular-nums ${scoreColor}`}>
                        {Math.round(a.overall_score)}
                      </span>
                    )}
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[a.status] || "bg-zinc-100 text-zinc-600"}`}>
                      {STATUS_LABELS[a.status] || a.status}
                    </span>
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/analyze/history/page.tsx
git commit -m "feat: add pitch analysis history page"
```

---

## Task 12: Navigation Updates

**Files:**
- Modify: `frontend/components/Navbar.tsx`

- [ ] **Step 1: Add Analyze link to Navbar**

In `frontend/components/Navbar.tsx`, add a new link after the existing navigation links. Find the nav links section and add:

```tsx
<Link href="/analyze" className="text-sm text-text-secondary hover:text-text-primary transition">
  Analyze
</Link>
```

Place it after "Companies" and before "Insights" in the navigation order.

- [ ] **Step 2: Commit**

```bash
git add frontend/components/Navbar.tsx
git commit -m "feat: add Analyze link to navbar"
```

---

## Task 13: Landing Page CTA

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Add pitch analysis CTA to landing page**

In `frontend/app/page.tsx`, find the CTA section near the bottom of the page and add a prominent link to `/analyze`. Add this section before the existing CTA:

```tsx
{/* Pitch Analysis CTA */}
<section className="rounded border border-accent/20 bg-accent/5 p-8 text-center mb-12">
  <h2 className="font-serif text-2xl text-text-primary mb-2">Free Pitch Analysis</h2>
  <p className="text-text-secondary text-sm mb-4 max-w-lg mx-auto">
    Upload your pitch deck and documents. Our AI evaluates your startup across 8 critical
    factors — market, team, traction, technology, and more — with detailed reports and
    fundraising projections.
  </p>
  <a
    href="/analyze"
    className="inline-block px-6 py-2.5 text-sm font-medium rounded bg-accent text-white hover:bg-accent-hover transition"
  >
    Analyze Your Pitch — Free
  </a>
</section>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat: add pitch analysis CTA to landing page"
```

---

## Task 14: Publish Consent Integration

This is already implemented in the worker (Task 5, `_create_startup_from_analysis`) and the API (Task 6, PATCH endpoint). This task verifies the integration works end-to-end.

- [ ] **Step 1: Verify the enrichment import works**

The worker imports `from app.services.enrichment import run_enrichment_pipeline`. Verify this function exists and accepts `(db: AsyncSession, startup: Startup)` as arguments. Check `backend/app/services/enrichment.py`.

- [ ] **Step 2: Verify the PATCH toggle logic**

The PATCH `/api/analyze/{id}` endpoint toggles `publish_consent` and sets the linked Startup status to `approved` or `rejected`. This was implemented in Task 6. Verify the Startup model has `StartupStatus.approved` and `StartupStatus.rejected` values.

- [ ] **Step 3: Commit (if any fixes needed)**

```bash
git commit -m "fix: verify publish consent integration"
```

---

## Self-Review

**Spec coverage:**
- ✅ S3 file upload with type/size validation
- ✅ Document text extraction (PDF, DOCX, DOC, PPTX, PPT, XLSX, XLS, CSV, MD, TXT)
- ✅ 8 parallel Claude analysis agents with rubrics
- ✅ Final scoring agent (Opus)
- ✅ Worker container with job loop
- ✅ All API endpoints (create, list, get, reports, delete, patch, resubmit)
- ✅ Frontend upload page with auth gate
- ✅ Frontend results page with progress + tabs
- ✅ Frontend history page
- ✅ Subscription gating (first free, then 402)
- ✅ Publish consent → Startup creation
- ✅ Docker compose + worker Dockerfile
- ✅ Navigation updates

**Type consistency:**
- `AnalysisStatus`, `AgentType`, `ReportStatus` enums used consistently across models, worker, and API
- `AGENT_LABELS` dict matches between frontend and backend AgentType values
- API response shapes match frontend TypeScript types

**No placeholders found.**
