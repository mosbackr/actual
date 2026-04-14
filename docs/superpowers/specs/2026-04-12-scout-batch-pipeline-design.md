# Scout Batch Pipeline Design

## Overview

Automated background pipeline that sweeps geographic markets to discover investors, find their portfolio startups, add them to triage, and trigger enrichment — with full progress tracking, pause/resume, and rate limiting.

## Problem

Currently the admin manually:
1. Asks scout to find investors in a specific city/state at a specific stage
2. For each investor, asks scout to find their portfolio startups
3. Adds startups to triage one batch at a time
4. Approves each startup for enrichment with manual delays

This is dozens of manual scout requests per city, across many cities. The batch pipeline automates the entire loop.

## Two Modes

**Initial run:** Full geographic sweep across all locations and all stages. Discovers every investor and every portfolio company it can find. Used to seed the database for the first time.

**Refresh run:** Same geographic sweep, but scout prompts are modified to ask for investors and deals from the last N days (configurable, default 30). Dedup skips everything already in the system. Intended to run manually ~weekly to pick up new activity.

## Data Model

### `batch_jobs` table

| Column | Type | Description |
|---|---|---|
| id | UUID, PK | |
| job_type | enum("initial", "refresh") | Which mode |
| status | enum("pending", "running", "paused", "completed", "failed", "cancelled") | Current state |
| refresh_days | int, nullable | For refresh runs: how many days back to look (null for initial) |
| progress_summary | JSON | Running counts updated as job progresses |
| current_phase | enum("discovering_investors", "finding_startups", "enriching", "complete") | High-level phase |
| error | text, nullable | Set on fatal errors or after 3 consecutive step failures |
| created_at | datetime | |
| updated_at | datetime | |
| completed_at | datetime, nullable | |

`progress_summary` JSON shape:
```json
{
  "locations_total": 300,
  "locations_completed": 45,
  "investors_found": 128,
  "startups_found": 412,
  "startups_added": 380,
  "startups_skipped_duplicate": 32,
  "startups_enriched": 210,
  "startups_enrich_failed": 3,
  "current_location": "Austin, TX",
  "current_stage": "seed",
  "current_investor": "Techstars Austin"
}
```

### `batch_job_steps` table

| Column | Type | Description |
|---|---|---|
| id | UUID, PK | |
| job_id | UUID, FK → batch_jobs | Parent job |
| step_type | enum("discover_investors", "find_startups", "add_to_triage", "enrich") | What this step does |
| status | enum("pending", "running", "completed", "failed", "skipped") | |
| params | JSON | Input for this step |
| result | JSON, nullable | Output after completion |
| error | text, nullable | Error message if failed |
| sort_order | int | Execution order within the job |
| created_at | datetime | |
| completed_at | datetime, nullable | |

#### Step types and their params/results

**discover_investors:**
- params: `{"city": "Austin", "state": "TX", "country": "US", "stage": "seed"}`
- result: `{"investors": ["Techstars Austin", "Capital Factory", ...], "scout_reply": "..."}`
- Scout prompt: "Find all {stage} venture capital firms and angel investor groups in {city}, {state}, {country}" (refresh mode appends "that have made investments in the last {refresh_days} days")

**find_startups:**
- params: `{"investor": "Techstars Austin", "stage": "seed", "city": "Austin", "state": "TX", "country": "US"}`
- result: `{"startups": [{name, website_url, ...}], "scout_reply": "..."}`
- Scout prompt: "Find all {stage} startup investments made by {investor}" (refresh mode appends "in the last {refresh_days} days")

**add_to_triage:**
- params: `{"startup_candidates": [{name, website_url, description, stage, ...}], "source_investor": "Techstars Austin"}`
- result: `{"created": [{id, name, slug}], "skipped": ["DuplicateCo", ...]}`
- Uses existing `scout_add_startups` logic internally (dedup via normalized name + domain)

**enrich:**
- params: `{"startup_id": "uuid-here", "startup_name": "CompanyX"}`
- result: `{"ai_score": 72, "enrichment_status": "complete"}` or `{"error": "..."}`
- Calls existing `run_enrichment_pipeline` internally
- Before calling: sets startup status to "approved" (which is prerequisite for enrichment)

## Hardcoded Location List

