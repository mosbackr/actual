# Zoom Marketplace App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Zoom Marketplace app that auto-imports cloud recordings into DeepThesis Pitch Intelligence via OAuth + webhooks.

**Architecture:** Zoom OAuth flow stores tokens in a `zoom_connections` table linked to DeepThesis users via email/password login. Zoom sends `recording.completed` webhooks which create PitchSessions with `source="zoom"`. The pitch worker downloads recordings via the Zoom API instead of yt-dlp. Frontend adds a connect page, profile section, and Zoom badges.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, httpx (Zoom API calls), Next.js (React), Tailwind CSS

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/app/config.py` | Add `zoom_client_id`, `zoom_client_secret`, `zoom_webhook_secret` |
| `backend/app/models/zoom_connection.py` | ZoomConnection SQLAlchemy model |
| `backend/app/models/pitch_session.py` | Add `source` and `zoom_meeting_id` columns |
| `backend/alembic/versions/h9i0j1k2l3m4_add_zoom_connections.py` | Migration: create table + add columns |
| `backend/app/services/zoom_client.py` | Token refresh, Zoom API calls, recording download |
| `backend/app/api/zoom.py` | OAuth callback, webhook, link/unlink endpoints |
| `backend/app/main.py` | Register zoom router |
| `backend/app/services/pitch_worker.py` | Handle `source="zoom"` in download step |
| `frontend/lib/types.ts` | Add `source` field to PitchSessionSummary |
| `frontend/lib/api.ts` | Add Zoom API methods |
| `frontend/app/zoom/connect/page.tsx` | Post-OAuth account linking page |
| `frontend/app/profile/page.tsx` | Add Connected Apps section |
| `frontend/app/pitch-intelligence/page.tsx` | Show Zoom badge on sessions |

---

### Task 1: Config Settings

**Files:**
- Modify: `backend/app/config.py:19-42`

- [ ] **Step 1: Add Zoom settings to config**

In `backend/app/config.py`, add three new settings after the `deepgram_api_key` line (line 19). Insert these lines after `deepgram_api_key: str = ""`:

```python
    # Zoom Marketplace
    zoom_client_id: str = ""
    zoom_client_secret: str = ""
    zoom_webhook_secret: str = ""
```

The full file becomes:

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
    deepgram_api_key: str = ""

    # Zoom Marketplace
    zoom_client_id: str = ""
    zoom_client_secret: str = ""
    zoom_webhook_secret: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""
    stripe_price_professional: str = ""
    stripe_price_unlimited: str = ""
    frontend_url: str = "https://www.deepthesis.org"
    promo_code_unlimited: str = "DEEPTHESIS2026"

    # Email (Resend)
    resend_api_key: str = ""
    email_from: str = "gaius@deepthesis.org"
    marketing_email_from: str = "updates@deepthesis.co"

    # Email verification
    hunter_api_key: str = ""
    neverbounce_api_key: str = ""

    # Compliance
    company_address: str = "3965 Lewis Link, New Albany, OH 43054"

    model_config = {"env_prefix": "ACUTAL_"}


settings = Settings()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/config.py
git commit -m "feat(zoom): add Zoom Marketplace config settings"
```

---

### Task 2: ZoomConnection Model & PitchSession Columns

**Files:**
- Create: `backend/app/models/zoom_connection.py`
- Modify: `backend/app/models/pitch_session.py:38-60`

- [ ] **Step 1: Create ZoomConnection model**

Create `backend/app/models/zoom_connection.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class ZoomConnection(Base):
    __tablename__ = "zoom_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    zoom_account_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    zoom_email: Mapped[str | None] = mapped_column(String(500), nullable=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship()
```

- [ ] **Step 2: Add source and zoom_meeting_id to PitchSession**

In `backend/app/models/pitch_session.py`, add two columns after `video_url` (line 51). The new lines go after `video_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)`:

```python
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    zoom_meeting_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

The imports stay the same. The full column block from `id` through `error` becomes:

```python
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    startup_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("startups.id"), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[PitchSessionStatus] = mapped_column(
        Enum(PitchSessionStatus, name="pitchsessionstatus"),
        nullable=False,
        default=PitchSessionStatus.uploading,
    )
    file_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    zoom_meeting_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcript_raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    transcript_labeled: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    benchmark_percentiles: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    investor_faq: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/zoom_connection.py backend/app/models/pitch_session.py
