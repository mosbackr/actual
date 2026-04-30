# Pitch Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone module for uploading pitch recordings, transcribing with speaker diarization, fact-checking both founders and investors, analyzing conversation dynamics, scoring, and benchmarking across accumulated pitches.

**Architecture:** New backend models (`pitch_session`, `pitch_analysis_result`, `pitch_benchmark`) + Deepgram for transcription + a 5-phase sequential AI pipeline reusing the existing `analysis_worker` container + new frontend pages at `/pitch-intelligence`. Presigned S3 uploads for large files. Progressive results display matching the existing analysis page pattern.

**Tech Stack:** FastAPI, SQLAlchemy (async), Alembic, Deepgram Nova-2, Claude Sonnet/Opus via Anthropic SDK, Perplexity API, boto3 (S3 presigned URLs), Next.js 15, React, Tailwind CSS.

**Spec:** `docs/superpowers/specs/2026-04-19-pitch-intelligence-design.md`

**Important:** Do NOT deploy. Build only.

---

### Task 1: Backend Models

**Files:**
- Create: `backend/app/models/pitch_session.py`

- [ ] **Step 1: Create the pitch_session model file**

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.industry import Base


class PitchSessionStatus(str, enum.Enum):
    uploading = "uploading"
    transcribing = "transcribing"
    labeling = "labeling"
    analyzing = "analyzing"
    complete = "complete"
    failed = "failed"


class PitchAnalysisPhase(str, enum.Enum):
    claim_extraction = "claim_extraction"
    fact_check_founders = "fact_check_founders"
    fact_check_investors = "fact_check_investors"
    conversation_analysis = "conversation_analysis"
    scoring = "scoring"
    benchmark = "benchmark"


class PitchPhaseStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    failed = "failed"


class PitchSession(Base):
    __tablename__ = "pitch_sessions"

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
    file_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transcript_raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    transcript_labeled: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    benchmark_percentiles: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="pitch_sessions")
    results: Mapped[list["PitchAnalysisResult"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class PitchAnalysisResult(Base):
    __tablename__ = "pitch_analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pitch_sessions.id"), nullable=False)
    phase: Mapped[PitchAnalysisPhase] = mapped_column(
        Enum(PitchAnalysisPhase, name="pitchanalysisphase"), nullable=False,
    )
    status: Mapped[PitchPhaseStatus] = mapped_column(
        Enum(PitchPhaseStatus, name="pitchphasestatus"),
        nullable=False,
        default=PitchPhaseStatus.pending,
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    session: Mapped["PitchSession"] = relationship(back_populates="results")


class PitchBenchmark(Base):
    __tablename__ = "pitch_benchmarks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dimension: Mapped[str] = mapped_column(String(100), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mean_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    median_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    p25: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    p75: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    patterns: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: Register models in `__init__.py`**

Add to `backend/app/models/__init__.py`:

```python
from app.models.pitch_session import PitchSession, PitchAnalysisResult, PitchBenchmark
```

And add to `__all__`:

```python
"PitchSession",
"PitchAnalysisResult",
"PitchBenchmark",
```

- [ ] **Step 3: Add relationship on User model**

In `backend/app/models/user.py`, add the reverse relationship:

```python
pitch_sessions: Mapped[list["PitchSession"]] = relationship(back_populates="user")
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/pitch_session.py backend/app/models/__init__.py backend/app/models/user.py
git commit -m "feat(pitch-intelligence): add PitchSession, PitchAnalysisResult, PitchBenchmark models"
```

---

### Task 2: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/w2x3y4z5a6b7_add_pitch_intelligence_tables.py`

- [ ] **Step 1: Create migration file**

```python
"""Add pitch intelligence tables

Revision ID: w2x3y4z5a6b7
Revises: v1w2x3y4z5a6
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = "w2x3y4z5a6b7"
down_revision = "v1w2x3y4z5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types
    op.execute(
        "DO $$ BEGIN CREATE TYPE pitchsessionstatus AS ENUM "
        "('uploading', 'transcribing', 'labeling', 'analyzing', 'complete', 'failed'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE pitchanalysisphase AS ENUM "
        "('claim_extraction', 'fact_check_founders', 'fact_check_investors', "
        "'conversation_analysis', 'scoring', 'benchmark'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE pitchphasestatus AS ENUM "
        "('pending', 'running', 'complete', 'failed'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    pitchsessionstatus = sa.Enum(
        'uploading', 'transcribing', 'labeling', 'analyzing', 'complete', 'failed',
        name='pitchsessionstatus', create_type=False,
    )
    pitchanalysisphase = sa.Enum(
        'claim_extraction', 'fact_check_founders', 'fact_check_investors',
        'conversation_analysis', 'scoring', 'benchmark',
        name='pitchanalysisphase', create_type=False,
    )
    pitchphasestatus = sa.Enum(
        'pending', 'running', 'complete', 'failed',
        name='pitchphasestatus', create_type=False,
    )

    op.create_table(
        "pitch_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("startup_id", UUID(as_uuid=True), sa.ForeignKey("startups.id"), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("status", pitchsessionstatus, nullable=False, server_default="uploading"),
        sa.Column("file_url", sa.String(1000), nullable=True),
        sa.Column("file_duration_seconds", sa.Integer, nullable=True),
        sa.Column("transcript_raw", JSON, nullable=True),
        sa.Column("transcript_labeled", JSON, nullable=True),
        sa.Column("scores", JSON, nullable=True),
        sa.Column("benchmark_percentiles", JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "pitch_analysis_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("pitch_sessions.id"), nullable=False),
        sa.Column("phase", pitchanalysisphase, nullable=False),
        sa.Column("status", pitchphasestatus, nullable=False, server_default="pending"),
        sa.Column("result", JSON, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "pitch_benchmarks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dimension", sa.String(100), nullable=False),
        sa.Column("stage", sa.String(50), nullable=True),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("sample_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("mean_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("median_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("p25", sa.Float, nullable=False, server_default="0"),
        sa.Column("p75", sa.Float, nullable=False, server_default="0"),
        sa.Column("patterns", JSON, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("ix_pitch_sessions_user_id", "pitch_sessions", ["user_id"])
    op.create_index("ix_pitch_sessions_status", "pitch_sessions", ["status"])
    op.create_index("ix_pitch_analysis_results_session_id", "pitch_analysis_results", ["session_id"])
    op.create_index("ix_pitch_benchmarks_dimension_stage", "pitch_benchmarks", ["dimension", "stage", "industry"])


def downgrade() -> None:
    op.drop_table("pitch_analysis_results")
    op.drop_table("pitch_sessions")
    op.drop_table("pitch_benchmarks")
    op.execute("DROP TYPE IF EXISTS pitchphasestatus")
    op.execute("DROP TYPE IF EXISTS pitchanalysisphase")
    op.execute("DROP TYPE IF EXISTS pitchsessionstatus")
```

- [ ] **Step 2: Commit**

```bash
git add backend/alembic/versions/w2x3y4z5a6b7_add_pitch_intelligence_tables.py
git commit -m "feat(pitch-intelligence): add migration for pitch_sessions, pitch_analysis_results, pitch_benchmarks"
```

---

### Task 3: Config + S3 Presigned URL Support

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/s3.py`

- [ ] **Step 1: Add Deepgram API key to config**

In `backend/app/config.py`, add to the `Settings` class:

```python
deepgram_api_key: str = ""
```

- [ ] **Step 2: Add presigned URL generation to S3 service**

In `backend/app/services/s3.py`, add this function:

```python
def generate_presigned_upload_url(s3_key: str, content_type: str, expires_in: int = 3600) -> str:
    """Generate a presigned URL for direct client-side upload to S3."""
    client = _get_client()
    url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket_name,
            "Key": s3_key,
            "ContentType": content_type,
        },
        ExpiresIn=expires_in,
    )
    return url
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py backend/app/services/s3.py
git commit -m "feat(pitch-intelligence): add Deepgram config + S3 presigned upload URL"
```

---

### Task 4: Backend API Routes

**Files:**
- Create: `backend/app/api/pitch_intelligence.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create the API routes file**

