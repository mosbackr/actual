# Investment Memo Generation — Design Spec

## Overview

Add investment memo generation to the pitch analysis result page. Users click "Generate Investment Memo" on a completed analysis, and the system uses Claude as orchestrator + Perplexity as research tool to produce a polished VC-style investment memo. The memo renders in-page and is downloadable as PDF or DOCX.

**Key constraints:**
- All changes are additive — no modifications to existing analysis, insights, or analyst code
- One memo per analysis, with ability to regenerate
- Background job with polling (not streaming)

---

## Data Model

### New table: `investment_memos`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK, default uuid4 |
| analysis_id | UUID FK | References `pitch_analyses.id`, **unique** (one memo per analysis) |
| status | Enum(`MemoStatus`) | `pending`, `researching`, `generating`, `formatting`, `complete`, `failed` |
| content | Text | Markdown memo content (null until generating phase completes) |
| s3_key_pdf | String(1000) | S3 key for PDF file (null until formatting completes) |
| s3_key_docx | String(1000) | S3 key for DOCX file (null until formatting completes) |
| error | Text | Error message if failed |
| created_at | DateTime(tz) | server_default=func.now() |
| completed_at | DateTime(tz) | Set when status=complete |

**New file:** `backend/app/models/investment_memo.py`

**Enum `MemoStatus`:** `pending`, `researching`, `generating`, `formatting`, `complete`, `failed`

**Relationship:** Add `memo: Mapped["InvestmentMemo" | None]` to `PitchAnalysis` model (additive only — new relationship attribute).

**Migration:** New Alembic migration creating the table. Use raw SQL for enum creation (same pattern as notifications migration to avoid SQLAlchemy enum auto-creation conflicts).

---

## Backend API

**New file:** `backend/app/api/memo.py` — mounted on the main router

### `POST /api/analyze/{analysis_id}/memo`

Trigger memo generation.

- Auth required (get_current_user), must own the analysis
- Analysis must have status=`complete`
- If memo exists with status in (`pending`, `researching`, `generating`, `formatting`): return 409 "Memo generation already in progress"
- If memo exists with status=`complete`: return 409 "Memo already exists. Use regenerate endpoint."
- If memo exists with status=`failed`: delete old row, create new one
- Creates `InvestmentMemo` row with status=`pending`
- Kicks off `BackgroundTasks.add_task(run_memo_generation, memo_id)`
- Returns `{ id, status }`

### `POST /api/analyze/{analysis_id}/memo/regenerate`

Regenerate existing memo.

- Auth required, must own the analysis
- Deletes old memo row (and S3 files if they exist)
- Creates fresh `InvestmentMemo` row, starts generation
- Returns `{ id, status }`

### `GET /api/analyze/{analysis_id}/memo`

Get memo status and content.

- Auth required, must own the analysis
- Returns 404 if no memo exists
- Returns `{ id, status, content, pdf_url, docx_url, error, created_at, completed_at }`
- `pdf_url` and `docx_url` are only present when status=`complete`; these are direct download endpoint URLs (not presigned S3 URLs — we use our own download endpoint for auth)

### `GET /api/analyze/{analysis_id}/memo/download/{format}`

Download memo file.

- Auth required, must own the analysis
- `format` path param: `pdf` or `docx`
- Streams file from S3 with content-disposition attachment header
- Returns 404 if memo not complete or file doesn't exist

---

## Memo Generator Service

**New file:** `backend/app/services/memo_generator.py`

### `async def run_memo_generation(memo_id: str)`

Entry point called by BackgroundTasks.

**Phase 1: Research (status=`researching`)**

Gather fresh intelligence via 4 parallel Perplexity calls using the existing `call_perplexity()` helper from `app.services.scout`:

1. **Recent news** — "Latest news about {company_name} in the last 6 months: funding announcements, product launches, partnerships, press coverage"
2. **Competitive landscape** — "Current competitors to {company_name} in {market_context}, their recent funding, market positioning, strengths and weaknesses"
3. **Market data** — "Current market size, growth rate, trends, and outlook for {market_context} in 2025-2026"
4. **Comparable deals** — "Recent VC investment deals and valuations for {stage} startups in {market_context}, notable exits"

`market_context` is derived from the Market & TAM agent report summary. `stage` comes from the analysis metadata.

All 4 calls run via `asyncio.gather()`.

**Phase 2: Synthesis (status=`generating`)**

One Claude API call (Anthropic SDK, model: `claude-sonnet-4-20250514`) with:

**System prompt:** Structured prompt defining the investment memo format, tone (professional VC analyst), and sections.

