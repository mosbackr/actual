# Marketing Email System — Design Spec

## Overview

Admin-initiated marketing email system that notifies scored investors of their ranking and drives them to sign up and view their detailed score on the platform.

## Architecture

Backend-driven approach: the admin types a free-form prompt, the backend calls Claude to generate branded HTML, the admin previews and sends. Batch sending uses the existing pause/resume job pattern.

Three pieces:
1. **Backend** — email generation via Claude, batch send with pause/resume, score detail API
2. **Admin UI** — composer + preview + send controls
3. **Frontend** — score detail page, navbar score indicator, signup/login redirect flow

---

## 1. Backend — Email Generation

### New file: `backend/app/services/marketing_email.py`

**`generate_email_html(prompt: str) -> str`**
- Calls Claude (claude-sonnet-4-6) with a system prompt containing:
  - Deep Thesis brand guide: colors (`#F28C28` accent, `#FAFAF8` background, `#1A1A1A` text, `#E8E6E3` borders), fonts (Georgia/serif for headings, Arial/sans-serif for body)
  - Logo HTML: circled "D" + "Deep Thesis" serif text (from existing `base.html` header)
  - CTA button style: orange pill button matching existing email templates
  - Email HTML constraints: inline CSS, table layout, max-width 600px, email-client-safe HTML
  - Instruction to include `{{score}}` and `{{cta_url}}` placeholders in the output
- Returns raw HTML string with placeholders intact

**`render_for_recipient(html_template: str, investor_ranking, investor_id: str, frontend_url: str) -> str`**
- Replaces `{{score}}` with the investor's `overall_score` (rounded to integer)
- Replaces `{{cta_url}}` with `{frontend_url}/score/{investor_id}?ref=email`
- Returns final HTML ready to send

---

## 2. Backend — Batch Send with Pause/Resume

### New model: `MarketingEmailJob` in `backend/app/models/marketing.py`

Follows the `InvestorRankingBatchJob` pattern:

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `status` | String(20) | pending → running → paused → completed → failed |
| `subject` | Text | Email subject line |
| `html_template` | Text | Generated HTML with placeholders |
| `total_recipients` | Integer | Count of scored investors at send time |
| `sent_count` | Integer | Successfully sent |
| `failed_count` | Integer | Failed sends |
| `current_investor_id` | UUID, nullable | Progress tracking |
| `current_investor_name` | String(300), nullable | Progress tracking |
| `from_address` | String(255) | Default: `updates@deepthesis.co` |
| `error` | Text, nullable | Error message if failed |
| `started_at` | DateTime, nullable | |
| `paused_at` | DateTime, nullable | |
| `completed_at` | DateTime, nullable | |
| `created_at` | DateTime | server_default now() |

Requires an Alembic migration.

### New routes: `backend/app/routes/marketing.py`

