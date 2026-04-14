import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.ai_review import StartupAIReview
from app.models.funding_round import StartupFundingRound
from app.models.industry import Industry
from app.models.startup import EntityType, Startup, StartupStage, StartupStatus, startup_industries

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

    # Date filter — based on funding round dates, not created_at
    date_cutoff_str = None
    if date_range:
        now_utc = datetime.now(timezone.utc)
        mapping = {"30d": 30, "90d": 90, "6m": 180, "1y": 365}
        days = mapping.get(date_range)
        if days:
            cutoff = now_utc - timedelta(days=days)
            date_cutoff_str = cutoff.strftime("%Y-%m")

    # Subquery: startup IDs with a funding round after cutoff
    date_filter_ids = None
    if date_cutoff_str:
        date_filter_ids = (
            select(StartupFundingRound.startup_id)
            .where(StartupFundingRound.date.isnot(None))
            .where(StartupFundingRound.date >= date_cutoff_str)
            .where(StartupFundingRound.date <= datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            .distinct()
        )

    def apply_filters(q):
        q = q.where(approved).where(Startup.entity_type == EntityType.startup)
        if stage:
            q = q.where(Startup.stage.in_(stage))
        if industry_filter is not None:
            q = q.where(Startup.id.in_(industry_filter))
        if country:
            q = q.where(Startup.location_country.in_(country))
        if state:
            q = q.where(Startup.location_state.in_(state))
        if score_min is not None:
            q = q.where(Startup.ai_score >= score_min)
        if score_max is not None:
            q = q.where(Startup.ai_score <= score_max)
        if date_filter_ids is not None:
            q = q.where(Startup.id.in_(date_filter_ids))
        return q

    # ── Total counts (unfiltered for "X of Y") ──
    total_q = select(func.count(Startup.id)).where(approved).where(Startup.entity_type == EntityType.startup)
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

    # Mode stage
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
    # Scatter: AI Score vs Funding (most startups have these)
    scatter_ids = [r.id for r in startup_rows if r.ai_score is not None]
    scatter = []
    if scatter_ids:
        industry_q2 = (
            select(
                startup_industries.c.startup_id,
                Industry.name,
            )
            .join(Industry, startup_industries.c.industry_id == Industry.id)
            .where(startup_industries.c.startup_id.in_(scatter_ids))
        )
        ind_rows = (await db.execute(industry_q2)).all()
        startup_industry: dict[str, str] = {}
        for ir in ind_rows:
            sid = str(ir.startup_id)
            if sid not in startup_industry:
                startup_industry[sid] = ir.name

        for r in startup_rows:
            if r.ai_score is not None:
                funding_val = parse_funding_to_float(r.total_funding) or 0
                scatter.append({
                    "id": str(r.id),
                    "slug": r.slug,
                    "name": r.name,
                    "ai_score": round(r.ai_score, 1),
                    "expert_score": round(r.expert_score, 1) if r.expert_score is not None else None,
                    "industry": startup_industry.get(str(r.id), "Other"),
                    "stage": r.stage.value if hasattr(r.stage, "value") else str(r.stage),
                    "total_funding_raw": funding_val,
                })

    # Histogram: AI score buckets
    histogram = []
    buckets = [(i * 10, (i + 1) * 10) for i in range(10)]
    for low, high in buckets:
        count = sum(1 for r in startup_rows if r.ai_score is not None and low <= r.ai_score < high)
        histogram.append({"bucket": f"{low}-{high}", "count": count})

    # Verdicts — exclude null/empty verdicts
    verdicts = []
    if startup_ids:
        verdict_all_q = (
            select(StartupAIReview.verdict, func.count(StartupAIReview.id).label("cnt"))
            .where(StartupAIReview.startup_id.in_(startup_ids))
            .where(StartupAIReview.verdict.isnot(None))
            .where(StartupAIReview.verdict != "")
            .group_by(StartupAIReview.verdict)
            .order_by(func.count(StartupAIReview.id).desc())
        )
        for row in (await db.execute(verdict_all_q)).all():
            verdicts.append({"verdict": row.verdict, "count": row.cnt})

    scores = {"scatter": scatter, "histogram": histogram, "verdicts": verdicts}

    # ── Funding section ──
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

    # Recent rounds — only include rows with ISO-ish dates (YYYY-MM or YYYY-MM-DD)
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
            .where(StartupFundingRound.date.isnot(None))
            .where(StartupFundingRound.date.regexp_match(r"^\d{4}-\d{2}"))
            .where(StartupFundingRound.date <= datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            .order_by(StartupFundingRound.date.desc())
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

    # ── Deal flow section — funding rounds per month ──
    now_str = now.strftime("%Y-%m-%d")
    monthly: dict[str, int] = {}
    if startup_ids:
        deal_rounds_q = (
            select(StartupFundingRound.date)
            .where(StartupFundingRound.startup_id.in_(startup_ids))
            .where(StartupFundingRound.date.isnot(None))
            .where(StartupFundingRound.date.regexp_match(r"^\d{4}-\d{2}"))
            .where(StartupFundingRound.date <= now_str)
        )
        for row in (await db.execute(deal_rounds_q)).all():
            month_key = row.date[:7]  # "YYYY-MM"
            monthly[month_key] = monthly.get(month_key, 0) + 1

    # Build last 12 months ensuring all months present
    monthly_list = []
    for i in range(11, -1, -1):
        d = now - timedelta(days=i * 30)
        key = d.strftime("%Y-%m")
        monthly_list.append({"month": key, "count": monthly.get(key, 0)})
    # Deduplicate (timedelta math can hit same month twice)
    seen_months: dict[str, dict] = {}
    for m_item in monthly_list:
        if m_item["month"] not in seen_months:
            seen_months[m_item["month"]] = m_item
        else:
            seen_months[m_item["month"]]["count"] = max(
                seen_months[m_item["month"]]["count"], m_item["count"]
            )
    monthly_list = list(seen_months.values())

    # Recent funding rounds (most recent by date)
    recent = []
    if startup_ids:
        recent_rounds_q = (
            select(
                StartupFundingRound.startup_id,
                StartupFundingRound.date,
                StartupFundingRound.round_name,
                StartupFundingRound.amount,
            )
            .where(StartupFundingRound.startup_id.in_(startup_ids))
            .where(StartupFundingRound.date.isnot(None))
            .where(StartupFundingRound.date.regexp_match(r"^\d{4}-\d{2}"))
            .where(StartupFundingRound.date <= now_str)
            .order_by(StartupFundingRound.date.desc())
            .limit(8)
        )
        recent_round_rows = (await db.execute(recent_rounds_q)).all()

        # Look up startup names + industries
        rr_startup_ids = list({r.startup_id for r in recent_round_rows})
        rr_name_map: dict[str, tuple] = {}
        if rr_startup_ids:
            name_q = select(Startup.id, Startup.name, Startup.slug, Startup.ai_score).where(
                Startup.id.in_(rr_startup_ids)
            )
            for sr in (await db.execute(name_q)).all():
                rr_name_map[str(sr.id)] = (sr.name, sr.slug, sr.ai_score)

            ri_q = (
                select(startup_industries.c.startup_id, Industry.name)
                .join(Industry, startup_industries.c.industry_id == Industry.id)
                .where(startup_industries.c.startup_id.in_(rr_startup_ids))
            )
            rr_industry: dict[str, str] = {}
            for ir in (await db.execute(ri_q)).all():
                sid = str(ir.startup_id)
                if sid not in rr_industry:
                    rr_industry[sid] = ir.name

        for rr in recent_round_rows:
            sid = str(rr.startup_id)
            info = rr_name_map.get(sid, ("Unknown", "unknown", None))
            recent.append({
                "name": info[0],
                "slug": info[1],
                "round_name": rr.round_name,
                "amount": rr.amount,
                "date": rr.date,
                "industry": rr_industry.get(sid, "Other") if rr_startup_ids else "Other",
                "ai_score": round(info[2], 1) if info[2] is not None else None,
            })

    deal_flow = {"monthly": monthly_list, "recent": recent}

    # ── Available filter options ──
    countries_q = (
        select(Startup.location_country)
        .where(approved)
        .where(Startup.entity_type == EntityType.startup)
        .where(Startup.location_country.isnot(None))
        .where(Startup.location_country != "")
        .distinct()
        .order_by(Startup.location_country)
    )
    available_countries = [r[0] for r in (await db.execute(countries_q)).all()]

    states_q = (
        select(Startup.location_state)
        .where(approved)
        .where(Startup.entity_type == EntityType.startup)
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
        .where(Startup.entity_type == EntityType.startup)
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
