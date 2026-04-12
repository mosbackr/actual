"""Enrichment pipeline service.

Calls Perplexity Sonar Pro twice (data research + scoring) and writes
results to the database.  Designed to run inside a FastAPI BackgroundTask.
"""

import json
import logging
import re
import uuid
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.session import async_session
from app.models.ai_review import StartupAIReview
from app.models.dimension import StartupDimension
from app.models.founder import StartupFounder
from app.models.funding_round import StartupFundingRound
from app.models.media import MediaType, StartupMedia
from app.models.score import ScoreType, StartupScoreHistory
from app.models.startup import CompanyStatus, EnrichmentStatus, Startup
from app.models.template import DueDiligenceTemplate, TemplateDimension

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ENRICHMENT_SYSTEM_PROMPT = """\
You are a startup research analyst. Given a startup name, website URL, and \
description, research the company thoroughly and return a JSON object with the \
following fields.  Use null for any field you cannot determine.

{
  "tagline": "one-line description",
  "website_url": "https://example.com",
  "description": "2-3 paragraph detailed description",
  "founded_date": "YYYY or YYYY-MM-DD",
  "company_status": "active | acquired | ipo | defunct",
  "business_model": "SaaS | Marketplace | Hardware | Fintech | etc.",
  "revenue_estimate": "$1M-$5M ARR (or whatever is reported/estimated)",
  "founders": [
    {"name": "Full Name", "title": "CEO / CTO / etc.", "linkedin_url": "https://...", "is_founder": true, "prior_experience": "Previously founded X (acquired by Y), VP Eng at Z", "education": "Stanford CS, MBA Wharton"}
  ],
  "management_team": [
    {"name": "Full Name", "title": "CFO / VP Sales / etc.", "linkedin_url": "https://...", "prior_experience": "10 years at Google, CFO at startup X", "education": "Harvard MBA"}
  ],
  "funding_rounds": [
    {"round_name": "Seed", "amount": "$2M", "date": "2023-01", "lead_investor": "Firm Name", "other_investors": "Angel A, Fund B, Fund C", "pre_money_valuation": "$8M", "post_money_valuation": "$10M"}
  ],
  "total_funding": "$10M",
  "employee_count": "50-100",
  "linkedin_url": "https://linkedin.com/company/...",
  "twitter_url": "https://twitter.com/...",
  "crunchbase_url": "https://crunchbase.com/organization/...",
  "competitors": "Competitor A, Competitor B, Competitor C",
  "tech_stack": "Python, React, AWS, ...",
  "key_metrics": "ARR $1M, 10k users, 20% MoM growth, ...",
  "hiring_signals": "Hiring 5 engineers, opened new SF office, ...",
  "patents": "Patent on X technology, filed Y patent, ...",
  "media": [
    {"url": "https://...", "title": "Article title", "source": "TechCrunch", "media_type": "article", "published_at": "2024-01-15"}
  ]
}

IMPORTANT: For funding_rounds, list ALL known investors per round (not just the lead). \
Include valuations when publicly reported. For founders and management_team, include \
prior work experience and education when available.

Return ONLY valid JSON. No markdown, no extra commentary.\
"""

SCORING_SYSTEM_PROMPT = """\
You are a senior VC analyst performing due diligence. You will be given \
enriched data about a startup, its industry and funding stage, and a list \
of scoring dimensions with weights.

IMPORTANT: Calibrate your scoring to the company's industry and stage.
- For pre-seed/seed companies, weight team, vision, and market signals more \
heavily; do not penalize for lack of revenue or metrics.
- For Series A, expect clear product-market fit evidence and early traction.
- For Series B+ and growth, expect strong revenue, unit economics, and a \
clear path to profitability.
- Apply industry-specific standards: a biotech company should be evaluated \
on clinical pipeline and regulatory, not SaaS metrics; a fintech company \
needs regulatory compliance assessment.

For each dimension, provide a score from 0 to 100 and a brief reasoning \
(1-2 sentences).

Also provide:
- investment_thesis: A 2-3 sentence investment thesis.
- key_risks: A bullet list of 3-5 key risks.
- verdict: One of "Strong Pass", "Pass", "Lean Pass", "Lean Invest", "Invest", "Strong Invest".

Return a JSON object:
{
  "dimensions": {
    "Dimension Name": {"score": 75, "reasoning": "..."},
    ...
  },
  "investment_thesis": "...",
  "key_risks": "- Risk 1\\n- Risk 2\\n- Risk 3",
  "verdict": "Lean Invest"
}

Return ONLY valid JSON. No markdown, no extra commentary.\
"""

