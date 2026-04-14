import asyncio
import json
import logging
import secrets
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_current_user_or_none, get_db
from app.config import settings
from app.models.analyst import (
    AnalystConversation,
    AnalystMessage,
    AnalystReport,
    MessageRole,
    ReportFormat,
    ReportGenStatus,
)
from app.models.user import SubscriptionStatus, User
from app.services.analyst_agent import run_agent
from app.services.analyst_reports import generate_report
from app.services import s3

logger = logging.getLogger(__name__)

router = APIRouter()

FREE_MESSAGE_LIMIT = 20
SUBSCRIBER_MESSAGE_LIMIT = 100
SUBSCRIBER_WARNING_AT = 80


# ── helpers ──────────────────────────────────────────────────────────

def _sub_status_value(user: User) -> str:
    s = user.subscription_status
    return s.value if hasattr(s, "value") else s


def _conversation_to_dict(c: AnalystConversation, include_messages: bool = False) -> dict:
    d = {
        "id": str(c.id),
        "title": c.title,
        "is_free_conversation": c.is_free_conversation,
        "message_count": c.message_count,
        "share_token": c.share_token,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
    if include_messages and c.messages:
        d["messages"] = [
            {
                "id": str(m.id),
                "role": m.role.value if hasattr(m.role, "value") else m.role,
                "content": m.content,
                "charts": m.charts,
                "citations": m.citations,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in c.messages
        ]
    if c.reports:
        d["reports"] = [
            {
                "id": str(r.id),
                "title": r.title,
                "format": r.format.value if hasattr(r.format, "value") else r.format,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "file_size_bytes": r.file_size_bytes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in c.reports
        ]
    return d


# ── conversation CRUD ────────────────────────────────────────────────

@router.post("/api/analyst/conversations")
async def create_conversation(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Gating: count existing conversations
    count_result = await db.execute(
        select(func.count(AnalystConversation.id)).where(
            AnalystConversation.user_id == user.id
        )
    )
    count = count_result.scalar() or 0

    if count >= 1 and _sub_status_value(user) != "active":
        raise HTTPException(
            status_code=402,
            detail="Subscribe for $19.99/mo for unlimited analyst access.",
        )

    is_free = count == 0
    conversation = AnalystConversation(
        user_id=user.id,
        is_free_conversation=is_free,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "is_free_conversation": is_free,
    }


@router.get("/api/analyst/conversations")
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystConversation)
        .where(AnalystConversation.user_id == user.id)
        .order_by(AnalystConversation.updated_at.desc())
    )
    conversations = result.scalars().all()
    return {
        "items": [
            {
                "id": str(c.id),
                "title": c.title,
                "message_count": c.message_count,
                "is_free_conversation": c.is_free_conversation,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in conversations
        ]
    }


@router.get("/api/analyst/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystConversation)
        .where(
            AnalystConversation.id == conversation_id,
            AnalystConversation.user_id == user.id,
        )
        .options(
            selectinload(AnalystConversation.messages),
            selectinload(AnalystConversation.reports),
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    return _conversation_to_dict(conversation, include_messages=True)


class UpdateConversationBody(BaseModel):
    title: str


@router.patch("/api/analyst/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: uuid.UUID,
    body: UpdateConversationBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystConversation).where(
            AnalystConversation.id == conversation_id,
            AnalystConversation.user_id == user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    conversation.title = body.title
    await db.commit()
    return {"ok": True}


@router.delete("/api/analyst/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystConversation)
        .where(
            AnalystConversation.id == conversation_id,
            AnalystConversation.user_id == user.id,
        )
        .options(selectinload(AnalystConversation.reports))
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    # Clean up S3 report files
    for report in conversation.reports:
        if report.s3_key:
            s3.delete_file(report.s3_key)

    await db.delete(conversation)
    await db.commit()
    return {"ok": True}


# ── SSE chat ─────────────────────────────────────────────────────────

class SendMessageBody(BaseModel):
    content: str


@router.post("/api/analyst/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    body: SendMessageBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Load conversation
    result = await db.execute(
        select(AnalystConversation)
        .where(
            AnalystConversation.id == conversation_id,
            AnalystConversation.user_id == user.id,
        )
        .options(selectinload(AnalystConversation.messages))
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    # Message limit check
    is_sub = _sub_status_value(user) == "active"
    limit = SUBSCRIBER_MESSAGE_LIMIT if is_sub else FREE_MESSAGE_LIMIT
    if conversation.message_count >= limit:
        raise HTTPException(
            400,
            f"Message limit reached ({limit}). {'Start a new conversation.' if is_sub else 'Subscribe for more.'}",
        )

    # Save user message
    user_msg = AnalystMessage(
        conversation_id=conversation.id,
        role=MessageRole.user.value,
        content=body.content,
    )
    db.add(user_msg)
    conversation.message_count = (conversation.message_count or 0) + 1

    # Update title from first message
    if conversation.message_count == 1:
        conversation.title = body.content[:100]

    await db.commit()

    # Build message history (last 20)
    history = []
    for msg in conversation.messages[-20:]:
        role = msg.role.value if hasattr(msg.role, "value") else msg.role
        history.append({"role": role, "content": msg.content})

    # Add the current user message (already in DB but make sure it's in history)
    if not history or history[-1]["content"] != body.content:
        history.append({"role": "user", "content": body.content})

    # Capture IDs needed for the streaming closure
    conv_id = conversation.id

    async def event_stream():
        full_text = ""
        charts = []
        citations = []

        try:
            async for event in run_agent(history):
                etype = event["type"]

                if etype == "text":
                    full_text += event["chunk"]
                    yield f"event: text\ndata: {json.dumps({'chunk': event['chunk']})}\n\n"

                elif etype == "status":
                    yield f"event: status\ndata: {json.dumps({'message': event['message']})}\n\n"

                elif etype == "charts":
                    charts.extend(event["charts"])
                    yield f"event: charts\ndata: {json.dumps({'charts': event['charts']})}\n\n"

                elif etype == "citations":
                    citations = event["citations"]
                    yield f"event: citations\ndata: {json.dumps({'citations': citations})}\n\n"

                elif etype == "done":
                    full_text = event.get("full_text", full_text)
                    charts = event.get("charts", charts)

                elif etype == "error":
                    yield f"event: error\ndata: {json.dumps({'message': event['message']})}\n\n"

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

        # Save assistant message to DB
        if full_text:
            from app.db.session import async_session
            async with async_session() as save_db:
                assistant_msg = AnalystMessage(
                    conversation_id=conv_id,
                    role=MessageRole.assistant.value,
                    content=full_text,
                    charts=charts if charts else None,
                    citations=citations if citations else None,
                )
                save_db.add(assistant_msg)

                await save_db.execute(
                    update(AnalystConversation)
                    .where(AnalystConversation.id == conv_id)
                    .values(message_count=AnalystConversation.message_count + 1)
                )
                await save_db.commit()

        # Warning at 80 messages for subscribers
        msg_count = (conversation.message_count or 0) + 1
        if is_sub and msg_count >= SUBSCRIBER_WARNING_AT:
            yield f"event: warning\ndata: {json.dumps({'message': f'{SUBSCRIBER_MESSAGE_LIMIT - msg_count} messages remaining in this conversation.'})}\n\n"

        yield f"event: done\ndata: {json.dumps({'full_text': full_text})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── reports ──────────────────────────────────────────────────────────

class CreateReportBody(BaseModel):
    format: str  # "docx" or "xlsx"
    title: str | None = None


@router.post("/api/analyst/conversations/{conversation_id}/reports")
async def create_report(
    conversation_id: uuid.UUID,
    body: CreateReportBody,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Gating: subscription required for reports
    if _sub_status_value(user) != "active":
        raise HTTPException(402, "Subscription required for report generation.")

    result = await db.execute(
        select(AnalystConversation).where(
            AnalystConversation.id == conversation_id,
            AnalystConversation.user_id == user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    if body.format not in ("docx", "xlsx"):
        raise HTTPException(400, "Format must be 'docx' or 'xlsx'")

    report = AnalystReport(
        conversation_id=conversation.id,
        user_id=user.id,
        title=body.title or conversation.title,
        format=body.format,
        status=ReportGenStatus.pending.value,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    background_tasks.add_task(generate_report, str(report.id))

    return {"id": str(report.id), "status": "pending"}


@router.get("/api/analyst/reports")
async def list_reports(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystReport)
        .where(AnalystReport.user_id == user.id)
        .order_by(AnalystReport.created_at.desc())
    )
    reports = result.scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "conversation_id": str(r.conversation_id),
                "title": r.title,
                "format": r.format.value if hasattr(r.format, "value") else r.format,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "file_size_bytes": r.file_size_bytes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reports
        ]
    }


@router.get("/api/analyst/reports/{report_id}")
async def get_report_status(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystReport).where(
            AnalystReport.id == report_id,
            AnalystReport.user_id == user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")

    return {
        "id": str(report.id),
        "status": report.status.value if hasattr(report.status, "value") else report.status,
        "file_size_bytes": report.file_size_bytes,
        "error": report.error,
    }


@router.get("/api/analyst/reports/{report_id}/download")
async def download_report(
    report_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystReport).where(
            AnalystReport.id == report_id,
            AnalystReport.user_id == user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(404, "Report not found")

    status_val = report.status.value if hasattr(report.status, "value") else report.status
    if status_val != "complete" or not report.s3_key:
        raise HTTPException(400, "Report not ready for download")

    file_data = s3.download_file(report.s3_key)
    fmt = report.format.value if hasattr(report.format, "value") else report.format
    if fmt == "docx":
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"{report.title}.docx"
    else:
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"{report.title}.xlsx"

    from fastapi.responses import Response
    return Response(
        content=file_data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── sharing ──────────────────────────────────────────────────────────

@router.post("/api/analyst/conversations/{conversation_id}/share")
async def share_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystConversation).where(
            AnalystConversation.id == conversation_id,
            AnalystConversation.user_id == user.id,
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    if not conversation.share_token:
        conversation.share_token = secrets.token_urlsafe(32)
        await db.commit()

    return {
        "share_token": conversation.share_token,
        "url": f"/insights/shared/{conversation.share_token}",
    }


@router.get("/api/analyst/shared/{share_token}")
async def get_shared_conversation(
    share_token: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AnalystConversation)
        .where(AnalystConversation.share_token == share_token)
        .options(selectinload(AnalystConversation.messages))
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Shared conversation not found")

    return {
        "title": conversation.title,
        "message_count": conversation.message_count,
        "messages": [
            {
                "id": str(m.id),
                "role": m.role.value if hasattr(m.role, "value") else m.role,
                "content": m.content,
                "charts": m.charts,
                "citations": m.citations,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in conversation.messages
        ],
    }