git commit -m "feat(zoom): add ZoomConnection model and PitchSession source/zoom_meeting_id columns"
```

---

### Task 3: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/h9i0j1k2l3m4_add_zoom_connections.py`

- [ ] **Step 1: Create migration file**

Create `backend/alembic/versions/h9i0j1k2l3m4_add_zoom_connections.py`:

```python
"""add zoom_connections table and pitch_session zoom columns

Revision ID: h9i0j1k2l3m4
Revises: g8h9i0j1k2l3
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "h9i0j1k2l3m4"
down_revision = "g8h9i0j1k2l3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "zoom_connections",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("zoom_account_id", sa.String(255), unique=True, nullable=False),
        sa.Column("zoom_email", sa.String(500), nullable=True),
        sa.Column("access_token", sa.Text, nullable=False),
        sa.Column("refresh_token", sa.Text, nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.add_column("pitch_sessions", sa.Column("source", sa.String(50), nullable=True))
    op.add_column("pitch_sessions", sa.Column("zoom_meeting_id", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("pitch_sessions", "zoom_meeting_id")
    op.drop_column("pitch_sessions", "source")
    op.drop_table("zoom_connections")
```

- [ ] **Step 2: Commit**

```bash
git add backend/alembic/versions/h9i0j1k2l3m4_add_zoom_connections.py
git commit -m "feat(zoom): add migration for zoom_connections table and pitch_session columns"
```

---

### Task 4: Zoom Client Service

**Files:**
- Create: `backend/app/services/zoom_client.py`

- [ ] **Step 1: Create zoom_client.py**

Create `backend/app/services/zoom_client.py`:

```python
import hashlib
import hmac
import logging
import os
import shutil
import tempfile
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/zoom_client.py
git commit -m "feat(zoom): add zoom_client service with OAuth, token refresh, and recording download"
```

---

### Task 5: Zoom API Endpoints

**Files:**
- Create: `backend/app/api/zoom.py`
- Modify: `backend/app/main.py:43-77` (imports) and `backend/app/main.py:104-137` (router includes)

- [ ] **Step 1: Create zoom.py API router**

Create `backend/app/api/zoom.py`:

```python
import hashlib
import hmac
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


# ── OAuth Callback ────────────────────────────────────────────────────


@router.get("/api/zoom/oauth/callback")
async def zoom_oauth_callback(code: str | None = None, error: str | None = None):
    """Zoom redirects here after user authorizes the app."""
    if error or not code:
        return RedirectResponse(
            url=f"{settings.frontend_url}/profile?zoom_error=auth_denied",
            status_code=302,
        )

    redirect_uri = f"{settings.frontend_url.rstrip('/')}/api/zoom/oauth/callback"
    # The actual backend URL for the redirect_uri registered with Zoom
    # Since nginx proxies /api/* to the backend, we use the frontend URL
    try:
        token_data = await zoom_client.exchange_code_for_tokens(code, redirect_uri)
    except Exception as e:
        logger.error("Zoom OAuth token exchange failed: %s", e)
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


# ── Link Account ──────────────────────────────────────────────────────


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


# ── Connection Status ─────────────────────────────────────────────────


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


# ── Disconnect ────────────────────────────────────────────────────────


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


# ── Webhook ───────────────────────────────────────────────────────────


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

        # Create PitchSession — analysis phase rows are created later
        # when the user labels speakers (standard flow)
        ps = PitchSession(
            user_id=conn.user_id,
            title=meeting_topic[:500],
            status=PitchSessionStatus.downloading,
            source="zoom",
            zoom_meeting_id=meeting_uuid,
            video_url=download_url,
        )
        db.add(ps)
        await db.commit()
        logger.info("Created PitchSession %s from Zoom recording (meeting %s)", ps.id, meeting_uuid)
```

- [ ] **Step 2: Register zoom router in main.py**

In `backend/app/main.py`, add the import after the existing router imports (after line 76):

```python
from app.api.zoom import router as zoom_router
```

Add the router include after the existing includes (after line 137):

```python
app.include_router(zoom_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/zoom.py backend/app/main.py
git commit -m "feat(zoom): add Zoom API endpoints and register router"
```

