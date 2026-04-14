# Notifications, Branded Reports & Report History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a notification system (bell icon + dropdown), scope report generation to the last assistant message, brand all report templates with Deep Thesis styling, and add a Reports tab to the insights sidebar.

**Architecture:** New `Notification` model + REST endpoints. Minimal surgical changes to existing `analyst_reports.py` (filter messages, update colors) and `analysis_worker.py` (add 3 lines for notification creation). New `NotificationBell` frontend component. New tab in `AnalystSidebar`. All changes are additive — no restructuring of working code.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), React/Next.js/TypeScript (frontend), PostgreSQL, Alembic migrations, matplotlib/reportlab/python-docx/python-pptx/openpyxl (report generation)

**CRITICAL CONSTRAINT:** Do NOT restructure or make hacky changes to existing insights or analyze functionality. All changes must be additive and surgical. The insights chat, analyze pipeline, and all existing endpoints must continue working exactly as they do now.

---

### Task 1: Notification Model & Migration

**Files:**
- Create: `backend/app/models/notification.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/q5r6s7t8u9v0_add_notifications_table.py`

- [ ] **Step 1: Create the Notification model**

Create `backend/app/models/notification.py`:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM, UUID

from app.models.industry import Base


class NotificationType(enum.Enum):
    analysis_complete = "analysis_complete"
    report_ready = "report_ready"


