"""Claude-powered analyst agent with database and web research tools.

Uses Claude as an orchestrator that can:
1. Query the startup database via read-only SQL
2. Research external market data via Perplexity
3. Create chart visualizations
"""

import json
import logging
from collections.abc import AsyncGenerator

import anthropic
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 15
MAX_ROWS = 200
SQL_TIMEOUT_MS = 10_000

TOOLS = [
    {
        "name": "run_sql",
        "description": (
            "Execute a read-only SQL SELECT query against the startup database.\n\n"
            "Available tables:\n\n"
            "startups:\n"
            "  id (UUID), name (VARCHAR), slug (VARCHAR), description (TEXT), tagline (VARCHAR),\n"
            "  website_url, logo_url, linkedin_url, twitter_url, crunchbase_url (VARCHAR),\n"
            "  location_city, location_state (2-letter code e.g. 'OH','CA'), location_country (VARCHAR, default 'US'),\n"
            "  founded_date (DATE),\n"
            "  total_funding (VARCHAR — stored as text like '$10M', '$1.5B', '$500K'),\n"
            "  employee_count (VARCHAR), revenue_estimate (VARCHAR), business_model (VARCHAR),\n"
            "  ai_score (FLOAT 0-100, higher=better), expert_score (FLOAT), user_score (FLOAT),\n"
            "  competitors (TEXT), tech_stack (TEXT), hiring_signals (TEXT), patents (TEXT), key_metrics (TEXT),\n"
            "  stage (VARCHAR: 'pre_seed','seed','series_a','series_b','series_c','growth','public'),\n"
            "  company_status (VARCHAR: 'active','acquired','ipo','defunct','unknown'),\n"
            "  entity_type (VARCHAR: 'startup','fund','vehicle','unknown'),\n"
            "  sec_cik (VARCHAR), form_sources (JSON), data_sources (JSON),\n"
            "  created_at, updated_at (TIMESTAMP WITH TZ)\n\n"
            "industries:\n"
            "  id (UUID), name (VARCHAR), slug (VARCHAR)\n\n"
            "startup_industries (junction):\n"
            "  startup_id (UUID FK→startups), industry_id (UUID FK→industries)\n\n"
            "Tips:\n"
            "- total_funding is text. To sort numerically, parse it. Example:\n"
            "  CASE WHEN total_funding LIKE '%B' THEN CAST(REPLACE(REPLACE(total_funding,'$',''),'B','') AS FLOAT)*1e9\n"
            "       WHEN total_funding LIKE '%M' THEN CAST(REPLACE(REPLACE(total_funding,'$',''),'M','') AS FLOAT)*1e6\n"
            "       WHEN total_funding LIKE '%K' THEN CAST(REPLACE(REPLACE(total_funding,'$',''),'K','') AS FLOAT)*1e3\n"
            "       ELSE 0 END as funding_numeric\n"
            "- JOIN startup_industries si ON s.id = si.startup_id JOIN industries i ON i.id = si.industry_id\n"
            "- Max 200 rows returned. Use LIMIT for large tables.\n"
            "- Only SELECT is allowed. No INSERT/UPDATE/DELETE/DDL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL SELECT query"},
                "description": {"type": "string", "description": "Brief description shown to user as status"},
            },
            "required": ["query", "description"],
        },
    },
    {
        "name": "web_research",
        "description": (
            "Search the web for external market intelligence via Perplexity. "
            "Use for Crunchbase data, PitchBook data, market reports, industry news, "
            "VC trends, and any information NOT in our startup database. Returns text with citations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Research question or search query"},
                "description": {"type": "string", "description": "Brief description shown to user as status"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "create_chart",
        "description": (
            "Create a chart visualization displayed to the user.\n\n"
            "Types: bar, line, pie, scatter, area.\n"
            "For bar/line/area/scatter: use xKey + yKeys.\n"
            "For pie: use nameKey + dataKey.\n"
            "Keep data under 30 items. Use descriptive titles.\n"
            "Default colors: ['#6366f1','#f59e0b','#10b981','#ef4444','#8b5cf6','#ec4899','#06b6d4','#84cc16']"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["bar", "line", "pie", "scatter", "area"]},
                "title": {"type": "string"},
                "data": {"type": "array", "items": {"type": "object"}},
                "xKey": {"type": "string", "description": "Key for x-axis (bar/line/area/scatter)"},
                "yKeys": {"type": "array", "items": {"type": "string"}, "description": "Keys for y-axis values"},
                "nameKey": {"type": "string", "description": "Key for pie chart segment names"},
                "dataKey": {"type": "string", "description": "Key for pie chart values"},
                "colors": {"type": "array", "items": {"type": "string"}, "description": "Hex color codes"},
            },
            "required": ["type", "title", "data"],
        },
    },
]

