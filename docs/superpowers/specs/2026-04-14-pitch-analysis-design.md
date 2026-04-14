# Pitch Analysis System — Design Spec

## Goal

Build a public-facing pitch analysis tool where founders upload their documents, get a detailed multi-agent AI evaluation across 8 factors, and receive actionable reports with fundraising projections. First analysis is free, then $19.99/mo. Analyzed companies optionally get published as startup profiles on the Deep Thesis public site.

## Architecture

Four components:

1. **Frontend** (`/analyze` routes in existing Next.js app) — Upload page with auth gate, live progress view, tabbed results dashboard.
2. **Backend API** (new routes in existing FastAPI) — File upload to S3, analysis job CRUD, progress polling, report retrieval.
3. **Analysis Worker** (new Docker container) — Polls for pending jobs, extracts document text, runs 8 Claude agents in parallel, synthesizes final scores, triggers Perplexity enrichment for public listing.
4. **S3 Bucket** — Stores uploaded documents. Worker reads from S3 for processing.

### Data Flow

```
User uploads docs → Backend validates + saves to S3 → Creates PitchAnalysis job (status: pending)
→ Worker picks up job → Extracts text from all docs → Runs 8 agents in parallel (asyncio.gather)
→ Each agent writes its AnalysisReport → Final scoring agent (Opus) synthesizes
→ If publish_consent: Perplexity enrichment → Creates Startup record
→ Worker marks job complete → Frontend polls and shows results
```

### Scaling Path

V1 uses Approach A: single async worker with `asyncio.gather()` for parallel agent calls. When concurrent users exceed 10-20, migrate to Approach B: task queue (SQS or Redis/Celery) with horizontally scalable workers on ECS Fargate. Agent functions are designed with clean standalone interfaces to make this migration a refactor, not a rewrite.

## Data Model

### Table: `pitch_analyses`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID, PK | |
| user_id | FK → users | Who submitted |
| company_name | string | Extracted from docs or user-provided |
| status | enum | pending, extracting, analyzing, enriching, complete, failed |
| current_agent | string, nullable | Which agent is running (for progress display) |
| overall_score | float, nullable | Composite score after all agents finish |
| fundraising_likelihood | float, nullable | 0-100, from final scoring agent |
| recommended_raise | string, nullable | e.g. "$2-3M" |
| exit_likelihood | float, nullable | 0-100 |
| expected_exit_value | string, nullable | e.g. "$50-100M" |
| expected_exit_timeline | string, nullable | e.g. "5-7 years" |
| startup_id | FK → startups, nullable | Link to public startup record if published |
| publish_consent | boolean, default true | Opt-out: user can uncheck to prevent public listing |
| is_free_analysis | boolean | First analysis per user is free |
| error | text, nullable | Error message if failed |
| created_at | timestamp | |
| completed_at | timestamp, nullable | |

### Table: `analysis_documents`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID, PK | |
| analysis_id | FK → pitch_analyses | |
| filename | string | Original filename |
| file_type | string | pdf, docx, xlsx, pptx, doc, ppt, xls, csv, md, txt |
| s3_key | string | Path in S3 bucket |
| file_size_bytes | int | |
| extracted_text | text, nullable | Populated by worker during extraction |
| created_at | timestamp | |

### Table: `analysis_reports`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID, PK | |
| analysis_id | FK → pitch_analyses | |
| agent_type | enum | problem_solution, market_tam, traction, technology_ip, competition_moat, team, gtm_business_model, financials_fundraising |
| status | enum | pending, running, complete, failed |
| score | float, nullable | 0-100 |
| summary | text, nullable | Short verdict paragraph |
| report | text, nullable | Full markdown report |
| key_findings | JSON, nullable | Structured findings for overview tab |
| started_at | timestamp, nullable | |
| completed_at | timestamp, nullable | |

### User table addition

Add `subscription_status` (enum: none, active, cancelled; default: none) to existing `users` table. V1 is manually managed — Stripe integration is a separate future project.

## Document Ingestion

### Supported Formats & Extraction

| Format | Library | Notes |
|--------|---------|-------|
| PDF | `pymupdf` (fitz) | Fast text extraction from text-based PDFs |
| DOCX | `python-docx` | Text + basic structure |
| DOC | libreoffice headless → DOCX → python-docx | Legacy format conversion |
| PPTX | `python-pptx` | Slide text extraction |
| PPT | libreoffice headless → PPTX → python-pptx | Legacy format conversion |
| XLSX | `openpyxl` | Dump sheets as markdown tables |
| XLS | `xlrd` | Legacy Excel support |
| CSV | Python stdlib `csv` | Dump as markdown table |
| MD | Direct read | Already structured |
| TXT | Direct read | Plain text |

### Consolidation

All extracted text is merged into a single context document:

```
=== DOCUMENT: pitch-deck.pdf (slides) ===
[extracted text]

=== DOCUMENT: financials.xlsx (spreadsheet) ===
[markdown tables]

=== DOCUMENT: business-plan.docx ===
[extracted text]
```

This consolidated text is the input to all 8 analysis agents.

### File Limits

