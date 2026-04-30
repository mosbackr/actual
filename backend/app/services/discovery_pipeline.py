import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import async_session
from app.models.discovery import DiscoveryBatchJob
from app.models.founder import StartupFounder
from app.models.investor import BatchJobStatus
from app.models.startup import ClassificationStatus, EnrichmentStatus, Startup, StartupStatus

logger = logging.getLogger(__name__)

CONCURRENCY = 10
DB_SEMAPHORE = asyncio.Semaphore(2)

# ── Heuristic Filter ────────────────────────────────────────────────────

NOT_STARTUP_PATTERNS = [
    r"\bholdings?\b",
    r"\bholding\s+co(mpany)?\b",
    r"\breal\s+estate\b",
    r"\brealty\b",
    r"\bpropert(y|ies)\b",
    r"\bproperty\s+management\b",
    r"\btrust(ee)?\b",
    r"\binsurance\b",
    r"\bassurance\b",
    r"\bbank(ing)?\b",
    r"\bchurch\b",
    r"\bministr(y|ies)\b",
    r"\btemple\b",
    r"\bmosque\b",
    r"\bfoundation\b(?!.*\b(ai|tech|data|software|digital)\b)",
    r"\bassociation\b",
    r"\bsociety\b",
    r"\bmortgage\b",
    r"\blending\b",
    r"\bconstruction\b",
    r"\bcontract(ing|ors?)\b",
    r"\brestaurant(s)?\b",
    r"\bfood\s+service\b",
    r"\bcapital\s+llc\b",
    r"\bcapital\s+lp\b",
    r"\bmanagement\s+co(mpany)?\b",
]

_NOT_STARTUP_RE = re.compile("|".join(NOT_STARTUP_PATTERNS), re.IGNORECASE)


def is_heuristic_not_startup(name: str) -> bool:
    """Return True if the name matches common non-startup patterns."""
    return bool(_NOT_STARTUP_RE.search(name))


# ── Scrapin.io ────────────────────────────────────────────────────────────

async def _scrapin_person_profile(linkedin_url: str) -> dict | None:
    """Fetch a person's LinkedIn profile via Scrapin.io."""
    if not settings.scrapin_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://api.scrapin.io/enrichment/profile",
                params={"apikey": settings.scrapin_api_key, "linkedInUrl": linkedin_url},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("success"):
                    return data.get("person")
    except Exception as e:
        logger.warning(f"Scrapin.io person profile failed for {linkedin_url}: {e}")
    return None


async def _search_founder_linkedin(company_name: str) -> list[str]:
    """Search Google/SerpAPI for founder LinkedIn URLs."""
    if not settings.serp_api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://serpapi.com/search",
                params={
                    "q": f'"{company_name}" founder OR CEO site:linkedin.com/in',
                    "api_key": settings.serp_api_key,
                    "num": 5,
                },
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            urls = []
            for result in data.get("organic_results", []):
                link = result.get("link", "")
                if "linkedin.com/in/" in link:
                    urls.append(link)
            return urls[:3]
    except Exception as e:
        logger.warning(f"SerpAPI search failed for {company_name}: {e}")
    return []


def _extract_work_history(profile: dict) -> list[dict]:
    """Extract structured work history from Scrapin.io profile."""
    positions = profile.get("positions") or {}
    history = positions.get("positionHistory") or []
    return [
        {
            "company": pos.get("companyName") or "",
            "title": pos.get("title") or "",
            "start_date": pos.get("startEndDate", {}).get("start", {}).get("month", "") if pos.get("startEndDate") else "",
            "end_date": pos.get("startEndDate", {}).get("end", {}).get("month", "") if pos.get("startEndDate") else "",
            "description": (pos.get("description") or "")[:500],
        }
        for pos in history[:10]
    ]


def _extract_education(profile: dict) -> list[dict]:
    """Extract structured education from Scrapin.io profile."""
    schools = profile.get("schools") or {}
    history = schools.get("educationHistory") or []
    return [
        {
            "school": edu.get("schoolName") or "",
            "degree": edu.get("degreeName") or "",
            "field": edu.get("fieldOfStudy") or "",
            "start_year": edu.get("startEndDate", {}).get("start", {}).get("year") if edu.get("startEndDate") else None,
            "end_year": edu.get("startEndDate", {}).get("end", {}).get("year") if edu.get("startEndDate") else None,
        }
        for edu in history[:5]
    ]


