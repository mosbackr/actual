# Insights File Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add file upload (drag-and-drop + attach button) to the AI Analyst Chat so users can share documents and images for the analyst to reference.

**Architecture:** Server-side multipart upload. Files go to S3, text is extracted via existing `document_extractor.py`, images are sent to Claude as base64 vision blocks. Attachments are stored in a new `analyst_attachments` table linked to messages.

**Tech Stack:** FastAPI (multipart), SQLAlchemy, S3 (boto3), Claude vision API, React (drag-and-drop), Next.js

---

### Task 1: Database Migration — `analyst_attachments` Table

**Files:**
- Create: `backend/alembic/versions/z5a6b7c8d9e0_add_analyst_attachments_table.py`

- [ ] **Step 1: Create migration file**

```python
"""Add analyst_attachments table

Revision ID: z5a6b7c8d9e0
Revises: y4z5a6b7c8d9
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "z5a6b7c8d9e0"
down_revision = "y4z5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analyst_attachments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("message_id", UUID(as_uuid=True), sa.ForeignKey("analyst_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", UUID(as_uuid=True), sa.ForeignKey("analyst_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("s3_key", sa.String(1000), nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False),
        sa.Column("extracted_text", sa.Text, nullable=True),
        sa.Column("is_image", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_analyst_attachments_message_id", "analyst_attachments", ["message_id"])
    op.create_index("ix_analyst_attachments_conversation_id", "analyst_attachments", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("analyst_attachments")
```

- [ ] **Step 2: Commit**

```bash
git add backend/alembic/versions/z5a6b7c8d9e0_add_analyst_attachments_table.py
git commit -m "feat(insights-upload): add analyst_attachments migration"
```

---

### Task 2: SQLAlchemy Model — `AnalystAttachment`

