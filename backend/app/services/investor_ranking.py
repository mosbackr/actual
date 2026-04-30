import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import async_session
from app.models.funding_round import StartupFundingRound
from app.models.investor import BatchJobStatus, Investor
from app.models.investor_ranking import InvestorRanking, InvestorRankingBatchJob
from app.models.startup import CompanyStatus, Startup

CONCURRENCY = 10  # parallel API workers
DB_SEMAPHORE = asyncio.Semaphore(2)  # limit DB connections

logger = logging.getLogger(__name__)

DIMENSION_NAMES = [
    "portfolio_performance",
    "deal_activity",
    "exit_track_record",
    "stage_expertise",
    "sector_expertise",
    "follow_on_rate",
    "network_quality",
]


async def _call_perplexity(messages: list[dict], timeout: int = 120) -> str:
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
                "max_tokens": 8000,
                "messages": messages,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _build_portfolio_prompt(investor: Investor) -> list[dict]:
    recent = ", ".join(investor.recent_investments or [])
    system_msg = (
        "You are a venture capital research analyst. Return structured, factual data about "
        "investors. Include numbers, dates, and specific company names. Return ONLY valid JSON."
    )
    user_msg = f"""Research the investment track record of {investor.partner_name} at {investor.firm_name}.

Known details:
- Stage focus: {investor.stage_focus or "Unknown"}
- Sector focus: {investor.sector_focus or "Unknown"}
- Location: {investor.location or "Unknown"}
- AUM/Fund size: {investor.aum_fund_size or "Unknown"}
- Recent investments: {recent or "Unknown"}

Return a JSON object with these fields:
{{
  "portfolio_companies": [
    {{"name": "Company Name", "stage_invested": "Seed/A/B", "year": 2023, "status": "active|acquired|ipo|defunct", "outcome_details": "acquired by X for $Y" or null}}
  ],
  "total_investments_count": number or null,
  "notable_exits": [
    {{"company": "Name", "exit_type": "acquisition|ipo", "exit_year": 2023, "return_multiple": "10x" or null, "acquirer_or_listing": "Google" or null}}
  ],
  "fund_details": {{
    "fund_size": "$100M" or null,
    "fund_vintage": "2020" or null,
    "fund_performance": "top quartile" or null
  }},
  "investment_pace": {{
    "deals_last_2_years": number or null,
    "deals_last_5_years": number or null,
    "avg_check_size": "$500K" or null
  }}
}}

Return ONLY the JSON object, no other text."""

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _build_network_prompt(investor: Investor) -> list[dict]:
    system_msg = (
        "You are a venture capital research analyst. Return structured, factual data about "
        "investors. Include numbers, dates, and specific names. Return ONLY valid JSON."
    )
    user_msg = f"""Research the co-investment network and follow-on patterns for {investor.partner_name} at {investor.firm_name}.

Return a JSON object with these fields:
{{
  "co_investors": [
    {{"firm": "Sequoia", "deals_together": 5, "tier": "top_tier|mid_tier|emerging"}}
  ],
  "follow_on_data": {{
    "companies_with_follow_on": number or null,
    "total_portfolio_size": number or null,
    "notable_follow_on_investors": ["Firm A", "Firm B"],
    "avg_time_to_next_round_months": number or null
  }},
  "stage_pattern": {{
    "primary_stage": "seed|series_a|series_b|growth",
    "stage_distribution": {{"pre_seed": 10, "seed": 50, "series_a": 30, "series_b": 10}}
  }},
  "sector_pattern": {{
    "primary_sectors": ["AI/ML", "Fintech"],
    "sector_distribution": {{"AI/ML": 40, "Fintech": 30, "SaaS": 20, "Other": 10}}
  }},
  "reputation_signals": {{
    "board_seats": number or null,
    "thought_leadership": "description or null",
    "notable_roles": "description or null"
  }}
}}

Return ONLY the JSON object, no other text."""

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _extract_json_object(text: str) -> dict:
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        return json.loads(m.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw = text[start : end + 1]
        raw = re.sub(r",\s*([}\]])", r"\1", raw)
        return json.loads(raw)

    raise ValueError("No JSON object found in response")


async def _get_internal_data(db: AsyncSession, investor: Investor) -> dict:
    firm_lower = investor.firm_name.lower()
    partner_lower = investor.partner_name.lower()

    result = await db.execute(
        select(StartupFundingRound, Startup)
        .join(Startup, StartupFundingRound.startup_id == Startup.id)
        .where(
            func.lower(StartupFundingRound.lead_investor).contains(firm_lower)
            | func.lower(StartupFundingRound.other_investors).contains(firm_lower)
            | func.lower(StartupFundingRound.lead_investor).contains(partner_lower)
            | func.lower(StartupFundingRound.other_investors).contains(partner_lower)
        )
    )
    rows = result.all()

    matched_startups = []
    lead_count = 0
    for funding_round, startup in rows:
        is_lead = funding_round.lead_investor and (
            firm_lower in funding_round.lead_investor.lower()
            or partner_lower in funding_round.lead_investor.lower()
        )
        if is_lead:
            lead_count += 1
        matched_startups.append({
            "name": startup.name,
            "stage": startup.stage.value if startup.stage else None,
            "ai_score": startup.ai_score,
            "company_status": startup.company_status.value if startup.company_status else None,
            "round_name": funding_round.round_name,
            "amount": funding_round.amount,
            "is_lead": is_lead,
        })

    statuses = [s["company_status"] for s in matched_startups]
    exits = statuses.count("acquired") + statuses.count("ipo")
    active = statuses.count("active")
    defunct = statuses.count("defunct")
    avg_ai_score = None
    scores = [s["ai_score"] for s in matched_startups if s["ai_score"] is not None]
    if scores:
        avg_ai_score = round(sum(scores) / len(scores), 1)

    source_count = len(investor.source_startups or [])

    return {
        "matched_funding_rounds": len(rows),
        "matched_startups": matched_startups,
        "lead_deals": lead_count,
        "exits_in_db": exits,
        "active_in_db": active,
        "defunct_in_db": defunct,
        "avg_ai_score_of_portfolio": avg_ai_score,
        "source_startups_count": source_count,
    }


SCORING_SYSTEM_PROMPT = """You are a venture capital analyst scoring investors across 7 dimensions.

Score each dimension from 0 to 100 based on the research data provided. Use these rubrics:

**Portfolio Performance (0-100):**
- Quality of portfolio companies (active vs defunct, known metrics)
- Funding trajectory (up-rounds, growing valuations)
- Weight toward recent investments (last 3 years)
- If internal DB data exists, factor in ai_scores and company_status

**Deal Activity (0-100):**
- Volume of investments (more = higher, diminishing returns above ~50/yr)
- Recency — heavily weight last 2 years
- Consistency — steady pace vs sporadic bursts

**Exit Track Record (0-100):**
- Number of exits (acquisitions + IPOs)
- Quality (IPO > major acquisition > acqui-hire)
- Known return multiples
- Exit rate as % of total portfolio

**Stage Expertise (0-100):**
- Concentration/depth at specific stages
- Track record at those stages
- Bonus for clear thesis/specialization

**Sector Expertise (0-100):**
- Concentration in specific verticals
- Track record within those verticals
- Domain signals (board seats, speaking, thought leadership)

**Follow-on Rate (0-100):**
- % of portfolio companies that raised subsequent rounds
- Quality of follow-on investors attracted
- Time between rounds (faster = stronger signal)

**Network / Co-investor Quality (0-100):**
- Quality tier of co-investors (top-tier VCs vs unknown angels)
- Diversity of co-investor network
- Repeat syndicate partnerships

For investors with limited data, score conservatively (40-60 range). Do not inflate scores.

Return ONLY a JSON object with this exact structure:
{
  "portfolio_performance": <int 0-100>,
  "deal_activity": <int 0-100>,
  "exit_track_record": <int 0-100>,
  "stage_expertise": <int 0-100>,
  "sector_expertise": <int 0-100>,
  "follow_on_rate": <int 0-100>,
  "network_quality": <int 0-100>,
  "narrative": "<2-3 paragraph analyst note about this investor's strengths, weaknesses, and notable deals. Professional tone, data-grounded.>"
}"""


async def _score_with_claude(
    investor: Investor,
    portfolio_research: dict,
    network_research: dict,
    internal_data: dict,
) -> dict:
    if not settings.anthropic_api_key:
        raise RuntimeError("ACUTAL_ANTHROPIC_API_KEY is not configured")

    user_msg = f"""Score this investor:

**Investor:** {investor.partner_name} at {investor.firm_name}
**Stage Focus:** {investor.stage_focus or "Unknown"}
**Sector Focus:** {investor.sector_focus or "Unknown"}
**Location:** {investor.location or "Unknown"}
**AUM/Fund Size:** {investor.aum_fund_size or "Unknown"}

---

**Perplexity Research — Portfolio & Performance:**
{json.dumps(portfolio_research, indent=2, default=str)}

---

**Perplexity Research — Network & Follow-on:**
{json.dumps(network_research, indent=2, default=str)}

---

**Internal Database Matches:**
- Funding rounds matched: {internal_data['matched_funding_rounds']}
- Lead deals in our DB: {internal_data['lead_deals']}
- Exits in our DB: {internal_data['exits_in_db']}
- Active companies in our DB: {internal_data['active_in_db']}
- Defunct companies in our DB: {internal_data['defunct_in_db']}
- Avg AI score of portfolio companies: {internal_data['avg_ai_score_of_portfolio'] or 'N/A'}
- Source startups count: {internal_data['source_startups_count']}
- Matched startups detail: {json.dumps(internal_data['matched_startups'][:20], default=str)}

Score this investor now."""

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 4096,
                "system": SCORING_SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_msg}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["content"][0]["text"]
        return _extract_json_object(content)


