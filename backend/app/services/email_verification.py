import hashlib
import hmac as hmac_module
import logging
import uuid
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy import select

from app.config import settings
from app.db.session import async_session
from app.models.investor import Investor
from app.models.investor_ranking import InvestorRanking
from app.models.marketing import EmailVerificationJob
from app.models.investor import BatchJobStatus

logger = logging.getLogger(__name__)

HUNTER_API_URL = "https://api.hunter.io/v2/email-verifier"
NEVERBOUNCE_API_URL = "https://api.neverbounce.com/v4/single/check"


async def verify_with_hunter(
    email: str, first_name: str, last_name: str, company: str
) -> dict:
    """Call Hunter.io Email Verifier API.

    Returns {"status": str, "suggested_email": str|None}.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            HUNTER_API_URL,
            params={
                "email": email,
                "api_key": settings.hunter_api_key,
            },
            timeout=30.0,
        )
    data = resp.json().get("data", {})
    returned_email = data.get("email", "").lower().strip()
    original_email = email.lower().strip()

    return {
        "status": data.get("status", "unknown"),
        "suggested_email": returned_email if returned_email != original_email else None,
    }


async def verify_with_neverbounce(email: str) -> dict:
    """Call NeverBounce Single Verification API.

    Returns {"result": "valid"|"invalid"|"disposable"|"catchall"|"unknown"}.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            NEVERBOUNCE_API_URL,
            params={
                "key": settings.neverbounce_api_key,
                "email": email,
            },
            timeout=30.0,
        )
    data = resp.json()
    return {"result": data.get("result", "unknown")}


def generate_unsubscribe_url(investor_id: str, frontend_url: str) -> str:
    """Generate an HMAC-signed unsubscribe URL for an investor."""
    token = hmac_module.new(
        settings.jwt_secret.encode(), investor_id.encode(), hashlib.sha256
    ).hexdigest()
    return f"{frontend_url}/unsubscribe/{investor_id}?token={token}"


def verify_unsubscribe_token(investor_id: str, token: str) -> bool:
    """Verify an HMAC unsubscribe token."""
    expected = hmac_module.new(
        settings.jwt_secret.encode(), investor_id.encode(), hashlib.sha256
    ).hexdigest()
    return hmac_module.compare_digest(token, expected)


async def run_verification_batch(job_id: str) -> None:
    """Verify emails for all scored investors via Hunter.io + NeverBounce."""
    db_factory = async_session

    # 1. Mark job as running
    async with db_factory() as db:
        job = await db.get(EmailVerificationJob, uuid.UUID(job_id))
        if not job:
            logger.error(f"Verification job {job_id} not found")
            return
        job.status = BatchJobStatus.running.value
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    # 2. Load all scored investors with non-null emails
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    async with db_factory() as db:
        result = await db.execute(
            select(Investor)
            .join(InvestorRanking, InvestorRanking.investor_id == Investor.id)
            .where(Investor.email.isnot(None))
            .where(Investor.email_status != "bounced")
            .order_by(Investor.firm_name.asc(), Investor.partner_name.asc())
        )
        all_investors = result.scalars().all()
        recipients = []
        skip_count = 0
        for inv in all_investors:
            if (
                inv.email_status in ("valid", "corrected")
                and inv.email_verified_at
                and inv.email_verified_at > thirty_days_ago
            ):
                skip_count += 1
                continue
            recipients.append({
                "id": inv.id,
                "firm_name": inv.firm_name,
                "partner_name": inv.partner_name,
                "email": inv.email,
            })

    # 3. Update job totals
    async with db_factory() as db:
        job = await db.get(EmailVerificationJob, uuid.UUID(job_id))
        job.total_recipients = len(recipients) + skip_count
        job.skipped_count = skip_count
        await db.commit()

    # 4. Check API keys
    if not settings.hunter_api_key or not settings.neverbounce_api_key:
        logger.error("Hunter or NeverBounce API key not configured")
        async with db_factory() as db:
            job = await db.get(EmailVerificationJob, uuid.UUID(job_id))
            job.status = BatchJobStatus.failed.value
            job.error = "Hunter or NeverBounce API key is not configured"
            await db.commit()
        return

    # 5. Verify each investor
    for idx, recipient in enumerate(recipients):
        async with db_factory() as db:
            job = await db.get(EmailVerificationJob, uuid.UUID(job_id))
            job.current_investor_name = (
                f"{recipient['firm_name']} ({recipient['partner_name']})"
            )
            await db.commit()

        email = recipient["email"]
        name_parts = recipient["partner_name"].strip().split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""
        was_corrected = False

        try:
            hunter_result = await verify_with_hunter(
                email, first_name, last_name, recipient["firm_name"]
            )

            if hunter_result["suggested_email"]:
                email = hunter_result["suggested_email"]
                was_corrected = True
                logger.info(
                    f"Hunter corrected {recipient['email']} -> {email} "
                    f"({recipient['firm_name']})"
                )

            nb_result = await verify_with_neverbounce(email)
            nb_status = nb_result["result"]

            async with db_factory() as db:
                investor = await db.get(Investor, recipient["id"])

                if nb_status in ("invalid", "disposable"):
                    investor.email_status = "bounced"
                    investor.email_verified_at = datetime.now(timezone.utc)
                    await db.commit()

                    async with db_factory() as db2:
                        job = await db2.get(EmailVerificationJob, uuid.UUID(job_id))
                        job.bounced_count += 1
                        await db2.commit()

                    logger.info(
                        f"Bounced: {email} ({recipient['firm_name']}) - {nb_status}"
                    )
                else:
                    if was_corrected:
                        investor.email = email
                        investor.email_status = "corrected"
                    else:
                        investor.email_status = "valid"
                    investor.email_verified_at = datetime.now(timezone.utc)
                    await db.commit()

                    async with db_factory() as db2:
                        job = await db2.get(EmailVerificationJob, uuid.UUID(job_id))
                        if was_corrected:
                            job.corrected_count += 1
                        job.verified_count += 1
                        await db2.commit()

                    if nb_status == "unknown":
                        logger.warning(
                            f"Unknown deliverability for {email} "
                            f"({recipient['firm_name']}) - proceeding anyway"
                        )

        except Exception as e:
            logger.error(
                f"Verification failed for {email} "
                f"({recipient['firm_name']}): {e}"
            )
            async with db_factory() as db:
                job = await db.get(EmailVerificationJob, uuid.UUID(job_id))
                job.skipped_count += 1
                errors = job.error or ""
                job.error = f"{errors}\n{recipient['firm_name']}: {e}".strip()
                await db.commit()

        logger.info(f"Verified {idx + 1}/{len(recipients)}: {email}")

    # 6. Mark job as completed
    async with db_factory() as db:
        job = await db.get(EmailVerificationJob, uuid.UUID(job_id))
        job.status = BatchJobStatus.completed.value
        job.current_investor_name = None
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()

    logger.info(f"Verification batch {job_id} complete")