**User message context includes:**
- Company name and analysis metadata (overall score, fundraising likelihood, recommended raise, exit projections)
- Executive summary from the analysis
- All 8 agent reports: for each, include agent_type label, score, summary, full report text, key findings
- All 4 Perplexity research results from Phase 1

**Output:** Markdown investment memo with these sections:
1. Executive Summary — Investment thesis, key metrics, overall recommendation
2. Company Overview — What they do, stage, founding context
3. Market Opportunity — TAM/SAM/SOM, growth drivers, timing, market data from research
4. Product & Technology — Solution, differentiation, technical moat
5. Competitive Landscape — Key competitors, positioning, recent competitive moves from research
6. Team Assessment — Founders, key hires, experience, gaps
7. Traction & Financials — Metrics, revenue model, unit economics
8. Investment Terms — Recommended raise, valuation context, comparable deals from research
9. Risk Factors — Key risks ranked by severity, mitigation strategies
10. Recommendation — Invest / Pass / Watch with conviction level and rationale

**Phase 3: Formatting (status=`formatting`)**

Convert the markdown content to PDF and DOCX:

- **PDF:** Use `weasyprint` (or `reportlab` as fallback). Deep Thesis branded — header with logo text, footer with "Generated by Deep Thesis | {date}". Professional typography.
- **DOCX:** Use `python-docx`. Same branding — title page with Deep Thesis branding, proper heading styles, professional formatting.
- Upload both to S3 under `memos/{memo_id}/memo.pdf` and `memos/{memo_id}/memo.docx`
- Store S3 keys in the memo row

**Error handling:** If any phase fails, set status=`failed` with error message. Perplexity failures in Phase 1 are non-fatal — if some research calls fail, proceed with whatever data was gathered.

---

## Frontend Changes

### New types (`frontend/lib/types.ts`)

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

### New API methods (`frontend/lib/api.ts`)

```typescript
generateMemo(token: string, analysisId: string): Promise<{ id: string; status: string }>
regenerateMemo(token: string, analysisId: string): Promise<{ id: string; status: string }>
getMemo(token: string, analysisId: string): Promise<InvestmentMemo>
getMemoDownloadUrl(analysisId: string, format: "pdf" | "docx"): string
```

### Analysis result page (`frontend/app/analyze/[id]/page.tsx`)

**Header area (when analysis.status === "complete"):**
- "Generate Investment Memo" button — visible when no memo exists
- Status indicator with phase label — visible when memo is generating
- Nothing extra — when memo is complete (user accesses via tab)

**Tab bar:**
- Add "Investment Memo" tab after the 8 agent tabs — only visible when memo exists (any status)

**Memo tab content:**
- **When generating:** Progress indicator with status labels:
  - `pending` → "Starting memo generation..."
  - `researching` → "Researching market data..."
  - `generating` → "Writing investment memo..."
  - `formatting` → "Formatting documents..."
- **When complete:** Rendered markdown content with download buttons (PDF, DOCX) at top. Small "Regenerate" link.
- **When failed:** Error message with "Retry" button

**Polling:** When memo status is not `complete` or `failed`, poll `GET /api/analyze/{id}/memo` every 3 seconds. Stop polling on terminal status.

---

## Files Created/Modified

### New files:
- `backend/app/models/investment_memo.py` — InvestmentMemo model + MemoStatus enum
- `backend/app/api/memo.py` — 4 API endpoints
- `backend/app/services/memo_generator.py` — Generation pipeline (Perplexity research + Claude synthesis + PDF/DOCX formatting)
- `backend/alembic/versions/xxxx_add_investment_memos_table.py` — Migration

### Modified files (additive only):
- `backend/app/models/pitch_analysis.py` — Add `memo` relationship to PitchAnalysis
- `backend/app/main.py` — Include memo router
- `frontend/lib/types.ts` — Add InvestmentMemo type
- `frontend/lib/api.ts` — Add 4 memo API methods
- `frontend/app/analyze/[id]/page.tsx` — Add memo button, tab, polling, and display

### Not modified:
- Analysis worker, agents, scoring — untouched
- Insights pages — untouched
- Analyst/conversation features — untouched
- History page — untouched
- Any existing API endpoints — untouched

---

## Dependencies

**New Python packages (if not already installed):**
- `weasyprint` — Markdown → PDF conversion (or `markdown` + `weasyprint`)
- `python-docx` — Markdown → DOCX conversion
- `markdown` — Markdown parsing for HTML intermediate (for weasyprint)

**Existing packages used:**
- `anthropic` — Claude API calls (already in use)
- `httpx` — Perplexity API calls via existing `call_perplexity()` helper
- `boto3` — S3 uploads via existing `s3` module