def _detect_brand_name(founder_profile: dict, corp_name: str) -> str | None:
    """If the founder's current company differs from corp name, return the brand name."""
    positions = founder_profile.get("positions") or {}
    history = positions.get("positionHistory") or []
    if not history:
        return None
    current = history[0]
    end_date = current.get("startEndDate", {}).get("end") if current.get("startEndDate") else None
    if not end_date:  # currently employed (no end date)
        company = current.get("companyName", "")
        if company and company.lower().strip() != corp_name.lower().strip():
            return company
    return None


async def _enrich_founders(db: AsyncSession, startup: Startup) -> list[StartupFounder]:
    """Find and enrich founders for a startup via Scrapin.io + SerpAPI."""
    corp_name = startup.delaware_corp_name or startup.name
    brand_name = startup.name if startup.name != corp_name else None
    search_name = brand_name or corp_name

    # Find founder LinkedIn URLs via SerpAPI
    linkedin_urls = await _search_founder_linkedin(search_name)
    if not linkedin_urls and brand_name:
        linkedin_urls.extend(await _search_founder_linkedin(corp_name))

    # Deduplicate URLs
    seen = set()
    unique_urls = []
    for url in linkedin_urls:
        normalized = url.rstrip("/").lower()
        if normalized not in seen:
            seen.add(normalized)
            unique_urls.append(url)

    founders: list[StartupFounder] = []

    for url in unique_urls[:3]:
        profile = await _scrapin_person_profile(url)
        if not profile:
            continue

        full_name = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
        if not full_name:
            continue

        # Check for brand name mismatch
        detected_brand = _detect_brand_name(profile, corp_name)
        if detected_brand and not brand_name:
            startup.name = detected_brand
            startup.slug = re.sub(r"[^a-z0-9]+", "-", detected_brand.lower()).strip("-") + "-" + uuid.uuid4().hex[:6]

        work_history = _extract_work_history(profile)
        education_history = _extract_education(profile)

        founder = StartupFounder(
            startup_id=startup.id,
            name=full_name,
            title=profile.get("headline", "").split(" at ")[0] if profile.get("headline") else None,
            linkedin_url=url,
            is_founder=True,
            headline=profile.get("headline"),
            location=profile.get("location"),
            profile_photo_url=profile.get("photoUrl"),
            work_history=work_history,
            education_history=education_history,
            proxycurl_raw=profile,
        )
        db.add(founder)
        founders.append(founder)

    return founders


# ── Claude Classification ────────────────────────────────────────────────

CLASSIFICATION_PROMPT = """You are a venture capital analyst. Given a Delaware corporate filing and founder LinkedIn data, determine if this is a venture-backable technology startup.

Classify as one of:
- "startup" — This is a venture-backable technology startup
- "not_startup" — This is a traditional business, holding company, consulting firm, or non-tech entity
- "uncertain" — Not enough signal to determine

Signals that indicate STARTUP:
- Founders with tech company backgrounds (FAANG, startups, tech firms)
- CS/engineering/PhD education
- Prior startup founding experience
- Tech-sounding company name or product focus
- Location in tech hubs (but not determinative)
- Multiple technical co-founders

Signals that indicate NOT A STARTUP:
- Founders with backgrounds in law, real estate, insurance, traditional finance
- Company name suggests traditional business (consulting, services, management)
- Single founder with no tech background
- No clear technology product or innovation

Return ONLY a JSON object:
{
  "classification": "startup" | "not_startup" | "uncertain",
  "confidence": 0.0-1.0,
  "reasoning": "One paragraph explaining your decision"
}"""


async def _classify_with_claude(startup: Startup, founders: list[StartupFounder]) -> dict:
    """Use Claude to classify whether this is a real startup."""
    founder_descriptions = []
    for f in founders:
        desc = f"**{f.name}** — {f.headline or 'No headline'}\n"
        if f.location:
            desc += f"Location: {f.location}\n"
        if f.work_history:
            desc += "Recent work:\n"
            for job in (f.work_history or [])[:3]:
                desc += f"  - {job.get('title', '?')} at {job.get('company', '?')}\n"
        if f.education_history:
            desc += "Education:\n"
            for edu in (f.education_history or [])[:2]:
                desc += f"  - {edu.get('degree', '?')} in {edu.get('field', '?')} from {edu.get('school', '?')}\n"
        founder_descriptions.append(desc)

    user_msg = f"""Delaware Corporate Filing:
- Corp Name: {startup.delaware_corp_name or startup.name}
- Brand Name: {startup.name if startup.name != startup.delaware_corp_name else "Same as corp name"}
- Filed Date: {startup.delaware_filed_at or "Unknown"}

{"Founders found:" if founder_descriptions else "No founder data found."}
{"---".join(founder_descriptions) if founder_descriptions else ""}

Classify this entity."""

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "temperature": 0.1,
                "system": CLASSIFICATION_PROMPT,
                "messages": [{"role": "user", "content": user_msg}],
            },
        )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"]

    # Parse JSON from response
    try:
        # Try fenced JSON
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
        if m:
            return json.loads(m.group(1))
        # Try bare JSON
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            return json.loads(content[start:end + 1])
    except json.JSONDecodeError:
        pass

    return {"classification": "uncertain", "confidence": 0.0, "reasoning": f"Failed to parse: {content[:200]}"}


