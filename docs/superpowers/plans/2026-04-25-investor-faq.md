# Investor FAQ Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add on-demand investor FAQ generation to both pitch deck analysis and pitch intelligence, producing a dedicated FAQ page per analysis.

**Architecture:** Add `investor_faq` JSONB column to both `PitchAnalysis` and `PitchSession` models. New `faq_generator.py` service calls Claude Sonnet to generate Q&A pairs. New `faq.py` API file with POST/GET endpoints for both features. Frontend gets a "Generate Investor FAQ" button on each results page and a dedicated `/faq` subpage.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Anthropic Python SDK (Claude Sonnet 4.6), Next.js, TypeScript, Tailwind CSS

---

### Task 1: Alembic Migration — Add `investor_faq` columns

**Files:**
- Create: `backend/alembic/versions/c3d4e5f6g7h8_add_investor_faq_columns.py`

- [ ] **Step 1: Create migration file**

```python
"""add investor_faq column to pitch_analyses and pitch_sessions

Revision ID: c3d4e5f6g7h8
Revises: 2b6d7e0b62b0
Create Date: 2026-04-25 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "c3d4e5f6g7h8"
down_revision = "2b6d7e0b62b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pitch_analyses", sa.Column("investor_faq", JSONB(), nullable=True))
    op.add_column("pitch_sessions", sa.Column("investor_faq", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("pitch_sessions", "investor_faq")
    op.drop_column("pitch_analyses", "investor_faq")
```

- [ ] **Step 2: Commit**

```bash
git add backend/alembic/versions/c3d4e5f6g7h8_add_investor_faq_columns.py
git commit -m "feat(investor-faq): add investor_faq JSONB columns migration"
```

---

### Task 2: Update Models — Add `investor_faq` field

**Files:**
- Modify: `backend/app/models/pitch_analysis.py:60` (after `technical_expert_review`)
- Modify: `backend/app/models/pitch_session.py:54` (after `benchmark_percentiles`)

- [ ] **Step 1: Add `investor_faq` to PitchAnalysis model**

In `backend/app/models/pitch_analysis.py`, add this line after line 60 (`technical_expert_review`):

```python
    investor_faq: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 2: Add `investor_faq` to PitchSession model**

In `backend/app/models/pitch_session.py`, first add `JSONB` to the import on line 7:

```python
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
```

Then add this line after line 54 (`benchmark_percentiles`):

```python
    investor_faq: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/pitch_analysis.py backend/app/models/pitch_session.py
git commit -m "feat(investor-faq): add investor_faq field to PitchAnalysis and PitchSession models"
```

---

### Task 3: FAQ Generation Service

**Files:**
- Create: `backend/app/services/faq_generator.py`

- [ ] **Step 1: Create the FAQ generator service**

```python
import json
import logging

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

SONNET_MODEL = "claude-sonnet-4-6"

FAQ_CATEGORIES = [
    "market", "traction", "financials", "team",
    "technology", "competition", "business_model", "risk",
]


