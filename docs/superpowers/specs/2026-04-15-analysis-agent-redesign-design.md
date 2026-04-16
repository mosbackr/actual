# Analysis Agent Redesign — Claude as Orchestrator with Tool Use

## Overview

Redesign the pitch analysis system so each of the 8 parallel Claude agents uses Anthropic's native tool-use API to invoke Perplexity web search and DeepThesis database lookups dynamically. Replace the current pre-fetched Perplexity research approach with Claude-driven tool calls. Persist every tool call in real-time and display them in a unified collapsible activity log on the frontend analyze page.

## Goals

- Claude decides what to research and when (not hardcoded queries)
- Perplexity used as a web search tool with access to Crunchbase, PitchBook, and the open web
- Claude can query the DeepThesis database for previously analyzed startups, analysis results, and expert profiles
- Every tool call persisted in real-time for frontend display
- Unified collapsible activity log on the analyze page, updated in real-time via polling
- No breaking changes to existing analyses

## Architecture

### Agent Loop

Each of the 8 agents (market_opportunity, competitive_landscape, team, financials, product, business_model, risk, scalability) gets a Claude conversation using the Anthropic tool-use API:

1. Send initial message to Claude with agent rubric + pitch document content + tool definitions
2. Claude responds — either with a `tool_use` content block or a final text report
3. If tool call: execute it, persist the call+result to the `tool_calls` table, send result back to Claude via `tool_result`, repeat
4. If `end_turn` stop reason with text: that's the agent's final report, store it
5. No hard cap on tool call iterations — Claude decides when it has enough information

Models remain unchanged: `claude-sonnet-4-6` for the 8 agents, `claude-opus-4-6` for final scoring. Final scoring has no tools.

### Tool Definitions

#### 1. `perplexity_search`

Web search powered by Perplexity (sonar-pro). Has access to Crunchbase, PitchBook, and the broader web. Use for: funding history, valuations, competitor analysis, market sizing, regulatory research, recent news, team background checks, industry trends — anything that benefits from up-to-date external data.

**Parameters:**
- `query` (string, required): Natural language search query

**Returns:** Search results with citations as text

**System prompt guidance:** "You have access to Perplexity web search which can query Crunchbase, PitchBook, and the open web. Use it aggressively to validate claims in the pitch deck, find comparable companies, check funding histories, and research market conditions."

#### 2. `db_search_startups`

Search DeepThesis startups by name, industry, or keyword. Returns matching company profiles.

**Parameters:**
- `query` (string, required): Search term (name, industry, keyword)
- `limit` (integer, optional, default 10): Max results

**Returns:** List of startup profiles: id, name, industry, stage, location, founding_date, description. No PII.

#### 3. `db_get_analysis`

Get full analysis results (scores + report summaries) for a specific startup by ID. Lets Claude compare the current pitch against previously analyzed companies.

**Parameters:**
- `startup_id` (string, required): UUID of the startup

**Returns:** Analysis scores per category, overall score, report summaries. No PII.

#### 4. `db_list_experts`

List approved domain experts with public profile info.

**Parameters:**
- `industry` (string, optional): Filter by industry/domain
- `limit` (integer, optional, default 10): Max results

**Returns:** List of expert profiles: name, title, areas of expertise. No PII, no emails, no credentials.

## Database

### New Table: `tool_calls`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| analysis_id | UUID | FK to pitch_analyses |
| agent_type | VARCHAR | Which agent made the call (e.g., "market_opportunity") |
| tool_name | VARCHAR | "perplexity_search", "db_search_startups", "db_get_analysis", "db_list_experts" |
| input | JSON | Arguments Claude passed to the tool |
| output | JSON | Result returned to Claude |
| created_at | TIMESTAMP | When the call was made, for chronological ordering |
| duration_ms | INTEGER | How long the tool call took to execute |

Each tool call is inserted immediately after execution (before sending the result back to Claude), so the frontend can poll and display them in real-time.

The existing `agent_results` table stays as-is for storing final reports and scores.

## Backend Changes

### `analysis_agents.py`

**Remove:**
- `PERPLEXITY_QUERIES` dict (hardcoded queries per agent type)
- `_research_with_perplexity()` function

