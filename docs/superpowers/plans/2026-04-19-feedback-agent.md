# Feedback Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a site-wide floating feedback chat widget that collects user feedback via Claude, auto-summarizes it, and surfaces it in the admin panel.

**Architecture:** Floating React chat bubble on all frontend pages → backend FastAPI endpoints that stream Claude Sonnet responses → JSONB transcript storage in `feedback_sessions` table → admin page with filters, detail view, and AI recommendations.

**Tech Stack:** FastAPI, SQLAlchemy (async), Claude Sonnet via anthropic SDK (streaming), React/Next.js, Tailwind CSS

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/app/models/feedback.py` | Create | FeedbackSession SQLAlchemy model |
| `backend/app/models/__init__.py` | Modify | Register FeedbackSession |
| `backend/app/services/feedback_agent.py` | Create | Claude conversation + summarization logic |
| `backend/app/api/feedback.py` | Create | User-facing feedback endpoints (create, message, complete) |
| `backend/app/api/admin_feedback.py` | Create | Admin feedback endpoints (list, detail) |
| `backend/app/main.py` | Modify | Register feedback + admin_feedback routers |
| `backend/alembic/versions/x3y4z5a6b7c8_add_feedback_sessions_table.py` | Create | DB migration |
| `frontend/components/FeedbackWidget.tsx` | Create | Floating bubble + expandable chat panel |
| `frontend/app/layout.tsx` | Modify | Add FeedbackWidget to global layout |
| `frontend/lib/api.ts` | Modify | Add feedback API methods |
| `frontend/lib/types.ts` | Modify | Add feedback types |
| `admin/app/feedback/page.tsx` | Create | Admin feedback list + detail page |
| `admin/lib/api.ts` | Modify | Add admin feedback API methods |
| `admin/lib/types.ts` | Modify | Add admin feedback types |
| `admin/components/Sidebar.tsx` | Modify | Add "Feedback" nav item |

---

### Task 1: Database Model & Migration

**Files:**
- Create: `backend/app/models/feedback.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/x3y4z5a6b7c8_add_feedback_sessions_table.py`

- [ ] **Step 1: Create the FeedbackSession model**

Create `backend/app/models/feedback.py`:

```python
import enum
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.industry import Base


class FeedbackStatus(enum.Enum):
    active = "active"
    complete = "complete"
    abandoned = "abandoned"


class FeedbackSession(Base):
    __tablename__ = "feedback_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, server_default="active")
    category = Column(String(50))
    severity = Column(String(20))
    area = Column(String(100))
    summary = Column(Text)
    recommendations = Column(JSONB)
    transcript = Column(JSONB)
    page_url = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: Register the model in `__init__.py`**

Add to `backend/app/models/__init__.py`:

At the top imports, add:
```python
from app.models.feedback import FeedbackSession
```

In the `__all__` list, add:
```python
    "FeedbackSession",
```

- [ ] **Step 3: Create the migration**

Create `backend/alembic/versions/x3y4z5a6b7c8_add_feedback_sessions_table.py`:

```python
"""Add feedback_sessions table

Revision ID: x3y4z5a6b7c8
Revises: w2x3y4z5a6b7
Create Date: 2026-04-19
"""
from alembic import op

revision = "x3y4z5a6b7c8"
down_revision = "w2x3y4z5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE feedback_sessions (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id),
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            category VARCHAR(50),
            severity VARCHAR(20),
            area VARCHAR(100),
            summary TEXT,
            recommendations JSONB,
            transcript JSONB,
            page_url VARCHAR(500),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_feedback_sessions_user_id ON feedback_sessions(user_id)")
    op.execute("CREATE INDEX ix_feedback_sessions_status ON feedback_sessions(status)")
    op.execute("CREATE INDEX ix_feedback_sessions_created_at ON feedback_sessions(created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS feedback_sessions")
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/feedback.py backend/app/models/__init__.py backend/alembic/versions/x3y4z5a6b7c8_add_feedback_sessions_table.py
git commit -m "feat(feedback): add FeedbackSession model and migration"
```

---

### Task 2: Feedback Agent Service (Claude Logic)

**Files:**
- Create: `backend/app/services/feedback_agent.py`

