# EDGAR SEC Filing Scraper — Design Spec

## Goal

Automated batch pipeline that scrapes SEC EDGAR for Form D, S-1, and 10-K filings, matches them to startups in our database, and extracts funding round data (amounts, valuations, share prices, investor counts) to supplement Perplexity-sourced data. Integrates into the admin panel as an on-demand batch process.

## Key Decisions

- **Trigger**: On-demand batch from admin panel (not part of enrichment pipeline)
- **Filing types**: Form D (XML, direct parse), S-1 (HTML, Claude parse), 10-K (HTML, Claude parse)
- **Matching**: CIK lookup + name match + Claude verification for uncertain matches
- **Merge strategy**: EDGAR wins for hard numbers (amount, valuation, date), Perplexity wins for context (investor names, round labels)
- **Data provenance**: Simple `data_source` field on `StartupFundingRound` — `perplexity`, `edgar`, or `manual`
- **CIK storage**: `sec_cik` column on `Startup` model, verified matches cached for future scans
- **LLM**: Claude API (not Perplexity) — EDGAR doesn't need web search, needs document parsing

---

## Architecture

### Three-layer system:

1. **EDGAR Client** (`backend/app/services/edgar.py`) — Talks to SEC EDGAR APIs. Searches for companies, fetches filings, downloads filing documents. Pure HTTP, no business logic.

2. **EDGAR Processor** (`backend/app/services/edgar_processor.py`) — Takes raw filings and extracts structured data. Uses Claude API for S-1/10-K parsing (unstructured HTML documents). Handles Form D XML directly (no LLM needed). Also handles company matching with Claude verification.

3. **EDGAR Batch Worker** (`backend/app/services/edgar_worker.py`) — Orchestrates the batch scan. Creates jobs/steps, claims work atomically, tracks progress. Follows the same pattern as the existing batch worker (concurrent workers, `SELECT FOR UPDATE SKIP LOCKED`, pause/resume).

### New model additions:
- `sec_cik` (String, nullable) and `edgar_last_scanned_at` (DateTime, nullable) columns on `Startup`
- `data_source` column on `StartupFundingRound` (enum: `perplexity`, `edgar`, `manual`)
- New `EdgarJob` and `EdgarJobStep` models (mirrors BatchJob/BatchJobStep pattern)

### Admin UI:
New "EDGAR" tab in admin panel with start/pause/resume, progress tracking, and activity log — same layout as the existing batch page.

---

## EDGAR Client — SEC API Integration

EDGAR has a free, unauthenticated REST API. Only requirement is a `User-Agent` header with company name and email (SEC policy).

### Three API endpoints:

1. **Company Search** — `https://efts.sec.gov/LATEST/search-index?q={company_name}&dateRange=custom&startdt=2000-01-01&enddt=2026-12-31` — Returns matching companies with their CIK numbers.

2. **Filing Index** — `https://data.sec.gov/submissions/CIK{cik_padded}.json` — Returns all filings for a CIK. Paginated. Contains filing type, date, accession number.

3. **Filing Document** — `https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}` — The actual filing. Form D is XML. S-1 and 10-K are HTML.

### Rate limiting:
SEC asks for max 10 requests/second. We'll set a 150ms delay between requests.

### Filing processing by type:

| Filing | Format | Parsing Method | Key Data |
|--------|--------|---------------|----------|
| Form D | XML | Direct parse, no LLM | Amount sold, investors count, min investment, date |
| S-1 | HTML | Claude API extraction | Full funding history, cap table, revenue, valuation |
| 10-K | HTML | Claude API extraction | Revenue, margins, growth, employee count |

Form D is the workhorse — structured XML, no Claude needed, cheap and fast. S-1 and 10-K are where Claude earns its keep parsing dense HTML into structured data.

---

## Company Matching & CIK Resolution

### Flow for each startup:

1. **Check `sec_cik`** — If already stored, skip to filing fetch. Fast path for previously matched startups.

2. **Search EDGAR by company name** — Use the company search API. Often returns multiple results (e.g., "Stripe" → "Stripe, Inc.", "Stripe Energy Corp", "Stripe International Inc").

3. **Candidate filtering** — Drop obvious non-matches by comparing:
   - State of incorporation vs our `location_state`
   - Filing dates vs our `founded_date`
   - SIC code (industry classifier) for rough sanity check

4. **Claude verification** — For remaining candidates (typically 1-3), send Claude a short prompt:
   ```
   Our startup: {name}, {description}, {website}, {location}
   SEC entity: {entity_name}, {state}, {SIC_code}, {recent_filings}
   Are these the same company? Answer YES or NO with one sentence of reasoning.
   ```
   Tiny prompt — fast and cheap. One call per candidate.

5. **Store CIK** — On verified match, write `sec_cik` to the startup. All future scans skip steps 2-4.

6. **No match** — If no candidates verify, mark `edgar_last_scanned_at` anyway so we don't re-scan every time. Can retry on next batch run (company may file later).

### Expected match rates:
~60-70% of US startups that have raised institutional capital will have Form D filings. International companies won't be on EDGAR — skip those (filter by `location_country = 'US'`).

---

## Data Extraction & Merge Logic