# ---------------------------------------------------------------------------
# Default dimensions (fallback when no template matches)
# ---------------------------------------------------------------------------

DEFAULT_DIMENSIONS: list[tuple[str, float]] = [
    ("Market Opportunity", 1.2),
    ("Team Strength", 1.3),
    ("Product & Technology", 1.1),
    ("Traction & Metrics", 1.2),
    ("Business Model", 1.0),
    ("Competitive Moat", 1.0),
    ("Financials & Unit Economics", 0.9),
    ("Timing & Market Readiness", 0.8),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Turn a dimension name into a slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _extract_json(text: str) -> dict:
    """Extract JSON from ```json fences or bare JSON."""
    # Try to find fenced JSON first
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())
    # Try bare JSON (find first { ... last })
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("No JSON found in response")


async def _call_perplexity(messages: list[dict], timeout: int = 90) -> str:
    """Call Perplexity Sonar Pro API and return the assistant message content."""
    if not settings.perplexity_api_key:
        raise RuntimeError("ACUTAL_PERPLEXITY_API_KEY is not configured")

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.perplexity_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar-pro",
                "temperature": 0.1,
                "max_tokens": 4096,
                "messages": messages,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def _enrich_data(
    startup_name: str,
    website_url: str | None,
    description: str,
) -> dict:
    """Call Perplexity for startup data enrichment."""
    user_msg = f"Startup: {startup_name}\n"
    if website_url:
        user_msg += f"Website: {website_url}\n"
    user_msg += f"Description: {description}"

    raw = await _call_perplexity(
        [
            {"role": "system", "content": ENRICHMENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
    )
    return _extract_json(raw)


async def _score_startup(
    enriched_data: dict,
    dimensions: list[dict],
    industry: str | None = None,
    stage: str | None = None,
) -> dict:
    """Call Perplexity for VC-style scoring with industry/stage context."""
    dim_text = "\n".join(
        f"- {d['name']} (weight {d['weight']})" for d in dimensions
    )

    context_parts = []
    if industry:
        context_parts.append(f"Industry: {industry}")
    if stage:
        stage_labels = {
            "pre_seed": "Pre-Seed",
            "seed": "Seed",
            "series_a": "Series A",
            "series_b": "Series B",
            "series_c": "Series C",
            "growth": "Growth / Late Stage",
        }
        context_parts.append(f"Funding Stage: {stage_labels.get(stage, stage)}")

    context_line = ""
    if context_parts:
        context_line = f"\n\nCompany context: {' | '.join(context_parts)}\n"

    user_msg = (
        f"Enriched data:\n```json\n{json.dumps(enriched_data, indent=2)}\n```\n"
        f"{context_line}\n"
        f"Scoring dimensions:\n{dim_text}"
    )

    raw = await _call_perplexity(
        [
            {"role": "system", "content": SCORING_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
    )
    return _extract_json(raw)


async def _fetch_logo_if_needed(startup: Startup, db) -> None:
    """Fetch logo from Logo.dev if the startup has a website but no logo."""
    if startup.logo_url or not startup.website_url or not settings.logo_dev_token:
        return

    try:
        parsed = urlparse(startup.website_url if "://" in startup.website_url else f"https://{startup.website_url}")
        domain = parsed.hostname
        if not domain:
            return
        domain = re.sub(r"^www\.", "", domain)

        logo_url = f"https://img.logo.dev/{domain}?token={settings.logo_dev_token}&size=200&format=png"

        # Verify the logo actually resolves (GET — Logo.dev returns 404 for HEAD)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(logo_url, follow_redirects=True)
            if resp.status_code == 200 and "image" in (resp.headers.get("content-type") or ""):
                startup.logo_url = logo_url
                await db.flush()
    except Exception:
        logger.debug("Logo fetch failed for %s, skipping", startup.name)


async def _ensure_dimensions(startup_id: uuid.UUID, db) -> list[dict]:
    """Ensure a startup has dimensions. Auto-apply template or use defaults.

    Template matching priority:
    1. Exact match: industry_slug + stage
    2. Industry match: industry_slug only (stage=NULL)
    3. Stage match: stage only (industry_slug=NULL)
    4. General fallback: both NULL, name="General"
    5. Hardcoded defaults

    Returns a list of dicts: [{"name": ..., "slug": ..., "weight": ...}, ...]
    """
    result = await db.execute(
        select(StartupDimension)
        .where(StartupDimension.startup_id == startup_id)
        .order_by(StartupDimension.sort_order)
    )
    existing = result.scalars().all()
    if existing:
        return [
            {"name": d.dimension_name, "slug": d.dimension_slug, "weight": d.weight}
            for d in existing
        ]

    # Load the startup with industries eagerly
    result = await db.execute(
        select(Startup).where(Startup.id == startup_id).options(selectinload(Startup.industries))
    )
    startup = result.scalars().first()
    template = None

    if startup:
        industry_slug = startup.industries[0].slug if startup.industries else None
        stage_value = startup.stage.value if startup.stage else None

        # 1. Exact match: industry + stage
        if industry_slug and stage_value:
            result = await db.execute(
                select(DueDiligenceTemplate).where(
                    DueDiligenceTemplate.industry_slug == industry_slug,
                    DueDiligenceTemplate.stage == stage_value,
                )
            )
            template = result.scalars().first()

        # 2. Industry-only match
        if template is None and industry_slug:
            result = await db.execute(
                select(DueDiligenceTemplate).where(
                    DueDiligenceTemplate.industry_slug == industry_slug,
                    DueDiligenceTemplate.stage.is_(None),
                )
            )
            template = result.scalars().first()

        # 3. Stage-only match
        if template is None and stage_value:
            result = await db.execute(
                select(DueDiligenceTemplate).where(
                    DueDiligenceTemplate.industry_slug.is_(None),
                    DueDiligenceTemplate.stage == stage_value,
                )
            )
            template = result.scalars().first()

    # 4. General fallback
    if template is None:
        result = await db.execute(
            select(DueDiligenceTemplate).where(DueDiligenceTemplate.name == "General")
        )
        template = result.scalars().first()

    dims_to_create: list[tuple[str, str, float]] = []

    if template is not None:
        result = await db.execute(
            select(TemplateDimension)
            .where(TemplateDimension.template_id == template.id)
            .order_by(TemplateDimension.sort_order)
        )
        tdims = result.scalars().all()
        if tdims:
            dims_to_create = [
                (td.dimension_name, td.dimension_slug, td.weight) for td in tdims
            ]
            if startup:
                startup.template_id = template.id

    # 5. Hardcoded defaults
    if not dims_to_create:
        dims_to_create = [
            (name, _slugify(name), weight) for name, weight in DEFAULT_DIMENSIONS
        ]

    created: list[dict] = []
    for idx, (name, slug, weight) in enumerate(dims_to_create):
        dim = StartupDimension(
            startup_id=startup_id,
            dimension_name=name,
            dimension_slug=slug,
            weight=weight,
            sort_order=idx,
        )
        db.add(dim)
        created.append({"name": name, "slug": slug, "weight": weight})

    await db.flush()
    return created


def _parse_founded_date(raw: str | None) -> date | None:
    """Parse a founded_date string into a date object."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        if len(raw) == 4:
            return date(int(raw), 1, 1)
        return date.fromisoformat(raw[:10])
    except (ValueError, TypeError):
        return None


def _map_media_type(raw: str | None) -> MediaType:
    """Map a raw media_type string to the MediaType enum, defaulting to article."""
    if not raw:
        return MediaType.article
    cleaned = raw.strip().lower().replace(" ", "_")
    try:
        return MediaType(cleaned)
    except ValueError:
        return MediaType.article


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


async def run_enrichment_pipeline(startup_id: str) -> None:
    """Run full enrichment pipeline for a startup.

    Designed to be called from FastAPI BackgroundTasks.
    Creates its own DB session so it is independent of the request lifecycle.
    """
    sid = uuid.UUID(startup_id)

    async with async_session() as db:
        try:
            # ----------------------------------------------------------
            # 1. Mark as running
            # ----------------------------------------------------------
            startup = await db.get(Startup, sid)
            if startup is None:
                logger.error("Startup %s not found", startup_id)
                return

            startup.enrichment_status = EnrichmentStatus.running
            startup.enrichment_error = None
            await db.commit()

            # ----------------------------------------------------------
            # 2. Enrichment: call Perplexity for data research
            # ----------------------------------------------------------
            enriched = await _enrich_data(
                startup_name=startup.name,
                website_url=startup.website_url,
                description=startup.description,
            )

            # Update scalar fields on startup
            if enriched.get("website_url") and not startup.website_url:
                startup.website_url = enriched["website_url"][:500]
            if enriched.get("tagline"):
                startup.tagline = enriched["tagline"][:500]
            if enriched.get("description"):
                startup.description = enriched["description"]
            if enriched.get("founded_date"):
                parsed_date = _parse_founded_date(enriched["founded_date"])
                if parsed_date:
                    startup.founded_date = parsed_date
            if enriched.get("total_funding"):
                startup.total_funding = enriched["total_funding"][:100]
            if enriched.get("employee_count"):
                startup.employee_count = enriched["employee_count"][:50]
            if enriched.get("linkedin_url"):
                startup.linkedin_url = enriched["linkedin_url"][:500]
            if enriched.get("twitter_url"):
                startup.twitter_url = enriched["twitter_url"][:500]
            if enriched.get("crunchbase_url"):
                startup.crunchbase_url = enriched["crunchbase_url"][:500]
            if enriched.get("competitors"):
                startup.competitors = enriched["competitors"]
            if enriched.get("tech_stack"):
                startup.tech_stack = enriched["tech_stack"]
            if enriched.get("key_metrics"):
                startup.key_metrics = enriched["key_metrics"]
            if enriched.get("hiring_signals"):
                startup.hiring_signals = enriched["hiring_signals"]
            if enriched.get("patents"):
                startup.patents = enriched["patents"]
            if enriched.get("company_status"):
                try:
                    startup.company_status = CompanyStatus(enriched["company_status"].lower().strip())
                except ValueError:
                    pass
            if enriched.get("revenue_estimate"):
                startup.revenue_estimate = enriched["revenue_estimate"][:200]
            if enriched.get("business_model"):
                startup.business_model = enriched["business_model"][:200]

            await db.flush()

            # ----------------------------------------------------------
            # 3. Replace founders and management team
            # ----------------------------------------------------------
            await db.execute(
                delete(StartupFounder).where(StartupFounder.startup_id == sid)
            )
            idx = 0
            for f in enriched.get("founders") or []:
                if not f.get("name"):
                    continue
                db.add(
                    StartupFounder(
                        startup_id=sid,
                        name=f["name"][:200],
                        title=(f.get("title") or "")[:200] or None,
                        linkedin_url=(f.get("linkedin_url") or "")[:500] or None,
                        is_founder=True,
                        prior_experience=(f.get("prior_experience") or "")[:2000] or None,
                        education=(f.get("education") or "")[:500] or None,
                        sort_order=idx,
                    )
                )
                idx += 1
            for m in enriched.get("management_team") or []:
                if not m.get("name"):
                    continue
                db.add(
                    StartupFounder(
                        startup_id=sid,
                        name=m["name"][:200],
                        title=(m.get("title") or "")[:200] or None,
                        linkedin_url=(m.get("linkedin_url") or "")[:500] or None,
                        is_founder=False,
                        prior_experience=(m.get("prior_experience") or "")[:2000] or None,
                        education=(m.get("education") or "")[:500] or None,
                        sort_order=idx,
                    )
                )
                idx += 1
            await db.flush()

            # ----------------------------------------------------------
            # 4. Replace funding rounds
            # ----------------------------------------------------------
            await db.execute(
                delete(StartupFundingRound).where(
                    StartupFundingRound.startup_id == sid
                )
            )
            for idx, fr in enumerate(enriched.get("funding_rounds") or []):
                if not fr.get("round_name"):
                    continue
                db.add(
                    StartupFundingRound(
                        startup_id=sid,
                        round_name=fr["round_name"][:100],
                        amount=(fr.get("amount") or "")[:50] or None,
                        date=(fr.get("date") or "")[:20] or None,
                        lead_investor=(fr.get("lead_investor") or "")[:200] or None,
                        other_investors=(fr.get("other_investors") or "")[:1000] or None,
                        pre_money_valuation=(fr.get("pre_money_valuation") or "")[:50] or None,
                        post_money_valuation=(fr.get("post_money_valuation") or "")[:50] or None,
                        sort_order=idx,
                    )
                )
            await db.flush()

            # ----------------------------------------------------------
            # 5. Replace media items
            # ----------------------------------------------------------
            await db.execute(
                delete(StartupMedia).where(StartupMedia.startup_id == sid)
            )
            for m in enriched.get("media") or []:
                if not m.get("url") or not m.get("title"):
                    continue
                published = None
                if m.get("published_at"):
                    try:
                        published = datetime.fromisoformat(
                            m["published_at"].replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        pass
                db.add(
                    StartupMedia(
                        startup_id=sid,
                        url=m["url"][:500],
                        title=m["title"][:500],
                        source=(m.get("source") or "unknown")[:100],
                        media_type=_map_media_type(m.get("media_type")),
                        published_at=published,
                    )
                )
            await db.flush()

            # ----------------------------------------------------------
            # 6. Fetch logo if needed
            # ----------------------------------------------------------
            await _fetch_logo_if_needed(startup, db)

            # ----------------------------------------------------------
            # 7. Ensure dimensions exist
            # ----------------------------------------------------------
            dimensions = await _ensure_dimensions(sid, db)

            # Reload startup with industries for scoring context
            result = await db.execute(
                select(Startup).where(Startup.id == sid).options(selectinload(Startup.industries))
            )
            startup = result.scalars().first()
            industry_name = startup.industries[0].name if startup and startup.industries else None
            stage_value = startup.stage.value if startup and startup.stage else None

            # ----------------------------------------------------------
            # 8. Scoring: call Perplexity for VC-style scoring
            # ----------------------------------------------------------
            score_result = await _score_startup(
                enriched, dimensions, industry=industry_name, stage=stage_value
            )

            dim_scores_raw = score_result.get("dimensions", {})
            investment_thesis = score_result.get("investment_thesis", "")
            key_risks = score_result.get("key_risks", "")
            verdict = score_result.get("verdict", "")

            # Build weight map and compute weighted average
            weight_map: dict[str, float] = {d["name"]: d["weight"] for d in dimensions}
            total_weight = 0.0
            weighted_sum = 0.0
            dimensions_json: dict[str, float] = {}

            for dim_name, dim_data in dim_scores_raw.items():
                score_val = dim_data.get("score", 0) if isinstance(dim_data, dict) else 0
                score_val = max(0.0, min(100.0, float(score_val)))
                dimensions_json[dim_name] = score_val

                # Find the matching weight (case-insensitive)
                matched_weight = 1.0
                for wname, wval in weight_map.items():
                    if wname.lower() == dim_name.lower():
                        matched_weight = wval
                        break
                weighted_sum += score_val * matched_weight
                total_weight += matched_weight

            overall_score = round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.0

            # Build full dimension_scores for the AI review (includes reasoning)
            dimension_scores_full: dict[str, dict] = {}
            for dim_name, dim_data in dim_scores_raw.items():
                if isinstance(dim_data, dict):
                    dimension_scores_full[dim_name] = {
                        "score": dim_data.get("score", 0),
                        "reasoning": dim_data.get("reasoning", ""),
                    }
                else:
                    dimension_scores_full[dim_name] = {"score": 0, "reasoning": ""}

            # ----------------------------------------------------------
            # 9. Upsert AI review
            # ----------------------------------------------------------
            existing_review = (
                await db.execute(
                    select(StartupAIReview).where(
                        StartupAIReview.startup_id == sid
                    )
                )
            ).scalars().first()

            if existing_review:
                existing_review.overall_score = overall_score
                existing_review.investment_thesis = investment_thesis
                existing_review.key_risks = key_risks
                existing_review.verdict = verdict
                existing_review.dimension_scores = dimension_scores_full
            else:
                db.add(
                    StartupAIReview(
                        startup_id=sid,
                        overall_score=overall_score,
                        investment_thesis=investment_thesis,
                        key_risks=key_risks,
                        verdict=verdict,
                        dimension_scores=dimension_scores_full,
                    )
                )
            await db.flush()

            # ----------------------------------------------------------
            # 10. Update ai_score on startup and add score history
            # ----------------------------------------------------------
            startup.ai_score = overall_score

            db.add(
                StartupScoreHistory(
                    startup_id=sid,
                    score_type=ScoreType.ai,
                    score_value=overall_score,
                    dimensions_json=dimensions_json,
                )
            )

            # ----------------------------------------------------------
            # 11. Mark enrichment complete
            # ----------------------------------------------------------
            startup.enrichment_status = EnrichmentStatus.complete
            startup.enriched_at = datetime.now(timezone.utc)
            startup.enrichment_error = None

            await db.commit()
            logger.info("Enrichment complete for startup %s (score: %.1f)", startup.name, overall_score)

        except Exception as exc:
            logger.exception("Enrichment failed for startup %s: %s", startup_id, exc)
            await db.rollback()

            # Mark as failed
            try:
                startup = await db.get(Startup, sid)
                if startup:
                    startup.enrichment_status = EnrichmentStatus.failed
                    startup.enrichment_error = str(exc)[:500]
                    await db.commit()
            except Exception:
                logger.exception("Failed to update enrichment_status to failed for %s", startup_id)