```python
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.pitch_session import (
    PitchAnalysisPhase,
    PitchAnalysisResult,
    PitchBenchmark,
    PitchPhaseStatus,
    PitchSession,
    PitchSessionStatus,
)
from app.models.user import User
from app.services import s3

router = APIRouter()

ALLOWED_CONTENT_TYPES = {
    "audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/x-m4a",
    "video/mp4", "video/webm", "audio/webm",
}


def _require_subscription(user: User) -> None:
    sub_status = user.subscription_status
    if hasattr(sub_status, "value"):
        sub_status = sub_status.value
    if sub_status != "active":
        raise HTTPException(status_code=402, detail="Active subscription required for Pitch Intelligence.")


def _session_to_dict(session: PitchSession, include_results: bool = False) -> dict:
    d = {
        "id": str(session.id),
        "user_id": str(session.user_id),
        "startup_id": str(session.startup_id) if session.startup_id else None,
        "title": session.title,
        "status": session.status.value if hasattr(session.status, "value") else session.status,
        "file_duration_seconds": session.file_duration_seconds,
        "scores": session.scores,
        "benchmark_percentiles": session.benchmark_percentiles,
        "error": session.error,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }
    if include_results:
        d["results"] = [
            {
                "id": str(r.id),
                "phase": r.phase.value if hasattr(r.phase, "value") else r.phase,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "result": r.result,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in (session.results or [])
        ]
    if session.transcript_labeled:
        d["has_labeled_transcript"] = True
        d["speaker_count"] = len(session.transcript_labeled.get("speakers", []))
    else:
        d["has_labeled_transcript"] = False
        d["speaker_count"] = 0
    return d


# ── Upload ────────────────────────────────────────────────────────────


class UploadRequest(BaseModel):
    filename: str
    content_type: str
    title: str | None = None
    startup_id: str | None = None


@router.post("/api/pitch-intelligence/upload")
async def create_upload(
    body: UploadRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_subscription(user)

    if body.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {body.content_type}")

    startup_id = uuid.UUID(body.startup_id) if body.startup_id else None

    session = PitchSession(
        user_id=user.id,
        startup_id=startup_id,
        title=body.title,
        status=PitchSessionStatus.uploading,
    )
    db.add(session)
    await db.flush()

    s3_key = f"pitch-intelligence/{session.id}/{body.filename}"
    session.file_url = s3_key

    await db.commit()
    await db.refresh(session)

    presigned_url = s3.generate_presigned_upload_url(s3_key, body.content_type)

    return {
        "id": str(session.id),
        "upload_url": presigned_url,
        "s3_key": s3_key,
    }


# ── Upload Complete → Trigger Transcription ───────────────────────────


@router.post("/api/pitch-intelligence/{session_id}/upload-complete")
async def upload_complete(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_subscription(user)

    result = await db.execute(
        select(PitchSession).where(PitchSession.id == session_id, PitchSession.user_id == user.id)
    )
    ps = result.scalar_one_or_none()
    if ps is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if ps.status != PitchSessionStatus.uploading:
        raise HTTPException(status_code=400, detail="Session is not in uploading state")

    ps.status = PitchSessionStatus.transcribing
    await db.commit()

    # Trigger transcription in the analysis worker via status change.
    # The worker polls for sessions in 'transcribing' status.

    return {"id": str(ps.id), "status": "transcribing"}


# ── Speaker Labeling ──────────────────────────────────────────────────


class SpeakerLabel(BaseModel):
    speaker_id: str
    name: str
    role: str  # "founder", "investor", "other"


class SpeakerLabelRequest(BaseModel):
    speakers: list[SpeakerLabel]


@router.put("/api/pitch-intelligence/{session_id}/speakers")
async def label_speakers(
    session_id: uuid.UUID,
    body: SpeakerLabelRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_subscription(user)

    result = await db.execute(
        select(PitchSession).where(PitchSession.id == session_id, PitchSession.user_id == user.id)
    )
    ps = result.scalar_one_or_none()
    if ps is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if ps.status != PitchSessionStatus.labeling:
        raise HTTPException(status_code=400, detail="Session is not ready for speaker labeling")

    # Build labeled transcript by merging speaker labels into raw transcript
    raw = ps.transcript_raw or {}
    speaker_map = {s.speaker_id: {"name": s.name, "role": s.role} for s in body.speakers}

    labeled = {
        "speakers": [
            {"id": s.speaker_id, "name": s.name, "role": s.role}
            for s in body.speakers
        ],
        "segments": [],
    }

    for segment in raw.get("segments", []):
        speaker_key = str(segment.get("speaker", ""))
        speaker_info = speaker_map.get(speaker_key, {"name": f"Speaker {speaker_key}", "role": "other"})
        labeled["segments"].append({
            "speaker_id": speaker_key,
            "speaker_name": speaker_info["name"],
            "speaker_role": speaker_info["role"],
            "text": segment.get("text", ""),
            "start": segment.get("start", 0),
            "end": segment.get("end", 0),
        })

    ps.transcript_labeled = labeled
    ps.status = PitchSessionStatus.analyzing

    # Create analysis phase rows
    for phase in PitchAnalysisPhase:
        phase_result = PitchAnalysisResult(
            session_id=ps.id,
            phase=phase,
            status=PitchPhaseStatus.pending,
        )
        db.add(phase_result)

    await db.commit()

    return {"id": str(ps.id), "status": "analyzing"}


# ── Get Session ───────────────────────────────────────────────────────


@router.get("/api/pitch-intelligence/{session_id}")
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchSession)
        .where(PitchSession.id == session_id, PitchSession.user_id == user.id)
        .options(selectinload(PitchSession.results))
    )
    ps = result.scalar_one_or_none()
    if ps is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return _session_to_dict(ps, include_results=True)


# ── Status (lightweight polling) ──────────────────────────────────────


@router.get("/api/pitch-intelligence/{session_id}/status")
async def get_status(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchSession)
        .where(PitchSession.id == session_id, PitchSession.user_id == user.id)
        .options(selectinload(PitchSession.results))
    )
    ps = result.scalar_one_or_none()
    if ps is None:
        raise HTTPException(status_code=404, detail="Session not found")

    phases = []
    for r in (ps.results or []):
        phases.append({
            "phase": r.phase.value if hasattr(r.phase, "value") else r.phase,
            "status": r.status.value if hasattr(r.status, "value") else r.status,
        })

    return {
        "id": str(ps.id),
        "status": ps.status.value if hasattr(ps.status, "value") else ps.status,
        "phases": phases,
    }


# ── List Sessions ────────────────────────────────────────────────────


@router.get("/api/pitch-intelligence")
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchSession)
        .where(PitchSession.user_id == user.id)
        .order_by(PitchSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return {"items": [_session_to_dict(ps) for ps in sessions]}


# ── Delete Session ────────────────────────────────────────────────────


@router.delete("/api/pitch-intelligence/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchSession)
        .where(PitchSession.id == session_id, PitchSession.user_id == user.id)
    )
    ps = result.scalar_one_or_none()
    if ps is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Delete S3 file
    if ps.file_url:
        try:
            s3.delete_file(ps.file_url)
        except Exception:
            pass

    await db.delete(ps)
    await db.commit()

    return {"deleted": True}


# ── Transcript ────────────────────────────────────────────────────────


@router.get("/api/pitch-intelligence/{session_id}/transcript")
async def get_transcript(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchSession).where(PitchSession.id == session_id, PitchSession.user_id == user.id)
    )
    ps = result.scalar_one_or_none()
    if ps is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if ps.transcript_labeled:
        return ps.transcript_labeled
    elif ps.transcript_raw:
        return ps.transcript_raw
    else:
        raise HTTPException(status_code=404, detail="No transcript available yet")


# ── Benchmarks ────────────────────────────────────────────────────────


@router.get("/api/pitch-intelligence/benchmarks")
async def get_benchmarks(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PitchBenchmark).order_by(PitchBenchmark.dimension)
    )
    benchmarks = result.scalars().all()
    return {
        "items": [
            {
                "dimension": b.dimension,
                "stage": b.stage,
                "industry": b.industry,
                "sample_count": b.sample_count,
                "mean_score": b.mean_score,
                "median_score": b.median_score,
                "p25": b.p25,
                "p75": b.p75,
                "patterns": b.patterns,
            }
            for b in benchmarks
        ]
    }
```

- [ ] **Step 2: Register router in main.py**

In `backend/app/main.py`, add the import after the existing router imports:

```python
from app.api.pitch_intelligence import router as pitch_intelligence_router
```

And add the include after the existing `app.include_router` calls:

```python
app.include_router(pitch_intelligence_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/pitch_intelligence.py backend/app/main.py
git commit -m "feat(pitch-intelligence): add API routes — upload, speakers, CRUD, transcript, benchmarks"
```

---

### Task 5: Deepgram Transcription Service

**Files:**
- Create: `backend/app/services/deepgram_transcription.py`

- [ ] **Step 1: Create the transcription service**

