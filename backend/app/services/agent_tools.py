import json
import logging
import time
import uuid

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.pitch_analysis import AgentType, AnalysisReport, PitchAnalysis
from app.models.startup import Startup, startup_industries
from app.models.expert import ExpertProfile, ApplicationStatus
from app.models.industry import Industry
from app.models.tool_call import ToolCall

logger = logging.getLogger(__name__)

# ── Tool definitions for Anthropic API ────────────────────────────────

AGENT_TOOLS = [
    {
        "name": "perplexity_search",
        "description": (
            "Web search powered by Perplexity (sonar-pro). Has access to Crunchbase, "
            "PitchBook, and the broader web. Use for: funding history, valuations, "
            "competitor analysis, market sizing, regulatory research, recent news, "
            "team background checks, industry trends — anything that benefits from "
            "up-to-date external data. Use this aggressively to validate claims in "
            "the pitch deck."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "db_search_startups",
        "description": (
            "Search the DeepThesis startup database by name, industry, or keyword. "
            "Returns matching company profiles. Use to find comparable companies that "
            "have been previously analyzed on the platform."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search term (company name, industry, or keyword)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default 10)",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "db_get_analysis",
        "description": (
            "Get full analysis results (scores and report summaries) for a previously "
            "analyzed startup by its ID. Use after db_search_startups to compare the "
            "current pitch against similar companies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "startup_id": {
                    "type": "string",
                    "description": "UUID of the startup to look up",
                },
            },
            "required": ["startup_id"],
        },
    },
    {
        "name": "db_list_experts",
        "description": (
            "List approved domain experts on the DeepThesis platform with their public "
            "profile information. Use to reference relevant expert perspectives."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "industry": {
                    "type": "string",
                    "description": "Optional industry filter",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results (default 10)",
                    "default": 10,
                },
            },
            "required": [],
        },
    },
]


# ── Tool execution ────────────────────────────────────────────────────

async def execute_perplexity_search(query: str) -> str:
    """Call Perplexity sonar-pro with the given query. Returns text results."""
    if not settings.perplexity_api_key:
        return "Perplexity API key not configured — web search unavailable."
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.perplexity_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar-pro",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Provide concise, factual research data. Include specific "
                                "numbers, dates, and sources where available. You have access "
                                "to Crunchbase and PitchBook data. Keep responses focused and "
                                "under 500 words — prioritize hard data over commentary."
                            ),
                        },
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 2048,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            # Cap response length to prevent context window bloat
            if len(content) > 3000:
                content = content[:3000] + "\n\n[Response truncated for brevity]"
            return content
    except Exception as e:
        logger.warning("Perplexity search failed: %s", e)
        return f"Search failed: {e}"


async def execute_db_search_startups(query: str, limit: int, db: AsyncSession) -> str:
    """Search startups by name/description using ILIKE, splitting multi-word queries."""
    try:
        # Split query into individual words and match ANY word against name or description
        words = [w.strip() for w in query.split() if len(w.strip()) >= 3]
        if not words:
            words = [query]  # fallback to full query if all words are short

        word_conditions = []
        for word in words:
            term = f"%{word}%"
            word_conditions.append(Startup.name.ilike(term))
            word_conditions.append(Startup.description.ilike(term))

        # Also match by industry name
        id_stmt = (
            select(Startup.id)
            .outerjoin(startup_industries, Startup.id == startup_industries.c.startup_id)
            .outerjoin(Industry, Industry.id == startup_industries.c.industry_id)
        )
        for word in words:
            word_conditions.append(Industry.name.ilike(f"%{word}%"))

        id_result = await db.execute(
            id_stmt.where(or_(*word_conditions))
            .distinct()
            .limit(min(limit, 20))
        )
        matched_ids = [row[0] for row in id_result]
        if not matched_ids:
            return "No matching startups found in the DeepThesis database."

        result = await db.execute(
            select(Startup).where(Startup.id.in_(matched_ids))
        )
        startups = result.scalars().all()
        if not startups:
            return "No matching startups found in the DeepThesis database."
        items = []
        for s in startups:
            items.append({
                "id": str(s.id),
                "name": s.name,
                "description": s.description[:300] if s.description else None,
                "stage": s.stage.value if hasattr(s.stage, "value") else s.stage,
                "location_city": s.location_city,
                "location_state": s.location_state,
                "location_country": s.location_country,
                "founded_date": str(s.founded_date) if s.founded_date else None,
                "ai_score": s.ai_score,
                "total_funding": s.total_funding,
                "business_model": s.business_model,
            })
        return json.dumps(items, indent=2)
    except Exception as e:
        logger.warning("DB search startups failed: %s", e)
        return f"Database search failed: {e}"