SYSTEM_PROMPT = """You are a senior venture analyst at Deep Thesis with a data science background.

You have three tools:
1. **run_sql** — Query our proprietary startup database with SQL. Always use this for questions about our portfolio.
2. **web_research** — Search the web via Perplexity for external market intelligence (Crunchbase, PitchBook, market reports, news, VC trends).
3. **create_chart** — Create visualizations when data supports it.

WORKFLOW:
- For questions about our startups/portfolio: query the database first. Never guess or fabricate data.
- For external market data: use web_research.
- For comparison questions (e.g. "compare our Ohio startups to national averages"): use both tools.
- Query the database BEFORE making claims about our portfolio. Run multiple queries if needed.

ANALYSIS STYLE:
- Provide analysis, not just data dumps. Interpret trends, flag risks, compare to benchmarks.
- Be specific — cite actual numbers from your queries.
- When you find interesting patterns, create a chart to visualize them.
- If a query returns no results, say so clearly.

CHART GUIDELINES:
- Bar: comparisons across categories
- Line: trends over time
- Pie: proportional breakdowns (max 7 segments)
- Scatter: correlations between two numeric variables
- Always use descriptive titles and limit data to 30 items
"""

# ── Read-only database engine (lazy singleton) ──────────────────────

_readonly_engine = None


def _get_readonly_engine():
    global _readonly_engine
    if _readonly_engine is None:
        url = settings.database_readonly_url or settings.database_url
        if not settings.database_readonly_url:
            logger.warning("ACUTAL_DATABASE_READONLY_URL not set, using main database URL")
        _readonly_engine = create_async_engine(url, pool_size=5, max_overflow=2)
    return _readonly_engine


# ── Tool executors ──────────────────────────────────────────────────

_FORBIDDEN_SQL = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "GRANT", "REVOKE", "COPY", "EXECUTE", "INTO",
}
_FORBIDDEN_TABLES = {
    "users", "analyst_conversations", "analyst_messages", "analyst_reports",
    "alembic_version",
}


def _validate_sql(query: str) -> None:
    """Raise ValueError if the query is not a safe SELECT."""
    normalized = query.strip()
    # Must start with SELECT (or WITH for CTEs)
    upper = normalized.upper()
    if not upper.startswith("SELECT") and not upper.startswith("WITH"):
        raise ValueError("Only SELECT queries are allowed")

    # Block dangerous keywords (check as whole words)
    import re
    words = set(re.findall(r'\b[A-Z_]+\b', upper))
    forbidden_found = words & _FORBIDDEN_SQL
    if forbidden_found:
        raise ValueError(f"Query contains forbidden keywords: {forbidden_found}")

    # Block access to user/auth tables
    lower = normalized.lower()
    for table in _FORBIDDEN_TABLES:
        if re.search(rf'\b{table}\b', lower):
            raise ValueError(f"Access to table '{table}' is not allowed")


async def _execute_sql(query: str) -> list[dict]:
    """Execute a validated read-only SQL query."""
    _validate_sql(query)

    engine = _get_readonly_engine()
    async with engine.connect() as conn:
        # Set statement timeout for safety
        await conn.execute(text(f"SET statement_timeout = '{SQL_TIMEOUT_MS}'"))
        result = await conn.execute(text(query))
        columns = list(result.keys())
        rows = result.fetchmany(MAX_ROWS)
        return [dict(zip(columns, row)) for row in rows]


