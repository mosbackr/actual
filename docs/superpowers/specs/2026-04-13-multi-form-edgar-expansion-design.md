# Multi-Form EDGAR Expansion

## Goal

Expand the EDGAR pipeline from Form D-only discovery to all useful SEC form types (S-1, 10-K, Form C, Form 1-A), use form-specific parsers to extract richer data, track data provenance at both startup and field level, and enrich existing startups with data from additional forms.

## Architecture

Two modes of operation:

1. **Discovery**: Search EFTS for each form type, extract company info, dedup against existing DB, create new startups, enrich via Perplexity
2. **Enrichment of existing**: When processing a known startup's filings, pull data from all available form types to fill gaps using source priority rules

### Data Flow

```
Admin triggers scan (all forms or per-form override)
  → discover_filings step per form type (parallel-safe)
  → extract_company step per hit (form-aware parsing)
  → add_startup step (classify startup/fund, create record, tag form source)
  → enrich_startup step (Perplexity enrichment + scoring, startups only)
```

### Parsing Strategy

| Form | Parser | API | Notes |
|------|--------|-----|-------|
| Form D | XML (deterministic) | None | Existing parser, minimal data |
| Form C, C-U, C/A | XML (deterministic) | None | Similar structure to Form D but richer |
| S-1, S-1/A | HTML extraction | Claude API | Existing parser, richest data source |
| 10-K, 10-K/A | HTML extraction | Claude API | Existing parser, financial data |
| Form 1-A, 1-A/A | HTML extraction | Claude API | New parser, similar to S-1 pattern |
| Classification | Text prompt | Perplexity | Startup vs fund (existing) |
| Enrichment + scoring | Text prompt | Perplexity | Data gaps + AI scoring (existing) |

**Requires**: Anthropic API key added to server `.env` for Claude-based HTML parsing.

## EFTS Search Expansion

New search functions in `edgar.py`, one per form type. All use the same EFTS endpoint with different `forms=` parameter:

| Function | EFTS `forms=` | Expected volume (365d) | Startup rate |
|---|---|---|---|
| `search_form_d_filings()` | `D` | ~10,000+ | ~15% |
| `search_s1_filings()` | `S-1,S-1/A` | ~500-800 | ~95% |
| `search_10k_filings()` | `10-K,10-K/A` | ~8,000+ | ~30% |
| `search_form_c_filings()` | `C,C-U,C/A` | ~2,000-4,000 | ~90% |
| `search_form_1a_filings()` | `1-A,1-A/A` | ~500-1,000 | ~80% |

## New Parsers

### Form C (XML)

Regulation Crowdfunding offerings. XML structure similar to Form D but richer:

- Company name, CIK, state
- Business description and plan
- Number of employees
- Revenue and net income (last 2 fiscal years)
- Amount being raised (target + maximum)
- Use of proceeds
- Officers/directors with titles
- Compensation of officers

Parser: Deterministic XML like `parse_form_d()`. No API call needed.

### Form 1-A (HTML)

Regulation A offering circulars:

- Business description
- Use of proceeds
- Management team + compensation
- Financial statements (2 years)
- Risk factors
- Capitalization table

Parser: Claude API extraction, same pattern as `parse_s1_html()`.

### S-1 and 10-K

Already have Claude-based parsers. No parser changes needed. Wire them into the discovery flow (currently only used in "Match" flow). When discovering an S-1, use parsed data to populate the startup directly instead of relying solely on enrichment.

## Database Changes

### Startup model — two new JSON columns

- `form_sources`: JSON array — `["D", "S-1", "10-K"]` — which SEC forms contributed data
- `data_sources`: JSON object — field-level provenance for ALL fields, including Perplexity and Logo.dev sourced data

Example `data_sources`:
```json
{
  "description": "S-1",
  "revenue_estimate": "S-1",
  "employee_count": "S-1",
  "total_funding": "S-1",
  "business_model": "S-1",
  "funding_rounds": "S-1",
  "founders": "S-1",
  "website_url": "perplexity",
  "tagline": "perplexity",
  "logo_url": "logo.dev",
  "linkedin_url": "perplexity",
  "twitter_url": "perplexity",
  "crunchbase_url": "perplexity",
  "competitors": "perplexity",
  "tech_stack": "perplexity",
  "hiring_signals": "perplexity",
  "patents": "perplexity",
  "key_metrics": "perplexity",
  "company_status": "perplexity",
  "ai_score": "perplexity",
  "industry": "perplexity",
  "stage": "D",
  "location_city": "perplexity",
  "location_state": "D",
  "location_country": "D",
  "founded_date": "perplexity",
  "media": "perplexity"
}
```

### EdgarStepType enum

No new step types. Keep single `discover_filings` type and differentiate via `params.form_type`.

### Scan mode

The `scan_mode` field on EdgarJob already supports `full`, `new_only`, `discover`. The start endpoint gains a `form_types` parameter:

```json
{"scan_mode": "discover", "form_types": ["D", "S-1", "10-K", "C", "1-A"]}
{"scan_mode": "discover", "form_types": ["S-1"]}
```

Default (no `form_types` specified): all five form types.

### Alembic migration

