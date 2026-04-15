# Investment Memo Generation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add investment memo generation to completed pitch analyses — Claude orchestrates synthesis of analysis data + fresh Perplexity research into a downloadable VC-style memo (PDF/DOCX).

**Architecture:** New `InvestmentMemo` model with its own migration. Dedicated `memo_generator.py` service runs 4 parallel Perplexity research calls, then one Claude synthesis call, then formats PDF/DOCX with reportlab/python-docx and uploads to S3. New `memo.py` API router exposes 4 endpoints. Frontend adds a "Generate Investment Memo" button + memo tab to the analysis result page.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, Alembic (raw SQL migration), Anthropic SDK (Claude), Perplexity Sonar Pro API (via httpx), reportlab (PDF), python-docx (DOCX), boto3 (S3), Next.js/React/TypeScript (frontend)

---

## File Structure

### New files:
| File | Responsibility |
|------|---------------|
| `backend/app/models/investment_memo.py` | InvestmentMemo model + MemoStatus enum |
| `backend/alembic/versions/r6s7t8u9v0w1_add_investment_memos_table.py` | DB migration |
| `backend/app/api/memo.py` | 4 API endpoints (generate, regenerate, get, download) |
| `backend/app/services/memo_generator.py` | 3-phase generation pipeline |

### Modified files (additive only):
| File | Change |
|------|--------|
| `backend/app/models/__init__.py` | Import InvestmentMemo |
| `backend/app/models/pitch_analysis.py` | Add `memo` relationship |
| `backend/app/main.py` | Include memo router |
| `frontend/lib/types.ts` | Add InvestmentMemo type |
| `frontend/lib/api.ts` | Add 4 memo API methods |
| `frontend/app/analyze/[id]/page.tsx` | Add memo button, tab, polling |

---

### Task 1: InvestmentMemo Model

**Files:**
- Create: `backend/app/models/investment_memo.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/pitch_analysis.py`

- [ ] **Step 1: Create the InvestmentMemo model file**

Create `backend/app/models/investment_memo.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class MemoStatus(enum.Enum):
    pending = "pending"
    researching = "researching"
    generating = "generating"
    formatting = "formatting"
    complete = "complete"
    failed = "failed"


memostatus_enum = ENUM(
    "pending", "researching", "generating", "formatting", "complete", "failed",
    name="memostatus", create_type=False,
)


class InvestmentMemo(Base):
    __tablename__ = "investment_memos"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pitch_analyses.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    status = mapped_column(memostatus_enum, nullable=False, default="pending")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    s3_key_pdf: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    s3_key_docx: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    analysis = relationship("PitchAnalysis", back_populates="memo")
```

- [ ] **Step 2: Add memo relationship to PitchAnalysis**

In `backend/app/models/pitch_analysis.py`, add after the `reports` relationship (around line 73):

```python
    memo: Mapped["InvestmentMemo | None"] = relationship(
        back_populates="analysis", uselist=False, cascade="all, delete-orphan"
    )
```

Also add the import at the top of the file (after existing imports from the same package — this is a forward reference so no circular import issue since it uses string annotation).

- [ ] **Step 3: Register InvestmentMemo in models __init__.py**

In `backend/app/models/__init__.py`, add:

```python
from app.models.investment_memo import InvestmentMemo
```

And add `"InvestmentMemo"` to the `__all__` list.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/investment_memo.py backend/app/models/__init__.py backend/app/models/pitch_analysis.py
git commit -m "feat(memo): add InvestmentMemo model and MemoStatus enum"
```

---

### Task 2: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/r6s7t8u9v0w1_add_investment_memos_table.py`

- [ ] **Step 1: Create the migration file**

Create `backend/alembic/versions/r6s7t8u9v0w1_add_investment_memos_table.py`:

```python
"""Add investment_memos table

Revision ID: r6s7t8u9v0w1
Revises: q5r6s7t8u9v0
Create Date: 2026-04-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "r6s7t8u9v0w1"
down_revision = "q5r6s7t8u9v0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE memostatus AS ENUM (
                'pending', 'researching', 'generating', 'formatting', 'complete', 'failed'
            );
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS investment_memos (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            analysis_id UUID NOT NULL UNIQUE REFERENCES pitch_analyses(id) ON DELETE CASCADE,
            status memostatus NOT NULL DEFAULT 'pending',
            content TEXT,
            s3_key_pdf VARCHAR(1000),
            s3_key_docx VARCHAR(1000),
            error TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            completed_at TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_investment_memos_analysis_id
        ON investment_memos (analysis_id)
    """)


def downgrade() -> None:
    op.drop_index("ix_investment_memos_analysis_id", table_name="investment_memos")
    op.drop_table("investment_memos")
    op.execute("DROP TYPE IF EXISTS memostatus")
```

