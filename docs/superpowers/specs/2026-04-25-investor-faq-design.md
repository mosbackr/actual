# Investor FAQ Generation — Design Spec

## Overview

Generate a "prep sheet" of likely investor questions and coached answers for every pitch deck analysis and pitch intelligence session. Helps founders anticipate tough questions by surfacing weaknesses, gaps, and concerns identified during analysis.

## Trigger

On-demand — user clicks a "Generate Investor FAQ" button on the completed analysis/session results page. Not generated automatically as part of the pipeline.

## Scope

Both features:
- Pitch deck analysis (`PitchAnalysis`)
- Pitch intelligence (`PitchSession`)

## Data Model

No new tables. Add a nullable JSONB column to each existing model:

- `PitchAnalysis.investor_faq` — JSONB, nullable
- `PitchSession.investor_faq` — JSONB, nullable

Single Alembic migration adds both columns.

### JSON Structure

```json
{
  "generated_at": "2026-04-25T12:00:00Z",
  "questions": [
    {
      "category": "market",
      "question": "How do you justify a $2B TAM when...",
      "answer": "Based on our analysis of...",
      "priority": "high"
    }
  ]
}
```

**Categories:** `market`, `traction`, `financials`, `team`, `technology`, `competition`, `business_model`, `risk`

**Priority:** `high` (likely to be asked), `medium`, `low`

**Target:** 15-25 Q&A pairs per generation.

## FAQ Generation Service

New file: `backend/app/services/faq_generator.py`

Single function: `generate_investor_faq(analysis_data: dict, source_type: str) -> dict`

- `analysis_data`: dict containing all scores, summaries, key findings, valuation, technical review, executive summary
- `source_type`: `"pitch_analysis"` or `"pitch_intelligence"` — adjusts the prompt slightly:
  - `pitch_analysis`: uses 8 agent reports (scores, summaries, key findings), overall score, valuation, technical review, executive summary
  - `pitch_intelligence`: uses scoring phase results (dimension scores, recommendations), fact-check results, conversation analysis, valuation assessment, technical expert review, executive summary
- Single Claude Sonnet 4.6 API call
- Returns the JSON structure above

### Prompt Design

The prompt instructs Claude to:
1. Identify weaknesses, gaps, and red flags from the scores and reports
2. Generate tough but realistic investor questions targeting those areas
3. Provide coached answers that acknowledge concerns honestly while presenting the best case
4. Categorize each Q&A into one of the 8 categories
5. Assign priority based on how likely an investor is to ask the question
6. Order by priority (high first within each category)

## API Endpoints

### Pitch Deck Analysis

- `POST /api/analyze/{id}/faq` — generates FAQ, stores in `investor_faq` column, returns it. Requires analysis status = `complete`. Idempotent: calling again regenerates and overwrites.
- `GET /api/analyze/{id}/faq` — returns stored FAQ. Returns 404 if not generated yet.

### Pitch Intelligence

- `POST /api/pitch-intelligence/{id}/faq` — generates FAQ, stores in `investor_faq` column, returns it. Requires session status = `complete`. Idempotent: calling again regenerates and overwrites.
- `GET /api/pitch-intelligence/{id}/faq` — returns stored FAQ. Returns 404 if not generated yet.

All endpoints require authentication and ownership verification (user can only access their own analyses/sessions).

## Frontend

### Button Placement

- **Pitch deck analysis** (`/analyze/[id]/page.tsx`): "Generate Investor FAQ" button in the overview tab, near the existing memo generation button. Shows loading state while generating. Once generated, links to `/analyze/[id]/faq`.
- **Pitch intelligence** (`/pitch-intelligence/[id]/page.tsx`): Same pattern — "Generate Investor FAQ" button, links to `/pitch-intelligence/[id]/faq`.

Both buttons only appear when status is `complete`.

### Dedicated FAQ Pages

Two new pages with identical visual structure:
- `/analyze/[id]/faq/page.tsx`
- `/pitch-intelligence/[id]/faq/page.tsx`

**Layout:**
- Header: company name / session title, generation date
- Questions grouped by category with category headers
- Each Q&A is an expandable accordion — question visible, click to reveal coached answer
- Priority badge on each question: high (red), medium (yellow), low (gray)
- "Regenerate" button to call POST again and refresh
- Clean, printable layout

**Shared component:** Both pages use the same FAQ display component since the data structure is identical. Only the API endpoint differs.

### No Download

Web page only — no PDF/DOCX generation. Users can print/save from the browser.

## Generation Flow

1. User clicks "Generate Investor FAQ" on completed analysis/session page
2. Frontend POSTs to the appropriate endpoint
3. Backend gathers all analysis data (reports, scores, summaries, key findings, valuation, technical review)
4. Calls `generate_investor_faq()` with that data
5. Stores result in the `investor_faq` JSONB column
6. Returns the FAQ JSON to frontend
7. Frontend redirects to the dedicated FAQ page

On subsequent visits, the GET endpoint returns the stored FAQ. The "Regenerate" button on the FAQ page calls POST again to overwrite.

## Cost

Approximately $0.05-0.10 per FAQ generation (single Sonnet 4.6 call with ~5-10K input tokens of analysis context).
