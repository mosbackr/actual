# Transactional Email System — Design Spec

## Overview

Transactional email system for DeepThesis using Resend as the email provider, with DNS on AWS Route 53. Sends branded HTML emails for key platform events — analysis completion, memo generation, account lifecycle, and billing. Emails are DeepThesis-branded with CTAs linking users back to the platform.

**Sender**: `gaius@deepthesis.org`
**Reply forwarding**: `gaius@deepthesis.org` → `lee@deepthesis.org` (via AWS SES, deferred to separate task)

---

## Architecture

### File Structure

```
backend/
  app/
    services/
      email_service.py          # EmailService class — Resend SDK wrapper
    templates/
      emails/
        base.html               # Shared layout (logo, header, footer, brand styles)
        welcome.html            # Signup welcome
        analysis_complete.html  # Pitch analysis finished
        memo_complete.html      # Investment memo ready
        report_ready.html       # Analyst report ready to download
        expert_applied.html     # Expert application received
        expert_approved.html    # Expert approved
        expert_rejected.html    # Expert application rejected
        payment_failed.html     # Stripe payment failed
        subscription_confirmed.html  # Subscription activated
        subscription_cancelled.html  # Subscription cancelled
```

### EmailService

Single class in `backend/app/services/email_service.py`:

- **`send(to, subject, template_name, context)`** — renders Jinja2 template with context dict, calls Resend API
- One public method per email type (e.g., `send_analysis_complete(user_email, user_name, analysis_id, startup_name)`) that builds the context and calls `send()`
- All sends are fire-and-forget with error logging — email failure never breaks the main flow
- Uses `jinja2.Environment` with `FileSystemLoader` pointing to `templates/emails/`

### Dependencies

Add `resend` to `backend/pyproject.toml`.

---

## Configuration

### Environment Variables

| Variable | Value | Notes |
|----------|-------|-------|
| `ACUTAL_RESEND_API_KEY` | Resend API key | Added to EC2 `.env` and `docker-compose.yml` mapping |
| `ACUTAL_EMAIL_FROM` | `gaius@deepthesis.org` | Sender address |
| `ACUTAL_FRONTEND_URL` | `https://deepthesis.org` | Used to build CTA links in templates |

Added to `backend/app/config.py` as optional fields (empty string defaults). EmailService checks if `RESEND_API_KEY` is set before attempting to send — graceful no-op in dev environments without keys.

### docker-compose.yml

```yaml
backend:
  environment:
    ACUTAL_RESEND_API_KEY: ${RESEND_API_KEY:-}
    ACUTAL_EMAIL_FROM: ${EMAIL_FROM:-gaius@deepthesis.org}
    ACUTAL_FRONTEND_URL: ${FRONTEND_URL:-https://deepthesis.org}
```

---

## Email Templates

### Base Template

All emails extend `base.html` which provides:

```
┌─────────────────────────────────┐
│  DeepThesis (Instrument Serif)  │
├─────────────────────────────────┤
│                                 │
│  {block: content}               │
│                                 │
│  ┌───────────────────────────┐  │
│  │    {CTA Button}           │  │
│  └───────────────────────────┘  │
│                                 │
│  {block: secondary}             │
│                                 │
├─────────────────────────────────┤
│  © 2026 DeepThesis              │
│  deepthesis.org                 │
└─────────────────────────────────┘
```

**Brand styling (inline CSS for email compatibility):**
- Background: `#FAFAF8` (warm off-white)
- Card surface: `#FFFFFF`
- Text primary: `#1A1A1A`
- Text secondary: `#6B6B6B`
- Accent / CTA button: `#B8553A` (terracotta)
- CTA hover: `#9C4530`
- Border: `#E8E6E3`
- Logo text: "DeepThesis" in serif font (Georgia fallback for email clients)
- Body font: Arial/Helvetica (safe email fallback for Inter)
- Max width: 600px, centered
- No emoji, no exclamation marks (per brand voice guidelines)

### CTA Button Style

```html
<a href="{url}" style="
  display: inline-block;
  background-color: #B8553A;
  color: #FFFFFF;
  padding: 14px 28px;
  text-decoration: none;
  font-family: Arial, Helvetica, sans-serif;
  font-size: 16px;
  font-weight: 500;
  border-radius: 4px;
">
  {button_text}
</a>
```

---

## Email Definitions

### 1. Welcome — Signup

| Field | Value |
|-------|-------|
| **Trigger** | `POST /api/credentials/register` — after successful user creation |
| **Subject** | Welcome to DeepThesis |
| **Body** | Brief intro to the platform, what they can do |
| **CTA** | "Explore the Platform" → `{FRONTEND_URL}/startups` |
| **Context** | `user_name`, `user_email` |
| **File** | `public_auth.py` — after `db.commit()` |

### 2. Analysis Complete

| Field | Value |
|-------|-------|
| **Trigger** | Analysis worker finishes all agents successfully |
| **Subject** | Your pitch analysis is ready |
| **Body** | "{startup_name} has been analyzed. View the full breakdown." |
| **CTA** | "View Analysis" → `{FRONTEND_URL}/analyze/{analysis_id}` |
| **Context** | `user_name`, `user_email`, `startup_name`, `analysis_id` |
| **File** | `analysis_worker.py` — after creating `analysis_complete` notification |