async def generate_investor_faq(analysis_data: dict, source_type: str) -> dict:
    """Generate investor FAQ from analysis data.

    Args:
        analysis_data: Dict with all scores, summaries, key findings, etc.
        source_type: "pitch_analysis" or "pitch_intelligence"

    Returns:
        Dict with "generated_at" and "questions" list.
    """
    from datetime import datetime, timezone

    context_text = _build_context(analysis_data, source_type)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=8192,
        system=(
            "You are a senior venture capital advisor helping founders prepare for investor meetings. "
            "Based on the pitch analysis data provided, generate 15-25 likely investor questions and "
            "coached answers.\n\n"
            "For each question:\n"
            "1. Identify weaknesses, gaps, red flags, and areas where scores are low\n"
            "2. Generate tough but realistic questions an investor would ask about those areas\n"
            "3. Provide a coached answer that acknowledges the concern honestly while presenting "
            "the strongest possible case\n"
            "4. Also include standard investor questions that are always asked (team background, "
            "use of funds, competitive differentiation, unit economics, etc.)\n\n"
            "Categorize each Q&A into exactly one of these categories: "
            "market, traction, financials, team, technology, competition, business_model, risk\n\n"
            "Assign a priority to each question:\n"
            "- \"high\": Very likely to be asked — addresses obvious weak spots or standard investor concerns\n"
            "- \"medium\": Likely to come up in a thorough meeting\n"
            "- \"low\": Possible follow-up or deep-dive question\n\n"
            "Return a JSON array of objects, each with:\n"
            "- \"category\": one of the 8 categories above\n"
            "- \"question\": the investor's question\n"
            "- \"answer\": the coached answer (2-4 sentences)\n"
            "- \"priority\": \"high\", \"medium\", or \"low\"\n\n"
            "Order by priority (all high first, then medium, then low). "
            "Return ONLY the JSON array, no other text."
        ),
        messages=[{"role": "user", "content": context_text}],
    )

    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        questions = json.loads(text)
    except json.JSONDecodeError:
        logger.error("Failed to parse FAQ JSON: %s", text[:500])
        questions = []

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "questions": questions,
    }


def _build_context(data: dict, source_type: str) -> str:
    """Build the context string for the Claude prompt from analysis data."""
    parts = []

    company = data.get("company_name") or data.get("title") or "Unknown Company"
    parts.append(f"Company/Pitch: {company}")

    if source_type == "pitch_analysis":
        # Pitch deck analysis data
        if data.get("overall_score") is not None:
            parts.append(f"Overall Score: {data['overall_score']}/100")
        if data.get("fundraising_likelihood") is not None:
            parts.append(f"Fundraising Likelihood: {data['fundraising_likelihood']}%")
        if data.get("recommended_raise"):
            parts.append(f"Recommended Raise: {data['recommended_raise']}")
        if data.get("estimated_valuation"):
            parts.append(f"Estimated Valuation: {data['estimated_valuation']}")
        if data.get("valuation_justification"):
            parts.append(f"Valuation Justification: {data['valuation_justification']}")
        if data.get("executive_summary"):
            parts.append(f"Executive Summary: {data['executive_summary']}")
        if data.get("exit_likelihood") is not None:
            parts.append(f"Exit Likelihood: {data['exit_likelihood']}%")
        if data.get("expected_exit_value"):
            parts.append(f"Expected Exit Value: {data['expected_exit_value']}")

        # Technical expert review
        ter = data.get("technical_expert_review")
        if ter and isinstance(ter, dict):
            parts.append(f"Technical Feasibility: {ter.get('technical_feasibility', 'N/A')}")
            parts.append(f"TRL Level: {ter.get('trl_level', 'N/A')}")
            if ter.get("red_flags"):
                parts.append(f"Technical Red Flags: {', '.join(ter['red_flags'])}")
            if ter.get("scientific_consensus"):
                parts.append(f"Scientific Consensus: {ter['scientific_consensus']}")

        # Agent reports
        reports = data.get("reports") or []
        for r in reports:
            agent = r.get("agent_type", "unknown")
            score = r.get("score")
            summary = r.get("summary", "")
            key_findings = r.get("key_findings") or []
            parts.append(f"\n--- {agent} (Score: {score}/100) ---")
            if summary:
                parts.append(f"Summary: {summary}")
            if key_findings:
                parts.append(f"Key Findings: {'; '.join(str(f) for f in key_findings)}")

    elif source_type == "pitch_intelligence":
        # Pitch intelligence data
        scores = data.get("scores") or {}
        for dim, val in scores.items():
            parts.append(f"Score - {dim}: {val}/100")

        # Phase results
        results = data.get("results") or []
        for r in results:
            phase = r.get("phase", "unknown")
            result_data = r.get("result")
            if not result_data:
                continue

            if phase == "scoring":
                if result_data.get("executive_summary"):
                    parts.append(f"Executive Summary: {result_data['executive_summary']}")
                recs = result_data.get("recommendations") or []
                if recs:
                    rec_texts = [f"- {rec.get('title', '')}: {rec.get('description', '')}" for rec in recs[:10]]
                    parts.append(f"Recommendations:\n" + "\n".join(rec_texts))
                va = result_data.get("valuation_assessment")
                if va:
                    parts.append(f"Estimated Valuation: {va.get('estimated_valuation', 'N/A')}")
                    parts.append(f"Valuation Justification: {va.get('justification', '')}")
                ter = result_data.get("technical_expert_review")
                if ter:
                    parts.append(f"Technical Feasibility: {ter.get('technical_feasibility', 'N/A')}")
                    if ter.get("red_flags"):
                        parts.append(f"Technical Red Flags: {', '.join(ter['red_flags'])}")

            elif phase == "claim_extraction":
                founder_claims = result_data.get("founder_claims") or []
                if founder_claims:
                    claims_text = [c.get("claim_summary", c.get("quote", "")) for c in founder_claims[:15]]
                    parts.append(f"Founder Claims: {'; '.join(claims_text)}")

            elif phase in ("fact_check_founders", "fact_check_investors"):
                summary = result_data.get("summary", "")
                disputed = result_data.get("disputed_count", 0)
                if summary:
                    parts.append(f"Fact Check ({phase}): {summary}")
                if disputed:
                    parts.append(f"Disputed claims: {disputed}")

            elif phase == "conversation_analysis":
                for section in ("presentation_quality", "meeting_dynamics", "strategic_read"):
                    section_data = result_data.get(section)
                    if section_data and isinstance(section_data, dict):
                        parts.append(f"{section} (Score: {section_data.get('score', 'N/A')}): {section_data.get('assessment', '')[:300]}")

    return "\n".join(parts)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/faq_generator.py
