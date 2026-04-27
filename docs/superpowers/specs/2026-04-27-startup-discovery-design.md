# Startup Discovery Pipeline Design Spec

## Overview

Build a startup discovery pipeline that sources companies from Delaware C-corp filings, enriches founders via Proxycurl (work history, education, location from LinkedIn), classifies real startups vs noise using Claude, and enriches qualified startups via Perplexity. Admin-only batch process with pause/resume support. Discovered startups feed into the existing startup model and analysis infrastructure.

## Rationale

~90%+ of VC-backable startups incorporate as Delaware C-corps. A Delaware filing is one of the earliest detectable signals that someone is starting a fundable company. Combined with Proxycurl for founder enrichment and Claude for classification, this pipeline can identify ~70-75% of new venture-targetable startups within days of formation.

The target dataset is ~250K startups from the last 3-5 years — the entire addressable universe of early-stage venture.

## Data Model

### `founders` table (new)

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Primary key |
| `startup_id` | FK -> startups | Which company this founder belongs to |
| `full_name` | String(300) | Full name from LinkedIn |
| `linkedin_url` | String(500) | LinkedIn profile URL |
| `title` | String(300) | Current title (CEO, CTO, etc.) |
| `location` | String(300) | City, State, Country from LinkedIn |
| `headline` | String(500) | LinkedIn headline |
| `work_history` | JSONB | Array of `{company, title, start_date, end_date, description}` |
| `education` | JSONB | Array of `{school, degree, field, start_year, end_year}` |
| `profile_photo_url` | String(500) | LinkedIn photo URL |
| `proxycurl_raw` | JSONB | Full Proxycurl response for auditability |
| `created_at` | DateTime(tz) | Record creation |
| `updated_at` | DateTime(tz) | Last update |

### Changes to `startups` table

- Add `discovered` to `StartupStatus` enum
- Add `discovery_source` column — String(50), nullable. Values: `"delaware"`, `"manual"`, null for existing records.
- Add `delaware_corp_name` column — String(300), nullable. The official filing name when different from brand name.
- Add `delaware_file_number` column — String(50), nullable, unique. Unique identifier from Delaware filing. Used for deduplication.
- Add `delaware_filed_at` column — Date, nullable. Incorporation date from filing.
- Add `classification_status` column — Enum: `unclassified`, `startup`, `not_startup`, `uncertain`. Default `unclassified`.
- Add `classification_metadata` column — JSONB, nullable. Claude's classification reasoning and signals.

### `discovery_batch_jobs` table (new)

Same pattern as `InvestorBatchJob` and `InvestorRankingBatchJob`.

| Column | Type | Purpose |
|--------|------|---------|
| `id` | UUID PK | Primary key |
| `status` | String(20) | pending, running, paused, completed, failed |
| `job_type` | String(30) | `"bulk_import"`, `"daily_scrape"`, `"classify"`, `"enrich"` |
| `total_items` | Integer | Total items to process |
| `processed_items` | Integer | How many completed |
| `current_item_name` | String(300), nullable | Currently processing |
| `items_created` | Integer | Count of new startups/founders created |
| `error` | Text, nullable | Accumulated error messages |
| `started_at` | DateTime(tz), nullable | |
| `paused_at` | DateTime(tz), nullable | |
| `completed_at` | DateTime(tz), nullable | |
| `created_at` | DateTime(tz) | Record creation |

Reuses `BatchJobStatus` enum from `app.models.investor`.

## Pipeline Steps

Six-step pipeline. Steps 1-2 handle data acquisition. Steps 3-6 run as a single batch with pause/resume, processing each startup through the full sequence before moving to the next.

### Step 1: Bulk Import (one-time backfill)

- Admin uploads Delaware bulk dataset (CSV) via admin UI
- Parse and insert into `startups` table:
  - `status` = `discovered`
  - `discovery_source` = `"delaware"`
  - `classification_status` = `unclassified`
  - `name` = corp name from filing (initial value; may be updated later when brand name is discovered)
  - `delaware_corp_name` = corp name from filing
  - `delaware_file_number` = file number from filing
  - `delaware_filed_at` = filing date
