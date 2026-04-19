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

    for phase in PitchAnalysisPhase:
        phase_result = PitchAnalysisResult(
            session_id=ps.id,
            phase=phase,
            status=PitchPhaseStatus.pending,
        )
        db.add(phase_result)

    await db.commit()

    return {"id": str(ps.id), "status": "analyzing"}


# ── Benchmarks (must be before /{session_id} routes) ──────────────────


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