All endpoints require `superadmin` auth.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/admin/marketing/generate` | Generate HTML email from prompt. Input: `{ "prompt": string }`. Returns: `{ "html": string }` |
| `POST` | `/api/admin/marketing/send` | Create batch job and start sending. Input: `{ "subject": string, "html_template": string }`. Returns: job object |
| `POST` | `/api/admin/marketing/jobs/{job_id}/pause` | Pause a running job |
| `POST` | `/api/admin/marketing/jobs/{job_id}/resume` | Resume a paused job |
| `GET` | `/api/admin/marketing/jobs` | List all marketing jobs with status/progress |

**Sending behavior:**
- From address: `updates@deepthesis.co` (marketing subdomain, already verified on Resend)
- Rate: ~1 email/second (within Resend limits)
- Iterates all investors with an `InvestorRanking` record
- Each investor's email is looked up from the `investors` table
- Checks job status between each send — if paused, stops the loop
- On resume, continues from `current_investor_id`

---

## 3. Backend — Score Detail API

### New endpoint on existing investor routes

**`GET /api/investors/{investor_id}/ranking`**
- Auth: requires authenticated user whose email matches the investor record, or superadmin
- Returns: all ranking fields (overall_score, 7 dimensions, narrative, scored_at)
- 403 if email doesn't match; 404 if no ranking exists

**`GET /api/investors/me/ranking`**
- Auth: requires authenticated user
- Looks up investor by the authenticated user's email
- Returns: ranking data + investor_id, or 404 if no match

---

## 4. Signup Flow & Investor Role Assignment

### Role: `investor`

New valid role value alongside existing `superadmin`, `admin`, `user`, `expert`.

### Assignment triggers

1. **On signup:** The registration endpoint checks if the new user's email matches any `investor` record. If yes, set role to `investor`.

2. **On login:** If an existing user with role `user` logs in and their email matches an `investor` record, upgrade role to `investor`.

### Rules
- Only upgrade from `user` → `investor`. Do not downgrade `expert`, `admin`, or `superadmin`.
- Email matching is case-insensitive.

---

## 5. Frontend — Score Detail Page

### New page: `frontend/app/score/[id]/page.tsx`

**Route:** `/score/{investor_id}`

**Auth:** Protected. If not authenticated, redirect to `/auth/signin?callbackUrl=/score/{investor_id}` so the user returns after login/signup.

**Layout:**
- Overall score prominently at the top — large number, color-coded (green `#2D6A4F` for 80+, gold `#B8860B` for 60-79, gray `#6B6B6B` for 40-59, red `#A23B3B` for <40)
- 7 dimension scores in a card grid, each showing:
  - Dimension name (e.g., "Portfolio Performance")
  - Score (0-100) with color coding
  - Visual bar indicator
- Narrative section below with the AI-generated explanation
- Branded: Inter body, Instrument Serif headings, orange accent

**Data:** Calls `GET /api/investors/{investor_id}/ranking` with the user's auth token.

---

## 6. Frontend — Navbar Score Indicator

### Modified file: `frontend/components/Navbar.tsx`

- After auth check, if user's role is `investor`, call `GET /api/investors/me/ranking`
- If a ranking exists, show a compact pill/badge in the navbar with the overall score number, color-coded
- Positioned between nav links and right-side icons (Watchlist, Notifications, Auth)
- Click navigates to `/score/{investor_id}`
- If no ranking exists, show nothing

---

## 7. Admin UI — Marketing Email Page

### New page: `admin/app/marketing/page.tsx`

**Two-panel layout:**

**Left panel — Composer:**
- Text area for the free-form prompt
- "Generate" button → calls `POST /api/admin/marketing/generate`
- Subject line text input (editable, separate from HTML body)
- Loading state while Claude generates

**Right panel — Preview:**
- Sandboxed iframe rendering the generated HTML
- Shows email with sample data (e.g., score = 85, sample CTA URL)
- Updates on each generation

**Bottom bar — Send controls:**
- "Send to All Scored Investors" button → creates batch job
- Once running: progress bar showing `sent_count / total_recipients`
- Pause / Resume buttons
- Status indicator (pending, running, paused, completed, failed)
- Job history — list of past sends with date, status, sent/total counts

### Sidebar addition

Add "Marketing" link to admin sidebar navigation.

---

## Files Changed / Created

### New files
- `backend/app/models/marketing.py` — MarketingEmailJob model
- `backend/app/services/marketing_email.py` — generate + render functions
- `backend/app/routes/marketing.py` — API endpoints
- `backend/alembic/versions/xxx_add_marketing_email_job.py` — migration
- `admin/app/marketing/page.tsx` — admin marketing page
- `frontend/app/score/[id]/page.tsx` — score detail page

### Modified files
- `backend/app/routes/__init__.py` or main router — register marketing routes
- `backend/app/auth/` — add investor role assignment on signup/login
- `frontend/components/Navbar.tsx` — add score indicator for investor role
- `admin/components/Sidebar.tsx` — add Marketing link