async def _web_research(query: str) -> dict:
    """Call Perplexity sonar-pro for web research. Returns text + citations."""
    if not settings.perplexity_api_key:
        return {"text": "Perplexity API key not configured.", "citations": []}

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.perplexity_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar-pro",
                "temperature": 0.3,
                "max_tokens": 2048,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a market research assistant. Provide factual data from "
                            "Crunchbase, PitchBook, and other sources. Include specific numbers, "
                            "dates, and sources. Be concise."
                        ),
                    },
                    {"role": "user", "content": query},
                ],
            },
        )

        if response.status_code != 200:
            return {"text": f"Research failed: HTTP {response.status_code}", "citations": []}

        data = response.json()
        text_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        raw_citations = data.get("citations", [])

        citations = []
        for c in raw_citations:
            if isinstance(c, str):
                citations.append({"url": c, "title": c})
            elif isinstance(c, dict):
                citations.append({"url": c.get("url", ""), "title": c.get("title", c.get("url", ""))})

        return {"text": text_content, "citations": citations}


# ── Main agent loop ─────────────────────────────────────────────────

async def run_agent(
    messages: list[dict],
    system_prompt: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Run the Claude analyst agent with tool use.

    Yields event dicts:
      {"type": "text",      "chunk": str}
      {"type": "status",    "message": str}
      {"type": "charts",    "charts": list}
      {"type": "citations", "citations": list}
      {"type": "done",      "full_text": str}
      {"type": "error",     "message": str}
    """
    if not settings.anthropic_api_key:
        yield {"type": "error", "message": "Anthropic API key not configured"}
        return

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    prompt = system_prompt or SYSTEM_PROMPT

    # Convert to Claude message format
    api_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

    full_text = ""
    all_charts: list[dict] = []
    all_citations: list[dict] = []

    try:
        for _round in range(MAX_TOOL_ROUNDS):
            # Stream Claude's response
            async with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=prompt,
                messages=api_messages,
                tools=TOOLS,
            ) as stream:
                async for event in stream:
                    if (
                        event.type == "content_block_delta"
                        and hasattr(event.delta, "text")
                    ):
                        full_text += event.delta.text
                        yield {"type": "text", "chunk": event.delta.text}

                response = await stream.get_final_message()

            # If no tool calls, we're done
            if response.stop_reason != "tool_use":
                break

            # Collect tool_use blocks
            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            if not tool_blocks:
                break

            # Add assistant turn (with all content blocks)
            api_messages.append({"role": "assistant", "content": response.content})

            # Execute each tool and collect results
            tool_results = []
            for tb in tool_blocks:
                try:
                    if tb.name == "run_sql":
                        desc = tb.input.get("description", "Running database query")
                        yield {"type": "status", "message": desc}

                        rows = await _execute_sql(tb.input["query"])
                        payload = json.dumps(rows, default=str)
                        if len(payload) > 50_000:
                            payload = payload[:50_000] + "\n... (truncated)"

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tb.id,
                            "content": f"{len(rows)} rows returned:\n{payload}",
                        })

                    elif tb.name == "web_research":
                        desc = tb.input.get("description", "Researching external data")
                        yield {"type": "status", "message": desc}

                        result = await _web_research(tb.input["query"])
                        all_citations.extend(result.get("citations", []))

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tb.id,
                            "content": result["text"],
                        })

                    elif tb.name == "create_chart":
                        chart = {"type": tb.input["type"], "title": tb.input["title"], "data": tb.input["data"]}
                        for key in ("xKey", "yKeys", "nameKey", "dataKey", "colors"):
                            if key in tb.input:
                                chart[key] = tb.input[key]

                        all_charts.append(chart)
                        yield {"type": "charts", "charts": [chart]}

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tb.id,
                            "content": "Chart created and displayed to the user.",
                        })

                    else:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tb.id,
                            "content": f"Unknown tool: {tb.name}",
                            "is_error": True,
                        })

                except Exception as e:
                    logger.error("Tool %s failed: %s", tb.name, e)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tb.id,
                        "content": f"Error: {e}",
                        "is_error": True,
                    })

            # Feed tool results back to Claude
            api_messages.append({"role": "user", "content": tool_results})

        # Emit final events
        if all_citations:
            yield {"type": "citations", "citations": all_citations}

        yield {"type": "done", "full_text": full_text, "charts": all_charts}

    except anthropic.APIStatusError as e:
        logger.error("Claude API error: %s", e)
        yield {"type": "error", "message": f"Claude API error: {e.status_code}"}
    except Exception as e:
        logger.error("Agent error: %s", e)
        yield {"type": "error", "message": f"Agent error: {e}"}
