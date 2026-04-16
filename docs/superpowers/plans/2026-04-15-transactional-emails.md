# Transactional Email System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add branded transactional emails for 10 platform events using the Resend API and Jinja2 HTML templates.

**Architecture:** A single `EmailService` class wraps the Resend Python SDK, renders Jinja2 HTML templates with brand styling, and exposes one method per email type. Each method is called at the event source (signup, analysis complete, billing webhook, etc.) wrapped in try/except so email failures never break the main flow.

**Tech Stack:** Resend Python SDK, Jinja2 (via FastAPI), inline CSS for email HTML

---

## File Structure

```
backend/
  app/
    config.py                          # MODIFY — add resend_api_key, email_from
    services/
      email_service.py                 # CREATE — EmailService class
    templates/
      emails/
        base.html                      # CREATE — shared branded layout
        welcome.html                   # CREATE
        analysis_complete.html         # CREATE
        memo_complete.html             # CREATE
        report_ready.html              # CREATE
        expert_applied.html            # CREATE
        expert_approved.html           # CREATE
        expert_rejected.html           # CREATE
        payment_failed.html            # CREATE
        subscription_confirmed.html    # CREATE
        subscription_cancelled.html    # CREATE
    api/
      public_auth.py                   # MODIFY — add welcome email
      experts.py                       # MODIFY — add expert_applied email
      admin.py                         # MODIFY — add expert_approved/rejected emails
      billing.py                       # MODIFY — add billing emails
    services/
      analysis_worker.py               # MODIFY — add analysis_complete email
      memo_generator.py                # MODIFY — add memo_complete email
      analyst_reports.py               # MODIFY — add report_ready email
  pyproject.toml                       # MODIFY — add resend dependency
docker-compose.yml                     # MODIFY — add env var mapping
```

---

### Task 1: Add Resend dependency and config

**Files:**
- Modify: `backend/pyproject.toml:5-27`
- Modify: `backend/app/config.py:20-29`
- Modify: `docker-compose.yml:22-36`

- [ ] **Step 1: Add `resend` to pyproject.toml**

In `backend/pyproject.toml`, add `"resend>=2.0.0",` after the `stripe` line:

```toml
    "stripe>=8.0.0",
    "resend>=2.0.0",
]
```

- [ ] **Step 2: Add email config fields to Settings**

In `backend/app/config.py`, add after the `promo_code_unlimited` line (line 27) and before `model_config`:

```python
    # Email (Resend)
    resend_api_key: str = ""
    email_from: str = "gaius@deepthesis.org"
```

- [ ] **Step 3: Add env var mappings to docker-compose.yml**

In `docker-compose.yml`, add to the `backend.environment` section after the Stripe vars:

```yaml
      ACUTAL_RESEND_API_KEY: ${RESEND_API_KEY:-}
      ACUTAL_EMAIL_FROM: ${EMAIL_FROM:-gaius@deepthesis.org}
      ACUTAL_FRONTEND_URL: ${FRONTEND_URL:-https://deepthesis.org}
```

Note: `ACUTAL_FRONTEND_URL` is already in `config.py` as `frontend_url` but was not mapped in docker-compose.

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/app/config.py docker-compose.yml
git commit -m "feat(email): add Resend dependency and config"
```

---

### Task 2: Create EmailService

**Files:**
- Create: `backend/app/services/email_service.py`

- [ ] **Step 1: Create the email service**

Create `backend/app/services/email_service.py`:

```python
import logging
from pathlib import Path

import resend
from jinja2 import Environment, FileSystemLoader

from app.config import settings

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "emails"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=True,
)


def _send(to: str, subject: str, template_name: str, context: dict) -> None:
    """Render a Jinja2 template and send via Resend. No-op if API key is not set."""
    if not settings.resend_api_key:
        logger.debug("Resend API key not configured — skipping email to %s", to)
        return

    resend.api_key = settings.resend_api_key
    html = _env.get_template(template_name).render(**context)

    resend.Emails.send(
        {
            "from": settings.email_from,
            "to": [to],
            "subject": subject,
            "html": html,
        }
    )
    logger.info("Email sent: %s → %s", subject, to)


