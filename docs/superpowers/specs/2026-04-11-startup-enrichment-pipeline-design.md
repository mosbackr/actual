# Startup Enrichment Pipeline — Design Spec

## Goal

When a startup is approved from triage (or manually triggered), automatically enrich it with comprehensive data from the web and generate an AI investment memo with per-dimension scoring. The result is a fully populated startup detail page with founders, funding history, social links, company intel, and a structured AI review — ready for expert and community evaluation.

## Architecture

Two-stage pipeline using Perplexity Sonar Pro for both web research and AI analysis. Runs as a fire-and-forget background task in FastAPI. Tracked via `enrichment_status` on the startup record. Triggered automatically on triage approval, or manually via a button on any startup's admin detail page.

**Tech:** Perplexity Sonar Pro API (single integration), FastAPI background tasks, PostgreSQL, Alembic migrations.

---

## 1. Deduplication

Dedup at three layers to ensure no startup appears twice on the platform.

### 1.1 Scout Chat Results

When Perplexity returns startup candidates in `/api/admin/scout/chat`, the backend checks each candidate's **name** (normalized: lowercase, strip "Inc", "Ltd", "Co.", etc.) and **website domain** (normalized: strip protocol, www, trailing slash) against all existing startups in the DB.

Matches are returned with `already_on_platform: true` and their current `status` (pending/approved/rejected/featured). The admin frontend renders these grayed out with an "Already in pipeline" label. They are not selectable for adding to triage.

### 1.2 Scout Add Endpoint

`POST /api/admin/scout/add` already does name-based dedup. Extend to also match on normalized website domain. If either name or domain matches an existing startup, skip it. Return which were skipped and why in the response.

### 1.3 Manual Create Form

On the admin "New Startup" form, after the admin enters a name or website URL, do a live check against existing startups. Show a warning with a link to the existing startup if a match is found. This is a frontend-only UX enhancement — the backend dedup in the create endpoint is the real guard.

### Normalization Logic

```
normalize_name(name):
  lowercase
  strip: "inc", "inc.", "ltd", "ltd.", "co", "co.", "llc", "corp", "corporation"
  strip leading/trailing whitespace and punctuation
  collapse multiple spaces

normalize_domain(url):
  parse URL, extract hostname
  strip "www." prefix
  strip trailing slash
  lowercase
```

Match on `normalize_name(a) == normalize_name(b)` OR `normalize_domain(a) == normalize_domain(b)`. Either match = duplicate.

---

## 2. Data Model Changes

### 2.1 New Fields on `Startup` Model

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tagline` | String(500) | null | One-liner for cards |
| `total_funding` | String(100) | null | e.g., "$25M" |
| `employee_count` | String(50) | null | e.g., "50-100" |
| `linkedin_url` | String(500) | null | Company LinkedIn page |
| `twitter_url` | String(500) | null | Twitter/X profile |
| `crunchbase_url` | String(500) | null | Crunchbase profile |
| `competitors` | Text | null | Competitor landscape |
| `tech_stack` | Text | null | Technologies used |
| `hiring_signals` | Text | null | Hiring activity, open roles, Glassdoor |
| `patents` | Text | null | Patent filings |
| `key_metrics` | Text | null | Public ARR, users, growth |
| `enrichment_status` | Enum | `none` | `none`, `running`, `complete`, `failed` |
| `enrichment_error` | Text | null | Error message if failed |
| `enriched_at` | DateTime | null | When enrichment last ran |

### 2.2 New Table: `startup_founders`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `startup_id` | UUID | FK → startups, cascade delete |
| `name` | String(200) | NOT NULL |
| `title` | String(200) | nullable (e.g., "CEO & Co-founder") |
| `linkedin_url` | String(500) | nullable |
| `sort_order` | Integer | default 0 |

### 2.3 New Table: `startup_funding_rounds`

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `startup_id` | UUID | FK → startups, cascade delete |
| `round_name` | String(100) | NOT NULL (e.g., "Seed", "Series A") |
| `amount` | String(50) | nullable (e.g., "$5M") |
| `date` | String(20) | nullable (e.g., "2024-03" or "2024") |
| `lead_investor` | String(200) | nullable |
| `sort_order` | Integer | default 0 |

### 2.4 New Table: `startup_ai_reviews`

One AI review per startup. Overwritten on re-run.

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `startup_id` | UUID | FK → startups, unique, cascade delete |
| `overall_score` | Float | NOT NULL, 0-100 |
| `investment_thesis` | Text | NOT NULL — bull case paragraph |
| `key_risks` | Text | NOT NULL — risk paragraph |
| `verdict` | Text | NOT NULL — recommendation |
| `dimension_scores` | JSONB | NOT NULL — `[{dimension_name, score, reasoning}]` |
| `created_at` | DateTime | NOT NULL |

### 2.5 Enrichment Status Enum

```python
class EnrichmentStatus(str, Enum):
    none = "none"
    running = "running"
    complete = "complete"
    failed = "failed"
