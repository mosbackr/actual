import logging
import uuid
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.models.user import SubscriptionStatus, SubscriptionTier, User
from app.services import email_service

logger = logging.getLogger(__name__)

router = APIRouter()

TIER_PRICE_MAP = {
    "starter": lambda: settings.stripe_price_starter,
    "professional": lambda: settings.stripe_price_professional,
    "unlimited": lambda: settings.stripe_price_unlimited,
}


def _price_id_to_tier(price_id: str) -> str | None:
    for tier, get_pid in TIER_PRICE_MAP.items():
        if get_pid() == price_id:
            return tier
    return None


def _get_stripe():
    if not settings.stripe_secret_key:
        raise HTTPException(500, "Stripe is not configured")
    stripe.api_key = settings.stripe_secret_key
    return stripe


async def _ensure_stripe_customer(user: User, db: AsyncSession) -> str:
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


class CheckoutBody(BaseModel):
    tier: str


@router.post("/api/billing/checkout")
async def create_checkout_session(
    body: CheckoutBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.tier not in TIER_PRICE_MAP:
        raise HTTPException(400, f"Invalid tier: {body.tier}. Must be one of: starter, professional, unlimited")

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


@router.post("/api/billing/portal")
async def create_portal_session(
    user: User = Depends(get_current_user),
):
    if not user.stripe_customer_id:
        raise HTTPException(400, "No billing account found. Subscribe to a plan first.")

    s = _get_stripe()

    session = s.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{settings.frontend_url}/billing",
    )

    return {"url": session.url}


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
    except (stripe.error.SignatureVerificationError, stripe.SignatureVerificationError, ValueError):
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
    customer_id = session_data.get("customer")
    subscription_id = session_data.get("subscription")
    metadata = session_data.get("metadata", {})
    tier = metadata.get("tier")
    user_id = metadata.get("user_id")

    if not customer_id:
        logger.warning("checkout.session.completed missing customer")
        return

    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()

    if not user and user_id:
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
    email_service.send_subscription_confirmed(
        user_email=user.email,
        user_name=user.name,
        tier_name=tier or "subscription",
    )
    logger.info("Subscription activated for user %s: tier=%s", user.id, tier)


async def _handle_subscription_updated(sub_data: dict, db: AsyncSession):
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

    period_end = sub_data.get("current_period_end")
    if period_end:
        user.subscription_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)

    items = sub_data.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id")
        if price_id:
            new_tier = _price_id_to_tier(price_id)
            if new_tier:
                user.subscription_tier = SubscriptionTier(new_tier)

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
    email_service.send_subscription_cancelled(
        user_email=user.email,
        user_name=user.name,
    )
    logger.info("Subscription deleted for user %s", user.id)


async def _handle_payment_failed(invoice_data: dict, db: AsyncSession):
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
    email_service.send_payment_failed(
        user_email=user.email,
        user_name=user.name,
    )
    logger.info("Payment failed for user %s — marked past_due", user.id)