---

### Task 6: Pitch Worker — Zoom Recording Download

**Files:**
- Modify: `backend/app/services/pitch_worker.py:191-239`

- [ ] **Step 1: Update pitch worker to handle Zoom source**

In `backend/app/services/pitch_worker.py`, modify the download section of `run_pitch_worker()`. The worker already polls for `downloading` sessions and calls `download_video()`. We need to add a branch: if `source == "zoom"`, use the zoom client to download instead of yt-dlp.

Add a new import at the top of the file (after existing imports, around line 26):

```python
from app.services.zoom_client import download_recording as zoom_download_recording, refresh_access_token
from app.models.zoom_connection import ZoomConnection
```

Replace the downloading block in `run_pitch_worker()` (lines 198-208). The current code is:

```python
            # Check for sessions needing video download
            async with async_session() as db:
                result = await db.execute(
                    select(PitchSession)
                    .where(PitchSession.status == PitchSessionStatus.downloading)
                    .order_by(PitchSession.created_at.asc())
                    .limit(1)
                )
                job = result.scalar_one_or_none()
                if job:
                    logger.info("[pitch-%s] Picking up video download job", job.id)
                    await download_video(job.id)
```

Replace with:

```python
            # Check for sessions needing video download
            async with async_session() as db:
                result = await db.execute(
                    select(PitchSession)
                    .where(PitchSession.status == PitchSessionStatus.downloading)
                    .order_by(PitchSession.created_at.asc())
                    .limit(1)
                )
                job = result.scalar_one_or_none()
                if job:
                    logger.info("[pitch-%s] Picking up video download job (source=%s)", job.id, job.source)
                    if job.source == "zoom":
                        await _download_zoom_recording(job.id)
                    else:
                        await download_video(job.id)
```

Then add the `_download_zoom_recording` function before `run_pitch_worker()` (after `_run_analysis_pipeline`):

```python
async def _download_zoom_recording(session_id: uuid.UUID) -> None:
    """Download a Zoom recording via the Zoom API and upload to S3."""
    logger.info("[pitch-%s] Starting Zoom recording download", session_id)

    try:
        async with async_session() as db:
            ps = (await db.execute(
                select(PitchSession).where(PitchSession.id == session_id)
            )).scalar_one()

            download_url = ps.video_url
            if not download_url:
                raise RuntimeError("No download URL for Zoom recording")

            # Find the Zoom connection for this user
            conn = (await db.execute(
                select(ZoomConnection).where(ZoomConnection.user_id == ps.user_id)
            )).scalar_one_or_none()

            if not conn:
                raise RuntimeError("Zoom connection not found for user")

            # Download the recording
            file_bytes = await zoom_download_recording(conn, db, download_url)

            # Upload to S3
            from app.services import s3
            s3_key = f"pitch-intelligence/{session_id}/audio.m4a"
            s3.upload_file(file_bytes, s3_key)
            logger.info("[pitch-%s] Uploaded Zoom recording to S3: %s (%d bytes)", session_id, s3_key, len(file_bytes))

        # Update session
        async with async_session() as db:
            ps = (await db.execute(
                select(PitchSession).where(PitchSession.id == session_id)
            )).scalar_one()
            ps.file_url = s3_key
            ps.status = PitchSessionStatus.transcribing
            await db.commit()

        logger.info("[pitch-%s] Zoom recording download complete, transitioning to transcribing", session_id)

    except Exception as e:
        logger.error("[pitch-%s] Zoom recording download failed: %s", session_id, e, exc_info=True)
        async with async_session() as db:
            ps = (await db.execute(
                select(PitchSession).where(PitchSession.id == session_id)
            )).scalar_one()
            ps.status = PitchSessionStatus.failed
            ps.error = f"Zoom recording download failed: {e}"
            await db.commit()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/pitch_worker.py
git commit -m "feat(zoom): handle Zoom recording downloads in pitch worker"
```

---

### Task 7: Frontend Types & API Methods

**Files:**
- Modify: `frontend/lib/types.ts:358-372`
- Modify: `frontend/lib/api.ts:416-505`

- [ ] **Step 1: Add source field to PitchSessionSummary**

In `frontend/lib/types.ts`, add `source` to the `PitchSessionSummary` interface. Add it after the `status` field (after line 363):

