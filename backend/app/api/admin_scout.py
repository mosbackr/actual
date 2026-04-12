from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.config import settings
from app.db.session import get_db
from app.models.startup import Startup
from app.models.user import User
from app.services.dedup import normalize_domain, normalize_name
from app.services.scout import (
    SCOUT_SYSTEM_PROMPT,
    StartupCandidate,
    add_startups_to_triage,
    call_perplexity,
    clean_reply,
    extract_startups_from_response,
)

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ScoutChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class ScoutAddRequest(BaseModel):
    startups: list[StartupCandidate]


@router.post("/api/admin/scout/chat")
async def scout_chat(
    body: ScoutChatRequest,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    if not settings.perplexity_api_key:
        raise HTTPException(
            status_code=500, detail="ACUTAL_PERPLEXITY_API_KEY not configured"
        )

    data = await call_perplexity(SCOUT_SYSTEM_PROMPT, body.message)
    if data is None:
        raise HTTPException(status_code=502, detail="Perplexity API failed")

    raw_content = data["choices"][0]["message"]["content"]
    citations = data.get("citations", [])

    startups_raw = extract_startups_from_response(raw_content)
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
        existing_lookup[normalize_name(es.name)] = {
            "id": str(es.id),
            "name": es.name,
            "status": es.status.value,
        }
        if es.website_url:
            existing_lookup[normalize_domain(es.website_url)] = {
                "id": str(es.id),
                "name": es.name,
                "status": es.status.value,
            }

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

    reply = clean_reply(raw_content)
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
    result = await add_startups_to_triage(db, body.startups)
    created = result["created"]
    skipped = result["skipped"]
    return {
        "created": created,
        "skipped": skipped,
        "message": f"Added {len(created)} startups to triage. {f'Skipped {len(skipped)} duplicates.' if skipped else ''}",
    }