```python
BATCH_LOCATIONS = [
    # US Tier 1
    {"city": "San Francisco", "state": "CA", "country": "US"},
    {"city": "New York", "state": "NY", "country": "US"},
    {"city": "Boston", "state": "MA", "country": "US"},
    {"city": "Los Angeles", "state": "CA", "country": "US"},
    {"city": "Seattle", "state": "WA", "country": "US"},
    {"city": "Austin", "state": "TX", "country": "US"},
    {"city": "Chicago", "state": "IL", "country": "US"},
    {"city": "Miami", "state": "FL", "country": "US"},
    {"city": "Denver", "state": "CO", "country": "US"},
    {"city": "Washington", "state": "DC", "country": "US"},
    # US Tier 2
    {"city": "San Diego", "state": "CA", "country": "US"},
    {"city": "Atlanta", "state": "GA", "country": "US"},
    {"city": "Dallas", "state": "TX", "country": "US"},
    {"city": "Houston", "state": "TX", "country": "US"},
    {"city": "Philadelphia", "state": "PA", "country": "US"},
    {"city": "Minneapolis", "state": "MN", "country": "US"},
    {"city": "Detroit", "state": "MI", "country": "US"},
    {"city": "Pittsburgh", "state": "PA", "country": "US"},
    {"city": "Nashville", "state": "TN", "country": "US"},
    {"city": "Raleigh-Durham", "state": "NC", "country": "US"},
    {"city": "Salt Lake City", "state": "UT", "country": "US"},
    {"city": "Portland", "state": "OR", "country": "US"},
    {"city": "Phoenix", "state": "AZ", "country": "US"},
    {"city": "Columbus", "state": "OH", "country": "US"},
    {"city": "Indianapolis", "state": "IN", "country": "US"},
    {"city": "St. Louis", "state": "MO", "country": "US"},
    {"city": "Baltimore", "state": "MD", "country": "US"},
    {"city": "Tampa", "state": "FL", "country": "US"},
    {"city": "Charlotte", "state": "NC", "country": "US"},
    {"city": "Las Vegas", "state": "NV", "country": "US"},
    {"city": "Cincinnati", "state": "OH", "country": "US"},
    {"city": "Kansas City", "state": "MO", "country": "US"},
    {"city": "Birmingham", "state": "AL", "country": "US"},
    {"city": "Madison", "state": "WI", "country": "US"},
    {"city": "Omaha", "state": "NE", "country": "US"},
    # International - North America
    {"city": "Toronto", "state": None, "country": "Canada"},
    {"city": "Vancouver", "state": None, "country": "Canada"},
    {"city": "Montreal", "state": None, "country": "Canada"},
    # International - Europe
    {"city": "London", "state": None, "country": "UK"},
    {"city": "Berlin", "state": None, "country": "Germany"},
    {"city": "Paris", "state": None, "country": "France"},
    {"city": "Amsterdam", "state": None, "country": "Netherlands"},
    {"city": "Stockholm", "state": None, "country": "Sweden"},
    # International - Asia-Pacific
    {"city": "Singapore", "state": None, "country": "Singapore"},
    {"city": "Sydney", "state": None, "country": "Australia"},
    {"city": "Bangalore", "state": None, "country": "India"},
    {"city": "Tel Aviv", "state": None, "country": "Israel"},
    # International - Latin America
    {"city": "Sao Paulo", "state": None, "country": "Brazil"},
    {"city": "Mexico City", "state": None, "country": "Mexico"},
    {"city": "Bogota", "state": None, "country": "Colombia"},
]

BATCH_STAGES = ["pre_seed", "seed", "series_a", "series_b", "series_c", "growth"]
```

50 locations x 6 stages = 300 initial discover_investors steps.

## Worker Loop

Single async function `run_batch_worker(job_id)`:

```
loop:
  1. Check job.status — if "paused" or "cancelled", exit loop
  2. Get next step where status="pending", ordered by sort_order
  3. If no pending steps, mark job as "completed", exit
  4. Mark step as "running"
  5. Execute step based on step_type:
     - discover_investors → call scout with investor discovery prompt
     - find_startups → call scout with portfolio discovery prompt
     - add_to_triage → call existing scout_add logic
     - enrich → set status=approved, call run_enrichment_pipeline, wait for it
  6. On success: mark step "completed", save result, generate follow-on steps
  7. On failure: mark step "failed", save error, increment consecutive_failures
     - If 3 consecutive failures → pause job, set error message, exit
     - Otherwise continue
  8. Update job.progress_summary with latest counts
  9. Wait delay based on step type, then goto 1
```

### Rate Limiting Delays

