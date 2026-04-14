# Notifications, Branded Reports & Report History — Design Spec

## Overview

Four interconnected features for Deep Thesis:

1. **Report generation scoped to last assistant message** — only the most recent AI response (with its charts/citations) goes into the generated document
2. **Deep Thesis branded reports** — PDF, DOCX, PPTX, XLSX all match the website aesthetic (warm off-white, terracotta accent, Instrument Serif headlines, logo)
3. **User notification system** — database-backed, bell icon dropdown in navbar, polling-based
4. **Report history in insights sidebar** — tab in the AnalystSidebar showing all generated reports

## Architecture

- **Notification model** in PostgreSQL, new `notifications` table
- **REST endpoints** for notification CRUD, report listing
- **Frontend polling** every 30 seconds for new notifications (consistent with existing patterns)
- **Bell icon dropdown** in Navbar following the AuthButton dropdown pattern
- **Reports tab** added to AnalystSidebar component
- **Branded report templates** updated in `analyst_reports.py`

No new infrastructure (no WebSockets, no push notifications, no message queues). Builds entirely on existing patterns.

---

## 1. Notification System

### 1.1 Backend Model

New `Notification` SQLAlchemy model in `backend/app/models/notification.py`:

| Column      | Type                          | Notes                                      |
|-------------|-------------------------------|---------------------------------------------|
| id          | UUID, PK                      | Default: uuid4                              |
| user_id     | UUID, FK → users.id           | Required, indexed                           |
| type        | Enum: analysis_complete, report_ready | Required                            |
| title       | String                        | Short title, e.g., "Analysis complete"      |
| message     | String                        | Detail, e.g., company name or "PDF report"  |
| link        | String                        | URL path, e.g., `/analyze/{id}`             |
| read        | Boolean                       | Default: false                              |
| created_at  | DateTime                      | Default: now(), indexed descending          |

Index on `(user_id, read, created_at DESC)` for efficient unread queries.

### 1.2 Backend API

New router in `backend/app/api/notifications.py`:

- **`GET /api/notifications`** — List notifications for current user, newest first, limit 20. Returns `{ items: [...], unread_count: int }`.
- **`PATCH /api/notifications/{id}/read`** — Mark single notification as read. Returns `{ success: true }`.
- **`POST /api/notifications/read-all`** — Mark all user's notifications as read. Returns `{ success: true }`.

All endpoints require authentication via `get_current_user` dependency.

### 1.3 Frontend — Bell Icon Component

New component: `frontend/components/NotificationBell.tsx`