def send_welcome(user_email: str, user_name: str) -> None:
    try:
        _send(
            to=user_email,
            subject="Welcome to DeepThesis",
            template_name="welcome.html",
            context={
                "user_name": user_name,
                "cta_url": f"{settings.frontend_url}/startups",
            },
        )
    except Exception:
        logger.warning("Failed to send welcome email to %s", user_email, exc_info=True)


def send_analysis_complete(
    user_email: str, user_name: str, analysis_id: str, startup_name: str
) -> None:
    try:
        _send(
            to=user_email,
            subject="Your pitch analysis is ready",
            template_name="analysis_complete.html",
            context={
                "user_name": user_name,
                "startup_name": startup_name,
                "cta_url": f"{settings.frontend_url}/analyze/{analysis_id}",
            },
        )
    except Exception:
        logger.warning("Failed to send analysis_complete email to %s", user_email, exc_info=True)


def send_memo_complete(
    user_email: str, user_name: str, analysis_id: str, startup_name: str
) -> None:
    try:
        _send(
            to=user_email,
            subject="Your investment memo is ready",
            template_name="memo_complete.html",
            context={
                "user_name": user_name,
                "startup_name": startup_name,
                "cta_url": f"{settings.frontend_url}/analyze/{analysis_id}?tab=memo",
            },
        )
    except Exception:
        logger.warning("Failed to send memo_complete email to %s", user_email, exc_info=True)


def send_report_ready(
    user_email: str, user_name: str, report_format: str
) -> None:
    try:
        _send(
            to=user_email,
            subject="Your analyst report is ready",
            template_name="report_ready.html",
            context={
                "user_name": user_name,
                "report_format": report_format.upper(),
                "cta_url": f"{settings.frontend_url}/insights",
            },
        )
    except Exception:
        logger.warning("Failed to send report_ready email to %s", user_email, exc_info=True)


def send_expert_applied(user_email: str, user_name: str) -> None:
    try:
        _send(
            to=user_email,
            subject="We received your expert application",
            template_name="expert_applied.html",
            context={
                "user_name": user_name,
                "cta_url": f"{settings.frontend_url}/experts/apply",
            },
        )
    except Exception:
        logger.warning("Failed to send expert_applied email to %s", user_email, exc_info=True)


def send_expert_approved(user_email: str, user_name: str) -> None:
    try:
        _send(
            to=user_email,
            subject="You've been approved as a DeepThesis expert",
            template_name="expert_approved.html",
            context={
                "user_name": user_name,
                "cta_url": f"{settings.frontend_url}/startups",
            },
        )
    except Exception:
        logger.warning("Failed to send expert_approved email to %s", user_email, exc_info=True)


def send_expert_rejected(user_email: str, user_name: str) -> None:
    try:
        _send(
            to=user_email,
            subject="Update on your expert application",
            template_name="expert_rejected.html",
            context={
                "user_name": user_name,
                "cta_url": f"{settings.frontend_url}/profile",
            },
        )
    except Exception:
        logger.warning("Failed to send expert_rejected email to %s", user_email, exc_info=True)


def send_payment_failed(user_email: str, user_name: str) -> None:
    try:
        _send(
            to=user_email,
            subject="Action needed: payment failed",
            template_name="payment_failed.html",
            context={
                "user_name": user_name,
                "cta_url": f"{settings.frontend_url}/profile",
            },
        )
    except Exception:
        logger.warning("Failed to send payment_failed email to %s", user_email, exc_info=True)


def send_subscription_confirmed(
    user_email: str, user_name: str, tier_name: str
) -> None:
    try:
        _send(
            to=user_email,
            subject=f"Your {tier_name} plan is active",
            template_name="subscription_confirmed.html",
            context={
                "user_name": user_name,
                "tier_name": tier_name,
                "cta_url": f"{settings.frontend_url}/startups",
            },
        )
    except Exception:
        logger.warning("Failed to send subscription_confirmed email to %s", user_email, exc_info=True)


def send_subscription_cancelled(user_email: str, user_name: str) -> None:
    try:
        _send(
            to=user_email,
            subject="Your subscription has been cancelled",
            template_name="subscription_cancelled.html",
            context={
                "user_name": user_name,
                "cta_url": f"{settings.frontend_url}/profile",
            },
        )
    except Exception:
        logger.warning("Failed to send subscription_cancelled email to %s", user_email, exc_info=True)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/email_service.py
