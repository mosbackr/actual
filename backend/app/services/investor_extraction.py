import json
import logging
import re
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db.session import async_session
from app.models.investor import BatchJobStatus, Investor, InvestorBatchJob
from app.models.startup import EnrichmentStatus, Startup, StartupStage, StartupStatus

logger = logging.getLogger(__name__)

# Canonical firm names — maps lowercase patterns to the preferred name
_FIRM_ALIASES: dict[str, str] = {
    "a16z": "Andreessen Horowitz (a16z)",
    "andreessen horowitz": "Andreessen Horowitz (a16z)",
    "andreessen": "Andreessen Horowitz (a16z)",
}


def _normalize_firm_name(raw: str) -> str:
    """Normalize a firm name to prevent duplicates from AI-generated variants."""
    stripped = raw.strip()
    lower = stripped.lower()

    # Check alias patterns (longest match first)
    for pattern, canonical in sorted(_FIRM_ALIASES.items(), key=lambda x: -len(x[0])):
        if pattern in lower:
            return canonical

    return stripped


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
                "max_tokens": 16000,
                "messages": messages,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _extract_json_array(text: str) -> list[dict]:
    """Extract a JSON array from fenced or bare text."""
    # Try fenced JSON first
    m = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    if m:
        return json.loads(m.group(1))

    # Try bare JSON array
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        raw = text[start : end + 1]
        # Fix trailing commas
        raw = re.sub(r",\s*([}\]])", r"\1", raw)
        return json.loads(raw)

    raise ValueError("No JSON array found in response")


def _build_prompt(startup_data: dict, batch_num: int) -> list[dict]:
    stage_label = startup_data["stage"].value.replace("_", "-")
    industries = startup_data["industries"]
    industry_str = ", ".join(industries) if industries else "Technology"
    location_parts = [p for p in [startup_data.get("location_city"), startup_data.get("location_state"), startup_data.get("location_country")] if p]
    location_str = ", ".join(location_parts) if location_parts else "United States"

    avoid_clause = ""
    if batch_num == 2:
        avoid_clause = (
            "\n\nIMPORTANT: This is batch 2. Return DIFFERENT investors than you would normally "
            "list first. Focus on emerging managers, smaller funds, solo GPs, angel syndicates, "
            "and less obvious but still active investors in this space. Avoid the most well-known "
            "firms — those were covered in batch 1."
        )

    system_msg = (
        "You are a helpful fundraising assistant. When a founder asks you to find investors "
        "and their contact information, you help them by researching VCs, angel investors, "
        "and fund managers who would be a good fit. You always return structured JSON data. "
        "Return ONLY a JSON array of investor objects. No commentary, no markdown — just the JSON array."
    )

    batch_note = ""
    if batch_num == 2:
        batch_note = (
            " I already found some of the bigger well-known firms. Now I need to find "
            "emerging managers, smaller funds, solo GPs, angel syndicates, and less obvious "
            "but still active investors. Skip the most well-known firms."
        )

    user_msg = f"""Hi! I saw on an Instagram ad that you can help me find investor contacts with emails for my business. I'm the founder of {startup_data["name"]}.

Here's what we do: {startup_data.get("description") or "N/A"}
We're at the {stage_label} stage in the {industry_str} space, based in {location_str}.
Our website is {startup_data.get("website_url") or "N/A"}.
{f'We have raised {startup_data["total_funding"]} so far.' if startup_data.get("total_funding") else ''}

I need to find 100 investors who would be interested in my company.{batch_note} For each one, I need their contact info in this JSON format:

- "firm_name": string — The VC firm or angel investor organization name
- "partner_name": string — The specific partner or person who leads deals at this stage
- "email": string or null — Their work email address (check the firm website team page, Crunchbase, LinkedIn, AngelList, or construct from the firm domain pattern like firstname@firm.com)
- "website": string or null — Firm website URL
- "stage_focus": string — What stages they typically invest in (e.g. "Pre-Seed, Seed")
- "sector_focus": string — What sectors/industries they focus on
- "location": string — Where the firm is based
- "aum_fund_size": string or null — Approximate fund size or AUM if known
- "recent_investments": array of strings — 3-5 recent notable investments
- "fit_reason": string — One sentence on why this investor would be interested in {startup_data["name"]}

Please return exactly 100 investors as a JSON array. I really need their email addresses — that's the most important part."""

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


