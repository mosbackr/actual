# Video URL Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to paste a YouTube or Loom URL in pitch intelligence and have the system download the audio, store it in S3, and transcribe it through the existing Deepgram pipeline.

**Architecture:** A new `POST /api/pitch-intelligence/video-url` endpoint creates a session with `downloading` status. The pitch worker polls for downloading sessions, uses `yt-dlp` to extract audio, uploads to S3, then transitions to `transcribing` for the existing pipeline. Frontend adds a "Video Link" tab and handles the new `downloading` status.

**Tech Stack:** yt-dlp (video download), ffmpeg (audio extraction), Deepgram (transcription), S3 (storage), FastAPI, Next.js

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/pyproject.toml` | Modify | Add `yt-dlp` dependency |
| `backend/Dockerfile` | Modify | Install `ffmpeg` via apt |
| `backend/app/models/pitch_session.py` | Modify | Add `downloading` enum value, `video_url` column |
| `backend/alembic/versions/f7g8h9i0j1k2_add_video_url_and_downloading.py` | Create | Migration for new column + enum value |
| `backend/app/services/video_downloader.py` | Create | yt-dlp download + S3 upload |
| `backend/app/api/pitch_intelligence.py` | Modify | Add `/video-url` endpoint |
| `backend/app/services/pitch_worker.py` | Modify | Add downloading poll check |
| `frontend/lib/api.ts` | Modify | Add `submitVideoUrl` method |
| `frontend/app/pitch-intelligence/page.tsx` | Modify | Add "Video Link" tab UI |
| `frontend/app/pitch-intelligence/[id]/page.tsx` | Modify | Handle `downloading` status in polling + display |

---

### Task 1: Add yt-dlp Dependency and ffmpeg to Docker

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/Dockerfile`

- [ ] **Step 1: Add yt-dlp to pyproject.toml**

In `backend/pyproject.toml`, add `"yt-dlp>=2024.0.0"` to the `dependencies` list after `"jinja2>=3.1.0"`:

```toml
    "jinja2>=3.1.0",
    "yt-dlp>=2024.0.0",
]
```

- [ ] **Step 2: Add ffmpeg to Dockerfile**

In `backend/Dockerfile`, add an `apt-get install` line before the `pip install` step. The file should become:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --no-cache-dir .
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml backend/Dockerfile
git commit -m "feat(video-url): add yt-dlp dependency and ffmpeg to Docker image"
```

---

### Task 2: Add `downloading` Status and `video_url` Column to Model

**Files:**
- Modify: `backend/app/models/pitch_session.py`
- Create: `backend/alembic/versions/f7g8h9i0j1k2_add_video_url_and_downloading.py`

- [ ] **Step 1: Add `downloading` to PitchSessionStatus enum**

In `backend/app/models/pitch_session.py`, add `downloading` as the first value in `PitchSessionStatus`:

```python
class PitchSessionStatus(str, enum.Enum):
    downloading = "downloading"
    uploading = "uploading"
    transcribing = "transcribing"
    labeling = "labeling"
    analyzing = "analyzing"
    complete = "complete"
    failed = "failed"
```

- [ ] **Step 2: Add `video_url` column to PitchSession**

In `backend/app/models/pitch_session.py`, add the `video_url` column after `file_url`:

```python
    file_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    file_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

- [ ] **Step 3: Create Alembic migration**

Create `backend/alembic/versions/f7g8h9i0j1k2_add_video_url_and_downloading.py`:

```python
"""Add video_url column and downloading status

Revision ID: f7g8h9i0j1k2
Revises: e6f7g8h9i0j1
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa

revision = "f7g8h9i0j1k2"
down_revision = "e6f7g8h9i0j1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add video_url column
    op.add_column("pitch_sessions", sa.Column("video_url", sa.String(2000), nullable=True))

    # Add 'downloading' to the pitchsessionstatus enum
    op.execute("ALTER TYPE pitchsessionstatus ADD VALUE IF NOT EXISTS 'downloading' BEFORE 'uploading'")


def downgrade() -> None:
    op.drop_column("pitch_sessions", "video_url")
    # Note: PostgreSQL does not support removing enum values
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/pitch_session.py backend/alembic/versions/f7g8h9i0j1k2_add_video_url_and_downloading.py
git commit -m "feat(video-url): add downloading status and video_url column to PitchSession"
```

---

