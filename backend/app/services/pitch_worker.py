import asyncio
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import async_session
from app.models.pitch_session import (
    PitchAnalysisPhase,
    PitchAnalysisResult,
    PitchPhaseStatus,
    PitchSession,
    PitchSessionStatus,
)
from app.services.deepgram_transcription import transcribe_pitch
from app.services.pitch_agents import (
    run_claim_extraction,
    run_conversation_analysis,
    run_fact_check,
    run_scoring,
)
from app.services.pitch_benchmark import calculate_benchmarks

logger = logging.getLogger(__name__)

POLL_INTERVAL = 5  # seconds


async def _update_phase(db: AsyncSession, session_id: uuid.UUID, phase: PitchAnalysisPhase, status: PitchPhaseStatus, result: dict | None = None, error: str | None = None) -> None:
    """Update a phase's status and result."""
    phase_result = await db.execute(
        select(PitchAnalysisResult).where(
            PitchAnalysisResult.session_id == session_id,
            PitchAnalysisResult.phase == phase,
        )
    )
    pr = phase_result.scalar_one_or_none()
    if pr:
        pr.status = status
        if result is not None:
            pr.result = result
        if error is not None:
            pr.error = error
        await db.commit()


async def _run_analysis_pipeline(session_id: uuid.UUID) -> None:
    """Run all 5 analysis phases sequentially."""
    logger.info("[pitch-%s] Starting analysis pipeline", session_id)

    # Phase 1: Claim Extraction
    try:
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.claim_extraction, PitchPhaseStatus.running)
            ps = (await db.execute(select(PitchSession).where(PitchSession.id == session_id))).scalar_one()
            transcript_labeled = ps.transcript_labeled

        logger.info("[pitch-%s] Phase 1: Claim Extraction", session_id)
        claims = await run_claim_extraction(transcript_labeled)

        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.claim_extraction, PitchPhaseStatus.complete, result=claims)
    except Exception as e:
        logger.error("[pitch-%s] Phase 1 failed: %s", session_id, e, exc_info=True)
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.claim_extraction, PitchPhaseStatus.failed, error=str(e))
            ps = (await db.execute(select(PitchSession).where(PitchSession.id == session_id))).scalar_one()
            ps.status = PitchSessionStatus.failed
            ps.error = f"Claim extraction failed: {e}"
            await db.commit()
        return

    # Phase 2: Fact-checking (founder + investor in parallel)
    try:
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.fact_check_founders, PitchPhaseStatus.running)
            await _update_phase(db, session_id, PitchAnalysisPhase.fact_check_investors, PitchPhaseStatus.running)

        logger.info("[pitch-%s] Phase 2: Fact-Checking (parallel)", session_id)
        founder_fc, investor_fc = await asyncio.gather(
            run_fact_check(claims, "founder"),
            run_fact_check(claims, "investor"),
        )
        fact_check_results = {
            "founder_fact_check": founder_fc,
            "investor_fact_check": investor_fc,
        }

        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.fact_check_founders, PitchPhaseStatus.complete, result=founder_fc)
            await _update_phase(db, session_id, PitchAnalysisPhase.fact_check_investors, PitchPhaseStatus.complete, result=investor_fc)
    except Exception as e:
        logger.error("[pitch-%s] Phase 2 failed: %s", session_id, e, exc_info=True)
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.fact_check_founders, PitchPhaseStatus.failed, error=str(e))
            await _update_phase(db, session_id, PitchAnalysisPhase.fact_check_investors, PitchPhaseStatus.failed, error=str(e))
            ps = (await db.execute(select(PitchSession).where(PitchSession.id == session_id))).scalar_one()
            ps.status = PitchSessionStatus.failed
            ps.error = f"Fact-checking failed: {e}"
            await db.commit()
        return

    # Phase 3: Conversation Analysis
    try:
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.conversation_analysis, PitchPhaseStatus.running)

        logger.info("[pitch-%s] Phase 3: Conversation Analysis", session_id)
        conversation = await run_conversation_analysis(transcript_labeled, fact_check_results)

        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.conversation_analysis, PitchPhaseStatus.complete, result=conversation)
    except Exception as e:
        logger.error("[pitch-%s] Phase 3 failed: %s", session_id, e, exc_info=True)
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.conversation_analysis, PitchPhaseStatus.failed, error=str(e))
            ps = (await db.execute(select(PitchSession).where(PitchSession.id == session_id))).scalar_one()
            ps.status = PitchSessionStatus.failed
            ps.error = f"Conversation analysis failed: {e}"
            await db.commit()
        return

    # Phase 4: Scoring & Recommendations
    try:
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.scoring, PitchPhaseStatus.running)

        logger.info("[pitch-%s] Phase 4: Scoring & Recommendations", session_id)
        scoring = await run_scoring(transcript_labeled, claims, fact_check_results, conversation)

        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.scoring, PitchPhaseStatus.complete, result=scoring)
            # Store scores on the session
            ps = (await db.execute(select(PitchSession).where(PitchSession.id == session_id))).scalar_one()
            ps.scores = scoring.get("scores", {})
            await db.commit()
    except Exception as e:
        logger.error("[pitch-%s] Phase 4 failed: %s", session_id, e, exc_info=True)
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.scoring, PitchPhaseStatus.failed, error=str(e))
            ps = (await db.execute(select(PitchSession).where(PitchSession.id == session_id))).scalar_one()
            ps.status = PitchSessionStatus.failed
            ps.error = f"Scoring failed: {e}"
            await db.commit()
        return

    # Phase 5: Benchmark Comparison
    try:
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.benchmark, PitchPhaseStatus.running)

        logger.info("[pitch-%s] Phase 5: Benchmark Comparison", session_id)
        async with async_session() as db:
            percentiles = await calculate_benchmarks(session_id, db)
            await _update_phase(db, session_id, PitchAnalysisPhase.benchmark, PitchPhaseStatus.complete, result=percentiles)
    except Exception as e:
        logger.error("[pitch-%s] Phase 5 failed: %s", session_id, e, exc_info=True)
        async with async_session() as db:
            await _update_phase(db, session_id, PitchAnalysisPhase.benchmark, PitchPhaseStatus.failed, error=str(e))

    # Mark session complete
    async with async_session() as db:
        ps = (await db.execute(select(PitchSession).where(PitchSession.id == session_id))).scalar_one()
        ps.status = PitchSessionStatus.complete
        await db.commit()

    logger.info("[pitch-%s] Analysis pipeline complete", session_id)


async def run_pitch_worker() -> None:
    """Poll for pitch sessions needing transcription or analysis."""
    logger.info("Pitch Intelligence worker started")

    while True:
        try:
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
