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