```python
import logging
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.pitch_session import PitchSession, PitchSessionStatus
from app.services import s3

logger = logging.getLogger(__name__)


async def transcribe_pitch(session_id: uuid.UUID, db: AsyncSession) -> None:
    """Download audio from S3, send to Deepgram, store transcript, update status."""
    result = await db.execute(select(PitchSession).where(PitchSession.id == session_id))
    ps = result.scalar_one_or_none()
    if ps is None:
        logger.error("Pitch session %s not found", session_id)
        return

    if not ps.file_url:
        ps.status = PitchSessionStatus.failed
        ps.error = "No file uploaded"
        await db.commit()
        return

    try:
        # Download from S3
        logger.info("[pitch-%s] Downloading audio from S3: %s", session_id, ps.file_url)
        audio_data = s3.download_file(ps.file_url)

        # Determine MIME type from file extension
        ext = ps.file_url.rsplit(".", 1)[-1].lower() if "." in ps.file_url else "mp3"
        mime_map = {
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "m4a": "audio/mp4",
            "mp4": "video/mp4",
            "webm": "video/webm",
        }
        content_type = mime_map.get(ext, "audio/mpeg")

        # Call Deepgram
        logger.info("[pitch-%s] Sending to Deepgram (%d bytes, %s)", session_id, len(audio_data), content_type)
        async with httpx.AsyncClient(timeout=600) as client:
            response = await client.post(
                "https://api.deepgram.com/v1/listen",
                params={
                    "model": "nova-2",
                    "diarize": "true",
                    "smart_format": "true",
                    "punctuate": "true",
                    "utterances": "true",
                },
                headers={
                    "Authorization": f"Token {settings.deepgram_api_key}",
                    "Content-Type": content_type,
                },
                content=audio_data,
            )
            response.raise_for_status()
            dg_result = response.json()

        # Extract segments from utterances (or words as fallback)
        segments = []
        utterances = dg_result.get("results", {}).get("utterances", [])
        if utterances:
            for utt in utterances:
                segments.append({
                    "speaker": str(utt.get("speaker", 0)),
                    "text": utt.get("transcript", ""),
                    "start": utt.get("start", 0),
                    "end": utt.get("end", 0),
                    "confidence": utt.get("confidence", 0),
                })
        else:
            # Fallback: build from channels/alternatives
            channels = dg_result.get("results", {}).get("channels", [])
            if channels:
                words = channels[0].get("alternatives", [{}])[0].get("words", [])
                current_speaker = None
                current_text = []
                current_start = 0
                for word in words:
                    speaker = str(word.get("speaker", 0))
                    if speaker != current_speaker:
                        if current_text:
                            segments.append({
                                "speaker": current_speaker,
                                "text": " ".join(current_text),
                                "start": current_start,
                                "end": word.get("start", 0),
                            })
                        current_speaker = speaker
                        current_text = [word.get("punctuated_word", word.get("word", ""))]
                        current_start = word.get("start", 0)
                    else:
                        current_text.append(word.get("punctuated_word", word.get("word", "")))
                if current_text:
                    segments.append({
                        "speaker": current_speaker,
                        "text": " ".join(current_text),
                        "start": current_start,
                        "end": words[-1].get("end", 0) if words else 0,
                    })

        # Detect unique speakers
        unique_speakers = sorted(set(seg["speaker"] for seg in segments))

        # Calculate duration
        duration = 0
        metadata = dg_result.get("metadata", {})
        if metadata.get("duration"):
            duration = int(metadata["duration"])
        elif segments:
            duration = int(segments[-1].get("end", 0))

        # Store raw transcript
        ps.transcript_raw = {
            "speakers": [{"id": sp, "label": f"Speaker {int(sp) + 1}"} for sp in unique_speakers],
            "segments": segments,
            "metadata": {
                "duration": duration,
                "model": "nova-2",
                "speaker_count": len(unique_speakers),
            },
        }
        ps.file_duration_seconds = duration
        ps.status = PitchSessionStatus.labeling
        await db.commit()

        logger.info(
            "[pitch-%s] Transcription complete: %d segments, %d speakers, %ds duration",
            session_id, len(segments), len(unique_speakers), duration,
        )

    except Exception as e:
        logger.error("[pitch-%s] Transcription failed: %s", session_id, e, exc_info=True)
        ps.status = PitchSessionStatus.failed
        ps.error = f"Transcription failed: {e}"
        await db.commit()
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/deepgram_transcription.py
git commit -m "feat(pitch-intelligence): add Deepgram transcription service with diarization"
```

---

### Task 6: AI Analysis Pipeline — Phases 1-4

**Files:**
- Create: `backend/app/services/pitch_agents.py`

- [ ] **Step 1: Create the pitch analysis agents module**

This is a large file — all 4 AI phases plus shared helpers.

```python
import json
import logging
import uuid

import anthropic
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

SONNET_MODEL = "claude-sonnet-4-6-20250514"
OPUS_MODEL = "claude-opus-4-6-20250514"


def _build_transcript_text(labeled: dict) -> str:
    """Convert labeled transcript JSON into readable text for the AI prompt."""
    lines = []
    for seg in labeled.get("segments", []):
        name = seg.get("speaker_name", "Unknown")
        role = seg.get("speaker_role", "other")
        timestamp = _format_time(seg.get("start", 0))
        text = seg.get("text", "")
        lines.append(f"[{timestamp}] {name} ({role}): {text}")
    return "\n".join(lines)


def _format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


async def _perplexity_search(query: str) -> str:
    """Reuse the existing Perplexity search pattern."""
    if not settings.perplexity_api_key:
        return "Perplexity API key not configured — web search unavailable."
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.perplexity_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar-pro",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Provide concise, factual research data. Include specific "
                                "numbers, dates, and sources where available. Keep responses focused and "
                                "under 500 words — prioritize hard data over commentary."
                            ),
                        },
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 2048,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            if len(content) > 3000:
                content = content[:3000] + "\n\n[Response truncated for brevity]"
            return content
    except Exception as e:
        logger.warning("Perplexity search failed: %s", e)
        return f"Search failed: {e}"


# ── Phase 1: Claim Extraction ─────────────────────────────────────────


async def run_claim_extraction(transcript_labeled: dict) -> dict:
    """Extract factual claims from founders and advice/assertions from investors."""
    transcript_text = _build_transcript_text(transcript_labeled)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=8192,
        system=(
            "You are an expert pitch analyst. Extract every factual claim made by founders "
            "(revenue numbers, growth rates, market size, user counts, competitive advantages, "
            "timelines) and every piece of advice or assertion made by investors (market opinions, "
            "valuation benchmarks, strategic suggestions, comparisons to other companies).\n\n"
            "Return a JSON object with two arrays:\n"
            "- \"founder_claims\": each with {\"speaker\", \"timestamp\", \"quote\", \"category\", \"claim_summary\"}\n"
            "- \"investor_claims\": each with {\"speaker\", \"timestamp\", \"quote\", \"category\", \"claim_summary\"}\n\n"
            "Categories for founders: revenue, growth, market_size, users, competitive, timeline, team, technology, unit_economics, other\n"
            "Categories for investors: market_opinion, valuation, strategy, comparison, risk, other\n\n"
            "Be thorough — extract every verifiable claim. Return valid JSON only."
        ),
        messages=[{"role": "user", "content": f"Transcript:\n\n{transcript_text}"}],
    )

    text = response.content[0].text
    # Parse JSON from response (handle markdown code blocks)
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse claim extraction JSON, returning raw text")
        return {"founder_claims": [], "investor_claims": [], "raw_text": text}


# ── Phase 2: Fact-Checking ────────────────────────────────────────────


async def run_fact_check(claims: dict, claim_type: str) -> dict:
    """
    Fact-check a set of claims using Perplexity search.
    claim_type: "founder" or "investor"
    """
    key = "founder_claims" if claim_type == "founder" else "investor_claims"
    claim_list = claims.get(key, [])

    if not claim_list:
        return {"claims": [], "summary": f"No {claim_type} claims to verify."}

    # Search for verification data on each claim (batch similar ones)
    verification_data = {}
    for i, claim in enumerate(claim_list):
        summary = claim.get("claim_summary", claim.get("quote", ""))
        if summary:
            search_result = await _perplexity_search(
                f"Verify: {summary}"
            )
            verification_data[i] = search_result

    # Now have Claude evaluate each claim against the search results
    claims_text = json.dumps(claim_list, indent=2)
    verification_text = json.dumps(verification_data, indent=2)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=SONNET_MODEL,
        max_tokens=8192,
        system=(
            f"You are a fact-checking analyst. Evaluate each {claim_type} claim against the "
            "verification data provided from web searches.\n\n"
            "For each claim, provide:\n"
            "- \"verdict\": one of \"verified\", \"disputed\", \"unverifiable\"\n"
            "- \"confidence\": 0-100\n"
            "- \"explanation\": why you reached this verdict\n"
            "- \"sources\": relevant sources from the verification data\n"
            "- \"original_claim\": the original claim object\n\n"
            "Return a JSON object with:\n"
            "- \"checked_claims\": array of evaluated claims\n"
            "- \"summary\": overall assessment paragraph\n"
            "- \"verified_count\", \"disputed_count\", \"unverifiable_count\": integers\n\n"
            "Return valid JSON only."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Claims to verify:\n{claims_text}\n\n"
                    f"Verification data from web searches:\n{verification_text}"
                ),
            }
        ],
    )

    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"checked_claims": [], "summary": text, "raw_text": text}


# ── Phase 3: Conversation Analysis ───────────────────────────────────


async def run_conversation_analysis(transcript_labeled: dict, fact_check_results: dict) -> dict:
    """Analyze presentation quality, meeting dynamics, and strategic read."""
    transcript_text = _build_transcript_text(transcript_labeled)

    fact_check_summary = ""
    for key in ["founder_fact_check", "investor_fact_check"]:
        fc = fact_check_results.get(key, {})
        if isinstance(fc, dict) and fc.get("summary"):
            fact_check_summary += f"\n{key}: {fc['summary']}\n"

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=OPUS_MODEL,
        max_tokens=8192,
        system=(
            "You are a senior venture capital advisor analyzing a pitch meeting. "
            "Evaluate the conversation across three dimensions:\n\n"
            "1. **Presentation Quality**: pacing, filler words, confidence level, clarity of explanations, "
            "how well founders handled tough questions, storytelling effectiveness\n\n"
            "2. **Meeting Dynamics**: who dominated the conversation (with percentage estimates), "
            "investor engagement level, tension points, moments where founders got defensive, "
            "rapport building, turn-taking patterns\n\n"
            "3. **Strategic Read**: investor interest signals (positive and negative), concerns "
            "that weren't voiced but were implied by questions, how the power dynamic shifted "
            "during the session, likelihood of follow-up\n\n"
            "For each dimension, cite specific moments from the transcript with timestamps.\n\n"
            "Return a JSON object with:\n"
            "- \"presentation_quality\": {\"score\": 0-100, \"assessment\": string, \"highlights\": [{\"timestamp\", \"observation\"}], \"improvements\": [string]}\n"
            "- \"meeting_dynamics\": {\"score\": 0-100, \"assessment\": string, \"speaker_balance\": {name: percentage}, \"key_moments\": [{\"timestamp\", \"observation\"}], \"tension_points\": [{\"timestamp\", \"description\"}]}\n"
            "- \"strategic_read\": {\"score\": 0-100, \"assessment\": string, \"interest_signals\": [{\"timestamp\", \"signal\", \"polarity\"}], \"unvoiced_concerns\": [string], \"follow_up_likelihood\": string}\n"
            "- \"overall_environment_score\": 0-100\n"
            "- \"environment_summary\": string\n\n"
            "Return valid JSON only."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Pitch meeting transcript:\n\n{transcript_text}\n\n"
                    f"Fact-check context:\n{fact_check_summary}"
                ),
            }
        ],
    )

    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}


# ── Phase 4: Scoring & Recommendations ───────────────────────────────


async def run_scoring(
    transcript_labeled: dict,
    claims: dict,
    fact_check_results: dict,
    conversation_analysis: dict,
) -> dict:
    """Generate final scores and prioritized recommendations."""
    transcript_text = _build_transcript_text(transcript_labeled)

    # Build context from prior phases
    prior_context = json.dumps({
        "claims_extracted": {
            "founder_count": len(claims.get("founder_claims", [])),
            "investor_count": len(claims.get("investor_claims", [])),
        },
        "fact_check": {
            k: {
                "verified": v.get("verified_count", 0),
                "disputed": v.get("disputed_count", 0),
                "unverifiable": v.get("unverifiable_count", 0),
                "summary": v.get("summary", ""),
            }
            for k, v in fact_check_results.items()
            if isinstance(v, dict)
        },
        "conversation_analysis": {
            k: v.get("score", 0) if isinstance(v, dict) else v
            for k, v in conversation_analysis.items()
            if k in ("presentation_quality", "meeting_dynamics", "strategic_read", "overall_environment_score")
        },
    }, indent=2)

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=OPUS_MODEL,
        max_tokens=8192,
        system=(
            "You are a senior pitch coach and venture analyst. Based on the full transcript "
            "and all prior analysis phases, generate final scores and actionable recommendations.\n\n"
            "Score each dimension 0-100:\n"
            "- pitch_clarity: How clear and compelling was the pitch narrative?\n"
            "- financial_rigor: How solid were the financial claims and projections?\n"
            "- q_and_a_handling: How well did founders handle investor questions?\n"
            "- investor_engagement: How engaged and interested were the investors?\n"
            "- fact_accuracy: What percentage of verifiable claims checked out?\n"
            "- overall: Weighted overall pitch effectiveness\n\n"
            "Then provide 5-10 prioritized recommendations, each tied to a specific transcript moment.\n\n"
            "Return a JSON object with:\n"
            "- \"scores\": {\"pitch_clarity\": int, \"financial_rigor\": int, \"q_and_a_handling\": int, \"investor_engagement\": int, \"fact_accuracy\": int, \"overall\": int}\n"
            "- \"recommendations\": [{\"priority\": 1-10, \"title\": string, \"description\": string, \"transcript_reference\": string, \"impact\": \"high\"|\"medium\"|\"low\"}]\n"
            "- \"executive_summary\": string (2-3 paragraph overall assessment)\n\n"
            "Return valid JSON only."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Transcript:\n\n{transcript_text}\n\n"
                    f"Analysis context:\n{prior_context}"
                ),
            }
        ],
    )

    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_text": text}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/pitch_agents.py
git commit -m "feat(pitch-intelligence): add AI analysis pipeline — claim extraction, fact-checking, conversation analysis, scoring"
```