```typescript
  source: string | null;
```

The updated interface becomes:

```typescript
export interface PitchSessionSummary {
  id: string;
  startup_id: string | null;
  title: string | null;
  status: "downloading" | "uploading" | "transcribing" | "labeling" | "analyzing" | "complete" | "failed";
  source: string | null;
  file_duration_seconds: number | null;
  scores: Record<string, number> | null;
  benchmark_percentiles: Record<string, number> | null;
  has_labeled_transcript: boolean;
  speaker_count: number;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
}
```

- [ ] **Step 2: Add Zoom API methods to api.ts**

In `frontend/lib/api.ts`, add a new section after the Pitch Intelligence section (after line 504, before the Feedback section). Add these methods:

```typescript
  // ── Zoom ────────────────────────────────────────────────────────────

  async getZoomConnection(token: string) {
    return apiFetch<{ connected: boolean; zoom_email?: string; zoom_account_id?: string; connected_at?: string }>(
      "/api/zoom/connection",
      { headers: authHeaders(token) }
    );
  },

  async linkZoom(token: string, tempCode: string) {
    return apiFetch<{ ok: boolean; zoom_email: string }>(
      "/api/zoom/link",
      {
        method: "POST",
        headers: authHeaders(token),
        body: JSON.stringify({ temp_code: tempCode }),
      }
    );
  },

  async disconnectZoom(token: string) {
    return apiFetch<{ ok: boolean }>(
      "/api/zoom/connection",
      { method: "DELETE", headers: authHeaders(token) }
    );
  },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat(zoom): add frontend types and API methods for Zoom integration"
```

---

### Task 8: Zoom Connect Page (Frontend)

**Files:**
- Create: `frontend/app/zoom/connect/page.tsx`

- [ ] **Step 1: Create the Zoom connect page**

Create `frontend/app/zoom/connect/page.tsx`:

```tsx
"use client";

import { useSession, signIn } from "next-auth/react";
import { useSearchParams, useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function ZoomConnectPage() {
  return (
    <Suspense fallback={<div className="p-8 text-text-secondary">Loading...</div>}>
      <ZoomConnectContent />
    </Suspense>
  );
}

function ZoomConnectContent() {
  const { data: session, status: authStatus } = useSession();
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = (session as any)?.backendToken;
  const tempCode = searchParams.get("code");

  const [linking, setLinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [zoomEmail, setZoomEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!tempCode) {
      setError("Missing authorization code. Please try connecting Zoom again from your profile.");
      return;
    }

    if (authStatus === "loading") return;

    if (!token) {
      // Not logged in — redirect to sign in, then back here
      signIn(undefined, { callbackUrl: `/zoom/connect?code=${tempCode}` });
      return;
    }

    // Auto-link once we have both the token and temp code
    if (token && tempCode && !linking && !success && !error) {
      setLinking(true);
      api
        .linkZoom(token, tempCode)
        .then((result) => {
          setSuccess(true);
          setZoomEmail(result.zoom_email);
        })
        .catch((err) => {
          setError(err.message || "Failed to link Zoom account.");
        })
        .finally(() => setLinking(false));
    }
  }, [token, tempCode, authStatus, linking, success, error]);

  return (
    <div className="mx-auto max-w-md px-6 py-20">
      <div className="rounded-lg border border-border bg-surface p-8 text-center">
        <h1 className="text-xl font-serif text-text-primary mb-4">Connect Zoom</h1>

        {linking && (
          <div>
            <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent mb-4" />
            <p className="text-text-secondary">Linking your Zoom account...</p>
          </div>
        )}

        {success && (
          <div>
            <div className="mx-auto h-12 w-12 rounded-full bg-green-100 flex items-center justify-center mb-4">
              <svg className="h-6 w-6 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-text-primary font-medium mb-1">Zoom connected successfully!</p>
            {zoomEmail && (
              <p className="text-sm text-text-secondary mb-4">{zoomEmail}</p>
            )}
            <p className="text-sm text-text-tertiary mb-6">
              Your Zoom cloud recordings will now automatically appear in Pitch Intelligence.
            </p>
            <button
              onClick={() => router.push("/profile")}
              className="rounded-lg bg-accent px-5 py-2 text-sm font-medium text-white hover:bg-accent/90 transition"
            >
              Go to Profile
            </button>
          </div>
        )}

        {error && (
          <div>
            <div className="mx-auto h-12 w-12 rounded-full bg-red-100 flex items-center justify-center mb-4">
              <svg className="h-6 w-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <p className="text-text-primary font-medium mb-1">Connection failed</p>
            <p className="text-sm text-red-600 mb-4">{error}</p>
            <button
              onClick={() => router.push("/profile")}
              className="rounded-lg border border-border px-5 py-2 text-sm text-text-secondary hover:text-text-primary hover:border-text-tertiary transition"
            >
              Back to Profile
            </button>
          </div>
        )}

        {!linking && !success && !error && authStatus === "loading" && (
          <p className="text-text-secondary">Checking authentication...</p>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/zoom/connect/page.tsx
git commit -m "feat(zoom): add Zoom connect page for post-OAuth account linking"
```

