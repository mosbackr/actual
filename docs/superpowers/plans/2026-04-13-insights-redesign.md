# Insights Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current Regional Insights page (maps + regional scores) with an interactive exploration dashboard featuring scatter plots, histograms, funding charts, industry comparisons, and deal flow visualizations — all controlled by a global sticky filter bar.

**Architecture:** Single backend endpoint (`GET /api/insights`) returns all dashboard data in one response, filtered by query params. Frontend is a `"use client"` page composed of 7 new components, each rendering a section of the dashboard. Filter state lives in URL search params for shareability. Recharts (already installed) handles all charting.

**Tech Stack:** FastAPI (Python), SQLAlchemy async, Next.js 16 (React 19), Recharts 3.8, Tailwind CSS 4

---

## File Structure

### Files to Create

| File | Responsibility |
|------|---------------|
| `frontend/lib/insights-types.ts` | TypeScript types for the insights API response |
| `frontend/components/insights/InsightsSummary.tsx` | Summary strip with 6 key metrics |
| `frontend/components/insights/InsightsFilters.tsx` | Sticky filter bar with all filter controls |
| `frontend/components/insights/RegionFilter.tsx` | Hierarchical country → state dropdown |
| `frontend/components/insights/ScoreLandscape.tsx` | Scatter plot + histogram + verdicts section |
| `frontend/components/insights/FundingOverview.tsx` | Funding by stage bars + recent rounds table |
| `frontend/components/insights/IndustryComparison.tsx` | Sortable industry bar table |
| `frontend/components/insights/DealFlow.tsx` | Monthly additions chart + recent feed |

### Files to Modify

| File | Changes |
|------|---------|
| `backend/app/api/insights.py` | Replace `/api/insights/regional` with new `/api/insights` endpoint |
| `frontend/app/insights/page.tsx` | Replace entirely with new dashboard composing all 7 components |
| `frontend/lib/api.ts` | Replace `getRegionalInsights` with `getInsights` |
| `frontend/lib/types.ts` | Remove `RegionMetrics` and `RegionalInsights` types |

### Files to Remove

| File | Reason |
|------|--------|
| `frontend/components/WorldMap.tsx` | Maps replaced by hierarchical region filter |
| `frontend/components/USMap.tsx` | Maps replaced by hierarchical region filter |

### Dependencies to Remove

| Package | Reason |
|---------|--------|
| `react-simple-maps` | Only used by WorldMap/USMap, which are being removed |
| `@types/react-simple-maps` | Types for removed package |

---

### Task 1: Backend API Endpoint — `/api/insights`

**Files:**
- Modify: `backend/app/api/insights.py` (replace entirely)

- [ ] **Step 1: Write the new endpoint**

Replace the entire contents of `backend/app/api/insights.py` with:

```python
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.ai_review import StartupAIReview
from app.models.funding_round import StartupFundingRound
from app.models.industry import Industry
from app.models.startup import Startup, StartupStage, StartupStatus, startup_industries

router = APIRouter()

STAGE_ORDER = [
    StartupStage.pre_seed,
    StartupStage.seed,
    StartupStage.series_a,
    StartupStage.series_b,
    StartupStage.series_c,
    StartupStage.growth,
    StartupStage.public,
]

STAGE_LABELS = {
    "pre_seed": "Pre-Seed",
    "seed": "Seed",
    "series_a": "Series A",
    "series_b": "Series B",
    "series_c": "Series C",
    "growth": "Growth",
    "public": "Public",
}


def parse_funding_to_float(funding_str: str | None) -> float | None:
    """Parse strings like '$12M', '$1.5B', '$500K' to float."""
    if not funding_str:
        return None
    s = funding_str.strip().replace(",", "").replace("$", "")
    m = re.match(r"([\d.]+)\s*([KMBkmb])?", s)
    if not m:
        return None
    val = float(m.group(1))
    suffix = (m.group(2) or "").upper()
    if suffix == "K":
        val *= 1_000
    elif suffix == "M":
        val *= 1_000_000
    elif suffix == "B":
        val *= 1_000_000_000
    return val


def format_funding(amount: float) -> str:
    """Format a float to '$X.XB', '$XXM', or '$XXK'."""
    if amount >= 1_000_000_000:
        return f"${amount / 1_000_000_000:.1f}B"
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.0f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.0f}K"
    return f"${amount:.0f}"


@router.get("/api/insights")
async def get_insights(
    stage: List[str] = Query(default=[]),
    industry: List[str] = Query(default=[]),
    country: List[str] = Query(default=[]),
    state: List[str] = Query(default=[]),
    score_min: Optional[int] = Query(default=None),
    score_max: Optional[int] = Query(default=None),
    date_range: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Single endpoint returning all insights dashboard data."""
    approved = Startup.status.in_([StartupStatus.approved, StartupStatus.featured])

    # Build industry subquery filter
    industry_filter = None
    if industry:
        industry_filter = (
            select(startup_industries.c.startup_id)
            .join(Industry, startup_industries.c.industry_id == Industry.id)
            .where(Industry.slug.in_(industry))
            .distinct()
        )

    # Date filter
    date_cutoff = None
    if date_range:
        now = datetime.now(timezone.utc)
        mapping = {"30d": 30, "90d": 90, "6m": 180, "1y": 365}
        days = mapping.get(date_range)
        if days:
            date_cutoff = now - timedelta(days=days)

    def apply_filters(q):
        q = q.where(approved)
        if stage:
            q = q.where(Startup.stage.in_(stage))
        if industry_filter is not None:
            q = q.where(Startup.id.in_(industry_filter))
        if country:
            if state:
                # Country OR state match
                q = q.where(
                    (Startup.location_country.in_(country))
                    | (Startup.location_state.in_(state))
                )
            else:
                q = q.where(Startup.location_country.in_(country))
        elif state:
            q = q.where(Startup.location_state.in_(state))
        if score_min is not None:
            q = q.where(Startup.ai_score >= score_min)
        if score_max is not None:
            q = q.where(Startup.ai_score <= score_max)
        if date_cutoff:
            q = q.where(Startup.created_at >= date_cutoff)
        return q

    # ── Total counts (unfiltered for "X of Y") ──
    total_q = select(func.count(Startup.id)).where(approved)
    total_startups = (await db.execute(total_q)).scalar() or 0

    # ── Filtered startups: fetch all matching rows ──
    startup_q = apply_filters(
        select(
            Startup.id,
            Startup.name,
            Startup.slug,
            Startup.ai_score,
            Startup.expert_score,
            Startup.stage,
            Startup.total_funding,
            Startup.location_country,
            Startup.location_state,
            Startup.created_at,
        )
    )
    startup_rows = (await db.execute(startup_q)).all()
    startup_ids = [r.id for r in startup_rows]
    filtered_count = len(startup_rows)

    # ── Summary metrics ──
    ai_scores = [r.ai_score for r in startup_rows if r.ai_score is not None]
    avg_ai = round(sum(ai_scores) / len(ai_scores), 1) if ai_scores else None

    funding_values = []
    for r in startup_rows:
        val = parse_funding_to_float(r.total_funding)
        if val:
            funding_values.append(val)
    total_funding_raw = sum(funding_values)
    total_funding_str = format_funding(total_funding_raw) if total_funding_raw > 0 else "$0"

    # Industry count
    if startup_ids:
        ind_count_q = (
            select(func.count(func.distinct(startup_industries.c.industry_id)))
            .where(startup_industries.c.startup_id.in_(startup_ids))
        )
        industry_count = (await db.execute(ind_count_q)).scalar() or 0
    else:
        industry_count = 0

    # Top verdict
    top_verdict = {"verdict": None, "count": 0}
    if startup_ids:
        verdict_q = (
            select(StartupAIReview.verdict, func.count(StartupAIReview.id).label("cnt"))
            .where(StartupAIReview.startup_id.in_(startup_ids))
            .group_by(StartupAIReview.verdict)
            .order_by(func.count(StartupAIReview.id).desc())
            .limit(1)
        )
        verdict_row = (await db.execute(verdict_q)).first()
        if verdict_row:
            top_verdict = {"verdict": verdict_row.verdict, "count": verdict_row.cnt}

    # Avg/mode stage
    stage_counts: dict[str, int] = {}
    for r in startup_rows:
        s = r.stage.value if hasattr(r.stage, "value") else str(r.stage)
        stage_counts[s] = stage_counts.get(s, 0) + 1
    mode_stage = max(stage_counts, key=stage_counts.get) if stage_counts else None

    # New this month
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    new_this_month = sum(1 for r in startup_rows if r.created_at and r.created_at >= month_start)

    summary = {
        "total_startups": total_startups,
        "filtered_startups": filtered_count,
        "avg_ai_score": avg_ai,
        "total_funding": total_funding_str,
        "total_funding_raw": total_funding_raw,
        "industry_count": industry_count,
        "top_verdict": top_verdict,
        "avg_stage": mode_stage,
        "median_stage": mode_stage,
        "new_this_month": new_this_month,
    }

    # ── Scores section ──
    # Scatter data: startups with both ai_score and expert_score
    # Need industry names for scatter dots
    scatter_ids = [r.id for r in startup_rows if r.ai_score is not None and r.expert_score is not None]
    scatter = []
    if scatter_ids:
        # Get primary industry per startup
        industry_q = (
            select(
                startup_industries.c.startup_id,
                Industry.name,
            )
            .join(Industry, startup_industries.c.industry_id == Industry.id)
            .where(startup_industries.c.startup_id.in_(scatter_ids))
        )
        ind_rows = (await db.execute(industry_q)).all()
        # First industry per startup
        startup_industry: dict[str, str] = {}
        for ir in ind_rows:
            sid = str(ir.startup_id)
            if sid not in startup_industry:
                startup_industry[sid] = ir.name

        for r in startup_rows:
            if r.ai_score is not None and r.expert_score is not None:
                scatter.append({
                    "id": str(r.id),
                    "slug": r.slug,
                    "name": r.name,
                    "ai_score": round(r.ai_score, 1),
                    "expert_score": round(r.expert_score, 1),
                    "industry": startup_industry.get(str(r.id), "Other"),
                    "stage": r.stage.value if hasattr(r.stage, "value") else str(r.stage),
                    "total_funding_raw": parse_funding_to_float(r.total_funding) or 0,
                })

    # Histogram: AI score buckets
    histogram = []
    buckets = [(i * 10, (i + 1) * 10) for i in range(10)]
    for low, high in buckets:
        count = sum(1 for r in startup_rows if r.ai_score is not None and low <= r.ai_score < high)
        histogram.append({"bucket": f"{low}-{high}", "count": count})

    # Verdicts
    verdicts = []
    if startup_ids:
        verdict_all_q = (
            select(StartupAIReview.verdict, func.count(StartupAIReview.id).label("cnt"))
            .where(StartupAIReview.startup_id.in_(startup_ids))
            .group_by(StartupAIReview.verdict)
            .order_by(func.count(StartupAIReview.id).desc())
        )
        for row in (await db.execute(verdict_all_q)).all():
            verdicts.append({"verdict": row.verdict, "count": row.cnt})

    scores = {"scatter": scatter, "histogram": histogram, "verdicts": verdicts}

    # ── Funding section ──
    # By stage
    by_stage = []
    for s in STAGE_ORDER:
        stage_val = s.value
        matching = [r for r in startup_rows if (r.stage.value if hasattr(r.stage, "value") else str(r.stage)) == stage_val]
        stage_funding = sum(parse_funding_to_float(r.total_funding) or 0 for r in matching)
        by_stage.append({
            "stage": stage_val,
            "label": STAGE_LABELS.get(stage_val, stage_val),
            "total_amount": stage_funding,
            "count": len(matching),
        })

    # Recent rounds
    recent_rounds = []
    if startup_ids:
        rounds_q = (
            select(
                StartupFundingRound.amount,
                StartupFundingRound.round_name,
                StartupFundingRound.date,
                Startup.name.label("startup_name"),
                Startup.slug.label("startup_slug"),
                Startup.stage.label("startup_stage"),
            )
            .join(Startup, StartupFundingRound.startup_id == Startup.id)
            .where(StartupFundingRound.startup_id.in_(startup_ids))
            .where(StartupFundingRound.amount.isnot(None))
            .where(StartupFundingRound.amount != "")
            .order_by(StartupFundingRound.date.desc().nulls_last())
            .limit(8)
        )
        for row in (await db.execute(rounds_q)).all():
            recent_rounds.append({
                "startup_name": row.startup_name,
                "startup_slug": row.startup_slug,
                "amount": row.amount,
                "stage": row.startup_stage.value if hasattr(row.startup_stage, "value") else str(row.startup_stage),
                "date": row.date,
                "round_name": row.round_name,
            })

    funding = {"by_stage": by_stage, "recent_rounds": recent_rounds}

    # ── Industries section ──
    industries_data = []
    if startup_ids:
        ind_agg_q = (
            select(
                Industry.name,
                Industry.slug,
                func.avg(Startup.ai_score).label("avg_ai"),
                func.count(Startup.id).label("cnt"),
            )
            .join(startup_industries, startup_industries.c.industry_id == Industry.id)
            .join(Startup, startup_industries.c.startup_id == Startup.id)
            .where(Startup.id.in_(startup_ids))
            .group_by(Industry.name, Industry.slug)
            .order_by(func.avg(Startup.ai_score).desc().nulls_last())
        )
        for row in (await db.execute(ind_agg_q)).all():
            # Calculate total funding for this industry
            ind_startup_q = (
                select(Startup.total_funding)
                .join(startup_industries, startup_industries.c.startup_id == Startup.id)
                .join(Industry, startup_industries.c.industry_id == Industry.id)
                .where(Industry.slug == row.slug)
                .where(Startup.id.in_(startup_ids))
            )
            ind_funding = 0.0
            for fr in (await db.execute(ind_startup_q)).all():
                val = parse_funding_to_float(fr.total_funding)
                if val:
                    ind_funding += val

            industries_data.append({
                "name": row.name,
                "slug": row.slug,
                "avg_ai_score": round(float(row.avg_ai), 1) if row.avg_ai else None,
                "count": row.cnt,
                "total_funding": ind_funding,
            })

    # ── Deal flow section ──
    # Monthly additions (last 12 months)
    monthly = []
    for i in range(11, -1, -1):
        d = now - timedelta(days=i * 30)
        month_label = d.strftime("%Y-%m")
        m_start = d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if d.month == 12:
            m_end = m_start.replace(year=m_start.year + 1, month=1)
        else:
            m_end = m_start.replace(month=m_start.month + 1)
        count = sum(1 for r in startup_rows if r.created_at and m_start <= r.created_at < m_end)
        monthly.append({"month": m_start.strftime("%Y-%m"), "count": count})

    # Deduplicate months (the 30-day approximation can cause dupes)
    seen_months: dict[str, dict] = {}
    for m in monthly:
        if m["month"] not in seen_months:
            seen_months[m["month"]] = m
        else:
            seen_months[m["month"]]["count"] += m["count"]
    monthly = list(seen_months.values())

    # Recent startups
    recent = []
    sorted_by_created = sorted(
        [r for r in startup_rows if r.created_at],
        key=lambda r: r.created_at,
        reverse=True,
    )[:8]
    # Get industries for recent
    recent_ids = [r.id for r in sorted_by_created]
    recent_industry: dict[str, str] = {}
    if recent_ids:
        ri_q = (
            select(startup_industries.c.startup_id, Industry.name)
            .join(Industry, startup_industries.c.industry_id == Industry.id)
            .where(startup_industries.c.startup_id.in_(recent_ids))
        )
        for ir in (await db.execute(ri_q)).all():
            sid = str(ir.startup_id)
            if sid not in recent_industry:
                recent_industry[sid] = ir.name

    for r in sorted_by_created:
        recent.append({
            "name": r.name,
            "slug": r.slug,
            "industry": recent_industry.get(str(r.id), "Other"),
            "stage": r.stage.value if hasattr(r.stage, "value") else str(r.stage),
            "ai_score": round(r.ai_score, 1) if r.ai_score is not None else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    deal_flow = {"monthly": monthly, "recent": recent}

    # ── Available filter options ──
    countries_q = (
        select(Startup.location_country)
        .where(approved)
        .where(Startup.location_country.isnot(None))
        .where(Startup.location_country != "")
        .distinct()
        .order_by(Startup.location_country)
    )
    available_countries = [r[0] for r in (await db.execute(countries_q)).all()]

    states_q = (
        select(Startup.location_state)
        .where(approved)
        .where(Startup.location_country == "US")
        .where(Startup.location_state.isnot(None))
        .where(Startup.location_state != "")
        .distinct()
        .order_by(Startup.location_state)
    )
    available_states = [r[0] for r in (await db.execute(states_q)).all()]

    all_industries_q = (
        select(Industry.name, Industry.slug)
        .join(startup_industries, startup_industries.c.industry_id == Industry.id)
        .join(Startup, startup_industries.c.startup_id == Startup.id)
        .where(approved)
        .distinct()
        .order_by(Industry.name)
    )
    available_industries = [
        {"name": r.name, "slug": r.slug}
        for r in (await db.execute(all_industries_q)).all()
    ]

    filters = {
        "available_countries": available_countries,
        "available_states": available_states,
        "available_industries": available_industries,
    }

    return {
        "summary": summary,
        "scores": scores,
        "funding": funding,
        "industries": industries_data,
        "deal_flow": deal_flow,
        "filters": filters,
    }
```

