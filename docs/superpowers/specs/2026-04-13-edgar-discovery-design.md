# EDGAR Company Discovery — Design Spec

## Goal

Extend the EDGAR scraper to discover new venture-backed startups from SEC Form D filings, extract structured data, add them to the database, and auto-enrich with Perplexity. EDGAR is the primary discovery source; Perplexity supplements with context (description, website, competitors, etc.). Companies land in "pending" status for admin review.

## Key Decisions

- **Trigger**: Separate "Discover New" button on EDGAR admin page (independent from existing "Run EDGAR Scan")
- **Time window**: Configurable, default 365 days
- **Filtering**: Aggressive — SIC code whitelist + amount range ($500K–$500M) to keep only venture-backed startups
- **Dedup**: Existing `normalize_name` service — no LLM needed
- **Enrichment**: Auto-enrich immediately with Perplexity after creation
- **Status**: New companies created as `pending` — admin reviews before going public
- **Location**: EDGAR-sourced location is authoritative — Perplexity enrichment must not overwrite it

---

## Architecture

### Extends the existing EDGAR system — same job/step models, same worker pattern.

New `EdgarJob` with `scan_mode="discover"`. Four new step types added to `EdgarStepType`:

1. **`discover_filings`** — Queries EDGAR full-text search API for recent Form D filings within the configured time window. Paginates through results (100/page). For each filing, checks SIC code against whitelist and downloads Form D XML to check raise amount ($500K–$500M). Generates one `extract_company` step per qualifying filing.

2. **`extract_company`** — Downloads Form D XML (reuses existing `parse_form_d`), extracts: company name, state of incorporation, SIC code, amount raised, date of first sale, number of investors, CIK. Runs dedup check against existing startups using `normalize_name`. If new company, generates `add_startup` step. If duplicate, skips and records match.

3. **`add_startup`** — Creates new `Startup` record with EDGAR-sourced data:
   - `name`: from Form D issuer name
   - `location_state`: from state of incorporation
   - `location_country`: "US" (EDGAR is US-only)
   - `stage`: inferred from raise amount (see table below)
   - `status`: pending (admin reviews before public)
   - `sec_cik`: from the filing (already resolved)
   - `description`: placeholder until Perplexity enriches
   - Creates initial `StartupFundingRound` with `data_source="edgar"`
   - Generates `enrich_startup` step

4. **`enrich_startup`** — Runs existing `run_enrichment_pipeline()` to fill in: description, website, logo, tagline, competitors, tech stack, additional funding rounds, AI scoring. Same logic as the batch worker's enrich step. Sets `enrichment_status` on completion. **Important:** EDGAR-sourced location data (state, country) must NOT be overwritten by Perplexity enrichment. EDGAR location is from legal filings and is authoritative. The enrichment pipeline should skip location fields for startups that have `sec_cik` set.

### Stage inference from Form D amount:

| Amount | Inferred Stage |
|--------|---------------|
| $500K–$2M | pre_seed |
| $2M–$10M | seed |
| $10M–$50M | series_a |
| $50M–$150M | series_b |
| $150M–$500M | series_c |

---

## EDGAR Full-Text Search API

The discovery phase uses EDGAR's EFTS (Electronic Full-Text Search):

```
https://efts.sec.gov/LATEST/search-index?q=*&forms=D&dateRange=custom&startdt=YYYY-MM-DD&enddt=YYYY-MM-DD&from=0&size=100
```

Returns JSON with `hits.hits[]` containing: `_source.file_num`, `_source.display_names`, `_source.period_of_report`, `_source.file_date`, plus `_id` (accession number). We paginate using `from` parameter.

For each hit, we need the CIK to fetch the actual Form D document. The CIK is embedded in the filing URL path or can be extracted from the accession number lookup.

### Rate limiting

Same 150ms delay between requests as the existing EDGAR client. Discovery scans may involve thousands of filings, so expect 5-10 minutes for a full year scan.

