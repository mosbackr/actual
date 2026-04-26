# Email Verification & Test Send — Design Spec

## Overview

Add email verification (Hunter.io + NeverBounce) and test-send capability to the existing marketing email system. Verification runs as an up-front batch step before sending. Invalid emails are permanently flagged. All emails include CAN-SPAM/GDPR-compliant unsubscribe links and a physical mailing address.

## Architecture

Three additions to the existing marketing email system:
1. **Email verification** — batch job that runs Hunter.io (person verification + email correction) then NeverBounce (deliverability) on all scored investors, updating investor records
2. **Test send** — endpoint to send a real investor's personalized email to an admin-provided address
3. **Compliance** — unsubscribe mechanism, physical address footer, and "why you're receiving this" disclosure in every email

---

## 1. Investor Model Changes

### New columns on `investors` table

| Column | Type | Default | Notes |
|--------|------|---------|-------|
| `email_status` | String(20) | `"unverified"` | `unverified`, `valid`, `corrected`, `bounced` |
| `email_verified_at` | DateTime, nullable | null | When last verified |
| `email_unsubscribed` | Boolean | `false` | Permanently opted out |
| `email_unsubscribed_at` | DateTime, nullable | null | When they opted out |

Requires an Alembic migration.

### Status definitions

- `unverified` — never checked
- `valid` — passed both Hunter + NeverBounce
- `corrected` — Hunter returned a different email, which was saved and passed NeverBounce
- `bounced` — failed NeverBounce (permanently skipped, never emailed)

### Batch sender query update

The existing `run_marketing_batch` query adds:
```python
.where(Investor.email_status != "bounced")
.where(Investor.email_unsubscribed != True)
```

---

## 2. Email Verification Service

### New file: `backend/app/services/email_verification.py`

**`verify_with_hunter(email: str, first_name: str, last_name: str, company: str) -> dict`**
- Calls Hunter.io Email Verifier API (`GET https://api.hunter.io/v2/email-verifier`)
- Passes email + context (name, company) for better accuracy
- Returns `{"status": "valid"|"invalid"|"accept_all"|"webmail"|"disposable"|"unknown", "suggested_email": str|None}`
- If Hunter returns a different/corrected email, that becomes `suggested_email`

**`verify_with_neverbounce(email: str) -> dict`**
- Calls NeverBounce Single Verification API (`GET https://api.neverbounce.com/v4/single/check`)
- Returns `{"result": "valid"|"invalid"|"disposable"|"catchall"|"unknown"}`

### Verification logic per investor