---

### Task 7: Benchmark Calculation (Phase 5)

**Files:**
- Create: `backend/app/services/pitch_benchmark.py`

- [ ] **Step 1: Create the benchmark service**

```python
import logging
import statistics
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pitch_session import PitchBenchmark, PitchSession, PitchSessionStatus

logger = logging.getLogger(__name__)

SCORE_DIMENSIONS = [
    "pitch_clarity",
    "financial_rigor",
    "q_and_a_handling",
    "investor_engagement",
    "fact_accuracy",
    "overall",
]


async def calculate_benchmarks(session_id: uuid.UUID, db: AsyncSession) -> dict:
    """
    Compare this pitch's scores against aggregate and update benchmark table.
    Returns percentile rankings per dimension.
    """
    result = await db.execute(select(PitchSession).where(PitchSession.id == session_id))
    ps = result.scalar_one_or_none()
    if ps is None or not ps.scores:
        return {}

    scores = ps.scores
    percentiles = {}

    for dimension in SCORE_DIMENSIONS:
        score = scores.get(dimension)
        if score is None:
            continue

        # Get all completed sessions' scores for this dimension
        all_result = await db.execute(
            select(PitchSession).where(
                PitchSession.status == PitchSessionStatus.complete,
                PitchSession.scores.isnot(None),
                PitchSession.id != session_id,
            )
        )
        all_sessions = all_result.scalars().all()
        all_scores = []
        for s in all_sessions:
            if s.scores and dimension in s.scores:
                all_scores.append(s.scores[dimension])

        # Add current score
        all_scores.append(score)

        if len(all_scores) < 2:
            percentiles[dimension] = 50  # Not enough data
            continue

        # Calculate percentile
        below = sum(1 for s in all_scores if s < score)
        percentile = int((below / len(all_scores)) * 100)
        percentiles[dimension] = percentile

        # Update benchmark table
        sorted_scores = sorted(all_scores)
        n = len(sorted_scores)
        p25_idx = max(0, int(n * 0.25) - 1)
        p75_idx = min(n - 1, int(n * 0.75))

        benchmark_result = await db.execute(
            select(PitchBenchmark).where(
                PitchBenchmark.dimension == dimension,
                PitchBenchmark.stage.is_(None),
                PitchBenchmark.industry.is_(None),
            )
        )
        benchmark = benchmark_result.scalar_one_or_none()

        if benchmark is None:
            benchmark = PitchBenchmark(
                dimension=dimension,
                stage=None,
                industry=None,
            )
            db.add(benchmark)

        benchmark.sample_count = n
        benchmark.mean_score = round(statistics.mean(all_scores), 1)
        benchmark.median_score = round(statistics.median(all_scores), 1)
        benchmark.p25 = round(sorted_scores[p25_idx], 1)
        benchmark.p75 = round(sorted_scores[p75_idx], 1)

    # Store percentiles on the session
    ps.benchmark_percentiles = percentiles
    await db.commit()

    return percentiles
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/pitch_benchmark.py
git commit -m "feat(pitch-intelligence): add benchmark calculation service"
```

---

### Task 8: Pitch Intelligence Worker

**Files:**
- Create: `backend/app/services/pitch_worker.py`

- [ ] **Step 1: Create the worker that orchestrates transcription + analysis**