git commit -m "feat(investor-faq): add FAQ generation service"
```

---

### Task 4: API Endpoints

**Files:**
- Create: `backend/app/api/faq.py`
- Modify: `backend/app/main.py:72` (add import and router registration)

- [ ] **Step 1: Create the FAQ API file**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.pitch_analysis import AnalysisReport, AnalysisStatus, PitchAnalysis
from app.models.pitch_session import PitchSession, PitchSessionStatus
from app.models.user import User
from app.services.faq_generator import generate_investor_faq

router = APIRouter()


# ── Pitch Deck Analysis FAQ ──────────────────────────────────────────


@router.post("/api/analyze/{analysis_id}/faq")
async def generate_analysis_faq(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate investor FAQ for a completed pitch deck analysis."""
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
        .options(selectinload(PitchAnalysis.reports))
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")

    status_val = analysis.status.value if hasattr(analysis.status, "value") else analysis.status
    if status_val != "complete":
        raise HTTPException(400, "Analysis must be complete before generating FAQ")

    # Build analysis data dict
    analysis_data = {
        "company_name": analysis.company_name,
        "overall_score": analysis.overall_score,
        "fundraising_likelihood": analysis.fundraising_likelihood,
        "recommended_raise": analysis.recommended_raise,
        "estimated_valuation": analysis.estimated_valuation,
        "valuation_justification": analysis.valuation_justification,
        "executive_summary": analysis.executive_summary,
        "exit_likelihood": analysis.exit_likelihood,
        "expected_exit_value": analysis.expected_exit_value,
        "expected_exit_timeline": analysis.expected_exit_timeline,
        "technical_expert_review": analysis.technical_expert_review,
        "reports": [],
    }

    # Load full reports for richer context
    report_result = await db.execute(
        select(AnalysisReport).where(AnalysisReport.analysis_id == analysis_id)
    )
    reports = report_result.scalars().all()
    for r in reports:
        analysis_data["reports"].append({
            "agent_type": r.agent_type.value if hasattr(r.agent_type, "value") else r.agent_type,
            "score": r.score,
            "summary": r.summary,
            "key_findings": r.key_findings,
        })

    faq = await generate_investor_faq(analysis_data, "pitch_analysis")
    analysis.investor_faq = faq
    await db.commit()

    return faq


@router.get("/api/analyze/{analysis_id}/faq")
async def get_analysis_faq(
    analysis_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get stored investor FAQ for an analysis."""
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.id == analysis_id, PitchAnalysis.user_id == user.id)
    )
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(404, "Analysis not found")
    if not analysis.investor_faq:
        raise HTTPException(404, "No FAQ generated yet")

    return analysis.investor_faq


# ── Pitch Intelligence FAQ ───────────────────────────────────────────


@router.post("/api/pitch-intelligence/{session_id}/faq")
async def generate_pitch_faq(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate investor FAQ for a completed pitch intelligence session."""
    result = await db.execute(
        select(PitchSession)
        .where(PitchSession.id == session_id, PitchSession.user_id == user.id)
        .options(selectinload(PitchSession.results))
    )
    ps = result.scalar_one_or_none()
    if not ps:
        raise HTTPException(404, "Session not found")

    status_val = ps.status.value if hasattr(ps.status, "value") else ps.status
    if status_val != "complete":
        raise HTTPException(400, "Session must be complete before generating FAQ")

    session_data = {
        "title": ps.title,
        "scores": ps.scores,
        "results": [
            {
                "phase": r.phase.value if hasattr(r.phase, "value") else r.phase,
                "result": r.result,
            }
            for r in (ps.results or [])
        ],
    }

    faq = await generate_investor_faq(session_data, "pitch_intelligence")
    ps.investor_faq = faq
    await db.commit()

    return faq


@router.get("/api/pitch-intelligence/{session_id}/faq")
async def get_pitch_faq(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get stored investor FAQ for a pitch session."""
    result = await db.execute(
        select(PitchSession)
        .where(PitchSession.id == session_id, PitchSession.user_id == user.id)
    )
    ps = result.scalar_one_or_none()
    if not ps:
        raise HTTPException(404, "Session not found")
    if not ps.investor_faq:
        raise HTTPException(404, "No FAQ generated yet")

    return ps.investor_faq
```