### Task 3: Create Video Downloader Service

**Files:**
- Create: `backend/app/services/video_downloader.py`

- [ ] **Step 1: Create the video downloader service**

Create `backend/app/services/video_downloader.py`:

```python
import logging
import os
import tempfile
import uuid

from sqlalchemy import select

from app.config import settings
from app.db.session import async_session
from app.models.pitch_session import PitchSession, PitchSessionStatus
from app.services import s3

logger = logging.getLogger(__name__)

MAX_DURATION_SECONDS = 7200  # 2 hours


def _validate_url(url: str) -> bool:
    """Check that URL is a supported YouTube or Loom link."""
    lower = url.lower().strip()
    return any(
        domain in lower
        for domain in ("youtube.com/", "youtu.be/", "loom.com/")
    )


def _extract_audio(url: str, output_path: str) -> dict:
    """
    Use yt-dlp to probe duration then download audio-only.
    Returns metadata dict with 'duration' and 'title'.
    Raises RuntimeError on failure.
    """
    import yt_dlp

    # Phase 1: Probe metadata (no download) to check duration
    probe_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(probe_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except Exception as e:
            raise RuntimeError(f"Could not access video: {e}")

    if not info:
        raise RuntimeError("Could not access video. It may be private or deleted.")

    duration = info.get("duration") or 0
    if duration > MAX_DURATION_SECONDS:
        raise RuntimeError(
            f"Video is {duration // 60} minutes long, which exceeds the 2 hour limit."
        )

    video_title = info.get("title", "")

    # Phase 2: Download audio only
    download_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": output_path,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(download_opts) as ydl:
        try:
            ydl.download([url])
        except Exception as e:
            raise RuntimeError(f"Failed to download video: {e}")

    return {"duration": duration, "title": video_title}


async def download_video(session_id: uuid.UUID) -> None:
    """Download video audio from URL, upload to S3, transition to transcribing."""
    logger.info("[pitch-%s] Starting video download", session_id)

    async with async_session() as db:
        result = await db.execute(
            select(PitchSession).where(PitchSession.id == session_id)
        )
        ps = result.scalar_one_or_none()
        if not ps or not ps.video_url:
            logger.error("[pitch-%s] Session not found or no video_url", session_id)
            return
        video_url = ps.video_url
        session_title = ps.title

    tmp_dir = tempfile.mkdtemp()
    # yt-dlp may append .m4a to the output path
    output_base = os.path.join(tmp_dir, "audio")
    try:
        metadata = _extract_audio(video_url, output_base)

        # Find the actual output file (yt-dlp may add extension)
        actual_file = None
        for f in os.listdir(tmp_dir):
            if f.startswith("audio"):
                actual_file = os.path.join(tmp_dir, f)
                break

        if not actual_file or not os.path.exists(actual_file):
            raise RuntimeError("Audio extraction produced no output file.")

        # Determine extension
        ext = os.path.splitext(actual_file)[1] or ".m4a"
        s3_key = f"pitch-intelligence/{session_id}/audio{ext}"

        # Upload to S3
        with open(actual_file, "rb") as fh:
            file_bytes = fh.read()

        s3.upload_file(s3_key, file_bytes, content_type="audio/mp4")
        logger.info("[pitch-%s] Uploaded audio to S3: %s (%d bytes)", session_id, s3_key, len(file_bytes))

        # Update session
        async with async_session() as db:
            result = await db.execute(
                select(PitchSession).where(PitchSession.id == session_id)
            )
            ps = result.scalar_one()
            ps.file_url = s3_key
            ps.status = PitchSessionStatus.transcribing
            # Use video title as session title if user didn't provide one
            if not session_title and metadata.get("title"):
                ps.title = metadata["title"][:500]
            await db.commit()

        logger.info("[pitch-%s] Video download complete, transitioning to transcribing", session_id)

    except RuntimeError as e:
        logger.error("[pitch-%s] Video download failed: %s", session_id, e)
        async with async_session() as db:
            result = await db.execute(
                select(PitchSession).where(PitchSession.id == session_id)
            )
            ps = result.scalar_one()
            ps.status = PitchSessionStatus.failed
            ps.error = str(e)
            await db.commit()

    except Exception as e:
        logger.error("[pitch-%s] Unexpected error during video download: %s", session_id, e, exc_info=True)
        async with async_session() as db:
            result = await db.execute(
                select(PitchSession).where(PitchSession.id == session_id)
            )
            ps = result.scalar_one()
            ps.status = PitchSessionStatus.failed
            ps.error = f"Failed to download video. Please check the URL and try again."
            await db.commit()

    finally:
        # Clean up temp files
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
```

