# Stripe Subscription & Billing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect Stripe to the existing subscription gating so users can pay, add a billing management page, and restructure navigation into a user dropdown menu.

**Architecture:** Stripe Checkout (hosted) for new subscriptions, Stripe Customer Portal (hosted) for managing subscriptions, webhook endpoint for keeping DB in sync. Three tiers: Starter ($19.99/mo), Professional ($200/mo), Unlimited ($500/mo). All Stripe Price IDs configured as env vars.

**Tech Stack:** Python `stripe` library, FastAPI, SQLAlchemy, Alembic, Next.js, NextAuth.js

---

## File Structure

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `backend/pyproject.toml` | Add `stripe>=8.0.0` dependency |
| Modify | `backend/app/config.py` | Add Stripe settings |
| Modify | `backend/app/models/user.py` | Add Stripe columns + `past_due` enum value |
| Create | `backend/alembic/versions/p4q5r6s7t8u9_add_stripe_billing_columns.py` | Migration for new columns |
| Create | `backend/app/api/billing.py` | All billing endpoints (checkout, portal, status, webhook) |
| Modify | `backend/app/main.py` | Register billing router |
| Modify | `docker-compose.prod.yml` | Add Stripe env vars to backend service |
| Modify | `frontend/lib/types.ts` | Add `BillingStatus` type |
| Modify | `frontend/lib/api.ts` | Add billing API methods |
| Modify | `frontend/components/AuthButton.tsx` | Replace link with dropdown menu |
| Create | `frontend/app/billing/page.tsx` | Billing management page |
| Modify | `frontend/middleware.ts` | Add `/billing` to protected paths |
| Modify | `frontend/app/page.tsx` | Dynamic pricing CTAs |

---

### Task 1: Add Stripe Dependency and Config

**Files:**
- Modify: `backend/pyproject.toml:5-26`
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add stripe to pyproject.toml**

In `backend/pyproject.toml`, add `"stripe>=8.0.0"` to the dependencies list:

```toml
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "pydantic-settings>=2.6.0",
    "python-jose[cryptography]>=3.3.0",
    "httpx>=0.27.0",
    "bcrypt>=4.0.0",
    "email-validator>=2.0.0",
    "boto3>=1.35.0",
    "anthropic>=0.40.0",
    "pymupdf>=1.24.0",
    "python-docx>=1.1.0",
    "python-pptx>=1.0.0",
    "openpyxl>=3.1.0",
    "matplotlib>=3.9.0",
    "xlrd>=2.0.0",
    "python-multipart>=0.0.9",
    "reportlab>=4.0.0",
    "stripe>=8.0.0",
]
```

- [ ] **Step 2: Add Stripe settings to config**

Replace the entire `backend/app/config.py` with:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://acutal:acutal@localhost:5432/acutal"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001", "http://98.89.232.52:3000", "http://98.89.232.52:3001", "https://deepthesis.org", "https://admin.deepthesis.org", "https://www.deepthesis.org"]
    admin_setup_key: str = "acutal-setup-2024"
    logo_dev_token: str = ""
    perplexity_api_key: str = ""
    anthropic_api_key: str = ""
    database_readonly_url: str = ""
    edgar_user_agent: str = "Acutal admin@deepthesis.org"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    s3_bucket_name: str = "deepthesis-pitch-documents"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""
    stripe_price_professional: str = ""
    stripe_price_unlimited: str = ""
    frontend_url: str = "https://deepthesis.org"

    model_config = {"env_prefix": "ACUTAL_"}


settings = Settings()
```

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml backend/app/config.py
git commit -m "feat: add Stripe dependency and config settings"
```

---

### Task 2: User Model — Add Stripe Columns and Migration

**Files:**
- Modify: `backend/app/models/user.py`
- Create: `backend/alembic/versions/p4q5r6s7t8u9_add_stripe_billing_columns.py`

- [ ] **Step 1: Update User model with Stripe fields**

Replace the entire `backend/app/models/user.py` with:

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.industry import Base


class AuthProvider(str, enum.Enum):
    google = "google"
    linkedin = "linkedin"
    github = "github"
    credentials = "credentials"


class UserRole(str, enum.Enum):
    user = "user"
    expert = "expert"
    superadmin = "superadmin"


class SubscriptionStatus(str, enum.Enum):
    none = "none"
    active = "active"
    cancelled = "cancelled"
    past_due = "past_due"


class SubscriptionTier(str, enum.Enum):
    starter = "starter"
    professional = "professional"
    unlimited = "unlimited"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    auth_provider: Mapped[AuthProvider] = mapped_column(Enum(AuthProvider), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False, default=UserRole.user)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ecosystem_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subscription_status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.none, server_default="none"
    )

    # Stripe billing
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subscription_tier: Mapped[SubscriptionTier | None] = mapped_column(Enum(SubscriptionTier), nullable=True)
    subscription_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: Create Alembic migration**

Create `backend/alembic/versions/p4q5r6s7t8u9_add_stripe_billing_columns.py`:

```python
"""Add Stripe billing columns to users

Revision ID: p4q5r6s7t8u9
Revises: o3p4q5r6s7t8
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa

revision = "p4q5r6s7t8u9"
down_revision = "o3p4q5r6s7t8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add past_due to subscription status enum
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'past_due'")

    # Create subscription tier enum
    op.execute(
        "DO $$ BEGIN CREATE TYPE subscriptiontier AS ENUM ('starter', 'professional', 'unlimited'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    # Add Stripe columns to users table
    op.add_column("users", sa.Column("stripe_customer_id", sa.String(255), unique=True, nullable=True))
    op.add_column("users", sa.Column("stripe_subscription_id", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "subscription_tier",
            sa.Enum("starter", "professional", "unlimited", name="subscriptiontier", create_type=False),
            nullable=True,
        ),
    )
    op.add_column("users", sa.Column("subscription_period_end", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "subscription_period_end")
    op.drop_column("users", "subscription_tier")
    op.drop_column("users", "stripe_subscription_id")
    op.drop_column("users", "stripe_customer_id")
    op.execute("DROP TYPE IF EXISTS subscriptiontier")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/user.py backend/alembic/versions/p4q5r6s7t8u9_add_stripe_billing_columns.py
git commit -m "feat: add Stripe billing columns to User model and migration"
```

---

### Task 3: Billing API Endpoints

**Files:**
- Create: `backend/app/api/billing.py`
- Modify: `backend/app/main.py:60-91`

- [ ] **Step 1: Create the billing router**

Create `backend/app/api/billing.py`:

```python
import logging
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.models.user import SubscriptionStatus, SubscriptionTier, User

logger = logging.getLogger(__name__)

router = APIRouter()

TIER_PRICE_MAP = {
    "starter": lambda: settings.stripe_price_starter,
    "professional": lambda: settings.stripe_price_professional,
    "unlimited": lambda: settings.stripe_price_unlimited,
}

# Reverse lookup: Stripe Price ID → tier name
def _price_id_to_tier(price_id: str) -> str | None:
    for tier, get_pid in TIER_PRICE_MAP.items():
        if get_pid() == price_id:
            return tier
    return None


def _get_stripe():
    """Return configured stripe module."""
    if not settings.stripe_secret_key:
        raise HTTPException(500, "Stripe is not configured")
    stripe.api_key = settings.stripe_secret_key
    return stripe


async def _ensure_stripe_customer(user: User, db: AsyncSession) -> str:
    """Create a Stripe customer if one doesn't exist. Returns customer ID."""
    if user.stripe_customer_id:
        return user.stripe_customer_id

    s = _get_stripe()
    customer = s.Customer.create(
        email=user.email,
        name=user.name,
        metadata={"user_id": str(user.id)},
    )
    user.stripe_customer_id = customer.id
    await db.commit()
    return customer.id


# ── Checkout ─────────────────────────────────────────────────────────

class CheckoutBody(BaseModel):
    tier: str  # "starter", "professional", or "unlimited"


@router.post("/api/billing/checkout")
async def create_checkout_session(
    body: CheckoutBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.tier not in TIER_PRICE_MAP:
        raise HTTPException(400, f"Invalid tier: {body.tier}. Must be one of: starter, professional, unlimited")

    # Don't allow checkout if already on the same active tier
    sub_status = user.subscription_status
    if hasattr(sub_status, "value"):
        sub_status = sub_status.value
    current_tier = user.subscription_tier
    if hasattr(current_tier, "value"):
        current_tier = current_tier.value

    if sub_status == "active" and current_tier == body.tier:
        raise HTTPException(400, "You already have an active subscription on this tier")

    s = _get_stripe()
    customer_id = await _ensure_stripe_customer(user, db)

    price_id = TIER_PRICE_MAP[body.tier]()
    if not price_id:
        raise HTTPException(500, f"Stripe price not configured for tier: {body.tier}")

    session = s.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.frontend_url}/billing?success=true&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.frontend_url}/billing?cancelled=true",
        metadata={"user_id": str(user.id), "tier": body.tier},
    )

    return {"url": session.url}


# ── Portal ───────────────────────────────────────────────────────────

@router.post("/api/billing/portal")
async def create_portal_session(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.stripe_customer_id:
        raise HTTPException(400, "No billing account found. Subscribe to a plan first.")

    s = _get_stripe()

    session = s.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{settings.frontend_url}/billing",
    )

    return {"url": session.url}


# ── Status ───────────────────────────────────────────────────────────

@router.get("/api/billing/status")
async def get_billing_status(
    user: User = Depends(get_current_user),
):
    sub_status = user.subscription_status
    if hasattr(sub_status, "value"):
        sub_status = sub_status.value

    sub_tier = user.subscription_tier
    if hasattr(sub_tier, "value"):
        sub_tier = sub_tier.value

    period_end = None
    if user.subscription_period_end:
        period_end = user.subscription_period_end.isoformat()

    return {
        "subscription_status": sub_status,
        "subscription_tier": sub_tier,
        "subscription_period_end": period_end,
        "has_stripe_customer": user.stripe_customer_id is not None,
    }


# ── Webhook ──────────────────────────────────────────────────────────

@router.post("/api/billing/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(400, "Missing Stripe-Signature header")

    s = _get_stripe()

    try:
        event = s.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except s.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")

    event_type = event["type"]
    data = event["data"]["object"]

    logger.info("Stripe webhook: %s", event_type)

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data, db)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data, db)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data, db)
    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed(data, db)

    return {"received": True}


async def _handle_checkout_completed(session_data: dict, db: AsyncSession):
    """Handle checkout.session.completed — activate subscription."""
    from sqlalchemy import select

    customer_id = session_data.get("customer")
    subscription_id = session_data.get("subscription")
    metadata = session_data.get("metadata", {})
    tier = metadata.get("tier")
    user_id = metadata.get("user_id")

    if not customer_id:
        logger.warning("checkout.session.completed missing customer")
        return

    # Find user by stripe_customer_id or user_id from metadata
    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()

    if not user and user_id:
        import uuid
        result = await db.execute(
            select(User).where(User.id == uuid.UUID(user_id))
        )
        user = result.scalar_one_or_none()
        if user:
            user.stripe_customer_id = customer_id

    if not user:
        logger.error("checkout.session.completed: user not found for customer %s", customer_id)
        return

    user.subscription_status = SubscriptionStatus.active
    user.stripe_subscription_id = subscription_id

    if tier and tier in ("starter", "professional", "unlimited"):
        user.subscription_tier = SubscriptionTier(tier)

    # Retrieve subscription to get period end
    if subscription_id:
        try:
            s = _get_stripe()
            sub = s.Subscription.retrieve(subscription_id)
            user.subscription_period_end = datetime.fromtimestamp(
                sub.current_period_end, tz=timezone.utc
            )
        except Exception as e:
            logger.warning("Failed to retrieve subscription details: %s", e)

    await db.commit()
    logger.info("Subscription activated for user %s: tier=%s", user.id, tier)


async def _handle_subscription_updated(sub_data: dict, db: AsyncSession):
    """Handle customer.subscription.updated — plan changes, cancellation scheduling."""
    from sqlalchemy import select

    customer_id = sub_data.get("customer")
    if not customer_id:
        return

    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("subscription.updated: user not found for customer %s", customer_id)
        return

    # Update period end
    period_end = sub_data.get("current_period_end")
    if period_end:
        user.subscription_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)

    # Check for plan change
    items = sub_data.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id")
        if price_id:
            new_tier = _price_id_to_tier(price_id)
            if new_tier:
                user.subscription_tier = SubscriptionTier(new_tier)

    # Check for cancellation scheduling
    cancel_at_period_end = sub_data.get("cancel_at_period_end", False)
    status = sub_data.get("status")

    if cancel_at_period_end:
        user.subscription_status = SubscriptionStatus.cancelled
    elif status == "active":
        user.subscription_status = SubscriptionStatus.active
    elif status == "past_due":
        user.subscription_status = SubscriptionStatus.past_due

    await db.commit()
    logger.info("Subscription updated for user %s", user.id)


async def _handle_subscription_deleted(sub_data: dict, db: AsyncSession):
    """Handle customer.subscription.deleted — subscription fully ended."""
    from sqlalchemy import select

    customer_id = sub_data.get("customer")
    if not customer_id:
        return

    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("subscription.deleted: user not found for customer %s", customer_id)
        return

    user.subscription_status = SubscriptionStatus.none
    user.stripe_subscription_id = None
    user.subscription_tier = None
    user.subscription_period_end = None

    await db.commit()
    logger.info("Subscription deleted for user %s", user.id)


async def _handle_payment_failed(invoice_data: dict, db: AsyncSession):
    """Handle invoice.payment_failed — mark as past due."""
    from sqlalchemy import select

    customer_id = invoice_data.get("customer")
    if not customer_id:
        return

    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return

    user.subscription_status = SubscriptionStatus.past_due
    await db.commit()
    logger.info("Payment failed for user %s — marked past_due", user.id)
```