async def execute_db_get_analysis(startup_id: str, db: AsyncSession) -> str:
    """Get analysis results for a startup by its ID."""
    try:
        sid = uuid.UUID(startup_id)
    except ValueError:
        return f"Invalid startup ID: {startup_id}"
    try:
        result = await db.execute(
            select(PitchAnalysis).where(PitchAnalysis.startup_id == sid)
        )
        analysis = result.scalar_one_or_none()
        if not analysis:
            return f"No analysis found for startup {startup_id}."

        # Get reports
        report_result = await db.execute(
            select(AnalysisReport).where(AnalysisReport.analysis_id == analysis.id)
        )
        reports = report_result.scalars().all()

        data = {
            "overall_score": analysis.overall_score,
            "fundraising_likelihood": analysis.fundraising_likelihood,
            "recommended_raise": analysis.recommended_raise,
            "exit_likelihood": analysis.exit_likelihood,
            "expected_exit_value": analysis.expected_exit_value,
            "executive_summary": analysis.executive_summary,
            "reports": [
                {
                    "agent_type": r.agent_type.value if hasattr(r.agent_type, "value") else r.agent_type,
                    "score": r.score,
                    "summary": r.summary,
                }
                for r in reports
                if (r.status.value if hasattr(r.status, "value") else r.status) == "complete"
            ],
        }
        return json.dumps(data, indent=2)
    except Exception as e:
        logger.warning("DB get analysis failed: %s", e)
        return f"Database lookup failed: {e}"


async def execute_db_list_experts(industry: str | None, limit: int, db: AsyncSession) -> str:
    """List approved experts, optionally filtered by industry."""
    try:
        query = select(ExpertProfile).where(
            ExpertProfile.application_status == ApplicationStatus.approved
        ).options(
            selectinload(ExpertProfile.user),
            selectinload(ExpertProfile.industries),
            selectinload(ExpertProfile.skills),
        )
        if industry:
            query = query.join(ExpertProfile.industries).where(
                Industry.name.ilike(f"%{industry}%")
            )
        result = await db.execute(query.limit(min(limit, 20)))
        experts = result.scalars().all()
        if not experts:
            return "No approved experts found."
        items = []
        for e in experts:
            user = e.user
            items.append({
                "name": user.name if user else "Unknown",
                "bio": e.bio[:300] if e.bio else None,
                "years_experience": e.years_experience,
                "industries": [ind.name for ind in e.industries] if e.industries else [],
                "skills": [sk.name for sk in e.skills] if e.skills else [],
            })
        return json.dumps(items, indent=2)
    except Exception as e:
        logger.warning("DB list experts failed: %s", e)
        return f"Database lookup failed: {e}"


# ── Tool dispatch ─────────────────────────────────────────────────────

async def execute_tool(
    tool_name: str,
    tool_input: dict,
    analysis_id: uuid.UUID,
    agent_type: str,
    db: AsyncSession,
) -> str:
    """Execute a tool call, persist it to the database, and return the result string."""
    from app.db.session import async_session

    start = time.monotonic()

    # Each tool call gets its own DB session to prevent poisoning across calls
    if tool_name == "perplexity_search":
        result_text = await execute_perplexity_search(tool_input["query"])
    elif tool_name == "db_search_startups":
        async with async_session() as tool_db:
            result_text = await execute_db_search_startups(
                tool_input["query"], tool_input.get("limit", 10), tool_db
            )
    elif tool_name == "db_get_analysis":
        async with async_session() as tool_db:
            result_text = await execute_db_get_analysis(tool_input["startup_id"], tool_db)
    elif tool_name == "db_list_experts":
        async with async_session() as tool_db:
            result_text = await execute_db_list_experts(
                tool_input.get("industry"), tool_input.get("limit", 10), tool_db
            )
    else:
        result_text = f"Unknown tool: {tool_name}"

    duration_ms = int((time.monotonic() - start) * 1000)

    # Persist tool call in its own session too
    try:
        async with async_session() as persist_db:
            tool_call = ToolCall(
                analysis_id=analysis_id,
                agent_type=agent_type,
                tool_name=tool_name,
                input=tool_input,
                output={"result": result_text[:10000]},
                duration_ms=duration_ms,
            )
            persist_db.add(tool_call)
            await persist_db.commit()
    except Exception:
        logger.warning("Failed to persist tool call for %s/%s", agent_type, tool_name)

    return result_text
