# Analyst Chat Insights Tools — Design Spec

> **For agentic workers:** This spec describes the feature. Use superpowers:writing-plans to create the implementation plan.

**Goal:** Give the Analyst Chat agent access to the user's pitch analysis data, investment memos, investor FAQs, and pitch intelligence sessions — plus action tools to regenerate memos and FAQs.

**Architecture:** Hybrid approach — keep existing `run_sql` for public startup data, add structured tools for user-scoped analysis data (secure by design), add action tools for memo/FAQ regeneration. New tool executors live in a dedicated `analyst_tools.py` file.

**Tech Stack:** FastAPI, SQLAlchemy async, Claude Sonnet 4.6 tool use, existing memo/FAQ generation services.

---

## 1. Overview

The Analyst Chat currently has 3 tools:
- `run_sql` — read-only SQL against the startup database
- `web_research` — Perplexity sonar-pro for external market data
- `create_chart` — chart visualizations

This feature adds 8 new tools that give the agent access to the user's analysis data:

### Query Tools (6)

| Tool | Input | Returns |
|------|-------|---------|
| `list_analyses` | `status?` (string), `search?` (string) | User's pitch analyses: id, company_name, status, overall_score, fundraising_likelihood, created_at. Max 50 results. |
| `get_analysis_detail` | `analysis_id` (string, required) | Full analysis: all scores, executive_summary, estimated_valuation, valuation_justification, technical_expert_review, plus all 8 agent reports (agent_type, score, summary, key_findings, full report text) |
| `get_memo` | `analysis_id` (string, required) | Investment memo: markdown content, status, created_at, completed_at. Returns status info if memo is still generating or doesn't exist. |
| `get_faq` | `analysis_id?` (string), `session_id?` (string) | Investor FAQ questions array: category, question, answer, priority. Exactly one of analysis_id or session_id must be provided. |
| `list_pitch_sessions` | `status?` (string), `search?` (string) | User's pitch intelligence sessions: id, title, status, scores, created_at. Max 50 results. |
| `get_pitch_session_detail` | `session_id` (string, required) | Full session: scores, benchmark_percentiles, investor_faq, and phase results (claim_extraction, fact_checks, conversation_analysis, scoring) |

### Action Tools (2)

| Tool | Input | Returns |
|------|-------|---------|
| `regenerate_memo` | `analysis_id` (string, required) | Creates or resets InvestmentMemo, triggers background generation. Returns memo_id and status "started". |
| `regenerate_faq` | `analysis_id?` (string), `session_id?` (string) | Runs FAQ generation inline (single Claude call). Returns the new FAQ questions array. Exactly one of analysis_id or session_id must be provided. |

## 2. Data Access Scoping

All query and action tools enforce scoping:

```
if is_admin:
    # See everything
elif analysis.user_id == current_user_id:
    # Own data — always accessible
elif analysis.publish_consent == True and analysis.status == "complete":
    # Published data — read-only access for all users
else:
    # Access denied
```

Action tools (`regenerate_memo`, `regenerate_faq`) require ownership — only the analysis owner or an admin can trigger regeneration. Published analyses are read-only for non-owners.

## 3. File Changes

### New file: `backend/app/services/analyst_tools.py`

All 8 tool executor functions live here. Each function:
- Takes `user_id: uuid.UUID`, `is_admin: bool`, and tool-specific params
- Uses `async_session` to query the database (same pattern as `_execute_sql` in `analyst_agent.py`)
- Returns a JSON-serializable dict
- Raises `ValueError` for access denied or not found (caught by agent loop)

Functions:

```python
async def tool_list_analyses(user_id, is_admin, status=None, search=None) -> list[dict]
async def tool_get_analysis_detail(user_id, is_admin, analysis_id) -> dict
async def tool_get_memo(user_id, is_admin, analysis_id) -> dict
async def tool_get_faq(user_id, is_admin, analysis_id=None, session_id=None) -> dict
async def tool_list_pitch_sessions(user_id, is_admin, status=None, search=None) -> list[dict]
async def tool_get_pitch_session_detail(user_id, is_admin, session_id) -> dict
async def tool_regenerate_memo(user_id, is_admin, analysis_id) -> dict
async def tool_regenerate_faq(user_id, is_admin, analysis_id=None, session_id=None) -> dict
```

Shared helper:

```python
def _check_access(obj, user_id, is_admin, require_owner=False) -> None:
    """Raise ValueError if user cannot access this object."""
    if is_admin:
        return
    if obj.user_id == user_id:
        return
    if not require_owner and hasattr(obj, 'publish_consent') and obj.publish_consent and obj.status == "complete":
        return
    raise ValueError("Analysis not found or access denied")
```

### Modified: `backend/app/services/analyst_agent.py`

1. **`TOOLS` list** — append 8 new tool definitions with proper input_schema
2. **`SYSTEM_PROMPT`** — add a section describing the new tools and when to use them:
   - "For questions about the user's pitch analyses, investment memos, FAQs, or pitch sessions, use the analysis tools"
   - "For regenerating memos or FAQs, use the action tools"
   - "For market/startup database queries, continue using run_sql and web_research"
3. **`run_agent()` signature** — add `user_id: uuid.UUID | None = None` and `is_admin: bool = False` parameters
4. **Tool executor switch** — add cases for all 8 new tools in the tool execution loop, calling the functions from `analyst_tools.py`

### Modified: `backend/app/api/analyst.py`

1. **`send_message()`** — pass `user.id` and `user.role == UserRole.superadmin` to `run_agent()`:

```python
async for event in run_agent(
    history,
    image_blocks=image_blocks if image_blocks else None,
    user_id=user.id,
    is_admin=user.role == UserRole.superadmin,
):
```

## 4. System Prompt Addition

Added to the end of `SYSTEM_PROMPT`:

```
ANALYSIS TOOLS:
You also have tools to access the user's pitch analysis data:
- list_analyses — List the user's pitch deck analyses
- get_analysis_detail — Get full analysis with all 8 agent reports, scores, and findings
- get_memo — Get the investment memo content for an analysis
- get_faq — Get the investor FAQ for an analysis or pitch session
- list_pitch_sessions — List the user's pitch intelligence sessions
- get_pitch_session_detail — Get full pitch session results with fact-checks and benchmarks

And action tools:
- regenerate_memo — Re-generate an investment memo for an analysis
- regenerate_faq — Re-generate the investor FAQ for an analysis or pitch session

Use these tools when the user asks about their analyses, memos, FAQs, pitch sessions,
scores, or wants to compare their analyzed companies. Always query real data — never
fabricate analysis results.
```

## 5. What Does NOT Change

- **No database migrations** — all data already exists in the current schema
- **No frontend changes** — the chat UI already handles tool status messages, text streaming, charts, and citations
- **No new API endpoints** — tools query the DB directly via `async_session`
- **Existing tools unchanged** — `run_sql`, `web_research`, `create_chart` work exactly as before
- **`_FORBIDDEN_TABLES`** — analysis tables remain in the forbidden list for raw SQL (access is only through the structured tools)

## 6. Example Interactions

**User:** "What were the weak points in my Acme Corp analysis?"
- Agent calls `list_analyses(search="Acme")` → finds the analysis
- Agent calls `get_analysis_detail(analysis_id=...)` → gets all 8 reports
- Agent analyzes scores and key_findings, identifies lowest-scoring dimensions
- Agent responds with specific weak points citing actual scores

**User:** "Compare the market scores across my last 5 pitches"
- Agent calls `list_analyses()` → gets recent analyses
- Agent calls `get_analysis_detail()` for each (or top 5)
- Agent extracts market_tam scores from each
- Agent calls `create_chart()` with a comparison bar chart
- Agent responds with analysis and chart

**User:** "What did the investment memo say about valuation for XYZ?"
- Agent calls `list_analyses(search="XYZ")` → finds analysis
- Agent calls `get_memo(analysis_id=...)` → gets memo markdown
- Agent extracts the "Valuation & Investment Terms" section
- Agent responds with the valuation details

**User:** "Regenerate the memo for my latest analysis"
- Agent calls `list_analyses()` → finds most recent complete analysis
- Agent calls `regenerate_memo(analysis_id=...)` → triggers background regeneration
- Agent responds: "Memo regeneration started for [company]. It'll take a couple minutes."

**User:** "Show me the FAQ for my pitch session with Sequoia"
- Agent calls `list_pitch_sessions(search="Sequoia")` → finds session
- Agent calls `get_faq(session_id=...)` → gets FAQ questions
- Agent responds with formatted FAQ grouped by category and priority