- [ ] **Step 2: Register billing router in main.py**

In `backend/app/main.py`, add these two lines. After the existing `from app.api.analyst import router as analyst_router` line, add:

```python
from app.api.billing import router as billing_router
```

After the existing `app.include_router(analyst_router)` line, add:

```python
app.include_router(billing_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/billing.py backend/app/main.py
git commit -m "feat: add Stripe billing endpoints (checkout, portal, status, webhook)"
```

---

### Task 4: Docker Compose — Add Stripe Env Vars

**Files:**
- Modify: `docker-compose.prod.yml:19-37`

- [ ] **Step 1: Add Stripe env vars to backend service**

In `docker-compose.prod.yml`, add these lines to the `backend` service `environment` section, after the existing `ACUTAL_S3_BUCKET_NAME` line:

```yaml
      ACUTAL_STRIPE_SECRET_KEY: ${STRIPE_SECRET_KEY:-}
      ACUTAL_STRIPE_WEBHOOK_SECRET: ${STRIPE_WEBHOOK_SECRET:-}
      ACUTAL_STRIPE_PRICE_STARTER: ${STRIPE_PRICE_STARTER:-}
      ACUTAL_STRIPE_PRICE_PROFESSIONAL: ${STRIPE_PRICE_PROFESSIONAL:-}
      ACUTAL_STRIPE_PRICE_UNLIMITED: ${STRIPE_PRICE_UNLIMITED:-}
      ACUTAL_FRONTEND_URL: ${FRONTEND_URL:-https://deepthesis.org}
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.prod.yml
git commit -m "feat: add Stripe env vars to docker-compose.prod.yml"
```

---

### Task 5: Frontend Types and API Client

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add BillingStatus type**

At the end of `frontend/lib/types.ts`, add:

```typescript
// ── Billing types ─────────────────────────────────────────────────────

export interface BillingStatus {
  subscription_status: "none" | "active" | "cancelled" | "past_due";
  subscription_tier: "starter" | "professional" | "unlimited" | null;
  subscription_period_end: string | null;
  has_stripe_customer: boolean;
}
```

- [ ] **Step 2: Add billing methods to API client**

In `frontend/lib/api.ts`, add these methods inside the `api` object, before the closing `};`:

```typescript
  // ── Billing ───────────────────────────────────────────────────────────

  async createCheckoutSession(token: string, tier: string) {
    return apiFetch<{ url: string }>("/api/billing/checkout", {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({ tier }),
    });
  },

  async createPortalSession(token: string) {
    return apiFetch<{ url: string }>("/api/billing/portal", {
      method: "POST",
      headers: authHeaders(token),
    });
  },

  async getBillingStatus(token: string) {
    return apiFetch<import("./types").BillingStatus>("/api/billing/status", {
      headers: authHeaders(token),
    });
  },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat: add billing types and API client methods"
```

---

### Task 6: Navigation Dropdown — AuthButton Refactor

**Files:**
- Modify: `frontend/components/AuthButton.tsx`

- [ ] **Step 1: Replace AuthButton with dropdown menu**

Replace the entire contents of `frontend/components/AuthButton.tsx` with:

```tsx
"use client";

import { signIn, signOut, useSession } from "next-auth/react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

export function AuthButton() {
  const { data: session } = useSession();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

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

  if (session) {
    const initials = (session.user?.name || "?")
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);

    return (
      <div ref={ref} className="relative">
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-2 hover:opacity-80 transition"
        >
          {session.user?.image ? (
            <img src={session.user.image} alt="" className="h-7 w-7 rounded-full object-cover" />
          ) : (
            <div className="h-7 w-7 rounded-full bg-accent/10 flex items-center justify-center text-accent text-xs font-medium">
              {initials}
            </div>
          )}
          <span className="text-sm text-text-secondary">{session.user?.name}</span>
          <svg
            className={`w-3.5 h-3.5 text-text-tertiary transition-transform ${open ? "rotate-180" : ""}`}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </button>

        {open && (
          <div className="absolute right-0 top-full mt-2 w-44 rounded border border-border bg-surface shadow-lg py-1 z-50">
            <Link
              href="/profile"
              onClick={() => setOpen(false)}
              className="block px-4 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-surface-alt transition"
            >
              Profile
            </Link>
            <Link
              href="/billing"
              onClick={() => setOpen(false)}
              className="block px-4 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-surface-alt transition"
            >
              Billing
            </Link>
            <div className="border-t border-border my-1" />
            <button
              onClick={() => {
                setOpen(false);
                signOut({ callbackUrl: "/" });
              }}
              className="block w-full text-left px-4 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-surface-alt transition"
            >
              Sign Out
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <Link
        href="/auth/signin"
        className="text-sm px-3 py-1.5 rounded border border-border text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
      >
        Sign In
      </Link>
      <Link
        href="/auth/signup"
        className="text-sm px-3 py-1.5 rounded bg-accent text-white hover:bg-accent-hover transition"
      >
        Sign Up
      </Link>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/AuthButton.tsx
git commit -m "feat: replace AuthButton with dropdown menu (Profile, Billing, Sign Out)"
```

---

### Task 7: Billing Page

**Files:**
- Create: `frontend/app/billing/page.tsx`
- Modify: `frontend/middleware.ts`

- [ ] **Step 1: Add /billing to protected paths in middleware**

In `frontend/middleware.ts`, update the `PROTECTED_PATHS` array and the `matcher`:

Change line 4 from:
```typescript
const PROTECTED_PATHS = ["/startups", "/insights", "/analyze"];
```
to:
```typescript
const PROTECTED_PATHS = ["/startups", "/insights", "/analyze", "/billing"];
```

Change line 31 from:
```typescript
  matcher: ["/startups/:path*", "/insights/:path*", "/analyze/:path*"],
```
to:
```typescript
  matcher: ["/startups/:path*", "/insights/:path*", "/analyze/:path*", "/billing/:path*"],
```

- [ ] **Step 2: Create the billing page**

Create `frontend/app/billing/page.tsx`:

```tsx
"use client";

import { useSession } from "next-auth/react";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { BillingStatus } from "@/lib/types";

const TIERS = [
  {
    key: "starter",
    name: "Starter",
    price: "$19.99",
    period: "/mo",
    features: [
      "10 startup analyses / month",
      "15 reports generated / month",
      "Unlimited company search & profiles",
      "VC Quant Agent access",
    ],
    highlighted: false,
  },
  {
    key: "professional",
    name: "Professional",
    price: "$200",
    period: "/mo",
    features: [
      "50 startup analyses / month",
      "Unlimited reports",
      "Unlimited company search & profiles",
      "VC Quant Agent access",
      "Priority processing",
    ],
    highlighted: true,
  },
  {
    key: "unlimited",
    name: "Unlimited",
    price: "$500",
    period: "/mo",
    features: [
      "Unlimited everything",
      "VC Quant Agent access",
      "Priority processing",
      "API access",
    ],
    highlighted: false,
  },
];

export default function BillingPage() {
  return (
    <Suspense fallback={<div className="text-center py-20 text-text-tertiary">Loading...</div>}>
      <BillingContent />
    </Suspense>
  );
}

function BillingContent() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const searchParams = useSearchParams();

  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);
  const [showSuccess, setShowSuccess] = useState(false);

  const loadBilling = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.getBillingStatus(token);
      setBilling(data);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadBilling();
  }, [loadBilling]);

  // Handle success redirect from Stripe
  useEffect(() => {
    if (searchParams.get("success") === "true" && token) {
      setShowSuccess(true);
      // Poll until status is active
      const interval = setInterval(async () => {
        try {
          const data = await api.getBillingStatus(token);
          setBilling(data);
          if (data.subscription_status === "active") {
            clearInterval(interval);
          }
        } catch {
          // keep polling
        }
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [searchParams, token]);

  const handleCheckout = async (tier: string) => {
    if (!token) return;
    setCheckoutLoading(tier);
    try {
      const { url } = await api.createCheckoutSession(token, tier);
      window.location.href = url;
    } catch (err: any) {
      alert(err.message || "Failed to start checkout");
      setCheckoutLoading(null);
    }
  };

  const handlePortal = async () => {
    if (!token) return;
    try {
      const { url } = await api.createPortalSession(token);
      window.location.href = url;
    } catch (err: any) {
      alert(err.message || "Failed to open billing portal");
    }
  };

  if (!session) {
    return (
      <div className="text-center py-20">
        <p className="text-text-secondary">Please sign in to manage billing.</p>
      </div>
    );
  }

  if (loading) {
    return <div className="text-center py-20 text-text-tertiary">Loading...</div>;
  }

  const status = billing?.subscription_status || "none";
  const tier = billing?.subscription_tier;
  const periodEnd = billing?.subscription_period_end
    ? new Date(billing.subscription_period_end).toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : null;

  // Success state after Stripe redirect
  if (showSuccess && status === "active") {
    const tierName = TIERS.find((t) => t.key === tier)?.name || tier;
    return (
      <div className="max-w-lg mx-auto py-20 text-center">
        <div className="w-16 h-16 rounded-full bg-score-high/10 flex items-center justify-center mx-auto mb-6">
          <svg className="w-8 h-8 text-score-high" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6L9 17l-5-5" />
          </svg>
        </div>
        <h1 className="font-serif text-3xl text-text-primary mb-3">Welcome to {tierName}!</h1>
        <p className="text-text-secondary mb-8">Your subscription is active. You now have full access.</p>
        <div className="flex items-center justify-center gap-4">
          <Link href="/analyze" className="px-6 py-2.5 text-sm rounded bg-accent text-white hover:bg-accent-hover transition">
            Analyze a Startup
          </Link>
          <Link href="/insights" className="px-6 py-2.5 text-sm rounded border border-border text-text-secondary hover:text-text-primary hover:border-text-tertiary transition">
            Open Analyst
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto py-10">
      <h1 className="font-serif text-3xl text-text-primary mb-8">Billing</h1>

      {/* Current plan status */}
      <div className="rounded border border-border bg-surface p-6 mb-8">
        {status === "active" && (
          <>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-text-tertiary">Current Plan</p>
                <p className="text-xl font-serif text-text-primary mt-1 capitalize">{tier}</p>
                {periodEnd && (
                  <p className="text-sm text-text-secondary mt-1">Renews on {periodEnd}</p>
                )}
              </div>
              <button
                onClick={handlePortal}
                className="px-4 py-2 text-sm rounded border border-border text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
              >
                Manage Subscription
              </button>
            </div>
          </>
        )}

        {status === "cancelled" && (
          <>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 rounded-full bg-score-mid" />
              <p className="text-sm font-medium text-score-mid">Cancelled</p>
            </div>
            <p className="text-text-primary capitalize">Your {tier} plan is cancelled</p>
            {periodEnd && (
              <p className="text-sm text-text-secondary mt-1">Access continues until {periodEnd}</p>
            )}
            <button
              onClick={handlePortal}
              className="mt-4 px-4 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover transition"
            >
              Resubscribe
            </button>
          </>
        )}

        {status === "past_due" && (
          <>
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 rounded-full bg-score-low" />
              <p className="text-sm font-medium text-score-low">Payment Failed</p>
            </div>
            <p className="text-text-secondary">Your last payment failed. Please update your payment method to continue your subscription.</p>
            <button
              onClick={handlePortal}
              className="mt-4 px-4 py-2 text-sm rounded bg-score-low text-white hover:opacity-90 transition"
            >
              Update Payment Method
            </button>
          </>
        )}

        {status === "none" && (
          <>
            <p className="text-text-primary font-medium">Free Plan</p>
            <p className="text-sm text-text-secondary mt-1">
              1 free startup analysis, 1 free analyst conversation, 20 messages per conversation.
            </p>
          </>
        )}
      </div>

      {/* Tier cards */}
      <h2 className="font-serif text-xl text-text-primary mb-4">
        {status === "active" ? "Your plan" : "Choose a plan"}
      </h2>
      <div className="grid md:grid-cols-3 gap-6">
        {TIERS.map((t) => {
          const isCurrent = status === "active" && tier === t.key;
          return (
            <div
              key={t.key}
              className={`rounded p-6 flex flex-col ${
                isCurrent
                  ? "border-2 border-accent bg-background ring-1 ring-accent/10"
                  : t.highlighted && status === "none"
                  ? "border-2 border-accent bg-background ring-1 ring-accent/10"
                  : "border border-border bg-background"
              }`}
            >
              {isCurrent && (
                <span className="text-xs font-medium text-accent mb-3">Current Plan</span>
              )}
              {!isCurrent && t.highlighted && status === "none" && (
                <span className="text-xs font-medium text-accent mb-3">Recommended</span>
              )}
              <h3 className="text-sm font-medium text-text-primary">{t.name}</h3>
              <div className="mt-3 mb-5">
                <span className="text-3xl font-serif text-text-primary tabular-nums">{t.price}</span>
                <span className="text-sm text-text-tertiary">{t.period}</span>
              </div>
              <ul className="space-y-2.5 mb-6 flex-1">
                {t.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-2 text-sm text-text-secondary">
                    <svg className="w-4 h-4 text-score-high shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20 6L9 17l-5-5" />
                    </svg>
                    {feature}
                  </li>
                ))}
              </ul>

              {isCurrent ? (
                <button
                  disabled
                  className="block text-center py-2.5 text-sm font-medium rounded border border-accent/30 text-accent/60 cursor-not-allowed"
                >
                  Current Plan
                </button>
              ) : status === "active" ? (
                <button
                  onClick={handlePortal}
                  className="block text-center py-2.5 text-sm font-medium rounded border border-border text-text-primary hover:border-text-tertiary transition"
                >
                  Switch Plan
                </button>
              ) : (
                <button
                  onClick={() => handleCheckout(t.key)}
                  disabled={!!checkoutLoading}
                  className={`block text-center py-2.5 text-sm font-medium rounded transition ${
                    t.highlighted
                      ? "bg-accent text-white hover:bg-accent-hover disabled:opacity-50"
                      : "border border-border text-text-primary hover:border-text-tertiary disabled:opacity-50"
                  }`}
                >
                  {checkoutLoading === t.key ? "Redirecting..." : "Subscribe"}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/billing/page.tsx frontend/middleware.ts
git commit -m "feat: add billing page with tier cards, status display, and Stripe checkout"
```