git commit -m "feat(email): add EmailService with Resend SDK"
```

---

### Task 3: Create base email template

**Files:**
- Create: `backend/app/templates/emails/base.html`

- [ ] **Step 1: Create the templates directory**

```bash
mkdir -p backend/app/templates/emails
```

- [ ] **Step 2: Create the base template**

Create `backend/app/templates/emails/base.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}DeepThesis{% endblock %}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #FAFAF8; font-family: Arial, Helvetica, sans-serif; color: #1A1A1A; -webkit-text-size-adjust: 100%;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color: #FAFAF8;">
    <tr>
      <td align="center" style="padding: 40px 20px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width: 600px; width: 100%; background-color: #FFFFFF; border: 1px solid #E8E6E3; border-radius: 4px;">

          <!-- Header -->
          <tr>
            <td style="padding: 32px 40px 24px 40px; border-bottom: 2px solid #B8553A;">
              <span style="font-family: Georgia, 'Times New Roman', serif; font-size: 24px; color: #1A1A1A; font-weight: normal; letter-spacing: -0.5px;">DeepThesis</span>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding: 40px;">
              {% block content %}{% endblock %}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding: 24px 40px; border-top: 1px solid #E8E6E3; text-align: center;">
              <p style="margin: 0; font-size: 12px; color: #9B9B9B; line-height: 1.6;">
                &copy; 2026 DeepThesis &middot; <a href="https://deepthesis.org" style="color: #9B9B9B; text-decoration: underline;">deepthesis.org</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/templates/emails/base.html
git commit -m "feat(email): add base HTML email template with brand styling"
```

---

### Task 4: Create all email templates

**Files:**
- Create: `backend/app/templates/emails/welcome.html`
- Create: `backend/app/templates/emails/analysis_complete.html`
- Create: `backend/app/templates/emails/memo_complete.html`
- Create: `backend/app/templates/emails/report_ready.html`
- Create: `backend/app/templates/emails/expert_applied.html`
- Create: `backend/app/templates/emails/expert_approved.html`
- Create: `backend/app/templates/emails/expert_rejected.html`
- Create: `backend/app/templates/emails/payment_failed.html`
- Create: `backend/app/templates/emails/subscription_confirmed.html`
- Create: `backend/app/templates/emails/subscription_cancelled.html`

All templates extend `base.html` and use a consistent pattern: greeting, body paragraph(s), CTA button, optional secondary text.

**CTA button HTML (reuse in every template):**
```html
<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 32px 0;">
  <tr>
    <td style="background-color: #B8553A; border-radius: 4px;">
      <a href="{{ cta_url }}" style="display: inline-block; padding: 14px 28px; color: #FFFFFF; text-decoration: none; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: 500;">BUTTON_TEXT</a>
    </td>
  </tr>
</table>
```

- [ ] **Step 1: Create welcome.html**

Create `backend/app/templates/emails/welcome.html`:

```html
{% extends "base.html" %}
{% block title %}Welcome to DeepThesis{% endblock %}
{% block content %}
<h1 style="font-family: Georgia, 'Times New Roman', serif; font-size: 28px; font-weight: normal; color: #1A1A1A; margin: 0 0 24px 0;">Welcome, {{ user_name }}</h1>

<p style="font-size: 16px; line-height: 1.6; color: #1A1A1A; margin: 0 0 16px 0;">
  Your account has been created. DeepThesis provides AI-powered due diligence and investment analysis for institutional investors.
</p>

<p style="font-size: 16px; line-height: 1.6; color: #1A1A1A; margin: 0 0 8px 0;">
  You can now browse startup analyses, upload pitch decks for analysis, and access our AI research analyst.
</p>

<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 32px 0;">
  <tr>
    <td style="background-color: #B8553A; border-radius: 4px;">
      <a href="{{ cta_url }}" style="display: inline-block; padding: 14px 28px; color: #FFFFFF; text-decoration: none; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: 500;">Explore the Platform</a>
    </td>
  </tr>