```python
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import async_session
from app.models.pitch_session import (
    PitchAnalysisPhase,
    PitchAnalysisResult,
    PitchPhaseStatus,
    PitchSession,
    PitchSessionStatus,
)
from app.services.deepgram_transcription import transcribe_pitch
from app.services.pitch_agents import (
    run_claim_extraction,
    run_conversation_analysis,
    run_fact_check,
    run_scoring,
)
from app.services.pitch_benchmark import calculate_benchmarks

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5  # seconds


async def _update_phase(db: AsyncSession, session_id: uuid.UUID, phase: PitchAnalysisPhase, status: PitchPhaseStatus, result: dict | None = None, error: str | None = None) -> None:
    """Update a phase's status and result."""
    phase_result = await db.execute(
        select(PitchAnalysisResult).where(
            PitchAnalysisResult.session_id == session_id,
            PitchAnalysisResult.phase == phase,
        )
    )
    pr = phase_result.scalar_one_or_none()
    if pr:
        pr.status = status
        if result is not None:
            pr.result = result
        if error is not None:
            pr.error = error
        await db.commit()


async def _run_analysis_pipeline(session_id: uuid.UUID) -> None:
    """Run all 5 analysis phases sequentially."""
    logger.info("[pitch-%s] Starting analysis pipeline", session_id)

    # Phase 1: Claim Extraction
    try:
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.claim_extraction, PitchPhaseStatus.running)
            ps = (await db.execute(select(PitchSession).where(PitchSession.id == session_id))).scalar_one()
            transcript_labeled = ps.transcript_labeled

        logger.info("[pitch-%s] Phase 1: Claim Extraction", session_id)
        claims = await run_claim_extraction(transcript_labeled)

        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.claim_extraction, PitchPhaseStatus.complete, result=claims)
    except Exception as e:
        logger.error("[pitch-%s] Phase 1 failed: %s", session_id, e, exc_info=True)
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.claim_extraction, PitchPhaseStatus.failed, error=str(e))
            ps = (await db.execute(select(PitchSession).where(PitchSession.id == session_id))).scalar_one()
            ps.status = PitchSessionStatus.failed
            ps.error = f"Claim extraction failed: {e}"
            await db.commit()
        return

    # Phase 2: Fact-checking (founder + investor in parallel)
    try:
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.fact_check_founders, PitchPhaseStatus.running)
            await _update_phase(db, session_id, PitchAnalysisPhase.fact_check_investors, PitchPhaseStatus.running)

        logger.info("[pitch-%s] Phase 2: Fact-Checking (parallel)", session_id)
        founder_fc, investor_fc = await asyncio.gather(
            run_fact_check(claims, "founder"),
            run_fact_check(claims, "investor"),
        )
        fact_check_results = {
            "founder_fact_check": founder_fc,
            "investor_fact_check": investor_fc,
        }

        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.fact_check_founders, PitchPhaseStatus.complete, result=founder_fc)
            await _update_phase(db, session_id, PitchAnalysisPhase.fact_check_investors, PitchPhaseStatus.complete, result=investor_fc)
    except Exception as e:
        logger.error("[pitch-%s] Phase 2 failed: %s", session_id, e, exc_info=True)
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.fact_check_founders, PitchPhaseStatus.failed, error=str(e))
            await _update_phase(db, session_id, PitchAnalysisPhase.fact_check_investors, PitchPhaseStatus.failed, error=str(e))
            ps = (await db.execute(select(PitchSession).where(PitchSession.id == session_id))).scalar_one()
            ps.status = PitchSessionStatus.failed
            ps.error = f"Fact-checking failed: {e}"
            await db.commit()
        return

    # Phase 3: Conversation Analysis
    try:
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.conversation_analysis, PitchPhaseStatus.running)

        logger.info("[pitch-%s] Phase 3: Conversation Analysis", session_id)
        conversation = await run_conversation_analysis(transcript_labeled, fact_check_results)

        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.conversation_analysis, PitchPhaseStatus.complete, result=conversation)
    except Exception as e:
        logger.error("[pitch-%s] Phase 3 failed: %s", session_id, e, exc_info=True)
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.conversation_analysis, PitchPhaseStatus.failed, error=str(e))
            ps = (await db.execute(select(PitchSession).where(PitchSession.id == session_id))).scalar_one()
            ps.status = PitchSessionStatus.failed
            ps.error = f"Conversation analysis failed: {e}"
            await db.commit()
        return

    # Phase 4: Scoring & Recommendations
    try:
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.scoring, PitchPhaseStatus.running)

        logger.info("[pitch-%s] Phase 4: Scoring & Recommendations", session_id)
        scoring = await run_scoring(transcript_labeled, claims, fact_check_results, conversation)

        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.scoring, PitchPhaseStatus.complete, result=scoring)
            # Store scores on the session
            ps = (await db.execute(select(PitchSession).where(PitchSession.id == session_id))).scalar_one()
            ps.scores = scoring.get("scores", {})
            await db.commit()
    except Exception as e:
        logger.error("[pitch-%s] Phase 4 failed: %s", session_id, e, exc_info=True)
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.scoring, PitchPhaseStatus.failed, error=str(e))
            ps = (await db.execute(select(PitchSession).where(PitchSession.id == session_id))).scalar_one()
            ps.status = PitchSessionStatus.failed
            ps.error = f"Scoring failed: {e}"
            await db.commit()
        return

    # Phase 5: Benchmark Comparison
    try:
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.benchmark, PitchPhaseStatus.running)

        logger.info("[pitch-%s] Phase 5: Benchmark Comparison", session_id)
        async with async_session() as db:
            percentiles = await calculate_benchmarks(session_id, db)
            await _update_phase(db, session_id, PitchAnalysisPhase.benchmark, PitchPhaseStatus.complete, result=percentiles)
    except Exception as e:
        logger.error("[pitch-%s] Phase 5 failed: %s", session_id, e, exc_info=True)
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.benchmark, PitchPhaseStatus.failed, error=str(e))

    # Mark session complete
    async with async_session() as db:
        ps = (await db.execute(select(PitchSession).where(PitchSession.id == session_id))).scalar_one()
        ps.status = PitchSessionStatus.complete
        await db.commit()

    logger.info("[pitch-%s] Analysis pipeline complete", session_id)


async def run_pitch_worker() -> None:
    """Poll for pitch sessions needing transcription or analysis."""
    logger.info("Pitch Intelligence worker started")

    while True:
        try:
            # Check for sessions needing transcription
            async with async_session() as db:
                result = await db.execute(
                    select(PitchSession)
                    .where(PitchSession.status == PitchSessionStatus.transcribing)
                    .order_by(PitchSession.created_at.asc())
                    .limit(1)
                )
                job = result.scalar_one_or_none()
                if job:
                    logger.info("[pitch-%s] Picking up transcription job", job.id)
                    await transcribe_pitch(job.id, db)

            # Check for sessions needing analysis
            async with async_session() as db:
                result = await db.execute(
                    select(PitchSession)
                    .where(PitchSession.status == PitchSessionStatus.analyzing)
                    .order_by(PitchSession.created_at.asc())
                    .limit(1)
                )
                job = result.scalar_one_or_none()
                if job:
                    logger.info("[pitch-%s] Picking up analysis job", job.id)
                    await _run_analysis_pipeline(job.id)

        except Exception as e:
            logger.error("Pitch worker error: %s", e, exc_info=True)

        await asyncio.sleep(POLL_INTERVAL)
```

- [ ] **Step 2: Integrate with analysis_worker.py**

In `backend/app/services/analysis_worker.py`, at the bottom where `asyncio.run(run_analysis_worker())` is called, change it to run both workers concurrently. Find the existing entry point and modify it:

Add this import at the top:

```python
from app.services.pitch_worker import run_pitch_worker
```

Then replace the bottom `asyncio.run(run_analysis_worker())` with:

```python
async def _main():
    await asyncio.gather(
        run_analysis_worker(),
        run_pitch_worker(),
    )

asyncio.run(_main())
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/pitch_worker.py backend/app/services/analysis_worker.py
git commit -m "feat(pitch-intelligence): add pitch worker with 5-phase pipeline orchestration"
```

---

### Task 9: Frontend Types + API Methods

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add TypeScript types**

Append to `frontend/lib/types.ts`:

```typescript
// ── Pitch Intelligence types ─────────────────────────────────────────

export interface PitchSessionSummary {
  id: string;
  startup_id: string | null;
  title: string | null;
  status: "uploading" | "transcribing" | "labeling" | "analyzing" | "complete" | "failed";
  file_duration_seconds: number | null;
  scores: Record<string, number> | null;
  benchmark_percentiles: Record<string, number> | null;
  has_labeled_transcript: boolean;
  speaker_count: number;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PitchPhaseResult {
  id: string;
  phase: string;
  status: "pending" | "running" | "complete" | "failed";
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PitchSessionDetail extends PitchSessionSummary {
  results: PitchPhaseResult[];
}

export interface PitchTranscriptSpeaker {
  id: string;
  name?: string;
  label?: string;
  role?: string;
}

export interface PitchTranscriptSegment {
  speaker: string;
  speaker_id?: string;
  speaker_name?: string;
  speaker_role?: string;
  text: string;
  start: number;
  end: number;
}

export interface PitchTranscript {
  speakers: PitchTranscriptSpeaker[];
  segments: PitchTranscriptSegment[];
  metadata?: Record<string, unknown>;
}

export interface PitchStatusResponse {
  id: string;
  status: string;
  phases: { phase: string; status: string }[];
}
```

- [ ] **Step 2: Add API methods**

Append to the `api` object in `frontend/lib/api.ts`:

```typescript
  // ── Pitch Intelligence ──────────────────────────────────────────────

  createPitchUpload: async (
    token: string,
    filename: string,
    contentType: string,
    title?: string,
    startupId?: string,
  ): Promise<{ id: string; upload_url: string; s3_key: string }> => {
    return apiFetch("/api/pitch-intelligence/upload", {
      method: "POST",
      headers: authHeaders(token),
      body: JSON.stringify({
        filename,
        content_type: contentType,
        title: title || null,
        startup_id: startupId || null,
      }),
    });
  },

  completePitchUpload: async (token: string, sessionId: string): Promise<{ id: string; status: string }> => {
    return apiFetch(`/api/pitch-intelligence/${sessionId}/upload-complete`, {
      method: "POST",
      headers: authHeaders(token),
    });
  },

  labelPitchSpeakers: async (
    token: string,
    sessionId: string,
    speakers: { speaker_id: string; name: string; role: string }[],
  ): Promise<{ id: string; status: string }> => {
    return apiFetch(`/api/pitch-intelligence/${sessionId}/speakers`, {
      method: "PUT",
      headers: authHeaders(token),
      body: JSON.stringify({ speakers }),
    });
  },

  getPitchSession: (token: string, sessionId: string): Promise<import("./types").PitchSessionDetail> =>
    apiFetch(`/api/pitch-intelligence/${sessionId}`, {
      headers: authHeaders(token),
    }),

  getPitchStatus: (token: string, sessionId: string): Promise<import("./types").PitchStatusResponse> =>
    apiFetch(`/api/pitch-intelligence/${sessionId}/status`, {
      headers: authHeaders(token),
    }),

  listPitchSessions: (token: string): Promise<{ items: import("./types").PitchSessionSummary[] }> =>
    apiFetch("/api/pitch-intelligence", {
      headers: authHeaders(token),
    }),

  deletePitchSession: async (token: string, sessionId: string): Promise<{ deleted: boolean }> =>
    apiFetch(`/api/pitch-intelligence/${sessionId}`, {
      method: "DELETE",
      headers: authHeaders(token),
    }),

  getPitchTranscript: (token: string, sessionId: string): Promise<import("./types").PitchTranscript> =>
    apiFetch(`/api/pitch-intelligence/${sessionId}/transcript`, {
      headers: authHeaders(token),
    }),
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat(pitch-intelligence): add frontend types and API methods"
```