---

### Task 9: Profile Page — Connected Apps Section

**Files:**
- Modify: `frontend/app/profile/page.tsx:55-303`

- [ ] **Step 1: Add Zoom connection state and effects**

In `frontend/app/profile/page.tsx`, add new state variables after the existing state declarations (after line 66, after `const fileInputRef = useRef<HTMLInputElement>(null);`):

```typescript
  const [zoomConnected, setZoomConnected] = useState(false);
  const [zoomEmail, setZoomEmail] = useState<string | null>(null);
  const [disconnectingZoom, setDisconnectingZoom] = useState(false);
```

In the existing `useEffect` (around line 70-81), add a call to fetch Zoom connection status. After the `api.getMe(backendToken)` call, add:

```typescript
      api.getZoomConnection(backendToken).then((data) => {
        setZoomConnected(data.connected);
        setZoomEmail(data.zoom_email || null);
      }).catch(() => {});
```

The full useEffect becomes:

```typescript
  useEffect(() => {
    if (!session) return;
    if (backendToken) {
      api.getMyApplication(backendToken).then(setApplication).catch(() => {});
      api.getMe(backendToken).then((data) => {
        setName(data.name);
        setAvatarUrl(data.avatar_url || null);
        setEcosystemRole(data.ecosystem_role || "");
        setRegion(data.region || "");
      }).catch(() => {});
      api.getZoomConnection(backendToken).then((data) => {
        setZoomConnected(data.connected);
        setZoomEmail(data.zoom_email || null);
      }).catch(() => {});
    }
  }, [session, backendToken]);
```

- [ ] **Step 2: Add Zoom connect/disconnect handler**

Add this function after `handleFileChange` (after line 152):

```typescript
  async function handleDisconnectZoom() {
    if (!backendToken) return;
    setDisconnectingZoom(true);
    try {
      await api.disconnectZoom(backendToken);
      setZoomConnected(false);
      setZoomEmail(null);
    } catch {
      setMessage("Failed to disconnect Zoom");
    } finally {
      setDisconnectingZoom(false);
    }
  }

  const zoomConnectUrl = `https://zoom.us/oauth/authorize?response_type=code&client_id=${process.env.NEXT_PUBLIC_ZOOM_CLIENT_ID || ""}&redirect_uri=${encodeURIComponent((process.env.NEXT_PUBLIC_API_URL || "") + "/api/zoom/oauth/callback")}`;
```

- [ ] **Step 3: Add Connected Apps section to the JSX**

In the return JSX, add the Connected Apps section between the profile card (closing `</div>` around line 283) and the contributor application section (line 285). Insert this block:

```tsx
      {/* Connected Apps */}
      <div className="rounded border border-border bg-surface p-6 mb-8">
        <h3 className="font-medium text-text-primary mb-4">Connected Apps</h3>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-blue-500 flex items-center justify-center">
              <svg className="h-5 w-5 text-white" viewBox="0 0 24 24" fill="currentColor">
                <path d="M4.585 6.836a1.44 1.44 0 0 0-1.443 1.443v5.3a1.44 1.44 0 0 0 2.163 1.249l3.98-2.65v1.401a1.44 1.44 0 0 0 2.163 1.249l4.432-2.95a1.44 1.44 0 0 0 0-2.497l-4.432-2.95a1.44 1.44 0 0 0-2.163 1.249v1.401l-3.98-2.65a1.44 1.44 0 0 0-.72-.195z"/>
              </svg>
            </div>
            <div>
              <p className="text-sm font-medium text-text-primary">Zoom</p>
              {zoomConnected ? (
                <p className="text-xs text-text-secondary">{zoomEmail || "Connected"}</p>
              ) : (
                <p className="text-xs text-text-tertiary">Auto-import cloud recordings</p>
              )}
            </div>
          </div>
          {zoomConnected ? (
            <button
              onClick={handleDisconnectZoom}
              disabled={disconnectingZoom}
              className="rounded border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 transition disabled:opacity-50"
            >
              {disconnectingZoom ? "Disconnecting..." : "Disconnect"}
            </button>
          ) : (
            <a
              href={zoomConnectUrl}
              className="rounded bg-blue-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-600 transition"
            >
              Connect Zoom
            </a>
          )}
        </div>
      </div>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/app/profile/page.tsx
