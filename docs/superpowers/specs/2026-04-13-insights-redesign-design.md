# Insights Page Redesign — Design Spec

## Goal

Replace the current "Regional Insights" page (maps + regional score breakdowns) with an interactive exploration dashboard for external visitors. The page should make visitors feel they can discover interesting startups and understand the platform's deal flow. Dense but organized, with scrollable sections tied together by global filters.

## Key Decisions

- **Audience**: External investors/visitors evaluating the platform's deal flow
- **Feel**: Interactive exploration tool — "I can discover here"
- **Exploration axes**: Industry, stage, scores, and region are all equal-weight filters (no primary axis)
- **Data density**: Dense dashboard organized into clear scrollable sections
- **Maps removed**: Geography becomes a hierarchical filter (country → state), not a visualization
- **Charting library**: Recharts (React-native, already common in Next.js ecosystems, lightweight)

---

## Page Structure

### 1. Summary Strip (top of page, static)

Six key metrics displayed horizontally across the page:

| Metric | Source | Format |
|--------|--------|--------|
| Total Startups | `COUNT(startups) WHERE status IN ('approved','featured')` | Integer + "+N this month" subtitle |
| Avg AI Score | `AVG(ai_score) WHERE ai_score IS NOT NULL` | Float to 1 decimal, "out of 100" |
| Total Funding | Sum of parsed `total_funding` across startups | Formatted as "$X.XB" or "$XXM" |
| Industries | `COUNT(DISTINCT industries)` with startups | Integer, "verticals tracked" |
| Top Verdict | Most common `verdict` from `startup_ai_reviews` | Verdict label + count |
| Avg Stage | Mode of `stage` column | Stage label + "median: X" subtitle |

The summary strip reacts to active filters — when filters are applied, these numbers reflect the filtered subset, with a subtle indicator showing "filtered" state.

---

### 2. Sticky Filter Bar (below summary, `position: sticky`)

Stays visible as user scrolls. Controls all four sections below.

**Filters:**

| Filter | Type | Options |
|--------|------|---------|
| Region | Hierarchical dropdown | Level 1: countries (from `location_country`). Level 2: US states (from `location_state`, shown when "US" selected). Multi-select at each level. |
| Stage | Multi-select dropdown | Pre-Seed, Seed, Series A, Series B, Series C, Growth, Public |
| Industry | Multi-select dropdown | All industries from database, sorted alphabetically |
| AI Score | Range slider | 0–100, with min/max inputs |
| Date Added | Preset dropdown | All time, Last 30 days, Last 90 days, Last 6 months, Last year |

**Filter bar also shows:**
- "Clear all" link (right side)
- "Showing X of Y startups" count (right side)

**Behavior:**
- Changing any filter triggers a single API call with all filter params
- All sections update from the same response
- URL query params update to make filtered views shareable

---

### 3. Section 1: Score Landscape

Two-column layout (2:1 ratio).

**Left — Scatter Plot (AI Score vs Expert Score):**
- X-axis: AI Score (0–100)
- Y-axis: Expert Score (0–100)
- Each dot = one startup
- Dot color = industry (use a consistent color palette, max ~8 distinct colors, others grouped as "Other")
- Dot size = total funding (parsed to float, scaled logarithmically)
- Hover tooltip: startup name, scores, industry, stage, funding
- Click: navigates to startup profile page (`/startups/[slug]`)
- Only show startups that have both `ai_score` and `expert_score` (skip nulls)

**Right top — Score Distribution Histogram:**
- AI Score distribution, bucketed into 10 bins (0–10, 10–20, ..., 90–100)
- Vertical bars, labeled x-axis
- Shows the shape of the scoring curve

**Right bottom — AI Verdict Breakdown:**
- Horizontal bar chart showing count per verdict category
- Categories from `startup_ai_reviews.verdict`: Strong Invest, Invest, Lean Invest, Lean Pass, Pass, Strong Pass
- Color-coded: greens for invest categories, reds/browns for pass categories

---

### 4. Section 2: Funding Overview

Two-column layout (1:1 ratio).

**Left — Funding by Stage (Bar Chart):**
- X-axis: stages (Pre-Seed through Growth)
- Y-axis: dollar amount (default) or count (toggle)
- Toggle in top-right: "$ Amount" | "Count"
- Dollar amounts parsed from `total_funding` string field on startups (not individual rounds)
- Bars colored consistently

**Right — Recent Rounds (Table):**
- Table showing the most recent funding rounds from `startup_funding_rounds`
- Columns: Company (linked to profile), Amount, Stage (from parent startup), Date
- Sorted by date descending
- Show top 8 rows
- Company name links to `/startups/[slug]`
- Only show rounds that have an `amount` value

---

### 5. Section 3: Industry Comparison

Full-width section.

**Sortable horizontal bar table:**
- Each row = one industry
- Columns:
  - Industry name (clickable — applies as filter, scrolls to top)
  - Avg AI Score (horizontal bar + number overlay)
  - Startup count (right-aligned number)
  - Total funding (right-aligned, formatted)
- Default sort: by Avg AI Score descending
- Click any column header to sort by that column
- Only show industries that have at least 1 approved/featured startup

---

### 6. Section 4: Deal Flow

Two-column layout (1:1 ratio).

**Left — New Startups per Month (Bar Chart):**
- Last 12 months
- X-axis: month labels (e.g., "May '25", "Jun '25", ...)
- Y-axis: count of startups added (`created_at` bucketed by month)
- Gradient-filled bars
- Shows platform velocity/growth