# ── Perplexity Enrichment ────────────────────────────────────────────────

async def _enrich_with_perplexity(startup: Startup, founders: list[StartupFounder]) -> dict:
    """Use Perplexity to research the startup and populate enrichment fields."""
    founder_names = ", ".join(f.name for f in founders) if founders else "Unknown"
    company_name = startup.name

    messages = [
        {
            "role": "system",
            "content": (
                "You are a startup research analyst. Given a company name and its founders, research the company and return structured data. "
                "Return ONLY a JSON object with these fields. Use null for unknown values."
            ),
        },
        {
            "role": "user",
            "content": f"""Research this startup:
Company: {company_name}
Founders: {founder_names}
Delaware filing name: {startup.delaware_corp_name or company_name}
Filed: {startup.delaware_filed_at or "Unknown"}

Return a JSON object with:
- "description": string — What the company does (2-3 sentences)
- "tagline": string or null — One-line pitch
- "website_url": string or null — Company website
- "linkedin_url": string or null — Company LinkedIn page
- "twitter_url": string or null — Company Twitter/X
- "crunchbase_url": string or null — Crunchbase profile
- "stage": "pre_seed" | "seed" | "series_a" | "series_b" | "series_c" | "growth" — Best guess at current stage
- "total_funding": string or null — e.g. "$2.5M"
- "employee_count": string or null — e.g. "5-10"
- "industries": array of strings — e.g. ["AI", "Healthcare"]
- "location_city": string or null
- "location_state": string or null
- "location_country": string — Default "US"
- "business_model": string or null — e.g. "B2B SaaS"
- "competitors": string or null — Comma-separated competitor names
- "hiring_signals": string or null — Any hiring activity""",
        },
    ]

    async with httpx.AsyncClient(timeout=120) as client:
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
        content = resp.json()["choices"][0]["message"]["content"]

    # Parse JSON
    try:
        m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
        if m:
            return json.loads(m.group(1))
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            raw = content[start:end + 1]
            raw = re.sub(r",\s*([}\]])", r"\1", raw)
            return json.loads(raw)
    except json.JSONDecodeError:
        pass

    return {}


def _apply_enrichment(startup: Startup, data: dict) -> None:
    """Apply Perplexity enrichment data to startup fields."""
    if data.get("description"):
        startup.description = data["description"]
    if data.get("tagline"):
        startup.tagline = data["tagline"]
    if data.get("website_url"):
        startup.website_url = data["website_url"]
    if data.get("linkedin_url"):
        startup.linkedin_url = data["linkedin_url"]
    if data.get("twitter_url"):
        startup.twitter_url = data["twitter_url"]
    if data.get("crunchbase_url"):
        startup.crunchbase_url = data["crunchbase_url"]
    if data.get("total_funding"):
        startup.total_funding = data["total_funding"]
    if data.get("employee_count"):
        startup.employee_count = data["employee_count"]
    if data.get("location_city"):
        startup.location_city = data["location_city"]
    if data.get("location_state"):
        startup.location_state = data["location_state"]
    if data.get("location_country"):
        startup.location_country = data["location_country"]
    if data.get("business_model"):
        startup.business_model = data["business_model"]
    if data.get("competitors"):
        startup.competitors = data["competitors"]
    if data.get("hiring_signals"):
        startup.hiring_signals = data["hiring_signals"]

    # Map stage string to enum if valid
    stage_str = data.get("stage")
    if stage_str:
        from app.models.startup import StartupStage
        try:
            startup.stage = StartupStage(stage_str)
        except ValueError:
            pass

    startup.enrichment_status = EnrichmentStatus.complete
    startup.enriched_at = datetime.now(timezone.utc)


