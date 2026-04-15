"""Shared scout logic: Perplexity API calls, response parsing, startup creation with dedup."""
import json
import re
import uuid
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.startup import EntityType, Startup, StartupStage, StartupStatus
from app.services.dedup import find_duplicate, normalize_domain, normalize_name


SCOUT_SYSTEM_PROMPT = """You are a startup research assistant for Acutal, a startup investment intelligence platform.

When the user asks you to find startups, search the web thoroughly and return your findings.

IMPORTANT: You MUST include a JSON block in your response with structured startup data. Format it exactly like this, wrapped in ```json code fences:

```json
[
  {
    "name": "Company Name",
    "website_url": "https://example.com",
    "description": "2-3 sentence description of what the company does, their product, and their market.",
    "stage": "seed",
    "location_city": "San Francisco",
    "location_state": "CA",
    "location_country": "US",
    "founders": "Founder Name 1, Founder Name 2",
    "funding_raised": "$10M",
    "key_investors": "Sequoia, Y Combinator",
    "linkedin_url": "https://linkedin.com/company/example",
    "founded_year": "2023"
  }
]
```

Rules:
- stage must be one of: pre_seed, seed, series_a, series_b, series_c, growth, public
- Use "public" for any publicly traded or post-IPO company. Use "growth" for late-stage private companies.
- CRITICAL: For EVERY company, you MUST research and include: website_url, founders (full names), \
funding_raised (total amount), location_city, location_state, key_investors, and founded_year. \
Search each company individually if needed. Empty fields are not acceptable when the information \
is publicly available.
- Be thorough in descriptions — include what the product does, their market, traction, and why they're notable
- If a field truly cannot be found after searching, use empty string
- Return as many startups as you can find that match the query
- After the JSON block, include a brief summary of what you found

When the user asks follow-up questions or wants to refine, update your search accordingly."""


class StartupCandidate(BaseModel):
    name: str
    website_url: str | None = None
    description: str = ""
    stage: str = "seed"
    location_city: str | None = None
    location_state: str | None = None
    location_country: str = "US"
    founders: str | None = None
    funding_raised: str | None = None
    key_investors: str | None = None
    linkedin_url: str | None = None
    founded_year: str | None = None


def extract_startups_from_response(text: str) -> list[dict]:
    """Extract structured startup data from Perplexity's response."""
    json_match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    array_match = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
    if array_match:
        try:
            data = json.loads(array_match.group(0))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    return []


def clean_reply(text: str) -> str:
    """Remove the JSON block from the reply text for display."""
    cleaned = re.sub(r"```json\s*\n.*?\n\s*```", "", text, flags=re.DOTALL)
    return cleaned.strip()


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug


async def call_perplexity(
    system_prompt: str, user_message: str, max_tokens: int = 16384
) -> dict | None:
    """Call Perplexity Sonar Pro API with retry logic.

    Returns the full API response dict on success, None on failure.
    """
    if not settings.perplexity_api_key:
        return None

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    last_error = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.perplexity_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "sonar-pro",
                        "messages": messages,
                        "temperature": 0.1,
                        "max_tokens": max_tokens,
                    },
                )
                if resp.status_code == 200:
                    return resp.json()
                last_error = f"Perplexity API error ({resp.status_code}): {resp.text[:200]}"
                if resp.status_code < 500:
                    break
        except httpx.TimeoutException:
            last_error = "Perplexity API timed out"
        except Exception as e:
            last_error = str(e)

    return None


async def add_startups_to_triage(
    db: AsyncSession, candidates: list[StartupCandidate]
) -> dict:
    """Add startup candidates to the database with dedup.

    Returns {"created": [...], "skipped": [...]}.
    """
    created = []
    skipped = []

    for candidate in candidates:
        dup = await find_duplicate(db, candidate.name, candidate.website_url)
        if dup is not None:
            skipped.append(candidate.name)
            continue

        slug = slugify(candidate.name)
        slug_check = await db.execute(select(Startup).where(Startup.slug == slug))
        if slug_check.scalar_one_or_none() is not None:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        stage = candidate.stage.lower().strip()
        valid_stages = [s.value for s in StartupStage]
        if stage not in valid_stages:
            # Map common AI-generated stage names to valid values
            stage_map = {
                "public": "public", "post_ipo": "public", "ipo": "public",
                "late": "growth", "late_stage": "growth", "mature": "growth",
                "pre-seed": "pre_seed", "preseed": "pre_seed",
                "series_d": "growth", "series_e": "growth", "series_f": "growth",
            }
            stage = stage_map.get(stage, "seed")

        startup = Startup(
            name=candidate.name,
            slug=slug,
            description=candidate.description or f"{candidate.name} startup",
            website_url=candidate.website_url,
            stage=StartupStage(stage),
            status=StartupStatus.pending,
            entity_type=EntityType.startup,
            location_city=candidate.location_city,
            location_state=candidate.location_state,
            location_country=candidate.location_country or "US",
        )
        db.add(startup)
        await db.flush()

        # Try to fetch logo
        if candidate.website_url and settings.logo_dev_token:
            try:
                parsed = urlparse(
                    candidate.website_url
                    if "://" in candidate.website_url
                    else f"https://{candidate.website_url}"
                )
                domain = parsed.hostname or ""
                domain = re.sub(r"^www\.", "", domain)
                if domain:
                    logo_url = f"https://img.logo.dev/{domain}?token={settings.logo_dev_token}&format=png&size=128"
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        logo_resp = await client.get(logo_url, follow_redirects=True)
                        if logo_resp.status_code == 200 and "image" in (
                            logo_resp.headers.get("content-type") or ""
                        ):
                            startup.logo_url = logo_url
            except Exception:
                pass

        created.append(
            {
                "id": str(startup.id),
                "name": startup.name,
                "slug": startup.slug,
                "status": startup.status.value,
            }
        )

    await db.commit()
    return {"created": created, "skipped": skipped}
