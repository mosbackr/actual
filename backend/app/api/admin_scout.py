import json
import re
import uuid
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.config import settings
from app.db.session import get_db
from app.models.industry import Industry
from app.models.startup import Startup, StartupStage, StartupStatus
from app.models.user import User
from app.services.dedup import normalize_name, normalize_domain

router = APIRouter()

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
- stage must be one of: pre_seed, seed, series_a, series_b, series_c, growth
- Always include website_url if you can find it
- Be thorough in descriptions — include what the product does, the market, and why it's notable
- If you can't find certain fields, omit them rather than guessing
- Return as many startups as you can find that match the query
- After the JSON block, include a brief summary of what you found

When the user asks follow-up questions or wants to refine, update your search accordingly."""


class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ScoutChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


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


class ScoutAddRequest(BaseModel):
    startups: list[StartupCandidate]


def _extract_startups_from_response(text: str) -> list[dict]:
    """Extract structured startup data from Perplexity's response."""
    # Look for JSON code blocks
    json_match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    # Fallback: look for any JSON array in the response
    array_match = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
    if array_match:
        try:
            data = json.loads(array_match.group(0))
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass

    return []


def _clean_reply(text: str) -> str:
    """Remove the JSON block from the reply text for display."""
    cleaned = re.sub(r"```json\s*\n.*?\n\s*```", "", text, flags=re.DOTALL)
    return cleaned.strip()


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug


@router.post("/api/admin/scout/chat")
async def scout_chat(
    body: ScoutChatRequest,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    if not settings.perplexity_api_key:
        raise HTTPException(status_code=500, detail="ACUTAL_PERPLEXITY_API_KEY not configured")

    # Build messages for Perplexity — no history, each request is standalone
    messages = [
        {"role": "system", "content": SCOUT_SYSTEM_PROMPT},
        {"role": "user", "content": body.message},
    ]

    # Call Perplexity Sonar Pro with retry
    last_error = None
    data = None
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
                        "max_tokens": 4096,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    break
                last_error = f"Perplexity API error ({resp.status_code}): {resp.text[:200]}"
                if resp.status_code < 500:
                    break  # Don't retry client errors
        except httpx.TimeoutException:
            last_error = "Perplexity API timed out"
        except Exception as e:
            last_error = str(e)

    if data is None:
        raise HTTPException(status_code=502, detail=last_error or "Perplexity API failed")

    raw_content = data["choices"][0]["message"]["content"]
    citations = data.get("citations", [])

    # Extract structured startups
    startups_raw = _extract_startups_from_response(raw_content)
    startups = []
    for s in startups_raw:
        try:
            startups.append(StartupCandidate(**s).model_dump())
        except Exception:
            continue

    # Check for duplicates against existing startups
    existing_result = await db.execute(select(Startup))
    existing_startups = existing_result.scalars().all()

    existing_lookup = {}
    for es in existing_startups:
        existing_lookup[normalize_name(es.name)] = {"id": str(es.id), "name": es.name, "status": es.status.value}
        if es.website_url:
            existing_lookup[normalize_domain(es.website_url)] = {"id": str(es.id), "name": es.name, "status": es.status.value}

    for startup_dict in startups:
        n = normalize_name(startup_dict.get("name", ""))
        d = normalize_domain(startup_dict.get("website_url", ""))
        match = existing_lookup.get(n) or (existing_lookup.get(d) if d else None)
        if match:
            startup_dict["already_on_platform"] = True
            startup_dict["existing_status"] = match["status"]
            startup_dict["existing_id"] = match["id"]
        else:
            startup_dict["already_on_platform"] = False

    # Clean reply for display
    reply = _clean_reply(raw_content)
    if not reply:
        reply = f"Found {len(startups)} startups."

    return {
        "reply": reply,
        "startups": startups,
        "citations": citations,
    }


@router.post("/api/admin/scout/add")
async def scout_add_startups(
    body: ScoutAddRequest,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    created = []
    skipped = []

    for candidate in body.startups:
        from app.services.dedup import find_duplicate
        dup = await find_duplicate(db, candidate.name, candidate.website_url)
        if dup is not None:
            skipped.append(candidate.name)
            continue

        slug = _slugify(candidate.name)
        # Ensure unique slug
        slug_check = await db.execute(select(Startup).where(Startup.slug == slug))
        if slug_check.scalar_one_or_none() is not None:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        # Validate stage
        stage = candidate.stage
        valid_stages = [s.value for s in StartupStage]
        if stage not in valid_stages:
            stage = "seed"

        startup = Startup(
            name=candidate.name,
            slug=slug,
            description=candidate.description or f"{candidate.name} startup",
            website_url=candidate.website_url,
            stage=StartupStage(stage),
            status=StartupStatus.pending,
            location_city=candidate.location_city,
            location_state=candidate.location_state,
            location_country=candidate.location_country or "US",
        )
        db.add(startup)
        await db.flush()

        # Try to fetch logo if we have a website URL and a Logo.dev token
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
                        if logo_resp.status_code == 200 and "image" in (logo_resp.headers.get("content-type") or ""):
                            startup.logo_url = logo_url
            except Exception:
                pass

        created.append({
            "id": str(startup.id),
            "name": startup.name,
            "slug": startup.slug,
            "status": startup.status.value,
        })

    await db.commit()

    return {
        "created": created,
        "skipped": skipped,
        "message": f"Added {len(created)} startups to triage. {f'Skipped {len(skipped)} duplicates.' if skipped else ''}",
    }