**Files:**
- Modify: `backend/app/models/analyst.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Add AnalystAttachment model to analyst.py**

Add at the end of `backend/app/models/analyst.py`:

```python
class AnalystAttachment(Base):
    __tablename__ = "analyst_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4)
    message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("analyst_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("analyst_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename = Column(String(500), nullable=False)
    file_type = Column(String(20), nullable=False)
    s3_key = Column(String(1000), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    extracted_text = Column(Text, nullable=True)
    is_image = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship("AnalystMessage", back_populates="attachments")
```

- [ ] **Step 2: Add attachments relationship to AnalystMessage**

In the existing `AnalystMessage` class in `backend/app/models/analyst.py`, add after the `conversation` relationship (line 79):

```python
    attachments = relationship(
        "AnalystAttachment",
        back_populates="message",
        cascade="all, delete-orphan",
    )
```

- [ ] **Step 3: Add import to `__init__.py`**

In `backend/app/models/__init__.py`, add the import:

```python
from app.models.analyst import AnalystAttachment
```

And add `"AnalystAttachment"` to the `__all__` list.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/analyst.py backend/app/models/__init__.py
git commit -m "feat(insights-upload): add AnalystAttachment model"
```

---

### Task 3: Backend — Modify Message Endpoint to Accept Files

**Files:**
- Modify: `backend/app/api/analyst.py`

- [ ] **Step 1: Add imports**

At the top of `backend/app/api/analyst.py`, add these imports:

```python
import base64
from fastapi import File, Form, UploadFile
from app.models.analyst import AnalystAttachment
from app.services.document_extractor import extract_text
```

- [ ] **Step 2: Add file validation constants**

After the existing `SUBSCRIBER_WARNING_AT = 80` line (line 35), add:

```python
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
```

- [ ] **Step 3: Replace the send_message endpoint**

Replace the `SendMessageBody` class and `send_message` function (lines 224-353) with:

```python
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
            # Check if this message has attachments by querying
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
            for filename, text in text_parts:
                if total_chars > MAX_TEXT_CHARS:
                    ratio = MAX_TEXT_CHARS / total_chars
                    truncated_len = int(len(text) * ratio)
                    text = text[:truncated_len] + f"\n[... truncated, {len(text)} characters total ...]"
                current_content += f"\n\n--- Attached: {filename} ---\n{text}"

    # Replace the last history entry (or add it) with the enriched content
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
```

- [ ] **Step 4: Add attachments to conversation detail response**

In the `_conversation_to_dict` helper (line 45), update the message serialization to include attachments. Replace the messages list comprehension:

```python
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
```

- [ ] **Step 5: Eagerly load attachments in get_conversation**

In the `get_conversation` endpoint (line 144), add `selectinload` for attachments. Update the `.options()` call:

```python
        .options(
            selectinload(AnalystConversation.messages).selectinload(AnalystMessage.attachments),
            selectinload(AnalystConversation.reports),
        )
```

Also add `AnalystMessage` to the imports from `app.models.analyst` at line 16.

- [ ] **Step 6: Clean up S3 attachments on conversation delete**

In the `delete_conversation` endpoint (line 194), add attachment cleanup. After loading the conversation, also load messages with attachments. Add before the `for report in conversation.reports` loop:

```python
    # Clean up S3 attachment files
    for msg in conversation.messages if hasattr(conversation, 'messages') and conversation.messages else []:
        if hasattr(msg, 'attachments') and msg.attachments:
            for att in msg.attachments:
                s3.delete_file(att.s3_key)
```

And update the query to also load messages + attachments:

```python
        .options(
            selectinload(AnalystConversation.reports),
            selectinload(AnalystConversation.messages).selectinload(AnalystMessage.attachments),
        )
```

- [ ] **Step 7: Remove the now-unused SendMessageBody class**

Delete the `SendMessageBody` class (was at line 224-225) since we now use `Form` parameters.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/analyst.py
git commit -m "feat(insights-upload): accept file uploads in message endpoint"
```

---

### Task 4: Backend — Add Image Block Support to Agent

**Files:**
- Modify: `backend/app/services/analyst_agent.py`

- [ ] **Step 1: Update run_agent signature and message building**

Modify the `run_agent` function signature (line 251) to accept image blocks:

```python
async def run_agent(
    messages: list[dict],
    system_prompt: str | None = None,
    image_blocks: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
```

- [ ] **Step 2: Update message conversion to handle image blocks**

Replace the `api_messages` conversion (line 273) with:

```python
    # Convert to Claude message format
    api_messages = []
    for i, m in enumerate(messages):
        # For the last user message, inject image blocks if present
        if i == len(messages) - 1 and m["role"] == "user" and image_blocks:
            content_blocks = [{"type": "text", "text": m["content"]}]
            content_blocks.extend(image_blocks)
            api_messages.append({"role": "user", "content": content_blocks})
        else:
            api_messages.append({"role": m["role"], "content": m["content"]})
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/analyst_agent.py
git commit -m "feat(insights-upload): add image block support to analyst agent"
```

---

### Task 5: Frontend Types — Add Attachment Types

**Files:**
- Modify: `frontend/lib/types.ts`

- [ ] **Step 1: Add AnalystAttachment interface**

After the `AnalystCitation` interface (line 245), add:

```typescript
export interface AnalystAttachment {
  id: string;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  is_image: boolean;
  s3_key: string;
}
```

- [ ] **Step 2: Add attachments to AnalystMessageData**

Update the `AnalystMessageData` interface (line 222) to include attachments:

```typescript
export interface AnalystMessageData {
  id: string;
  role: "user" | "assistant";
  content: string;
  charts: AnalystChartConfig[] | null;
  citations: AnalystCitation[] | null;
  attachments?: AnalystAttachment[];
  created_at: string | null;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts
git commit -m "feat(insights-upload): add attachment types"
```

---

### Task 6: Frontend API — Update streamMessage to Send FormData

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Update streamMessage method**

Replace the `streamMessage` method (lines 217-227) with:

```typescript
  streamMessage(token: string, conversationId: string, content: string, files?: File[]) {
    const url = `${API_URL}/api/analyst/conversations/${conversationId}/messages`;
    const formData = new FormData();
    formData.append("content", content);
    if (files) {
      for (const file of files) {
        formData.append("files", file);
      }
    }
    return fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
    });
  },
```

Note: Remove `Content-Type` header — browser sets it automatically with the multipart boundary.

- [ ] **Step 2: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(insights-upload): update streamMessage to use FormData"
```

---

### Task 7: Frontend — Update AnalystInput with File Attach Button and Preview

**Files:**
- Modify: `frontend/components/analyst/AnalystInput.tsx`

- [ ] **Step 1: Rewrite AnalystInput with file support**

Replace the entire file content:

```tsx
"use client";

import { useRef, useState } from "react";

const ALLOWED_EXTENSIONS = new Set([
  "pdf", "docx", "doc", "pptx", "ppt", "xlsx", "xls", "csv", "md", "txt",
  "png", "jpg", "jpeg", "gif", "webp",
]);
const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB
const MAX_FILES = 10;

interface Props {
  onSend: (message: string, files?: File[]) => void;
  onGenerateReport: (format: "docx" | "xlsx" | "pdf" | "pptx") => void;
  isStreaming: boolean;
  hasMessages: boolean;
  isSubscriber: boolean;
}

function getFileExt(name: string): string {
  return name.rsplit ? name.split(".").pop()?.toLowerCase() || "" : name.split(".").pop()?.toLowerCase() || "";
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

export function AnalystInput({ onSend, onGenerateReport, isStreaming, hasMessages, isSubscriber }: Props) {
  const [input, setInput] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const [showReportMenu, setShowReportMenu] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateAndAddFiles = (newFiles: FileList | File[]) => {
    setFileError(null);
    const filesToAdd: File[] = [];

    for (const file of Array.from(newFiles)) {
      const ext = file.name.split(".").pop()?.toLowerCase() || "";
      if (!ALLOWED_EXTENSIONS.has(ext)) {
        setFileError(`Unsupported file type: .${ext}`);
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        setFileError(`${file.name} exceeds 20MB limit`);
        return;
      }
      filesToAdd.push(file);
    }

    const total = attachedFiles.length + filesToAdd.length;
    if (total > MAX_FILES) {
      setFileError(`Maximum ${MAX_FILES} files allowed`);
      return;
    }

    setAttachedFiles((prev) => [...prev, ...filesToAdd]);
  };

  const removeFile = (index: number) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
    setFileError(null);
  };

  const handleSubmit = () => {
    const trimmed = input.trim();
    if ((!trimmed && attachedFiles.length === 0) || isStreaming) return;
    onSend(trimmed || "Please analyze the attached files.", attachedFiles.length > 0 ? attachedFiles : undefined);
    setInput("");
    setAttachedFiles([]);
    setFileError(null);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 150) + "px";
  };

  const fileTypeIcon = (name: string) => {
    const ext = name.split(".").pop()?.toLowerCase() || "";
    const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "gif", "webp"]);
    if (IMAGE_EXTS.has(ext)) return "\u{1F5BC}";
    if (ext === "pdf") return "\u{1F4C4}";
    if (["docx", "doc"].includes(ext)) return "\u{1F4DD}";
    if (["pptx", "ppt"].includes(ext)) return "\u{1F4CA}";
    if (["xlsx", "xls", "csv"].includes(ext)) return "\u{1F4CA}";
    return "\u{1F4CE}";
  };

  return (
    <div className="border-t border-border bg-surface px-4 py-3">
      {/* File preview bar */}
      {attachedFiles.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {attachedFiles.map((file, i) => (
            <div
              key={`${file.name}-${i}`}
              className="flex items-center gap-1.5 bg-background border border-border rounded px-2 py-1 text-xs"
            >
              <span>{fileTypeIcon(file.name)}</span>
              <span className="text-text-primary truncate max-w-[150px]">{file.name}</span>
              <span className="text-text-tertiary">({formatSize(file.size)})</span>
              <button
                onClick={() => removeFile(i)}
                className="text-text-tertiary hover:text-score-low ml-1"
              >
                x
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Error message */}
      {fileError && (
        <p className="text-xs text-score-low mb-2">{fileError}</p>
      )}

      <div className="flex items-end gap-2">
        {/* Attach button */}
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isStreaming}
          className="px-2 py-2 text-text-tertiary hover:text-text-primary disabled:opacity-50 transition"
          title="Attach files"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
          </svg>
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls,.csv,.md,.txt,.png,.jpg,.jpeg,.gif,.webp"
          className="hidden"
          onChange={(e) => {
            if (e.target.files) validateAndAddFiles(e.target.files);
            e.target.value = "";
          }}
        />

        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder="Ask about your portfolio, market trends, competitor analysis..."
          rows={1}
          disabled={isStreaming}
          className="flex-1 resize-none rounded border border-border bg-background px-3 py-2 text-sm text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent disabled:opacity-50"
        />

        <button
          onClick={handleSubmit}
          disabled={(!input.trim() && attachedFiles.length === 0) || isStreaming}
          className="px-4 py-2 text-sm rounded bg-accent text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition"
        >
          {isStreaming ? "..." : "Send"}
        </button>

        {hasMessages && (
          <div className="relative">
            <button
              onClick={() => setShowReportMenu(!showReportMenu)}
              disabled={isStreaming}
              className="px-3 py-2 text-xs rounded border border-border text-text-secondary hover:text-text-primary hover:border-accent/50 disabled:opacity-50 transition whitespace-nowrap"
              title={isSubscriber ? "Generate report" : "Subscribe to generate reports"}
            >
              Report
            </button>
            {showReportMenu && (
              <div className="absolute bottom-full right-0 mb-1 bg-surface border border-border rounded shadow-lg py-1 z-10">
                <button
                  onClick={() => { onGenerateReport("pdf"); setShowReportMenu(false); }}
                  className="block w-full text-left px-4 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-alt"
                >
                  PDF (.pdf)
                </button>
                <button
                  onClick={() => { onGenerateReport("docx"); setShowReportMenu(false); }}
                  className="block w-full text-left px-4 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-alt"
                >
                  Word (.docx)
                </button>
                <button
                  onClick={() => { onGenerateReport("pptx"); setShowReportMenu(false); }}
                  className="block w-full text-left px-4 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-alt"
                >
                  PowerPoint (.pptx)
                </button>
                <button
                  onClick={() => { onGenerateReport("xlsx"); setShowReportMenu(false); }}
                  className="block w-full text-left px-4 py-1.5 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-alt"
                >
                  Excel (.xlsx)
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/analyst/AnalystInput.tsx
git commit -m "feat(insights-upload): add file attach button and preview to input"
```

---

### Task 8: Frontend — Add Drag-and-Drop to Chat Area

**Files:**
- Modify: `frontend/app/insights/page.tsx`

- [ ] **Step 1: Add file state and drop zone logic**

In `InsightsContent` (line 28), add state for attached files and drag state:

```typescript
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
```

- [ ] **Step 2: Add drag event handlers**

After the state declarations, add:

```typescript
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    // Only set false if leaving the container (not entering a child)
    if (e.currentTarget === e.target) {
      setIsDragging(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) {
      setAttachedFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)]);
    }
  };
```

- [ ] **Step 3: Update sendMessage to accept files**

Change the `sendMessage` function signature (line 135) to accept files:

```typescript
  const sendMessage = async (content: string, overrideConvId?: string, files?: File[]) => {
```

Update the `api.streamMessage` call (line 170) to pass files:

```typescript
      const response = await api.streamMessage(token, targetConvId, content, files);
```

- [ ] **Step 4: Update the chat container div to handle drag events**

Wrap the main content area (`flex-1 flex flex-col min-w-0` div, line 327) with drag handlers:

```tsx
      <div
        className="flex-1 flex flex-col min-w-0 relative"
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Drag overlay */}
        {isDragging && (
          <div className="absolute inset-0 z-50 bg-accent/5 border-2 border-dashed border-accent rounded-lg flex items-center justify-center">
            <p className="text-accent font-medium text-sm">Drop files here</p>
          </div>
        )}
```

- [ ] **Step 5: Update AnalystInput usage**

Update the `<AnalystInput>` component (line 369) to pass files and receive the updated onSend:

```tsx
        <AnalystInput
          onSend={(msg, files) => {
            sendMessage(msg, undefined, files);
            setAttachedFiles([]);
          }}
          onGenerateReport={handleGenerateReport}
          isStreaming={isStreaming}
          hasMessages={messages.length > 0}
          isSubscriber={true}
          externalFiles={attachedFiles}
          onClearExternalFiles={() => setAttachedFiles([])}
        />
```

- [ ] **Step 6: Update AnalystInput Props to accept external files**

In `frontend/components/analyst/AnalystInput.tsx`, add to the Props interface:

```typescript
  externalFiles?: File[];
  onClearExternalFiles?: () => void;
```

Add a useEffect to merge external files (drag-dropped) into the local attachedFiles state:

```typescript
  // Merge externally dropped files
  useEffect(() => {
    if (externalFiles && externalFiles.length > 0) {
      validateAndAddFiles(externalFiles);
      onClearExternalFiles?.();
    }
  }, [externalFiles]);
```

Add the `import { useRef, useState, useEffect } from "react";` at the top (add `useEffect`).

- [ ] **Step 7: Commit**

```bash
git add frontend/app/insights/page.tsx frontend/components/analyst/AnalystInput.tsx
git commit -m "feat(insights-upload): add drag-and-drop file upload to chat"
```

---

### Task 9: Frontend — Show Attachment Badges on Messages

**Files:**
- Modify: `frontend/components/analyst/AnalystMessage.tsx`

- [ ] **Step 1: Add attachment display to AnalystMessage**

Update the Props interface to include attachments:

```typescript
import type { AnalystChartConfig, AnalystCitation, AnalystAttachment } from "@/lib/types";

interface Props {
  role: "user" | "assistant";
  content: string;
  charts?: AnalystChartConfig[] | null;
  citations?: AnalystCitation[] | null;
  attachments?: AnalystAttachment[];
  isStreaming?: boolean;
}
```

Update the function signature:

```typescript
export function AnalystMessage({ role, content, charts, citations, attachments, isStreaming }: Props) {
```

Add attachment badges after the user message text and before charts. Insert after the closing of the user/assistant content conditional (after line 68, before the `{/* Charts */}` comment):

```tsx
        {/* Attachments */}
        {attachments && attachments.length > 0 && (
          <div className={`flex flex-wrap gap-1.5 mt-2 ${isUser ? "" : "border-t border-border/30 pt-2"}`}>
            {attachments.map((att) => (
              <span
                key={att.id}
                className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded ${
                  isUser
                    ? "bg-white/15 text-white/90"
                    : "bg-background border border-border text-text-secondary"
                }`}
              >
                {att.is_image ? "\u{1F5BC}" : "\u{1F4CE}"} {att.filename}
                <span className="opacity-60">
                  ({att.file_size_bytes < 1024 * 1024
                    ? `${(att.file_size_bytes / 1024).toFixed(0)}KB`
                    : `${(att.file_size_bytes / (1024 * 1024)).toFixed(1)}MB`})
                </span>
              </span>
            ))}
          </div>
        )}
