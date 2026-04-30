# Site-Wide Feedback Agent — Design Spec

**Date:** 2026-04-19
**Status:** Design approved

## Overview

A floating chat widget available to all authenticated users that collects structured feedback about the DeepThesis platform. The agent uses Claude Sonnet to conduct 2-4 targeted follow-up questions, then auto-summarizes the conversation into a structured feedback record with category, severity, area tags, and AI-generated improvement recommendations. Superadmins view all feedback in a dedicated admin panel page.

## Access

- **Submit feedback:** Any authenticated user
- **View feedback:** Superadmin only (admin panel)

## Architecture

### Components

1. **Floating chat widget** — React component in the global layout, visible on all pages
2. **Backend API** — FastAPI endpoints for creating/completing feedback sessions, streaming Claude responses
3. **Admin feedback page** — Table view with filters, detail view with summary/recommendations/transcript

### Data Flow

```
User clicks bubble → Opens chat panel → Types feedback
  → POST /api/feedback/sessions (creates session)
  → POST /api/feedback/sessions/{id}/messages (streams Claude response)
  → Claude asks 2-4 follow-up questions
  → User responds to each
  → After sufficient context, Claude generates summary
  → PATCH /api/feedback/sessions/{id}/complete (stores summary + tags)
  → Superadmin views in admin panel
```

### Storage

Single `feedback_sessions` table with JSONB columns for transcript and tags:

```sql
CREATE TABLE feedback_sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, complete, abandoned
    category VARCHAR(50),        -- bug, feature_request, ux_issue, performance, general
    severity VARCHAR(20),        -- critical, high, medium, low
    area VARCHAR(100),           -- e.g. "pitch-intelligence", "analyst", "startups", "billing"
    summary TEXT,                -- AI-generated 2-3 sentence summary
    recommendations JSONB,       -- AI-generated improvement steps [{title, description, priority}]
    transcript JSONB,            -- [{role: "user"|"assistant", content: string, timestamp: string}]
    page_url VARCHAR(500),       -- URL where feedback was initiated
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Chat Widget UX

### Collapsed State

- Small circular bubble (48px) fixed to bottom-right corner (24px margin)
- Chat icon, subtle pulse animation on first visit
- Z-index high enough to float above all page content

### Expanded State

- Panel: 380px wide × 500px tall, anchored to bottom-right
- Header: "Share Feedback" title + close button
- Message area: scrollable conversation thread
- Input: text field + send button
- Smooth open/close animation

### Conversation Flow

1. **Opening message** (from agent): "What's on your mind? I'm here to collect feedback about DeepThesis — bugs, feature requests, or anything that could be better."
2. **User describes issue** — free-form text
3. **Agent asks 2-4 follow-up questions** — one at a time, to clarify category, severity, reproduction steps (for bugs), or desired behavior (for features)
4. **Agent confirms understanding** — presents a brief summary back to user: "Got it — I've logged this as [category]. Thanks for the feedback!"
5. **Session auto-completes** — summary, tags, and recommendations stored

### Edge Cases

- User closes mid-conversation → session marked "abandoned", partial transcript saved
- User navigates to different page → widget stays open, continues conversation
- User not authenticated → bubble hidden entirely

## Admin Feedback Page

### Location

`/admin/feedback` — superadmin only

### Table View

| Column | Content |
|--------|---------|
| Date | Created timestamp |
| User | Name + email |
| Category | Bug / Feature / UX / Performance / General |
| Severity | Critical / High / Medium / Low |
| Area | Site section tag |
| Summary | Truncated AI summary |
| Status | Active / Complete / Abandoned |

- Filterable by category, severity, area, status, date range
- Sortable by date (default: newest first)
- Click row → detail view

### Detail View

- **Summary card** — Full AI-generated summary
- **Recommendations** — Ordered list of AI improvement suggestions with priority
- **Tags** — Category, severity, area displayed as pills
- **Transcript** — Full conversation thread, styled like the chat widget
- **Metadata** — User info, page URL, timestamps

## Claude Integration

### System Prompt

The feedback agent uses Claude Sonnet with a system prompt that:
- Identifies itself as a DeepThesis feedback collector
- Asks targeted follow-up questions (2-4 max, not more)
- Classifies feedback into category/severity/area
- Generates a concise summary and actionable recommendations
- Maintains a professional, appreciative tone

### Summarization

After the conversation reaches sufficient depth (agent has asked follow-ups and user responded), the backend calls Claude one final time with the full transcript to generate:
- `summary`: 2-3 sentence description of the feedback
- `category`: one of bug, feature_request, ux_issue, performance, general
- `severity`: critical, high, medium, low
- `area`: the site section being discussed
- `recommendations`: 2-5 actionable improvement steps

This happens server-side when the session is completed.

## API Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/feedback/sessions` | user | Create new feedback session |
| POST | `/api/feedback/sessions/{id}/messages` | user | Send message, get streamed Claude response |
| PATCH | `/api/feedback/sessions/{id}/complete` | user | Trigger summarization + close session |
| GET | `/api/admin/feedback` | superadmin | List all feedback (paginated, filterable) |
| GET | `/api/admin/feedback/{id}` | superadmin | Get single feedback detail |

## File Structure

### Backend
- `backend/app/models/feedback.py` — FeedbackSession SQLAlchemy model
- `backend/app/api/feedback.py` — User-facing feedback endpoints
- `backend/app/api/admin_feedback.py` — Admin feedback endpoints
- `backend/app/services/feedback_agent.py` — Claude conversation + summarization logic
- `backend/alembic/versions/x3y4z5a6b7c8_add_feedback_sessions_table.py` — Migration

### Frontend
- `frontend/components/FeedbackWidget.tsx` — Floating bubble + expandable chat panel
- `frontend/lib/api.ts` — Add feedback API methods
- `frontend/lib/types.ts` — Add feedback types
- `admin/app/feedback/page.tsx` — Admin feedback list + detail page
- `admin/lib/api.ts` — Add admin feedback API methods
- `admin/lib/types.ts` — Add admin feedback types