| Step Type | Delay After | Reason |
|---|---|---|
| discover_investors | 90 seconds | Perplexity API breathing room |
| find_startups | 90 seconds | Perplexity API breathing room |
| add_to_triage | 2 seconds | DB only, minimal delay |
| enrich | 10 seconds | Enrichment itself makes 2 Perplexity calls internally |

### Follow-on Step Generation

After `discover_investors` completes:
- For each investor name in the result, create a `find_startups` step
- Skip investors that already have a completed `find_startups` step in any batch job (dedup across runs)
- New steps get `sort_order` values that place them after all existing discover steps (so we finish discovering a full location/stage block before diving into startups)

After `find_startups` completes:
- Create one `add_to_triage` step with all the startup candidates from this investor
- `add_to_triage` step is created immediately after its parent `find_startups` step in sort order

After `add_to_triage` completes:
- For each startup that was actually created (not skipped as duplicate), create an `enrich` step
- Enrich steps go at the end of the current sort order

### Pause / Resume / Cancel

- **Pause:** Set `job.status = "paused"`. Worker exits at next loop iteration check. Current step finishes executing (no mid-step interruption).
- **Resume:** Set `job.status = "running"`. Launch new `run_batch_worker(job_id)` as background task. It picks up the next pending step.
- **Cancel:** Set `job.status = "cancelled"`. Same as pause — worker exits, but the intent is to not resume. Can still be resumed if needed.
- **Server restart:** Job stays in "running" status but no worker is active. Admin UI should detect this (status is "running" but no steps have progressed in >5 minutes) and show a "Restart worker" button that re-launches the worker.

### Deduplication (Multi-Layer)

1. **Investor dedup:** Before creating `find_startups` steps, check if this investor name (normalized) already has a completed `find_startups` step in any previous batch job. If so, skip on refresh runs. On initial runs, skip if same investor was already found in this job.

2. **Startup dedup at triage:** Uses existing `find_duplicate(db, name, website_url)` from `dedup.py` — checks normalized name and domain against all existing startups. Duplicates are skipped and counted in `startups_skipped_duplicate`.

3. **Startup dedup at enrich:** Before creating enrich steps, verify the startup still exists and hasn't already been enriched (status check on `enrichment_status`).

## Scout Prompts

### Discover Investors (Initial)
```
Find all {stage_label} venture capital firms, angel investor groups, and startup accelerators
that are actively investing in {city}, {state_or_country}.

Return EVERY firm you can find — include fund name, notable partners, investment focus,
and approximate deal count. Be thorough and search multiple sources.
```

### Discover Investors (Refresh)
```
Find all {stage_label} venture capital firms, angel investor groups, and startup accelerators
that have made investments in {city}, {state_or_country} in the last {refresh_days} days.

Return EVERY firm you can find — include fund name, notable partners, investment focus,
and approximate deal count. Be thorough and search multiple sources.
```

### Find Startups (Initial)
```
Find all startup investments made by {investor_name} at the {stage_label} stage.
List every portfolio company you can find with their details.
```

### Find Startups (Refresh)
```
Find all startup investments made by {investor_name} at the {stage_label} stage
in the last {refresh_days} days. List every new portfolio company you can find with their details.
```

Note: These prompts are prepended with the existing `SCOUT_SYSTEM_PROMPT` from `admin_scout.py` which instructs the AI to return structured JSON. The batch pipeline reuses this system prompt unchanged.

## API Endpoints

All under `/api/admin/batch/`, all require superadmin role.

### `POST /api/admin/batch/start`
Start a new batch job. Only one job can be running at a time.
```json
// Request
{"job_type": "initial"}
// or
{"job_type": "refresh", "refresh_days": 30}

// Response
{"job_id": "uuid", "status": "running", "total_steps": 300}
```

### `POST /api/admin/batch/{job_id}/pause`
```json
{"status": "paused"}
```

### `POST /api/admin/batch/{job_id}/resume`
```json
{"status": "running"}
```

### `POST /api/admin/batch/{job_id}/cancel`
```json
{"status": "cancelled"}
```

### `GET /api/admin/batch/active`
Returns current/most recent job with progress summary.
```json
{
  "id": "uuid",
  "job_type": "initial",
  "status": "running",
  "current_phase": "discovering_investors",
  "progress_summary": { ... },
  "created_at": "...",
  "updated_at": "...",
  "elapsed_seconds": 3420
}
```

