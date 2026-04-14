# AI Venture Analyst — Design Spec

**Replaces:** Current Insights page (dashboard with static charts and tables)

**Goal:** Replace the Insights page with a conversational AI venture analyst powered by Perplexity sonar-pro. The analyst has access to all internal startup data and external market intelligence (Crunchbase, PitchBook via Perplexity's web access). It acts like a senior venture associate with a data science background — generating charts, running analyses, and producing downloadable Word/Excel reports.

---

## Architecture Overview

**Interaction pattern:** Hybrid chat interface with a sidebar of suggested analyses. Free-form conversation plus guided discovery for first-time users.

**AI engine:** Perplexity sonar-pro exclusively. Leverages built-in web access for Crunchbase, PitchBook, and market data alongside injected internal startup data.

**Data access:** Pre-aggregated portfolio summaries injected into every call. Full startup profiles injected when specific companies or filters are referenced.

**Chart rendering:** Recharts (client-side). Perplexity outputs structured chart JSON blocks, backend extracts them, frontend renders via Recharts.

**Report generation:** Server-side using python-docx and openpyxl. Charts rendered as images via matplotlib.

**Streaming:** SSE-based. Text streams in real-time. Charts and citations sent as events after stream completes.

**Flow:**
```
User message → Backend API → Inject DB context → Perplexity sonar-pro →
Stream text via SSE → Extract charts on completion → Render in Recharts
```

---

## Database Schema

### `analyst_conversations`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users |
| title | String(500) | Auto-generated from first message, editable |
| share_token | String(64) | Unique, nullable. Generated on first share |
| is_free_conversation | Boolean | First conversation is free |
| message_count | Integer | Denormalized for quick display |
| created_at | DateTime(tz) | server_default=now() |
| updated_at | DateTime(tz) | server_default=now(), onupdate=now() |

### `analyst_messages`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| conversation_id | UUID | FK → analyst_conversations, CASCADE |
| role | Enum(user, assistant) | messagerole enum |
| content | Text | The message text (charts stripped) |
| charts | JSON | Nullable. Array of Recharts-compatible chart configs |
| citations | JSON | Nullable. Array of Perplexity source URLs |
| context_startups | JSON | Nullable. Startup IDs referenced in this turn |
| created_at | DateTime(tz) | server_default=now() |

### `analyst_reports`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| conversation_id | UUID | FK → analyst_conversations, CASCADE |
| user_id | UUID | FK → users |
| title | String(500) | User-provided or auto-generated |
| format | Enum(docx, xlsx) | reportformat enum |
| status | Enum(pending, generating, complete, failed) | reportgenstatus enum |
| s3_key | String(1000) | S3 path for completed report |
| file_size_bytes | Integer | Nullable until complete |
| error | Text | Nullable. Error message if failed |
| created_at | DateTime(tz) | server_default=now() |

No changes to existing tables. `subscription_status` on users already handles gating.

---

## Backend API Endpoints

### Conversation Management

**`POST /api/analyst/conversations`**
- Auth: required
- Gating: count completed conversations. If >= 1 and subscription != active, return 402.
- Body: none (title auto-generated after first message)
- Returns: `{id, title, is_free_conversation}`

**`GET /api/analyst/conversations`**
- Auth: required
- Returns: `{items: [{id, title, message_count, updated_at, is_free_conversation}]}`, ordered by updated_at desc

**`GET /api/analyst/conversations/{id}`**
- Auth: required (owner only)
- Returns: full conversation with all messages (content, charts, citations), plus associated reports

**`PATCH /api/analyst/conversations/{id}`**
- Auth: required (owner only)
- Body: `{title: string}`
- Returns: `{ok: true}`

**`DELETE /api/analyst/conversations/{id}`**
- Auth: required (owner only)
- Deletes conversation, messages, and associated reports (S3 cleanup)
- Returns: `{ok: true}`

### Chat (SSE Streaming)

**`POST /api/analyst/conversations/{id}/messages`**
- Auth: required (owner only)
- Body: `{content: string}`
- Gating: free conversation limited to 20 messages. Subscribed: 100 messages per conversation (warning at 80).
- Returns: SSE stream with events:
  - `event: text` — `{chunk: string}` — streamed text
  - `event: charts` — `{charts: [{type, title, data, xKey, yKeys, colors}]}` — after stream completes
  - `event: citations` — `{citations: [{url, title}]}` — after stream completes
  - `event: done` — `{}` — signals completion
  - `event: error` — `{message: string}` — on failure

### Reports

**`POST /api/analyst/conversations/{id}/reports`**
- Auth: required (owner only)
- Gating: subscription required (even for free conversation)
- Body: `{format: "docx"|"xlsx", title?: string}`
- Returns: `{id, status: "pending"}`

**`GET /api/analyst/reports`**
- Auth: required
- Returns: `{items: [{id, conversation_id, title, format, status, file_size_bytes, created_at}]}`

**`GET /api/analyst/reports/{id}/download`**
- Auth: required (owner only)
- Returns: redirect to S3 signed URL

### Sharing

**`POST /api/analyst/conversations/{id}/share`**
- Auth: required (owner only)
- Generates share_token if not exists
- Returns: `{share_token, url}`

**`GET /api/analyst/shared/{share_token}`**
- Auth: none (public)
- Returns: read-only conversation with messages, charts, citations. No user info beyond display name.

---

## Perplexity Integration

### System Prompt

```
You are a senior venture analyst at Deep Thesis with a data science background.
You have access to a proprietary database of {n} startups and external
market intelligence via Crunchbase and PitchBook.

PORTFOLIO SUMMARY:
- {n} total startups across {sectors} sectors
- Stage distribution: Pre-seed ({n}), Seed ({n}), Series A ({n})...
- Average AI score: {x}/100
- Total tracked funding: ${x}M
- Top sectors by count: {list}
- Score distribution: {histogram buckets}

When the user asks about specific companies in our database, their full
profiles will be provided. For external companies, use your web access
to research Crunchbase, PitchBook, and other sources.

Respond with analysis, not just data. Interpret trends, flag risks,
compare to benchmarks. When data supports it, suggest a chart using
this JSON format:

:::chart
{"type": "bar|line|pie|scatter|area", "title": "...", "data": [...],
 "xKey": "...", "yKeys": ["..."], "colors": ["..."]}
:::

You may include multiple charts per response. Always explain what the
chart shows before or after it.
```

### Context Injection Logic

1. **Every call:** Query DB for portfolio summary (cached in-memory, refreshed every 5 minutes)
2. **Company mentions:** Fuzzy match user message against startups table. Inject full profile for matches.
3. **Sector/stage filters:** When user asks about a sector or stage, inject all matching startups.
4. **Conversation history:** Include last 20 messages for continuity.

### Chart Extraction

After Perplexity's full response is received:
1. Regex extract all `:::chart {JSON} :::` blocks
2. Validate each as valid JSON with required fields (type, data, xKey, yKeys)
3. Strip chart blocks from text content
4. Send charts as separate SSE event
5. Store charts JSON on the analyst_messages record

---

## Frontend Components

### Page Layout (`/insights`)

```
┌─────────────────────────────────────────────────┐
│ Navbar                                          │
├──────────┬──────────────────────────────────────┤
│ Sidebar  │  Chat Area                           │
│          │                                      │
│ [+ New]  │  Message bubbles with inline charts  │
│          │                                      │
│ History  │  ┌─────────────────────────────┐     │
│ - Conv 1 │  │ User: "Show me fintech..."  │     │
│ - Conv 2 │  │                             │     │
│ - Conv 3 │  │ Analyst: "Here's the..."    │     │
│          │  │ [===BAR CHART===]           │     │
│ ──────── │  │ "As you can see..."         │     │
│ Suggested│  └─────────────────────────────┘     │
│ Analyses │                                      │
│ - Sector │  ┌─────────────────────────────┐     │
│ - Scores │  │ Input box          [Send]   │     │
│ - Trends │  │            [Generate Report]│     │
│          │  └─────────────────────────────┘     │
└──────────┴──────────────────────────────────────┘
```

### Components

- **`AnalystSidebar`** — Conversation history list, "New conversation" button, suggested analyses section. Collapsible on mobile (hamburger toggle).
- **`AnalystChat`** — Message list with auto-scroll. Handles SSE streaming. Shows typing indicator during stream.
- **`AnalystMessage`** — Single message bubble. Renders markdown text, inline Recharts components for chart data, citation links at bottom.
- **`AnalystChart`** — Wrapper around Recharts. Accepts chart config JSON, renders appropriate chart type (BarChart, LineChart, PieChart, ScatterChart, AreaChart). Uses design system colors.
- **`AnalystInput`** — Text input with send button. "Generate Report" dropdown (Word/Excel) visible when conversation has content. Disabled during streaming.
- **`ShareModal`** — Shows shareable link with copy button. Triggered from conversation header menu.
- **`/insights/shared/[token]/page.tsx`** — Public read-only view of shared conversation. Same message/chart components, no input box.

### Suggested Analyses (Sidebar)

- "Portfolio sector breakdown"
- "Score distribution analysis"
- "Funding stage pipeline"
- "Top performers deep dive"
- "Market trend comparison"
- "Competitive landscape for [sector]"
- "Due diligence checklist for [company]"

Clicking a suggestion starts a new conversation with that prompt pre-filled.

---

## Report Generation

### Flow

1. User clicks "Generate Report" → picks Word or Excel → enters optional title
2. Frontend calls `POST /api/analyst/conversations/{id}/reports`
3. Backend creates report record (status: pending)
4. Worker picks up report job and assembles the document

### Word (.docx) Contents

- **Cover page:** "Deep Thesis Analyst Report" + title + date
- **Executive summary:** Perplexity-generated summary of conversation findings
- **Sections:** Each analyst response as a section, with headings derived from user questions
- **Charts:** Rendered as PNG images via matplotlib from chart JSON configs
- **Data tables:** Tabular data extracted from responses
- **Sources:** All Perplexity citations as bibliography
- **Footer:** "Generated by Deep Thesis AI Analyst"

### Excel (.xlsx) Contents

- **Summary sheet:** Key metrics and findings
- **Data sheets:** One per chart, containing raw data behind each visualization
- **Charts sheet:** Excel-native charts recreated from chart configs
- **Sources sheet:** Citation URLs with descriptions

### Worker

- Reuses existing worker infrastructure (same container, new task type)
- Report status: pending → generating → complete → failed
- Completed reports uploaded to S3
- Download via signed URL

---

## Subscription Gating

| Action | Free users | Subscribers |
|--------|-----------|-------------|
| First conversation | Yes | Yes |
| Additional conversations | No (402) | Unlimited |
| Messages per conversation | 20 max | 100 max (warning at 80) |
| Report generation | No (402) | Yes |
| View shared conversations | Yes | Yes |
| Share own conversations | Yes | Yes |

**Gating check:** Count user's conversations. If >= 1 and subscription_status != "active", block creation with "Subscribe for $19.99/mo for unlimited analyst access."

**Rate limiting:** 200 Perplexity API calls per user per day for subscribers.

---

## Error Handling

- **Perplexity API failure:** Send SSE error event, save partial message if any text was streamed
- **Invalid chart JSON:** Skip the chart, log warning, still display text
- **Report generation failure:** Mark report as failed with error message, user can retry
- **Rate limit hit:** Return 429 with clear message about limit and reset time
- **Conversation message limit:** Return 400 with message count info, suggest starting new conversation