---

### Task 10: Frontend — Upload Page

**Files:**
- Create: `frontend/app/pitch-intelligence/page.tsx`

- [ ] **Step 1: Create the main pitch intelligence page**

```tsx
"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { PitchSessionSummary } from "@/lib/types";

export default function PitchIntelligencePage() {
  return (
    <Suspense fallback={<div className="p-8 text-text-secondary">Loading...</div>}>
      <PitchIntelligenceContent />
    </Suspense>
  );
}

const ACCEPTED_TYPES: Record<string, string> = {
  "audio/mpeg": ".mp3",
  "audio/wav": ".wav",
  "audio/x-wav": ".wav",
  "audio/mp4": ".m4a",
  "audio/x-m4a": ".m4a",
  "video/mp4": ".mp4",
  "video/webm": ".webm",
  "audio/webm": ".webm",
};

function PitchIntelligenceContent() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const router = useRouter();

  const [sessions, setSessions] = useState<PitchSessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [title, setTitle] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadSessions = useCallback(async () => {
    if (!token) return;
    try {
      const data = await api.listPitchSessions(token);
      setSessions(data.items);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleUpload = async (file: File) => {
    if (!token) return;
    if (!ACCEPTED_TYPES[file.type]) {
      setError("Unsupported file type. Please upload MP3, WAV, M4A, MP4, or WebM.");
      return;
    }
    if (file.size > 500 * 1024 * 1024) {
      setError("File too large. Maximum size is 500MB.");
      return;
    }

    setError(null);
    setUploading(true);
    setUploadProgress(0);

    try {
      // 1. Get presigned URL
      const { id, upload_url } = await api.createPitchUpload(
        token,
        file.name,
        file.type,
        title || undefined,
      );

      // 2. Upload directly to S3
      setUploadProgress(10);
      const xhr = new XMLHttpRequest();
      await new Promise<void>((resolve, reject) => {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            setUploadProgress(10 + Math.round((e.loaded / e.total) * 80));
          }
        };
        xhr.onload = () => (xhr.status < 400 ? resolve() : reject(new Error(`Upload failed: ${xhr.status}`)));
        xhr.onerror = () => reject(new Error("Upload failed"));
        xhr.open("PUT", upload_url);
        xhr.setRequestHeader("Content-Type", file.type);
        xhr.send(file);
      });

      // 3. Notify backend
      setUploadProgress(95);
      await api.completePitchUpload(token, id);
      setUploadProgress(100);

      // Navigate to session page
      router.push(`/pitch-intelligence/${id}`);
    } catch (e: any) {
      setError(e.message || "Upload failed");
      setUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
  };

  const statusLabel = (status: string) => {
    const map: Record<string, { text: string; color: string }> = {
      uploading: { text: "Uploading", color: "text-yellow-600" },
      transcribing: { text: "Transcribing", color: "text-blue-600" },
      labeling: { text: "Needs Speaker Labels", color: "text-orange-600" },
      analyzing: { text: "Analyzing", color: "text-blue-600" },
      complete: { text: "Complete", color: "text-green-600" },
      failed: { text: "Failed", color: "text-red-600" },
    };
    const info = map[status] || { text: status, color: "text-text-secondary" };
    return <span className={info.color}>{info.text}</span>;
  };

  if (!session) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-16 text-center">
        <p className="text-text-secondary">Sign in to access Pitch Intelligence.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-serif text-text-primary mb-2">Pitch Intelligence</h1>
        <p className="text-text-secondary">
          Upload a pitch recording to get AI-powered analysis, fact-checking, and coaching.
        </p>
      </div>

      {/* Upload Zone */}
      {!uploading && (
        <div className="mb-8">
          <div className="mb-4">
            <input
              type="text"
              placeholder="Session title (optional)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded border border-border bg-surface px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none"
            />
          </div>
          <div
            className={`relative rounded-lg border-2 border-dashed p-12 text-center transition cursor-pointer ${
              dragOver
                ? "border-accent bg-accent/5"
                : "border-border hover:border-accent/50"
            }`}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".mp3,.wav,.m4a,.mp4,.webm"
              className="hidden"
              onChange={handleFileSelect}
            />
            <div className="text-4xl mb-3 text-text-tertiary">&#127908;</div>
            <p className="text-text-primary font-medium mb-1">
              Drop an audio or video file here, or click to browse
            </p>
            <p className="text-text-tertiary text-sm">
              MP3, WAV, M4A, MP4, WebM — up to 500MB
            </p>
          </div>
        </div>
      )}

      {/* Upload Progress */}
      {uploading && (
        <div className="mb-8 rounded-lg border border-border bg-surface p-6">
          <p className="text-sm text-text-secondary mb-3">Uploading...</p>
          <div className="h-2 rounded-full bg-surface-alt overflow-hidden">
            <div
              className="h-full rounded-full bg-accent transition-all duration-300"
              style={{ width: `${uploadProgress}%` }}
            />
          </div>
          <p className="text-xs text-text-tertiary mt-2">{uploadProgress}%</p>
        </div>
      )}

      {error && (
        <div className="mb-6 rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Session List */}
      <div>
        <h2 className="text-lg font-medium text-text-primary mb-4">Your Pitch Sessions</h2>
        {loading ? (
          <p className="text-text-tertiary text-sm">Loading...</p>
        ) : sessions.length === 0 ? (
          <p className="text-text-tertiary text-sm">No pitch sessions yet. Upload your first recording above.</p>
        ) : (
          <div className="space-y-3">
            {sessions.map((s) => (
              <Link
                key={s.id}
                href={`/pitch-intelligence/${s.id}`}
                className="block rounded-lg border border-border bg-surface p-4 hover:border-accent/50 transition"
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-medium text-text-primary">
                      {s.title || "Untitled Pitch"}
                    </p>
                    <p className="text-sm text-text-tertiary mt-0.5">
                      {s.created_at ? new Date(s.created_at).toLocaleDateString() : ""}
                      {s.file_duration_seconds
                        ? ` · ${Math.round(s.file_duration_seconds / 60)}min`
                        : ""}
                    </p>
                  </div>
                  <div className="flex items-center gap-4">
                    {s.scores?.overall != null && (
                      <span className="text-lg font-medium text-accent">{s.scores.overall}</span>
                    )}
                    <span className="text-sm">{statusLabel(s.status)}</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/pitch-intelligence/page.tsx
git commit -m "feat(pitch-intelligence): add upload page with drag-and-drop, S3 direct upload, session list"
```

---

### Task 11: Frontend — Session Detail / Results Page

**Files:**
- Create: `frontend/app/pitch-intelligence/[id]/page.tsx`

- [ ] **Step 1: Create the session detail page**

This is the largest frontend file — handles speaker labeling, progressive results display, transcript viewer, fact-check tabs, scores, and recommendations.

