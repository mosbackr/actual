# Investor Extraction & Management — Design Spec

## Goal

Build an admin batch process that uses Perplexity to find ~200 prospective investors for each pre-seed/seed startup on the platform, store them in a deduplicated investor database, and provide an admin UI to browse/search/filter the results.

## Architecture

Three components: database tables, batch extraction service, admin frontend page.

## Data Model

### `investors` table

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| firm_name | String(300) | NOT NULL |
| partner_name | String(300) | NOT NULL |
| email | String(300) | nullable |
| website | String(500) | nullable |
| stage_focus | String(200) | e.g. "Pre-Seed, Seed" |
| sector_focus | String(500) | e.g. "AI/ML, Fintech, SaaS" |
| location | String(300) | e.g. "San Francisco, CA" |
| aum_fund_size | String(100) | e.g. "$50M" |
| recent_investments | JSON | Array of strings: ["Company A", "Company B"] |
| fit_reason | Text | Why Perplexity thinks they're a fit (from most recent extraction) |
| source_startups | JSON | Array of `{"id": "uuid", "name": "Company Name"}` |
| created_at | DateTime | |
| updated_at | DateTime | |

**Unique constraint**: `(firm_name, partner_name)` — for deduplication. On conflict, append to `source_startups` and update other fields if richer data is found.

**Future pivot**: If a many-to-many relationship is needed later, create an `investor_startup_sources` join table and migrate the JSON array. The `(firm_name, partner_name)` unique constraint ensures clean dedup regardless.

### `investor_batch_jobs` table

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| status | Enum | pending, running, paused, completed, failed |
| total_startups | Integer | Count of startups to process |
| processed_startups | Integer | How many done so far |
| current_startup_id | UUID | nullable, which startup is being processed now |
| current_startup_name | String | nullable, for display |
| investors_found | Integer | Running total of investors inserted/updated |
| error | Text | nullable |
| started_at | DateTime | nullable |
| paused_at | DateTime | nullable |
| completed_at | DateTime | nullable |
| created_at | DateTime | |

Only one job can be `running` or `paused` at a time (enforced in API).

## Batch Extraction Service

### Trigger

Admin clicks "Extract Investors" button. Backend creates a job record and starts processing in the analysis_worker (or a new background task).

### Process per startup

1. Query all pre-seed/seed startups with `status IN (approved, featured)` and `enrichment_status = complete`, ordered by `created_at ASC`.
2. For each startup, call Perplexity Sonar Pro with a prompt like:

```
You are an investor research analyst. Find 200 venture capital firms and angel investors
that would be interested in investing in this company:

Company: {name}
Description: {description}
Stage: {stage}
Industry: {industries}
Location: {location}
Website: {website_url}

For each investor, return:
- firm_name: The VC firm or angel investor organization name
- partner_name: The specific partner or person who leads deals at this stage
- email: Their professional email if publicly available, otherwise null
- website: Firm website
- stage_focus: What stages they typically invest in
- sector_focus: What sectors/industries they focus on
- location: Where the firm is based
- aum_fund_size: Approximate fund size or AUM if known
- recent_investments: List of 3-5 recent notable investments
- fit_reason: One sentence on why this investor would be interested in this specific company

Return as a JSON array of objects. Return exactly 200 investors.
Focus on investors who actively invest in {stage} stage companies in the {industries} space.
Include a mix of well-known firms and emerging/smaller funds.
```

3. Parse the JSON response. For each investor:
   - Check if `(firm_name, partner_name)` already exists
   - If exists: append this startup to `source_startups` (if not already there), update fields if new data is richer
   - If new: insert full record with `source_startups = [{"id": startup_id, "name": startup_name}]`

4. Update job progress: increment `processed_startups`, update `current_startup_id/name`, increment `investors_found`.

### Pause/Resume

- Before processing each startup, check if job status has been set to `paused` (by admin clicking Pause).
- If paused, stop the loop. `processed_startups` tracks where we left off.
- On restart, query the job, set status back to `running`, skip the first `processed_startups` startups, continue.

### Chunking Perplexity calls

Perplexity may not reliably return 200 investors in one call. Strategy:
- Make 2 calls per startup requesting 100 each, with the second call instructed to avoid duplicates from the first batch.
- Deduplicate within the response before inserting.

## Admin API Endpoints

### `POST /api/admin/investors/batch`
Start a new batch job. Returns job record. Fails if a job is already running/paused.

### `PUT /api/admin/investors/batch/{job_id}/pause`
Set job status to `paused`.

### `PUT /api/admin/investors/batch/{job_id}/resume`
Set job status back to `running`, restart processing from where it left off.

### `GET /api/admin/investors/batch/status`
Returns the current/latest job with progress info.

### `GET /api/admin/investors`
Paginated list with filters:
- `q` (text search across firm_name, partner_name, email)
- `stage_focus` (substring match)
- `sector_focus` (substring match)
- `location` (substring match)
- `source_startup_id` (filter by specific startup in source_startups JSON)
- `page`, `per_page` (default 50)
- `sort` (firm_name, partner_name, created_at)

Returns: `{ total, page, per_page, pages, items: [...] }`

### `GET /api/admin/investors/{id}`
Single investor detail.

### `DELETE /api/admin/investors/{id}`
Remove an investor record.

## Admin Frontend

### Sidebar
Add "Investors" link to the admin sidebar, below "Startups".

### Investors Page (`/admin/app/investors/page.tsx`)

**Top section — Batch control:**
- If no job running: "Extract Investors" button
- If running: progress bar showing `{processed_startups}/{total_startups}` startups, current startup name, total investors found, "Pause" button
- If paused: same progress info, "Resume" button
- Polls `GET /api/admin/investors/batch/status` every 3 seconds while running

**Main section — Investor table:**
- Uses existing `DataTable` component
- Columns: Firm Name, Partner, Email, Stage Focus, Sector Focus, Location, Sources (count badge)
- Search bar for text search
- Filter dropdowns/pills for stage, sector, location
- Pagination
- Click row to expand/view detail (fit_reason, recent_investments, full source startup list)

## Error Handling

- If Perplexity call fails for a startup, log the error, skip that startup, continue to next. Don't fail the whole batch.
- Store per-startup errors in job `error` field (append).
- If the worker crashes, job stays in `running` state. A stale job check (similar to analysis_worker) resets jobs stuck in `running` for > 30 minutes back to `paused` so they can be resumed.

## No Scope

- No export/CSV download (can add later)
- No email outreach features
- No investor editing from admin UI
- No automatic triggering after enrichment (manual only)
