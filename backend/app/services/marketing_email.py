import asyncio
import logging
import uuid
from datetime import datetime, timezone

import anthropic
import resend
from sqlalchemy import select

from app.config import settings
from app.db.session import async_session
from app.models.investor import BatchJobStatus, Investor
from app.models.investor_ranking import InvestorRanking
from app.models.marketing import MarketingEmailJob, MarketingEmailSent

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

BRAND_SYSTEM_PROMPT = """\
You are an expert email designer for Deep Thesis, a venture-capital analytics platform.

Generate a COMPLETE, self-contained HTML email using ONLY inline CSS and table-based layout.
The email must be max-width 600px, centered, and render correctly in all major email clients
(Gmail, Outlook, Apple Mail).

Brand guidelines:
- Accent color: #F28C28 (orange)
- Background color: #FAFAF8 (warm off-white)
- Text color: #1A1A1A (near-black)
- Border color: #E8E6E3 (light warm gray)
- Font stack: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif

Logo HTML (place at the top of the email):
<table role="presentation" width="100%"><tr><td align="center" style="padding:24px 0;">
  <span style="display:inline-block;width:36px;height:36px;border-radius:50%;background:#F28C28;color:#fff;font-weight:700;font-size:18px;line-height:36px;text-align:center;vertical-align:middle;">D</span>
  <span style="font-size:20px;font-weight:700;color:#1A1A1A;vertical-align:middle;margin-left:8px;">Deep Thesis</span>
</td></tr></table>

CTA button style (orange pill):
<table role="presentation" align="center" style="margin:24px auto;"><tr><td style="background:#F28C28;border-radius:9999px;padding:12px 32px;">
  <a href="{{cta_url}}" style="color:#fff;text-decoration:none;font-weight:600;font-size:16px;">View Your Score</a>
</td></tr></table>

REQUIRED FOOTER (must appear at the bottom of EVERY email):
<table role="presentation" width="100%" style="margin-top:32px;border-top:1px solid #E8E6E3;padding-top:16px;">
<tr><td align="center" style="font-size:12px;color:#999;line-height:1.5;">
  <p>You're receiving this because you were scored on the Deep Thesis platform.</p>
  <p>{{company_address}}</p>
  <p><a href="{{unsubscribe_url}}" style="color:#999;text-decoration:underline;">Unsubscribe</a></p>
</td></tr></table>

Constraints:
- Use ONLY inline CSS (no <style> blocks)
- Use table-based layout throughout
- Max-width 600px, centered with margin: 0 auto
- Include the placeholder {{score}} where the investor's overall score should appear
- Available dimension placeholders: {{deal_activity}}, {{sector_expertise}}, {{stage_expertise}}, {{follow_on_rate}}, {{network_quality}}, {{portfolio_performance}}, {{exit_track_record}} — use any of these to show individual scores
- Include the placeholder {{cta_url}} where the link to the score page should appear
- Include the REQUIRED FOOTER exactly as shown above — do not omit or modify it
- Output ONLY the raw HTML, no markdown fences or explanation
"""


async def generate_email_html(prompt: str) -> str:
    """Call Claude claude-sonnet-4-6 with the brand system prompt and the user's creative brief
    to generate a marketing email HTML template."""
    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=BRAND_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def render_for_recipient(
    html_template: str,
    investor_ranking: InvestorRanking,
    investor_id: uuid.UUID,
    frontend_url: str,
) -> str:
    """Replace {{score}}, {{cta_url}}, {{unsubscribe_url}}, and {{company_address}}
    placeholders with investor-specific values."""
    from app.services.email_verification import generate_unsubscribe_url

    score = str(round(investor_ranking.overall_score))
    cta_url = f"{frontend_url}/score/{investor_id}"
    unsubscribe_url = generate_unsubscribe_url(str(investor_id), frontend_url)

    # Decode HTML-encoded braces that Claude may generate
    html = html_template.replace("&#123;", "{").replace("&#125;", "}")
    html = html.replace("&lbrace;", "{").replace("&rbrace;", "}")

    html = html.replace("{{score}}", score)
    html = html.replace("{{cta_url}}", cta_url)
    html = html.replace("{{unsubscribe_url}}", unsubscribe_url)
    html = html.replace("{{company_address}}", settings.company_address)
    html = html.replace("{{deal_activity}}", str(round(investor_ranking.deal_activity)))
    html = html.replace("{{sector_expertise}}", str(round(investor_ranking.sector_expertise)))
    html = html.replace("{{stage_expertise}}", str(round(investor_ranking.stage_expertise)))
    html = html.replace("{{follow_on_rate}}", str(round(investor_ranking.follow_on_rate)))
    html = html.replace("{{network_quality}}", str(round(investor_ranking.network_quality)))
    html = html.replace("{{portfolio_performance}}", str(round(investor_ranking.portfolio_performance)))
    html = html.replace("{{exit_track_record}}", str(round(investor_ranking.exit_track_record)))
    return html