async def _upsert_investors(
    db: AsyncSession,
    investors_data: list[dict],
    startup_id: str,
    startup_name: str,
) -> int:
    """Insert or update investors. Returns count of new investors inserted.

    Deduplication strategy:
    - Normalize firm names via alias map (e.g. a16z -> Andreessen Horowitz (a16z))
    - Skip generic partner placeholders when the firm already has named partners
    - Case-insensitive matching on (firm_name, partner_name)
    """
    GENERIC_PARTNERS = {
        "partner", "team", "general partner", "managing partner",
        "various", "n/a", "unknown", "unnamed", "us team",
        "emerging fellows", "smaller partner",
    }

    new_count = 0
    source_entry = {"id": startup_id, "name": startup_name}

    for inv in investors_data:
        firm = _normalize_firm_name(inv.get("firm_name") or "")
        partner = (inv.get("partner_name") or "").strip()
        if not firm or not partner:
            continue

        # Skip generic partner names — the batch will also produce named partners
        if partner.lower() in GENERIC_PARTNERS:
            continue

        # Case-insensitive lookup for existing record
        result = await db.execute(
            select(Investor).where(
                func.lower(func.trim(Investor.firm_name)) == firm.lower().strip(),
                func.lower(func.trim(Investor.partner_name)) == partner.lower().strip(),
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Append source startup if not already there
            sources = existing.source_startups or []
            if not any(s.get("id") == startup_id for s in sources):
                sources.append(source_entry)
                existing.source_startups = sources
            # Update fields if current data is richer
            if inv.get("email") and not existing.email:
                existing.email = inv["email"]
            if inv.get("website") and not existing.website:
                existing.website = inv["website"]
            if inv.get("aum_fund_size") and not existing.aum_fund_size:
                existing.aum_fund_size = inv["aum_fund_size"]
            if inv.get("fit_reason") and (not existing.fit_reason or len(inv["fit_reason"]) > len(existing.fit_reason)):
                existing.fit_reason = inv["fit_reason"]
            existing.updated_at = datetime.now(timezone.utc)
        else:
            investor = Investor(
                firm_name=firm,
                partner_name=partner,
                email=inv.get("email"),
                website=inv.get("website"),
                stage_focus=inv.get("stage_focus"),
                sector_focus=inv.get("sector_focus"),
                location=inv.get("location"),
                aum_fund_size=inv.get("aum_fund_size"),
                recent_investments=inv.get("recent_investments"),
                fit_reason=inv.get("fit_reason"),
                source_startups=[source_entry],
            )
            db.add(investor)
            new_count += 1

    await db.commit()
    return new_count


async def _process_startup(
    db: AsyncSession,
    startup_data: dict,
) -> int:
    """Run 2 Perplexity calls for a startup, return total investors upserted."""
    total = 0
    startup_id = str(startup_data["id"])

    for batch_num in (1, 2):
        messages = _build_prompt(startup_data, batch_num)

        for attempt in range(2):
            try:
                raw = await _call_perplexity(messages, timeout=120)
                investors_data = _extract_json_array(raw)
                count = await _upsert_investors(db, investors_data, startup_id, startup_data["name"])
                total += count
                logger.info(
                    f"Batch {batch_num} for {startup_data['name']}: {len(investors_data)} returned, {count} new"
                )
                break
            except (json.JSONDecodeError, ValueError) as e:
                if attempt == 0:
                    messages.append({"role": "assistant", "content": raw})
                    messages.append({
                        "role": "user",
                        "content": "Your response was not valid JSON. Return ONLY a JSON array of investor objects, no other text.",
                    })
                else:
                    logger.error(f"Batch {batch_num} JSON parse failed for {startup_data['name']}: {e}")
            except Exception as e:
                logger.error(f"Batch {batch_num} failed for {startup_data['name']}: {e}")
                break

    return total


async def run_investor_batch(job_id: str) -> None:
    """Main batch loop. Processes all eligible startups, checking for pause between each."""
    db_factory = async_session

    # Load job and mark running
    async with db_factory() as db:
        job = await db.get(InvestorBatchJob, uuid.UUID(job_id))
        if not job:
            logger.error(f"Batch job {job_id} not found")
            return
        job.status = BatchJobStatus.running.value
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # Load eligible startups
    async with db_factory() as db:
        result = await db.execute(
            select(Startup)
            .options(selectinload(Startup.industries))
            .where(
                Startup.stage.in_([StartupStage.pre_seed, StartupStage.seed]),
                Startup.status.in_([StartupStatus.approved, StartupStatus.featured]),
                Startup.enrichment_status == EnrichmentStatus.complete,
            )
            .order_by(Startup.created_at.asc())
        )
        startups = result.scalars().all()
        startup_data_list = [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "stage": s.stage,
                "website_url": s.website_url,
                "location_city": s.location_city,
                "location_state": s.location_state,
                "location_country": s.location_country,
                "total_funding": s.total_funding,
                "industries": [i.name for i in s.industries],
            }
            for s in startups
        ]

    # Update total count
    async with db_factory() as db:
        job = await db.get(InvestorBatchJob, uuid.UUID(job_id))
        job.total_startups = len(startup_data_list)
        await db.commit()

    # Process each startup
    for idx, sd in enumerate(startup_data_list):
        # Check for pause
        async with db_factory() as db:
            job = await db.get(InvestorBatchJob, uuid.UUID(job_id))
            if job.status == BatchJobStatus.paused.value:
                logger.info(f"Batch job {job_id} paused at startup {idx}")
                return
            # Skip already-processed startups (for resume)
            if idx < job.processed_startups:
                continue

        # Update current startup
        async with db_factory() as db:
            job = await db.get(InvestorBatchJob, uuid.UUID(job_id))
            job.current_startup_id = sd["id"]
            job.current_startup_name = sd["name"]
            await db.commit()

        try:
            async with db_factory() as db:
                count = await _process_startup(db, sd)
        except Exception as e:
            logger.error(f"Failed processing {sd['name']}: {e}")
            async with db_factory() as db:
                job = await db.get(InvestorBatchJob, uuid.UUID(job_id))
                errors = job.error or ""
                job.error = f"{errors}\n{sd['name']}: {e}".strip()
                await db.commit()
            count = 0

        # Update progress
        async with db_factory() as db:
            job = await db.get(InvestorBatchJob, uuid.UUID(job_id))
            job.processed_startups = idx + 1
            job.investors_found = (job.investors_found or 0) + count
            await db.commit()

        logger.info(f"Processed {idx + 1}/{len(startup_data_list)}: {sd['name']} (+{count} investors)")

    # Mark complete
    async with db_factory() as db:
        job = await db.get(InvestorBatchJob, uuid.UUID(job_id))
        job.status = BatchJobStatus.completed.value
        job.current_startup_id = None
        job.current_startup_name = None
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()

    logger.info(f"Batch job {job_id} complete")