```

- [ ] **Step 2: Update AnalystChat to pass attachments**

In `frontend/components/analyst/AnalystChat.tsx`, update the `AnalystMessage` usage (line 45-51) to pass attachments:

```tsx
        <AnalystMessage
          key={msg.id}
          role={msg.role}
          content={msg.content}
          charts={msg.charts}
          citations={msg.citations}
          attachments={msg.attachments}
        />
```

- [ ] **Step 3: Update optimistic user message in insights page**

In `frontend/app/insights/page.tsx`, update the optimistic user message creation in `sendMessage` to include attachments for display. After creating `userMsg` (around line 156), add attachment info:

```typescript
    const userMsg: AnalystMessageData = {
      id: `temp-${Date.now()}`,
      role: "user",
      content,
      charts: null,
      citations: null,
      attachments: files?.map((f, i) => ({
        id: `temp-att-${i}`,
        filename: f.name,
        file_type: f.name.split(".").pop()?.toLowerCase() || "",
        file_size_bytes: f.size,
        is_image: ["png", "jpg", "jpeg", "gif", "webp"].includes(f.name.split(".").pop()?.toLowerCase() || ""),
        s3_key: "",
      })),
      created_at: new Date().toISOString(),
    };
```

- [ ] **Step 4: Commit**

```bash
git add frontend/components/analyst/AnalystMessage.tsx frontend/components/analyst/AnalystChat.tsx frontend/app/insights/page.tsx
git commit -m "feat(insights-upload): display attachment badges on messages"
```

---

### Task 10: Deploy and Run Migration

**Files:** None (deployment only)

- [ ] **Step 1: Commit any remaining changes**

```bash
git add -A
git commit -m "feat(insights-upload): complete file upload for analyst chat"
git push origin main
```

- [ ] **Step 2: Rsync to production**

```bash
rsync -avz \
  --exclude=node_modules --exclude=.git --exclude=__pycache__ \
  --exclude=.next --exclude=.worktrees --exclude=.superpowers \
  --exclude=infra/cdk.out --exclude=.env \
  -e "ssh -i ~/.ssh/deepthesis-deploy.pem" \
  /Users/leemosbacker/acutal/ ec2-user@3.212.120.144:~/acutal/
```

- [ ] **Step 3: Run migration**

```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "cd ~/acutal && docker compose -f docker-compose.prod.yml exec backend alembic upgrade head"
```

- [ ] **Step 4: Rebuild and restart services**

```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "cd ~/acutal && docker compose -f docker-compose.prod.yml up -d --build backend frontend"
```

- [ ] **Step 5: Verify**

Open `https://www.deepthesis.org/insights`, start a conversation, attach a PDF, send a message. Confirm:
- File badge appears on the user message
- Analyst response references the file content
- Drop zone overlay appears on drag-over