async def _score_single_investor(db: AsyncSession, investor: Investor) -> InvestorRanking:
    portfolio_research = {}
    network_research = {}

    messages = _build_portfolio_prompt(investor)
    for attempt in range(2):
        try:
            raw = await _call_perplexity(messages)
            portfolio_research = _extract_json_object(raw)
            break
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == 0:
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": "Your response was not valid JSON. Return ONLY a JSON object, no other text.",
                })
            else:
                logger.warning(f"Portfolio research JSON parse failed for {investor.firm_name}: {e}")

    messages = _build_network_prompt(investor)
    for attempt in range(2):
        try:
            raw = await _call_perplexity(messages)
            network_research = _extract_json_object(raw)
            break
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == 0:
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": "Your response was not valid JSON. Return ONLY a JSON object, no other text.",
                })
            else:
                logger.warning(f"Network research JSON parse failed for {investor.firm_name}: {e}")

    internal_data = await _get_internal_data(db, investor)

    scores = await _score_with_claude(investor, portfolio_research, network_research, internal_data)

    dimension_scores = {}
    for dim in DIMENSION_NAMES:
        val = scores.get(dim, 50)
        if not isinstance(val, (int, float)):
            val = 50
        dimension_scores[dim] = max(0.0, min(100.0, float(val)))

    overall = round(sum(dimension_scores.values()) / len(DIMENSION_NAMES), 1)
    narrative = scores.get("narrative", "No narrative generated.")

    result = await db.execute(
        select(InvestorRanking).where(InvestorRanking.investor_id == investor.id)
    )
    existing = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing:
        existing.overall_score = overall
        existing.portfolio_performance = dimension_scores["portfolio_performance"]
        existing.deal_activity = dimension_scores["deal_activity"]
        existing.exit_track_record = dimension_scores["exit_track_record"]
        existing.stage_expertise = dimension_scores["stage_expertise"]
        existing.sector_expertise = dimension_scores["sector_expertise"]
        existing.follow_on_rate = dimension_scores["follow_on_rate"]
        existing.network_quality = dimension_scores["network_quality"]
        existing.narrative = narrative
        existing.perplexity_research = {
            "portfolio": portfolio_research,
            "network": network_research,
        }
        existing.scoring_metadata = {
            "internal_data": internal_data,
            "raw_scores": scores,
        }
        existing.scored_at = now
        existing.updated_at = now
        ranking = existing
    else:
        ranking = InvestorRanking(
            investor_id=investor.id,
            overall_score=overall,
            portfolio_performance=dimension_scores["portfolio_performance"],
            deal_activity=dimension_scores["deal_activity"],
            exit_track_record=dimension_scores["exit_track_record"],
            stage_expertise=dimension_scores["stage_expertise"],
            sector_expertise=dimension_scores["sector_expertise"],
            follow_on_rate=dimension_scores["follow_on_rate"],
            network_quality=dimension_scores["network_quality"],
            narrative=narrative,
            perplexity_research={
                "portfolio": portfolio_research,
                "network": network_research,
            },
            scoring_metadata={
                "internal_data": internal_data,
                "raw_scores": scores,
            },
            scored_at=now,
        )
        db.add(ranking)

    await db.commit()
    return ranking