- Max 10 files per analysis
- Max 20MB per file
- Max 50MB total per analysis
- Validated on both client and server

## Analysis Agents

### Agent Design Pattern

All 8 agents share the same execution pattern:

- **Model:** `claude-sonnet-4-6` for analysis agents, `claude-opus-4-6` for final scoring
- **Input:** System prompt with evaluation rubric + consolidated document text
- **Web search:** Enabled via Perplexity API for market data, competitor info, team backgrounds
- **Output:** Structured JSON — score (0-100), summary, full markdown report, key_findings array
- **Error handling:** 1 automatic retry on failure, then status = failed with error message. Other agents continue regardless.

### The 8 Agents

**1. Problem & Solution**
Evaluates whether the problem is real and validated. Assesses solution defensibility and differentiation. Checks for problem-solution fit signals. Flags solutions looking for problems.

**2. Market & TAM**
Independently researches market size via web search. Validates or challenges the startup's TAM/SAM/SOM claims with external data. Produces a mini market report with cited sources. Flags unrealistic market sizing.

**3. Traction**
Evaluates revenue, users, growth rates, milestones against stage-appropriate benchmarks. Flags vanity metrics (downloads without engagement, GMV without revenue). Assesses product-market fit signals.

**4. Technology & IP**
Skeptical technical review against scientific consensus. Are the technical claims feasible with current technology? Any patents or trade secrets? Is the tech defensible or easily replicated? Flags pseudoscience or overblown technical claims.

**5. Competition & Moat**
Independently researches competitors via web search (not just what the deck lists). Maps the competitive landscape. Evaluates switching costs, network effects, data moats, brand moats. Identifies competitors the startup may have omitted.

**6. Team**
Researches founders' and key team members' backgrounds via web search. Evaluates domain expertise, previous startup experience, exits. Identifies gaps (e.g., all technical founders, no go-to-market person). Assesses advisor quality and relevance.

**7. GTM & Business Model**
Evaluates go-to-market strategy feasibility. Sanity-checks unit economics (CAC, LTV, margins). Assesses pricing strategy against market norms. Evaluates customer acquisition channels and scalability.

**8. Financials & Fundraising**
Sanity-checks financial projections against industry benchmarks. Analyzes burn rate and runway. Recommends appropriate raise amount based on stage and plan. Evaluates regional fundraising realities by state and vertical. Assesses exit probability, expected value, and timeline based on comparable outcomes.

### Final Scoring Agent

Runs after all 8 agents complete. Uses `claude-opus-4-6`.

**Input:** All 8 agent reports + scores.

**Output:**
- `overall_score` — weighted composite (0-100)
- `fundraising_likelihood` — probability of successfully raising (0-100%)
- `recommended_raise` — dollar amount with range (e.g. "$2-3M")
- `exit_likelihood` — probability of meaningful exit (0-100%)
- `expected_exit_value` — range (e.g. "$50-100M")
- `expected_exit_timeline` — range (e.g. "5-7 years")
- `executive_summary` — one paragraph synthesis

## API Endpoints

All endpoints require authentication (`Depends(get_current_user)`).

### Upload & Job Management

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/analyze` | Multipart upload. Accepts files + company_name + publish_consent. Validates file types/sizes, uploads to S3, creates PitchAnalysis + AnalysisDocument records. Returns analysis ID. Checks subscription: if user has 1+ completed analyses and subscription_status != active → 402. |
| GET | `/api/analyze` | List user's analyses (for history page). Returns id, company_name, status, overall_score, created_at. |
| GET | `/api/analyze/{id}` | Analysis status + progress. Returns full PitchAnalysis record + all AnalysisReport statuses/scores (for polling). User can only access their own. |
| GET | `/api/analyze/{id}/reports` | All 8 agent reports for a completed analysis. Returns full report markdown + scores + key_findings. |
| GET | `/api/analyze/{id}/reports/{agent_type}` | Single agent report. |
| DELETE | `/api/analyze/{id}` | Soft delete. Marks analysis as deleted, cleans up S3 files. |
| PATCH | `/api/analyze/{id}` | Update publish_consent. If toggling to false and startup_id exists, sets the linked Startup to status=rejected (hides from public). If toggling to true, sets to status=approved. |
| POST | `/api/analyze/{id}/resubmit` | Upload new documents. Clears old S3 files + analysis_documents + analysis_reports. Resets analysis status to pending. Requires active subscription (not free). |

## Worker Container

### Docker Setup

New service `analysis_worker` in `docker-compose.prod.yml`. Based on Python slim image with `libreoffice-core` installed for .doc/.ppt conversion (~200MB addition).

Shares the same backend codebase (models, database connection, S3 client) but runs a different entrypoint: `python -m app.workers.analysis_worker`.

### Environment Variables (new)

- `ANTHROPIC_API_KEY` — for Claude API calls
- `AWS_ACCESS_KEY_ID` — S3 access
- `AWS_SECRET_ACCESS_KEY` — S3 access
- `S3_BUCKET_NAME` — e.g. "deepthesis-pitch-documents"

Plus existing: `ACUTAL_DATABASE_URL`, `ACUTAL_PERPLEXITY_API_KEY`.

### Job Loop

```
Every 5 seconds:
  1. Query pitch_analyses WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1
  2. Claim job: SET status = 'extracting'
  3. Download all analysis_documents from S3
  4. Extract text from each file using format-appropriate library
  5. Save extracted_text on each AnalysisDocument record
  6. Consolidate all extracted text into single context string
  7. SET status = 'analyzing'
  8. Create 8 AnalysisReport records with status = 'pending'
  9. Run all 8 agents in parallel via asyncio.gather():
     - SET report status = 'running', SET analysis current_agent = agent_type
     - Call Claude API with agent system prompt + consolidated text
     - Call Perplexity for web research where needed
     - Parse structured JSON response
     - Save score, summary, report, key_findings on AnalysisReport
     - SET report status = 'complete'
  10. Run final scoring agent (Opus): read all 8 reports → compute overall_score + fundraising metrics
  11. Save overall_score, fundraising_likelihood, recommended_raise, exit_likelihood, expected_exit_value, expected_exit_timeline on PitchAnalysis
  12. SET status = 'enriching'
  13. If publish_consent = true:
      - Run Perplexity enrichment (same as existing startup enrichment)
      - Create new Startup record with status = 'approved'
      - Link via startup_id on PitchAnalysis
  14. SET status = 'complete', SET completed_at = now()