- [ ] **Step 1: Create the feedback agent service**

Create `backend/app/services/feedback_agent.py`:

```python
"""Claude-powered feedback collection agent.

Conducts a short feedback conversation (2-4 follow-up questions),
then summarizes with structured tags and recommendations.
"""

import json
import logging
from collections.abc import AsyncGenerator

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)

FEEDBACK_SYSTEM_PROMPT = """\
You are DeepThesis's feedback collection assistant. Your job is to help users report bugs, \
request features, or share suggestions about the DeepThesis platform.

Guidelines:
- Start by understanding what the user wants to share
- Ask 2-4 targeted follow-up questions, ONE at a time, to clarify:
  - For bugs: steps to reproduce, expected vs actual behavior, severity
  - For features: desired behavior, use case, priority
  - For UX issues: what felt wrong, what they expected
- Keep responses short and conversational (1-3 sentences)
- Be appreciative — thank them for their feedback
- After gathering enough context (2-4 exchanges), respond with a brief confirmation \
like "Thanks, I've captured this feedback!" — do NOT ask more questions after that
- Never make promises about timelines or implementation
- Do not discuss topics unrelated to DeepThesis platform feedback
"""

SUMMARIZE_SYSTEM_PROMPT = """\
Analyze this feedback conversation and produce a structured summary.

Return a JSON object with:
- "summary": 2-3 sentence description of the feedback
- "category": exactly one of: "bug", "feature_request", "ux_issue", "performance", "general"
- "severity": exactly one of: "critical", "high", "medium", "low"
- "area": the site section discussed (e.g. "pitch-intelligence", "analyst", "startups", \
"billing", "insights", "navigation", "auth", "general")
- "recommendations": array of 2-5 objects, each with:
  - "title": short action title
  - "description": what to do
  - "priority": 1 (highest) to 5 (lowest)

Return valid JSON only.
"""


async def stream_feedback_response(
    transcript: list[dict],
) -> AsyncGenerator[dict, None]:
    """Stream a Claude response for the feedback conversation.

    Args:
        transcript: list of {"role": "user"|"assistant", "content": str}

    Yields:
        {"type": "text", "chunk": str} for streamed text
        {"type": "done", "full_text": str} when complete
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    messages = [{"role": m["role"], "content": m["content"]} for m in transcript]

    full_text = ""
    try:
        async with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=FEEDBACK_SYSTEM_PROMPT,
            messages=messages,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                    full_text += event.delta.text
                    yield {"type": "text", "chunk": event.delta.text}
    except Exception as e:
        logger.error("Feedback agent streaming error: %s", e)
        yield {"type": "error", "message": str(e)}
        return

    yield {"type": "done", "full_text": full_text}


async def summarize_feedback(transcript: list[dict]) -> dict:
    """Call Claude to summarize a completed feedback conversation.

    Returns dict with summary, category, severity, area, recommendations.
    """
    conversation_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in transcript
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SUMMARIZE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Feedback conversation:\n\n{conversation_text}"}],
    )

    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse feedback summary JSON")
        return {
            "summary": text[:500],
            "category": "general",
            "severity": "medium",
            "area": "general",
            "recommendations": [],
        }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/feedback_agent.py
git commit -m "feat(feedback): add Claude feedback agent service with streaming + summarization"
```

---

### Task 3: User-Facing Feedback API

**Files:**
- Create: `backend/app/api/feedback.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the feedback API endpoints**

Create `backend/app/api/feedback.py`:

```python
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.feedback import FeedbackSession
from app.models.user import User
from app.services.feedback_agent import stream_feedback_response, summarize_feedback

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateSessionRequest(BaseModel):
    page_url: str | None = None


class SendMessageRequest(BaseModel):
    content: str