```

---

## 3. Enrichment Pipeline

Runs as a FastAPI `BackgroundTask`. Two Perplexity API calls.

### 3.1 Trigger

- **Automatic:** When `PUT /api/admin/startups/{id}` changes `status` to `approved`, fire the pipeline as a background task.
- **Manual:** `POST /api/admin/startups/{id}/enrich` fires the pipeline. Available on any startup regardless of status.

### 3.2 Step 1 — Set Status

```python
startup.enrichment_status = EnrichmentStatus.running
startup.enrichment_error = None
await db.commit()
```

### 3.3 Step 2 — Perplexity Enrichment Call

Call Perplexity Sonar Pro with a system prompt instructing comprehensive web research. Pass the startup's name, website URL, description, and any existing data as context.

**System prompt instructs Perplexity to return a JSON block with:**
- `tagline`: one-liner
- `description`: improved 2-3 sentence description
- `founded_date`: ISO date or year string
- `founders`: `[{name, title, linkedin_url}]`
- `funding_rounds`: `[{round_name, amount, date, lead_investor}]`
- `total_funding`: string
- `employee_count`: string
- `linkedin_url`, `twitter_url`, `crunchbase_url`: strings
- `competitors`: paragraph
- `tech_stack`: paragraph
- `key_metrics`: paragraph
- `hiring_signals`: paragraph
- `patents`: paragraph
- `media`: `[{title, url, source, media_type, published_at}]`

**Parse response.** Extract JSON block (same regex approach as scout). Update startup fields. Clear and re-insert `startup_founders`, `startup_funding_rounds`, `startup_media` rows (so re-runs get fresh data). Fetch logo via Logo.dev if `logo_url` is null and we have a website domain.

### 3.4 Step 3 — Perplexity Scoring Call

Load the startup's dimensions. If none exist, auto-apply a template: find the first industry on the startup, look for a template matching that industry name. If no industry match, apply a "Default" template (must exist as a seed).

Send enriched data + dimensions to Perplexity with a system prompt:

> You are a senior VC analyst at a top-tier fund. Evaluate this startup based on the research data provided. For each dimension, assign a score from 0-100 and write 2-3 sentences of specific, evidence-based reasoning. Then write an Investment Thesis (bull case for why this startup could succeed), Key Risks (what could go wrong), and a Verdict (your overall recommendation).

**Return JSON:**
```json
{
  "overall_score": 72,
  "investment_thesis": "...",
  "key_risks": "...",
  "verdict": "...",
  "dimension_scores": [
    {"dimension_name": "Market Opportunity", "score": 80, "reasoning": "..."},
    {"dimension_name": "Team Strength", "score": 75, "reasoning": "..."}
  ]
}
```

**Parse response.** Upsert into `startup_ai_reviews` (delete existing + insert, since it's unique per startup). Update `startup.ai_score` with the weighted overall score (using dimension weights from `StartupDimension`). Insert a new `StartupScoreHistory` record with `score_type=ai`, `score_value=overall`, `dimensions_json={dimension_name: score}`.

### 3.5 Step 4 — Finalize

```python
startup.enrichment_status = EnrichmentStatus.complete
startup.enriched_at = datetime.utcnow()
await db.commit()
```

### 3.6 Error Handling

Wrap entire pipeline in try/except. On failure:

```python
startup.enrichment_status = EnrichmentStatus.failed
startup.enrichment_error = str(error)[:500]
await db.commit()
```

Partial enrichment is fine — if the enrichment call succeeds but scoring fails, the enriched data is kept. Re-run always executes the full pipeline from scratch, overwriting all enriched data and scores with fresh results.

---

## 4. API Endpoints

### 4.1 New Endpoints

**`POST /api/admin/startups/{id}/enrich`**
- Auth: superadmin
- Fires the enrichment pipeline as a background task
- Returns `200 {status: "running"}` immediately
- If already running, returns `409 {detail: "Enrichment already in progress"}`

**`GET /api/admin/startups/{id}/enrichment-status`**
- Auth: superadmin
- Returns `{enrichment_status, enrichment_error, enriched_at}`
- Used for polling from the admin UI

**`GET /api/admin/startups/{id}/ai-review`**
- Auth: superadmin
- Returns the full AI review: `{overall_score, investment_thesis, key_risks, verdict, dimension_scores: [{dimension_name, score, reasoning}], created_at}`
- Returns `404` if no AI review exists

### 4.2 Modified Endpoints

**`PUT /api/admin/startups/{id}`** — When `status` changes to `approved`, fire the enrichment pipeline as a background task.

**`GET /api/admin/startups/pipeline`** — Include `enrichment_status` in each item.

**`GET /api/startups/{slug}` (public)** — Extend response to include:
- `tagline`, `total_funding`, `employee_count`
- `linkedin_url`, `twitter_url`, `crunchbase_url`
- `founders: [{name, title, linkedin_url}]`
- `funding_rounds: [{round_name, amount, date, lead_investor}]`
- `ai_review: {overall_score, investment_thesis, key_risks, verdict, dimension_scores, created_at}` (null if not yet scored)
- `competitors`, `tech_stack`, `key_metrics` (company intel)

**`POST /api/admin/scout/chat`** — Before returning results, check each candidate against DB. Tag matches with `already_on_platform: true` and `existing_status`.

**`POST /api/admin/scout/add`** — Extend dedup to match on normalized domain in addition to name.

---

## 5. Admin Frontend Changes

### 5.1 Startup Detail Page

**Header area:**
- Enrichment status badge: spinner + "Enriching..." (running), green "Enriched" (complete), red "Failed: {error}" (failed), nothing (none)
- "Run AI Enrichment" button (if status is `none` or `failed`) / "Re-run Enrichment" button (if status is `complete`)

**New sections below existing editor (only shown when enriched):**

- **Founders** — Cards: name, title, LinkedIn link icon
- **Funding Rounds** — Table: round, amount, date, lead investor
- **AI Investment Memo** — Boxed section:
  - Overall score (large, color-coded)
  - Investment Thesis paragraph
  - Dimension scores: list of dimension name + score bar + reasoning text
  - Key Risks paragraph
  - Verdict paragraph
  - "Generated on {date}" footer
- **Company Intel** — Grid: tagline, employee count, key metrics, competitors, tech stack, hiring signals, patents, social links
- **Media Coverage** — List of article cards (title, source, date, link)

### 5.2 Triage Page

No UI changes. Approve triggers enrichment silently in the background.

### 5.3 Scout Results

Startup cards matching existing DB entries:
- Grayed out styling, not selectable
- Badge: "Already in pipeline" or "Already approved"
- Show existing status

### 5.4 Create Startup Form

Live dedup check: after typing name or URL, hit a dedup endpoint or check client-side. Show warning + link to existing startup if match found.

---

## 6. Public Frontend Changes

### 6.1 Startup Detail Page

**Header enhancement:**
- Tagline below name
- Social links row (LinkedIn, Twitter, Crunchbase icons)
- Employee count, total funding badges

**New sections:**

- **AI Analysis** — The investment memo, displayed publicly:
  - Overall AI score (prominent)
  - Investment Thesis section
  - Dimension Breakdown: each dimension with score bar (0-100, color-coded) and reasoning paragraph
  - Key Risks section
  - Verdict section
  - Existing `DimensionRadar` component now has data from `dimensions_json`

- **Founders** — Card row: name, title, LinkedIn link

- **Funding History** — Timeline or table of rounds

- **Company Intel** — Key metrics, competitors, tech stack (collapsible or tabbed if dense)

- **Media Coverage** — Existing section, now populated with enriched articles

### 6.2 Startup Card (Listings)

- Tagline shown below description (single line, truncated)
- AI score already displays via existing `ScoreBadge` (now has a value)

---

## 7. Default Scoring Template

Seed a "Default" DD template used when a startup has no industry-matched template:

| Dimension | Weight |
|-----------|--------|
| Market Opportunity | 1.2 |
| Team Strength | 1.3 |
| Product & Technology | 1.1 |
| Traction & Metrics | 1.2 |
| Business Model | 1.0 |
| Competitive Moat | 1.0 |
| Financials & Unit Economics | 0.9 |
| Timing & Market Readiness | 0.8 |

Industry-specific templates can override this. Template selection logic: match first startup industry to a template by name. If no match, use "Default".

---

## 8. Scope Boundaries

**In scope:**
- Enrichment pipeline (two Perplexity calls)
- Data model changes + migration
- Admin detail page enrichment UI
- Public detail page AI review display
- Deduplication at Scout, add, and create layers
- Default scoring template seed
- Re-run capability
- Error handling and status tracking

**Out of scope (future work):**
- Expert review submission system (experts scoring dimensions)
- Community review system
- Scheduled re-enrichment (cron)
- Webhook/notification when enrichment completes
- Enrichment cost tracking/budgeting
- Bulk enrichment of existing startups