```tsx
"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSession } from "next-auth/react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type {
  PitchSessionDetail,
  PitchTranscript,
  PitchPhaseResult,
} from "@/lib/types";

export default function PitchSessionPage() {
  return (
    <Suspense fallback={<div className="p-8 text-text-secondary">Loading...</div>}>
      <PitchSessionContent />
    </Suspense>
  );
}

function PitchSessionContent() {
  const { data: session } = useSession();
  const token = (session as any)?.backendToken;
  const params = useParams();
  const sessionId = params.id as string;
  const router = useRouter();

  const [ps, setPs] = useState<PitchSessionDetail | null>(null);
  const [transcript, setTranscript] = useState<PitchTranscript | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"transcript" | "fact-check" | "analysis" | "scores">("transcript");
  const [factCheckTab, setFactCheckTab] = useState<"founders" | "investors">("founders");

  // Speaker labeling state
  const [speakerLabels, setSpeakerLabels] = useState<Record<string, { name: string; role: string }>>({});
  const [labeling, setLabeling] = useState(false);

  const loadSession = useCallback(async () => {
    if (!token || !sessionId) return;
    try {
      const data = await api.getPitchSession(token, sessionId);
      setPs(data);

      // Load transcript if available
      if (["labeling", "analyzing", "complete"].includes(data.status)) {
        try {
          const t = await api.getPitchTranscript(token, sessionId);
          setTranscript(t);
          // Initialize speaker labels
          if (data.status === "labeling" && t.speakers) {
            const labels: Record<string, { name: string; role: string }> = {};
            t.speakers.forEach((sp) => {
              labels[sp.id] = { name: sp.name || sp.label || "", role: "founder" };
            });
            setSpeakerLabels(labels);
          }
        } catch {
          // transcript not ready yet
        }
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [token, sessionId]);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  // Poll for status updates when transcribing or analyzing
  useEffect(() => {
    if (!token || !ps || !["transcribing", "analyzing"].includes(ps.status)) return;
    const interval = setInterval(async () => {
      try {
        const data = await api.getPitchSession(token, sessionId);
        setPs(data);
        if (["labeling", "complete", "failed"].includes(data.status)) {
          clearInterval(interval);
          if (data.status === "labeling") {
            const t = await api.getPitchTranscript(token, sessionId);
            setTranscript(t);
            const labels: Record<string, { name: string; role: string }> = {};
            t.speakers?.forEach((sp) => {
              labels[sp.id] = { name: sp.name || sp.label || "", role: "founder" };
            });
            setSpeakerLabels(labels);
          }
        }
      } catch {
        // silent
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [token, ps?.status, sessionId]);

  const handleLabelSubmit = async () => {
    if (!token) return;
    setLabeling(true);
    try {
      const speakers = Object.entries(speakerLabels).map(([id, info]) => ({
        speaker_id: id,
        name: info.name || `Speaker ${parseInt(id) + 1}`,
        role: info.role,
      }));
      await api.labelPitchSpeakers(token, sessionId, speakers);
      await loadSession();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLabeling(false);
    }
  };

  const getPhaseResult = (phase: string): PitchPhaseResult | undefined => {
    return ps?.results?.find((r) => r.phase === phase);
  };

  const phaseStatus = (phase: string) => {
    const r = getPhaseResult(phase);
    if (!r) return "pending";
    return r.status;
  };

  if (!session) {
    return <div className="p-8 text-text-secondary">Sign in to access Pitch Intelligence.</div>;
  }
  if (loading) {
    return <div className="p-8 text-text-secondary">Loading...</div>;
  }
  if (error || !ps) {
    return <div className="p-8 text-red-600">{error || "Session not found"}</div>;
  }

  // ── Transcribing state ─────────────────────────────────────────────
  if (ps.status === "uploading" || ps.status === "transcribing") {
    return (
      <div className="mx-auto max-w-4xl px-6 py-16 text-center">
        <div className="animate-pulse text-4xl mb-4">&#127908;</div>
        <h2 className="text-xl font-medium text-text-primary mb-2">
          {ps.status === "uploading" ? "Processing upload..." : "Transcribing your pitch..."}
        </h2>
        <p className="text-text-secondary">
          This usually takes 1-3 minutes depending on the recording length.
        </p>
      </div>
    );
  }

  // ── Speaker labeling state ─────────────────────────────────────────
  if (ps.status === "labeling") {
    return (
      <div className="mx-auto max-w-4xl px-6 py-10">
        <h1 className="text-2xl font-serif text-text-primary mb-2">Label Speakers</h1>
        <p className="text-text-secondary mb-6">
          We detected {transcript?.speakers?.length || 0} speakers. Assign names and roles to each.
        </p>

        <div className="space-y-4 mb-8">
          {transcript?.speakers?.map((sp) => {
            const label = speakerLabels[sp.id] || { name: "", role: "founder" };
            // Find sample segments for this speaker
            const samples = (transcript.segments || [])
              .filter((seg) => seg.speaker === sp.id || seg.speaker_id === sp.id)
              .slice(0, 2);
            return (
              <div key={sp.id} className="rounded-lg border border-border bg-surface p-4">
                <p className="text-sm text-text-tertiary mb-2">{sp.label || `Speaker ${parseInt(sp.id) + 1}`}</p>
                {samples.length > 0 && (
                  <div className="mb-3 space-y-1">
                    {samples.map((seg, i) => (
                      <p key={i} className="text-sm text-text-secondary italic">
                        &ldquo;{seg.text.slice(0, 150)}{seg.text.length > 150 ? "..." : ""}&rdquo;
                      </p>
                    ))}
                  </div>
                )}
                <div className="flex gap-3">
                  <input
                    type="text"
                    placeholder="Name"
                    value={label.name}
                    onChange={(e) =>
                      setSpeakerLabels((prev) => ({
                        ...prev,
                        [sp.id]: { ...prev[sp.id], name: e.target.value },
                      }))
                    }
                    className="flex-1 rounded border border-border bg-background px-3 py-1.5 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none"
                  />
                  <select
                    value={label.role}
                    onChange={(e) =>
                      setSpeakerLabels((prev) => ({
                        ...prev,
                        [sp.id]: { ...prev[sp.id], role: e.target.value },
                      }))
                    }
                    className="rounded border border-border bg-background px-3 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none"
                  >
                    <option value="founder">Founder</option>
                    <option value="investor">Investor</option>
                    <option value="other">Other</option>
                  </select>
                </div>
              </div>
            );
          })}
        </div>

        <button
          onClick={handleLabelSubmit}
          disabled={labeling}
          className="rounded bg-accent px-6 py-2 text-sm font-medium text-white hover:bg-accent/90 disabled:opacity-50 transition"
        >
          {labeling ? "Starting Analysis..." : "Start Analysis"}
        </button>
      </div>
    );
  }

  // ── Failed state ───────────────────────────────────────────────────
  if (ps.status === "failed") {
    return (
      <div className="mx-auto max-w-4xl px-6 py-16 text-center">
        <h2 className="text-xl font-medium text-red-600 mb-2">Analysis Failed</h2>
        <p className="text-text-secondary">{ps.error || "An error occurred during analysis."}</p>
        <button
          onClick={() => router.push("/pitch-intelligence")}
          className="mt-4 text-sm text-accent hover:underline"
        >
          Back to Pitch Intelligence
        </button>
      </div>
    );
  }

  // ── Analyzing / Complete — show results ────────────────────────────

  const claimResult = getPhaseResult("claim_extraction");
  const founderFcResult = getPhaseResult("fact_check_founders");
  const investorFcResult = getPhaseResult("fact_check_investors");
  const conversationResult = getPhaseResult("conversation_analysis");
  const scoringResult = getPhaseResult("scoring");
  const benchmarkResult = getPhaseResult("benchmark");

  const scores = ps.scores || scoringResult?.result?.scores as Record<string, number> || {};
  const recommendations = (scoringResult?.result?.recommendations || []) as any[];
  const executiveSummary = scoringResult?.result?.executive_summary as string || "";

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-serif text-text-primary">
            {ps.title || "Untitled Pitch"}
          </h1>
          <p className="text-sm text-text-tertiary mt-1">
            {ps.created_at ? new Date(ps.created_at).toLocaleDateString() : ""}
            {ps.file_duration_seconds ? ` · ${Math.round(ps.file_duration_seconds / 60)} min` : ""}
          </p>
        </div>
        {scores.overall != null && (
          <div className="text-right">
            <div className="text-3xl font-bold text-accent">{scores.overall}</div>
            <div className="text-xs text-text-tertiary">Overall Score</div>
          </div>
        )}
      </div>

      {/* Phase Progress */}
      {ps.status === "analyzing" && (
        <div className="mb-6 rounded-lg border border-border bg-surface p-4">
          <p className="text-sm font-medium text-text-primary mb-3">Analysis in progress...</p>
          <div className="grid grid-cols-6 gap-2">
            {["claim_extraction", "fact_check_founders", "fact_check_investors", "conversation_analysis", "scoring", "benchmark"].map((phase) => {
              const st = phaseStatus(phase);
              const label = phase.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
              return (
                <div key={phase} className="text-center">
                  <div
                    className={`h-2 rounded-full mb-1 ${
                      st === "complete" ? "bg-green-500" :
                      st === "running" ? "bg-blue-500 animate-pulse" :
                      st === "failed" ? "bg-red-500" :
                      "bg-surface-alt"
                    }`}
                  />
                  <p className="text-[10px] text-text-tertiary leading-tight">{label}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Executive Summary */}
      {executiveSummary && (
        <div className="mb-6 rounded-lg border border-border bg-surface p-5">
          <h3 className="text-sm font-medium text-text-primary mb-2">Executive Summary</h3>
          <p className="text-sm text-text-secondary whitespace-pre-line">{executiveSummary}</p>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex gap-1 border-b border-border mb-6">
        {(["transcript", "fact-check", "analysis", "scores"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
              activeTab === tab
                ? "border-accent text-accent"
                : "border-transparent text-text-tertiary hover:text-text-secondary"
            }`}
          >
            {tab === "fact-check" ? "Fact-Check" : tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === "transcript" && (
        <TranscriptPanel sessionId={sessionId} token={token} transcript={transcript} />
      )}

      {activeTab === "fact-check" && (
        <div>
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setFactCheckTab("founders")}
              className={`px-3 py-1 text-sm rounded ${factCheckTab === "founders" ? "bg-accent text-white" : "bg-surface-alt text-text-secondary"}`}
            >
              Founder Claims
            </button>
            <button
              onClick={() => setFactCheckTab("investors")}
              className={`px-3 py-1 text-sm rounded ${factCheckTab === "investors" ? "bg-accent text-white" : "bg-surface-alt text-text-secondary"}`}
            >
              Investor Advice
            </button>
          </div>
          <FactCheckPanel
            result={factCheckTab === "founders" ? founderFcResult : investorFcResult}
            phase={factCheckTab === "founders" ? "fact_check_founders" : "fact_check_investors"}
          />
        </div>
      )}

      {activeTab === "analysis" && (
        <ConversationAnalysisPanel result={conversationResult} />
      )}

      {activeTab === "scores" && (
        <ScoresPanel
          scores={scores}
          percentiles={ps.benchmark_percentiles || {}}
          recommendations={recommendations}
        />
      )}
    </div>
  );
}