---

### Task 8: Landing Page — Dynamic Pricing CTAs

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Convert landing page to client component with dynamic CTAs**

Replace the entire contents of `frontend/app/page.tsx` with the following. Key changes: add `"use client"`, import `useSession` and `api`, add `handleCheckout`/`handlePortal` handlers, and make pricing CTA buttons dynamic based on auth + subscription state.

```tsx
"use client";

import Link from "next/link";
import { useSession } from "next-auth/react";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { BillingStatus } from "@/lib/types";

const TIERS = [
  {
    key: "starter",
    name: "Starter",
    price: "$19.99",
    period: "/mo",
    annual: "$240/yr",
    features: [
      "10 startup analyses / month",
      "15 reports generated / month",
      "Unlimited company search & profiles",
      "VC Quant Agent access",
    ],
    highlighted: false,
  },
  {
    key: "professional",
    name: "Professional",
    price: "$200",
    period: "/mo",
    annual: "$2,400/yr",
    features: [
      "50 startup analyses / month",
      "Unlimited reports",
      "Unlimited company search & profiles",
      "VC Quant Agent access",
      "Priority processing",
    ],
    highlighted: true,
  },
  {
    key: "unlimited",
    name: "Unlimited",
    price: "$500",
    period: "/mo",
    annual: "$6,000/yr",
    features: [
      "Unlimited everything",
      "VC Quant Agent access",
      "Priority processing",
      "API access",
    ],
    highlighted: false,
  },
];

const DATA_SOURCES = [
  {
    title: "Buy-Side Transaction Data",
    description:
      "1,000+ closed VC transactions with pricing, terms, and outcomes from actual buy-side deals.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6" />
      </svg>
    ),
  },
  {
    title: "VC Secondaries Market",
    description:
      "Real secondary market pricing and liquidity data on venture-backed companies — the layer most platforms ignore.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3v18h18" />
        <path d="M7 16l4-8 4 5 5-9" />
      </svg>
    ),
  },
  {
    title: "Crunchbase + PitchBook",
    description:
      "Funding rounds, investors, team data, and company profiles aggregated and cross-referenced.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <ellipse cx="12" cy="5" rx="9" ry="3" />
        <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5" />
        <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3" />
      </svg>
    ),
  },
  {
    title: "AI Agent Network",
    description:
      "An army of specialized agents that continuously evaluate companies across 8 dimensions — market, team, traction, technology, competition, financials, and more.",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="4" width="16" height="16" rx="2" />
        <path d="M9 9h6M9 13h6M9 17h4" />
      </svg>
    ),
  },
];

const TOOLS = [
  {
    number: "01",
    title: "Company Search & Discovery",
    description:
      "Browse 2,800+ venture-backed companies with structured profiles — founders, funding history, investors, tech stack, competitors. Filter by stage, industry, state, AI score. Every profile backed by multi-source data.",
    cta: "Explore companies",
    href: "/startups",
  },
  {
    number: "02",
    title: "Startup Analysis",
    description:
      "Upload a pitch deck and documents. Eight AI agents independently evaluate the company across market, team, traction, technology, competition, GTM, financials, and problem/solution fit. Get a scored report with fundraising projections — your first analysis is free.",
    cta: "Try it free",
    href: "/analyze",
  },
  {
    number: "03",
    title: "VC Quant Agent",
    description:
      "Ask questions across our entire dataset. Draft investment memos. Run quantitative comparisons. Generate reports grounded in real transaction data, not vibes. The analyst you'd hire for $150K — available on demand.",
    cta: "Try it",
    href: "/insights",
  },
];

export default function LandingPage() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);

  const loadBilling = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.getBillingStatus(token);
      setBilling(data);
    } catch {
      // silent
    }
  }, [token]);

  useEffect(() => {
    loadBilling();
  }, [loadBilling]);

  const handleCheckout = async (tierKey: string) => {
    if (!token) return;
    setCheckoutLoading(tierKey);
    try {
      const { url } = await api.createCheckoutSession(token, tierKey);
      window.location.href = url;
    } catch (err: any) {
      alert(err.message || "Failed to start checkout");
      setCheckoutLoading(null);
    }
  };

  const handlePortal = async () => {
    if (!token) return;
    try {
      const { url } = await api.createPortalSession(token);
      window.location.href = url;
    } catch (err: any) {
      alert(err.message || "Failed to open billing portal");
    }
  };

  const subStatus = billing?.subscription_status || "none";
  const subTier = billing?.subscription_tier;

  return (
    <div className="-mx-6 lg:-mx-8 -mt-12">
      {/* Hero */}
      <section className="px-6 lg:px-8 pt-28 pb-20 text-center">
        <h1 className="font-serif text-5xl md:text-6xl lg:text-7xl text-text-primary max-w-4xl mx-auto leading-[1.1] tracking-tight">
          Institutional-grade deal intelligence.
          <br />
          <span className="text-accent">Angel investor price.</span>
        </h1>
        <p className="text-text-secondary text-lg md:text-xl mt-8 max-w-2xl mx-auto leading-relaxed">
          Deep Thesis aggregates data from 1,000+ buy-side VC transactions,
          secondaries markets, Crunchbase, PitchBook, and an army of AI agents
          — so you can make quantitative investment decisions without a $20K/yr
          data subscription.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mt-10">
          <Link
            href="/analyze"
            className="px-8 py-3.5 bg-accent text-white text-sm font-medium rounded hover:bg-accent-hover transition"
          >
            Analyze a Startup — Free
          </Link>
          <a
            href="#pricing"
            className="px-8 py-3.5 border border-border text-text-secondary text-sm font-medium rounded hover:border-text-tertiary hover:text-text-primary transition"
          >
            See Pricing
          </a>
        </div>

        {/* Stat bar */}
        <div className="mt-16 flex flex-col sm:flex-row items-center justify-center gap-6 sm:gap-12 py-5 border-y border-border">
          {[
            { value: "1,000+", label: "transactions tracked" },
            { value: "2,800+", label: "companies profiled" },
            { value: "8", label: "AI agents per analysis" },
          ].map((stat) => (
            <div key={stat.label} className="text-center">
              <span className="text-2xl font-serif text-text-primary tabular-nums">
                {stat.value}
              </span>
              <p className="text-xs text-text-tertiary mt-1">{stat.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* The Problem */}
      <section className="px-6 lg:px-8 py-20 border-t border-border">
        <div className="max-w-5xl mx-auto">
          <h2 className="font-serif text-3xl md:text-4xl text-text-primary text-center mb-14">
            The math doesn&apos;t work.
          </h2>
          <div className="grid md:grid-cols-2 gap-12 md:gap-16">
            <div>
              <div className="space-y-4">
                {[
                  { label: "PitchBook", value: "~$20,000/yr" },
                  { label: "Crunchbase Pro", value: "~$5,000/yr" },
                  { label: "Your average check size", value: "$25K–$50K" },
                ].map((row) => (
                  <div key={row.label} className="flex items-center justify-between py-3 border-b border-border">
                    <span className="text-sm text-text-secondary">{row.label}</span>
                    <span className="text-sm font-medium text-text-primary tabular-nums">{row.value}</span>
                  </div>
                ))}
              </div>
              <p className="text-sm text-text-tertiary mt-6 italic">
                You shouldn&apos;t need to spend more on data than you deploy in a deal.
              </p>
            </div>
            <div className="flex items-center">
              <p className="text-lg text-text-secondary leading-relaxed">
                Deep Thesis was built for investors who write their own checks — angels, scouts, solo GPs, and emerging managers who need{" "}
                <span className="text-text-primary font-medium">real data</span>, not a Bloomberg terminal budget.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Data Sources */}
      <section className="px-6 lg:px-8 py-20 border-t border-border bg-surface">
        <div className="max-w-5xl mx-auto">
          <h2 className="font-serif text-3xl md:text-4xl text-text-primary text-center mb-14">
            Data you can&apos;t Google.
          </h2>
          <div className="grid md:grid-cols-2 gap-6">
            {DATA_SOURCES.map((source) => (
              <div key={source.title} className="rounded border border-border bg-background p-6 hover:border-text-tertiary transition">
                <div className="w-10 h-10 rounded bg-accent/10 flex items-center justify-center mb-4 text-accent">
                  {source.icon}
                </div>
                <h3 className="text-sm font-medium text-text-primary mb-2">{source.title}</h3>
                <p className="text-sm text-text-secondary leading-relaxed">{source.description}</p>
              </div>
            ))}
          </div>
          <p className="text-sm text-text-tertiary text-center mt-8">
            All of this feeds into every company profile, every analysis, and every report you generate.
          </p>
        </div>
      </section>

      {/* Three Core Tools */}
      <section className="px-6 lg:px-8 py-20 border-t border-border">
        <div className="max-w-4xl mx-auto">
          <h2 className="font-serif text-3xl md:text-4xl text-text-primary text-center mb-14">
            Search. Analyze. Reason.
          </h2>
          <div className="space-y-12">
            {TOOLS.map((tool) => (
              <div key={tool.number} className="flex gap-6 md:gap-8">
                <div className="shrink-0">
                  <span className="font-serif text-3xl text-accent/30">{tool.number}</span>
                </div>
                <div>
                  <h3 className="text-lg font-medium text-text-primary mb-2">{tool.title}</h3>
                  <p className="text-sm text-text-secondary leading-relaxed mb-3">{tool.description}</p>
                  <Link href={tool.href} className="text-sm text-accent hover:text-accent-hover transition">
                    {tool.cta} &rarr;
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="px-6 lg:px-8 py-20 border-t border-border bg-surface scroll-mt-16">
        <div className="max-w-5xl mx-auto">
          <h2 className="font-serif text-3xl md:text-4xl text-text-primary text-center mb-14">
            A fraction of what you&apos;d pay anywhere else.
          </h2>
          <div className="grid md:grid-cols-3 gap-6">
            {TIERS.map((tier) => {
              const isCurrent = subStatus === "active" && subTier === tier.key;
              return (
                <div
                  key={tier.name}
                  className={`rounded p-6 flex flex-col ${
                    isCurrent
                      ? "border-2 border-accent bg-background ring-1 ring-accent/10"
                      : tier.highlighted
                      ? "border-2 border-accent bg-background ring-1 ring-accent/10"
                      : "border border-border bg-background"
                  }`}
                >
                  {isCurrent && (
                    <span className="text-xs font-medium text-accent mb-3">Current Plan</span>
                  )}
                  {!isCurrent && tier.highlighted && (
                    <span className="text-xs font-medium text-accent mb-3">Recommended</span>
                  )}
                  <h3 className="text-sm font-medium text-text-primary">{tier.name}</h3>
                  <div className="mt-3 mb-5">
                    <span className="text-3xl font-serif text-text-primary tabular-nums">{tier.price}</span>
                    <span className="text-sm text-text-tertiary">{tier.period}</span>
                  </div>
                  <ul className="space-y-2.5 mb-6 flex-1">
                    {tier.features.map((feature) => (
                      <li key={feature} className="flex items-start gap-2 text-sm text-text-secondary">
                        <svg className="w-4 h-4 text-score-high shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M20 6L9 17l-5-5" />
                        </svg>
                        {feature}
                      </li>
                    ))}
                  </ul>

                  {/* Dynamic CTA */}
                  {isCurrent ? (
                    <button
                      disabled
                      className="block text-center py-2.5 text-sm font-medium rounded border border-accent/30 text-accent/60 cursor-not-allowed"
                    >
                      Current Plan
                    </button>
                  ) : session && subStatus === "active" ? (
                    <button
                      onClick={handlePortal}
                      className="block text-center py-2.5 text-sm font-medium rounded border border-border text-text-primary hover:border-text-tertiary transition"
                    >
                      Switch Plan
                    </button>
                  ) : session ? (
                    <button
                      onClick={() => handleCheckout(tier.key)}
                      disabled={!!checkoutLoading}
                      className={`block text-center py-2.5 text-sm font-medium rounded transition ${
                        tier.highlighted
                          ? "bg-accent text-white hover:bg-accent-hover disabled:opacity-50"
                          : "border border-border text-text-primary hover:border-text-tertiary disabled:opacity-50"
                      }`}
                    >
                      {checkoutLoading === tier.key ? "Redirecting..." : "Subscribe"}
                    </button>
                  ) : (
                    <Link
                      href="/auth/signup"
                      className={`block text-center py-2.5 text-sm font-medium rounded transition ${
                        tier.highlighted
                          ? "bg-accent text-white hover:bg-accent-hover"
                          : "border border-border text-text-primary hover:border-text-tertiary"
                      }`}
                    >
                      Get Started &rarr;
                    </Link>
                  )}
                </div>
              );
            })}
          </div>

          {/* Comparison line */}
          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4 sm:gap-8 text-sm">
            <span className="text-text-tertiary line-through">PitchBook: $20,000/yr</span>
            <span className="text-text-tertiary line-through">Crunchbase Pro: $5,000/yr</span>
            <span className="text-text-primary font-medium">Deep Thesis Starter: $240/yr</span>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="px-6 lg:px-8 py-24 border-t border-border text-center">
        <h2 className="font-serif text-3xl md:text-4xl text-text-primary mb-4">
          Stop overpaying for deal intelligence.
        </h2>
        <p className="text-text-secondary text-lg mb-10 max-w-md mx-auto">
          Your first startup analysis is free. No credit card required.
        </p>
        <Link
          href="/analyze"
          className="inline-block px-8 py-3.5 bg-accent text-white text-sm font-medium rounded hover:bg-accent-hover transition"
        >
          Analyze a Startup — Free
        </Link>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat: make landing page pricing CTAs dynamic based on auth and subscription state"
```

