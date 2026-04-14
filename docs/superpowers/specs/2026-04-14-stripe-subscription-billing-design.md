# Stripe Subscription & Billing Design

## Goal

Connect Stripe to the existing subscription gating so users can actually pay. Add a billing page for subscription management and restructure navigation to include a user dropdown menu.

## Architecture

Three Stripe Products matching the existing pricing tiers. **Stripe Checkout (hosted)** for new subscriptions — user clicks CTA, backend creates a Checkout Session, user is redirected to Stripe, then back on success. **Stripe Customer Portal (hosted)** for managing existing subscriptions — cancel, change plan, update payment method, view invoices. A **webhook endpoint** receives Stripe events to keep the database `subscription_status` in sync.

### Payment Flow

1. User clicks pricing CTA on landing page or billing page
2. Frontend calls `POST /api/billing/checkout` with the desired `tier`
3. Backend creates/retrieves Stripe Customer, creates Checkout Session, returns `{url}`
4. Frontend redirects to Stripe Checkout
5. User completes payment on Stripe
6. Stripe redirects to `/billing?success=true&session_id=...`
7. Stripe fires `checkout.session.completed` webhook
8. Backend webhook handler sets user `subscription_status = active`, stores `stripe_customer_id`, `stripe_subscription_id`, `subscription_tier`, `subscription_period_end`
9. Frontend billing success page polls `GET /api/billing/status` until active, then shows confirmation

### Subscription Management Flow

1. User clicks "Manage Subscription" on billing page
2. Frontend calls `POST /api/billing/portal`
3. Backend creates Stripe Customer Portal session, returns `{url}`
4. Frontend redirects to Stripe Portal
5. User changes plan / cancels / updates payment on Stripe
6. Stripe fires webhooks (`customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`)
7. Backend webhook handler updates user record accordingly

## Pricing Tiers

| Tier | Monthly Price | Stripe Product |
|------|--------------|----------------|
| Starter | $19.99/mo | Created in Stripe Dashboard, Price ID stored in backend config |
| Professional | $200/mo | Created in Stripe Dashboard, Price ID stored in backend config |
| Unlimited | $500/mo | Created in Stripe Dashboard, Price ID stored in backend config |

Price IDs are configured as backend environment variables (not hardcoded). The landing page and billing page display tier info from a shared constant, but actual prices come from Stripe.

## Backend Changes

### User Model Additions

Add to `users` table:

| Column | Type | Notes |
|--------|------|-------|
| `stripe_customer_id` | `String(255)`, nullable, unique | Links user to Stripe Customer object |
| `stripe_subscription_id` | `String(255)`, nullable | Current active subscription |
| `subscription_tier` | `ENUM('starter', 'professional', 'unlimited')`, nullable | Which plan they're on |
| `subscription_period_end` | `DateTime(timezone=True)`, nullable | Current billing period end |

Add `past_due` to the existing `subscription_status` PostgreSQL ENUM (values: `none`, `active`, `cancelled`, `past_due`).

### New Endpoints

All under new router file `backend/app/api/billing.py`.

#### `POST /api/billing/checkout`

- **Auth:** Required (Bearer token)
- **Body:** `{ "tier": "starter" | "professional" | "unlimited" }`
- **Logic:**
  1. Look up Stripe Price ID from config for the given tier
  2. If user has no `stripe_customer_id`, create Stripe Customer with user's email and name, store ID
  3. Create Stripe Checkout Session:
     - `mode: "subscription"`
     - `customer: stripe_customer_id`
     - `line_items: [{price: price_id, quantity: 1}]`
     - `success_url: {FRONTEND_URL}/billing?success=true&session_id={CHECKOUT_SESSION_ID}`
     - `cancel_url: {FRONTEND_URL}/billing?cancelled=true`
     - `metadata: {user_id: str(user.id), tier: tier}`
  4. Return `{ "url": session.url }`
- **Errors:** 400 if already has active subscription at same tier, 400 if invalid tier

#### `POST /api/billing/portal`

- **Auth:** Required
- **Logic:**
  1. Requires user has `stripe_customer_id` (400 if not)
  2. Create Stripe Billing Portal Session:
     - `customer: stripe_customer_id`
     - `return_url: {FRONTEND_URL}/billing`
  3. Return `{ "url": session.url }`

#### `GET /api/billing/status`

- **Auth:** Required
- **Response:**
  ```json
  {
    "subscription_status": "active" | "none" | "cancelled" | "past_due",
    "subscription_tier": "starter" | "professional" | "unlimited" | null,
    "subscription_period_end": "2026-05-14T00:00:00Z" | null,
    "has_stripe_customer": true | false
  }
  ```

#### `POST /api/billing/webhook`

- **Auth:** None (verified by Stripe signature)
- **Headers:** Requires `Stripe-Signature` header
- **Logic:** Verify webhook signature using `STRIPE_WEBHOOK_SECRET`, then handle events:

