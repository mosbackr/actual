import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.feedback import FeedbackSession
from app.models.user import User
from app.services.feedback_agent import stream_feedback_response, summarize_feedback

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateSessionRequest(BaseModel):
    page_url: str | None = None


class SendMessageRequest(BaseModel):
    content: str


@router.post("/api/feedback/sessions")
async def create_session(
    body: CreateSessionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = FeedbackSession(
        user_id=user.id,
        status="active",
        page_url=body.page_url,
        transcript=[],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return {"id": str(session.id), "status": "active"}


@router.post("/api/feedback/sessions/{session_id}/messages")
async def send_message(
    session_id: uuid.UUID,
    body: SendMessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FeedbackSession).where(
            FeedbackSession.id == session_id,
            FeedbackSession.user_id == user.id,
        )
    )
    fs = result.scalar_one_or_none()
    if fs is None:
        raise HTTPException(status_code=404, detail="Feedback session not found")
    if fs.status != "active":
        raise HTTPException(status_code=400, detail="Feedback session is not active")

    # Append user message to transcript
    transcript = list(fs.transcript or [])
    transcript.append({
        "role": "user",
        "content": body.content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    fs.transcript = transcript
    await db.commit()

    # Capture for streaming closure
    fs_id = fs.id
    # Build messages for Claude (strip timestamps)
    messages = [{"role": m["role"], "content": m["content"]} for m in transcript]

    async def event_stream():
        full_text = ""
        try:
            async for event in stream_feedback_response(messages):
                etype = event["type"]
                if etype == "text":
                    full_text += event["chunk"]
                    yield f"event: text\ndata: {json.dumps({'chunk': event['chunk']})}\n\n"
                elif etype == "error":
                    yield f"event: error\ndata: {json.dumps({'message': event['message']})}\n\n"
                elif etype == "done":
                    full_text = event.get("full_text", full_text)
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

        # Save assistant message to transcript
        if full_text:
            from app.db.session import async_session
            async with async_session() as save_db:
                save_result = await save_db.execute(
                    select(FeedbackSession).where(FeedbackSession.id == fs_id)
                )
                save_fs = save_result.scalar_one_or_none()
                if save_fs:
                    updated_transcript = list(save_fs.transcript or [])
                    updated_transcript.append({
                        "role": "assistant",
                        "content": full_text,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    save_fs.transcript = updated_transcript
                    await save_db.commit()

        yield f"event: done\ndata: {json.dumps({'full_text': full_text})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.patch("/api/feedback/sessions/{session_id}/complete")
async def complete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FeedbackSession).where(
            FeedbackSession.id == session_id,
            FeedbackSession.user_id == user.id,
        )
    )
    fs = result.scalar_one_or_none()
    if fs is None:
        raise HTTPException(status_code=404, detail="Feedback session not found")

    transcript = list(fs.transcript or [])
    if len(transcript) < 2:
        # Too short to summarize — just mark complete
        fs.status = "complete"
        fs.summary = transcript[0]["content"] if transcript else "No content"
        fs.category = "general"
        fs.severity = "medium"
        fs.area = "general"
        fs.recommendations = []
        await db.commit()
        return {"id": str(fs.id), "status": "complete"}

    # Summarize with Claude
    summary_data = await summarize_feedback(transcript)

    fs.status = "complete"
    fs.summary = summary_data.get("summary", "")
    fs.category = summary_data.get("category", "general")
    fs.severity = summary_data.get("severity", "medium")
    fs.area = summary_data.get("area", "general")
    fs.recommendations = summary_data.get("recommendations", [])
    await db.commit()

    return {"id": str(fs.id), "status": "complete"}


@router.patch("/api/feedback/sessions/{session_id}/abandon")
async def abandon_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FeedbackSession).where(
            FeedbackSession.id == session_id,
            FeedbackSession.user_id == user.id,
        )
    )
    fs = result.scalar_one_or_none()
    if fs is None:
        raise HTTPException(status_code=404, detail="Feedback session not found")

    fs.status = "abandoned"
    await db.commit()

    return {"id": str(fs.id), "status": "abandoned"}