async def run_marketing_batch(job_id: str) -> None:
    """Send marketing emails to all scored investors.

    Follows the same separate-session-per-DB-operation pattern as
    investor_ranking.run_ranking_batch to avoid detached-instance errors.
    """
    db_factory = async_session

    # ── 1. Mark job as running ──────────────────────────────────────────
    async with db_factory() as db:
        job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
        if not job:
            logger.error(f"Marketing email job {job_id} not found")
            return
        job.status = BatchJobStatus.running.value
        job.started_at = datetime.now(timezone.utc)

        # Cache template fields BEFORE session closes
        html_template = job.html_template
        subject = job.subject
        from_address = job.from_address

        await db.commit()

    # ── 2. Load only verified investors with rankings ──────────────────
    async with db_factory() as db:
        result = await db.execute(
            select(Investor, InvestorRanking)
            .join(InvestorRanking, InvestorRanking.investor_id == Investor.id)
            .where(Investor.email.isnot(None))
            .where(Investor.email_status.in_(["valid", "corrected"]))
            .where(Investor.email_unsubscribed != True)
            .order_by(Investor.firm_name.asc(), Investor.partner_name.asc())
        )
        rows = result.all()
        recipients = [
            {
                "investor_id": inv.id,
                "firm_name": inv.firm_name,
                "partner_name": inv.partner_name,
                "email": inv.email,
                "overall_score": ranking.overall_score,
                "deal_activity": ranking.deal_activity,
                "sector_expertise": ranking.sector_expertise,
                "stage_expertise": ranking.stage_expertise,
                "follow_on_rate": ranking.follow_on_rate,
                "network_quality": ranking.network_quality,
                "portfolio_performance": ranking.portfolio_performance,
                "exit_track_record": ranking.exit_track_record,
            }
            for inv, ranking in rows
        ]

    # ── 3. Update total_recipients ──────────────────────────────────────
    async with db_factory() as db:
        job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
        job.total_recipients = len(recipients)
        await db.commit()

    # ── 4. Check Resend API key ─────────────────────────────────────────
    if not settings.resend_api_key:
        logger.error("Resend API key not configured — failing marketing batch job")
        async with db_factory() as db:
            job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
            job.status = BatchJobStatus.failed.value
            job.error = "Resend API key is not configured"
            await db.commit()
        return

    resend.api_key = settings.resend_api_key

    # ── 5. Loop through recipients ──────────────────────────────────────
    for idx, recipient in enumerate(recipients):
        # Check for pause
        async with db_factory() as db:
            job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
            if job.status == BatchJobStatus.paused.value:
                logger.info(f"Marketing batch {job_id} paused at recipient {idx}")
                return
            # Skip already processed
            if idx < job.sent_count + job.failed_count:
                continue

        # Update current investor info
        async with db_factory() as db:
            job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
            job.current_investor_id = recipient["investor_id"]
            job.current_investor_name = (
                f"{recipient['firm_name']} ({recipient['partner_name']})"
            )
            await db.commit()

        # Build a lightweight ranking-like object for render_for_recipient
        class _RankingProxy:
            def __init__(self, r: dict):
                self.overall_score = r["overall_score"]
                self.deal_activity = r.get("deal_activity", 0)
                self.sector_expertise = r.get("sector_expertise", 0)
                self.stage_expertise = r.get("stage_expertise", 0)
                self.follow_on_rate = r.get("follow_on_rate", 0)
                self.network_quality = r.get("network_quality", 0)
                self.portfolio_performance = r.get("portfolio_performance", 0)
                self.exit_track_record = r.get("exit_track_record", 0)

        ranking_proxy = _RankingProxy(recipient)
        personalized_html = render_for_recipient(
            html_template, ranking_proxy, recipient["investor_id"], settings.frontend_url
        )

        # Send email
        try:
            resend.Emails.send(
                {
                    "from": from_address,
                    "to": [recipient["email"]],
                    "subject": subject,
                    "html": personalized_html,
                }
            )
            async with db_factory() as db:
                job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
                job.sent_count += 1
                db.add(MarketingEmailSent(
                    job_id=uuid.UUID(job_id),
                    investor_id=recipient["investor_id"],
                    firm_name=recipient["firm_name"],
                    partner_name=recipient["partner_name"],
                    email=recipient["email"],
                    status="sent",
                ))
                await db.commit()

            logger.info(
                f"Sent {idx + 1}/{len(recipients)}: {recipient['email']} "
                f"({recipient['firm_name']})"
            )
        except Exception as e:
            logger.error(
                f"Failed sending to {recipient['email']} "
                f"({recipient['firm_name']}): {e}"
            )
            async with db_factory() as db:
                job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
                job.failed_count += 1
                errors = job.error or ""
                job.error = f"{errors}\n{recipient['firm_name']}: {e}".strip()
                db.add(MarketingEmailSent(
                    job_id=uuid.UUID(job_id),
                    investor_id=recipient["investor_id"],
                    firm_name=recipient["firm_name"],
                    partner_name=recipient["partner_name"],
                    email=recipient["email"],
                    status="failed",
                    error=str(e),
                ))
                await db.commit()

        # Rate limit: 2 emails per second
        if idx < len(recipients) - 1:
            await asyncio.sleep(0.5)

    # ── 6. Mark job as completed ────────────────────────────────────────
    async with db_factory() as db:
        job = await db.get(MarketingEmailJob, uuid.UUID(job_id))
        job.status = BatchJobStatus.completed.value
        job.current_investor_id = None
        job.current_investor_name = None
        job.completed_at = datetime.now(timezone.utc)
        await db.commit()

    logger.info(f"Marketing batch {job_id} complete")
