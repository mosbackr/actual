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


def send_dataroom_request(
    founder_email: str,
    founder_name: str | None,
    investor_name: str,
    company_name: str | None,
    personal_message: str | None,
    share_token: str,
) -> None:
    try:
        _send(
            to=founder_email,
            subject=f"{investor_name} has requested your dataroom",
            template_name="dataroom_request.html",
            context={
                "founder_name": founder_name,
                "investor_name": investor_name,
                "company_name": company_name,
                "personal_message": personal_message,
                "cta_url": f"{settings.frontend_url}/dataroom/{share_token}",
            },
        )
    except Exception:
        logger.warning("Failed to send dataroom_request email to %s", founder_email, exc_info=True)


def send_dataroom_submitted(
    investor_email: str,
    investor_name: str,
    founder_name: str,
    company_name: str | None,
    dataroom_id: str,
) -> None:
    try:
        _send(
            to=investor_email,
            subject=f"Dataroom received from {founder_name}",
            template_name="dataroom_submitted.html",
            context={
                "investor_name": investor_name,
                "founder_name": founder_name,
                "company_name": company_name or "their company",
                "cta_url": f"{settings.frontend_url}/datarooms/{dataroom_id}",
            },
        )
    except Exception:
        logger.warning("Failed to send dataroom_submitted email to %s", investor_email, exc_info=True)


def send_dataroom_complete(
    investor_email: str,
    investor_name: str,
    company_name: str | None,
    dataroom_id: str,
) -> None:
    try:
        _send(
            to=investor_email,
            subject="Dataroom analysis is ready",
            template_name="dataroom_complete.html",
            context={
                "investor_name": investor_name,
                "company_name": company_name or "the company",
                "cta_url": f"{settings.frontend_url}/datarooms/{dataroom_id}",
            },
        )
    except Exception:
        logger.warning("Failed to send dataroom_complete email to %s", investor_email, exc_info=True)
