# Video URL Ingestion for Pitch Intelligence

## Goal

Allow users to paste a YouTube or Loom video URL into pitch intelligence. The system downloads the audio, stores it in S3, and transcribes it via Deepgram — same pipeline as uploaded recordings.

## Supported Platforms

- YouTube (youtube.com, youtu.be)
- Loom (loom.com)

## Constraints

- Max video duration: 2 hours
- Audio-only extraction (no video stream stored)
- Requires active subscription (same gate as existing upload)

---

## Architecture

### New Status

`PitchSessionStatus` gains a `downloading` value. Full flow:

```
downloading → transcribing → labeling → analyzing → complete
```

### New Model Column

`PitchSession.video_url: str | None` — stores the original URL for display purposes. Alembic migration adds this column and the new enum value.

### New Endpoint

```
POST /api/pitch-intelligence/video-url
Body: { url: string, title?: string }
Response: { id: UUID, status: "downloading" }
```

Validation:
- URL must match YouTube or Loom patterns (regex)
- User must have active subscription
- Rejects with 400 if URL is not recognized

Creates a `PitchSession` with `status=downloading`, `video_url=<url>`, optional `title`.

### New Service: `backend/app/services/video_downloader.py`

Single function:

```python
async def download_video(session_id: UUID) -> None
```

Steps:
1. Fetch session from DB, get `video_url`
2. Probe video metadata via `yt-dlp` (no download) to get duration
3. If duration > 7200 seconds, fail with "Video exceeds 2 hour limit"
4. Download audio-only to temp file using `yt-dlp` with `format: bestaudio[ext=m4a]/bestaudio` and `ffmpeg` postprocessor to convert to m4a
5. Upload temp file to S3 at `pitch-intelligence/{session_id}/audio.m4a`
6. Set `session.file_url` to the S3 key
7. Transition status: `downloading → transcribing`
8. Clean up temp file in `finally` block

Error cases:
- Private/deleted video → status=failed, error="Video is private or unavailable"
- Network/download failure → status=failed, error="Failed to download video. Please check the URL and try again."
- Duration exceeded → status=failed, error="Video exceeds the 2 hour limit"

### Worker Update: `backend/app/services/pitch_worker.py`

Add a third poll block in `run_pitch_worker()`:

```python
# Check for sessions needing video download
if PitchSession.status == downloading:
    await download_video(job.id)
```

Placed before the existing `transcribing` and `analyzing` checks.

### Docker Changes

Backend Dockerfile:
- Add `RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*`
- Add `yt-dlp` to `pyproject.toml` dependencies

---

## Frontend Changes

### Pitch Intelligence Page (`frontend/app/pitch-intelligence/page.tsx`)

Add third mode tab: "Upload Recording" | "Video Link" | "Paste Transcript"

"Video Link" mode UI:
- Text input for URL (placeholder: "Paste YouTube or Loom link")
- Optional title input (same as existing modes)
- Submit button

On submit:
- Basic client-side URL validation (contains youtube.com, youtu.be, or loom.com)
- Calls `api.submitVideoUrl(token, url, title)`
- Navigates to `/pitch-intelligence/{id}`

### Session Detail Page (`frontend/app/pitch-intelligence/[id]/page.tsx`)

Add `downloading` to the status display:
- Show "Downloading video..." with spinner
- Existing polling picks up the transition to `transcribing` automatically

### API Client (`frontend/lib/api.ts`)

Add method:

```typescript
submitVideoUrl(token: string, url: string, title?: string): Promise<{ id: string; status: string }>
```

---

## Files Changed

### New Files
- `backend/app/services/video_downloader.py` — download + S3 upload logic
- `backend/alembic/versions/XXXX_add_video_url_and_downloading_status.py` — migration

### Modified Files
- `backend/app/models/pitch_session.py` — add `downloading` enum, `video_url` column
- `backend/app/api/pitch_intelligence.py` — add `/video-url` endpoint
- `backend/app/services/pitch_worker.py` — add downloading poll check
- `backend/Dockerfile` — add ffmpeg
- `backend/pyproject.toml` — add yt-dlp dependency
- `frontend/app/pitch-intelligence/page.tsx` — add Video Link tab
- `frontend/app/pitch-intelligence/[id]/page.tsx` — handle downloading status
- `frontend/lib/api.ts` — add submitVideoUrl method