- [ ] **Step 2: Register the router in main.py**

In `backend/app/main.py`, add this import after line 71 (`from app.api.admin_investor_rankings ...`):

```python
from app.api.faq import router as faq_router
```

And add this line after line 129 (`app.include_router(admin_investor_rankings_router)`):

```python
app.include_router(faq_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/faq.py backend/app/main.py
git commit -m "feat(investor-faq): add FAQ API endpoints for both features"
```

---

### Task 5: Frontend API Client and Types

**Files:**
- Modify: `frontend/lib/types.ts` (add `InvestorFAQ` type)
- Modify: `frontend/lib/api.ts` (add FAQ API methods)

- [ ] **Step 1: Add types to `frontend/lib/types.ts`**

Add at the end of the file, before the closing (after the `FeedbackSessionResponse` interface around line 429):

```typescript
// ── Investor FAQ types ────────────────────────────────────────────────

export interface InvestorFAQQuestion {
  category: string;
  question: string;
  answer: string;
  priority: "high" | "medium" | "low";
}

export interface InvestorFAQ {
  generated_at: string;
  questions: InvestorFAQQuestion[];
}
```

- [ ] **Step 2: Add API methods to `frontend/lib/api.ts`**

Add these methods inside the `api` object, after the memo methods (after the `getMemoDownloadUrl` method around line 354):