- Add `form_sources` JSON column to `startups` (default `[]`)
- Add `data_sources` JSON column to `startups` (default `{}`)

## Worker Flow

### Discovery phase

When a combined scan starts, create one `discover_filings` step per form type:

```
discover_filings (form_type="D", discover_days=365)
discover_filings (form_type="S-1", discover_days=365)
discover_filings (form_type="10-K", discover_days=365)
discover_filings (form_type="C", discover_days=365)
discover_filings (form_type="1-A", discover_days=365)
```

These run in parallel (different EFTS queries, no conflicts).

### Extract phase

`extract_company` receives `form_type` from its parent discover step. Per form type:

- **Form D**: Parse XML, check SIC whitelist, check qualifying amount ($500K-$500M). Same as today.
- **S-1**: Every hit is a real company. Skip SIC filter. Parse HTML via Claude for business description, funding history, financials.
- **10-K**: Apply SIC whitelist (filter old-economy companies). Parse HTML via Claude for revenue, employees, business description.
- **Form C**: Parse XML for company info, business plan, financials. Lower amount threshold (Form C caps at $5M, so qualifying range: $50K-$5M).
- **Form 1-A**: Parse HTML via Claude. Medium amount threshold (Form 1-A caps at $75M, so qualifying range: $500K-$75M).

### Dedup

Same as today (CIK match first, then name match). If a startup already exists, instead of skipping, check if the new form has higher-priority data and update fields accordingly. Add form type to `form_sources` array.

### Add startup

Same flow but:

- Sets `form_sources` to include the discovering form type
- Sets `data_sources` for each field populated from the filing
- Classification (startup vs fund) runs for Form D and Form 1-A (fund noise). Skipped for S-1 and Form C (virtually all startups). 10-K: skip classification (public companies are real companies).

### Enrich startup

Same as today. Perplexity fills gaps not covered by filing data. Fields already populated from a higher-priority form source are not overwritten. Enrichment updates `data_sources` for each field it sets.

## Data Priority & Merge Logic

When multiple forms provide the same field:

**Priority order (highest wins):**
```
S-1 > 10-K > Form C > Form 1-A > Form D > Perplexity
```

**Merge behavior:**

- Field is empty → set it, record source in `data_sources`
- Field has value from lower-priority source → overwrite, update `data_sources`
- Field has value from higher or equal priority source → keep existing

**Field availability by form type:**

| Field | Form D | S-1 | 10-K | Form C | Form 1-A |
|---|---|---|---|---|---|
| description | - | Yes | - | Yes | Yes |
| revenue_estimate | - | Yes | Yes | Yes | - |
| employee_count | - | - | Yes | Yes | - |
| total_funding | Yes (amount sold) | Yes (full history) | - | Yes (target) | Yes (offering) |
| funding_rounds | Yes (1 round) | Yes (multiple) | - | Yes (1 round) | Yes (1 round) |
| business_model | - | Yes | Yes | Yes | Yes |
| founders | - | Yes | - | Yes | Yes |
| risk factors | - | Yes | - | - | Yes |
| financials | - | Yes (audited) | Yes (audited) | Yes (unaudited) | Yes (unaudited) |

## Admin UI Changes

### Start scan dialog

- Add checkboxes for form types: Form D, S-1, 10-K, Form C, Form 1-A (all checked by default)
- "Select All / None" toggle

### Progress summary

Add counters per form type:
```
Form D: 8,432 found → 1,200 qualifying → 180 startups
S-1: 623 found → 590 qualifying → 412 startups
10-K: 2,100 found → 340 qualifying → 285 startups
Form C: 1,800 found → 1,650 qualifying → 1,400 startups
Form 1-A: 480 found → 380 qualifying → 310 startups
```

### Activity log

Extend log message formatting for new form types in the discovery flow. Each log entry already shows step_type.

No new pages needed.

## Frontend Data Source Display

On the startup detail page:

- Small "Source: S-1" or "Source: Perplexity" label next to each data field or section
- On startup card/list view, badge showing which forms contributed: `D` `S-1` `10-K` etc.
- Tooltip on hover with full form name (e.g., "Form D — SEC Private Placement Notice")

Reads from `form_sources` array and `data_sources` JSON on the startup. No new API endpoints needed.

## Files Affected

### Backend — modify

- `backend/app/services/edgar.py` — add EFTS search functions per form type
- `backend/app/services/edgar_processor.py` — add Form C XML parser, Form 1-A HTML parser, data priority merge logic
- `backend/app/services/edgar_worker.py` — form-aware discover/extract/add steps, provenance tracking
- `backend/app/services/enrichment.py` — update `data_sources` when setting fields
- `backend/app/models/startup.py` — add `form_sources` and `data_sources` columns
- `backend/app/api/admin_edgar.py` — accept `form_types` param, per-form progress counters, log messages
- `backend/alembic/versions/` — new migration for columns

### Frontend — modify

- Admin EDGAR page — form type checkboxes, per-form progress display
- Startup detail page — data source labels/tooltips
- Startup list/card — form source badges

### Backend — no changes

- `backend/app/models/edgar_job.py` — no new enums needed
- `backend/app/api/insights.py` — no changes (already filters by entity_type)
- `backend/app/api/startups.py` — no changes (already filters by entity_type)