```

### Error Handling

- Individual agent failure: report gets status = 'failed' with error message. Remaining agents continue. Overall analysis still completes with partial results.
- Extraction failure (all docs unreadable): entire job fails. SET status = 'failed' with error.
- Agent retry: 1 automatic retry per agent before marking as failed.
- Worker crash: job stays in 'extracting' or 'analyzing' status. Worker picks it up again on restart (add a `claimed_at` timestamp, reset jobs claimed more than 15 minutes ago).

## Frontend Pages

### `/analyze` — Upload Page

- **Not logged in:** Hero explaining the free analysis offer + sign up / sign in buttons
- **Logged in, eligible for free analysis:** Upload zone (drag & drop + file picker), company name text input, publish consent checkbox (default checked with explanatory copy: "Allow Deep Thesis to display your company on our public startup directory. Only your company name, industry, stage, and description are shown — reports, documents, and scores remain private."), submit button
- **Logged in, free analysis used, no subscription:** Paywall message — "Your free analysis is complete. Get unlimited analyses for $19.99/mo." CTA button (placeholder for Stripe, links to contact for now)
- **Logged in, active subscription:** Same upload zone as free analysis, no restrictions
- File type validation client-side (accept attribute + JS check). Size validation client-side with server enforcement.

### `/analyze/[id]` — Progress & Results

**While running (status != complete):**
- Company name header
- Progress card with 8 rows, one per agent:
  - Agent name | status icon (spinner if running, checkmark if complete, X if failed, dash if pending)
  - Shows which agent is currently running
- Overall progress bar (completed agents / 8)
- Polls backend every 3 seconds via `GET /api/analyze/{id}`

**When complete:**
- **Overview tab (default):**
  - Overall score (large, prominent)
  - Fundraising metrics: likelihood %, recommended raise, exit likelihood %, expected exit value, expected exit timeline
  - Executive summary paragraph
  - 8 score cards in a grid — agent name + score + one-line summary, colored by score (green/yellow/red)
- **8 agent tabs:**
  - Each tab shows the full markdown report rendered with proper formatting
  - Score badge at the top
  - Key findings highlighted
- **Actions:**
  - Download full report as PDF (all 8 reports combined)
  - Resubmit (upload new docs for re-evaluation, requires subscription)
  - Toggle publish consent
  - Delete analysis

### `/analyze/history` — Past Analyses

- List/card view of user's analyses
- Each card: company name, date submitted, overall score (color-coded), status badge
- Click through to `/analyze/[id]`
- Sort by date (newest first)

## Publish Consent & Public Startup Creation

When `publish_consent = true` and analysis completes:

1. Worker runs Perplexity enrichment using the company_name + extracted context
2. Creates a new `Startup` record with:
   - `name` = company_name
   - `status` = approved (visible on public site)
   - `ai_score` = overall_score from analysis
   - `enrichment_status` = complete
   - All Perplexity-enriched fields (tagline, description, industry, stage, funding, etc.)
   - `form_sources` = ["pitch_analysis"]
   - `data_sources` = field-level provenance as with existing enrichment
3. Links the Startup via `startup_id` on the PitchAnalysis record

The startup appears on the public site like any other enriched startup — same card format, same detail page. The analysis reports and uploaded documents are never exposed publicly.

**Toggle behavior:** If user later unchecks publish_consent, the linked Startup gets `status = rejected` (hidden from public). If they re-check, it goes back to `status = approved`.

## Out of Scope (Future Projects)

- Stripe subscription integration (v1 uses manual subscription_status field)
- Google Docs link import
- OCR for scanned PDFs
- Custom evaluation rubrics per industry
- Comparison analysis (analyze two startups side by side)
- Investor matching based on analysis results