async def run_ranking_batch(job_id: str) -> None:
    db_factory = async_session

    async with db_factory() as db:
        job = await db.get(InvestorRankingBatchJob, uuid.UUID(job_id))
        if not job:
            logger.error(f"Ranking batch job {job_id} not found")
            return
        job.status = BatchJobStatus.running.value
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # Prioritize unscored investors with emails (ready for verification/marketing)
    async with db_factory() as db:
        scored_ids_result = await db.execute(
            select(InvestorRanking.investor_id)
        )
        scored_ids = {row[0] for row in scored_ids_result.all()}

        result = await db.execute(
            select(Investor).order_by(
                # Unscored with email first, then unscored without, then already scored
                Investor.email.is_(None).asc(),
                Investor.firm_name.asc(),
                Investor.partner_name.asc(),
            )
        )
        all_investors = result.scalars().all()
        # Put unscored investors first
        unscored = [inv for inv in all_investors if inv.id not in scored_ids]
        scored = [inv for inv in all_investors if inv.id in scored_ids]
        ordered = unscored + scored
        investor_data = [
            {
                "id": inv.id,
                "firm_name": inv.firm_name,
                "partner_name": inv.partner_name,
            }
            for inv in ordered
        ]

    async with db_factory() as db:
        job = await db.get(InvestorRankingBatchJob, uuid.UUID(job_id))
        job.total_investors = len(investor_data)
        await db.commit()

    # Skip already-processed investors
    async with db_factory() as db:
        job = await db.get(InvestorRankingBatchJob, uuid.UUID(job_id))
        start_idx = job.processed_investors or 0
    investor_data = investor_data[start_idx:]

    api_sem = asyncio.Semaphore(CONCURRENCY)
    processed_count = start_idx
    scored_count = 0
    paused = False

    async def score_one(inv_data: dict, idx: int) -> None:
        nonlocal processed_count, scored_count, paused
        if paused:
            return

        scored = 0
        try:
            # API calls (Perplexity + Claude) — limited by api_sem
            async with api_sem:
                if paused:
                    return
                async with DB_SEMAPHORE:
                    async with db_factory() as db:
                        investor = await db.get(Investor, inv_data["id"])
                if not investor:
                    return
                # Do the expensive API work outside DB semaphore
                portfolio_research = {}
                network_research = {}
                messages = _build_portfolio_prompt(investor)
                for attempt in range(2):
                    try:
                        raw = await _call_perplexity(messages)
                        portfolio_research = _extract_json_object(raw)
                        break
                    except (json.JSONDecodeError, ValueError) as e:
                        if attempt == 0:
                            messages.append({"role": "assistant", "content": raw})
                            messages.append({"role": "user", "content": "Your response was not valid JSON. Return ONLY a JSON object, no other text."})
                        else:
                            logger.warning(f"Portfolio research JSON parse failed for {inv_data['firm_name']}: {e}")

                messages = _build_network_prompt(investor)
                for attempt in range(2):
                    try:
                        raw = await _call_perplexity(messages)
                        network_research = _extract_json_object(raw)
                        break
                    except (json.JSONDecodeError, ValueError) as e:
                        if attempt == 0:
                            messages.append({"role": "assistant", "content": raw})
                            messages.append({"role": "user", "content": "Your response was not valid JSON. Return ONLY a JSON object, no other text."})
                        else:
                            logger.warning(f"Network research JSON parse failed for {inv_data['firm_name']}: {e}")

                # Score with Claude
                async with DB_SEMAPHORE:
                    async with db_factory() as db:
                        investor = await db.get(Investor, inv_data["id"])
                        internal_data = await _get_internal_data(db, investor)

                scores = await _score_with_claude(investor, portfolio_research, network_research, internal_data)

                # Save to DB
                dimension_scores = {}
                for dim in DIMENSION_NAMES:
                    val = scores.get(dim, 50)
                    if not isinstance(val, (int, float)):
                        val = 50
                    dimension_scores[dim] = max(0.0, min(100.0, float(val)))
                overall = round(sum(dimension_scores.values()) / len(DIMENSION_NAMES), 1)
                narrative = scores.get("narrative", "No narrative generated.")

                async with DB_SEMAPHORE:
                    async with db_factory() as db:
                        investor = await db.get(Investor, inv_data["id"])
                        result = await db.execute(
                            select(InvestorRanking).where(InvestorRanking.investor_id == investor.id)
                        )
                        existing = result.scalar_one_or_none()
                        now = datetime.now(timezone.utc)
                        if existing:
                            existing.overall_score = overall
                            for dim in DIMENSION_NAMES:
                                setattr(existing, dim, dimension_scores[dim])
                            existing.narrative = narrative
                            existing.perplexity_research = {"portfolio": portfolio_research, "network": network_research}
                            existing.scoring_metadata = {"internal_data": internal_data, "raw_scores": scores}
                            existing.scored_at = now
                            existing.updated_at = now
                        else:
                            ranking = InvestorRanking(
                                investor_id=investor.id,
                                overall_score=overall,
                                narrative=narrative,
                                perplexity_research={"portfolio": portfolio_research, "network": network_research},
                                scoring_metadata={"internal_data": internal_data, "raw_scores": scores},
                                scored_at=now,
                                **dimension_scores,
                            )
                            db.add(ranking)
                        await db.commit()
                scored = 1
        except Exception as e:
            logger.error(f"Failed scoring {inv_data['firm_name']}: {e}")
            async with DB_SEMAPHORE:
                async with db_factory() as db:
                    job = await db.get(InvestorRankingBatchJob, uuid.UUID(job_id))
                    errors = job.error or ""
                    job.error = f"{errors}\n{inv_data['firm_name']}: {e}".strip()
                    await db.commit()

        processed_count += 1
        scored_count += scored
        logger.info(f"Scored {processed_count}/{start_idx + len(investor_data)}: {inv_data['firm_name']} ({inv_data['partner_name']})")

    # Process in batches of CONCURRENCY
    for batch_start in range(0, len(investor_data), CONCURRENCY):
        # Check for pause
        async with DB_SEMAPHORE:
            async with db_factory() as db:
                job = await db.get(InvestorRankingBatchJob, uuid.UUID(job_id))
                if job.status == BatchJobStatus.paused.value:
                    logger.info(f"Ranking batch {job_id} paused at {processed_count}")
                    paused = True
                    return

        batch = investor_data[batch_start:batch_start + CONCURRENCY]
        tasks = [score_one(inv_data, start_idx + batch_start + i) for i, inv_data in enumerate(batch)]
        await asyncio.gather(*tasks)

        # Update job progress
        async with DB_SEMAPHORE:
            async with db_factory() as db:
                job = await db.get(InvestorRankingBatchJob, uuid.UUID(job_id))
                job.processed_investors = processed_count
                job.investors_scored = (job.investors_scored or 0) + scored_count
                scored_count = 0  # reset for next batch
                job.current_investor_name = f"Batch {batch_start + CONCURRENCY}/{len(investor_data)}"
                await db.commit()

    async with DB_SEMAPHORE:
        async with db_factory() as db:
            job = await db.get(InvestorRankingBatchJob, uuid.UUID(job_id))
            job.status = BatchJobStatus.completed.value
            job.current_investor_id = None
            job.current_investor_name = None
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

    logger.info(f"Ranking batch {job_id} complete")


async def rescore_single(investor_id: str) -> InvestorRanking:
    async with async_session() as db:
        investor = await db.get(Investor, uuid.UUID(investor_id))
        if not investor:
            raise ValueError(f"Investor {investor_id} not found")
        return await _score_single_investor(db, investor)
