import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import async_session
from app.models.pitch_analysis import (
    AgentType,
    AnalysisDocument,
    AnalysisReport,
    AnalysisStatus,
    PitchAnalysis,
    ReportStatus,
)
from app.models.startup import EnrichmentStatus, Startup, StartupStage, StartupStatus
from app.models.user import User
from app.services import email_service, s3
from app.services.analysis_agents import run_agent, run_final_scoring
from app.services.document_extractor import consolidate_documents, extract_text
from app.models.notification import Notification, NotificationType

logger = logging.getLogger(__name__)

STALE_CLAIM_MINUTES = 15


async def _claim_job(db: AsyncSession) -> PitchAnalysis | None:
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=STALE_CLAIM_MINUTES)

    # Reset stale claimed jobs
    await db.execute(
        update(PitchAnalysis)
        .where(
            PitchAnalysis.status.in_([AnalysisStatus.extracting, AnalysisStatus.analyzing]),
            PitchAnalysis.claimed_at < stale_cutoff,
        )
        .values(status=AnalysisStatus.pending, claimed_at=None, current_agent=None)
    )

    # Claim a pending job
    result = await db.execute(
        select(PitchAnalysis)
        .where(PitchAnalysis.status == AnalysisStatus.pending)
        .order_by(PitchAnalysis.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if job:
        job.status = AnalysisStatus.extracting
        job.claimed_at = datetime.now(timezone.utc)
        await db.commit()
    return job


async def _extract_documents(db: AsyncSession, analysis_id: uuid.UUID) -> str:
    result = await db.execute(
        select(AnalysisDocument).where(AnalysisDocument.analysis_id == analysis_id)
    )
    docs = result.scalars().all()

    extracted = []
    for doc in docs:
        logger.info(f"Extracting: {doc.filename} ({doc.file_type})")
        file_data = s3.download_file(doc.s3_key)
        text = extract_text(file_data, doc.filename, doc.file_type)
        doc.extracted_text = text
        extracted.append({"filename": doc.filename, "file_type": doc.file_type, "text": text})

    await db.commit()
    return consolidate_documents(extracted)


async def _run_single_agent(
    db_factory,
    analysis_id: uuid.UUID,
    agent_type: AgentType,
    consolidated_text: str,
    company_name: str,
) -> dict | None:
    async with db_factory() as db:
        # Mark report as running
        result = await db.execute(
            select(AnalysisReport).where(
                AnalysisReport.analysis_id == analysis_id,
                AnalysisReport.agent_type == agent_type,
            )
        )
        report = result.scalar_one()
        report.status = ReportStatus.running
        report.started_at = datetime.now(timezone.utc)
        await db.commit()

        # Update current_agent on analysis
        await db.execute(
            update(PitchAnalysis)
            .where(PitchAnalysis.id == analysis_id)
            .values(current_agent=agent_type.value)
        )
        await db.commit()

    try:
        # Run agent with its own DB session for tool call persistence
        async with db_factory() as db:
            agent_result = await run_agent(
                agent_type, consolidated_text, company_name, analysis_id, db
            )

        async with db_factory() as db:
            result = await db.execute(
                select(AnalysisReport).where(
                    AnalysisReport.analysis_id == analysis_id,
                    AnalysisReport.agent_type == agent_type,
                )
            )
            report = result.scalar_one()
            report.status = ReportStatus.complete
            report.score = agent_result["score"]
            report.summary = agent_result["summary"]
            report.report = agent_result["report"]
            report.key_findings = agent_result["key_findings"]
            report.completed_at = datetime.now(timezone.utc)
            await db.commit()

        logger.info(f"Agent {agent_type.value} complete: score={agent_result['score']}")
        return {"agent_type": agent_type.value, **agent_result}

    except Exception as e:
        logger.error(f"Agent {agent_type.value} failed: {e}")
        async with db_factory() as db:
            result = await db.execute(
                select(AnalysisReport).where(
                    AnalysisReport.analysis_id == analysis_id,
                    AnalysisReport.agent_type == agent_type,
                )
            )
            report = result.scalar_one()
            report.status = ReportStatus.failed
            report.error = str(e)
            report.completed_at = datetime.now(timezone.utc)
            await db.commit()
        return None


async def _create_startup_from_analysis(
    db: AsyncSession, analysis: PitchAnalysis, consolidated_text: str
) -> None:
    from app.services.enrichment import run_enrichment_pipeline

    slug_base = analysis.company_name.lower().replace(" ", "-")
    slug_base = "".join(c for c in slug_base if c.isalnum() or c == "-")
    slug = f"{slug_base}-{str(uuid.uuid4())[:6]}"

    startup = Startup(
        name=analysis.company_name,
        slug=slug,
        description=f"Submitted for analysis on Deep Thesis",
        stage=StartupStage.pre_seed,
        status=StartupStatus.approved,
        ai_score=analysis.overall_score,
        form_sources=["pitch_analysis"],
        enrichment_status=EnrichmentStatus.running,
    )
    db.add(startup)
    await db.flush()

    analysis.startup_id = startup.id
    await db.commit()

    try:
        await run_enrichment_pipeline(str(startup.id))
    except Exception as e:
        logger.error(f"Enrichment failed for {analysis.company_name}: {e}")
        async with async_session() as err_db:
            s = await err_db.get(Startup, startup.id)
            if s:
                s.enrichment_status = EnrichmentStatus.failed
                s.enrichment_error = str(e)
                await err_db.commit()


async def _process_job(analysis_id: uuid.UUID) -> None:
    db_factory = async_session

    # Phase 1: Extract documents
    async with db_factory() as db:
        result = await db.execute(
            select(PitchAnalysis).where(PitchAnalysis.id == analysis_id)
        )
        analysis = result.scalar_one()
        company_name = analysis.company_name
        publish_consent = analysis.publish_consent

    async with db_factory() as db:
        try:
            consolidated_text = await _extract_documents(db, analysis_id)
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            result = await db.execute(
                select(PitchAnalysis).where(PitchAnalysis.id == analysis_id)
            )
            analysis = result.scalar_one()
            analysis.status = AnalysisStatus.failed
            analysis.error = f"Document extraction failed: {e}"
            await db.commit()
            return

    # Phase 2: Create report records and run agents
    async with db_factory() as db:
        result = await db.execute(
            select(PitchAnalysis).where(PitchAnalysis.id == analysis_id)
        )
        analysis = result.scalar_one()
        analysis.status = AnalysisStatus.analyzing
        await db.commit()

        for agent_type in AgentType:
            report = AnalysisReport(
                analysis_id=analysis_id,
                agent_type=agent_type,
                status=ReportStatus.pending,
            )
            db.add(report)
        await db.commit()

    # Run all 8 agents in parallel
    tasks = [
        _run_single_agent(db_factory, analysis_id, agent_type, consolidated_text, company_name)
        for agent_type in AgentType
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect successful results for scoring
    completed_reports = [r for r in results if isinstance(r, dict)]

    if not completed_reports:
        async with db_factory() as db:
            result = await db.execute(
                select(PitchAnalysis).where(PitchAnalysis.id == analysis_id)
            )
            analysis = result.scalar_one()
            analysis.status = AnalysisStatus.failed
            analysis.error = "All agents failed"
            await db.commit()
        return

    # Phase 3: Final scoring
    try:
        scoring = await run_final_scoring(completed_reports, company_name)
    except Exception as e:
        logger.error(f"Final scoring failed: {e}")
        scoring = {
            "overall_score": sum(r["score"] for r in completed_reports) / len(completed_reports),
            "fundraising_likelihood": None,
            "recommended_raise": None,
            "exit_likelihood": None,
            "expected_exit_value": None,
            "expected_exit_timeline": None,
            "executive_summary": "Final scoring agent failed. Scores shown are raw averages.",
        }

    async with db_factory() as db:
        result = await db.execute(
            select(PitchAnalysis).where(PitchAnalysis.id == analysis_id)
        )
        analysis = result.scalar_one()
        analysis.overall_score = scoring["overall_score"]
        analysis.fundraising_likelihood = scoring.get("fundraising_likelihood")
        analysis.recommended_raise = scoring.get("recommended_raise")
        analysis.exit_likelihood = scoring.get("exit_likelihood")
        analysis.expected_exit_value = scoring.get("expected_exit_value")
        analysis.expected_exit_timeline = scoring.get("expected_exit_timeline")
        analysis.executive_summary = scoring.get("executive_summary")
        analysis.current_agent = None

        # Phase 4: Publish if consented
        if publish_consent:
            analysis.status = AnalysisStatus.enriching
            await db.commit()
            await _create_startup_from_analysis(db, analysis, consolidated_text)

        analysis.status = AnalysisStatus.complete
        analysis.completed_at = datetime.now(timezone.utc)
        await db.commit()

        # Create notification for user
        notification = Notification(
            user_id=analysis.user_id,
            type=NotificationType.analysis_complete,
            title="Analysis complete",
            message=company_name or "Your startup analysis",
            link=f"/analyze/{analysis.id}",
        )
        db.add(notification)
        await db.commit()

        # Send email notification
        user_result = await db.execute(select(User).where(User.id == analysis.user_id))
        user = user_result.scalar_one_or_none()
        if user:
            email_service.send_analysis_complete(
                user_email=user.email,
                user_name=user.name,
                analysis_id=str(analysis.id),
                startup_name=company_name or "Your startup",
            )

    logger.info(f"Analysis complete for {company_name}: score={scoring['overall_score']}")


async def run_analysis_worker() -> None:
    logger.info("Analysis worker started")
    while True:
        try:
            async with async_session() as db:
                job = await _claim_job(db)

            if job:
                logger.info(f"Processing analysis: {job.company_name} ({job.id})")
                await _process_job(job.id)
            else:
                await asyncio.sleep(5)

        except Exception as e:
            logger.error(f"Worker error: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_analysis_worker())