---

## SIC Code Whitelist

Target SIC codes for venture-backed startups:

| SIC Range | Industry |
|-----------|----------|
| 2830–2836 | Pharmaceutical/Biotech |
| 3570–3579 | Computer hardware |
| 3600–3699 | Electronic components |
| 3674 | Semiconductors |
| 3812 | Defense/navigation electronics |
| 3841–3845 | Medical devices/instruments |
| 4812–4813 | Telecommunications |
| 4899 | Communications services |
| 5045 | Computers & peripherals wholesale |
| 7371–7379 | Computer programming/software/services |
| 8711–8742 | Engineering/R&D/Management consulting |

Plus amount filter: $500K minimum (excludes tiny angel rounds), $500M maximum (excludes large fund formations, PE deals).

Entities with "FUND", "LP", "PARTNERS", "CAPITAL", "TRUST", "REIT", or "HOLDINGS" in the name are excluded (likely investment vehicles, not operating companies).

---

## Dedup Logic

Before creating a new startup:

1. Normalize the EDGAR issuer name using existing `normalize_name()` (strips "Inc.", "LLC", "Corp.", etc., lowercases, removes punctuation)
2. Query `startups` table for any row where `normalize_name(name)` matches
3. Also check `sec_cik` — if any existing startup already has this CIK, it's a match
4. If match found: skip, log as duplicate, optionally update `sec_cik` on the existing startup if it was missing
5. If no match: proceed to `add_startup`

---

## Admin UI Changes

### Existing EDGAR page (`admin/app/edgar/page.tsx`):

**Control bar additions:**
- "Discover New" button (alongside existing "Run EDGAR Scan" / "Scan New Only")
- Days input field next to "Discover New" (default 365)

**Progress summary additions** (when running a discover job):
- Companies Discovered (new startups created)
- Duplicates Skipped
- Enrichments Queued / Completed

The existing Startups tab, Filings tab, and Activity Log already work generically off step data — they'll display discovery steps naturally. The log messages just need formatting for the new step types.

### API changes:

- `POST /api/admin/edgar/start` already accepts `scan_mode` — add `"discover"` as a new valid mode
- Add `discover_days` field to `EdgarStartRequest` (default 365)
- Job creation logic branches on `scan_mode`: if `"discover"`, generate `discover_filings` steps instead of `resolve_cik`/`fetch_filings` steps

---

## Worker Changes

### New step executors added to `edgar_worker.py`:

- `_execute_discover_filings` — calls EDGAR EFTS, filters results, generates `extract_company` steps
- `_execute_extract_company` — downloads Form D, parses XML, dedup check, generates `add_startup` steps
- `_execute_add_startup` — creates Startup + FundingRound records, generates `enrich_startup` steps
- `_execute_enrich_startup` — runs Perplexity enrichment pipeline

### Worker preferences for discover mode:

- Workers 0-1: prefer `discover_filings` and `extract_company`
- Workers 2-3: prefer `enrich_startup`

### Step chaining:

```
discover_filings → extract_company (×N per qualifying filing)
                       ��� add_startup (if new)
                            → enrich_startup
```

---

## Model Changes

### EdgarStepType enum — add 4 new values:

- `discover_filings`
- `extract_company`
- `add_startup`
- `enrich_startup`

### EdgarStartRequest — add field:

- `discover_days: int = 365`

### No new tables or columns needed — the existing EdgarJob/EdgarJobStep models handle everything.

---

## Database Migration

Add new enum values to the `edgar_job_steps.step_type` column. Since we store step_type as `String(20)`, no migration needed — the new values just work. Same for `scan_mode` on `edgar_jobs` (stored as `Text`).

The only migration needed is if any of the new step type names exceed 20 characters. Checking: `discover_filings` (17), `extract_company` (15), `add_startup` (11), `enrich_startup` (15). All fit.

No migration required.
