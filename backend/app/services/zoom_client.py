import hashlib
import hmac
import logging
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.zoom_connection import ZoomConnection

logger = logging.getLogger(__name__)

ZOOM_OAUTH_TOKEN_URL = "https://zoom.us/oauth/token"
ZOOM_API_BASE = "https://api.zoom.us/v2"


async def exchange_code_for_tokens(code: str, redirect_uri: str) -> dict:
    """Exchange OAuth authorization code for access + refresh tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            ZOOM_OAUTH_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            auth=(settings.zoom_client_id, settings.zoom_client_secret),
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(connection: ZoomConnection, db: AsyncSession) -> str:
    """Refresh the access token if expired. Returns a valid access token."""
    now = datetime.now(timezone.utc)
    if connection.token_expires_at > now + timedelta(minutes=5):
        return connection.access_token

    logger.info("Refreshing Zoom token for user %s", connection.user_id)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            ZOOM_OAUTH_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": connection.refresh_token,
            },
            auth=(settings.zoom_client_id, settings.zoom_client_secret),
        )
        resp.raise_for_status()
        data = resp.json()

    connection.access_token = data["access_token"]
    connection.refresh_token = data["refresh_token"]
    connection.token_expires_at = now + timedelta(seconds=data["expires_in"])
    await db.commit()

    return connection.access_token


async def get_zoom_user(access_token: str) -> dict:
    """Get the authenticated Zoom user's profile."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ZOOM_API_BASE}/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def download_recording(connection: ZoomConnection, db: AsyncSession, download_url: str) -> bytes:
    """Download a recording file from Zoom using authenticated access."""
    token = await refresh_access_token(connection, db)
    async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
        resp = await client.get(
            download_url,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.content


def select_best_recording_file(recording_files: list[dict]) -> dict | None:
    """Select the best recording file from a Zoom recording payload.

    Priority: audio_only > speaker_view MP4 > any MP4
    """
    audio_only = None
    speaker_view = None
    any_mp4 = None

    for rf in recording_files:
        file_type = rf.get("file_type", "").upper()
        recording_type = rf.get("recording_type", "")
        status = rf.get("status", "")

        if status != "completed":
            continue

        if recording_type == "audio_only":
            audio_only = rf
        elif file_type == "MP4":
            if recording_type in ("shared_screen_with_speaker_view", "speaker_view"):
                speaker_view = rf
            elif any_mp4 is None:
                any_mp4 = rf

    return audio_only or speaker_view or any_mp4


def validate_webhook_signature(request_body: bytes, signature: str, timestamp: str) -> bool:
    """Validate a Zoom webhook signature."""
    message = f"v0:{timestamp}:{request_body.decode('utf-8')}"
    expected = "v0=" + hmac.new(
        settings.zoom_webhook_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def compute_url_validation_response(plain_token: str) -> str:
    """Compute the hashed token for Zoom endpoint URL validation."""
    return hmac.new(
        settings.zoom_webhook_secret.encode("utf-8"),
        plain_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