### `GET /api/admin/batch/{job_id}/steps`
Paginated steps list. Query params: `step_type`, `status`, `page`, `per_page`.
```json
{
  "total": 450,
  "page": 1,
  "per_page": 50,
  "items": [
    {
      "id": "uuid",
      "step_type": "discover_investors",
      "status": "completed",
      "params": {"city": "Austin", "state": "TX", "country": "US", "stage": "seed"},
      "result": {"investors": ["Techstars", "Capital Factory"]},
      "created_at": "...",
      "completed_at": "..."
    }
  ]
}
```

### `GET /api/admin/batch/{job_id}/investors`
Aggregated investor view.
```json
{
  "total": 128,
  "items": [
    {
      "name": "Techstars Austin",
      "city": "Austin",
      "state": "TX",
      "country": "US",
      "stage": "seed",
      "startups_found": 12,
      "status": "completed"
    }
  ]
}
```

### `GET /api/admin/batch/{job_id}/startups`
All startups from this batch with pipeline status.
```json
{
  "total": 380,
  "items": [
    {
      "id": "uuid",
      "name": "CompanyX",
      "source_investor": "Techstars Austin",
      "stage": "seed",
      "city": "Austin",
      "state": "TX",
      "triage_status": "approved",
      "enrichment_status": "complete",
      "ai_score": 72
    }
  ]
}
```

### `GET /api/admin/batch/{job_id}/log`
Recent activity log, most recent first.
```json
{
  "items": [
    {
      "timestamp": "2026-04-12T15:30:00Z",
      "message": "Found 8 pre-seed investors in Austin, TX",
      "step_type": "discover_investors",
      "status": "completed"
    }
  ]
}
```

## Admin UI

New page at `/batch` in the admin panel. Added to the sidebar navigation.

### Control Bar (top)
- Two buttons: "Start Initial Batch" / "Start Refresh Batch" (with refresh_days input, default 30)
- Buttons disabled when a job is running/paused
- Status badge showing job state with color coding
- Pause / Resume / Cancel buttons (shown contextually)
- Elapsed time counter (live)
- Summary stat row: locations swept, investors found, startups added, startups enriched, duplicates skipped

### Progress View (middle, tabbed)

**Locations tab:**
- Table grouped by location
- Each location has nested rows for each stage
- Columns: Location, Stage, Status (badge), Investors Found
- Current row highlighted with accent color
- Completed rows show green checkmark

**Investors tab:**
- Flat table of all discovered investors
- Columns: Investor Name, Location, Stage, Startups Found, Status
- Filterable by location and stage
- Sortable by any column

**Startups tab:**
- Table of all startups from this batch
- Columns: Name, Source Investor, Location, Stage, Pipeline Status, AI Score
- Pipeline status shown as colored badge: Triage (gray) → Enriching (yellow) → Enriched (green) → Failed (red)
- Failed rows show error tooltip on hover
- Filterable by status

### Live Log (bottom)
- Scrolling log feed, most recent at top
- Auto-scrolls when new entries appear
- Each entry: timestamp, message, status icon
- Shows last 100 entries, "Load more" button for history

### Polling
- Every 5 seconds when job is running
- Every 30 seconds when paused or no active job
- Fetches: active job summary + current tab's data + latest log entries

## Files to Create/Modify

### New files:
- `backend/app/models/batch_job.py` — BatchJob and BatchJobStep models
- `backend/app/services/batch_worker.py` — Worker loop, step execution, follow-on generation
- `backend/app/services/batch_locations.py` — Hardcoded BATCH_LOCATIONS and BATCH_STAGES
- `backend/app/api/admin_batch.py` — API endpoints
- `admin/app/batch/page.tsx` — Admin UI page

### Modified files:
- `backend/app/main.py` — Register batch router
- `backend/app/models/__init__.py` — Import new models (if exists)
- `admin/components/Sidebar.tsx` — Add "Batch" nav item
- Alembic migration for new tables

## Internal Reuse

The batch worker does NOT call the admin API endpoints via HTTP. Instead it directly reuses:

- **From `admin_scout.py`:** The Perplexity API call logic (httpx client, system prompt, retry logic), `_extract_startups_from_response()`, `_clean_reply()`, and the `StartupCandidate` model. These should be extracted into a shared service module (`services/scout.py`) that both the admin endpoint and the batch worker import.
- **From `admin_scout.py`:** The `scout_add_startups` dedup-and-create logic. Also extracted to the shared service.
- **From `services/enrichment.py`:** `run_enrichment_pipeline(startup_id)` called directly.
- **From `services/dedup.py`:** `find_duplicate()`, `normalize_name()`, `normalize_domain()` called directly.

This avoids HTTP overhead, auth token management, and keeps the batch worker as a pure internal service.