- [ ] **Step 2: Check if s3.upload_file exists, or if we need to add it**

The existing `s3.py` has `generate_presigned_upload_url`, `download_file`, and `delete_file` but may not have a direct `upload_file`. Check `backend/app/services/s3.py`. If `upload_file` does not exist, add it:

```python
def upload_file(s3_key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    """Upload bytes directly to S3."""
    _client().put_object(
        Bucket=settings.s3_bucket_name,
        Key=s3_key,
        Body=data,
        ContentType=content_type,
    )
```

Add this function in `backend/app/services/s3.py` near the existing `download_file` function.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/video_downloader.py backend/app/services/s3.py
git commit -m "feat(video-url): add video downloader service with yt-dlp"
```

---

### Task 4: Add Video URL API Endpoint

**Files:**
- Modify: `backend/app/api/pitch_intelligence.py`

- [ ] **Step 1: Add VideoUrlRequest model and endpoint**

In `backend/app/api/pitch_intelligence.py`, add the following after the `TranscriptPasteRequest` class and `paste_transcript` endpoint (around line 257), before the `upload_complete` endpoint:

```python
# ── Video URL ───────────────────────────────────────────────────────


import re

VIDEO_URL_PATTERNS = [
    re.compile(r"https?://(www\.)?youtube\.com/watch\?v=[\w-]+"),
    re.compile(r"https?://youtu\.be/[\w-]+"),
    re.compile(r"https?://(www\.)?youtube\.com/live/[\w-]+"),
    re.compile(r"https?://(www\.)?loom\.com/share/[\w-]+"),
]


class VideoUrlRequest(BaseModel):
    url: str
    title: str | None = None
    startup_id: str | None = None