- Renders a bell SVG icon in the Navbar, positioned between the nav links and the AuthButton
- Shows an orange (#F28C28) dot badge when `unread_count > 0`
- Click opens a dropdown (same pattern as AuthButton: useState for open/closed, useRef + click-outside listener, absolute positioning, z-50)
- Dropdown contents:
  - Header row: "Notifications" label + "Mark all read" text button (only shown when unread exist)
  - List of up to 20 notifications, each showing:
    - Orange left border if unread
    - Title (bold) + message (secondary text)
    - Time ago (e.g., "2m ago", "1h ago")
    - Entire row is clickable → navigates to `notification.link`, marks as read
  - Empty state: "No notifications" in text-tertiary
  - For `report_ready` notifications where `link` is an API download path (starts with `/api/`), handle as authenticated fetch + blob download (same pattern already used in insights page report download). For all other notification types, use `router.push(link)` for client-side navigation.
- Polling: `useEffect` with `setInterval` every 30 seconds, only when document is visible (`document.visibilityState === "visible"`)
- Initial fetch on mount

### 1.4 Navbar Integration

Modify `frontend/components/Navbar.tsx`:
- Import and render `<NotificationBell />` after the nav links div, before `<AuthButton />`
- Only render when `session` exists (authenticated users only)

---

## 2. Report Generation — Last Message Only

### 2.1 Backend Change

Modify `backend/app/services/analyst_reports.py`:

In the `generate_report()` function, where conversation messages are loaded:
- Instead of passing all messages to the document generators, filter to only the **last message with `role="assistant"`**
- Include that message's `charts` and `citations`
- The conversation `title` is still used as the report title for context
- If the last assistant message has no content (edge case), fall back to all messages

This affects all four format generators (DOCX, PDF, PPTX, XLSX) since they all receive the same message data.

---

## 3. Deep Thesis Branded Reports

### 3.1 Brand Assets

Create `backend/app/services/report_assets/` directory containing:
- `logo.png` — Deep Thesis logo exported from the frontend SVG (LogoIcon component), sized for document embedding (~200px wide)
- Brand constants defined at top of `analyst_reports.py`:
  - Background: `#FAFAF8` (warm off-white)
  - Accent: `#F28C28` (terracotta/orange)
  - Text primary: `#1A1A1A`
  - Text secondary: `#6B6B6B`
  - Score high: `#2D6A4F`, mid: `#B8860B`, low: `#A23B3B`

### 3.2 PDF (reportlab)

- Page background: warm off-white (#FAFAF8)
- Header: Deep Thesis logo (left) + report date (right), separated by thin terracotta rule
- Title: large serif font (use reportlab's built-in serif, closest to Instrument Serif)
- Body: clean sans-serif
- Headings: terracotta color (#F28C28)
- Charts: embedded as before, but with warm-toned matplotlib theme
- Footer: "Generated by Deep Thesis" + page number, terracotta text
- Sources/citations section at end with subtle styling

### 3.3 DOCX (python-docx)

- Cover page: Deep Thesis logo centered, report title in large serif, date, subtle terracotta accent line
- Heading styles: terracotta color
- Body: clean default font
- Footer on every page: "Deep Thesis" left, page number right
- Charts embedded as images
- Citations formatted as footnote-style references

### 3.4 PPTX (python-pptx)

- Replace current dark theme (RGB 26,26,46) with warm off-white background (#FAFAF8)
- Title slide: Deep Thesis logo, report title, date, terracotta accent bar
- Content slides: dark text on off-white, terracotta for headings
- Chart slides: warm-themed charts
- Footer on each slide: "Deep Thesis" + slide number

### 3.5 XLSX (openpyxl)

- Header row: terracotta background (#F28C28) with white text
- Summary sheet: "Deep Thesis" branding at top, report title, date
- Data cells: clean formatting, alternating row shading using warm tones
- Chart sheets: warm color palette

### 3.6 Matplotlib Chart Theme

Update the chart rendering function to use brand colors:
- Background: warm off-white
- Grid lines: light warm gray (#E8E6E3)
- Bar/line colors: terracotta primary, with secondary palette from brand
- Text: dark (#1A1A1A)
- Remove the current dark theme

---

## 4. Report History in Insights Sidebar

### 4.1 Backend Endpoint

New endpoint in `backend/app/api/analyst.py`:

- **`GET /api/analyst/reports`** — List all reports for current user across all conversations. Returns:
  ```json
  {
    "items": [
      {
        "id": "uuid",
        "conversation_id": "uuid",
        "conversation_title": "string",
        "format": "pdf",
        "status": "complete",
        "file_size_bytes": 12345,
        "error": null,
        "created_at": "iso-datetime"
      }
    ]
  }
  ```
  Joins `AnalystReport` with `AnalystConversation` to get conversation title. Ordered by `created_at DESC`. Requires authentication.

### 4.2 Frontend — Sidebar Tabs

Modify `frontend/components/analyst/AnalystSidebar.tsx`:

- Add two tabs at the top of the sidebar: **Conversations** (default) | **Reports**
- Tab styling: text buttons, active tab gets `text-text-primary font-medium` + bottom border in accent color, inactive gets `text-text-tertiary`
- Conversations tab: existing conversation list (no changes)
- Reports tab: list of generated reports showing:
  - Format badge (PDF, DOCX, etc.) — small pill/tag
  - Conversation title (truncated)
  - Date (relative, e.g., "2h ago")
  - Status indicator: green dot for complete, pulsing orange for generating, red for failed
  - Click complete report → triggers download via existing `api.downloadReport()` pattern
  - Click failed report → shows error in AlertModal
  - Click generating report → no action (or tooltip "Generating...")
- Empty state: "No reports generated yet" in text-tertiary

### 4.3 Frontend API & Types

Add to `frontend/lib/api.ts`:
- `listReports(token: string)` — GET `/api/analyst/reports`
- `getNotifications(token: string)` — GET `/api/notifications`
- `markNotificationRead(token: string, id: string)` — PATCH `/api/notifications/{id}/read`
- `markAllNotificationsRead(token: string)` — POST `/api/notifications/read-all`

Add to `frontend/lib/types.ts`:
- `Notification` interface: `{ id, type, title, message, link, read, created_at }`
- `NotificationList` interface: `{ items: Notification[], unread_count: number }`
- `ReportListItem` interface: `{ id, conversation_id, conversation_title, format, status, file_size_bytes, error, created_at }`

---

## 5. Notification Creation Points

### 5.1 Analysis Completion

In `backend/app/services/analysis_worker.py`, at the end of `run_analysis()` after setting `analysis.status = "complete"`:

```python
notification = Notification(
    user_id=analysis.user_id,
    type=NotificationType.analysis_complete,
    title="Analysis complete",
    message=analysis.company_name or "Your startup analysis",
    link=f"/analyze/{analysis.id}",
)
db.add(notification)
```

### 5.2 Report Generation

In `backend/app/services/analyst_reports.py`, at the end of `generate_report()` after setting `report.status = "complete"`:

```python
notification = Notification(
    user_id=conversation.user_id,
    type=NotificationType.report_ready,
    title="Report ready",
    message=f"{report.format.upper()} report",
    link=f"/api/analyst/reports/{report.id}/download",
)
db.add(notification)
```

### 5.3 No Notification For

- Failed analyses (user sees the error on the analyze page)
- Failed reports (user sees the error in the insights UI)
- Billing events (handled by Stripe emails)

---

## 6. Database Migration

Single Alembic migration that:
1. Creates `notification_type` ENUM type with values: `analysis_complete`, `report_ready`
2. Creates `notifications` table with all columns from section 1.1
3. Creates index on `(user_id, read, created_at DESC)`

---

## 7. Files Changed

**New files:**
- `backend/app/models/notification.py` — Notification model
- `backend/app/api/notifications.py` — Notification endpoints
- `backend/app/services/report_assets/logo.png` — Deep Thesis logo for reports
- `frontend/components/NotificationBell.tsx` — Bell icon + dropdown
- Alembic migration file

**Modified files:**
- `backend/app/models/__init__.py` — Import Notification model
- `backend/app/main.py` — Register notifications router
- `backend/app/services/analyst_reports.py` — Last-message-only + branding + notification creation
- `backend/app/services/analysis_worker.py` — Notification creation on analysis complete
- `backend/app/api/analyst.py` — Add `GET /api/analyst/reports` endpoint
- `frontend/components/Navbar.tsx` — Add NotificationBell
- `frontend/components/analyst/AnalystSidebar.tsx` — Add Reports tab
- `frontend/lib/api.ts` — Add notification + report listing methods
- `frontend/lib/types.ts` — Add Notification + ReportListItem types