- Deduplicate on `delaware_file_number` — skip if already exists
- Filter out non-C-corp entity types during import (LLCs, LPs, etc.)
- Generate slug from corp name with random suffix to avoid collisions (e.g. `acme-technologies-a3f2`). Slug is updated when brand name is discovered in Step 4c.

**Expected CSV columns:** file_number, entity_name, entity_type, filed_date, state, status. Exact column mapping will be determined by the actual bulk data format.

### Step 2: Daily Scraper (ongoing)

- Scrape Delaware Division of Corporations website for new C-corp filings since last run
- Same insert logic as bulk import
- Rate-limited to 1-2 requests/second to be respectful
- Triggered via admin UI or scheduled cron
- Stores the last-scraped date to know where to resume

### Step 3: Heuristic Filter

Regex/keyword pass on `unclassified` records. Marks obvious non-startups as `classification_status=not_startup`. No API calls.

**Filter patterns (mark as not_startup):**
- "Holdings", "Holding Company", "Holding Co"
- "Real Estate", "Realty", "Properties", "Property Management"
- "Trust", "Trustee"
- "Insurance", "Assurance"
- "Bank", "Banking", "Financial Services"
- "Church", "Ministry", "Ministries", "Temple", "Mosque"
- "Foundation" (standalone, not in "AI Foundation" etc.)
- "Association", "Society"
- "Mortgage", "Lending"
- "Construction", "Contracting", "Contractors"
- "Restaurant", "Restaurants", "Food Service"
- "Consulting Group" (ambiguous but mostly not startups at scale)
- "Capital LLC", "Capital LP" (SPVs/fund vehicles)
- "Management Company", "Management Co"

Records that pass the heuristic filter remain `unclassified` and proceed to Step 4.

### Step 4: Founder Discovery + Proxycurl Enrichment

For each `unclassified` startup (those that passed the heuristic filter):

**4a. Find founder LinkedIn URLs (two methods, try both):**

1. **Proxycurl Company API** — Look up company LinkedIn page by name. If found, get employee list to identify founders/C-suite.
2. **Google Search fallback** — Search `"Corp Name" founder OR CEO site:linkedin.com/in`. Parse search results for LinkedIn profile URLs.

Use Google Custom Search API or SerpAPI for the search step.

**4b. Enrich founder profiles via Proxycurl Person API:**

For each discovered founder LinkedIn URL:
- Call Proxycurl Person Profile API (~$0.01/lookup)
- Extract: full name, headline, title, location, work history, education, profile photo
- Insert into `founders` table with full `proxycurl_raw` response

**4c. Brand name resolution:**

If the founder's LinkedIn shows a current company name different from the Delaware corp name:
- Update `startups.name` to the brand name from LinkedIn
- Keep `delaware_corp_name` as the filing name
- Update slug

**Cost:** ~$0.02-0.04 per startup (company lookup + 1-2 person lookups).

### Step 5: Claude Classification

For each startup with founder data:

Send to Claude (`claude-sonnet-4-6`) via Anthropic Messages API:
- Delaware corp name
- Brand name (if different)
- Filing date
- All founder profiles: name, headline, work history, education, location

**Claude determines:**
- `startup` — This is a venture-backable technology startup
- `not_startup` — This is a traditional business, holding company, or non-tech entity
- `uncertain` — Not enough signal to determine