@router.post("/api/feedback/sessions")
async def create_session(
    body: CreateSessionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = FeedbackSession(
        user_id=user.id,
        status="active",
        page_url=body.page_url,
        transcript=[],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return {"id": str(session.id), "status": "active"}


@router.post("/api/feedback/sessions/{session_id}/messages")
async def send_message(
    session_id: uuid.UUID,
    body: SendMessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FeedbackSession).where(
            FeedbackSession.id == session_id,
            FeedbackSession.user_id == user.id,
        )
    )
    fs = result.scalar_one_or_none()
    if fs is None:
        raise HTTPException(status_code=404, detail="Feedback session not found")
    if fs.status != "active":
        raise HTTPException(status_code=400, detail="Feedback session is not active")

    # Append user message to transcript
    transcript = list(fs.transcript or [])
    transcript.append({
        "role": "user",
        "content": body.content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    fs.transcript = transcript
    await db.commit()

    # Capture for streaming closure
    fs_id = fs.id
    # Build messages for Claude (strip timestamps)
    messages = [{"role": m["role"], "content": m["content"]} for m in transcript]

    async def event_stream():
        full_text = ""
        try:
            async for event in stream_feedback_response(messages):
                etype = event["type"]
                if etype == "text":
                    full_text += event["chunk"]
                    yield f"event: text\ndata: {json.dumps({'chunk': event['chunk']})}\n\n"
                elif etype == "error":
                    yield f"event: error\ndata: {json.dumps({'message': event['message']})}\n\n"
                elif etype == "done":
                    full_text = event.get("full_text", full_text)
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

        # Save assistant message to transcript
        if full_text:
            from app.db.session import async_session
            async with async_session() as save_db:
                save_result = await save_db.execute(
                    select(FeedbackSession).where(FeedbackSession.id == fs_id)
                )
                save_fs = save_result.scalar_one_or_none()
                if save_fs:
                    updated_transcript = list(save_fs.transcript or [])
                    updated_transcript.append({
                        "role": "assistant",
                        "content": full_text,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    save_fs.transcript = updated_transcript
                    await save_db.commit()

        yield f"event: done\ndata: {json.dumps({'full_text': full_text})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.patch("/api/feedback/sessions/{session_id}/complete")
async def complete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FeedbackSession).where(
            FeedbackSession.id == session_id,
            FeedbackSession.user_id == user.id,
        )
    )
    fs = result.scalar_one_or_none()
    if fs is None:
        raise HTTPException(status_code=404, detail="Feedback session not found")

    transcript = list(fs.transcript or [])
    if len(transcript) < 2:
        # Too short to summarize — just mark complete
        fs.status = "complete"
        fs.summary = transcript[0]["content"] if transcript else "No content"
        fs.category = "general"
        fs.severity = "medium"
        fs.area = "general"
        fs.recommendations = []
        await db.commit()
        return {"id": str(fs.id), "status": "complete"}

    # Summarize with Claude
    summary_data = await summarize_feedback(transcript)

    fs.status = "complete"
    fs.summary = summary_data.get("summary", "")
    fs.category = summary_data.get("category", "general")
    fs.severity = summary_data.get("severity", "medium")
    fs.area = summary_data.get("area", "general")
    fs.recommendations = summary_data.get("recommendations", [])
    await db.commit()

    return {"id": str(fs.id), "status": "complete"}


@router.patch("/api/feedback/sessions/{session_id}/abandon")
async def abandon_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FeedbackSession).where(
            FeedbackSession.id == session_id,
            FeedbackSession.user_id == user.id,
        )
    )
    fs = result.scalar_one_or_none()
    if fs is None:
        raise HTTPException(status_code=404, detail="Feedback session not found")

    fs.status = "abandoned"
    await db.commit()

    return {"id": str(fs.id), "status": "abandoned"}
```

- [ ] **Step 2: Register the router in main.py**

In `backend/app/main.py`, add after the pitch_intelligence import (line 69):

```python
from app.api.feedback import router as feedback_router
```

And after `app.include_router(pitch_intelligence_router)` (line 123), add:

```python
app.include_router(feedback_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/feedback.py backend/app/main.py
git commit -m "feat(feedback): add user-facing feedback API with streaming chat"
```

---

### Task 4: Admin Feedback API

**Files:**
- Create: `backend/app/api/admin_feedback.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the admin feedback endpoints**

Create `backend/app/api/admin_feedback.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.feedback import FeedbackSession
from app.models.user import User

router = APIRouter()


def _feedback_to_dict(fs: FeedbackSession, user: User | None = None) -> dict:
    d = {
        "id": str(fs.id),
        "user_id": str(fs.user_id),
        "status": fs.status,
        "category": fs.category,
        "severity": fs.severity,
        "area": fs.area,
        "summary": fs.summary,
        "recommendations": fs.recommendations,
        "transcript": fs.transcript,
        "page_url": fs.page_url,
        "created_at": fs.created_at.isoformat() if fs.created_at else None,
        "updated_at": fs.updated_at.isoformat() if fs.updated_at else None,
    }
    if user:
        d["user_name"] = user.name
        d["user_email"] = user.email
    return d


@router.get("/api/admin/feedback")
async def list_feedback(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    status: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    area: str | None = None,
):
    query = select(FeedbackSession, User).join(User, FeedbackSession.user_id == User.id)

    if status:
        query = query.where(FeedbackSession.status == status)
    if category:
        query = query.where(FeedbackSession.category == category)
    if severity:
        query = query.where(FeedbackSession.severity == severity)
    if area:
        query = query.where(FeedbackSession.area == area)

    # Count
    count_query = select(func.count()).select_from(FeedbackSession)
    if status:
        count_query = count_query.where(FeedbackSession.status == status)
    if category:
        count_query = count_query.where(FeedbackSession.category == category)
    if severity:
        count_query = count_query.where(FeedbackSession.severity == severity)
    if area:
        count_query = count_query.where(FeedbackSession.area == area)
    total = (await db.execute(count_query)).scalar() or 0

    # Paginate
    query = query.order_by(FeedbackSession.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    rows = result.all()

    items = [_feedback_to_dict(fs, user) for fs, user in rows]

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "items": items,
    }


@router.get("/api/admin/feedback/{feedback_id}")
async def get_feedback(
    feedback_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FeedbackSession, User)
        .join(User, FeedbackSession.user_id == User.id)
        .where(FeedbackSession.id == feedback_id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Feedback not found")

    fs, user = row
    return _feedback_to_dict(fs, user)
```

- [ ] **Step 2: Register the admin router in main.py**

In `backend/app/main.py`, add after the feedback_router import:

```python
from app.api.admin_feedback import router as admin_feedback_router
```

And after `app.include_router(feedback_router)`:

```python
app.include_router(admin_feedback_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/admin_feedback.py backend/app/main.py
git commit -m "feat(feedback): add admin feedback API with pagination and filters"
```

---

### Task 5: Frontend Types & API Methods

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add feedback types**

Add to the end of `frontend/lib/types.ts`:

```typescript
// ── Feedback ──────────────────────────────────────────────────────────

export interface FeedbackMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface FeedbackSessionResponse {
  id: string;
  status: string;
}
```

- [ ] **Step 2: Add feedback API methods**

Add to the `api` object in `frontend/lib/api.ts`, before the closing `};`:

```typescript
  // ── Feedback ─────────────────────────────────────────────────────────

  createFeedbackSession: async (
    token: string,
    pageUrl?: string,
  ): Promise<{ id: string; status: string }> => {
    return apiFetch("/api/feedback/sessions", {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ page_url: pageUrl || null }),
    });
  },

  sendFeedbackMessage(token: string, sessionId: string, content: string) {
    const url = `${API_URL}/api/feedback/sessions/${sessionId}/messages`;
    return fetch(url, {
      method: "POST",
      headers: {
        ...authHeaders(token),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ content }),
    });
  },

  completeFeedbackSession: async (
    token: string,
    sessionId: string,
  ): Promise<{ id: string; status: string }> => {
    return apiFetch(`/api/feedback/sessions/${sessionId}/complete`, {
      method: "PATCH",
      headers: authHeaders(token),
    });
  },

  abandonFeedbackSession: async (
    token: string,
    sessionId: string,
  ): Promise<{ id: string; status: string }> => {
    return apiFetch(`/api/feedback/sessions/${sessionId}/abandon`, {
      method: "PATCH",
      headers: authHeaders(token),
    });
  },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat(feedback): add frontend feedback types and API methods"
```

---

### Task 6: Feedback Chat Widget

**Files:**
- Create: `frontend/components/FeedbackWidget.tsx`
- Modify: `frontend/app/layout.tsx`

- [ ] **Step 1: Create the FeedbackWidget component**

Create `frontend/components/FeedbackWidget.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const OPENING_MESSAGE: Message = {
  role: "assistant",
  content:
    "What's on your mind? I'm here to collect feedback about DeepThesis — bugs, feature requests, or anything that could be better.",
};

export function FeedbackWidget() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const pathname = usePathname();

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([OPENING_MESSAGE]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [completed, setCompleted] = useState(false);
  const [messageCount, setMessageCount] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = useCallback(async () => {
    if (!token || !input.trim() || streaming) return;

    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setStreaming(true);

    try {
      // Create session on first message
      let sid = sessionId;
      if (!sid) {
        const { id } = await api.createFeedbackSession(token, pathname);
        sid = id;
        setSessionId(id);
      }

      // Send message and stream response
      const response = await api.sendFeedbackMessage(token, sid, userMessage);
      if (!response.ok) {
        throw new Error("Failed to send message");
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response stream");

      const decoder = new TextDecoder();
      let assistantText = "";
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6);
            try {
              const parsed = JSON.parse(data);
              if (parsed.chunk) {
                assistantText += parsed.chunk;
                setMessages((prev) => {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    role: "assistant",
                    content: assistantText,
                  };
                  return updated;
                });
              }
            } catch {
              // skip unparseable
            }
          }
        }
      }

      const newCount = messageCount + 1;
      setMessageCount(newCount);

      // Auto-complete after 3+ user messages (agent has had enough context)
      if (newCount >= 3) {
        try {
          await api.completeFeedbackSession(token, sid);
          setCompleted(true);
        } catch {
          // non-critical
        }
      }
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Sorry, something went wrong. Please try again." },
      ]);
    } finally {
      setStreaming(false);
    }
  }, [token, input, streaming, sessionId, pathname, messageCount]);

  const handleClose = useCallback(async () => {
    // Abandon if not completed and has a session
    if (sessionId && !completed) {
      try {
        if (messageCount >= 2) {
          await api.completeFeedbackSession(token!, sessionId);
        } else {
          await api.abandonFeedbackSession(token!, sessionId);
        }
      } catch {
        // non-critical
      }
    }
    setOpen(false);
    // Reset state for next time
    setMessages([OPENING_MESSAGE]);
    setInput("");
    setSessionId(null);
    setCompleted(false);
    setMessageCount(0);
  }, [sessionId, completed, token, messageCount]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!session) return null;

  return (
    <>
      {/* Floating bubble */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 flex h-12 w-12 items-center justify-center rounded-full bg-accent text-white shadow-lg hover:bg-accent/90 transition"
          aria-label="Share feedback"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </button>
      )}

      {/* Expanded panel */}
      {open && (
        <div className="fixed bottom-6 right-6 z-50 flex w-[380px] flex-col rounded-xl border border-border bg-surface shadow-2xl"
          style={{ height: "500px" }}
        >
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <h3 className="text-sm font-medium text-text-primary">Share Feedback</h3>
            <button
              onClick={handleClose}
              className="text-text-tertiary hover:text-text-primary transition"
              aria-label="Close feedback"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                    msg.role === "user"
                      ? "bg-accent text-white"
                      : "bg-surface-alt text-text-primary"
                  }`}
                >
                  {msg.content || (
                    <span className="inline-block animate-pulse text-text-tertiary">...</span>
                  )}
                </div>
              </div>
            ))}
            {completed && (
              <div className="text-center text-xs text-text-tertiary py-2">
                Feedback submitted. Thank you!
              </div>
            )}
          </div>

          {/* Input */}
          {!completed && (
            <div className="border-t border-border px-3 py-3">
              <div className="flex items-end gap-2">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Type your feedback..."
                  rows={1}
                  disabled={streaming}
                  className="flex-1 resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none disabled:opacity-50"
                />
                <button
                  onClick={handleSend}
                  disabled={!input.trim() || streaming}
                  className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-white hover:bg-accent/90 transition disabled:opacity-40 disabled:cursor-not-allowed"
                  aria-label="Send"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="22" y1="2" x2="11" y2="13" />
                    <polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 2: Add FeedbackWidget to the global layout**

In `frontend/app/layout.tsx`, add the import after the Navbar import:

```typescript
import { FeedbackWidget } from "@/components/FeedbackWidget";
```

And add `<FeedbackWidget />` right after `</main>` and before the closing `</Providers>`:

```tsx
        <Providers>
          <Navbar />
          <main className="mx-auto max-w-6xl px-6 lg:px-8 py-12">
            {children}
          </main>
          <FeedbackWidget />
        </Providers>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/FeedbackWidget.tsx frontend/app/layout.tsx
git commit -m "feat(feedback): add floating feedback chat widget to global layout"
```

---

### Task 7: Admin Feedback Types & API

**Files:**
- Modify: `admin/lib/types.ts`
- Modify: `admin/lib/api.ts`

- [ ] **Step 1: Add admin feedback types**

Add to the end of `admin/lib/types.ts`:

```typescript
// ── Feedback ──────────────────────────────────────────────────────────

export interface FeedbackRecommendation {
  title: string;
  description: string;
  priority: number;
}

export interface FeedbackTranscriptMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface FeedbackItem {
  id: string;
  user_id: string;
  user_name: string | null;
  user_email: string | null;
  status: string;
  category: string | null;
  severity: string | null;
  area: string | null;
  summary: string | null;
  recommendations: FeedbackRecommendation[] | null;
  transcript: FeedbackTranscriptMessage[] | null;
  page_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface FeedbackListResponse {
  total: number;
  page: number;
  per_page: number;
  pages: number;
  items: FeedbackItem[];
}
```

- [ ] **Step 2: Add admin feedback API methods**

Add to the `adminApi` object in `admin/lib/api.ts`:

First add the import at the top alongside existing imports:

```typescript
import type {
  // ... existing imports ...
  FeedbackItem,
  FeedbackListResponse,
} from "./types";
```

Then add methods to the `adminApi` object:

```typescript
  // Feedback
  getFeedbackList: (token: string, params?: {
    page?: number;
    status?: string;
    category?: string;
    severity?: string;
    area?: string;
  }) => {
    const sp = new URLSearchParams();
    if (params?.page) sp.set("page", String(params.page));
    if (params?.status) sp.set("status", params.status);
    if (params?.category) sp.set("category", params.category);
    if (params?.severity) sp.set("severity", params.severity);
    if (params?.area) sp.set("area", params.area);
    const qs = sp.toString();
    return apiFetch<FeedbackListResponse>(`/api/admin/feedback${qs ? `?${qs}` : ""}`, token);
  },

  getFeedbackDetail: (token: string, id: string) =>
    apiFetch<FeedbackItem>(`/api/admin/feedback/${id}`, token),
```

- [ ] **Step 3: Commit**

```bash
git add admin/lib/types.ts admin/lib/api.ts
git commit -m "feat(feedback): add admin feedback types and API methods"
```

---

### Task 8: Admin Feedback Page

**Files:**
- Create: `admin/app/feedback/page.tsx`
- Modify: `admin/components/Sidebar.tsx`

- [ ] **Step 1: Create the admin feedback page**

Create `admin/app/feedback/page.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { adminApi } from "@/lib/api";
import type { FeedbackItem, FeedbackListResponse } from "@/lib/types";

const CATEGORIES = ["bug", "feature_request", "ux_issue", "performance", "general"];
const SEVERITIES = ["critical", "high", "medium", "low"];
const STATUSES = ["active", "complete", "abandoned"];

const SEVERITY_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-700",
  high: "bg-orange-100 text-orange-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-green-100 text-green-700",
};

const CATEGORY_LABELS: Record<string, string> = {
  bug: "Bug",
  feature_request: "Feature",
  ux_issue: "UX Issue",
  performance: "Performance",
  general: "General",
};

export default function FeedbackPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;

  const [data, setData] = useState<FeedbackListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<FeedbackItem | null>(null);
  const [filters, setFilters] = useState<{
    status?: string;
    category?: string;
    severity?: string;
  }>({});
  const [page, setPage] = useState(1);

  const fetchData = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const result = await adminApi.getFeedbackList(token, { page, ...filters });
      setData(result);
    } catch (e) {
      console.error("Failed to load feedback", e);
    }
    setLoading(false);
  }, [token, page, filters]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSelectItem = async (item: FeedbackItem) => {
    if (!token) return;
    try {
      const detail = await adminApi.getFeedbackDetail(token, item.id);
      setSelected(detail);
    } catch {
      setSelected(item);
    }
  };

  if (selected) {
    return (
      <div className="p-6">
        <button
          onClick={() => setSelected(null)}
          className="mb-4 text-sm text-text-secondary hover:text-text-primary transition"
        >
          &larr; Back to list
        </button>

        <div className="space-y-6">
          {/* Summary */}
          <div className="rounded-lg border border-border bg-surface p-5">
            <h2 className="text-lg font-medium text-text-primary mb-2">Summary</h2>
            <p className="text-text-secondary text-sm">{selected.summary || "No summary available"}</p>
          </div>

          {/* Tags */}
          <div className="flex flex-wrap gap-2">
            {selected.category && (
              <span className="rounded-full bg-blue-100 text-blue-700 px-3 py-1 text-xs font-medium">
                {CATEGORY_LABELS[selected.category] || selected.category}
              </span>
            )}
            {selected.severity && (
              <span className={`rounded-full px-3 py-1 text-xs font-medium ${SEVERITY_COLORS[selected.severity] || "bg-gray-100 text-gray-700"}`}>
                {selected.severity}
              </span>
            )}
            {selected.area && (
              <span className="rounded-full bg-purple-100 text-purple-700 px-3 py-1 text-xs font-medium">
                {selected.area}
              </span>
            )}
            <span className={`rounded-full px-3 py-1 text-xs font-medium ${
              selected.status === "complete" ? "bg-green-100 text-green-700"
              : selected.status === "abandoned" ? "bg-gray-100 text-gray-500"
              : "bg-yellow-100 text-yellow-700"
            }`}>
              {selected.status}
            </span>
          </div>

          {/* Recommendations */}
          {selected.recommendations && selected.recommendations.length > 0 && (
            <div className="rounded-lg border border-border bg-surface p-5">
              <h2 className="text-lg font-medium text-text-primary mb-3">AI Recommendations</h2>
              <div className="space-y-3">
                {selected.recommendations
                  .sort((a, b) => a.priority - b.priority)
                  .map((rec, i) => (
                    <div key={i} className="flex gap-3">
                      <span className="flex-shrink-0 flex items-center justify-center h-6 w-6 rounded-full bg-accent/10 text-accent text-xs font-medium">
                        {rec.priority}
                      </span>
                      <div>
                        <p className="text-sm font-medium text-text-primary">{rec.title}</p>
                        <p className="text-sm text-text-secondary mt-0.5">{rec.description}</p>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="rounded-lg border border-border bg-surface p-5">
            <h2 className="text-lg font-medium text-text-primary mb-2">Details</h2>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-text-tertiary">User:</span>{" "}
                <span className="text-text-primary">{selected.user_name || "Unknown"}</span>
              </div>
              <div>
                <span className="text-text-tertiary">Email:</span>{" "}
                <span className="text-text-primary">{selected.user_email || "—"}</span>
              </div>
              <div>
                <span className="text-text-tertiary">Page:</span>{" "}
                <span className="text-text-primary">{selected.page_url || "—"}</span>
              </div>
              <div>
                <span className="text-text-tertiary">Date:</span>{" "}
                <span className="text-text-primary">
                  {selected.created_at ? new Date(selected.created_at).toLocaleString() : "—"}
                </span>
              </div>
            </div>
          </div>

          {/* Transcript */}
          {selected.transcript && selected.transcript.length > 0 && (
            <div className="rounded-lg border border-border bg-surface p-5">
              <h2 className="text-lg font-medium text-text-primary mb-3">Conversation</h2>
              <div className="space-y-3">
                {selected.transcript.map((msg, i) => (
                  <div
                    key={i}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                        msg.role === "user"
                          ? "bg-accent/10 text-text-primary"
                          : "bg-surface-alt text-text-primary"
                      }`}
                    >
                      <p className="text-xs text-text-tertiary mb-1">
                        {msg.role === "user" ? "User" : "Agent"}
                      </p>
                      {msg.content}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <h1 className="text-xl font-serif text-text-primary mb-6">User Feedback</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <select
          value={filters.status || ""}
          onChange={(e) => { setFilters((f) => ({ ...f, status: e.target.value || undefined })); setPage(1); }}
          className="rounded border border-border bg-surface px-3 py-1.5 text-sm text-text-primary"
        >
          <option value="">All Statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          value={filters.category || ""}
          onChange={(e) => { setFilters((f) => ({ ...f, category: e.target.value || undefined })); setPage(1); }}
          className="rounded border border-border bg-surface px-3 py-1.5 text-sm text-text-primary"
        >
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{CATEGORY_LABELS[c] || c}</option>
          ))}
        </select>
        <select
          value={filters.severity || ""}
          onChange={(e) => { setFilters((f) => ({ ...f, severity: e.target.value || undefined })); setPage(1); }}
          className="rounded border border-border bg-surface px-3 py-1.5 text-sm text-text-primary"
        >
          <option value="">All Severities</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      {loading ? (
        <p className="text-text-tertiary text-sm">Loading...</p>
      ) : !data || data.items.length === 0 ? (
        <p className="text-text-tertiary text-sm">No feedback found.</p>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-alt text-left">
                  <th className="px-4 py-2 font-medium text-text-secondary">Date</th>
                  <th className="px-4 py-2 font-medium text-text-secondary">User</th>
                  <th className="px-4 py-2 font-medium text-text-secondary">Category</th>
                  <th className="px-4 py-2 font-medium text-text-secondary">Severity</th>
                  <th className="px-4 py-2 font-medium text-text-secondary">Area</th>
                  <th className="px-4 py-2 font-medium text-text-secondary">Summary</th>
                  <th className="px-4 py-2 font-medium text-text-secondary">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr
                    key={item.id}
                    onClick={() => handleSelectItem(item)}
                    className="border-b border-border hover:bg-hover-row cursor-pointer transition"
                  >
                    <td className="px-4 py-2 text-text-tertiary whitespace-nowrap">
                      {new Date(item.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-2 text-text-primary">
                      {item.user_name || item.user_email || "Unknown"}
                    </td>
                    <td className="px-4 py-2">
                      {item.category && (
                        <span className="rounded-full bg-blue-100 text-blue-700 px-2 py-0.5 text-xs">
                          {CATEGORY_LABELS[item.category] || item.category}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      {item.severity && (
                        <span className={`rounded-full px-2 py-0.5 text-xs ${SEVERITY_COLORS[item.severity] || "bg-gray-100 text-gray-700"}`}>
                          {item.severity}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-text-secondary text-xs">
                      {item.area || "—"}
                    </td>
                    <td className="px-4 py-2 text-text-secondary max-w-xs truncate">
                      {item.summary || "—"}
                    </td>
                    <td className="px-4 py-2">
                      <span className={`text-xs ${
                        item.status === "complete" ? "text-green-600"
                        : item.status === "abandoned" ? "text-gray-400"
                        : "text-yellow-600"
                      }`}>
                        {item.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {data.pages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <p className="text-xs text-text-tertiary">
                Page {data.page} of {data.pages} ({data.total} total)
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-3 py-1 text-sm rounded border border-border hover:bg-hover-row disabled:opacity-40 transition"
                >
                  Prev
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                  disabled={page === data.pages}
                  className="px-3 py-1 text-sm rounded border border-border hover:bg-hover-row disabled:opacity-40 transition"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add Feedback to admin sidebar**

In `admin/components/Sidebar.tsx`, add to the `NAV_ITEMS` array after the `Users` entry:

```typescript
  { href: "/feedback", label: "Feedback" },
```

So the array becomes:
```typescript
const NAV_ITEMS = [
  { href: "/", label: "Triage" },
  { href: "/scout", label: "Scout" },
  { href: "/batch", label: "Batch" },
  { href: "/edgar", label: "EDGAR" },
  { href: "/startups", label: "Startups" },
  { href: "/investors", label: "Investors" },
  { href: "/experts", label: "Experts" },
  { href: "/templates", label: "Templates" },
  { href: "/users", label: "Users" },
  { href: "/feedback", label: "Feedback" },
];
```

- [ ] **Step 3: Commit**

```bash
git add admin/app/feedback/page.tsx admin/components/Sidebar.tsx
git commit -m "feat(feedback): add admin feedback page with table, filters, and detail view"
```