- [ ] **Step 2: Commit**

```bash
git add backend/alembic/versions/r6s7t8u9v0w1_add_investment_memos_table.py
git commit -m "feat(memo): add investment_memos migration"
```

---

### Task 3: Memo Generator Service

**Files:**
- Create: `backend/app/services/memo_generator.py`

- [ ] **Step 1: Create the memo generator service**

Create `backend/app/services/memo_generator.py`:

```python
"""Investment memo generation pipeline.

Phase 1: Perplexity research (4 parallel calls)
Phase 2: Claude synthesis (1 call producing markdown memo)
Phase 3: Format PDF + DOCX, upload to S3
"""
import asyncio
import io
import logging
import uuid
from datetime import datetime, timezone

import anthropic
import httpx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.session import async_session
from app.models.investment_memo import InvestmentMemo, MemoStatus
from app.models.pitch_analysis import AnalysisReport, PitchAnalysis
from app.services import s3

logger = logging.getLogger(__name__)

# Deep Thesis brand colors (matches analyst_reports.py)
BRAND_ACCENT = "#F28C28"
BRAND_TEXT = "#1A1A1A"
BRAND_TEXT_SECONDARY = "#6B6B6B"

AGENT_LABELS = {
    "problem_solution": "Problem & Solution",
    "market_tam": "Market & TAM",
    "traction": "Traction",
    "technology_ip": "Technology & IP",
    "competition_moat": "Competition & Moat",
    "team": "Team",
    "gtm_business_model": "GTM & Business Model",
    "financials_fundraising": "Financials & Fundraising",
}


# ── Phase 1: Perplexity Research ─────────────────────────────────────

async def _research_perplexity(system_prompt: str, query: str) -> str:
    """Call Perplexity Sonar Pro API. Returns response text or error message."""
    if not settings.perplexity_api_key:
        return "[Perplexity API key not configured — skipping research]"
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
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 4096,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            return f"[Perplexity error: {resp.status_code}]"
    except Exception as e:
        logger.warning("Perplexity research failed: %s", e)
        return f"[Research unavailable: {e}]"


async def _run_research(company_name: str, market_context: str, stage: str) -> dict[str, str]:
    """Run 4 parallel Perplexity research queries. Returns dict of research results."""
    system = "Provide factual, detailed research data. Include specific numbers, dates, company names, and sources where available. Be thorough."

    queries = {
        "recent_news": f"Latest news about {company_name} in the last 6 months: funding announcements, product launches, partnerships, press coverage, hiring activity",
        "competitive_landscape": f"Current competitors to {company_name} in {market_context}: their recent funding rounds, market positioning, strengths and weaknesses, market share",
        "market_data": f"Current market size, growth rate (CAGR), trends, and outlook for {market_context} in 2025-2026. Include TAM/SAM estimates from research firms.",
        "comparable_deals": f"Recent VC investment deals and valuations for {stage} startups in {market_context}. Notable exits, M&A activity, and valuation multiples.",
    }

    tasks = {key: _research_perplexity(system, query) for key, query in queries.items()}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    research = {}
    for key, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            research[key] = f"[Research failed: {result}]"
        else:
            research[key] = result

    return research


# ── Phase 2: Claude Synthesis ────────────────────────────────────────

MEMO_SYSTEM_PROMPT = """You are a senior venture capital analyst at a top-tier VC firm. You are writing a formal investment memo for your investment committee.

Write a comprehensive, professional investment memo in markdown format. The memo should be thorough, data-driven, and balanced — highlighting both opportunities and risks.

## Required Sections

1. **Executive Summary** — Investment thesis in 3-4 sentences. Include overall score, key strengths, key risks, and your recommendation (Invest / Pass / Watch).

2. **Company Overview** — What the company does, founding stage, product description, and current status.

3. **Market Opportunity** — TAM/SAM/SOM analysis, market growth drivers, timing assessment. Use both the analysis data and fresh market research provided.

4. **Product & Technology** — Solution description, technical differentiation, IP/defensibility, technical risks.

5. **Competitive Landscape** — Key competitors with specific details, competitive positioning, moat analysis. Incorporate fresh competitive intelligence from research.

6. **Team Assessment** — Founder backgrounds, team composition, key gaps, founder-market fit.

7. **Traction & Financials** — Current metrics, growth trajectory, unit economics, financial projections assessment.

8. **Investment Terms** — Recommended raise amount, valuation context based on comparable deals, use of funds assessment.

9. **Risk Factors** — Top 5-7 risks ranked by severity, with mitigation strategies for each.

10. **Recommendation** — Final verdict: **Invest**, **Pass**, or **Watch**. Include conviction level (High/Medium/Low) and specific conditions or milestones that would change your recommendation.

## Formatting Rules
- Use markdown headers (## for sections, ### for subsections)
- Use bullet points for lists
- Use **bold** for emphasis on key metrics and findings
- Include specific numbers and data points wherever possible
- Be concise but thorough — target 2000-3000 words
- Write in third person, professional tone
- Do NOT include a title — the system will add one"""


async def _synthesize_memo(
    company_name: str,
    analysis: dict,
    reports: list[dict],
    research: dict[str, str],
) -> str:
    """Call Claude to synthesize all data into a markdown investment memo."""
    # Build the analysis context
    reports_text = ""
    for r in reports:
        label = AGENT_LABELS.get(r["agent_type"], r["agent_type"])
        reports_text += f"\n### {label} (Score: {r['score']}/100)\n"
        reports_text += f"**Summary:** {r['summary']}\n\n"
        reports_text += f"{r['report']}\n\n"
        if r.get("key_findings"):
            reports_text += "**Key Findings:**\n"
            for f in r["key_findings"]:
                reports_text += f"- {f}\n"
            reports_text += "\n"

    user_message = f"""# Company: {company_name}

## Analysis Metadata
- **Overall Score:** {analysis['overall_score']}/100
- **Fundraising Likelihood:** {analysis.get('fundraising_likelihood', 'N/A')}%
- **Recommended Raise:** {analysis.get('recommended_raise', 'N/A')}
- **Exit Likelihood:** {analysis.get('exit_likelihood', 'N/A')}%
- **Expected Exit Value:** {analysis.get('expected_exit_value', 'N/A')}
- **Expected Exit Timeline:** {analysis.get('expected_exit_timeline', 'N/A')}

## Executive Summary from Analysis
{analysis.get('executive_summary', 'N/A')}

## Detailed Agent Reports
{reports_text}

## Fresh Market Research

### Recent News & Developments
{research.get('recent_news', 'No data available')}

### Competitive Landscape Update
{research.get('competitive_landscape', 'No data available')}

### Market Data
{research.get('market_data', 'No data available')}

### Comparable Deals & Valuations
{research.get('comparable_deals', 'No data available')}

---

Write the investment memo now. Synthesize ALL the above data — both the analysis reports and the fresh research — into a cohesive, professional document."""

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=MEMO_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


# ── Phase 3: PDF + DOCX Formatting ──────────────────────────────────

def _generate_memo_pdf(company_name: str, content: str) -> bytes:
    """Convert markdown memo to branded PDF using reportlab."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "MemoTitle", parent=styles["Title"], fontSize=28,
        textColor=HexColor(BRAND_ACCENT), spaceAfter=12,
    ))
    styles.add(ParagraphStyle(
        "MemoSubtitle", parent=styles["Title"], fontSize=18,
        textColor=HexColor("#333333"), spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "MemoDate", parent=styles["Normal"], fontSize=12,
        textColor=HexColor("#808080"), alignment=1, spaceAfter=24,
    ))
    styles.add(ParagraphStyle(
        "MemoH2", parent=styles["Heading2"], fontSize=16,
        textColor=HexColor(BRAND_TEXT), spaceBefore=14, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        "MemoH3", parent=styles["Heading3"], fontSize=13,
        textColor=HexColor("#333333"), spaceBefore=10, spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "MemoBody", parent=styles["BodyText"], fontSize=10,
        leading=14, spaceAfter=8,
    ))
    styles.add(ParagraphStyle(
        "MemoBullet", parent=styles["BodyText"], fontSize=10,
        leading=14, leftIndent=20, bulletIndent=10, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "MemoFooter", parent=styles["Normal"], fontSize=8,
        textColor=HexColor("#808080"), alignment=1,
    ))

    story = []

    # Cover page
    story.append(Spacer(1, 2 * inch))
    story.append(Paragraph("Deep Thesis", styles["MemoTitle"]))
    story.append(Paragraph("Investment Memo", styles["MemoSubtitle"]))
    story.append(Spacer(1, 0.5 * inch))
    safe_name = company_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    story.append(Paragraph(safe_name, styles["MemoSubtitle"]))
    story.append(Paragraph(datetime.now(timezone.utc).strftime("%B %d, %Y"), styles["MemoDate"]))
    story.append(PageBreak())

    # Parse markdown content into paragraphs
    for block in content.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        safe = block.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        if block.startswith("## "):
            story.append(Paragraph(safe[3:], styles["MemoH2"]))
        elif block.startswith("### "):
            story.append(Paragraph(safe[4:], styles["MemoH3"]))
        elif block.startswith("- ") or block.startswith("* "):
            for line in block.split("\n"):
                line = line.strip()
                if line.startswith("- ") or line.startswith("* "):
                    safe_line = line[2:].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    # Handle bold markers
                    safe_line = safe_line.replace("**", "<b>", 1).replace("**", "</b>", 1)
                    story.append(Paragraph(f"• {safe_line}", styles["MemoBullet"]))
        else:
            # Handle inline bold markers for body text
            safe = safe.replace("**", "<b>", 1)
            while "**" in safe:
                safe = safe.replace("**", "</b>", 1)
                if "**" in safe:
                    safe = safe.replace("**", "<b>", 1)
            story.append(Paragraph(safe, styles["MemoBody"]))

    # Footer
    story.append(Spacer(1, 24))
    story.append(Paragraph("Generated by Deep Thesis | Confidential", styles["MemoFooter"]))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


def _generate_memo_docx(company_name: str, content: str) -> bytes:
    """Convert markdown memo to branded DOCX using python-docx."""
    doc = Document()

    # Cover page
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Deep Thesis")
    run.font.size = Pt(28)
    run.font.color.rgb = RGBColor(0xF2, 0x8C, 0x28)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Investment Memo")
    run.font.size = Pt(22)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(company_name)
    run.font.size = Pt(18)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(datetime.now(timezone.utc).strftime("%B %d, %Y"))
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(128, 128, 128)

    doc.add_page_break()

    # Parse markdown content
    for block in content.split("\n\n"):
        block = block.strip()
        if not block:
            continue

        if block.startswith("## "):
            doc.add_heading(block[3:], level=2)
        elif block.startswith("### "):
            doc.add_heading(block[4:], level=3)
        elif block.startswith("- ") or block.startswith("* "):
            for line in block.split("\n"):
                line = line.strip()
                if line.startswith("- ") or line.startswith("* "):
                    doc.add_paragraph(line[2:], style="List Bullet")
        else:
            doc.add_paragraph(block)

    # Footer
    section = doc.sections[0]
    footer = section.footer
    footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer_para.add_run("Generated by Deep Thesis | Confidential")
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor(128, 128, 128)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


# ── Main Entry Point ─────────────────────────────────────────────────

async def run_memo_generation(memo_id: str) -> None:
    """Main entry point for background memo generation."""
    mid = uuid.UUID(memo_id)

    async with async_session() as db:
        try:
            # Load memo + analysis + reports
            result = await db.execute(
                select(InvestmentMemo).where(InvestmentMemo.id == mid)
            )
            memo = result.scalar_one_or_none()
            if not memo:
                logger.error("Memo %s not found", memo_id)
                return

            result = await db.execute(
                select(PitchAnalysis)
                .where(PitchAnalysis.id == memo.analysis_id)
                .options(selectinload(PitchAnalysis.reports))
            )
            analysis = result.scalar_one()

            # Gather analysis data
            analysis_data = {
                "overall_score": analysis.overall_score,
                "fundraising_likelihood": analysis.fundraising_likelihood,
                "recommended_raise": analysis.recommended_raise,
                "exit_likelihood": analysis.exit_likelihood,
                "expected_exit_value": analysis.expected_exit_value,
                "expected_exit_timeline": analysis.expected_exit_timeline,
                "executive_summary": analysis.executive_summary,
            }

            reports_data = []
            market_context = ""
            for r in analysis.reports:
                agent_type = r.agent_type.value if hasattr(r.agent_type, "value") else r.agent_type
                report_dict = {
                    "agent_type": agent_type,
                    "score": r.score,
                    "summary": r.summary or "",
                    "report": r.report or "",
                    "key_findings": r.key_findings or [],
                }
                reports_data.append(report_dict)
                # Extract market context from the market_tam report
                if agent_type == "market_tam" and r.summary:
                    market_context = r.summary

            company_name = analysis.company_name
            if not market_context:
                market_context = f"{company_name} industry"

            # Determine stage string for research queries
            stage = "seed"
            if analysis.recommended_raise:
                raise_str = analysis.recommended_raise.lower()
                if "series a" in raise_str or "$5" in raise_str or "$10" in raise_str:
                    stage = "series_a"
                elif "series b" in raise_str:
                    stage = "series_b"
                elif "pre" in raise_str:
                    stage = "pre_seed"

            # ── Phase 1: Research ──
            memo.status = MemoStatus.researching
            await db.commit()

            research = await _run_research(company_name, market_context, stage)

            # ── Phase 2: Synthesis ──
            memo.status = MemoStatus.generating
            await db.commit()

            content = await _synthesize_memo(company_name, analysis_data, reports_data, research)
            memo.content = content

            # ── Phase 3: Formatting ──
            memo.status = MemoStatus.formatting
            await db.commit()

            pdf_bytes = _generate_memo_pdf(company_name, content)
            docx_bytes = _generate_memo_docx(company_name, content)

            pdf_key = f"memos/{memo.id}/memo.pdf"
            docx_key = f"memos/{memo.id}/memo.docx"

            s3.upload_file(pdf_bytes, pdf_key)
            s3.upload_file(docx_bytes, docx_key)

            memo.s3_key_pdf = pdf_key
            memo.s3_key_docx = docx_key
            memo.status = MemoStatus.complete
            memo.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info("Memo %s generated for %s (PDF: %d bytes, DOCX: %d bytes)",
                        memo_id, company_name, len(pdf_bytes), len(docx_bytes))

        except Exception as e:
            logger.error("Memo generation failed for %s: %s", memo_id, e)
            try:
                memo.status = MemoStatus.failed
                memo.error = str(e)[:500]
                await db.commit()
            except Exception:
                logger.error("Failed to update memo status for %s", memo_id)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/memo_generator.py
git commit -m "feat(memo): add memo generation service — Perplexity research + Claude synthesis + PDF/DOCX"
```

