# Investor Rankings Design Spec

## Overview

Add a scoring and ranking system for every investor in the database. A batch pipeline uses Perplexity to research each investor's track record, merges findings with internal data, then uses Claude to compute 7 dimension scores (0-100) and generate an analyst narrative. Rankings are computed and viewed in the admin panel. Public-facing investor profiles with email outreach are a future phase, not in this scope.

## Data Model

### `investor_rankings` table

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Primary key |
| `investor_id` | FK → investors (unique) | One ranking per investor |
| `overall_score` | Float | Weighted composite of all 7 dimensions |
| `portfolio_performance` | Float | 0-100 score |
| `deal_activity` | Float | 0-100 score |
| `exit_track_record` | Float | 0-100 score |
| `stage_expertise` | Float | 0-100 score |
| `sector_expertise` | Float | 0-100 score |
| `follow_on_rate` | Float | 0-100 score |
| `network_quality` | Float | 0-100 score |
| `narrative` | Text | Claude-generated 2-3 paragraph analyst note |
| `perplexity_research` | JSONB | Raw Perplexity research responses for auditability |
| `scoring_metadata` | JSONB | Breakdown details per dimension (portfolio companies, exits, co-investors, internal matches, etc.) |
| `scored_at` | DateTime(tz) | When this scoring was last computed |
| `created_at` | DateTime(tz) | Record creation |
| `updated_at` | DateTime(tz) | Last update |

Unique constraint on `investor_id`. Re-scoring overwrites the existing record.

### `investor_ranking_batch_jobs` table

Same structure as existing `investor_batch_jobs`:

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Primary key |
| `status` | Enum: pending, running, paused, completed, failed | Job state |
| `total_investors` | Integer | Total investors to process |
| `processed_investors` | Integer | How many completed |
| `current_investor_id` | UUID, nullable | Currently processing |
| `current_investor_name` | String, nullable | Firm + partner name for display |
| `investors_scored` | Integer | Running count of successfully scored investors |
| `error` | Text, nullable | Accumulated error messages |
| `started_at` | DateTime, nullable | |
| `paused_at` | DateTime, nullable | |
| `completed_at` | DateTime, nullable | |
| `created_at` | DateTime | |

Constraint: only one job can be `running` or `paused` at a time.

## Scoring Pipeline

Three-step process per investor, executed as a batch with pause/resume support.

### Step 1: Perplexity Research (2 calls per investor)

**Call 1 — Portfolio & Performance:**
- Full investment history and notable portfolio companies
- Known exits (acquisitions, IPOs, return multiples if available)
- Fund size, AUM, fund vintage/performance
- Recent deal activity and investment frequency

**Call 2 — Network & Follow-on:**
- Co-investor relationships and syndicate partners
- Portfolio companies' subsequent fundraising rounds (did they raise again? who led?)
- Stage and sector patterns across their deals
- Reputation/thought leadership signals

Both calls use `sonar-pro` model, temperature 0.1, max_tokens 8000, timeout 120s. JSON response format with structured fields.

### Step 2: Internal Data Merge

Cross-reference Perplexity findings with our database:
- Match portfolio companies against `startups` table by name → pull `ai_score`, `company_status`, `stage`
- Match against `funding_rounds` → count deals where investor appears as `lead_investor` or in `other_investors`
- Compile internal match data into the scoring context
- Track which data points came from internal DB vs Perplexity

### Step 3: Claude Scoring + Narrative (1 call per investor)

Send the merged research to Claude (`claude-sonnet-4-6`) with structured prompt containing:
- All research data from steps 1-2
- Explicit scoring rubrics for each dimension
- Instructions to return JSON with 7 dimension scores and narrative

**Claude returns:**
```json
{
  "portfolio_performance": 82,
  "deal_activity": 71,
  "exit_track_record": 65,
  "stage_expertise": 88,
  "sector_expertise": 91,
  "follow_on_rate": 74,
  "network_quality": 79,
  "narrative": "..."
}
```

Overall score = equal-weighted average of all 7 dimensions (~14.3% each).

### Batch Mechanics

