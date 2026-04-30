# Investor Portfolio Management — Phase 1 Design Spec

## Goal

Let investors claim their profile on Deep Thesis and manage a portfolio of companies, creating a verified investor-startup graph that improves scoring accuracy and drives engagement beyond the initial marketing email.

## Architecture

Extend the existing `/score/[id]` page from a read-only report card into an interactive investor profile. Portfolio data lives in a new `portfolio_companies` table with an optional FK to `startups`. Investors link to their profile via a new `user_id` column on the `investors` table. No new pages — the score page grows a portfolio section that's read-only for visitors and editable for the owner.

## Data Model

### New table: `portfolio_companies`

| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK, default uuid4 |
| investor_id | uuid | FK → investors.id, NOT NULL |
| startup_id | uuid | FK → startups.id, nullable |
| company_name | string(300) | NOT NULL |
| company_website | string(500) | nullable |
| investment_date | date | nullable |
| round_stage | string(50) | nullable (seed, series_a, etc.) |
| check_size | string(100) | nullable (free text: "$150K") |
| is_lead | boolean | default false |
| board_seat | boolean | default false |
| status | string(20) | default "active" (active/exited/written_off) |
| exit_type | string(20) | nullable (acquisition/ipo) |
| exit_multiple | float | nullable |
| is_public | boolean | default true |
| created_at | datetime(tz) | server_default now() |
| updated_at | datetime(tz) | server_default now(), onupdate |

Unique constraint: `(investor_id, company_name)` — one entry per company per investor.

When `startup_id` is null, the company exists only as a portfolio record (not in the startups table). `company_name` and `company_website` are always stored so the portfolio entry is self-contained even without a linked startup.

### Modified table: `investors`

Add column:

| Column | Type | Constraints |
|--------|------|-------------|
| user_id | uuid | FK → users.id, nullable, unique |

This links a logged-in user to their investor profile. Set during the claim flow.

## API Endpoints

New file: `backend/app/api/investor_portfolio.py`

### Portfolio CRUD

All require authentication. Write operations require ownership (investor.user_id == current user).

**`GET /api/investors/{investor_id}/portfolio`**
- Public: returns only `is_public = true` entries
- Owner: returns all entries
- Response: array of portfolio company objects, each including startup slug/logo_url if startup_id is linked

**`POST /api/investors/{investor_id}/portfolio`**
- Owner only
- Body: `{ company_name, startup_id?, company_website?, investment_date?, round_stage?, check_size?, is_lead?, board_seat?, status?, is_public? }`
- If `startup_id` provided, validate it exists in startups table
- Returns created portfolio entry

**`PUT /api/investors/{investor_id}/portfolio/{id}`**
- Owner only
- Body: any subset of the create fields
- Returns updated portfolio entry

**`DELETE /api/investors/{investor_id}/portfolio/{id}`**
- Owner only
- Returns 204

### Profile Claiming

**`POST /api/investors/claim`**
- Requires authenticated user
- Matches `user.email` against `investor.email`
- If match found and `investor.user_id` is null, sets `investor.user_id = user.id` and sets `user.role = investor`
- Returns the investor record
- If no match: 404
- If already claimed: 409

### Suggested Portfolio

**`GET /api/investors/{investor_id}/suggested-portfolio`**
- Owner only
- Reads `investor.recent_investments` (JSON array of company name strings)
- Fuzzy-matches each against `startups.name` using ILIKE
- Returns array: `{ company_name, matched_startup: { id, slug, name, logo_url, stage } | null }`
- Used during claim flow to pre-populate portfolio

### Existing Endpoint Reuse

Startup search (`GET /api/startups?q=...`) already exists and supports text search. The frontend type-ahead reuses this endpoint directly — no new search API needed.

## Frontend

### Score Page (`/score/[id]`) — Extended

The page keeps its existing structure (score, dimensions, narrative) and adds sections below.

#### Claim Banner