- [ ] **Step 2: Verify syntax**

Run: `cd /Users/leemosbacker/acutal && python3 -m py_compile backend/app/api/insights.py`
Expected: No output (clean compile)

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/insights.py
git commit -m "feat(insights): replace regional endpoint with full dashboard API"
```

---

### Task 2: Frontend Types + API Client

**Files:**
- Create: `frontend/lib/insights-types.ts`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/lib/types.ts`

- [ ] **Step 1: Create insights types file**

Create `frontend/lib/insights-types.ts`:

```typescript
export interface InsightsSummary {
  total_startups: number;
  filtered_startups: number;
  avg_ai_score: number | null;
  total_funding: string;
  total_funding_raw: number;
  industry_count: number;
  top_verdict: { verdict: string | null; count: number };
  avg_stage: string | null;
  median_stage: string | null;
  new_this_month: number;
}

export interface ScatterPoint {
  id: string;
  slug: string;
  name: string;
  ai_score: number;
  expert_score: number;
  industry: string;
  stage: string;
  total_funding_raw: number;
}

export interface HistogramBucket {
  bucket: string;
  count: number;
}

export interface VerdictCount {
  verdict: string;
  count: number;
}

export interface ScoresData {
  scatter: ScatterPoint[];
  histogram: HistogramBucket[];
  verdicts: VerdictCount[];
}

export interface StageFunding {
  stage: string;
  label: string;
  total_amount: number;
  count: number;
}

export interface RecentRound {
  startup_name: string;
  startup_slug: string;
  amount: string;
  stage: string;
  date: string | null;
  round_name: string;
}

export interface FundingData {
  by_stage: StageFunding[];
  recent_rounds: RecentRound[];
}

export interface IndustryRow {
  name: string;
  slug: string;
  avg_ai_score: number | null;
  count: number;
  total_funding: number;
}

export interface MonthlyCount {
  month: string;
  count: number;
}

export interface RecentStartup {
  name: string;
  slug: string;
  industry: string;
  stage: string;
  ai_score: number | null;
  created_at: string | null;
}

export interface DealFlowData {
  monthly: MonthlyCount[];
  recent: RecentStartup[];
}

export interface FilterOptions {
  available_countries: string[];
  available_states: string[];
  available_industries: { name: string; slug: string }[];
}

export interface InsightsResponse {
  summary: InsightsSummary;
  scores: ScoresData;
  funding: FundingData;
  industries: IndustryRow[];
  deal_flow: DealFlowData;
  filters: FilterOptions;
}
```

- [ ] **Step 2: Update API client**

In `frontend/lib/api.ts`, replace the `getRegionalInsights` method with:

```typescript
  getInsights: (params?: URLSearchParams) =>
    apiFetch<import("./insights-types").InsightsResponse>(
      `/api/insights${params ? `?${params}` : ""}`
    ),
```

- [ ] **Step 3: Remove old types from types.ts**

Remove `RegionMetrics` and `RegionalInsights` interfaces from `frontend/lib/types.ts`.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/insights-types.ts frontend/lib/api.ts frontend/lib/types.ts
git commit -m "feat(insights): add dashboard types and update API client"
```

---

### Task 3: InsightsSummary Component

**Files:**
- Create: `frontend/components/insights/InsightsSummary.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/components/insights/InsightsSummary.tsx`:

```tsx
import type { InsightsSummary as SummaryData } from "@/lib/insights-types";

const STAGE_LABELS: Record<string, string> = {
  pre_seed: "Pre-Seed",
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  series_c: "Series C",
  growth: "Growth",
  public: "Public",
};

interface Props {
  data: SummaryData;
  isFiltered: boolean;
}