# ── Main Pipeline ────────────────────────────────────────────────────────

async def _process_single_startup(startup_id: uuid.UUID) -> str:
    """Process a single startup through the full pipeline. Returns status string."""
    async with DB_SEMAPHORE:
        async with async_session() as db:
            startup = await db.get(Startup, startup_id)
            if not startup:
                return "not_found"

            name = startup.delaware_corp_name or startup.name

            # Step 1: Heuristic filter
            if is_heuristic_not_startup(name):
                startup.classification_status = ClassificationStatus.not_startup
                startup.classification_metadata = {"method": "heuristic", "pattern_matched": True}
                await db.commit()
                return "filtered"

            # Step 2: Founder discovery + enrichment
            founders = await _enrich_founders(db, startup)
            await db.commit()

            # Step 3: Claude classification
            try:
                classification = await _classify_with_claude(startup, founders)
                status_str = classification.get("classification", "uncertain")
                try:
                    startup.classification_status = ClassificationStatus(status_str)
                except ValueError:
                    startup.classification_status = ClassificationStatus.uncertain
                startup.classification_metadata = classification
                await db.commit()
            except Exception as e:
                logger.error(f"Classification failed for {name}: {e}")
                startup.classification_status = ClassificationStatus.uncertain
                startup.classification_metadata = {"error": str(e)}
                await db.commit()
                return "classification_error"

            # Step 4: Perplexity enrichment (only for startups)
            if startup.classification_status == ClassificationStatus.startup:
                try:
                    enrichment_data = await _enrich_with_perplexity(startup, founders)
                    _apply_enrichment(startup, enrichment_data)
                    startup.data_sources = {**(startup.data_sources or {}), "perplexity_discovery": True}
                    await db.commit()
                except Exception as e:
                    logger.error(f"Perplexity enrichment failed for {name}: {e}")
                    startup.enrichment_status = EnrichmentStatus.failed
                    startup.enrichment_error = str(e)
                    await db.commit()
                    return "enrichment_error"

            return startup.classification_status.value


async def run_discovery_pipeline(job_id: str) -> None:
    """Main batch loop. Process all unclassified discovered startups."""
    db_factory = async_session

    # Mark job running
    async with db_factory() as db:
        job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
        if not job:
            logger.error(f"Discovery job {job_id} not found")
            return
        job.status = BatchJobStatus.running.value
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # Load unclassified discovered startups
    async with db_factory() as db:
        result = await db.execute(
            select(Startup.id, Startup.name)
            .where(
                Startup.status == StartupStatus.discovered,
                Startup.classification_status == ClassificationStatus.unclassified,
            )
            .order_by(Startup.delaware_filed_at.desc().nullslast())
        )
        startup_rows = result.all()

    # Update total
    async with db_factory() as db:
        job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
        if job:
            job.total_items = len(startup_rows)
            await db.commit()

    processed = 0
    created = 0
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def _worker(startup_id: uuid.UUID, startup_name: str, index: int):
        nonlocal processed, created
        async with semaphore:
            # Check for pause
            async with db_factory() as db:
                job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
                if job and job.status == BatchJobStatus.paused.value:
                    return

            try:
                result = await _process_single_startup(startup_id)
                if result == "startup":
                    created += 1
            except Exception as e:
                logger.error(f"Pipeline failed for {startup_name}: {e}")
                async with db_factory() as db:
                    job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
                    if job:
                        errors = job.error or ""
                        job.error = f"{errors}\n{startup_name}: {e}".strip()
                        await db.commit()

            processed += 1

            # Update progress
            async with db_factory() as db:
                job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
                if job:
                    job.processed_items = processed
                    job.items_created = created
                    job.current_item_name = startup_name
                    await db.commit()

    # Process in batches
    batch_size = CONCURRENCY
    for i in range(0, len(startup_rows), batch_size):
        # Check for pause before each batch
        async with db_factory() as db:
            job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
            if job and job.status == BatchJobStatus.paused.value:
                logger.info(f"Discovery job {job_id} paused")
                return

        batch = startup_rows[i:i + batch_size]
        tasks = [_worker(row[0], row[1], i + j) for j, row in enumerate(batch)]
        await asyncio.gather(*tasks)

    # Mark complete
    async with db_factory() as db:
        job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
        if job:
            job.status = BatchJobStatus.completed.value
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

    logger.info(f"Discovery pipeline job {job_id} complete: {created} startups identified out of {processed} processed")