---

## Self-Review

**Spec coverage check:**
- Payment flow (checkout → redirect → webhook → activate) → Task 3 (billing.py) + Task 7 (billing page success polling)
- Subscription management flow (portal) → Task 3 (portal endpoint) + Task 7 (Manage Subscription button)
- User model additions → Task 2
- Backend config → Task 1
- Migration → Task 2
- Billing endpoints (checkout, portal, status, webhook) → Task 3
- Docker compose env vars → Task 4
- Frontend types + API client → Task 5
- Navigation dropdown → Task 6
- Billing page (all 5 states) → Task 7
- Landing page dynamic CTAs → Task 8
- Dependencies → Task 1
- Middleware update → Task 7

**Placeholder scan:** No TBDs, TODOs, or vague instructions found. All steps have complete code.

**Type consistency:**
- `BillingStatus` type in Task 5 matches the response shape in Task 3's `/api/billing/status` endpoint
- `SubscriptionTier` enum values (`starter`, `professional`, `unlimited`) consistent across model (Task 2), API (Task 3), frontend types (Task 5), tier cards (Tasks 7 & 8)
- `SubscriptionStatus` enum values (`none`, `active`, `cancelled`, `past_due`) consistent everywhere
- `TIER_PRICE_MAP` keys match the tier enum values
- API methods in Task 5 match the endpoints in Task 3