export function InsightsSummary({ data, isFiltered }: Props) {
  const metrics = [
    {
      label: "Total Startups",
      value: data.filtered_startups.toLocaleString(),
      subtitle: isFiltered
        ? `of ${data.total_startups.toLocaleString()}`
        : `+${data.new_this_month} this month`,
    },
    {
      label: "Avg AI Score",
      value: data.avg_ai_score !== null ? data.avg_ai_score.toFixed(1) : "—",
      subtitle: "out of 100",
    },
    {
      label: "Total Funding",
      value: data.total_funding,
      subtitle: isFiltered ? "filtered" : null,
    },
    {
      label: "Industries",
      value: data.industry_count.toString(),
      subtitle: "verticals tracked",
    },
    {
      label: "Top Verdict",
      value: data.top_verdict.verdict || "—",
      subtitle: data.top_verdict.count > 0 ? `${data.top_verdict.count} startups` : null,
    },
    {
      label: "Avg Stage",
      value: data.avg_stage ? STAGE_LABELS[data.avg_stage] || data.avg_stage : "—",
      subtitle: data.median_stage ? `median: ${STAGE_LABELS[data.median_stage] || data.median_stage}` : null,
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      {metrics.map((m) => (
        <div
          key={m.label}
          className="rounded border border-border bg-surface p-4"
        >
          <p className="text-xs text-text-tertiary mb-1">{m.label}</p>
          <p className="font-serif text-2xl text-text-primary tabular-nums truncate">
            {m.value}
          </p>
          {m.subtitle && (
            <p className="text-xs text-text-tertiary mt-0.5">{m.subtitle}</p>
          )}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/insights/InsightsSummary.tsx
git commit -m "feat(insights): add InsightsSummary component"
```

---

### Task 4: RegionFilter + InsightsFilters Components

**Files:**
- Create: `frontend/components/insights/RegionFilter.tsx`
- Create: `frontend/components/insights/InsightsFilters.tsx`

- [ ] **Step 1: Create RegionFilter**

Create `frontend/components/insights/RegionFilter.tsx`:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";

const STATE_NAMES: Record<string, string> = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California",
  CO: "Colorado", CT: "Connecticut", DE: "Delaware", FL: "Florida", GA: "Georgia",
  HI: "Hawaii", ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa",
  KS: "Kansas", KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland",
  MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi",
  MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada",
  NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York",
  NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma",
  OR: "Oregon", PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina",
  SD: "South Dakota", TN: "Tennessee", TX: "Texas", UT: "Utah", VT: "Vermont",
  VA: "Virginia", WA: "Washington", WV: "West Virginia", WI: "Wisconsin",
  WY: "Wyoming", DC: "District of Columbia",
};

const COUNTRY_NAMES: Record<string, string> = {
  US: "United States", GB: "United Kingdom", CA: "Canada", DE: "Germany",
  FR: "France", AU: "Australia", IN: "India", IL: "Israel", SG: "Singapore",
  BR: "Brazil", JP: "Japan", KR: "South Korea", CN: "China", SE: "Sweden",
  NL: "Netherlands", CH: "Switzerland", IE: "Ireland", ES: "Spain",
  IT: "Italy", NO: "Norway", DK: "Denmark", FI: "Finland", NZ: "New Zealand",
  AE: "UAE", SA: "Saudi Arabia", MX: "Mexico", AR: "Argentina", CL: "Chile",
  CO: "Colombia", NG: "Nigeria", KE: "Kenya", ZA: "South Africa", EG: "Egypt",
  PL: "Poland", CZ: "Czechia", RO: "Romania", UA: "Ukraine", TR: "Turkey",
  TH: "Thailand", VN: "Vietnam", PH: "Philippines", ID: "Indonesia",
  MY: "Malaysia", BD: "Bangladesh", PK: "Pakistan",
};

interface Props {
  availableCountries: string[];
  availableStates: string[];
  selectedCountries: string[];
  selectedStates: string[];
  onCountriesChange: (countries: string[]) => void;
  onStatesChange: (states: string[]) => void;
}

export function RegionFilter({
  availableCountries,
  availableStates,
  selectedCountries,
  selectedStates,
  onCountriesChange,
  onStatesChange,
}: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const showStates = selectedCountries.includes("US");
  const totalSelected = selectedCountries.length + selectedStates.length;

  const toggleCountry = (code: string) => {
    if (selectedCountries.includes(code)) {
      onCountriesChange(selectedCountries.filter((c) => c !== code));
      if (code === "US") onStatesChange([]);
    } else {
      onCountriesChange([...selectedCountries, code]);
    }
  };

  const toggleState = (code: string) => {
    onStatesChange(
      selectedStates.includes(code)
        ? selectedStates.filter((s) => s !== code)
        : [...selectedStates, code]
    );
  };

  const displayText =
    totalSelected === 0
      ? "Region"
      : totalSelected <= 2
        ? [...selectedCountries.map((c) => COUNTRY_NAMES[c] || c), ...selectedStates.map((s) => STATE_NAMES[s] || s)].join(", ")
        : `${totalSelected} regions`;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-2 rounded border px-3 py-2 text-sm outline-none transition ${
          totalSelected > 0
            ? "border-accent bg-accent/5 text-accent"
            : "border-border bg-surface text-text-primary"
        }`}
      >
        <span className="max-w-[180px] truncate">{displayText}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 w-64 max-h-80 overflow-y-auto rounded border border-border bg-surface shadow-lg">
          {totalSelected > 0 && (
            <button
              onClick={() => { onCountriesChange([]); onStatesChange([]); }}
              className="w-full px-3 py-2 text-left text-xs text-accent hover:bg-hover-row transition border-b border-border"
            >
              Clear all
            </button>
          )}
          <div className="px-3 py-1.5 text-xs font-medium text-text-tertiary border-b border-border">
            Countries
          </div>
          {availableCountries.map((code) => (
            <label
              key={code}
              className="flex items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-hover-row cursor-pointer transition"
            >
              <input
                type="checkbox"
                checked={selectedCountries.includes(code)}
                onChange={() => toggleCountry(code)}
                className="accent-accent"
              />
              {COUNTRY_NAMES[code] || code}
            </label>
          ))}
          {showStates && availableStates.length > 0 && (
            <>
              <div className="px-3 py-1.5 text-xs font-medium text-text-tertiary border-t border-b border-border mt-1">
                US States
              </div>
              {availableStates.map((code) => (
                <label
                  key={code}
                  className="flex items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-hover-row cursor-pointer transition pl-5"
                >
                  <input
                    type="checkbox"
                    checked={selectedStates.includes(code)}
                    onChange={() => toggleState(code)}
                    className="accent-accent"
                  />
                  {STATE_NAMES[code] || code}
                </label>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create InsightsFilters**

Create `frontend/components/insights/InsightsFilters.tsx`:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { RegionFilter } from "./RegionFilter";
import type { FilterOptions } from "@/lib/insights-types";

const STAGE_OPTIONS = [
  { value: "pre_seed", label: "Pre-Seed" },
  { value: "seed", label: "Seed" },
  { value: "series_a", label: "Series A" },
  { value: "series_b", label: "Series B" },
  { value: "series_c", label: "Series C" },
  { value: "growth", label: "Growth" },
  { value: "public", label: "Public" },
];

const DATE_OPTIONS = [
  { value: "all", label: "All time" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
  { value: "6m", label: "Last 6 months" },
  { value: "1y", label: "Last year" },
];

/* ── Multi-select dropdown ── */
function MultiSelect({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onChange: (values: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const toggle = (val: string) => {
    onChange(
      selected.includes(val)
        ? selected.filter((v) => v !== val)
        : [...selected, val]
    );
  };

  const displayText =
    selected.length === 0
      ? label
      : selected.length <= 2
        ? options.filter((o) => selected.includes(o.value)).map((o) => o.label).join(", ")
        : `${selected.length} selected`;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-2 rounded border px-3 py-2 text-sm outline-none transition ${
          selected.length > 0
            ? "border-accent bg-accent/5 text-accent"
            : "border-border bg-surface text-text-primary"
        }`}
      >
        <span className="max-w-[180px] truncate">{displayText}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 w-56 max-h-64 overflow-y-auto rounded border border-border bg-surface shadow-lg">
          {selected.length > 0 && (
            <button
              onClick={() => onChange([])}
              className="w-full px-3 py-2 text-left text-xs text-accent hover:bg-hover-row transition border-b border-border"
            >
              Clear all
            </button>
          )}
          {options.map((opt) => (
            <label
              key={opt.value}
              className="flex items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-hover-row cursor-pointer transition"
            >
              <input
                type="checkbox"
                checked={selected.includes(opt.value)}
                onChange={() => toggle(opt.value)}
                className="accent-accent"
              />
              {opt.label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

export interface FilterState {
  stages: string[];
  industries: string[];
  countries: string[];
  states: string[];
  scoreMin: number;
  scoreMax: number;
  dateRange: string;
}

interface Props {
  filters: FilterState;
  filterOptions: FilterOptions;
  filteredCount: number;
  totalCount: number;
  onChange: (filters: FilterState) => void;
}

export function InsightsFilters({
  filters,
  filterOptions,
  filteredCount,
  totalCount,
  onChange,
}: Props) {
  const hasFilters =
    filters.stages.length > 0 ||
    filters.industries.length > 0 ||
    filters.countries.length > 0 ||
    filters.states.length > 0 ||
    filters.scoreMin > 0 ||
    filters.scoreMax < 100 ||
    filters.dateRange !== "all";

  const clearAll = () =>
    onChange({
      stages: [],
      industries: [],
      countries: [],
      states: [],
      scoreMin: 0,
      scoreMax: 100,
      dateRange: "all",
    });

  return (
    <div className="sticky top-0 z-40 bg-background border-b border-border py-3">
      <div className="flex flex-wrap items-center gap-3">
        <RegionFilter
          availableCountries={filterOptions.available_countries}
          availableStates={filterOptions.available_states}
          selectedCountries={filters.countries}
          selectedStates={filters.states}
          onCountriesChange={(countries) => onChange({ ...filters, countries })}
          onStatesChange={(states) => onChange({ ...filters, states })}
        />
        <MultiSelect
          label="Stage"
          options={STAGE_OPTIONS}
          selected={filters.stages}
          onChange={(stages) => onChange({ ...filters, stages })}
        />
        <MultiSelect
          label="Industry"
          options={filterOptions.available_industries.map((i) => ({
            value: i.slug,
            label: i.name,
          }))}
          selected={filters.industries}
          onChange={(industries) => onChange({ ...filters, industries })}
        />

        {/* AI Score range */}
        <div className="flex items-center gap-2 text-sm">
          <span className="text-text-tertiary text-xs">AI Score</span>
          <input
            type="number"
            min={0}
            max={100}
            value={filters.scoreMin}
            onChange={(e) =>
              onChange({ ...filters, scoreMin: Math.max(0, Math.min(100, Number(e.target.value))) })
            }
            className="w-14 rounded border border-border bg-surface px-2 py-1.5 text-sm text-text-primary tabular-nums"
          />
          <span className="text-text-tertiary">–</span>
          <input
            type="number"
            min={0}
            max={100}
            value={filters.scoreMax}
            onChange={(e) =>
              onChange({ ...filters, scoreMax: Math.max(0, Math.min(100, Number(e.target.value))) })
            }
            className="w-14 rounded border border-border bg-surface px-2 py-1.5 text-sm text-text-primary tabular-nums"
          />
        </div>

        {/* Date range */}
        <select
          value={filters.dateRange}
          onChange={(e) => onChange({ ...filters, dateRange: e.target.value })}
          className="rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary outline-none"
        >
          {DATE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        {/* Right side */}
        <div className="ml-auto flex items-center gap-4">
          {hasFilters && (
            <button
              onClick={clearAll}
              className="text-xs text-accent hover:text-accent-hover transition"
            >
              Clear all
            </button>
          )}
          <span className="text-xs text-text-tertiary tabular-nums">
            Showing {filteredCount.toLocaleString()} of {totalCount.toLocaleString()} startups
          </span>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/insights/RegionFilter.tsx frontend/components/insights/InsightsFilters.tsx
git commit -m "feat(insights): add RegionFilter and InsightsFilters components"
```

---

### Task 5: ScoreLandscape Component

**Files:**
- Create: `frontend/components/insights/ScoreLandscape.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/components/insights/ScoreLandscape.tsx`:

```tsx
"use client";

import { useRouter } from "next/navigation";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar,
} from "recharts";
import type { ScoresData } from "@/lib/insights-types";

const INDUSTRY_COLORS: Record<string, string> = {
  "AI/ML": "#B8553A",
  "FinTech": "#2D6A4F",
  "BioTech": "#7B2D8E",
  "HealthTech": "#1A6B8A",
  "SaaS": "#B8860B",
  "CleanTech": "#3A7D44",
  "EdTech": "#C2553A",
  "Cybersecurity": "#4A4A8A",
};

const VERDICT_COLORS: Record<string, string> = {
  "Strong Invest": "#1B7340",
  "Invest": "#2D6A4F",
  "Lean Invest": "#5A9E6F",
  "Lean Pass": "#C4883A",
  "Pass": "#B8553A",
  "Strong Pass": "#8B3A2A",
};

function getIndustryColor(industry: string): string {
  return INDUSTRY_COLORS[industry] || "#9B9B9B";
}

interface Props {
  data: ScoresData;
}

export function ScoreLandscape({ data }: Props) {
  const router = useRouter();

  return (
    <section>
      <h2 className="font-serif text-xl text-text-primary mb-4">Score Landscape</h2>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Scatter plot — 2 columns wide */}
        <div className="lg:col-span-2 rounded border border-border bg-surface p-4">
          <h3 className="text-sm font-medium text-text-primary mb-3">AI Score vs Expert Score</h3>
          <ResponsiveContainer width="100%" height={360}>
            <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E8E6E3" />
              <XAxis
                type="number"
                dataKey="ai_score"
                domain={[0, 100]}
                name="AI Score"
                stroke="#9B9B9B"
                fontSize={11}
                label={{ value: "AI Score", position: "bottom", offset: -5, fill: "#9B9B9B", fontSize: 11 }}
              />
              <YAxis
                type="number"
                dataKey="expert_score"
                domain={[0, 100]}
                name="Expert Score"
                stroke="#9B9B9B"
                fontSize={11}
                label={{ value: "Expert Score", angle: -90, position: "insideLeft", fill: "#9B9B9B", fontSize: 11 }}
              />
              <Tooltip
                content={({ payload }) => {
                  if (!payload || payload.length === 0) return null;
                  const d = payload[0].payload;
                  return (
                    <div className="rounded border border-border bg-surface px-3 py-2 shadow-lg text-xs">
                      <p className="font-medium text-text-primary">{d.name}</p>
                      <p className="text-text-secondary">AI: {d.ai_score} | Expert: {d.expert_score}</p>
                      <p className="text-text-tertiary">{d.industry} · {d.stage}</p>
                      {d.total_funding_raw > 0 && (
                        <p className="text-text-tertiary">
                          Funding: ${d.total_funding_raw >= 1e6 ? `${(d.total_funding_raw / 1e6).toFixed(1)}M` : `${(d.total_funding_raw / 1e3).toFixed(0)}K`}
                        </p>
                      )}
                    </div>
                  );
                }}
              />
              <Scatter
                data={data.scatter}
                onClick={(entry) => {
                  if (entry?.slug) router.push(`/startups/${entry.slug}`);
                }}
                cursor="pointer"
              >
                {data.scatter.map((entry, i) => (
                  <circle
                    key={i}
                    fill={getIndustryColor(entry.industry)}
                    fillOpacity={0.7}
                    r={Math.max(4, Math.min(16, Math.log10(entry.total_funding_raw + 1) * 2))}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
          {/* Industry legend */}
          <div className="flex flex-wrap gap-3 mt-3 px-2">
            {Object.entries(INDUSTRY_COLORS).map(([name, color]) => (
              <div key={name} className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: color }} />
                <span className="text-xs text-text-tertiary">{name}</span>
              </div>
            ))}
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded-full" style={{ backgroundColor: "#9B9B9B" }} />
              <span className="text-xs text-text-tertiary">Other</span>
            </div>
          </div>
        </div>

        {/* Right column */}
        <div className="flex flex-col gap-4">
          {/* Histogram */}
          <div className="rounded border border-border bg-surface p-4 flex-1">
            <h3 className="text-sm font-medium text-text-primary mb-3">AI Score Distribution</h3>
            <ResponsiveContainer width="100%" height={150}>
              <BarChart data={data.histogram} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                <XAxis dataKey="bucket" stroke="#9B9B9B" fontSize={9} interval={1} />
                <YAxis stroke="#9B9B9B" fontSize={9} width={30} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#FFFFFF",
                    border: "1px solid #E8E6E3",
                    borderRadius: "4px",
                    color: "#1A1A1A",
                    fontSize: "12px",
                  }}
                />
                <Bar dataKey="count" fill="#B8553A" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Verdict breakdown */}
          <div className="rounded border border-border bg-surface p-4 flex-1">
            <h3 className="text-sm font-medium text-text-primary mb-3">AI Verdict Breakdown</h3>
            <div className="space-y-2">
              {data.verdicts.map((v) => {
                const maxCount = Math.max(...data.verdicts.map((x) => x.count), 1);
                return (
                  <div key={v.verdict} className="flex items-center gap-2">
                    <span className="text-xs text-text-secondary w-24 truncate">{v.verdict}</span>
                    <div className="flex-1 h-5 bg-background rounded overflow-hidden">
                      <div
                        className="h-full rounded"
                        style={{
                          width: `${(v.count / maxCount) * 100}%`,
                          backgroundColor: VERDICT_COLORS[v.verdict] || "#9B9B9B",
                        }}
                      />
                    </div>
                    <span className="text-xs text-text-tertiary tabular-nums w-8 text-right">
                      {v.count}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/insights/ScoreLandscape.tsx
git commit -m "feat(insights): add ScoreLandscape component with scatter, histogram, verdicts"
```

---

### Task 6: FundingOverview Component

**Files:**
- Create: `frontend/components/insights/FundingOverview.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/components/insights/FundingOverview.tsx`:

```tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { FundingData } from "@/lib/insights-types";

function formatAmount(val: number): string {
  if (val >= 1_000_000_000) return `$${(val / 1_000_000_000).toFixed(1)}B`;
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(0)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(0)}K`;
  return `$${val}`;
}

const STAGE_LABELS: Record<string, string> = {
  pre_seed: "Pre-Seed",
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  series_c: "Series C",
  growth: "Growth",
  public: "Public",
};

interface Props {
  data: FundingData;
}

export function FundingOverview({ data }: Props) {
  const [mode, setMode] = useState<"amount" | "count">("amount");

  const chartData = data.by_stage.map((s) => ({
    name: s.label,
    value: mode === "amount" ? s.total_amount : s.count,
  }));

  return (
    <section>
      <h2 className="font-serif text-xl text-text-primary mb-4">Funding Overview</h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Left — bar chart */}
        <div className="rounded border border-border bg-surface p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-text-primary">Funding by Stage</h3>
            <div className="flex items-center gap-1 rounded border border-border bg-background p-0.5">
              <button
                onClick={() => setMode("amount")}
                className={`px-3 py-1 text-xs font-medium rounded transition ${
                  mode === "amount" ? "bg-accent text-white" : "text-text-tertiary hover:text-text-secondary"
                }`}
              >
                $ Amount
              </button>
              <button
                onClick={() => setMode("count")}
                className={`px-3 py-1 text-xs font-medium rounded transition ${
                  mode === "count" ? "bg-accent text-white" : "text-text-tertiary hover:text-text-secondary"
                }`}
              >
                Count
              </button>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData} margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E8E6E3" horizontal />
              <XAxis dataKey="name" stroke="#9B9B9B" fontSize={11} />
              <YAxis
                stroke="#9B9B9B"
                fontSize={11}
                tickFormatter={(v) => mode === "amount" ? formatAmount(v) : v}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#FFFFFF",
                  border: "1px solid #E8E6E3",
                  borderRadius: "4px",
                  color: "#1A1A1A",
                  fontSize: "12px",
                }}
                formatter={(value: number) => [
                  mode === "amount" ? formatAmount(value) : value,
                  mode === "amount" ? "Total Funding" : "Startups",
                ]}
              />
              <Bar dataKey="value" fill="#2D6A4F" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Right — recent rounds table */}
        <div className="rounded border border-border bg-surface p-4">
          <h3 className="text-sm font-medium text-text-primary mb-3">Recent Rounds</h3>
          {data.recent_rounds.length === 0 ? (
            <p className="text-sm text-text-tertiary py-8 text-center">No funding rounds data</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left px-3 py-2 text-xs font-medium text-text-tertiary">Company</th>
                    <th className="text-right px-3 py-2 text-xs font-medium text-text-tertiary">Amount</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-text-tertiary">Stage</th>
                    <th className="text-left px-3 py-2 text-xs font-medium text-text-tertiary">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_rounds.map((round, i) => (
                    <tr key={i} className="border-b border-border last:border-b-0 hover:bg-hover-row transition">
                      <td className="px-3 py-2">
                        <Link
                          href={`/startups/${round.startup_slug}`}
                          className="text-accent hover:text-accent-hover transition"
                        >
                          {round.startup_name}
                        </Link>
                      </td>
                      <td className="px-3 py-2 text-right text-text-primary tabular-nums">{round.amount}</td>
                      <td className="px-3 py-2 text-text-secondary">{STAGE_LABELS[round.stage] || round.stage}</td>
                      <td className="px-3 py-2 text-text-tertiary">{round.date || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/insights/FundingOverview.tsx
git commit -m "feat(insights): add FundingOverview component with stage chart and rounds table"
```

---

### Task 7: IndustryComparison Component

**Files:**
- Create: `frontend/components/insights/IndustryComparison.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/components/insights/IndustryComparison.tsx`:

```tsx
"use client";

import { useState } from "react";
import type { IndustryRow } from "@/lib/insights-types";

type SortKey = "avg_ai_score" | "count" | "total_funding";

function formatFunding(val: number): string {
  if (val >= 1_000_000_000) return `$${(val / 1_000_000_000).toFixed(1)}B`;
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(0)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(0)}K`;
  if (val > 0) return `$${val}`;
  return "—";
}

interface Props {
  data: IndustryRow[];
  onIndustryClick: (slug: string) => void;
}

export function IndustryComparison({ data, onIndustryClick }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("avg_ai_score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "desc" ? "asc" : "desc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const sorted = [...data].sort((a, b) => {
    const av = a[sortKey] ?? 0;
    const bv = b[sortKey] ?? 0;
    return sortDir === "desc" ? bv - av : av - bv;
  });

  const maxScore = Math.max(...data.map((d) => d.avg_ai_score ?? 0), 1);

  const sortArrow = (key: SortKey) => {
    if (sortKey !== key) return "";
    return sortDir === "desc" ? " ↓" : " ↑";
  };

  return (
    <section>
      <h2 className="font-serif text-xl text-text-primary mb-4">Industry Comparison</h2>
      <div className="rounded border border-border bg-surface overflow-x-auto">
        <table className="w-full text-sm min-w-[600px]">
          <thead>
            <tr className="border-b border-border bg-background">
              <th className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary w-48">
                Industry
              </th>
              <th
                className="text-left px-4 py-2.5 text-xs font-medium text-text-tertiary cursor-pointer hover:text-text-secondary transition"
                onClick={() => toggleSort("avg_ai_score")}
              >
                Avg AI Score{sortArrow("avg_ai_score")}
              </th>
              <th
                className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary cursor-pointer hover:text-text-secondary transition"
                onClick={() => toggleSort("count")}
              >
                Startups{sortArrow("count")}
              </th>
              <th
                className="text-right px-4 py-2.5 text-xs font-medium text-text-tertiary cursor-pointer hover:text-text-secondary transition"
                onClick={() => toggleSort("total_funding")}
              >
                Total Funding{sortArrow("total_funding")}
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr
                key={row.slug}
                className="border-b border-border last:border-b-0 hover:bg-hover-row transition cursor-pointer"
                onClick={() => onIndustryClick(row.slug)}
              >
                <td className="px-4 py-2.5 text-text-primary font-medium">{row.name}</td>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-4 bg-background rounded overflow-hidden">
                      <div
                        className="h-full bg-accent rounded"
                        style={{ width: `${((row.avg_ai_score ?? 0) / maxScore) * 100}%` }}
                      />
                    </div>
                    <span className="text-xs text-text-primary tabular-nums w-8 text-right">
                      {row.avg_ai_score !== null ? row.avg_ai_score.toFixed(1) : "—"}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-2.5 text-right text-text-secondary tabular-nums">{row.count}</td>
                <td className="px-4 py-2.5 text-right text-text-secondary tabular-nums">
                  {formatFunding(row.total_funding)}
                </td>
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-text-tertiary text-sm">
                  No industry data
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/insights/IndustryComparison.tsx
git commit -m "feat(insights): add IndustryComparison sortable table component"
```

---

### Task 8: DealFlow Component

**Files:**
- Create: `frontend/components/insights/DealFlow.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/components/insights/DealFlow.tsx`:

```tsx
"use client";

import Link from "next/link";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { DealFlowData } from "@/lib/insights-types";

const STAGE_LABELS: Record<string, string> = {
  pre_seed: "Pre-Seed",
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  series_c: "Series C",
  growth: "Growth",
  public: "Public",
};

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  if (days === 0) return "today";
  if (days === 1) return "1d ago";
  if (days < 7) return `${days}d ago`;
  const weeks = Math.floor(days / 7);
  if (weeks < 5) return `${weeks}w ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

function formatMonth(monthStr: string): string {
  // "2025-05" → "May '25"
  const [year, month] = monthStr.split("-");
  const date = new Date(Number(year), Number(month) - 1);
  const m = date.toLocaleString("en-US", { month: "short" });
  return `${m} '${year.slice(2)}`;
}

function scoreColor(score: number | null): string {
  if (score === null) return "text-text-tertiary";
  if (score >= 70) return "text-score-high";
  if (score >= 40) return "text-score-mid";
  return "text-score-low";
}

interface Props {
  data: DealFlowData;
}

export function DealFlow({ data }: Props) {
  const chartData = data.monthly.map((m) => ({
    name: formatMonth(m.month),
    count: m.count,
  }));

  return (
    <section>
      <h2 className="font-serif text-xl text-text-primary mb-4">Deal Flow</h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Left — monthly chart */}
        <div className="rounded border border-border bg-surface p-4">
          <h3 className="text-sm font-medium text-text-primary mb-3">New Startups per Month</h3>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={chartData} margin={{ top: 10, right: 10, bottom: 10, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E8E6E3" horizontal />
              <XAxis dataKey="name" stroke="#9B9B9B" fontSize={10} />
              <YAxis stroke="#9B9B9B" fontSize={11} allowDecimals={false} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#FFFFFF",
                  border: "1px solid #E8E6E3",
                  borderRadius: "4px",
                  color: "#1A1A1A",
                  fontSize: "12px",
                }}
                formatter={(value: number) => [value, "Startups added"]}
              />
              <Bar dataKey="count" fill="#B8553A" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Right — recent feed */}
        <div className="rounded border border-border bg-surface p-4">
          <h3 className="text-sm font-medium text-text-primary mb-3">Recently Added</h3>
          {data.recent.length === 0 ? (
            <p className="text-sm text-text-tertiary py-8 text-center">No recent startups</p>
          ) : (
            <div className="space-y-0">
              {data.recent.map((startup) => (
                <div
                  key={startup.slug}
                  className="flex items-center justify-between py-3 border-b border-border last:border-b-0"
                >
                  <div className="min-w-0 flex-1">
                    <Link
                      href={`/startups/${startup.slug}`}
                      className="text-sm font-medium text-accent hover:text-accent-hover transition truncate block"
                    >
                      {startup.name}
                    </Link>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-xs text-text-tertiary">{startup.industry}</span>
                      <span className="text-xs px-1.5 py-0.5 rounded bg-background text-text-secondary">
                        {STAGE_LABELS[startup.stage] || startup.stage}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 ml-3">
                    {startup.ai_score !== null && (
                      <span className={`text-sm font-medium tabular-nums ${scoreColor(startup.ai_score)}`}>
                        {startup.ai_score.toFixed(0)}
                      </span>
                    )}
                    <span className="text-xs text-text-tertiary w-12 text-right">
                      {timeAgo(startup.created_at)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/insights/DealFlow.tsx
git commit -m "feat(insights): add DealFlow component with monthly chart and recent feed"
```

---

### Task 9: Insights Page (compose all components)

**Files:**
- Modify: `frontend/app/insights/page.tsx` (replace entirely)

- [ ] **Step 1: Replace the page**

Replace the entire contents of `frontend/app/insights/page.tsx` with:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { InsightsResponse } from "@/lib/insights-types";
import { InsightsSummary } from "@/components/insights/InsightsSummary";
import { InsightsFilters, type FilterState } from "@/components/insights/InsightsFilters";
import { ScoreLandscape } from "@/components/insights/ScoreLandscape";
import { FundingOverview } from "@/components/insights/FundingOverview";
import { IndustryComparison } from "@/components/insights/IndustryComparison";
import { DealFlow } from "@/components/insights/DealFlow";

function parseFiltersFromParams(params: URLSearchParams): FilterState {
  return {
    stages: params.get("stage")?.split(",").filter(Boolean) || [],
    industries: params.get("industry")?.split(",").filter(Boolean) || [],
    countries: params.get("country")?.split(",").filter(Boolean) || [],
    states: params.get("state")?.split(",").filter(Boolean) || [],
    scoreMin: Number(params.get("score_min") || 0),
    scoreMax: Number(params.get("score_max") || 100),
    dateRange: params.get("date_range") || "all",
  };
}

function filtersToParams(filters: FilterState): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.stages.length) params.set("stage", filters.stages.join(","));
  if (filters.industries.length) params.set("industry", filters.industries.join(","));
  if (filters.countries.length) params.set("country", filters.countries.join(","));
  if (filters.states.length) params.set("state", filters.states.join(","));
  if (filters.scoreMin > 0) params.set("score_min", String(filters.scoreMin));
  if (filters.scoreMax < 100) params.set("score_max", String(filters.scoreMax));
  if (filters.dateRange !== "all") params.set("date_range", filters.dateRange);
  return params;
}

const DEFAULT_FILTERS: FilterState = {
  stages: [],
  industries: [],
  countries: [],
  states: [],
  scoreMin: 0,
  scoreMax: 100,
  dateRange: "all",
};

export default function InsightsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [data, setData] = useState<InsightsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<FilterState>(() =>
    parseFiltersFromParams(searchParams)
  );
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  const isFiltered =
    filters.stages.length > 0 ||
    filters.industries.length > 0 ||
    filters.countries.length > 0 ||
    filters.states.length > 0 ||
    filters.scoreMin > 0 ||
    filters.scoreMax < 100 ||
    filters.dateRange !== "all";

  const fetchData = useCallback(async (f: FilterState) => {
    setLoading(true);
    try {
      const params = filtersToParams(f);
      const result = await api.getInsights(params.toString() ? params : undefined);
      setData(result);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchData(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFilterChange = (newFilters: FilterState) => {
    setFilters(newFilters);
    // Update URL
    const params = filtersToParams(newFilters);
    const qs = params.toString();
    router.replace(qs ? `?${qs}` : "/insights", { scroll: false });
    // Debounce API call
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchData(newFilters), 300);
  };

  const handleIndustryClick = (slug: string) => {
    const newFilters = { ...filters, industries: [slug] };
    handleFilterChange(newFilters);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="font-serif text-3xl text-text-primary">Insights</h1>
        <p className="text-text-secondary mt-1">
          Explore deal flow, scores, and funding across the platform.
        </p>
      </div>

      {loading && !data ? (
        <div className="text-center py-20 text-text-tertiary text-sm">Loading insights...</div>
      ) : data ? (
        <>
          <InsightsSummary data={data.summary} isFiltered={isFiltered} />

          <div className="mt-6">
            <InsightsFilters
              filters={filters}
              filterOptions={data.filters}
              filteredCount={data.summary.filtered_startups}
              totalCount={data.summary.total_startups}
              onChange={handleFilterChange}
            />
          </div>

          <div className="mt-8 space-y-10">
            <ScoreLandscape data={data.scores} />
            <FundingOverview data={data.funding} />
            <IndustryComparison
              data={data.industries}
              onIndustryClick={handleIndustryClick}
            />
            <DealFlow data={data.deal_flow} />
          </div>
        </>
      ) : (
        <div className="text-center py-20 text-text-tertiary text-sm">
          Failed to load insights data.
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/insights/page.tsx
git commit -m "feat(insights): replace page with full dashboard composing all sections"
```

---

### Task 10: Remove Old Map Components and Dependencies

**Files:**
- Delete: `frontend/components/WorldMap.tsx`
- Delete: `frontend/components/USMap.tsx`
- Modify: `frontend/package.json`

- [ ] **Step 1: Delete map components**

```bash
rm frontend/components/WorldMap.tsx frontend/components/USMap.tsx
```

- [ ] **Step 2: Remove react-simple-maps dependencies**

In `frontend/package.json`, remove these two entries:
- From `dependencies`: `"react-simple-maps": "^3.0.0"`
- From `devDependencies`: `"@types/react-simple-maps": "^3.0.0"`

- [ ] **Step 3: Run npm install to update lockfile**

```bash
cd frontend && npm install
```

- [ ] **Step 4: Verify no remaining imports of removed files**

```bash
grep -r "WorldMap\|USMap\|react-simple-maps" frontend/app/ frontend/components/ frontend/lib/ --include="*.ts" --include="*.tsx"
```

Expected: No results

- [ ] **Step 5: Commit**

```bash
git add frontend/components/WorldMap.tsx frontend/components/USMap.tsx frontend/package.json frontend/package-lock.json
git commit -m "chore: remove WorldMap, USMap, and react-simple-maps dependency"
```

---

### Task 11: Deploy and Verify

**Files:** None (deployment task)

- [ ] **Step 1: Sync to EC2 and rebuild**

Per the project's deployment workflow: rsync changes to EC2, rebuild Docker containers.

```bash
# From project root
rsync -avz --delete --exclude=node_modules --exclude=.git --exclude=__pycache__ . ec2:~/acutal/
ssh ec2 "cd ~/acutal && docker compose up -d --build"
```

- [ ] **Step 2: Verify backend endpoint**

```bash
curl -s "https://<domain>/api/insights" | python3 -m json.tool | head -30
```

Expected: JSON response with `summary`, `scores`, `funding`, `industries`, `deal_flow`, `filters` keys.

- [ ] **Step 3: Verify filters work**

```bash
curl -s "https://<domain>/api/insights?stage=seed&score_min=50" | python3 -m json.tool | head -10
```

Expected: `filtered_startups` < `total_startups`

- [ ] **Step 4: Verify frontend renders**

Open `https://<domain>/insights` in browser. Verify:
- Summary strip shows 6 metrics
- Filter bar is sticky on scroll
- Scatter plot renders dots
- Histogram and verdicts appear
- Funding chart and rounds table render
- Industry table is sortable
- Deal flow chart and recent feed render
- Clicking a filter updates all sections
- URL updates when filters change
- Sharing a filtered URL loads with those filters applied