### Form D (XML) — direct parse, no LLM:

Extract: `total_amount_sold`, `total_amount_remaining`, `number_of_investors`, `min_investment_accepted`, `date_of_first_sale`, `federal_exemptions_used`

Map to our model: `amount` = total_amount_sold, `date` = date_of_first_sale. Form D doesn't name the round (no "Series A" label) — infer from amount + date proximity to existing rounds.

### S-1 (HTML) — Claude extraction:

Send relevant sections (not the full 100+ pages) to Claude:
- "Use of Proceeds" section → current raise amount
- "Capitalization" section → share counts, valuations
- "Dilution" section → pre/post money
- "Principal Stockholders" section → investor names, ownership %
- "Description of Capital Stock" section → funding round history

Extract sections by HTML heading patterns first, then send ~10-20 pages to Claude instead of 200.

### 10-K (HTML) — Claude extraction:

Target sections:
- Revenue, cost of revenue, operating income
- Employee count
- Business description updates

### Merge logic (EDGAR wins for financials, Perplexity wins for context):

| Field | EDGAR overwrites? | Notes |
|-------|-------------------|-------|
| amount | Yes | SEC-reported, legally accurate |
| pre_money_valuation | Yes | Replaces `~` estimates |
| post_money_valuation | Yes | Replaces `~` estimates |
| date | Yes | Filing date is exact |
| lead_investor | No | Form D doesn't name investors |
| other_investors | No | Keep Perplexity data |
| round_name | No | Form D doesn't label rounds |

`data_source` set to `"edgar"` on any round touched by the scraper.

### Round matching:

When EDGAR gives us a filing, match to an existing round or create a new one. Match by: date within 90 days + amount within 20% tolerance. If no match, create a new round.

---

## Batch Job Flow & Worker Architecture

Follows the existing batch worker pattern exactly. Same concurrent workers, atomic claiming, pause/resume.

### Step types for EDGAR jobs:

1. `resolve_cik` — Search EDGAR + Claude verification for one startup. Stores CIK on match.
2. `fetch_filings` — Pull filing index for a CIK. Identify new Form D / S-1 / 10-K filings since last scan.
3. `process_filing` — Parse one filing (XML for Form D, Claude for S-1/10-K). Extract data, merge into funding rounds.

### Job creation flow:

- Admin clicks "Run EDGAR Scan"
- Creates `EdgarJob` with status `running`
- Generates `resolve_cik` steps for all startups that have `sec_cik IS NULL` and `location_country = 'US'`
- Generates `fetch_filings` steps for all startups that already have a `sec_cik`
- Launches 4 concurrent workers (lower than batch's 6 — SEC rate limit is the bottleneck)

### Step chaining (same parent→child pattern as batch worker):

- `resolve_cik` succeeds → generates `fetch_filings` step
- `fetch_filings` finds new filings → generates one `process_filing` step per filing

### Worker preferences:

- Workers 0-1: prefer `resolve_cik`
- Workers 2-3: prefer `process_filing`
- `fetch_filings` is fast (single HTTP call), any worker picks it up

### Rate limiting:

- SEC API calls: 150ms minimum between requests
- Claude API calls: no hard limit, but 500ms delay to be conservative
- Total throughput: ~5-6 startups/minute for CIK resolution, faster for filing processing

### Progress summary tracks:

- Startups scanned, CIKs resolved, filings found, filings processed
- Rounds created, rounds updated, valuations added

---

## Admin UI

New "EDGAR" tab in the admin panel — mirrors the batch page layout.

### Control bar:

- "Run EDGAR Scan" button (starts full scan)
- "Scan New Only" button (only startups with no `sec_cik` and no `edgar_last_scanned_at`)
- Pause / Resume / Cancel buttons
- Status badge + elapsed time

### Progress summary (6 cards):

- Startups Scanned
- CIKs Matched (with % match rate)
- Filings Found
- Filings Processed
- Rounds Updated
- Valuations Added

### Three tabs:

1. **Startups** — Table showing each startup's EDGAR status: name, CIK (or "No match"), filings found, last scanned, status badge
2. **Filings** — Table of processed filings: company name, filing type (Form D / S-1 / 10-K), date, data extracted (rounds updated, valuations found)
3. **Activity Log** — Same live log pattern as batch page

---

## Config

New environment variables:
- `ACUTAL_ANTHROPIC_API_KEY` — Claude API key for S-1/10-K parsing and company verification
- `EDGAR_USER_AGENT` — Required by SEC, format: "CompanyName admin@email.com"

---

## Database Migration

Add to `startups` table:
- `sec_cik VARCHAR(20) NULL`
- `edgar_last_scanned_at TIMESTAMP WITH TIME ZONE NULL`

Add to `startup_funding_rounds` table:
- `data_source VARCHAR(20) NOT NULL DEFAULT 'perplexity'` (enum: perplexity, edgar, manual)

New tables:
- `edgar_jobs` — mirrors `batch_jobs` structure (id, status, progress_summary, current_phase, error, timestamps)
- `edgar_job_steps` — mirrors `batch_job_steps` structure (id, job_id, step_type, status, params, result, error, sort_order, timestamps)
