import logging
import os
import shutil
import tempfile
import uuid

from sqlalchemy import select

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

        s3.upload_file(file_bytes, s3_key)
        logger.info("[pitch-%s] Uploaded audio to S3: %s (%d bytes)", session_id, s3_key, len(file_bytes))

        # Update session
        async with async_session() as db:
            result = await db.execute(
                select(PitchSession).where(PitchSession.id == session_id)
            )
            ps = result.scalar_one()
            ps.file_url = s3_key
            ps.status = PitchSessionStatus.transcribing
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
            ps.error = "Failed to download video. Please check the URL and try again."
            await db.commit()

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