- Same pause/resume pattern as `InvestorBatchJob` in `investor_extraction.py`
- Admin triggers from admin panel
- Processes investors sequentially, commits after each one
- Per-investor errors logged and accumulated; batch continues to next investor on failure
- Checks job status before each investor for pause support
- On resume, skips already-scored investors and continues from checkpoint

## Scoring Rubrics

Baked into the Claude prompt for consistent scoring.

### Portfolio Performance (0-100)
- Quality of portfolio companies (active vs defunct, known metrics)
- Funding trajectory of portfolio companies (up-rounds, growing valuations)
- Weighted toward recent investments (last 3 years)
- Internal DB boost: if portfolio companies exist in our DB, factor in their `ai_score` and `company_status`

### Deal Activity (0-100)
- Volume of investments (more = higher, diminishing returns above ~50/yr)
- Recency — heavily weighted toward last 2 years
- Consistency — steady deal pace vs sporadic bursts

### Exit Track Record (0-100)
- Number of exits (acquisitions + IPOs)
- Quality of exits (IPO > major acquisition > acqui-hire)
- Known return multiples if available
- Exit rate as percentage of total portfolio

### Stage Expertise (0-100)
- Concentration/depth at specific stages
- Track record at those stages (do their seed bets reach Series A?)
- Bonus for clear thesis/specialization vs scattered across all stages

### Sector Expertise (0-100)
- Concentration in specific verticals
- Track record within those verticals (exits, up-rounds)
- Domain signals (board seats, speaking, thought leadership)

### Follow-on Rate (0-100)
- Percentage of portfolio companies that raised subsequent rounds
- Quality of follow-on investors attracted
- Time between rounds (faster = stronger signal)

### Network / Co-investor Quality (0-100)
- Quality tier of co-investors (top-tier VCs vs unknown angels)
- Diversity of co-investor network
- Repeat syndicate partnerships

### Overall Score
- Equal-weighted average of all 7 dimensions (~14.3% each)
- Can be reweighted later without re-scoring

## API Endpoints

All endpoints require `superadmin` role. Prefix: `/api/admin/investors/rankings`.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/admin/investors/rankings/batch` | POST | Start ranking batch job |
| `/api/admin/investors/rankings/batch/{job_id}/pause` | PUT | Pause running job |
| `/api/admin/investors/rankings/batch/{job_id}/resume` | PUT | Resume paused job |
| `/api/admin/investors/rankings/batch/status` | GET | Get latest job status and progress |
| `/api/admin/investors/rankings` | GET | List ranked investors, paginated, sortable |
| `/api/admin/investors/rankings/{investor_id}/rescore` | POST | Re-score a single investor |

### List endpoint query params
- `sort`: `overall_score` (default), `portfolio_performance`, `deal_activity`, `exit_track_record`, `stage_expertise`, `sector_expertise`, `follow_on_rate`, `network_quality`, `firm_name`
- `order`: `desc` (default), `asc`
- `q`: text search across firm_name, partner_name
- `min_score`: filter by minimum overall score
- `page`, `per_page` (default 50, max 200)

## Admin UI

Added to the existing admin investors page (`/admin/investors`) as a new "Rankings" tab alongside the existing investor list.

### Rankings Tab

**Batch Controls (top):**
- "Score All Investors" button — triggers batch job
- Progress bar while running: "Scoring investor 42/1,200 — Sequoia Capital (Alfred Lin)" with investors_scored count
- Pause/Resume buttons during job
- Completion summary when done

**Ranked Investor Table:**
- Columns: Rank, Firm, Partner, Overall Score, Portfolio Perf, Deal Activity, Exits, Stage, Sector, Follow-on, Network, Scored Date
- Sortable by clicking any score column header
- Search bar for filtering by name
- Expandable rows showing:
  - Full narrative text
  - Scoring metadata details
  - "Re-score" button for individual re-scoring
- Pagination controls

## Out of Scope (Future Phases)

- Public-facing investor profile pages
- Email outreach integration (sending "you've been ranked" emails)
- Linking investor email to public profile URL
- CSV/PDF export of rankings
- Score change tracking over time (historical scores)
- Automated re-scoring on schedule
- Investor self-claim / profile editing