</table>
{% endblock %}
```

- [ ] **Step 2: Create analysis_complete.html**

Create `backend/app/templates/emails/analysis_complete.html`:

```html
{% extends "base.html" %}
{% block title %}Analysis Ready{% endblock %}
{% block content %}
<h1 style="font-family: Georgia, 'Times New Roman', serif; font-size: 28px; font-weight: normal; color: #1A1A1A; margin: 0 0 24px 0;">Analysis Complete</h1>

<p style="font-size: 16px; line-height: 1.6; color: #1A1A1A; margin: 0 0 16px 0;">
  Hi {{ user_name }}, the pitch analysis for <strong>{{ startup_name }}</strong> is complete. View the full breakdown including scoring, risk factors, and investment recommendations.
</p>

<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 32px 0;">
  <tr>
    <td style="background-color: #B8553A; border-radius: 4px;">
      <a href="{{ cta_url }}" style="display: inline-block; padding: 14px 28px; color: #FFFFFF; text-decoration: none; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: 500;">View Analysis</a>
    </td>
  </tr>
</table>
{% endblock %}
```

- [ ] **Step 3: Create memo_complete.html**

Create `backend/app/templates/emails/memo_complete.html`:

```html
{% extends "base.html" %}
{% block title %}Memo Ready{% endblock %}
{% block content %}
<h1 style="font-family: Georgia, 'Times New Roman', serif; font-size: 28px; font-weight: normal; color: #1A1A1A; margin: 0 0 24px 0;">Investment Memo Ready</h1>

<p style="font-size: 16px; line-height: 1.6; color: #1A1A1A; margin: 0 0 16px 0;">
  Hi {{ user_name }}, the investment memo for <strong>{{ startup_name }}</strong> is ready. Download it in PDF or DOCX format.
</p>

<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 32px 0;">
  <tr>
    <td style="background-color: #B8553A; border-radius: 4px;">
      <a href="{{ cta_url }}" style="display: inline-block; padding: 14px 28px; color: #FFFFFF; text-decoration: none; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: 500;">Download Memo</a>
    </td>
  </tr>
</table>
{% endblock %}
```

- [ ] **Step 4: Create report_ready.html**

Create `backend/app/templates/emails/report_ready.html`:

```html
{% extends "base.html" %}
{% block title %}Report Ready{% endblock %}
{% block content %}
<h1 style="font-family: Georgia, 'Times New Roman', serif; font-size: 28px; font-weight: normal; color: #1A1A1A; margin: 0 0 24px 0;">Report Ready</h1>

<p style="font-size: 16px; line-height: 1.6; color: #1A1A1A; margin: 0 0 16px 0;">
  Hi {{ user_name }}, your {{ report_format }} analyst report is ready to download.
</p>

<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 32px 0;">
  <tr>
    <td style="background-color: #B8553A; border-radius: 4px;">
      <a href="{{ cta_url }}" style="display: inline-block; padding: 14px 28px; color: #FFFFFF; text-decoration: none; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: 500;">Download Report</a>
    </td>
  </tr>
</table>
{% endblock %}
```

- [ ] **Step 5: Create expert_applied.html**

Create `backend/app/templates/emails/expert_applied.html`:

```html
{% extends "base.html" %}
{% block title %}Application Received{% endblock %}
{% block content %}
<h1 style="font-family: Georgia, 'Times New Roman', serif; font-size: 28px; font-weight: normal; color: #1A1A1A; margin: 0 0 24px 0;">Application Received</h1>

<p style="font-size: 16px; line-height: 1.6; color: #1A1A1A; margin: 0 0 16px 0;">
  Hi {{ user_name }}, we have received your expert application. Our team will review it and follow up with a decision.
</p>

<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 32px 0;">
  <tr>
    <td style="background-color: #B8553A; border-radius: 4px;">
      <a href="{{ cta_url }}" style="display: inline-block; padding: 14px 28px; color: #FFFFFF; text-decoration: none; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: 500;">View Application Status</a>
    </td>
  </tr>
</table>
{% endblock %}
```

- [ ] **Step 6: Create expert_approved.html**

Create `backend/app/templates/emails/expert_approved.html`:

```html
{% extends "base.html" %}
{% block title %}Expert Approved{% endblock %}
{% block content %}
<h1 style="font-family: Georgia, 'Times New Roman', serif; font-size: 28px; font-weight: normal; color: #1A1A1A; margin: 0 0 24px 0;">You've Been Approved</h1>