notificationtype_enum = ENUM(
    "analysis_complete", "report_ready",
    name="notificationtype", create_type=False,
)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    type = Column(notificationtype_enum, nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(String(500), nullable=False)
    link = Column(String(500), nullable=False)
    read = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
```

- [ ] **Step 2: Register model in `__init__.py`**

Add to `backend/app/models/__init__.py`, after the `PitchAnalysis` import line:

```python
from app.models.notification import Notification
```

Add `"Notification"` to the `__all__` list.

- [ ] **Step 3: Create Alembic migration**

Create `backend/alembic/versions/q5r6s7t8u9v0_add_notifications_table.py`:

```python
"""Add notifications table

Revision ID: q5r6s7t8u9v0
Revises: p4q5r6s7t8u9
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "q5r6s7t8u9v0"
down_revision = "p4q5r6s7t8u9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create notification type enum
    op.execute(
        "DO $$ BEGIN CREATE TYPE notificationtype AS ENUM ('analysis_complete', 'report_ready'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.Enum("analysis_complete", "report_ready", name="notificationtype", create_type=False), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("link", sa.String(500), nullable=False),
        sa.Column("read", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_notifications_user_read_created", "notifications", ["user_id", "read", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_notifications_user_read_created", table_name="notifications")
    op.drop_table("notifications")
    op.execute("DROP TYPE IF EXISTS notificationtype")
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/notification.py backend/app/models/__init__.py backend/alembic/versions/q5r6s7t8u9v0_add_notifications_table.py
git commit -m "feat: add Notification model and migration"
```

---

### Task 2: Notification API Endpoints

**Files:**
- Create: `backend/app/api/notifications.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the notifications router**

Create `backend/app/api/notifications.py`:

```python
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.notification import Notification
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/notifications")
async def list_notifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get recent notifications
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(20)
    )
    notifications = result.scalars().all()

    # Get unread count
    count_result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read == False)
    )
    unread_count = count_result.scalar() or 0

    return {
        "items": [
            {
                "id": str(n.id),
                "type": n.type.value if hasattr(n.type, "value") else n.type,
                "title": n.title,
                "message": n.message,
                "link": n.link,
                "read": n.read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in notifications
        ],
        "unread_count": unread_count,
    }


@router.patch("/api/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(404, "Notification not found")

    notification.read = True
    await db.commit()
    return {"success": True}


@router.post("/api/notifications/read-all")
async def mark_all_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read == False)
        .values(read=True)
    )
    await db.commit()
    return {"success": True}
```

- [ ] **Step 2: Register the router in `main.py`**

In `backend/app/main.py`, add after the `from app.api.billing import router as billing_router` line:

```python
from app.api.notifications import router as notifications_router
```

Add after `app.include_router(billing_router)`:

```python
app.include_router(notifications_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/notifications.py backend/app/main.py
git commit -m "feat: add notification API endpoints"
```

---

### Task 3: Notification Creation on Analysis Complete

**Files:**
- Modify: `backend/app/services/analysis_worker.py` (add 3 lines only)

**CRITICAL:** This is a surgical addition. Do NOT restructure any existing code in this file. Add only the import and the 3 notification lines at the exact locations specified.

- [ ] **Step 1: Add import at top of file**

In `backend/app/services/analysis_worker.py`, add after the existing imports (after line 22 `from app.services.document_extractor import consolidate_documents, extract_text`):

```python
from app.models.notification import Notification, NotificationType
```

- [ ] **Step 2: Add notification creation after analysis completes**

In `backend/app/services/analysis_worker.py`, inside `_process_job()`, find lines 280-283:

```python
        analysis.status = AnalysisStatus.complete
        analysis.completed_at = datetime.now(timezone.utc)
        await db.commit()

    logger.info(f"Analysis complete for {company_name}: score={scoring['overall_score']}")
```

Add the notification creation between `await db.commit()` and the `logger.info` line, so it becomes:

```python
        analysis.status = AnalysisStatus.complete
        analysis.completed_at = datetime.now(timezone.utc)
        await db.commit()

        # Create notification for user
        notification = Notification(
            user_id=analysis.user_id,
            type=NotificationType.analysis_complete,
            title="Analysis complete",
            message=company_name or "Your startup analysis",
            link=f"/analyze/{analysis.id}",
        )
        db.add(notification)
        await db.commit()

    logger.info(f"Analysis complete for {company_name}: score={scoring['overall_score']}")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/analysis_worker.py
git commit -m "feat: create notification when analysis completes"
```

---

### Task 4: Notification Creation on Report Ready

**Files:**
- Modify: `backend/app/services/analyst_reports.py` (add notification import + 8 lines at end of generate_report)

**CRITICAL:** Surgical addition only. Do NOT change any existing logic. Add import at top, add notification lines after the existing success commit.

- [ ] **Step 1: Add import**

In `backend/app/services/analyst_reports.py`, add after line 34 (`from app.models.analyst import ...`):

```python
from app.models.notification import Notification, NotificationType
```

- [ ] **Step 2: Add notification creation after report completes**

In `backend/app/services/analyst_reports.py`, inside `generate_report()`, find lines 631-635:

```python
            report.status = ReportGenStatus.complete.value
            await db.commit()

            logger.info("Report %s generated: %s (%d bytes)", report_id, s3_key, len(file_bytes))
```

Add notification creation between `await db.commit()` and the `logger.info`, so it becomes:

```python
            report.status = ReportGenStatus.complete.value
            await db.commit()

            # Create notification for user
            fmt_label = ext.upper()
            notification = Notification(
                user_id=report.user_id,
                type=NotificationType.report_ready,
                title="Report ready",
                message=f"{fmt_label} report",
                link=f"/api/analyst/reports/{report.id}/download",
            )
            db.add(notification)
            await db.commit()

            logger.info("Report %s generated: %s (%d bytes)", report_id, s3_key, len(file_bytes))
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/analyst_reports.py
git commit -m "feat: create notification when report generation completes"
```

---

### Task 5: Scope Report Generation to Last Assistant Message

**Files:**
- Modify: `backend/app/services/analyst_reports.py` (change 1 line in generate_report)

**CRITICAL:** This is a one-line change. Do NOT change anything else in this function.

- [ ] **Step 1: Filter messages to last assistant message only**

In `backend/app/services/analyst_reports.py`, inside `generate_report()`, find line 605:

```python
            messages = list(conversation.messages)
```

Replace with:

```python
            all_messages = list(conversation.messages)
            # Use only the last assistant message for the report
            assistant_messages = [
                m for m in all_messages
                if (m.role.value if hasattr(m.role, "value") else m.role) == "assistant"
            ]
            messages = [assistant_messages[-1]] if assistant_messages else all_messages
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/analyst_reports.py
git commit -m "feat: scope report generation to last assistant message only"
```

---

### Task 6: Deep Thesis Branded Report Templates

**Files:**
- Modify: `backend/app/services/analyst_reports.py` (update color constants and template functions)

This task updates the existing report styling from the current purple/dark theme to Deep Thesis brand colors. Changes are to color values and style definitions only — no structural changes to the rendering logic.

- [ ] **Step 1: Update chart color constants**

In `backend/app/services/analyst_reports.py`, find line 39:

```python
CHART_COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16"]
```

Replace with:

```python
# Deep Thesis brand colors
BRAND_ACCENT = "#F28C28"
BRAND_ACCENT_HOVER = "#D97A1E"
BRAND_BG = "#FAFAF8"
BRAND_TEXT = "#1A1A1A"
BRAND_TEXT_SECONDARY = "#6B6B6B"
BRAND_TEXT_TERTIARY = "#9B9B9B"
BRAND_BORDER = "#E8E6E3"
BRAND_SCORE_HIGH = "#2D6A4F"
BRAND_SCORE_MID = "#B8860B"
BRAND_SCORE_LOW = "#A23B3B"

CHART_COLORS = [BRAND_ACCENT, BRAND_SCORE_HIGH, BRAND_SCORE_MID, BRAND_SCORE_LOW, "#6366f1", "#ec4899", "#06b6d4", "#84cc16"]
```

- [ ] **Step 2: Update chart rendering to use brand theme**

In `backend/app/services/analyst_reports.py`, inside `_render_chart_image()`, find lines 55-63:

```python
        fig, ax = plt.subplots(figsize=(8, 5))
        fig.patch.set_facecolor("#1a1a2e")
        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors="#a0a0b0")
        ax.xaxis.label.set_color("#a0a0b0")
        ax.yaxis.label.set_color("#a0a0b0")
        ax.title.set_color("#e0e0e8")
        for spine in ax.spines.values():
            spine.set_color("#2a2a3e")
```

Replace with:

```python
        fig, ax = plt.subplots(figsize=(8, 5))
        fig.patch.set_facecolor(BRAND_BG)
        ax.set_facecolor(BRAND_BG)
        ax.tick_params(colors=BRAND_TEXT_SECONDARY)
        ax.xaxis.label.set_color(BRAND_TEXT_SECONDARY)
        ax.yaxis.label.set_color(BRAND_TEXT_SECONDARY)
        ax.title.set_color(BRAND_TEXT)
        for spine in ax.spines.values():
            spine.set_color(BRAND_BORDER)
```

Also update the legend colors. Find each occurrence of:
```python
            ax.legend(facecolor="#1a1a2e", edgecolor="#2a2a3e", labelcolor="#a0a0b0")
```

Replace each with:
```python
            ax.legend(facecolor=BRAND_BG, edgecolor=BRAND_BORDER, labelcolor=BRAND_TEXT_SECONDARY)
```

There are 2 occurrences: one in the scatter block (~line 77) and one in the bar/line/area block (~line 98).

- [ ] **Step 3: Update pie chart text color**

Find:
```python
                   textprops={"color": "#e0e0e8"})
```

Replace with:
```python
                   textprops={"color": BRAND_TEXT})
```

- [ ] **Step 4: Update DOCX branding**

In `_generate_docx()`, find lines 123-124:

```python
    run = p.add_run("Deep Thesis Analyst Report")
    run.font.size = Pt(28)
    run.font.color.rgb = RGBColor(99, 102, 241)
```

Replace with:

```python
    run = p.add_run("Deep Thesis Analyst Report")
    run.font.size = Pt(28)
    run.font.color.rgb = RGBColor(0xF2, 0x8C, 0x28)
```

- [ ] **Step 5: Update PDF branding**

In `_generate_pdf()`, update the custom style colors. Find and replace these style definitions:

Find:
```python
    styles.add(ParagraphStyle(
        "CoverTitle", parent=styles["Title"], fontSize=28,
        textColor=HexColor("#6366f1"), spaceAfter=12,
    ))
```
Replace with:
```python
    styles.add(ParagraphStyle(
        "CoverTitle", parent=styles["Title"], fontSize=28,
        textColor=HexColor(BRAND_ACCENT), spaceAfter=12,
    ))
```

Find:
```python
    styles.add(ParagraphStyle(
        "UserQuestion", parent=styles["Heading2"], fontSize=14,
        textColor=HexColor("#6366f1"), spaceBefore=16, spaceAfter=8,
    ))
```
Replace with:
```python
    styles.add(ParagraphStyle(
        "UserQuestion", parent=styles["Heading2"], fontSize=14,
        textColor=HexColor(BRAND_ACCENT), spaceBefore=16, spaceAfter=8,
    ))
```

Find:
```python
    styles.add(ParagraphStyle(
        "SectionH1", parent=styles["Heading2"], fontSize=16,
        textColor=HexColor("#1a1a2e"), spaceBefore=14, spaceAfter=8,
    ))
```
Replace with:
```python
    styles.add(ParagraphStyle(
        "SectionH1", parent=styles["Heading2"], fontSize=16,
        textColor=HexColor(BRAND_TEXT), spaceBefore=14, spaceAfter=8,
    ))
```

- [ ] **Step 6: Update PPTX branding**

In `_generate_pptx()`, replace all dark background colors with brand colors.

Find every occurrence of (there are multiple in the function):
```python
    bg.fore_color.rgb = PptxRGBColor(26, 26, 46)
```
Replace each with:
```python
    bg.fore_color.rgb = PptxRGBColor(0xFA, 0xFA, 0xF8)
```

Find the title slide text colors:
```python
    p.font.color.rgb = PptxRGBColor(99, 102, 241)
```
Replace with:
```python
    p.font.color.rgb = PptxRGBColor(0xF2, 0x8C, 0x28)
```

Find subtitle text color:
```python
    p2.font.color.rgb = PptxRGBColor(224, 224, 232)
```
Replace with:
```python
    p2.font.color.rgb = PptxRGBColor(0x1A, 0x1A, 0x1A)
```

Find date text color:
```python
    p3.font.color.rgb = PptxRGBColor(160, 160, 176)
```
Replace with:
```python
    p3.font.color.rgb = PptxRGBColor(0x6B, 0x6B, 0x6B)
```

For content slide headings, find:
```python
                    p.font.color.rgb = PptxRGBColor(99, 102, 241)
```
Replace with:
```python
                    p.font.color.rgb = PptxRGBColor(0xF2, 0x8C, 0x28)
```

For content slide subheadings, find:
```python
                    p.font.color.rgb = PptxRGBColor(224, 224, 232)
```
Replace with:
```python
                    p.font.color.rgb = PptxRGBColor(0x1A, 0x1A, 0x1A)
```

For body text on slides, find each occurrence of:
```python
                    p.font.color.rgb = PptxRGBColor(200, 200, 210)
```
Replace each with:
```python
                    p.font.color.rgb = PptxRGBColor(0x6B, 0x6B, 0x6B)
```

Also update bullet points — find:
```python
                            bp.font.color.rgb = PptxRGBColor(200, 200, 210)
```
Replace with:
```python
                            bp.font.color.rgb = PptxRGBColor(0x6B, 0x6B, 0x6B)
```

For chart title slide text, find:
```python
                        p.font.color.rgb = PptxRGBColor(224, 224, 232)
```
Replace with:
```python
                        p.font.color.rgb = PptxRGBColor(0x1A, 0x1A, 0x1A)
```

For sources slide, find:
```python
        p.font.color.rgb = PptxRGBColor(99, 102, 241)
```
(in the sources section) replace with:
```python
        p.font.color.rgb = PptxRGBColor(0xF2, 0x8C, 0x28)
```

And source items:
```python
            p.font.color.rgb = PptxRGBColor(200, 200, 210)
```
Replace with:
```python
            p.font.color.rgb = PptxRGBColor(0x6B, 0x6B, 0x6B)
```

- [ ] **Step 7: Update XLSX header styling**

In `_generate_xlsx()`, add header styling after the `ws.append(["Question", "Response Summary"])` line (line 211). Add this import at the top of the file, after the existing `from openpyxl import Workbook` line:

```python
from openpyxl.styles import Font, PatternFill, Alignment
```

Then after line 211 (`ws.append(["Question", "Response Summary"])`), add:

```python
    # Brand the header row
    header_fill = PatternFill(start_color="F28C28", end_color="F28C28", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in ws[5]:
        if cell.value:
            cell.fill = header_fill
            cell.font = header_font
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/analyst_reports.py
git commit -m "feat: brand all report templates with Deep Thesis styling"
```

---

### Task 7: Frontend Types and API Client

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add notification types**

In `frontend/lib/types.ts`, add at the end of the file (after the `BillingStatus` interface):

```typescript

// ── Notification types ────────────────────────────────────────────────

export interface NotificationItem {
  id: string;
  type: "analysis_complete" | "report_ready";
  title: string;
  message: string;
  link: string;
  read: boolean;
  created_at: string | null;
}

export interface NotificationList {
  items: NotificationItem[];
  unread_count: number;
}

export interface ReportListItem {
  id: string;
  conversation_id: string;
  title: string;
  conversation_title: string;
  format: "docx" | "xlsx" | "pdf" | "pptx";
  status: "pending" | "generating" | "complete" | "failed";
  file_size_bytes: number | null;
  created_at: string | null;
}
```

- [ ] **Step 2: Add notification API methods**

In `frontend/lib/api.ts`, add the notification import at the top. Find line 1:

```typescript
import type {
  AnalystConversationSummary,
  AnalystConversationDetail,
  AnalystReportSummary,
  AnalystSharedConversation,
} from "./types";
```

Replace with:

```typescript
import type {
  AnalystConversationSummary,
  AnalystConversationDetail,
  AnalystReportSummary,
  AnalystSharedConversation,
  NotificationList,
  ReportListItem,
} from "./types";
```

Then add notification methods at the end of the `api` object, before the closing `};`. Find the last method (line 280: `  },` closing `getBillingStatus`) and add after it:

```typescript

  // ── Notifications ───────────────────────────────────────────────────

  async getNotifications(token: string) {
    return apiFetch<NotificationList>("/api/notifications", {
      headers: authHeaders(token),
    });
  },

  async markNotificationRead(token: string, id: string) {
    return apiFetch<{ success: boolean }>(`/api/notifications/${id}/read`, {
      method: "PATCH",
      headers: authHeaders(token),
    });
  },

  async markAllNotificationsRead(token: string) {
    return apiFetch<{ success: boolean }>("/api/notifications/read-all", {
      method: "POST",
      headers: authHeaders(token),
    });
  },

  async listAllReports(token: string) {
    return apiFetch<{ items: ReportListItem[] }>("/api/analyst/reports", {
      headers: authHeaders(token),
    });
  },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat: add notification and report types and API methods"
```

---

### Task 8: NotificationBell Component

**Files:**
- Create: `frontend/components/NotificationBell.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/components/NotificationBell.tsx`:

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { NotificationItem } from "@/lib/types";

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "";
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const seconds = Math.floor((now - then) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function NotificationBell() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const router = useRouter();

  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  const loadNotifications = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.getNotifications(token);
      setNotifications(data.items);
      setUnreadCount(data.unread_count);
    } catch {
      // silent
    }
  }, [token]);

  // Initial load
  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);

  // Poll every 30 seconds when tab is visible
  useEffect(() => {
    if (!token) return;
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") {
        loadNotifications();
      }
    }, 30000);
    return () => clearInterval(interval);
  }, [token, loadNotifications]);

  // Close on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [open]);

  const handleClick = async (notification: NotificationItem) => {
    if (!token) return;

    // Mark as read
    if (!notification.read) {
      try {
        await api.markNotificationRead(token, notification.id);
        setNotifications((prev) =>
          prev.map((n) => (n.id === notification.id ? { ...n, read: true } : n))
        );
        setUnreadCount((prev) => Math.max(0, prev - 1));
      } catch {
        // silent
      }
    }

    setOpen(false);

    // Handle report downloads (link starts with /api/)
    if (notification.link.startsWith("/api/")) {
      const url = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}${notification.link}`;
      try {
        const resp = await fetch(url, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!resp.ok) return;
        const blob = await resp.blob();
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = blobUrl;
        a.download = "";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
      } catch {
        // silent
      }
    } else {
      router.push(notification.link);
    }
  };

  const handleMarkAllRead = async () => {
    if (!token) return;
    try {
      await api.markAllNotificationsRead(token);
      setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
      setUnreadCount(0);
    } catch {
      // silent
    }
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="relative p-1.5 text-text-secondary hover:text-text-primary transition"
        aria-label="Notifications"
      >
        <svg
          className="w-5 h-5"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 01-3.46 0" />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute top-0.5 right-0.5 w-2 h-2 rounded-full bg-accent" />
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-80 rounded border border-border bg-surface shadow-lg z-50">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
            <span className="text-sm font-medium text-text-primary">Notifications</span>
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                className="text-xs text-accent hover:text-accent-hover transition"
              >
                Mark all read
              </button>
            )}
          </div>

          {/* List */}
          <div className="max-h-80 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-text-tertiary">
                No notifications
              </div>
            ) : (
              notifications.map((n) => (
                <button
                  key={n.id}
                  onClick={() => handleClick(n)}
                  className={`w-full text-left px-4 py-3 border-b border-border last:border-b-0 hover:bg-surface-alt transition ${
                    !n.read ? "border-l-2 border-l-accent" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className={`text-sm truncate ${!n.read ? "font-medium text-text-primary" : "text-text-secondary"}`}>
                        {n.title}
                      </p>
                      <p className="text-xs text-text-tertiary truncate mt-0.5">
                        {n.message}
                      </p>
                    </div>
                    <span className="text-[10px] text-text-tertiary whitespace-nowrap shrink-0">
                      {timeAgo(n.created_at)}
                    </span>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/NotificationBell.tsx
git commit -m "feat: add NotificationBell component with dropdown"
```

---

### Task 9: Add NotificationBell to Navbar

**Files:**
- Modify: `frontend/components/Navbar.tsx`

- [ ] **Step 1: Add import and render**

In `frontend/components/Navbar.tsx`, add the import after the existing imports (after line 4 `import { AuthButton } from "./AuthButton";`):

```typescript
import { NotificationBell } from "./NotificationBell";
```

Then find the AuthButton in the JSX (line 40):

```tsx
          <AuthButton />
```

Replace with:

```tsx
          <div className="flex items-center gap-3">
            {session && <NotificationBell />}
            <AuthButton />
          </div>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/Navbar.tsx
git commit -m "feat: add notification bell to navbar"
```

---

### Task 10: Reports Tab in Insights Sidebar

**Files:**
- Modify: `frontend/components/analyst/AnalystSidebar.tsx`

- [ ] **Step 1: Add Reports tab with report list**

Replace the entire contents of `frontend/components/analyst/AnalystSidebar.tsx` with:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { api } from "@/lib/api";
import type { AnalystConversationSummary, ReportListItem } from "@/lib/types";

const SUGGESTED_ANALYSES = [
  "Portfolio sector breakdown",
  "Score distribution analysis",
  "Funding stage pipeline",
  "Top performers deep dive",
  "Market trend comparison",
  "Competitive landscape overview",
  "Due diligence checklist template",
];

interface Props {
  conversations: AnalystConversationSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onSuggestion: (prompt: string) => void;
  isOpen: boolean;
  onToggle: () => void;
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "";
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const seconds = Math.floor((now - then) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

const FORMAT_LABELS: Record<string, string> = {
  pdf: "PDF",
  docx: "DOCX",
  pptx: "PPTX",
  xlsx: "XLSX",
};

export function AnalystSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onSuggestion,
  isOpen,
  onToggle,
}: Props) {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const [activeTab, setActiveTab] = useState<"conversations" | "reports">("conversations");
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [reportsLoaded, setReportsLoaded] = useState(false);

  const loadReports = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.listAllReports(token);
      setReports(data.items);
    } catch {
      // silent
    } finally {
      setReportsLoaded(true);
    }
  }, [token]);

  // Load reports when tab switches to reports
  useEffect(() => {
    if (activeTab === "reports" && !reportsLoaded) {
      loadReports();
    }
  }, [activeTab, reportsLoaded, loadReports]);

  const handleReportClick = async (report: ReportListItem) => {
    if (report.status !== "complete" || !token) return;
    const url = api.getReportDownloadUrl(report.id);
    try {
      const resp = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) return;
      const blob = await resp.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `${report.conversation_title || report.title}.${report.format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch {
      // silent
    }
  };

  return (
    <>
      {/* Mobile toggle */}
      <button
        onClick={onToggle}
        className="md:hidden fixed top-20 left-3 z-30 p-2 rounded bg-surface border border-border text-text-secondary hover:text-text-primary"
        aria-label="Toggle sidebar"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Overlay for mobile */}
      {isOpen && (
        <div className="md:hidden fixed inset-0 bg-black/30 z-30" onClick={onToggle} />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed md:relative z-40 md:z-auto top-0 left-0 h-full w-64 bg-surface border-r border-border flex flex-col transition-transform md:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* New button */}
        <div className="p-3 border-b border-border">
          <button
            onClick={onNew}
            className="w-full px-3 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover transition"
          >
            + New Conversation
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-border">
          <button
            onClick={() => setActiveTab("conversations")}
            className={`flex-1 px-3 py-2 text-xs font-medium transition ${
              activeTab === "conversations"
                ? "text-text-primary border-b-2 border-accent"
                : "text-text-tertiary hover:text-text-secondary"
            }`}
          >
            Conversations
          </button>
          <button
            onClick={() => setActiveTab("reports")}
            className={`flex-1 px-3 py-2 text-xs font-medium transition ${
              activeTab === "reports"
                ? "text-text-primary border-b-2 border-accent"
                : "text-text-tertiary hover:text-text-secondary"
            }`}
          >
            Reports
          </button>
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto">
          {activeTab === "conversations" ? (
            <>
              {conversations.length > 0 && (
                <div className="p-3">
                  <p className="text-[10px] uppercase tracking-wider text-text-tertiary mb-2">History</p>
                  <div className="space-y-0.5">
                    {conversations.map((c) => (
                      <button
                        key={c.id}
                        onClick={() => onSelect(c.id)}
                        className={`w-full text-left px-2 py-1.5 rounded text-sm truncate transition ${
                          activeId === c.id
                            ? "bg-accent/10 text-accent"
                            : "text-text-secondary hover:text-text-primary hover:bg-surface-alt"
                        }`}
                        title={c.title}
                      >
                        {c.title}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Suggestions */}
              <div className="p-3 border-t border-border">
                <p className="text-[10px] uppercase tracking-wider text-text-tertiary mb-2">Suggested</p>
                <div className="space-y-0.5">
                  {SUGGESTED_ANALYSES.map((s) => (
                    <button
                      key={s}
                      onClick={() => onSuggestion(s)}
                      className="w-full text-left px-2 py-1.5 rounded text-xs text-text-tertiary hover:text-text-secondary hover:bg-surface-alt transition truncate"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            </>
          ) : (
            <div className="p-3">
              {!reportsLoaded ? (
                <p className="text-xs text-text-tertiary text-center py-4">Loading...</p>
              ) : reports.length === 0 ? (
                <p className="text-xs text-text-tertiary text-center py-4">No reports generated yet</p>
              ) : (
                <div className="space-y-1">
                  {reports.map((r) => (
                    <button
                      key={r.id}
                      onClick={() => handleReportClick(r)}
                      className={`w-full text-left px-2 py-2 rounded transition ${
                        r.status === "complete"
                          ? "hover:bg-surface-alt cursor-pointer"
                          : "cursor-default opacity-70"
                      }`}
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-accent/10 text-accent shrink-0">
                          {FORMAT_LABELS[r.format] || r.format.toUpperCase()}
                        </span>
                        <span className="text-sm text-text-secondary truncate flex-1">
                          {r.title}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 mt-1 ml-8">
                        {r.status === "complete" && (
                          <span className="w-1.5 h-1.5 rounded-full bg-score-high shrink-0" />
                        )}
                        {r.status === "generating" && (
                          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse shrink-0" />
                        )}
                        {r.status === "failed" && (
                          <span className="w-1.5 h-1.5 rounded-full bg-score-low shrink-0" />
                        )}
                        {r.status === "pending" && (
                          <span className="w-1.5 h-1.5 rounded-full bg-text-tertiary shrink-0" />
                        )}
                        <span className="text-[10px] text-text-tertiary">
                          {timeAgo(r.created_at)}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
```

Note: This is a full rewrite of the sidebar component. The existing conversation list and suggestions are preserved exactly as they were — they're now wrapped in the "conversations" tab. The only addition is the tabs UI and the reports tab content.

- [ ] **Step 2: Commit**

```bash
git add frontend/components/analyst/AnalystSidebar.tsx
git commit -m "feat: add Reports tab to insights sidebar"
```

---

### Task 11: Add conversation_title to list_reports endpoint

**Files:**
- Modify: `backend/app/api/analyst.py` (update existing `list_reports` endpoint to join conversation title)

- [ ] **Step 1: Update the list_reports endpoint**

In `backend/app/api/analyst.py`, find the existing `list_reports` function (line 404-428). The current query only selects `AnalystReport`. Update it to join with `AnalystConversation` to include the title.

Find:

```python
@router.get("/api/analyst/reports")
async def list_reports(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystReport)
        .where(AnalystReport.user_id == user.id)
        .order_by(AnalystReport.created_at.desc())
    )
    reports = result.scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "conversation_id": str(r.conversation_id),
                "title": r.title,
                "format": r.format.value if hasattr(r.format, "value") else r.format,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "file_size_bytes": r.file_size_bytes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ]
    }
```

Replace with:

```python
@router.get("/api/analyst/reports")
async def list_reports(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystReport)
        .where(AnalystReport.user_id == user.id)
        .order_by(AnalystReport.created_at.desc())
        .options(selectinload(AnalystReport.conversation))
    )
    reports = result.scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "conversation_id": str(r.conversation_id),
                "title": r.title,
                "conversation_title": r.conversation.title if r.conversation else r.title,
                "format": r.format.value if hasattr(r.format, "value") else r.format,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "file_size_bytes": r.file_size_bytes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ]
    }
```

Note: `selectinload` is already imported in this file (check existing imports). If not, add `from sqlalchemy.orm import selectinload` to the imports.

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/analyst.py
git commit -m "feat: include conversation_title in report list endpoint"
```

---

### Task 12: Deploy

**Files:** No file changes — deployment only.

**CRITICAL:** Follow the deployment pattern exactly. NEVER use `--delete` with rsync.

- [ ] **Step 1: Sync files to EC2**

```bash
rsync -avz \
  --exclude=node_modules --exclude=.git --exclude=__pycache__ \
  --exclude=.next --exclude=.worktrees --exclude=.superpowers \
  -e "ssh -i ~/.ssh/acutal-deploy.pem" \
  /Users/leemosbacker/acutal/ ec2-user@98.89.232.52:~/acutal/
```

- [ ] **Step 2: Run the Alembic migration on EC2**

```bash
ssh -i ~/.ssh/acutal-deploy.pem ec2-user@98.89.232.52 \
  "cd ~/acutal && docker compose -f docker-compose.prod.yml exec backend alembic upgrade head"
```

- [ ] **Step 3: Rebuild and restart both services**

```bash
ssh -i ~/.ssh/acutal-deploy.pem ec2-user@98.89.232.52 \
  "cd ~/acutal && docker compose -f docker-compose.prod.yml up -d --build backend frontend"
```

- [ ] **Step 4: Verify health**

```bash
ssh -i ~/.ssh/acutal-deploy.pem ec2-user@98.89.232.52 \
  "curl -s http://localhost:8000/api/health"
```

Expected: `{"status":"ok"}`