```typescript
  // ── Investor FAQ ───────────────────────────────────────────────────

  async generateAnalysisFaq(token: string, analysisId: string) {
    return apiFetch<import("./types").InvestorFAQ>(
      `/api/analyze/${analysisId}/faq`,
      { method: "POST", headers: authHeaders(token) }
    );
  },

  async getAnalysisFaq(token: string, analysisId: string) {
    return apiFetch<import("./types").InvestorFAQ>(
      `/api/analyze/${analysisId}/faq`,
      { headers: authHeaders(token) }
    );
  },

  async generatePitchFaq(token: string, sessionId: string) {
    return apiFetch<import("./types").InvestorFAQ>(
      `/api/pitch-intelligence/${sessionId}/faq`,
      { method: "POST", headers: authHeaders(token) }
    );
  },

  async getPitchFaq(token: string, sessionId: string) {
    return apiFetch<import("./types").InvestorFAQ>(
      `/api/pitch-intelligence/${sessionId}/faq`,
      { headers: authHeaders(token) }
    );
  },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat(investor-faq): add frontend types and API client methods"
```

---

### Task 6: Add "Generate FAQ" Button to Pitch Deck Analysis Page

**Files:**
- Modify: `frontend/app/analyze/[id]/page.tsx`

- [ ] **Step 1: Add state and handler**

In the `AnalysisDetailContent` component (or equivalent), add state variables near the other state declarations (around line 134, after the memo state):

```typescript
  const [faqLoading, setFaqLoading] = useState(false);
  const [hasFaq, setHasFaq] = useState(false);
```

Add a check for existing FAQ inside the `fetchData` callback (after memo/reports are loaded), adding this effect after the `fetchMemo` effect:

```typescript
  const checkFaq = useCallback(async () => {
    if (!token || !id) return;
    try {
      await api.getAnalysisFaq(token, id);
      setHasFaq(true);
    } catch {
      setHasFaq(false);
    }
  }, [token, id]);

  useEffect(() => {
    checkFaq();
  }, [checkFaq]);
```

Add the handler function near `handleGenerateMemo`:

```typescript
  async function handleGenerateFaq() {
    if (!token || !id) return;
    setFaqLoading(true);
    try {
      await api.generateAnalysisFaq(token, id);
      setHasFaq(true);
      router.push(`/analyze/${id}/faq`);
    } catch {
      // ignore
    }
    setFaqLoading(false);
  }
```

- [ ] **Step 2: Add button to the header**

In the header buttons area (around line 336, inside the `<div className="flex items-center gap-3">`), add these elements before the "Generate Investment Memo" button:

```tsx
          {analysis.status === "complete" && !hasFaq && !faqLoading && (
            <button
              onClick={handleGenerateFaq}
              className="px-3 py-1.5 text-xs font-medium rounded border border-accent text-accent hover:bg-accent hover:text-white transition"
            >
              Generate Investor FAQ
            </button>
          )}
          {analysis.status === "complete" && faqLoading && (
            <span className="flex items-center gap-1.5 text-xs text-text-tertiary">
              <span className="animate-spin inline-block w-3 h-3 border border-accent/30 border-t-accent rounded-full" />
              Generating FAQ...
            </span>
          )}
          {hasFaq && (
            <Link
              href={`/analyze/${id}/faq`}
              className="text-xs font-medium text-accent/70 hover:text-accent transition"
            >
              Investor FAQ
            </Link>
          )}
```

Make sure `Link` is imported from `next/link` at the top of the file (it should already be imported).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/analyze/[id]/page.tsx
git commit -m "feat(investor-faq): add Generate FAQ button to analysis page"
```

---

### Task 7: Add "Generate FAQ" Button to Pitch Intelligence Page

**Files:**
- Modify: `frontend/app/pitch-intelligence/[id]/page.tsx`

- [ ] **Step 1: Add state, effect, and handler**

Add state variables near the top of the `PitchSessionContent` component (around line 33, after `factCheckTab`):

```typescript
  const [faqLoading, setFaqLoading] = useState(false);
  const [hasFaq, setHasFaq] = useState(false);
```

Add a check for existing FAQ — add this after the `loadSession` effect:

```typescript
  const checkFaq = useCallback(async () => {
    if (!token || !sessionId) return;
    try {
      await api.getPitchFaq(token, sessionId);
      setHasFaq(true);
    } catch {
      setHasFaq(false);
    }
  }, [token, sessionId]);

  useEffect(() => {
    checkFaq();
  }, [checkFaq]);
