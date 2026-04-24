import asyncio
import base64
import json
import logging
import secrets
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_current_user_or_none, get_db
from app.config import settings
from app.models.analyst import (
    AnalystAttachment,
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
from app.services.document_extractor import extract_text
from app.services import s3

logger = logging.getLogger(__name__)

router = APIRouter()

FREE_MESSAGE_LIMIT = 20
SUBSCRIBER_MESSAGE_LIMIT = 100
SUBSCRIBER_WARNING_AT = 80

ALLOWED_TEXT_TYPES = {"pdf", "docx", "doc", "pptx", "ppt", "xlsx", "xls", "csv", "md", "txt"}
ALLOWED_IMAGE_TYPES = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_FILE_TYPES = ALLOWED_TEXT_TYPES | ALLOWED_IMAGE_TYPES
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB
MAX_FILES = 10
MAX_TEXT_CHARS = 100_000  # 100K character limit for context injection
IMAGE_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
}


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
        d["messages"] = []
        for m in c.messages:
            msg_dict = {
                "id": str(m.id),
                "role": m.role.value if hasattr(m.role, "value") else m.role,
                "content": m.content,
                "charts": m.charts,
                "citations": m.citations,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "attachments": [],
            }
            if hasattr(m, "attachments") and m.attachments:
                msg_dict["attachments"] = [
                    {
                        "id": str(a.id),
                        "filename": a.filename,
                        "file_type": a.file_type,
                        "file_size_bytes": a.file_size_bytes,
                        "is_image": a.is_image,
                        "s3_key": a.s3_key,
                    }
                    for a in m.attachments
                ]
            d["messages"].append(msg_dict)
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
            selectinload(AnalystConversation.messages).selectinload(AnalystMessage.attachments),
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
        .options(
            selectinload(AnalystConversation.reports),
            selectinload(AnalystConversation.messages).selectinload(AnalystMessage.attachments),
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(404, "Conversation not found")

    # Clean up S3 attachment files
    for msg in conversation.messages or []:
        for att in (msg.attachments or []):
            s3.delete_file(att.s3_key)

    # Clean up S3 report files
    for report in conversation.reports:
        if report.s3_key:
            s3.delete_file(report.s3_key)

    await db.delete(conversation)
    await db.commit()
    return {"ok": True}


# ── SSE chat ─────────────────────────────────────────────────────────

@router.post("/api/analyst/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    content: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate file count
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Maximum {MAX_FILES} files allowed")

    # Validate files
    file_data_list: list[dict] = []
    for f in files:
        ext = f.filename.rsplit(".", 1)[-1].lower() if f.filename and "." in f.filename else ""
        if ext not in ALLOWED_FILE_TYPES:
            raise HTTPException(400, f"Unsupported file type: .{ext}")
        data = await f.read()
        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(400, f"File {f.filename} exceeds 20MB limit")
        file_data_list.append({
            "filename": f.filename or "unnamed",
            "ext": ext,
            "data": data,
            "is_image": ext in ALLOWED_IMAGE_TYPES,
        })

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
        content=content,
    )
    db.add(user_msg)
    conversation.message_count = (conversation.message_count or 0) + 1

    # Update title from first message
    if conversation.message_count == 1:
        conversation.title = content[:100]

    await db.commit()
    await db.refresh(user_msg)

    # Process files: upload to S3, extract text, create attachment records
    attachment_records: list[dict] = []
    for fd in file_data_list:
        file_uuid = str(uuid.uuid4())
        s3_key = f"analyst-attachments/{conversation_id}/{user_msg.id}/{file_uuid}/{fd['filename']}"
        s3.upload_file(fd["data"], s3_key)

        extracted = None
        if not fd["is_image"]:
            extracted = extract_text(fd["data"], fd["filename"], fd["ext"])

        attachment = AnalystAttachment(
            message_id=user_msg.id,
            conversation_id=conversation.id,
            filename=fd["filename"],
            file_type=fd["ext"],
            s3_key=s3_key,
            file_size_bytes=len(fd["data"]),
            extracted_text=extracted,
            is_image=fd["is_image"],
        )
        db.add(attachment)
        attachment_records.append({
            "filename": fd["filename"],
            "ext": fd["ext"],
            "is_image": fd["is_image"],
            "extracted_text": extracted,
            "image_data": fd["data"] if fd["is_image"] else None,
        })

    if attachment_records:
        await db.commit()

    # Build message history (last 20)
    history = []
    for msg in conversation.messages[-20:]:
        role = msg.role.value if hasattr(msg.role, "value") else msg.role
        msg_content = msg.content

        # For past messages with attachments, show placeholder only
        if msg.id != user_msg.id:
            att_result = await db.execute(
                select(AnalystAttachment.filename).where(AnalystAttachment.message_id == msg.id)
            )
            att_names = att_result.scalars().all()
            if att_names:
                msg_content += "\n\n" + "\n".join(f"[Attached: {name}]" for name in att_names)

        history.append({"role": role, "content": msg_content})

    # Add current user message with full attachment content
    current_content = content
    if attachment_records:
        text_parts = []
        for att in attachment_records:
            if not att["is_image"] and att["extracted_text"]:
                text_parts.append((att["filename"], att["extracted_text"]))

        # Truncate if total text exceeds limit
        if text_parts:
            total_chars = sum(len(t) for _, t in text_parts)
            for filename, text_content in text_parts:
                if total_chars > MAX_TEXT_CHARS:
                    ratio = MAX_TEXT_CHARS / total_chars
                    truncated_len = int(len(text_content) * ratio)
                    text_content = text_content[:truncated_len] + f"\n[... truncated, {len(text_content)} characters total ...]"
                current_content += f"\n\n--- Attached: {filename} ---\n{text_content}"

    # Replace the last history entry with the enriched content
    if history and history[-1]["content"] == content:
        history[-1]["content"] = current_content
    else:
        history.append({"role": "user", "content": current_content})

    # Build image content blocks for Claude
    image_blocks: list[dict] = []
    for att in attachment_records:
        if att["is_image"] and att["image_data"]:
            media_type = IMAGE_MEDIA_TYPES.get(att["ext"], "image/png")
            b64 = base64.b64encode(att["image_data"]).decode("utf-8")
            image_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64},
            })

    # Capture IDs needed for the streaming closure
    conv_id = conversation.id

    async def event_stream():
        full_text = ""
        charts = []
        citations = []

        try:
            async for event in run_agent(history, image_blocks=image_blocks if image_blocks else None):
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

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── reports ──────────────────────────────────────────────────────────

class CreateReportBody(BaseModel):
    format: str  # "docx", "xlsx", "pdf", or "pptx"
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

    if body.format not in ("docx", "xlsx", "pdf", "pptx"):
        raise HTTPException(400, "Format must be 'docx', 'xlsx', 'pdf', or 'pptx'")

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
        .options(selectinload(AnalystReport.conversation))
    )
    reports = result.scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "conversation_id": str(r.conversation_id),
                "title": r.title,
                "conversation_title": r.conversation.title if r.conversation else r.title,
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
    media_types = {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf": "application/pdf",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    media_type = media_types.get(fmt, "application/octet-stream")
    filename = f"{report.title}.{fmt}"

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
        .options(selectinload(AnalystConversation.messages).selectinload(AnalystMessage.attachments))
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
                "attachments": [
                    {
                        "id": str(a.id),
                        "filename": a.filename,
                        "file_type": a.file_type,
                        "file_size_bytes": a.file_size_bytes,
                        "is_image": a.is_image,
                        "s3_key": a.s3_key,
                    }
                    for a in (m.attachments or [])
                ],
            }
            for m in conversation.messages
        ],
    }