// ── Sub-components ───────────────────────────────────────────────────

function TranscriptPanel({
  sessionId,
  token,
  transcript,
}: {
  sessionId: string;
  token: string;
  transcript: PitchTranscript | null;
}) {
  const [data, setData] = useState<PitchTranscript | null>(transcript);

  useEffect(() => {
    if (transcript) {
      setData(transcript);
      return;
    }
    if (!token || !sessionId) return;
    api.getPitchTranscript(token, sessionId).then(setData).catch(() => {});
  }, [token, sessionId, transcript]);

  if (!data) return <p className="text-text-tertiary text-sm">Transcript not available yet.</p>;

  const roleColors: Record<string, string> = {
    founder: "text-blue-600",
    investor: "text-emerald-600",
    other: "text-text-secondary",
  };

  return (
    <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
      {data.segments?.map((seg, i) => {
        const role = seg.speaker_role || "other";
        const name = seg.speaker_name || seg.speaker || `Speaker ${i}`;
        const time = formatTime(seg.start);
        return (
          <div key={i} className="flex gap-3">
            <span className="text-xs text-text-tertiary w-12 shrink-0 pt-0.5">{time}</span>
            <div>
              <span className={`text-sm font-medium ${roleColors[role] || roleColors.other}`}>
                {name}
              </span>
              <p className="text-sm text-text-primary">{seg.text}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FactCheckPanel({ result, phase }: { result?: PitchPhaseResult; phase: string }) {
  if (!result || result.status === "pending") {
    return <p className="text-text-tertiary text-sm">Waiting for fact-check to start...</p>;
  }
  if (result.status === "running") {
    return <p className="text-blue-600 text-sm animate-pulse">Fact-checking in progress...</p>;
  }
  if (result.status === "failed") {
    return <p className="text-red-600 text-sm">Fact-check failed: {result.error}</p>;
  }

  const data = result.result as any;
  const claims = data?.checked_claims || [];

  const verdictBadge = (verdict: string) => {
    const styles: Record<string, string> = {
      verified: "bg-green-100 text-green-700",
      disputed: "bg-red-100 text-red-700",
      unverifiable: "bg-yellow-100 text-yellow-700",
    };
    return (
      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${styles[verdict] || styles.unverifiable}`}>
        {verdict}
      </span>
    );
  };

  return (
    <div>
      {data?.summary && (
        <p className="text-sm text-text-secondary mb-4">{data.summary}</p>
      )}
      <div className="space-y-3">
        {claims.map((claim: any, i: number) => (
          <div key={i} className="rounded border border-border bg-surface p-4">
            <div className="flex items-start justify-between gap-3 mb-2">
              <p className="text-sm text-text-primary italic">
                &ldquo;{claim.original_claim?.quote || claim.quote || "—"}&rdquo;
              </p>
              {verdictBadge(claim.verdict)}
            </div>
            <p className="text-sm text-text-secondary">{claim.explanation}</p>
            {claim.sources && (
              <p className="text-xs text-text-tertiary mt-1">Sources: {claim.sources}</p>
            )}
          </div>
        ))}
        {claims.length === 0 && (
          <p className="text-text-tertiary text-sm">No claims found for this category.</p>
        )}
      </div>
    </div>
  );
}

function ConversationAnalysisPanel({ result }: { result?: PitchPhaseResult }) {
  if (!result || result.status === "pending") {
    return <p className="text-text-tertiary text-sm">Waiting for conversation analysis...</p>;
  }
  if (result.status === "running") {
    return <p className="text-blue-600 text-sm animate-pulse">Analyzing conversation...</p>;
  }
  if (result.status === "failed") {
    return <p className="text-red-600 text-sm">Analysis failed: {result.error}</p>;
  }

  const data = result.result as any;

  const renderSection = (title: string, section: any) => {
    if (!section) return null;
    return (
      <div className="rounded-lg border border-border bg-surface p-5 mb-4">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-medium text-text-primary">{title}</h4>
          {section.score != null && (
            <span className="text-lg font-medium text-accent">{section.score}</span>
          )}
        </div>
        <p className="text-sm text-text-secondary mb-3">{section.assessment}</p>
        {section.highlights && (
          <div className="space-y-1">
            {section.highlights.map((h: any, i: number) => (
              <p key={i} className="text-xs text-text-tertiary">
                <span className="font-mono">[{h.timestamp}]</span> {h.observation}
              </p>
            ))}
          </div>
        )}
        {section.tension_points && section.tension_points.length > 0 && (
          <div className="mt-3 space-y-1">
            <p className="text-xs font-medium text-red-600">Tension Points:</p>
            {section.tension_points.map((t: any, i: number) => (
              <p key={i} className="text-xs text-text-tertiary">
                <span className="font-mono">[{t.timestamp}]</span> {t.description}
              </p>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div>
      {renderSection("Presentation Quality", data?.presentation_quality)}
      {renderSection("Meeting Dynamics", data?.meeting_dynamics)}
      {renderSection("Strategic Read", data?.strategic_read)}
      {data?.environment_summary && (
        <div className="rounded-lg border border-border bg-surface p-5">
          <h4 className="text-sm font-medium text-text-primary mb-2">Pitch Environment</h4>
          <p className="text-sm text-text-secondary">{data.environment_summary}</p>
        </div>
      )}
    </div>
  );
}

function ScoresPanel({
  scores,
  percentiles,
  recommendations,
}: {
  scores: Record<string, number>;
  percentiles: Record<string, number>;
  recommendations: any[];
}) {
  const dimensions = [
    { key: "pitch_clarity", label: "Pitch Clarity" },
    { key: "financial_rigor", label: "Financial Rigor" },
    { key: "q_and_a_handling", label: "Q&A Handling" },
    { key: "investor_engagement", label: "Investor Engagement" },
    { key: "fact_accuracy", label: "Fact Accuracy" },
  ];

  if (Object.keys(scores).length === 0) {
    return <p className="text-text-tertiary text-sm">Scores not available yet.</p>;
  }

  return (
    <div>
      {/* Score bars */}
      <div className="rounded-lg border border-border bg-surface p-5 mb-6">
        <h4 className="text-sm font-medium text-text-primary mb-4">Dimension Scores</h4>
        <div className="space-y-3">
          {dimensions.map(({ key, label }) => {
            const score = scores[key];
            const pct = percentiles[key];
            if (score == null) return null;
            return (
              <div key={key}>
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="text-text-secondary">{label}</span>
                  <span className="font-medium text-text-primary">{score}/100</span>
                </div>
                <div className="h-2 rounded-full bg-surface-alt overflow-hidden">
                  <div
                    className="h-full rounded-full bg-accent transition-all"
                    style={{ width: `${score}%` }}
                  />
                </div>
                {pct != null && (
                  <p className="text-[10px] text-text-tertiary mt-0.5">{pct}th percentile</p>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Recommendations */}
      {recommendations.length > 0 && (
        <div className="rounded-lg border border-border bg-surface p-5">
          <h4 className="text-sm font-medium text-text-primary mb-4">Recommendations</h4>
          <div className="space-y-4">
            {recommendations.map((rec: any, i: number) => (
              <div key={i} className="flex gap-3">
                <span
                  className={`shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
                    rec.impact === "high"
                      ? "bg-red-100 text-red-700"
                      : rec.impact === "medium"
                      ? "bg-yellow-100 text-yellow-700"
                      : "bg-green-100 text-green-700"
                  }`}
                >
                  {i + 1}
                </span>
                <div>
                  <p className="text-sm font-medium text-text-primary">{rec.title}</p>
                  <p className="text-sm text-text-secondary">{rec.description}</p>
                  {rec.transcript_reference && (
                    <p className="text-xs text-text-tertiary mt-0.5 font-mono">
                      {rec.transcript_reference}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/pitch-intelligence/[id]/page.tsx
git commit -m "feat(pitch-intelligence): add session detail page — speaker labeling, progressive results, fact-check, scores"
```

---

### Task 12: Navbar Link

**Files:**
- Modify: `frontend/components/Navbar.tsx`

- [ ] **Step 1: Add Pitch Intelligence link to the navbar**

In `frontend/components/Navbar.tsx`, add a new link after the "Insights" link inside the `{session && (` block:

```tsx
<Link href="/pitch-intelligence" className="text-sm text-text-secondary hover:text-text-primary transition">
  Pitch Intel
</Link>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/Navbar.tsx
git commit -m "feat(pitch-intelligence): add Pitch Intel link to navbar"
```

---

### Task 13: Request Body Size Limit

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: No change needed**

The presigned URL upload goes directly to S3, bypassing the backend. The existing 50MB limit in `main.py` does not affect pitch intelligence uploads. No changes needed.

---

### Task 14: Docker Compose — Deepgram API Key

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add Deepgram API key environment variable**

In `docker-compose.yml`, add to the `backend` service's environment section:

```yaml
ACUTAL_DEEPGRAM_API_KEY: ${DEEPGRAM_API_KEY:-}
```

Also add the same variable to the `analysis_worker` service's environment section (since the worker runs transcription):

```yaml
ACUTAL_DEEPGRAM_API_KEY: ${DEEPGRAM_API_KEY:-}
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(pitch-intelligence): add DEEPGRAM_API_KEY to docker-compose environment"
```