<p style="font-size: 16px; line-height: 1.6; color: #1A1A1A; margin: 0 0 16px 0;">
  Hi {{ user_name }}, your expert application has been approved. You can now review startups and provide due diligence assessments on the platform.
</p>

<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 32px 0;">
  <tr>
    <td style="background-color: #B8553A; border-radius: 4px;">
      <a href="{{ cta_url }}" style="display: inline-block; padding: 14px 28px; color: #FFFFFF; text-decoration: none; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: 500;">Start Reviewing</a>
    </td>
  </tr>
</table>
{% endblock %}
```

- [ ] **Step 7: Create expert_rejected.html**

Create `backend/app/templates/emails/expert_rejected.html`:

```html
{% extends "base.html" %}
{% block title %}Application Update{% endblock %}
{% block content %}
<h1 style="font-family: Georgia, 'Times New Roman', serif; font-size: 28px; font-weight: normal; color: #1A1A1A; margin: 0 0 24px 0;">Application Update</h1>

<p style="font-size: 16px; line-height: 1.6; color: #1A1A1A; margin: 0 0 16px 0;">
  Hi {{ user_name }}, after reviewing your expert application, we are unable to approve it at this time. You are welcome to update your profile and reapply in the future.
</p>

<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 32px 0;">
  <tr>
    <td style="background-color: #B8553A; border-radius: 4px;">
      <a href="{{ cta_url }}" style="display: inline-block; padding: 14px 28px; color: #FFFFFF; text-decoration: none; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: 500;">View Profile</a>
    </td>
  </tr>
</table>
{% endblock %}
```

- [ ] **Step 8: Create payment_failed.html**

Create `backend/app/templates/emails/payment_failed.html`:

```html
{% extends "base.html" %}
{% block title %}Payment Failed{% endblock %}
{% block content %}
<h1 style="font-family: Georgia, 'Times New Roman', serif; font-size: 28px; font-weight: normal; color: #1A1A1A; margin: 0 0 24px 0;">Payment Failed</h1>

<p style="font-size: 16px; line-height: 1.6; color: #1A1A1A; margin: 0 0 16px 0;">
  Hi {{ user_name }}, your most recent payment could not be processed. Please update your payment method to avoid interruption to your subscription.
</p>

<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 32px 0;">
  <tr>
    <td style="background-color: #B8553A; border-radius: 4px;">
      <a href="{{ cta_url }}" style="display: inline-block; padding: 14px 28px; color: #FFFFFF; text-decoration: none; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: 500;">Update Payment Method</a>
    </td>
  </tr>
</table>
{% endblock %}
```

- [ ] **Step 9: Create subscription_confirmed.html**

Create `backend/app/templates/emails/subscription_confirmed.html`:

```html
{% extends "base.html" %}
{% block title %}Subscription Active{% endblock %}
{% block content %}
<h1 style="font-family: Georgia, 'Times New Roman', serif; font-size: 28px; font-weight: normal; color: #1A1A1A; margin: 0 0 24px 0;">Your {{ tier_name }} Plan is Active</h1>

<p style="font-size: 16px; line-height: 1.6; color: #1A1A1A; margin: 0 0 16px 0;">
  Hi {{ user_name }}, your {{ tier_name }} subscription has been activated. You now have full access to all features included in your plan.
</p>

<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 32px 0;">
  <tr>
    <td style="background-color: #B8553A; border-radius: 4px;">
      <a href="{{ cta_url }}" style="display: inline-block; padding: 14px 28px; color: #FFFFFF; text-decoration: none; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: 500;">Go to Dashboard</a>
    </td>
  </tr>
</table>
{% endblock %}
```

- [ ] **Step 10: Create subscription_cancelled.html**

Create `backend/app/templates/emails/subscription_cancelled.html`:

```html
{% extends "base.html" %}
{% block title %}Subscription Cancelled{% endblock %}
{% block content %}
<h1 style="font-family: Georgia, 'Times New Roman', serif; font-size: 28px; font-weight: normal; color: #1A1A1A; margin: 0 0 24px 0;">Subscription Cancelled</h1>