git commit -m "feat(zoom): add Connected Apps section with Zoom connect/disconnect to profile page"
```

---

### Task 10: Pitch Intelligence — Zoom Badge & Source in API Response

**Files:**
- Modify: `backend/app/api/pitch_intelligence.py:40-73`
- Modify: `frontend/app/pitch-intelligence/page.tsx:410-436`

- [ ] **Step 1: Add source to _session_to_dict in backend**

In `backend/app/api/pitch_intelligence.py`, add `source` to the `_session_to_dict` function. After the `"status"` line (line 46), add:

```python
        "source": session.source,
```

The updated dict construction (lines 41-53) becomes:

```python
def _session_to_dict(session: PitchSession, include_results: bool = False) -> dict:
    d = {
        "id": str(session.id),
        "user_id": str(session.user_id),
        "startup_id": str(session.startup_id) if session.startup_id else None,
        "title": session.title,
        "status": session.status.value if hasattr(session.status, "value") else session.status,
        "source": session.source,
        "file_duration_seconds": session.file_duration_seconds,
        "scores": session.scores,
        "benchmark_percentiles": session.benchmark_percentiles,
        "error": session.error,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }
```

- [ ] **Step 2: Add Zoom badge to frontend session list**

In `frontend/app/pitch-intelligence/page.tsx`, update the session list item to show a Zoom badge. Find the session title display (around line 419):

```tsx
                    <p className="font-medium text-text-primary">
                      {s.title || "Untitled Pitch"}
                    </p>
```

Replace with:

```tsx
                    <p className="font-medium text-text-primary">
                      {s.title || "Untitled Pitch"}
                      {s.source === "zoom" && (
                        <span className="ml-2 inline-flex items-center rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-medium text-blue-700">
                          Zoom
                        </span>
                      )}
                    </p>
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/pitch_intelligence.py frontend/app/pitch-intelligence/page.tsx
git commit -m "feat(zoom): add source to API response and Zoom badge in session list"
```

---

### Task 11: Add httpx Dependency

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add httpx to dependencies**

In `backend/pyproject.toml`, add `"httpx>=0.27.0"` to the `dependencies` list (alongside the existing dependencies like `"yt-dlp>=2024.0.0"`).

- [ ] **Step 2: Commit**

```bash
git add backend/pyproject.toml
git commit -m "feat(zoom): add httpx dependency for Zoom API calls"
```

---

### Task 12: Deploy

**Files:** None (deployment steps)

- [ ] **Step 1: Set environment variables in AWS**

Add these three environment variables to AWS Secrets Manager (or the `.env` file on EC2):

```
ACUTAL_ZOOM_CLIENT_ID=<from Zoom Marketplace developer portal>
ACUTAL_ZOOM_CLIENT_SECRET=<from Zoom Marketplace developer portal>
ACUTAL_ZOOM_WEBHOOK_SECRET=<from Zoom Marketplace developer portal>
```

Also add to the frontend environment:

```
NEXT_PUBLIC_ZOOM_CLIENT_ID=<same Zoom client ID>
```

- [ ] **Step 2: Rsync code to EC2**

```bash
rsync -avz --exclude node_modules --exclude .next --exclude __pycache__ --exclude .git \
  -e "ssh -i ~/.ssh/deepthesis-deploy.pem" \
  /Users/leemosbacker/acutal/ ec2-user@3.212.120.144:~/acutal/