```

Add the handler function:

```typescript
  async function handleGenerateFaq() {
    if (!token || !sessionId) return;
    setFaqLoading(true);
    try {
      await api.generatePitchFaq(token, sessionId);
      setHasFaq(true);
      router.push(`/pitch-intelligence/${sessionId}/faq`);
    } catch {
      // ignore
    }
    setFaqLoading(false);
  }
```

- [ ] **Step 2: Add button to the header**

In the header area (around line 256), modify the `<div className="mb-6 flex items-start justify-between">` block. After the closing `</div>` of the title section and before the overall score section, add a buttons row. Replace the header block with:

```tsx
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-serif text-text-primary">
            {ps.title || "Untitled Pitch"}
          </h1>
          <p className="text-sm text-text-tertiary mt-1">
            {ps.created_at ? new Date(ps.created_at).toLocaleDateString() : ""}
            {ps.file_duration_seconds ? ` · ${Math.round(ps.file_duration_seconds / 60)} min` : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {ps.status === "complete" && !hasFaq && !faqLoading && (
            <button
              onClick={handleGenerateFaq}
              className="px-3 py-1.5 text-xs font-medium rounded border border-accent text-accent hover:bg-accent hover:text-white transition"
            >
              Generate Investor FAQ
            </button>
          )}
          {ps.status === "complete" && faqLoading && (
            <span className="flex items-center gap-1.5 text-xs text-text-tertiary">
              <span className="animate-spin inline-block w-3 h-3 border border-accent/30 border-t-accent rounded-full" />
              Generating FAQ...
            </span>
          )}
          {hasFaq && (
            <Link
              href={`/pitch-intelligence/${sessionId}/faq`}
              className="text-xs font-medium text-accent/70 hover:text-accent transition"
            >
              Investor FAQ
            </Link>
          )}
          {scores.overall != null && (
            <div className="text-right">
              <div className="text-3xl font-bold text-accent">{scores.overall}</div>
              <div className="text-xs text-text-tertiary">Overall Score</div>
            </div>
          )}
        </div>
      </div>
```

Make sure `Link` is imported from `next/link` at the top of the file. If not already imported, add:

```typescript
import Link from "next/link";
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/pitch-intelligence/[id]/page.tsx
git commit -m "feat(investor-faq): add Generate FAQ button to pitch intelligence page"
```

---

### Task 8: Shared FAQ Display Component

**Files:**
- Create: `frontend/components/InvestorFaqView.tsx`

- [ ] **Step 1: Create the shared FAQ display component**

```tsx
"use client";

import { useState } from "react";
import type { InvestorFAQ, InvestorFAQQuestion } from "@/lib/types";

const CATEGORY_LABELS: Record<string, string> = {
  market: "Market & Opportunity",
  traction: "Traction & Growth",
  financials: "Financials & Unit Economics",
  team: "Team & Leadership",
  technology: "Technology & Product",
  competition: "Competition & Moat",
  business_model: "Business Model & GTM",
  risk: "Risks & Challenges",
};

const PRIORITY_STYLES: Record<string, string> = {
  high: "bg-score-low/10 text-score-low border-score-low/20",
  medium: "bg-yellow-500/10 text-yellow-600 border-yellow-500/20",
  low: "bg-text-tertiary/10 text-text-tertiary border-text-tertiary/20",
};

export default function InvestorFaqView({
  faq,
  onRegenerate,
  regenerating,
}: {
  faq: InvestorFAQ;
  onRegenerate: () => void;
  regenerating: boolean;
}) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  // Group questions by category
  const grouped: Record<string, InvestorFAQQuestion[]> = {};
  for (const q of faq.questions) {
    const cat = q.category || "risk";
    if (!grouped[cat]) grouped[cat] = [];
    grouped[cat].push(q);
  }

  // Order categories by which appear first in the questions array
  const categoryOrder = Object.keys(CATEGORY_LABELS).filter((c) => grouped[c]);

  let globalIndex = 0;

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="text-xs text-text-tertiary">
            Generated {new Date(faq.generated_at).toLocaleDateString()} · {faq.questions.length} questions
          </p>
        </div>
        <button
          onClick={onRegenerate}
          disabled={regenerating}
          className="px-3 py-1.5 text-xs font-medium rounded border border-border text-text-secondary hover:text-text-primary hover:border-text-tertiary transition disabled:opacity-50"
        >
          {regenerating ? "Regenerating..." : "Regenerate"}
        </button>
      </div>

      {/* Questions grouped by category */}
      {categoryOrder.map((category) => {
        const questions = grouped[category];
        return (
          <div key={category} className="mb-6">
            <h3 className="text-sm font-medium text-text-primary mb-3 uppercase tracking-wide">
              {CATEGORY_LABELS[category] || category}
            </h3>
            <div className="space-y-2">
              {questions.map((q) => {
                const idx = globalIndex++;
                const isOpen = openIndex === idx;
                return (
                  <div
                    key={idx}
                    className="rounded-lg border border-border bg-surface overflow-hidden"
                  >
                    <button
                      onClick={() => setOpenIndex(isOpen ? null : idx)}
                      className="w-full text-left px-4 py-3 flex items-start gap-3 hover:bg-surface-hover transition"
                    >
                      <span
                        className={`mt-0.5 text-[10px] px-1.5 py-0.5 rounded border font-medium shrink-0 ${PRIORITY_STYLES[q.priority] || PRIORITY_STYLES.low}`}
                      >
                        {q.priority}
                      </span>
                      <span className="text-sm text-text-primary flex-1">
                        {q.question}
                      </span>
                      <span className="text-text-tertiary text-xs mt-0.5 shrink-0">
                        {isOpen ? "−" : "+"}
                      </span>
                    </button>
                    {isOpen && (
                      <div className="px-4 pb-4 pt-0 ml-[42px]">
                        <p className="text-sm text-text-secondary leading-relaxed">
                          {q.answer}
                        </p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/InvestorFaqView.tsx
git commit -m "feat(investor-faq): add shared FAQ display component"
```

---

### Task 9: Dedicated FAQ Page for Pitch Deck Analysis

**Files:**
- Create: `frontend/app/analyze/[id]/faq/page.tsx`

- [ ] **Step 1: Create the FAQ page**

```tsx
"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { InvestorFAQ } from "@/lib/types";
import InvestorFaqView from "@/components/InvestorFaqView";

export default function AnalysisFaqPage() {
  return (
    <Suspense fallback={<div className="p-8 text-text-secondary">Loading...</div>}>
      <AnalysisFaqContent />
    </Suspense>
  );
}

function AnalysisFaqContent() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const params = useParams();
  const id = params.id as string;
  const router = useRouter();

  const [faq, setFaq] = useState<InvestorFAQ | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);

  const loadFaq = useCallback(async () => {
    if (!token || !id) return;
    try {
      const data = await api.getAnalysisFaq(token, id);
      setFaq(data);
    } catch {
      setFaq(null);
    }
    setLoading(false);
  }, [token, id]);

  useEffect(() => {
    loadFaq();
  }, [loadFaq]);

  useEffect(() => {
    if (!token || !id) return;
    api.getAnalysis(token, id).then((a) => setCompanyName(a.company_name)).catch(() => {});
  }, [token, id]);

  async function handleRegenerate() {
    if (!token || !id) return;
    setRegenerating(true);
    try {
      const data = await api.generateAnalysisFaq(token, id);
      setFaq(data);
    } catch {
      // ignore
    }
    setRegenerating(false);
  }

  if (loading) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  if (!faq) {
    return (
      <div className="max-w-3xl mx-auto text-center py-20">
        <p className="text-text-tertiary mb-4">No FAQ generated yet.</p>
        <Link href={`/analyze/${id}`} className="text-accent hover:text-accent-hover text-sm">
          Back to Analysis
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <Link href={`/analyze/${id}`} className="text-xs text-text-tertiary hover:text-text-secondary">
          ← Back to Analysis
        </Link>
        <h1 className="font-serif text-2xl text-text-primary mt-2">
          Investor FAQ — {companyName || "Analysis"}
        </h1>
      </div>

      <InvestorFaqView faq={faq} onRegenerate={handleRegenerate} regenerating={regenerating} />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/analyze/[id]/faq/page.tsx
git commit -m "feat(investor-faq): add dedicated FAQ page for pitch deck analysis"
```

---

### Task 10: Dedicated FAQ Page for Pitch Intelligence

**Files:**
- Create: `frontend/app/pitch-intelligence/[id]/faq/page.tsx`

- [ ] **Step 1: Create the FAQ page**

```tsx
"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { InvestorFAQ } from "@/lib/types";
import InvestorFaqView from "@/components/InvestorFaqView";

export default function PitchFaqPage() {
  return (
    <Suspense fallback={<div className="p-8 text-text-secondary">Loading...</div>}>
      <PitchFaqContent />
    </Suspense>
  );
}

function PitchFaqContent() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const params = useParams();
  const sessionId = params.id as string;
  const router = useRouter();

  const [faq, setFaq] = useState<InvestorFAQ | null>(null);
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);

  const loadFaq = useCallback(async () => {
    if (!token || !sessionId) return;
    try {
      const data = await api.getPitchFaq(token, sessionId);
      setFaq(data);
    } catch {
      setFaq(null);
    }
    setLoading(false);
  }, [token, sessionId]);

  useEffect(() => {
    loadFaq();
  }, [loadFaq]);

  useEffect(() => {
    if (!token || !sessionId) return;
    api.getPitchSession(token, sessionId).then((s) => setTitle(s.title || "Untitled Pitch")).catch(() => {});
  }, [token, sessionId]);

  async function handleRegenerate() {
    if (!token || !sessionId) return;
    setRegenerating(true);
    try {
      const data = await api.generatePitchFaq(token, sessionId);
      setFaq(data);
    } catch {
      // ignore
    }
    setRegenerating(false);
  }

  if (loading) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  if (!faq) {
    return (
      <div className="max-w-3xl mx-auto text-center py-20">
        <p className="text-text-tertiary mb-4">No FAQ generated yet.</p>
        <Link href={`/pitch-intelligence/${sessionId}`} className="text-accent hover:text-accent-hover text-sm">
          Back to Session
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <Link href={`/pitch-intelligence/${sessionId}`} className="text-xs text-text-tertiary hover:text-text-secondary">
          ← Back to Session
        </Link>
        <h1 className="font-serif text-2xl text-text-primary mt-2">
          Investor FAQ — {title}
        </h1>
      </div>

      <InvestorFaqView faq={faq} onRegenerate={handleRegenerate} regenerating={regenerating} />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/pitch-intelligence/[id]/faq/page.tsx
git commit -m "feat(investor-faq): add dedicated FAQ page for pitch intelligence"
```

---

### Task 11: Deploy to Production

**Files:** None (deployment steps only)

- [ ] **Step 1: Rsync files to EC2**

```bash
rsync -avz --exclude='node_modules' --exclude='.next' --exclude='__pycache__' --exclude='.git' \
  -e "ssh -i ~/.ssh/deepthesis-deploy.pem" \
  /Users/leemosbacker/acutal/ ec2-user@3.212.120.144:~/acutal/
```

- [ ] **Step 2: Run alembic migration**

```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "cd ~/acutal && docker compose exec backend alembic upgrade head"
```

- [ ] **Step 3: Rebuild and restart containers**

```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "cd ~/acutal && docker compose up -d --build backend frontend"
```

- [ ] **Step 4: Verify deployment**

```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "docker logs acutal-backend-1 --tail 20"
```

Test by visiting a completed analysis page and clicking "Generate Investor FAQ".