1. Call Hunter with investor's email + partner_name (split into first/last) + firm_name
2. If Hunter suggests a corrected email -> update `investor.email` to the corrected one (overwrite, no history)
3. Call NeverBounce on the (possibly corrected) email
4. If NeverBounce returns `valid` or `catchall` -> set `email_status = "valid"` (or `"corrected"` if email was changed)
5. If NeverBounce returns `invalid` or `disposable` -> set `email_status = "bounced"`
6. If NeverBounce returns `unknown` -> treat as `valid` (don't block, log a warning)
7. Set `email_verified_at = now()`

### Config additions

```python
hunter_api_key: str = ""
neverbounce_api_key: str = ""
company_address: str = "3965 Lewis Link, New Albany, OH 43054"
```

Values stored in AWS Secrets Manager, injected via environment at deploy time (same pattern as existing Resend, Anthropic keys).

---

## 3. Verification Batch Job

### New model: `EmailVerificationJob` in `backend/app/models/marketing.py`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `status` | String(20) | pending -> running -> completed -> failed |
| `total_recipients` | Integer | Count of scored investors with emails |
| `verified_count` | Integer | Passed verification |
| `corrected_count` | Integer | Hunter corrected the email |
| `bounced_count` | Integer | Failed NeverBounce |
| `skipped_count` | Integer | Already verified recently / no email |
| `current_investor_name` | String(300), nullable | Progress tracking |
| `error` | Text, nullable | |
| `started_at` | DateTime, nullable | |
| `completed_at` | DateTime, nullable | |
| `created_at` | DateTime | server_default now() |

Requires an Alembic migration.

### Batch runner: `run_verification_batch(job_id: str)`

- Queries all scored investors with non-null email and `email_status != "bounced"`
- Investors already marked `valid` or `corrected` within the last 30 days are skipped (no need to re-verify recent ones)
- For each: run Hunter -> maybe update email -> run NeverBounce -> update `email_status` + `email_verified_at`
- Follows the same separate-session-per-DB-operation pattern as `run_marketing_batch`

### New API endpoints (superadmin)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/admin/marketing/verify` | Start verification job |
| `GET` | `/api/admin/marketing/verify/jobs` | List verification jobs with status/progress |

---

## 4. Test Send

### New API endpoint (superadmin)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/admin/marketing/test-send` | Send test email to a specific address |

**Input:** `{ "email": string, "subject": string, "html_template": string, "investor_id": string }`

**Behavior:**
- Looks up investor by `investor_id`, gets their `InvestorRanking`
- Calls `render_for_recipient` with the real investor's data (score, CTA URL, unsubscribe URL)
- Sends the personalized email to the admin-provided `email` address (not the investor's)
- Uses `updates@deepthesis.co` as the from address
- Synchronous — returns success/failure immediately, no batch job
- Returns 404 if investor or ranking not found

---

## 5. Email Compliance (CAN-SPAM / GDPR)

### Unsubscribe mechanism

**URL format:** `{frontend_url}/unsubscribe/{investor_id}?token={hmac_signature}`

- HMAC generated using `investor_id` + the existing `jwt_secret` as the signing key
- No login required — clicking the link works immediately

**Backend endpoint (public, no auth):**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/unsubscribe/{investor_id}` | Verify HMAC token, set `email_unsubscribed = true`, set `email_unsubscribed_at = now()` |

Returns 400 if token is invalid. Returns 200 on success (idempotent).

**Frontend page:** `frontend/app/unsubscribe/[id]/page.tsx`
- Simple branded page: "You've been unsubscribed from Deep Thesis emails."
- On mount, calls the backend endpoint with the token from the URL query string
- Shows success or error state
- No login required

### Email template changes

**New placeholder:** `{{unsubscribe_url}}` added to `render_for_recipient`
- Generated per investor using the HMAC signing scheme

**`BRAND_SYSTEM_PROMPT` updated** to require every generated email includes a footer with:
- Unsubscribe link using `{{unsubscribe_url}}`
- Physical mailing address using `{{company_address}}`
- Disclosure: "You're receiving this because you were scored on the Deep Thesis platform."

**`render_for_recipient` updated** to replace:
- `{{unsubscribe_url}}` -> signed unsubscribe link
- `{{company_address}}` -> value from `settings.company_address`

### Batch sender filter

Query adds `.where(Investor.email_unsubscribed != True)` alongside the existing bounced check.

---

## 6. Admin UI Changes

### Modifications to `admin/app/marketing/page.tsx`

**Verification section** (above send controls):
- "Verify Recipients" button -> starts verification job via `POST /api/admin/marketing/verify`
- While running: progress bar showing progress / total, current investor name
- On completion: summary line — e.g., "142 valid, 8 corrected, 5 bounced, 3 skipped"
- "Send to All Verified Investors" button disabled until at least one verification has completed

**Test send section** (below preview panel):
- Text input for admin email address
- Investor search/dropdown — lists scored investors by firm + partner name
- "Send Test" button -> calls `POST /api/admin/marketing/test-send`
- Inline success/error feedback

**Send button label** changes from "Send to All Scored Investors" to "Send to All Verified Investors"

### Admin API client additions

New methods in `admin/lib/api.ts`:
- `startVerification(token)` -> POST `/api/admin/marketing/verify`
- `getVerificationJobs(token)` -> GET `/api/admin/marketing/verify/jobs`
- `sendTestEmail(token, email, subject, htmlTemplate, investorId)` -> POST `/api/admin/marketing/test-send`

### Admin types additions

New interface in `admin/lib/types.ts`:
- `VerificationJob` — mirrors the `EmailVerificationJob` model fields

---

## Files Changed / Created

### New files
- `backend/app/services/email_verification.py` — Hunter.io + NeverBounce verification functions + batch runner
- `backend/alembic/versions/xxx_add_email_verification_columns.py` — investor columns migration
- `backend/alembic/versions/xxx_add_email_verification_job.py` — verification job table migration
- `backend/app/api/unsubscribe.py` — public unsubscribe endpoint
- `frontend/app/unsubscribe/[id]/page.tsx` — unsubscribe landing page

### Modified files
- `backend/app/models/investor.py` — add `email_status`, `email_verified_at`, `email_unsubscribed`, `email_unsubscribed_at` columns
- `backend/app/models/marketing.py` — add `EmailVerificationJob` model
- `backend/app/models/__init__.py` — register new model
- `backend/app/config.py` — add `hunter_api_key`, `neverbounce_api_key`, `company_address`
- `backend/app/services/marketing_email.py` — update `BRAND_SYSTEM_PROMPT`, `render_for_recipient` (new placeholders), `run_marketing_batch` (skip bounced + unsubscribed)
- `backend/app/api/admin_marketing.py` — add verify and test-send endpoints
- `backend/app/main.py` — register unsubscribe router
- `admin/lib/types.ts` — add `VerificationJob` interface
- `admin/lib/api.ts` — add verification + test-send API methods
- `admin/app/marketing/page.tsx` — verification section, test send section, updated send button