### 3. Memo Complete

| Field | Value |
|-------|-------|
| **Trigger** | Memo generator finishes successfully (status → complete) |
| **Subject** | Your investment memo is ready |
| **Body** | "The investment memo for {startup_name} is ready to download." |
| **CTA** | "Download Memo" → `{FRONTEND_URL}/analyze/{analysis_id}?tab=memo` |
| **Context** | `user_name`, `user_email`, `startup_name`, `analysis_id` |
| **File** | `memo_generator.py` — after setting status to complete |

### 4. Report Ready

| Field | Value |
|-------|-------|
| **Trigger** | Analyst report finishes generating |
| **Subject** | Your analyst report is ready |
| **Body** | "Your {format} report is ready to download." |
| **CTA** | "Download Report" → `{FRONTEND_URL}/insights` |
| **Context** | `user_name`, `user_email`, `report_format` |
| **File** | `analyst_reports.py` — after creating `report_ready` notification |

### 5. Expert Applied

| Field | Value |
|-------|-------|
| **Trigger** | `POST /api/experts/apply` — after creating application |
| **Subject** | We received your expert application |
| **Body** | Confirmation that application is under review |
| **CTA** | "View Application Status" → `{FRONTEND_URL}/experts/apply` |
| **Context** | `user_name`, `user_email` |
| **File** | `experts.py` — after `db.commit()` |

### 6. Expert Approved

| Field | Value |
|-------|-------|
| **Trigger** | Admin approves expert via `PUT /api/admin/experts/{id}/approve` |
| **Subject** | You've been approved as a DeepThesis expert |
| **Body** | Congratulations, explain what they can now do |
| **CTA** | "Start Reviewing" → `{FRONTEND_URL}/startups` |
| **Context** | `user_name`, `user_email` |
| **File** | Admin experts endpoint — after approval commit |

### 7. Expert Rejected

| Field | Value |
|-------|-------|
| **Trigger** | Admin rejects expert via `PUT /api/admin/experts/{id}/reject` |
| **Subject** | Update on your expert application |
| **Body** | Professional decline, encourage to update profile and reapply |
| **CTA** | "View Profile" → `{FRONTEND_URL}/profile` |
| **Context** | `user_name`, `user_email` |
| **File** | Admin experts endpoint — after rejection commit |

### 8. Payment Failed

| Field | Value |
|-------|-------|
| **Trigger** | Stripe webhook `invoice.payment_failed` |
| **Subject** | Action needed: payment failed |
| **Body** | Payment could not be processed, update payment method to avoid service interruption |
| **CTA** | "Update Payment Method" → portal session URL or `{FRONTEND_URL}/profile` |
| **Context** | `user_name`, `user_email` |
| **File** | `billing.py` — in `invoice.payment_failed` webhook handler |

### 9. Subscription Confirmed

| Field | Value |
|-------|-------|
| **Trigger** | Stripe webhook `checkout.session.completed` |
| **Subject** | Your {tier} plan is active |
| **Body** | Subscription confirmed, what's included in their tier |
| **CTA** | "Go to Dashboard" → `{FRONTEND_URL}/startups` |
| **Context** | `user_name`, `user_email`, `tier_name` |
| **File** | `billing.py` — in `checkout.session.completed` webhook handler |

### 10. Subscription Cancelled

| Field | Value |
|-------|-------|
| **Trigger** | Stripe webhook `customer.subscription.deleted` |
| **Subject** | Your subscription has been cancelled |
| **Body** | Access continues until end of billing period, option to resubscribe |
| **CTA** | "Resubscribe" → `{FRONTEND_URL}/profile` |
| **Context** | `user_name`, `user_email` |
| **File** | `billing.py` — in `customer.subscription.deleted` webhook handler |

---

## Integration Points

Each email is added as a single `email_service.send_*()` call at the event source, wrapped in try/except:

```python
try:
    email_service.send_analysis_complete(
        user_email=user.email,
        user_name=user.name,
        analysis_id=str(analysis.id),
        startup_name=analysis.company_name,
    )
except Exception:
    logger.warning("Failed to send analysis_complete email", exc_info=True)
```

**Files modified for integration:**
- `backend/app/api/public_auth.py` — welcome email after signup
- `backend/app/services/analysis_worker.py` — analysis complete email
- `backend/app/services/memo_generator.py` — memo complete email
- `backend/app/services/analyst_reports.py` — report ready email
- `backend/app/api/experts.py` — expert applied email
- `backend/app/api/admin/experts.py` (or equivalent admin endpoint) — expert approved/rejected emails
- `backend/app/api/billing.py` — payment failed, subscription confirmed, subscription cancelled emails

---

## Error Handling

- All email sends wrapped in try/except — failures are logged as warnings, never raised
- EmailService is a no-op if `RESEND_API_KEY` is not configured (dev/test environments)
- No retry logic — Resend handles delivery retries internally
- No database tracking of sent emails — Resend dashboard provides delivery logs

---

## What This Spec Does NOT Cover

- Email forwarding from `gaius@deepthesis.org` → `lee@deepthesis.org` (separate task, requires AWS SES receiving + Zoho mailbox setup)
- Email preferences / unsubscribe (can be added later if users request it)
- Marketing / drip emails
- Email queueing (unnecessary at current scale; Resend API is ~200ms)