**Classification signals Claude evaluates:**
- Founder backgrounds (tech companies, CS degrees, prior startups)
- Company name signals (tech-sounding vs traditional business)
- Location (tech hubs get a slight boost but aren't determinative)
- Recency of founding
- Team composition (multiple technical co-founders = strong startup signal)

Stores classification result and reasoning in `classification_status` and `classification_metadata`.

**Cost:** ~$0.01-0.02 per startup (short prompt, structured output).

### Step 6: Perplexity Enrichment

For startups classified as `startup` only:

Call Perplexity (`sonar-pro`, temp 0.1, max_tokens 8000) to research:
- What the company does (product/service description)
- Market/industry
- Traction signals (press, product launches, app store, customers)
- Funding status (any announced rounds)
- Competitive landscape
- Team size / hiring signals

Populate existing startup fields:
- `description`, `tagline`
- `stage` (inferred from funding/team size)
- `total_funding`
- `employee_count`
- `website_url`, `linkedin_url`, `twitter_url`, `crunchbase_url`
- `industries` (link to existing industries table)
- `enrichment_status` = `complete`

Startups that complete this step are full records, ready for AI scoring via the existing analysis pipeline.

**Cost:** ~$0.05-0.10 per startup.

### Batch Execution

Steps 3-6 run as a single admin-triggered batch with pause/resume:
- Processing order per startup: heuristic check -> founder lookup -> classify -> enrich
- Each startup commits individually so progress is saved
- Per-startup errors logged and accumulated; batch continues to next startup on failure
- Checks job status before each startup for pause support
- On resume, skips already-processed startups
- Concurrency: 10 parallel workers with DB semaphore (matching investor_ranking.py pattern)

### Cost Estimates

For 50K startups passing the heuristic filter:
- Proxycurl: ~$1,000-2,000 (company + person lookups)
- Claude classification: ~$500-1,000
- Perplexity enrichment (assuming ~15-20K classified as startup): ~$1,000-2,000
- **Total initial backfill: ~$2,500-5,000**
- **Ongoing daily: ~$5-15/day** (50-100 new filings/day)

## API Endpoints

All require `superadmin` role. Prefix: `/api/admin/discovery`.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/admin/discovery/import` | POST | Upload bulk Delaware dataset (CSV) |
| `/api/admin/discovery/batch` | POST | Start classification + enrichment pipeline batch |
| `/api/admin/discovery/batch/{job_id}/pause` | PUT | Pause running job |
| `/api/admin/discovery/batch/{job_id}/resume` | PUT | Resume paused job |
| `/api/admin/discovery/batch/status` | GET | Get latest job status and progress |
| `/api/admin/discovery/startups` | GET | List discovered startups, paginated, filterable |
| `/api/admin/discovery/startups/{id}/promote` | PUT | Promote to `approved` status |
| `/api/admin/discovery/startups/{id}/reject` | PUT | Mark as `not_startup` |

### List endpoint query params

- `classification`: filter by classification_status (`all`, `startup`, `not_startup`, `uncertain`, `unclassified`)
- `enrichment`: filter by enrichment_status (`all`, `none`, `complete`, `failed`)
- `q`: text search across name, delaware_corp_name
- `sort`: `filed_date` (default), `name`, `created_at`
- `order`: `desc` (default), `asc`
- `page`, `per_page` (default 50, max 200)

## Admin UI

New page at `/admin/discovery` with sidebar link.

### Batch Controls (top section)

- **"Import Bulk Data"** button — file upload for CSV, triggers bulk import job
- **"Run Pipeline"** button — starts classification + enrichment batch on all unprocessed records
- Progress bar while running: "Processing 142/4,200 - Acme Technologies Inc" with running counts
- Pause/Resume buttons during job
- Completion summary when done

### Stats Bar

- Total filings imported
- Classified as startup
- Enriched
- Promoted to approved

### Discovered Startups Table

- **Columns:** Name, Delaware Corp Name, Filed Date, Classification, Founders (count), Enrichment Status, Actions
- **Filterable** by classification status tabs: All / Startup / Not Startup / Uncertain / Unclassified
- **Searchable** by name
- **Expandable rows** showing:
  - Founder details: name, title, location, headline
  - Work history (most recent 3 positions)
  - Education
  - Claude's classification reasoning
  - Company details once enriched (description, stage, funding, website)
- **Action buttons:** Promote to Approved, Reject
- **Pagination** controls

## External Service Dependencies

| Service | Purpose | Auth |
|---------|---------|------|
| Proxycurl | Company lookup + person profiles | API key (new config: `proxycurl_api_key`) |
| Google Custom Search / SerpAPI | Find founder LinkedIn URLs | API key (new config: `google_search_api_key` or `serp_api_key`) |
| Anthropic Claude | Classification | Existing `anthropic_api_key` |
| Perplexity | Startup enrichment | Existing `perplexity_api_key` |

Two new config entries in `Settings`:
- `proxycurl_api_key: str = ""`
- `serp_api_key: str = ""`

## Out of Scope (Future Phases)

- Automated daily scraper cron (manual trigger first, automate later)
- Public-facing discovered startup pages
- Automatic AI scoring of discovered startups (manual promotion first)
- Integration with investor matching pipeline
- Alerts/notifications for high-signal discoveries
- Historical filing backfill beyond 5 years