**Replace `run_agent()` with tool-use loop:**
- Build tool definitions list for the Anthropic API
- Send initial message with agent rubric + pitch content + tools
- Loop: check stop_reason — if `tool_use`, execute the tool, persist to DB, send `tool_result` back; if `end_turn`, extract final report text
- Return the final report

**Add tool execution functions:**
- `_execute_perplexity_search(query)` — Calls Perplexity sonar-pro API
- `_execute_db_search_startups(query, limit)` — SQLAlchemy query against companies table
- `_execute_db_get_analysis(startup_id)` — SQLAlchemy query for analysis results
- `_execute_db_list_experts(industry, limit)` — SQLAlchemy query for approved experts

Each execution function persists to the `tool_calls` table and returns the result.

**Error handling in tool execution:**
- If a tool call fails (e.g., Perplexity timeout, DB query error), return an error message as the `tool_result` content (e.g., "Search failed: timeout after 30s"). Claude can then decide to retry or proceed without that data.
- Tool call is still persisted with the error in the `output` field.
- Agent loop does NOT abort on tool errors — only on Claude API errors.

**Update agent system prompts:**
- Remove instructions about pre-provided research context
- Add guidance about available tools and when to use them
- Include Perplexity's Crunchbase/PitchBook/web access in the prompt
- Tell Claude to be thorough but efficient — don't repeat searches, don't search for info already in the pitch deck

### `analysis_worker.py`

**Flow changes:**
1. Claim job (unchanged)
2. Run 8 agents in parallel via `asyncio.gather()` — each agent now enters a tool-use loop
3. `current_agent` field still updated to show which agents are active
4. Run final scoring (unchanged — single Claude call, no tools)
5. Save results (unchanged)

## API

### New Endpoint: `GET /api/analyses/{analysis_id}/tool-calls`

- Returns all tool calls for an analysis, ordered by `created_at`
- Query param `since` (ISO timestamp) — only return tool calls after this timestamp for incremental polling
- Query param `include_output` (boolean, default false) — include the full output JSON (can be large)
- Requires auth, user must own the analysis

**Response shape:**
```json
{
  "tool_calls": [
    {
      "id": "uuid",
      "agent_type": "market_opportunity",
      "tool_name": "perplexity_search",
      "input": {"query": "fintech market size 2025"},
      "created_at": "2026-04-15T12:00:01Z",
      "duration_ms": 1200
    }
  ]
}
```

## Frontend

### Unified Collapsible Activity Log

**Location:** New panel on the analyze page (`/analyze/[id]`).

**Behavior:**
- Collapsed by default, expandable via button: "Activity Log (12 tool calls)"
- Polls `GET /api/analyses/{id}/tool-calls?since=<last_timestamp>` every 3 seconds (same interval as existing status poll)
- New tool calls append to the bottom of the log in real-time
- Counter in button header updates as new calls arrive

**Each log entry shows:**
- Agent icon/label (color-coded by agent type, consistent with existing agent status icons)
- Tool name as a badge (e.g., "Perplexity Search", "DB Lookup")
- Query/input in plain text
- Timestamp
- Duration (e.g., "1.2s")
- Expandable to show full output on click (fetches with `include_output=true`)

**Styling:** Matches existing analyze page. Monospace for queries, muted colors for log background.

**After analysis completes:** Log stays available, polling stops, full log is cached.

## Cost & Performance

**Cost:**
- Variable per analysis — no hard cap on tool calls
- With 8 agents each potentially making 5-10 Perplexity calls, a single analysis could hit 40-80 Perplexity API calls + extra Claude tokens for the tool-use loop
- Meaningful increase from the current fixed 8 Perplexity + 9 Claude calls
- Mitigated by prompt guidance: tell Claude to be thorough but efficient

**Latency:**
- Each agent makes multiple sequential API calls instead of one, so individual agent time increases
- Agents still run in parallel — wall-clock time = slowest agent's total loop time
- Expect 2-4x longer per analysis compared to current (~60-120s vs ~30-60s)
- Real-time tool call log makes the wait feel shorter

**No breaking changes:** Existing analyses unaffected. `tool_calls` table is additive. Old analyses have zero tool call entries.

## Security

- All database tool functions are read-only
- No PII exposed: no emails, passwords, payment data, API keys
- Tool results sanitized before storage
- Auth required on tool-calls endpoint, user must own the analysis
- Database queries use parameterized SQLAlchemy — no SQL injection risk
