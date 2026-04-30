import logging
import secrets
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.db.session import async_session, get_db
from app.models.pitch_session import PitchSession, PitchSessionStatus
from app.models.user import User
from app.models.zoom_connection import ZoomConnection
from app.services import zoom_client

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory store for temporary OAuth codes (short-lived, maps temp_code -> token_data)
# In production with multiple workers, use Redis. For single-container deploy this is fine.
_pending_links: dict[str, dict] = {}

ZOOM_OAUTH_AUTHORIZE_URL = "https://zoom.us/oauth/authorize"


# -- OAuth Callback --


@router.get("/api/zoom/oauth/callback")
async def zoom_oauth_callback(code: str | None = None, error: str | None = None):
    """Zoom redirects here after user authorizes the app."""
    if error or not code:
        return RedirectResponse(
            url=f"{settings.frontend_url}/profile?zoom_error=auth_denied",
            status_code=302,
        )

    redirect_uri = f"{settings.frontend_url.rstrip('/')}/api/zoom/oauth/callback"
    try:
        token_data = await zoom_client.exchange_code_for_tokens(code, redirect_uri)
    except Exception as e:
        logger.error("Zoom OAuth token exchange failed: %s (redirect_uri=%s, client_id=%s)", e, redirect_uri, settings.zoom_client_id)
        if hasattr(e, 'response'):
            logger.error("Zoom response body: %s", e.response.text)
        return RedirectResponse(
            url=f"{settings.frontend_url}/profile?zoom_error=token_exchange_failed",
            status_code=302,
        )

    # Get Zoom user info
    try:
        zoom_user = await zoom_client.get_zoom_user(token_data["access_token"])
    except Exception as e:
        logger.error("Failed to get Zoom user info: %s", e)
        return RedirectResponse(
            url=f"{settings.frontend_url}/profile?zoom_error=user_info_failed",
            status_code=302,
        )

    # Store tokens temporarily with a random code
    temp_code = secrets.token_urlsafe(32)
    _pending_links[temp_code] = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_in": token_data.get("expires_in", 3600),
        "zoom_account_id": zoom_user.get("account_id", ""),
        "zoom_email": zoom_user.get("email", ""),
        "created_at": datetime.now(timezone.utc),
    }

    return RedirectResponse(
        url=f"{settings.frontend_url}/zoom/connect?code={temp_code}",
        status_code=302,
    )


# -- Link Account --


class LinkRequest(BaseModel):
    temp_code: str