**Right — Recently Added (Feed):**
- 8 most recently added startups (by `created_at`)
- Each card shows: name (linked), primary industry, stage badge, AI score
- Relative time ("2d ago", "1w ago")
- Names link to `/startups/[slug]`

---

## API Design

### Single Endpoint: `GET /api/insights`

Returns all data for the page in one call. Accepts filter query params.

**Query Parameters:**

| Param | Type | Example |
|-------|------|---------|
| `stage` | comma-separated | `seed,series_a` |
| `industry` | comma-separated slugs | `ai-ml,fintech` |
| `country` | comma-separated | `US,UK` |
| `state` | comma-separated | `CA,NY` (only meaningful when country includes US) |
| `score_min` | integer | `50` |
| `score_max` | integer | `100` |
| `date_range` | string | `30d`, `90d`, `6m`, `1y`, `all` |

**Response Shape:**

```json
{
  "summary": {
    "total_startups": 247,
    "filtered_startups": 247,
    "avg_ai_score": 68.4,
    "total_funding": "$2.1B",
    "total_funding_raw": 2100000000,
    "industry_count": 14,
    "top_verdict": {"verdict": "Invest", "count": 23},
    "avg_stage": "seed",
    "median_stage": "series_a",
    "new_this_month": 12
  },
  "scores": {
    "scatter": [
      {"id": "uuid", "slug": "novabio", "name": "NovaBio", "ai_score": 84, "expert_score": 72, "industry": "BioTech", "stage": "series_a", "total_funding_raw": 12000000}
    ],
    "histogram": [
      {"bucket": "0-10", "count": 3},
      {"bucket": "10-20", "count": 8}
    ],
    "verdicts": [
      {"verdict": "Strong Invest", "count": 5},
      {"verdict": "Invest", "count": 23}
    ]
  },
  "funding": {
    "by_stage": [
      {"stage": "pre_seed", "total_amount": 5000000, "count": 18}
    ],
    "recent_rounds": [
      {"startup_name": "NovaBio", "startup_slug": "novabio", "amount": "$12M", "stage": "series_a", "date": "2026-03", "round_name": "Series A"}
    ]
  },
  "industries": [
    {"name": "AI/ML", "slug": "ai-ml", "avg_ai_score": 82.1, "count": 42, "total_funding": 890000000}
  ],
  "deal_flow": {
    "monthly": [
      {"month": "2025-05", "count": 8},
      {"month": "2025-06", "count": 12}
    ],
    "recent": [
      {"name": "NovaBio", "slug": "novabio", "industry": "BioTech", "stage": "series_a", "ai_score": 84, "created_at": "2026-04-11T..."}
    ]
  },
  "filters": {
    "available_countries": ["US", "UK", "DE"],
    "available_states": ["CA", "NY", "TX"],
    "available_industries": [{"name": "AI/ML", "slug": "ai-ml"}]
  }
}
```

### Why One Endpoint

The filters apply globally across all sections. One request with all filter params is simpler than coordinating 5 separate requests that all need the same filters. The response is bounded — scatter plot is the largest array. If more than 300 startups match filters, return all of them (the scatter plot can handle it). Recharts handles up to ~1000 dots reasonably. If the platform grows beyond that, add server-side downsampling later.

---

## Frontend Architecture

### Page: `frontend/app/insights/page.tsx`

Replace the existing regional insights page entirely. This is a public page (no auth required).

### Components (new files):

| Component | File | Responsibility |
|-----------|------|----------------|
| `InsightsSummary` | `frontend/components/insights/InsightsSummary.tsx` | Summary strip with 6 metrics |
| `InsightsFilters` | `frontend/components/insights/InsightsFilters.tsx` | Sticky filter bar with all filter controls |
| `ScoreLandscape` | `frontend/components/insights/ScoreLandscape.tsx` | Scatter plot + histogram + verdicts |
| `FundingOverview` | `frontend/components/insights/FundingOverview.tsx` | Stage bars + recent rounds table |
| `IndustryComparison` | `frontend/components/insights/IndustryComparison.tsx` | Sortable industry table with bars |
| `DealFlow` | `frontend/components/insights/DealFlow.tsx` | Monthly chart + recent feed |
| `RegionFilter` | `frontend/components/insights/RegionFilter.tsx` | Hierarchical country → state dropdown |

### Charting

Use **Recharts** (`recharts` npm package):
- `ScatterChart` for the score landscape scatter plot
- `BarChart` for histograms, funding by stage, monthly additions
- `ResponsiveContainer` for auto-sizing
- Custom tooltips matching the site's design system

### State Management

- Filters managed in URL search params (shareable URLs)
- `useSearchParams` + `useRouter` for filter state
- Single `useSWR` or `useEffect` fetch triggered by filter changes
- Debounce filter changes (300ms) to avoid excessive API calls

---

## Files to Remove

- `frontend/components/WorldMap.tsx` — no longer used
- `frontend/components/USMap.tsx` — no longer used
- `react-simple-maps` dependency can be removed from package.json

The old `backend/app/api/insights.py` (`/api/insights/regional`) can be removed or kept alongside the new endpoint — it's not hurting anything. Recommend removing for cleanliness.

---

## Scope Boundaries

**In scope:**
- New insights API endpoint with filtering
- New frontend page with 4 sections
- Sticky filter bar with hierarchical region filter
- Recharts-based visualizations
- Shareable filter URLs
- Removing map components

**Out of scope:**
- Score history / temporal trends (future enhancement)
- Individual startup deep-dive from insights (just link to profile)
- Export / download functionality
- Admin-only insights (this is public-facing)
- Real-time updates / websockets