<p style="font-size: 16px; line-height: 1.6; color: #1A1A1A; margin: 0 0 16px 0;">
  Hi {{ user_name }}, your subscription has been cancelled. You will continue to have access until the end of your current billing period.
</p>

<p style="font-size: 14px; line-height: 1.6; color: #6B6B6B; margin: 0 0 8px 0;">
  If this was unintentional, you can resubscribe at any time.
</p>

<table role="presentation" cellpadding="0" cellspacing="0" style="margin: 32px 0;">
  <tr>
    <td style="background-color: #B8553A; border-radius: 4px;">
      <a href="{{ cta_url }}" style="display: inline-block; padding: 14px 28px; color: #FFFFFF; text-decoration: none; font-family: Arial, Helvetica, sans-serif; font-size: 16px; font-weight: 500;">Resubscribe</a>
    </td>
  </tr>
</table>
{% endblock %}
```

- [ ] **Step 11: Commit**

```bash
git add backend/app/templates/
git commit -m "feat(email): add all 10 branded HTML email templates"
```

---

### Task 5: Integrate — welcome email on signup

**Files:**
- Modify: `backend/app/api/public_auth.py:94-95`

- [ ] **Step 1: Add email import and call**

In `backend/app/api/public_auth.py`, add to the imports at the top:

```python
from app.services import email_service
```

Then after line 95 (`await db.refresh(user)`) and before the return statement (line 97), add:

```python
    email_service.send_welcome(user_email=user.email, user_name=user.name)