@router.post("/api/zoom/link")
async def link_zoom_account(
    body: LinkRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Link a Zoom account to the authenticated DeepThesis user."""
    pending = _pending_links.pop(body.temp_code, None)
    if not pending:
        raise HTTPException(status_code=400, detail="Invalid or expired link code.")

    # Check if code is too old (10 minutes)
    age = datetime.now(timezone.utc) - pending["created_at"]
    if age.total_seconds() > 600:
        raise HTTPException(status_code=400, detail="Link code expired. Please reconnect Zoom.")

    # Check if user already has a Zoom connection
    existing = await db.execute(
        select(ZoomConnection).where(ZoomConnection.user_id == user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="You already have a Zoom account connected. Disconnect it first.")

    # Check if this Zoom account is already linked to another user
    existing_zoom = await db.execute(
        select(ZoomConnection).where(ZoomConnection.zoom_account_id == pending["zoom_account_id"])
    )
    if existing_zoom.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This Zoom account is already linked to another DeepThesis user.")

    now = datetime.now(timezone.utc)
    connection = ZoomConnection(
        user_id=user.id,
        zoom_account_id=pending["zoom_account_id"],
        zoom_email=pending["zoom_email"],
        access_token=pending["access_token"],
        refresh_token=pending["refresh_token"],
        token_expires_at=now + timedelta(seconds=pending["expires_in"]),
    )
    db.add(connection)
    await db.commit()

    return {"ok": True, "zoom_email": pending["zoom_email"]}


# -- Connection Status --


@router.get("/api/zoom/connection")
async def get_zoom_connection(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's Zoom connection status."""
    result = await db.execute(
        select(ZoomConnection).where(ZoomConnection.user_id == user.id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        return {"connected": False}

    return {
        "connected": True,
        "zoom_email": conn.zoom_email,
        "zoom_account_id": conn.zoom_account_id,
        "connected_at": conn.created_at.isoformat() if conn.created_at else None,
    }


# -- Disconnect --


@router.delete("/api/zoom/connection")
async def disconnect_zoom(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disconnect the user's Zoom account."""
    result = await db.execute(
        select(ZoomConnection).where(ZoomConnection.user_id == user.id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="No Zoom connection found.")

    await db.delete(conn)
    await db.commit()

    return {"ok": True}


# -- Import Recording --


@router.post("/api/zoom/import/{session_id}")
async def import_zoom_recording(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import a Zoom recording that is in zoom_available status."""
    result = await db.execute(
        select(PitchSession).where(
            PitchSession.id == session_id,
            PitchSession.user_id == user.id,
        )
    )
    ps = result.scalar_one_or_none()
    if not ps:
        raise HTTPException(status_code=404, detail="Session not found")
    if ps.status != PitchSessionStatus.zoom_available:
        raise HTTPException(status_code=400, detail="Recording is not available for import")

    ps.status = PitchSessionStatus.downloading
    await db.commit()

    return {"ok": True, "id": str(ps.id)}


# -- Webhook --


@router.post("/api/zoom/webhook")
async def zoom_webhook(request: Request):
    """Handle Zoom webhook events."""
    body = await request.body()
    payload = await request.json()

    event = payload.get("event", "")

    # Handle URL validation challenge
    if event == "endpoint.url_validation":
        plain_token = payload.get("payload", {}).get("plainToken", "")
        hashed = zoom_client.compute_url_validation_response(plain_token)
        return {"plainToken": plain_token, "encryptedToken": hashed}

    # Validate webhook signature for all other events
    signature = request.headers.get("x-zm-signature", "")
    timestamp = request.headers.get("x-zm-request-timestamp", "")
    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing webhook signature")

    if not zoom_client.validate_webhook_signature(body, signature, timestamp):
        logger.warning("Invalid Zoom webhook signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if event == "recording.completed":
        await _handle_recording_completed(payload)

    return {"status": "ok"}


async def _handle_recording_completed(payload: dict) -> None:
    """Process a recording.completed webhook event."""
    obj = payload.get("payload", {}).get("object", {})
    account_id = obj.get("account_id") or payload.get("payload", {}).get("account_id", "")
    meeting_uuid = obj.get("uuid", "")
    meeting_topic = obj.get("topic", "Zoom Recording")
    recording_files = obj.get("recording_files", [])

    if not account_id:
        logger.warning("recording.completed webhook missing account_id")
        return

    # Find the linked DeepThesis user
    async with async_session() as db:
        result = await db.execute(
            select(ZoomConnection).where(ZoomConnection.zoom_account_id == account_id)
        )
        conn = result.scalar_one_or_none()
        if not conn:
            logger.info("No linked user for Zoom account %s, skipping", account_id)
            return

        # Check for duplicate
        dup = await db.execute(
            select(PitchSession).where(PitchSession.zoom_meeting_id == meeting_uuid)
        )
        if dup.scalar_one_or_none():
            logger.info("Duplicate recording for meeting %s, skipping", meeting_uuid)
            return

        # Select best recording file
        best_file = zoom_client.select_best_recording_file(recording_files)
        if not best_file:
            logger.warning("No completed recording files for meeting %s", meeting_uuid)
            return

        download_url = best_file.get("download_url", "")
        if not download_url:
            logger.warning("No download_url in recording file for meeting %s", meeting_uuid)
            return

        # Create PitchSession -- analysis phase rows are created later
        # when the user labels speakers (standard flow)
        ps = PitchSession(
            user_id=conn.user_id,
            title=meeting_topic[:500],
            status=PitchSessionStatus.zoom_available,
            source="zoom",
            zoom_meeting_id=meeting_uuid,
            video_url=download_url,
        )
        db.add(ps)
        await db.commit()
        logger.info("Created PitchSession %s from Zoom recording (meeting %s)", ps.id, meeting_uuid)
