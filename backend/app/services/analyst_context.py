"""Portfolio context injection for the AI analyst.

Provides pre-aggregated portfolio summaries and per-company profiles
to include in Perplexity system prompts.
"""

import logging
import time
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.industry import Industry
from app.models.startup import Startup, StartupStage, startup_industries

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 minutes

_portfolio_cache: dict | None = None
_portfolio_cache_time: float = 0


def _parse_funding(raw: str | None) -> float:
    """Parse a funding string like '$10M' or '$1.5B' to a float in dollars."""
    if not raw:
        return 0.0
    cleaned = raw.strip().replace(",", "").replace("$", "").upper()
    multiplier = 1.0
    if cleaned.endswith("B"):
        multiplier = 1_000_000_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith("M"):
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith("K"):
        multiplier = 1_000
        cleaned = cleaned[:-1]
    try:
        return float(cleaned) * multiplier
    except ValueError:
        return 0.0


async def get_portfolio_summary(db: AsyncSession) -> dict:
    """Return pre-aggregated portfolio summary. Cached for 5 minutes."""
    global _portfolio_cache, _portfolio_cache_time

    now = time.time()
    if _portfolio_cache and (now - _portfolio_cache_time) < CACHE_TTL:
        return _portfolio_cache

    # Total startups
    total_result = await db.execute(select(func.count(Startup.id)))
    total = total_result.scalar() or 0

    # Stage distribution
    stage_result = await db.execute(
        select(Startup.stage, func.count(Startup.id)).group_by(Startup.stage)
    )
    stage_dist = {
        (row[0].value if hasattr(row[0], "value") else str(row[0])): row[1]
        for row in stage_result.all()
        if row[0]
    }

    # Average AI score
    avg_result = await db.execute(
        select(func.avg(Startup.ai_score)).where(Startup.ai_score.isnot(None))
    )
    avg_score = avg_result.scalar()
    avg_score = round(avg_score, 1) if avg_score else 0

    # Total funding
    all_funding = await db.execute(select(Startup.total_funding))
    total_funding = sum(_parse_funding(row[0]) for row in all_funding.all())
    if total_funding >= 1_000_000_000:
        total_funding_str = f"${total_funding / 1_000_000_000:.1f}B"
    elif total_funding >= 1_000_000:
        total_funding_str = f"${total_funding / 1_000_000:.1f}M"
    else:
        total_funding_str = f"${total_funding:,.0f}"

    # Top industries by count
    industry_result = await db.execute(
        select(Industry.name, func.count(startup_industries.c.startup_id))
        .join(startup_industries, Industry.id == startup_industries.c.industry_id)
        .group_by(Industry.name)
        .order_by(func.count(startup_industries.c.startup_id).desc())
        .limit(10)
    )
    top_industries = [{"name": row[0], "count": row[1]} for row in industry_result.all()]

    # Score distribution (buckets of 10)
    score_result = await db.execute(
        select(Startup.ai_score).where(Startup.ai_score.isnot(None))
    )
    scores = [row[0] for row in score_result.all()]
    score_buckets = defaultdict(int)
    for s in scores:
        bucket = int(s // 10) * 10
        score_buckets[f"{bucket}-{bucket + 9}"] += 1

    summary = {
        "total_startups": total,
        "stage_distribution": stage_dist,
        "avg_ai_score": avg_score,
        "total_funding": total_funding_str,
        "top_industries": top_industries,
        "score_distribution": dict(sorted(score_buckets.items())),
    }

    _portfolio_cache = summary
    _portfolio_cache_time = now
    return summary


async def find_matching_startups(
    db: AsyncSession, message: str, limit: int = 5
) -> list[dict]:
    """Find startups whose names appear in the user message."""
    result = await db.execute(select(Startup.id, Startup.name))
    all_startups = result.all()

    message_lower = message.lower()
    matched_ids = []
    for sid, name in all_startups:
        if name and len(name) > 2 and name.lower() in message_lower:
            matched_ids.append(sid)

    if not matched_ids:
        return []

    result = await db.execute(
        select(Startup)
        .where(Startup.id.in_(matched_ids))
        .options(selectinload(Startup.industries))
        .limit(limit)
    )
    startups = result.scalars().all()
    return [_startup_to_context(s) for s in startups]


async def find_startups_by_filter(
    db: AsyncSession, message: str, limit: int = 20
) -> list[dict]:
    """Find startups matching sector or stage keywords in the message."""
    message_lower = message.lower()

    # Check for stage keywords
    stage_map = {
        "pre-seed": "pre_seed", "pre seed": "pre_seed", "preseed": "pre_seed",
        "seed": "seed",
        "series a": "series_a",
        "series b": "series_b",
        "series c": "series_c",
        "growth": "growth",
        "public": "public", "ipo": "public",
    }
    matched_stage = None
    for keyword, stage_val in stage_map.items():
        if keyword in message_lower:
            matched_stage = stage_val
            break

    # Check for industry keywords
    industry_result = await db.execute(select(Industry.id, Industry.name))
    all_industries = industry_result.all()
    matched_industry_id = None
    for ind_id, ind_name in all_industries:
        if ind_name and ind_name.lower() in message_lower:
            matched_industry_id = ind_id
            break

    if not matched_stage and not matched_industry_id:
        return []

    query = select(Startup).options(selectinload(Startup.industries))
    if matched_stage:
        query = query.where(Startup.stage == matched_stage)
    if matched_industry_id:
        query = query.where(
            Startup.id.in_(
                select(startup_industries.c.startup_id).where(
                    startup_industries.c.industry_id == matched_industry_id
                )
            )
        )
    query = query.order_by(Startup.ai_score.desc().nulls_last()).limit(limit)

    result = await db.execute(query)
    startups = result.scalars().all()
    return [_startup_to_context(s) for s in startups]


def _startup_to_context(s: Startup) -> dict:
    """Convert a Startup ORM object to a context dict for the system prompt."""
    return {
        "id": str(s.id),
        "name": s.name,
        "tagline": s.tagline,
        "description": s.description,
        "stage": s.stage.value if s.stage else None,
        "ai_score": s.ai_score,
        "total_funding": s.total_funding,
        "employee_count": s.employee_count,
        "business_model": s.business_model,
        "revenue_estimate": s.revenue_estimate,
        "competitors": s.competitors,
        "tech_stack": s.tech_stack,
        "key_metrics": s.key_metrics,
        "website_url": s.website_url,
        "industries": [ind.name for ind in s.industries] if s.industries else [],
    }


def build_system_prompt(summary: dict, startup_profiles: list[dict] | None = None) -> str:
    """Build the Perplexity system prompt with injected portfolio context."""
    stage_lines = ", ".join(
        f"{stage}: {count}" for stage, count in summary["stage_distribution"].items()
    )
    industry_lines = ", ".join(
        f"{ind['name']} ({ind['count']})" for ind in summary["top_industries"][:7]
    )
    score_lines = ", ".join(
        f"{bucket}: {count}" for bucket, count in summary["score_distribution"].items()
    )

    prompt = f"""You are a senior venture analyst at Deep Thesis with a data science background.
You have access to a proprietary database of {summary['total_startups']} startups and external market intelligence via Crunchbase and PitchBook.

PORTFOLIO SUMMARY:
- {summary['total_startups']} total startups
- Stage distribution: {stage_lines}
- Average AI score: {summary['avg_ai_score']}/100
- Total tracked funding: {summary['total_funding']}
- Top sectors by count: {industry_lines}
- Score distribution: {score_lines}
"""

    if startup_profiles:
        prompt += "\nSTARTUP PROFILES (from our database):\n"
        for sp in startup_profiles:
            prompt += f"\n--- {sp['name']} ---\n"
            for key, val in sp.items():
                if key == "id" or val is None:
                    continue
                prompt += f"  {key}: {val}\n"

    prompt += """
When the user asks about specific companies in our database, their full profiles are provided above. For external companies, use your web access to research Crunchbase, PitchBook, and other sources.

Respond with analysis, not just data. Interpret trends, flag risks, compare to benchmarks. When data supports it, include a chart using this exact JSON format:

:::chart
{"type": "bar", "title": "Chart Title", "data": [{"name": "A", "value": 10}], "xKey": "name", "yKeys": ["value"], "colors": ["#6366f1"]}
:::

Valid chart types: bar, line, pie, scatter, area.
You may include multiple charts per response. Always explain what the chart shows before or after it.
For pie charts, use "nameKey" instead of "xKey" and "dataKey" instead of "yKeys".
Keep chart data arrays reasonable (under 30 items).
"""
    return prompt