```

- [ ] **Step 3: Run Alembic migration**

```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "cd ~/acutal && docker compose exec backend alembic upgrade head"
```

- [ ] **Step 4: Rebuild and restart backend**

```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "cd ~/acutal && docker compose up -d --build backend"
```

- [ ] **Step 5: Rebuild and restart frontend**

```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "cd ~/acutal && docker compose up -d --build frontend"
```

- [ ] **Step 6: Restart analysis worker**

The analysis worker runs as a standalone container. Restart it so it picks up the new Zoom download code:

```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "cd ~/acutal && docker stop analysis-worker 2>/dev/null; docker rm analysis-worker 2>/dev/null; docker run -d --name analysis-worker --network acutal_default -e ACUTAL_DATABASE_URL='postgresql+asyncpg://acutal:1Vj1hzYawacU1clnlVUWqzZt@db:5432/acutal' -e ACUTAL_ANTHROPIC_API_KEY=\$(grep ACUTAL_ANTHROPIC_API_KEY .env | cut -d= -f2) -e ACUTAL_PERPLEXITY_API_KEY=\$(grep ACUTAL_PERPLEXITY_API_KEY .env | cut -d= -f2) -e ACUTAL_AWS_ACCESS_KEY_ID=\$(grep ACUTAL_AWS_ACCESS_KEY_ID .env | cut -d= -f2) -e ACUTAL_AWS_SECRET_ACCESS_KEY=\$(grep ACUTAL_AWS_SECRET_ACCESS_KEY .env | cut -d= -f2) -e ACUTAL_DEEPGRAM_API_KEY=\$(grep ACUTAL_DEEPGRAM_API_KEY .env | cut -d= -f2) -e ACUTAL_ZOOM_CLIENT_ID=\$(grep ACUTAL_ZOOM_CLIENT_ID .env | cut -d= -f2) -e ACUTAL_ZOOM_CLIENT_SECRET=\$(grep ACUTAL_ZOOM_CLIENT_SECRET .env | cut -d= -f2) -e ACUTAL_ZOOM_WEBHOOK_SECRET=\$(grep ACUTAL_ZOOM_WEBHOOK_SECRET .env | cut -d= -f2) acutal-backend python -m app.services.analysis_worker"
```

- [ ] **Step 7: Configure Zoom Marketplace App**

On the Zoom Marketplace developer portal (marketplace.zoom.us):

1. Create a "General App"
2. Set OAuth redirect URL to: `https://deepthesis.org/api/zoom/oauth/callback`
3. Set webhook endpoint URL to: `https://deepthesis.org/api/zoom/webhook`
4. Subscribe to event: `recording.completed`
5. Request scopes: `recording:read`, `user:read`
6. Copy Client ID, Client Secret, and Webhook Secret Token into the environment variables from Step 1

- [ ] **Step 8: Verify deployment**

1. Visit `https://www.deepthesis.org/profile` — should see "Connected Apps" section with "Connect Zoom" button
2. Click "Connect Zoom" — should redirect to Zoom authorization page
3. After authorizing, should redirect to `/zoom/connect?code=...` and auto-link
4. Profile should show "Zoom Connected" with email and "Disconnect" button
5. Record a short Zoom meeting — after it processes, a new pitch session should appear in Pitch Intelligence with a "Zoom" badge

---

## Notes

- **Zoom App Registration:** The app must be registered on marketplace.zoom.us before any of the OAuth/webhook functionality works. The Client ID, Client Secret, and Webhook Secret come from there.
- **Webhook URL Validation:** When you set the webhook endpoint URL in the Zoom portal, Zoom sends a `endpoint.url_validation` challenge. The backend handles this automatically.
- **In-Memory Pending Links:** The `_pending_links` dict in `zoom.py` stores temporary OAuth codes in memory. This works for single-container deployment. If you scale to multiple backend workers, replace with Redis or a database table.
- **hmac.new vs hmac.new:** The `zoom_client.py` uses `hmac.new()` — note this is the `hmac` module's `new()` constructor, not `hmac.HMAC()`. Both work identically.
- **Analysis Phase Rows:** The webhook handler creates `PitchAnalysisResult` rows upfront (same pattern as the speaker labeling endpoint) so the phases are ready when the worker finishes downloading and transcribing.