---

### Task 4: Memo API Endpoints

**Files:**
- Create: `backend/app/api/memo.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the memo API router**

Create `backend/app/api/memo.py`:

```python
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.investment_memo import InvestmentMemo, MemoStatus
from app.models.pitch_analysis import AnalysisStatus, PitchAnalysis
from app.models.user import User
from app.services import s3
from app.services.memo_generator import run_memo_generation

router = APIRouter()


async def _get_user_analysis(
    analysis_id: uuid.UUID, user: User, db: AsyncSession
) -> PitchAnalysis:
    """Load analysis and verify ownership."""
    result = await db.execute(
        select(PitchAnalysis).where(
            PitchAnalysis.id == analysis_id,
            PitchAnalysis.user_id == user.id,
        )
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    return analysis


@router.post("/api/analyze/{analysis_id}/memo")
async def generate_memo(
    analysis_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger investment memo generation for a completed analysis."""
    analysis = await _get_user_analysis(analysis_id, user, db)

    status_val = analysis.status.value if hasattr(analysis.status, "value") else analysis.status
    if status_val != "complete":
        raise HTTPException(400, "Analysis must be complete before generating a memo")

    # Check for existing memo
    result = await db.execute(
        select(InvestmentMemo).where(InvestmentMemo.analysis_id == analysis_id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing_status = existing.status.value if hasattr(existing.status, "value") else existing.status
        if existing_status in ("pending", "researching", "generating", "formatting"):
            raise HTTPException(409, "Memo generation already in progress")
        if existing_status == "complete":
            raise HTTPException(409, "Memo already exists. Use the regenerate endpoint.")
        # Failed memo — delete and recreate
        await db.delete(existing)
        await db.flush()

    memo = InvestmentMemo(analysis_id=analysis_id)
    db.add(memo)
    await db.commit()
    await db.refresh(memo)

    background_tasks.add_task(run_memo_generation, str(memo.id))

    return {"id": str(memo.id), "status": "pending"}


@router.post("/api/analyze/{analysis_id}/memo/regenerate")
async def regenerate_memo(
    analysis_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate investment memo (deletes existing, creates fresh)."""
    analysis = await _get_user_analysis(analysis_id, user, db)

    status_val = analysis.status.value if hasattr(analysis.status, "value") else analysis.status
    if status_val != "complete":
        raise HTTPException(400, "Analysis must be complete")

    # Delete existing memo and S3 files
    result = await db.execute(
        select(InvestmentMemo).where(InvestmentMemo.analysis_id == analysis_id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        # Clean up S3
        keys_to_delete = [k for k in [existing.s3_key_pdf, existing.s3_key_docx] if k]
        if keys_to_delete:
            s3.delete_files(keys_to_delete)
        await db.delete(existing)
        await db.flush()

    memo = InvestmentMemo(analysis_id=analysis_id)
    db.add(memo)
    await db.commit()
    await db.refresh(memo)

    background_tasks.add_task(run_memo_generation, str(memo.id))

    return {"id": str(memo.id), "status": "pending"}


@router.get("/api/analyze/{analysis_id}/memo")
async def get_memo(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get memo status and content."""
    await _get_user_analysis(analysis_id, user, db)

    result = await db.execute(
        select(InvestmentMemo).where(InvestmentMemo.analysis_id == analysis_id)
    )
    memo = result.scalar_one_or_none()
    if not memo:
        raise HTTPException(404, "No memo exists for this analysis")

    status_val = memo.status.value if hasattr(memo.status, "value") else memo.status

    response = {
        "id": str(memo.id),
        "status": status_val,
        "content": memo.content,
        "error": memo.error,
        "created_at": memo.created_at.isoformat() if memo.created_at else None,
        "completed_at": memo.completed_at.isoformat() if memo.completed_at else None,
        "pdf_url": None,
        "docx_url": None,
    }

    if status_val == "complete":
        response["pdf_url"] = f"/api/analyze/{analysis_id}/memo/download/pdf"
        response["docx_url"] = f"/api/analyze/{analysis_id}/memo/download/docx"

    return response


@router.get("/api/analyze/{analysis_id}/memo/download/{fmt}")
async def download_memo(
    analysis_id: uuid.UUID,
    fmt: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download memo as PDF or DOCX."""
    await _get_user_analysis(analysis_id, user, db)

    if fmt not in ("pdf", "docx"):
        raise HTTPException(400, "Format must be 'pdf' or 'docx'")

    result = await db.execute(
        select(InvestmentMemo).where(InvestmentMemo.analysis_id == analysis_id)
    )
    memo = result.scalar_one_or_none()
    if not memo:
        raise HTTPException(404, "No memo exists")

    status_val = memo.status.value if hasattr(memo.status, "value") else memo.status
    if status_val != "complete":
        raise HTTPException(400, "Memo not yet complete")

    s3_key = memo.s3_key_pdf if fmt == "pdf" else memo.s3_key_docx
    if not s3_key:
        raise HTTPException(404, "File not found")

    file_data = s3.download_file(s3_key)

    content_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    import io
    return StreamingResponse(
        io.BytesIO(file_data),
        media_type=content_types[fmt],
        headers={"Content-Disposition": f"attachment; filename=investment-memo-{analysis_id}.{fmt}"},
    )
```

- [ ] **Step 2: Register the memo router in main.py**

In `backend/app/main.py`, add after the notifications import (around line 62):

```python
from app.api.memo import router as memo_router
```

And add after the notifications include_router (around line 95):

```python
app.include_router(memo_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/memo.py backend/app/main.py
git commit -m "feat(memo): add memo API endpoints — generate, regenerate, get, download"
```

---

### Task 5: Frontend Types and API Client

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add InvestmentMemo type**

In `frontend/lib/types.ts`, add at the end of the file (before the closing, after the `ReportListItem` interface):

```typescript
export interface InvestmentMemo {
  id: string;
  status: "pending" | "researching" | "generating" | "formatting" | "complete" | "failed";
  content: string | null;
  pdf_url: string | null;
  docx_url: string | null;
  error: string | null;
  created_at: string | null;
  completed_at: string | null;
}
```

- [ ] **Step 2: Add memo API methods**

In `frontend/lib/api.ts`, add at the end of the `api` object (before the closing `};`), after the `listAllReports` method:

```typescript
  // ── Investment Memo ────────────────────────────────────────────────

  async generateMemo(token: string, analysisId: string) {
    return apiFetch<{ id: string; status: string }>(
      `/api/analyze/${analysisId}/memo`,
      { method: "POST", headers: authHeaders(token) }
    );
  },

  async regenerateMemo(token: string, analysisId: string) {
    return apiFetch<{ id: string; status: string }>(
      `/api/analyze/${analysisId}/memo/regenerate`,
      { method: "POST", headers: authHeaders(token) }
    );
  },

  async getMemo(token: string, analysisId: string) {
    return apiFetch<import("./types").InvestmentMemo>(
      `/api/analyze/${analysisId}/memo`,
      { headers: authHeaders(token) }
    );
  },

  getMemoDownloadUrl(analysisId: string, format: "pdf" | "docx") {
    return `${API_URL}/api/analyze/${analysisId}/memo/download/${format}`;
  },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat(memo): add frontend InvestmentMemo type and API methods"
```

---

### Task 6: Analysis Result Page — Memo Button, Tab, and Polling

**Files:**
- Modify: `frontend/app/analyze/[id]/page.tsx`

This is the largest frontend change. It adds:
1. A "Generate Investment Memo" button in the header (when analysis is complete and no memo exists)
2. An "Investment Memo" tab in the tab bar (when memo exists)
3. Memo tab content: progress indicator during generation, rendered content + download buttons when complete, error + retry when failed
4. Polling logic for memo status

- [ ] **Step 1: Add memo state, fetch, and polling logic**

In `frontend/app/analyze/[id]/page.tsx`, add after the existing imports (around line 8):

```typescript
import type { InvestmentMemo } from "@/lib/types";
```

Inside the `AnalysisResultPage` component, add after the existing state declarations (after `const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);` around line 52):

```typescript
  const [memo, setMemo] = useState<InvestmentMemo | null>(null);
  const [memoLoading, setMemoLoading] = useState(false);
```

Add a memo fetch function after the existing `fetchData` callback (after line 68):

```typescript
  const fetchMemo = useCallback(async () => {
    if (!token || !id) return;
    try {
      const m = await api.getMemo(token, id);
      setMemo(m);
    } catch {
      // 404 = no memo yet, that's fine
      setMemo(null);
    }
  }, [token, id]);
```

Add memo fetch to the initial load effect. Replace the existing `useEffect(() => { fetchData(); }, [fetchData]);` (line 70) with:

```typescript
  useEffect(() => {
    fetchData();
    fetchMemo();
  }, [fetchData, fetchMemo]);
```

Add memo polling effect after the existing analysis polling effect (after line 77):

```typescript
  useEffect(() => {
    if (!memo) return;
    if (["complete", "failed"].includes(memo.status)) return;
    const timer = setInterval(fetchMemo, 3000);
    return () => clearInterval(timer);
  }, [memo?.status, fetchMemo]);
```

Add the generate memo handler after the effects:

```typescript
  async function handleGenerateMemo() {
    if (!token || !id) return;
    setMemoLoading(true);
    try {
      await api.generateMemo(token, id);
      await fetchMemo();
    } catch {
      // ignore — user may get 409 if already generating
    }
    setMemoLoading(false);
  }

  async function handleRegenerateMemo() {
    if (!token || !id) return;
    setMemoLoading(true);
    try {
      await api.regenerateMemo(token, id);
      await fetchMemo();
    } catch {
      // ignore
    }
    setMemoLoading(false);
  }
```

- [ ] **Step 2: Add memo button to the header**

In the RESULTS VIEW header area, find the `<div className="flex items-center gap-3">` block that contains the History link and Delete button (around line 158-168). Add the Generate Memo button before the History link:

```typescript
          {analysis.status === "complete" && !memo && (
            <button
              onClick={handleGenerateMemo}
              disabled={memoLoading}
              className="px-3 py-1.5 text-xs font-medium rounded bg-accent text-white hover:bg-accent-hover disabled:opacity-50 transition"
            >
              {memoLoading ? "Starting..." : "Generate Investment Memo"}
            </button>
          )}
```

- [ ] **Step 3: Add Investment Memo tab**

Find where the `tabs` array is constructed (around line 145):

```typescript
  const tabs = ["overview", ...Object.keys(AGENT_LABELS)];
```

Replace with:

```typescript
  const hasMemo = memo !== null;
  const tabs = ["overview", ...Object.keys(AGENT_LABELS), ...(hasMemo ? ["memo"] : [])];
```

In the tab button rendering, update the label for the memo tab. Find the tab button's text content (around line 195):

```typescript
            {t === "overview" ? "Overview" : AGENT_LABELS[t]}
```

Replace with:

```typescript
            {t === "overview" ? "Overview" : t === "memo" ? "Investment Memo" : AGENT_LABELS[t]}
```

- [ ] **Step 4: Add memo tab content**

After the agent report tab content block (after the closing of `{activeTab !== "overview" && activeReport && (...)}`), add:

```typescript
      {/* Investment Memo tab */}
      {activeTab === "memo" && memo && (
        <div>
          {/* Generating state */}
          {["pending", "researching", "generating", "formatting"].includes(memo.status) && (
            <div className="text-center py-12">
              <div className="animate-spin inline-block w-8 h-8 border-2 border-accent/30 border-t-accent rounded-full mb-4" />
              <p className="text-sm text-text-secondary">
                {memo.status === "pending" && "Starting memo generation..."}
                {memo.status === "researching" && "Researching market data..."}
                {memo.status === "generating" && "Writing investment memo..."}
                {memo.status === "formatting" && "Formatting documents..."}
              </p>
            </div>
          )}

          {/* Complete state */}
          {memo.status === "complete" && (
            <div>
              <div className="flex items-center gap-3 mb-4">
                <a
                  href={api.getMemoDownloadUrl(id, "pdf")}
                  className="px-3 py-1.5 text-xs font-medium rounded bg-accent text-white hover:bg-accent-hover transition"
                  download
                >
                  Download PDF
                </a>
                <a
                  href={api.getMemoDownloadUrl(id, "docx")}
                  className="px-3 py-1.5 text-xs font-medium rounded border border-border text-text-primary hover:border-accent/50 transition"
                  download
                >
                  Download DOCX
                </a>
                <button
                  onClick={handleRegenerateMemo}
                  disabled={memoLoading}
                  className="text-xs text-text-tertiary hover:text-text-secondary ml-auto"
                >
                  Regenerate
                </button>
              </div>
              {memo.content && (
                <div className="rounded border border-border bg-surface p-6 text-sm text-text-primary leading-relaxed whitespace-pre-wrap">
                  {memo.content}
                </div>
              )}
            </div>
          )}

          {/* Failed state */}
          {memo.status === "failed" && (
            <div className="text-center py-12">
              <p className="text-score-low text-sm mb-3">Memo generation failed</p>
              <p className="text-text-tertiary text-xs mb-4">{memo.error || "An unexpected error occurred"}</p>
              <button
                onClick={handleRegenerateMemo}
                disabled={memoLoading}
                className="px-3 py-1.5 text-xs font-medium rounded bg-accent text-white hover:bg-accent-hover disabled:opacity-50 transition"
              >
                Retry
              </button>
            </div>
          )}
        </div>
      )}
```

- [ ] **Step 5: Fix download links to include auth token**

The download endpoints require auth. The `<a>` tags won't send the Bearer token. We need to use fetch + blob download instead. Replace the download `<a>` tags in the complete state with:

```typescript
                <button
                  onClick={async () => {
                    const res = await fetch(api.getMemoDownloadUrl(id, "pdf"), {
                      headers: { Authorization: `Bearer ${token}` },
                    });
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `investment-memo-${analysis.company_name}.pdf`;
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                  className="px-3 py-1.5 text-xs font-medium rounded bg-accent text-white hover:bg-accent-hover transition"
                >
                  Download PDF
                </button>
                <button
                  onClick={async () => {
                    const res = await fetch(api.getMemoDownloadUrl(id, "docx"), {
                      headers: { Authorization: `Bearer ${token}` },
                    });
                    const blob = await res.blob();
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = `investment-memo-${analysis.company_name}.docx`;
                    a.click();
                    URL.revokeObjectURL(url);
                  }}
                  className="px-3 py-1.5 text-xs font-medium rounded border border-border text-text-primary hover:border-accent/50 transition"
                >
                  Download DOCX
                </button>
```

- [ ] **Step 6: Commit**

```bash
git add frontend/app/analyze/[id]/page.tsx
git commit -m "feat(memo): add investment memo button, tab, and polling to analysis page"
```

---

### Task 7: Deploy to Production

**Files:** None (deployment commands only)

- [ ] **Step 1: Sync backend to EC2**

```bash
rsync -avz --exclude='__pycache__' --exclude='.git' --exclude='node_modules' --exclude='.env' \
  -e "ssh -i ~/.ssh/acutal-deploy.pem" \
  backend/ ubuntu@98.89.232.52:~/acutal/backend/
```

- [ ] **Step 2: Sync frontend to EC2**

```bash
rsync -avz --exclude='__pycache__' --exclude='.git' --exclude='node_modules' --exclude='.next' --exclude='.env' \
  -e "ssh -i ~/.ssh/acutal-deploy.pem" \
  frontend/ ubuntu@98.89.232.52:~/acutal/frontend/
```

- [ ] **Step 3: Run Alembic migration on EC2**

```bash
ssh -i ~/.ssh/acutal-deploy.pem ubuntu@98.89.232.52 \
  "cd ~/acutal && docker compose exec backend alembic upgrade head"
```

- [ ] **Step 4: Rebuild and restart containers**

```bash
ssh -i ~/.ssh/acutal-deploy.pem ubuntu@98.89.232.52 \
  "cd ~/acutal && docker compose up -d --build"
```

- [ ] **Step 5: Verify deployment**

```bash
# Check backend health
curl -s https://deepthesis.org/api/health

# Check migration applied (should show investment_memos table)
ssh -i ~/.ssh/acutal-deploy.pem ubuntu@98.89.232.52 \
  "cd ~/acutal && docker compose exec backend alembic current"
```

- [ ] **Step 6: Commit (if any deployment fixes needed)**

```bash
git add -A
git commit -m "fix(memo): deployment fixes"
```