```

The full function ending becomes:

```python
    db.add(user)
    await db.commit()
    await db.refresh(user)

    email_service.send_welcome(user_email=user.email, user_name=user.name)

    return {
        "token": make_token(user),
        "user": _user_dict(user),
        "promo_applied": bool(promo_valid),
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/public_auth.py
git commit -m "feat(email): send welcome email on signup"
```

---

### Task 6: Integrate — expert application emails

**Files:**
- Modify: `backend/app/api/experts.py:54`
- Modify: `backend/app/api/admin.py:345-393`

- [ ] **Step 1: Add email to expert apply**

In `backend/app/api/experts.py`, add to imports:

```python
from app.services import email_service
```

After line 54 (`await db.commit()`) and before the re-fetch query (line 57), add:

```python
    email_service.send_expert_applied(user_email=user.email, user_name=user.name)
```

- [ ] **Step 2: Add emails to admin approve/reject**

In `backend/app/api/admin.py`, add to imports (near the top of the file, with the other imports):

```python
from app.services import email_service
```

In `approve_expert` (around line 365), after `await db.commit()` and before `await db.refresh(profile)`, add:

```python
    email_service.send_expert_approved(user_email=user.email, user_name=user.name)
```

The `user` variable is already loaded at line 362: `user = user_result.scalar_one()`.

In `reject_expert` (around line 387), after `await db.commit()` and before `await db.refresh(profile)`, load the user and send the email:

```python
    user_result = await db.execute(select(User).where(User.id == profile.user_id))
    user = user_result.scalar_one()
    email_service.send_expert_rejected(user_email=user.email, user_name=user.name)
```

Make sure `User` is imported at the top of `admin.py`. Check if it already is — it's likely imported as it's used elsewhere in the file.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/experts.py backend/app/api/admin.py
git commit -m "feat(email): send expert application/approval/rejection emails"
```

---

### Task 7: Integrate — analysis complete email

**Files:**
- Modify: `backend/app/services/analysis_worker.py:285-296`

- [ ] **Step 1: Add email after analysis notification**

In `backend/app/services/analysis_worker.py`, add to imports at the top:

```python
from app.services import email_service
from app.models.user import User
```

After the notification commit (line 294: `await db.commit()`) and before the logger.info (line 296), add a user lookup and email send:

```python
        # Send email notification
        user_result = await db.execute(select(User).where(User.id == analysis.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            email_service.send_analysis_complete(
                user_email=user.email,
                user_name=user.name,
                analysis_id=str(analysis.id),
                startup_name=company_name or "Your startup",
            )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/analysis_worker.py
git commit -m "feat(email): send email on analysis completion"
```

---

### Task 8: Integrate — memo complete email

**Files:**
- Modify: `backend/app/services/memo_generator.py:448-453`

- [ ] **Step 1: Add email after memo completion**

In `backend/app/services/memo_generator.py`, add to imports at the top:

```python
from app.services import email_service
from app.models.user import User
```

After the memo complete commit (line 450: `await db.commit()`) and before the logger.info (line 452), add:

```python
            # Send email notification
            user_result = await db.execute(select(User).where(User.id == analysis.user_id))
            user = user_result.scalar_one_or_none()
            if user:
                email_service.send_memo_complete(
                    user_email=user.email,
                    user_name=user.name,
                    analysis_id=str(analysis.id),
                    startup_name=analysis.company_name or "Your startup",
                )
```

Note: `analysis` is already loaded at line 376 in this function.

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/memo_generator.py
git commit -m "feat(email): send email on memo completion"
```

---

### Task 9: Integrate — report ready email

**Files:**
- Modify: `backend/app/services/analyst_reports.py:663-675`

- [ ] **Step 1: Add email after report notification**

In `backend/app/services/analyst_reports.py`, add to imports at the top:

```python
from app.services import email_service
from app.models.user import User
```

After the notification commit (line 673: `await db.commit()`) and before the logger.info (line 675), add:

```python
            # Send email notification
            user_result = await db.execute(select(User).where(User.id == report.user_id))
            user = user_result.scalar_one_or_none()
            if user:
                email_service.send_report_ready(
                    user_email=user.email,
                    user_name=user.name,
                    report_format=ext,
                )
```

Note: `ext` is already defined at this point (line 639-651).

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/analyst_reports.py
git commit -m "feat(email): send email on report ready"
```

---

### Task 10: Integrate — billing emails

**Files:**
- Modify: `backend/app/api/billing.py:175-299`

- [ ] **Step 1: Add email import**

In `backend/app/api/billing.py`, add to imports:

```python
from app.services import email_service
```

- [ ] **Step 2: Add subscription confirmed email**

In `_handle_checkout_completed`, after line 219 (`await db.commit()`) and before line 220 (`logger.info(...)`), add:

```python
    email_service.send_subscription_confirmed(
        user_email=user.email,
        user_name=user.name,
        tier_name=tier or "subscription",
    )
```

- [ ] **Step 3: Add subscription cancelled email**

In `_handle_subscription_deleted`, after line 280 (`await db.commit()`) and before line 281 (`logger.info(...)`), add:

```python
    email_service.send_subscription_cancelled(
        user_email=user.email,
        user_name=user.name,
    )
```

- [ ] **Step 4: Add payment failed email**

In `_handle_payment_failed`, after line 297 (`await db.commit()`) and before line 298 (`logger.info(...)`), add:

```python
    email_service.send_payment_failed(
        user_email=user.email,
        user_name=user.name,
    )
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/billing.py
git commit -m "feat(email): send billing emails (subscription confirmed/cancelled, payment failed)"
```

---

### Task 11: Add Resend API key to EC2 and deploy

**Files:**
- Modify: EC2 `.env` file (remote)

- [ ] **Step 1: Add Resend API key to EC2 .env**

```bash
ssh -i ~/.ssh/acutal-deploy.pem ec2-user@98.89.232.52 "echo 'RESEND_API_KEY=re_eorUadEg_Pb453AYeV9DkBo1UBwg61fQK' >> /home/ec2-user/acutal/.env"
```

- [ ] **Step 2: Rsync changes to EC2**

```bash
rsync -avz --exclude='.git' --exclude='node_modules' --exclude='.next' --exclude='__pycache__' -e "ssh -i ~/.ssh/acutal-deploy.pem" /Users/leemosbacker/acutal/ ec2-user@98.89.232.52:/home/ec2-user/acutal/
```

- [ ] **Step 3: Rebuild backend**

```bash
ssh -i ~/.ssh/acutal-deploy.pem ec2-user@98.89.232.52 "cd /home/ec2-user/acutal && docker compose up -d --build backend"
```

- [ ] **Step 4: Verify backend is healthy**

```bash
ssh -i ~/.ssh/acutal-deploy.pem ec2-user@98.89.232.52 "curl -s http://127.0.0.1:8000/api/health"
```

Expected: `{"status":"ok"}`

- [ ] **Step 5: Test by creating a new account on the site**

Sign up with a test email on `https://deepthesis.org` and verify the welcome email arrives.