@router.post("/api/pitch-intelligence/video-url")
async def submit_video_url(
    body: VideoUrlRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_subscription(user)

    url = body.url.strip()
    if not any(p.match(url) for p in VIDEO_URL_PATTERNS):
        raise HTTPException(
            status_code=400,
            detail="Unsupported URL. Please provide a YouTube or Loom video link.",
        )

    startup_id = uuid.UUID(body.startup_id) if body.startup_id else None

    ps = PitchSession(
        user_id=user.id,
        startup_id=startup_id,
        title=body.title,
        video_url=url,
        status=PitchSessionStatus.downloading,
    )
    db.add(ps)
    await db.commit()
    await db.refresh(ps)

    return {"id": str(ps.id), "status": "downloading"}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/pitch_intelligence.py
git commit -m "feat(video-url): add POST /api/pitch-intelligence/video-url endpoint"
```

---

### Task 5: Update Pitch Worker to Handle Downloading Status

**Files:**
- Modify: `backend/app/services/pitch_worker.py`

- [ ] **Step 1: Add import for download_video**

At the top of `backend/app/services/pitch_worker.py`, add:

```python
from app.services.video_downloader import download_video
```

- [ ] **Step 2: Add downloading poll check**

In the `run_pitch_worker` function, add a third poll block **before** the existing `transcribing` check. The full while loop body should be:

```python
    while True:
        try:
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

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/pitch_worker.py
git commit -m "feat(video-url): add downloading status poll to pitch worker"
```

---

### Task 6: Add Frontend API Method

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add submitVideoUrl method**

In `frontend/lib/api.ts`, add the following method near the existing `submitPitchTranscript` method:

```typescript
  submitVideoUrl: async (
    token: string,
    url: string,
    title?: string,
  ): Promise<{ id: string; status: string }> => {
    return apiFetch("/api/pitch-intelligence/video-url", {
      method: "POST",
      headers: { ...authHeaders(token), "Content-Type": "application/json" },
      body: JSON.stringify({ url, title }),
    });
  },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(video-url): add submitVideoUrl API client method"
```

---

### Task 7: Add "Video Link" Tab to Frontend Page

**Files:**
- Modify: `frontend/app/pitch-intelligence/page.tsx`

- [ ] **Step 1: Add videoUrl state and mode option**

In `frontend/app/pitch-intelligence/page.tsx`, in the `PitchIntelligenceContent` function:

1. Update the `mode` state type to include `"video"`:

```typescript
  const [mode, setMode] = useState<"upload" | "video" | "transcript">("upload");
```

2. Add state for the video URL and submission:

```typescript
  const [videoUrl, setVideoUrl] = useState("");
  const [submittingVideo, setSubmittingVideo] = useState(false);
```

3. Add the `handleVideoSubmit` function after `handleTranscriptSubmit`:

```typescript
  const handleVideoSubmit = async () => {
    if (!token) return;
    const trimmed = videoUrl.trim();
    if (!trimmed) {
      setError("Please paste a video URL.");
      return;
    }
    if (
      !trimmed.includes("youtube.com/") &&
      !trimmed.includes("youtu.be/") &&
      !trimmed.includes("loom.com/")
    ) {
      setError("Please provide a YouTube or Loom link.");
      return;
    }
    setError(null);
    setSubmittingVideo(true);
    try {
      const result = await api.submitVideoUrl(token, trimmed, title || undefined);
      router.push(`/pitch-intelligence/${result.id}`);
    } catch (e: any) {
      setError(e.message || "Failed to submit video URL");
      setSubmittingVideo(false);
    }
  };
```

- [ ] **Step 2: Add the Video Link tab button**

In the mode toggle `<div className="flex gap-2 mb-4">`, add a third button between "Upload Recording" and "Paste Transcript":

```tsx
            <button
              onClick={() => setMode("upload")}
              className={`px-4 py-2 text-sm rounded-lg border transition ${
                mode === "upload"
                  ? "bg-accent text-white border-accent"
                  : "bg-surface text-text-secondary border-border hover:border-accent/50"
              }`}
            >
              Upload Recording
            </button>
            <button
              onClick={() => setMode("video")}
              className={`px-4 py-2 text-sm rounded-lg border transition ${
                mode === "video"
                  ? "bg-accent text-white border-accent"
                  : "bg-surface text-text-secondary border-border hover:border-accent/50"
              }`}
            >
              Video Link
            </button>
            <button
              onClick={() => setMode("transcript")}
              className={`px-4 py-2 text-sm rounded-lg border transition ${
                mode === "transcript"
                  ? "bg-accent text-white border-accent"
                  : "bg-surface text-text-secondary border-border hover:border-accent/50"
              }`}
            >
              Paste Transcript
            </button>
```

- [ ] **Step 3: Add the Video Link mode UI**

Replace the current conditional `{mode === "upload" ? (...) : (...)}` with a three-way conditional. After the title input and before the closing of the mode section:

```tsx
          {mode === "upload" ? (
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
          ) : mode === "video" ? (
            <div>
              <input
                type="text"
                placeholder="Paste YouTube or Loom link"
                value={videoUrl}
                onChange={(e) => setVideoUrl(e.target.value)}
                className="w-full rounded-lg border border-border bg-surface px-4 py-3 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none"
              />
              <p className="text-xs text-text-tertiary mt-2">
                Supports YouTube and Loom videos up to 2 hours
              </p>
              <div className="flex justify-end mt-4">
                <button
                  onClick={handleVideoSubmit}
                  disabled={!videoUrl.trim()}
                  className="px-5 py-2 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent/90 transition disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Analyze Video
                </button>
              </div>
            </div>
          ) : (
            /* existing transcript mode UI — no changes needed */
```

- [ ] **Step 4: Update the guard condition to include submittingVideo**

Change the condition that hides the mode toggle during submission:

```tsx
      {!uploading && !submittingTranscript && !submittingVideo && (
```

- [ ] **Step 5: Add the downloading status to the session list**

In the `statusLabel` function, add `downloading`:

```typescript
  const statusLabel = (status: string) => {
    const map: Record<string, { text: string; color: string }> = {
      downloading: { text: "Downloading", color: "text-blue-600" },
      uploading: { text: "Uploading", color: "text-yellow-600" },
      transcribing: { text: "Transcribing", color: "text-blue-600" },
      labeling: { text: "Needs Speaker Labels", color: "text-orange-600" },
      analyzing: { text: "Analyzing", color: "text-blue-600" },
      complete: { text: "Complete", color: "text-green-600" },
      failed: { text: "Failed", color: "text-red-600" },
    };
```

- [ ] **Step 6: Commit**

```bash
git add frontend/app/pitch-intelligence/page.tsx
git commit -m "feat(video-url): add Video Link tab to pitch intelligence page"
```

---

### Task 8: Handle `downloading` Status on Session Detail Page

**Files:**
- Modify: `frontend/app/pitch-intelligence/[id]/page.tsx`

- [ ] **Step 1: Add `downloading` to the polling status list**

In `frontend/app/pitch-intelligence/[id]/page.tsx`, find the polling useEffect (around line 102):

```typescript
    if (!token || !ps || !["transcribing", "analyzing"].includes(ps.status)) return;
```

Change it to:

```typescript
    if (!token || !ps || !["downloading", "transcribing", "analyzing"].includes(ps.status)) return;
```

- [ ] **Step 2: Add `downloading` to the waiting state display**

Find the block (around line 165):

```typescript
  if (ps.status === "uploading" || ps.status === "transcribing") {
```

Change it to:

```typescript
  if (ps.status === "uploading" || ps.status === "downloading" || ps.status === "transcribing") {
```

And update the message text (around line 170):

```typescript
        <h2 className="text-xl font-medium text-text-primary mb-2">
          {ps.status === "uploading"
            ? "Processing upload..."
            : ps.status === "downloading"
              ? "Downloading video..."
              : "Transcribing your pitch..."}
        </h2>
        <p className="text-text-secondary">
          {ps.status === "downloading"
            ? "Fetching audio from the video link. This may take a minute."
            : "This usually takes 1-3 minutes depending on the recording length."}
        </p>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/pitch-intelligence/[id]/page.tsx
git commit -m "feat(video-url): handle downloading status on session detail page"
```

---

### Task 9: Deploy to Production

**Files:**
- No code changes — deployment steps only.

- [ ] **Step 1: Rsync all changes to EC2**

```bash
rsync -avz \
  --exclude=node_modules --exclude=.git --exclude=__pycache__ \
  --exclude=.next --exclude=.worktrees --exclude=.superpowers \
  -e "ssh -i ~/.ssh/deepthesis-deploy.pem" \
  /Users/leemosbacker/acutal/ ec2-user@3.212.120.144:~/acutal/
```

- [ ] **Step 2: Run Alembic migration**

```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "cd ~/acutal && docker exec acutal-backend-1 alembic upgrade head"
```

If the backend is restarting due to the DB password issue, first run:
```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "docker exec acutal-db-1 psql -U acutal -d acutal -c \"ALTER TYPE pitchsessionstatus ADD VALUE IF NOT EXISTS 'downloading' BEFORE 'uploading'\"" && \
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "docker exec acutal-db-1 psql -U acutal -d acutal -c \"ALTER TABLE pitch_sessions ADD COLUMN IF NOT EXISTS video_url VARCHAR(2000)\""
```

- [ ] **Step 3: Rebuild backend and frontend**

```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "cd ~/acutal && docker compose -f docker-compose.prod.yml up -d --build backend frontend"
```

If the DB password mismatch occurs (backend crash loop), fix it:
```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "docker exec acutal-db-1 psql -U acutal -d acutal -c \"ALTER USER acutal PASSWORD '1Vj1hzYawacU1clnlVUWqzZt'\""
```
Then restart:
```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "docker restart acutal-backend-1"
```

- [ ] **Step 4: Restart the analysis worker with the new image**

```bash
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "docker stop acutal-analysis_worker-1 && docker rm acutal-analysis_worker-1 && \
   cd ~/acutal && docker run -d --name acutal-analysis_worker-1 --network acutal_default \
   --env-file .env \
   -e ACUTAL_DATABASE_URL='postgresql+asyncpg://acutal:1Vj1hzYawacU1clnlVUWqzZt@db:5432/acutal' \
   acutal-backend python -m app.services.analysis_worker"
```

- [ ] **Step 5: Verify deployment**

```bash
# Check backend health
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "curl -s http://localhost:8000/api/health"

# Check worker is running
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "docker logs acutal-analysis_worker-1 --tail 5"

# Check ffmpeg is available in the container
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "docker exec acutal-analysis_worker-1 ffmpeg -version | head -1"

# Check yt-dlp is available
ssh -i ~/.ssh/deepthesis-deploy.pem ec2-user@3.212.120.144 \
  "docker exec acutal-analysis_worker-1 python -c 'import yt_dlp; print(yt_dlp.version.__version__)'"
```