| Event | Action |
|-------|--------|
| `checkout.session.completed` | Set `subscription_status = active`, store `stripe_subscription_id`, set `subscription_tier` from metadata, set `subscription_period_end` from subscription object |
| `customer.subscription.updated` | Update `subscription_tier` if plan changed, update `subscription_period_end`, if `cancel_at_period_end` is true set status to `cancelled` |
| `customer.subscription.deleted` | Set `subscription_status = none`, clear `stripe_subscription_id`, `subscription_tier`, `subscription_period_end` |
| `invoice.payment_failed` | Set `subscription_status = past_due` |

Webhook handler retrieves user by `stripe_customer_id` from the event's customer field.

### Backend Config

New settings in `app/config.py`:

```
STRIPE_SECRET_KEY: str
STRIPE_WEBHOOK_SECRET: str
STRIPE_PRICE_STARTER: str      # Stripe Price ID
STRIPE_PRICE_PROFESSIONAL: str  # Stripe Price ID
STRIPE_PRICE_UNLIMITED: str     # Stripe Price ID
FRONTEND_URL: str               # For Stripe redirect URLs
```

### Migration

Single Alembic migration:
1. Add `stripe_customer_id` (String 255, nullable, unique) to users
2. Add `stripe_subscription_id` (String 255, nullable) to users
3. Add `subscription_tier` ENUM type and column (nullable) to users
4. Add `subscription_period_end` (DateTime, nullable) to users
5. Add `past_due` to `subscriptionstatus` ENUM

### Dependencies

Add `stripe>=8.0.0` to `backend/pyproject.toml`.

## Frontend Changes

### Navigation Dropdown

Replace the current `AuthButton` component behavior. Currently: avatar + name links to `/profile`.

New behavior when logged in: clicking avatar opens a dropdown menu with three items:
- **Profile** → `/profile`
- **Billing** → `/billing`
- **Sign Out** → triggers signOut()

Dropdown closes on click outside or menu item selection. Use existing site styling (bg-surface, border-border, text-text-primary/secondary classes).

### New `/billing` Page

Route: `/billing` (add to protected paths in middleware).

**States:**

1. **No subscription:** Shows "You're on the Free plan" with feature limits listed (1 free analysis, 1 free conversation, 20 messages). Below that, shows the three tiers as cards with "Subscribe" buttons that trigger Stripe Checkout.

2. **Active subscription:** Shows current tier name, "Renews on {date}" text, "Manage Subscription" button (opens Stripe Portal), tier comparison showing their current plan highlighted.

3. **Cancelled:** Shows "Your {tier} plan is cancelled" with "Resubscribe" button and note about when access expires.

4. **Past due:** Shows warning that payment failed with "Update Payment Method" button (opens Stripe Portal).

5. **Success state** (`?success=true`): Shows "Welcome to {tier}!" confirmation, polls `/api/billing/status` until active.

### Landing Page Pricing CTAs

Update the three pricing tier buttons:

- **Not logged in:** "Get Started" → `/auth/signup`
- **Logged in, no subscription:** "Subscribe" → calls `POST /api/billing/checkout` with tier, redirects to Stripe
- **Logged in, active on this tier:** "Current Plan" (disabled/highlighted)
- **Logged in, active on different tier:** "Switch Plan" → opens Stripe Portal

### Frontend API Client Additions

Add to `frontend/lib/api.ts`:

```typescript
createCheckoutSession(token: string, tier: string): Promise<{ url: string }>
createPortalSession(token: string): Promise<{ url: string }>
getBillingStatus(token: string): Promise<BillingStatus>
```

### Frontend Types

Add to `frontend/lib/types.ts`:

```typescript
interface BillingStatus {
  subscription_status: "none" | "active" | "cancelled" | "past_due";
  subscription_tier: "starter" | "professional" | "unlimited" | null;
  subscription_period_end: string | null;
  has_stripe_customer: boolean;
}
```

## Environment Variables

New env vars for `docker-compose.prod.yml` backend service:

```yaml
STRIPE_SECRET_KEY: ${STRIPE_SECRET_KEY:-}
STRIPE_WEBHOOK_SECRET: ${STRIPE_WEBHOOK_SECRET:-}
STRIPE_PRICE_STARTER: ${STRIPE_PRICE_STARTER:-}
STRIPE_PRICE_PROFESSIONAL: ${STRIPE_PRICE_PROFESSIONAL:-}
STRIPE_PRICE_UNLIMITED: ${STRIPE_PRICE_UNLIMITED:-}
FRONTEND_URL: ${FRONTEND_URL:-https://deepthesis.org}
```

These values are set in the `.env` file on the EC2 server after creating the Stripe products in the Stripe Dashboard.

## What This Does NOT Include

- Annual billing toggle (monthly only for now)
- Free trial periods
- Coupon/promo code support
- Usage-based billing
- Multiple subscriptions per user
- Team/org billing
- Custom payment form (uses Stripe hosted pages)
- Email notifications for billing events (Stripe handles these)