Shown when:
- User is logged in
- User's email matches an investor record
- That investor record has `user_id = null`

Display: A banner at the top of the page: "Is this you? Claim your profile to manage your portfolio." with a "Claim Profile" button.

On click: calls `POST /api/investors/claim`. On success, shows the suggested portfolio flow.

#### Suggested Portfolio Flow

Shown immediately after a successful claim:

- Fetches `GET /api/investors/{id}/suggested-portfolio`
- Displays a list of company names from `recent_investments` with checkboxes, pre-checked
- For companies that fuzzy-matched a startup, shows the startup's logo and name
- "Confirm Portfolio" button → bulk-creates portfolio entries for checked items via `POST /api/investors/{id}/portfolio`
- Skipped items are simply not added

#### Portfolio Section (Visitor View)

Below the narrative section. Only shown if the investor has public portfolio entries.

- Section header: "Portfolio"
- Grid of cards (same `grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6` as startups page)
- Each card:
  - Company logo (from linked startup) or first-letter fallback
  - Company name (linked to `/startups/[slug]` if startup_id exists)
  - Round stage badge (e.g., "Seed")
  - Status badge: Active (green border), Exited (gold border), Written Off (red border)
- If no public entries: section is hidden entirely

#### Portfolio Section (Owner View)

Same grid but with additional controls:

- Portfolio summary bar above grid: "8 companies · 2 exits · Seed focus"
- "Add Company" button (accent-colored, top-right of section header)
- Each card includes a "..." dropdown menu: Edit, Remove, Toggle Public/Private
- Private companies shown with reduced opacity and a lock indicator

#### Add Company Modal

Triggered by the "Add Company" button. A modal dialog with:

1. **Search input** at top — debounced type-ahead against `GET /api/startups?q=`
2. **Results dropdown** — shows matching startups: logo, name, stage, AI score
3. **Clicking a result** fills `company_name` and `startup_id`, collapses search
4. **"Company not listed?"** link — switches to manual entry mode with name and website text fields
5. **Detail form** (always visible below search/manual):
   - Round stage: dropdown (Pre-Seed, Seed, Series A, B, C, Growth)
   - Investment date: date picker
   - Check size: text input
   - Role: radio (Lead / Follow)
   - Board seat: toggle
6. **"Add to Portfolio"** submit button

### Startup Page (`/startups/[slug]`) — Add to Portfolio Button

For logged-in users with `role: investor` and a linked investor profile:

- "Add to Portfolio" button next to the existing "Watch" button
- Same visual style as WatchButton
- On click: opens a compact version of the add modal with company_name and startup_id pre-filled — only shows the detail form (round, date, check size, lead/follow, board)
- If company already in portfolio: button shows "In Portfolio" with a green check, disabled state

### Navbar

For users with `role: investor` and a linked investor profile, add a "Portfolio" link:

```
Companies  Analyze  Insights  Pitch Intel  Contribute    [Portfolio] [Score 74]
```

"Portfolio" links to `/score/{investor_id}#portfolio` and scrolls to the portfolio section. Same styling as other nav links: `text-sm text-text-secondary hover:text-text-primary`.

## Design System

All new UI follows the existing design language:

- Cards: `rounded border border-border bg-surface p-5`
- Headers: `font-serif text-xl text-text-primary`
- Body text: `text-sm text-text-secondary`
- Accent: `#F28C28` for CTAs, active states
- Status badges:
  - Active: `border-score-high/30 text-score-high`
  - Exited: `border-accent/30 text-accent`
  - Written Off: `border-score-low/30 text-score-low`
- Grid: `grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6`
- Modals: `rounded border border-border bg-surface` with overlay backdrop

## Out of Scope (Phase 2+)

- Portfolio analytics (stage distribution, sector concentration charts)
- Linking investor names in funding round tables to investor profiles
- "Known Investors" section on startup pages
- Co-investor discovery
- Batch enrichment of unlinked portfolio companies into startup records
- Portfolio benchmarking against peers
