# Insights File Upload — Design Spec

**Date:** 2026-04-24
**Status:** Approved

## Overview

Add file upload support to the AI Analyst Chat (insights page). Users can drag-and-drop or attach files to their messages. File content is extracted and injected into the Claude conversation as context, allowing the analyst to reference and discuss the uploaded material.

## Supported File Types

**Text-extractable:** PDF, DOCX, DOC, PPTX, PPT, XLSX, XLS, CSV, MD, TXT
**Images (Claude vision):** PNG, JPG, JPEG, GIF, WebP

## Limits

- Up to 10 files per message
- 20MB per file
- Images sent as base64 vision input; text files processed through existing `document_extractor.py`

## Data Model

New table: `analyst_attachments`

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| message_id | UUID | FK to analyst_messages |
| conversation_id | UUID | FK to analyst_conversations |
| filename | VARCHAR | Original filename |
| file_type | VARCHAR | Extension (pdf, docx, png, etc.) |
| s3_key | VARCHAR | S3 storage path |
| file_size_bytes | INTEGER | File size |
| extracted_text | TEXT | Extracted text (null for images) |
| is_image | BOOLEAN | Whether to send as vision input |
| created_at | TIMESTAMP | |

S3 key pattern: `analyst-attachments/{conversation_id}/{message_id}/{uuid}/{filename}`

## Backend API Changes

**Modified endpoint:** `POST /api/analyst/conversations/{conversation_id}/messages`

Changes from JSON body to **multipart/form-data**:
- `content` — user's message text (required)
- `files` — up to 10 files, 20MB each (optional)

### Processing Flow

1. Validate files (type, size, count)
2. Upload files to S3
3. Extract text from documents / read image bytes
4. Create `analyst_attachments` records linked to the user message
5. Build Claude messages:
   - Text files: append extracted text to user message as `\n\n--- Attached: {filename} ---\n{extracted_text}`
   - Images: add as image content blocks in the Claude API call (`{"type": "image", "source": {"type": "base64", "media_type": "...", "data": "..."}}`)
6. Stream response via SSE as usual

No new endpoints needed.

## Context Window Management

- If total extracted text exceeds 100K characters, truncate each file proportionally with a note: `[... truncated, {X} characters total ...]`
- When loading conversation history (last 20 messages), past attachments are NOT re-injected as full text — shown as `[Attached: filename.pdf]` placeholders only. Only the current message's attachments get full content injection. This prevents context window bloat.

## Frontend Changes

### Insights page (`frontend/app/insights/page.tsx`)

- Change message submission from JSON `fetch` to `FormData` with files attached
- Track `attachedFiles` state array (cleared after send)

### Chat input area — file attachment UI

- **Drop zone:** drag-and-drop overlay on the chat area, shows "Drop files here" on dragover
- **Attach button:** paperclip/attach icon next to the send button, opens file picker
- **File preview bar:** above the input, shows attached file names with remove (x) buttons, file type icons, and file size
- **Validation:** client-side checks on type and size before attaching, toast on rejection

### Message display (`AnalystChat.tsx`)

- User messages with attachments show file badges (filename + type icon) below the message text
- For images, show a thumbnail preview in the message bubble
- Attachment metadata included in the message API response (attachments array)

### No changes to sidebar or reports.

## Existing Code Reuse

- `backend/app/services/document_extractor.py` — text extraction for all document types
- `backend/app/services/s3.py` — S3 upload/download operations
- `backend/app/api/analyze.py` — file validation patterns (type checking, size limits)
