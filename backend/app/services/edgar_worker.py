"""EDGAR batch worker: processes EDGAR job steps concurrently with rate limiting.

Same architecture as batch_worker.py:
- 4 concurrent workers (lower than batch's 6 — SEC rate limit is the bottleneck)
- Atomic step claiming with SELECT FOR UPDATE SKIP LOCKED
- Step chaining: resolve_cik → fetch_filings → process_filing
- Pause/resume support
"""
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models.edgar_job import (
    EdgarJob,
    EdgarJobPhase,
    EdgarJobStatus,
    EdgarJobStep,
    EdgarStepStatus,
    EdgarStepType,
)
from app.models.startup import Startup
from app.services import edgar
from app.services.dedup import normalize_name, find_duplicate
from app.services.edgar_processor import (
    form_d_to_funding_round,
    is_qualifying_filing,
    infer_stage_from_amount,
    merge_funding_round,
    parse_form_d,
    parse_s1_html,
    parse_10k_html,
    resolve_cik,
    SIC_WHITELIST,
)
from app.services.enrichment import run_enrichment_pipeline
from app.utils import slugify

logger = logging.getLogger(__name__)

CONCURRENCY = 4

STEP_DELAYS = {
    EdgarStepType.resolve_cik: 1.0,
    EdgarStepType.fetch_filings: 0.5,
    EdgarStepType.process_filing: 1.0,
    EdgarStepType.discover_filings: 0.2,
    EdgarStepType.extract_company: 1.0,
    EdgarStepType.add_startup: 0.5,
    EdgarStepType.enrich_startup: 2.0,
}


async def _get_next_sort_order(db: AsyncSession, job_id) -> int:
    result = await db.execute(
        select(func.coalesce(func.max(EdgarJobStep.sort_order), 0))
        .where(EdgarJobStep.job_id == job_id)
    )
    return (result.scalar() or 0) + 1


async def _update_progress(db: AsyncSession, job: EdgarJob):
    """Recalculate job progress_summary from step data."""
    steps_result = await db.execute(
        select(EdgarJobStep).where(EdgarJobStep.job_id == job.id)
    )
    all_steps = steps_result.scalars().all()

    startups_scanned = 0
    ciks_matched = 0
    filings_found = 0
    filings_processed = 0
    rounds_updated = 0
    rounds_created = 0
    valuations_added = 0

    # Discovery-mode counters
    filings_discovered = 0
    companies_extracted = 0
    duplicates_skipped = 0
    startups_created = 0
    enrichments_completed = 0
    enrichments_failed = 0

    for step in all_steps:
        if step.step_type == EdgarStepType.resolve_cik and step.status == EdgarStepStatus.completed:
            startups_scanned += 1
            if step.result and step.result.get("cik"):
                ciks_matched += 1
        elif step.step_type == EdgarStepType.fetch_filings and step.status == EdgarStepStatus.completed:
            if step.result:
                filings_found += step.result.get("filings_count", 0)
        elif step.step_type == EdgarStepType.process_filing and step.status == EdgarStepStatus.completed:
            filings_processed += 1
            if step.result:
                if step.result.get("action") == "updated":
                    rounds_updated += 1
                elif step.result.get("action") == "created":
                    rounds_created += 1
                if step.result.get("valuation_added"):
                    valuations_added += 1
        elif step.step_type == EdgarStepType.discover_filings and step.status == EdgarStepStatus.completed:
            if step.result:
                filings_discovered += step.result.get("extract_steps_created", 0)
        elif step.step_type == EdgarStepType.extract_company and step.status == EdgarStepStatus.completed:
            companies_extracted += 1
            if step.result and step.result.get("action") == "duplicate":
                duplicates_skipped += 1
        elif step.step_type == EdgarStepType.add_startup and step.status == EdgarStepStatus.completed:
            if step.result and step.result.get("action") == "created":
                startups_created += 1
        elif step.step_type == EdgarStepType.enrich_startup and step.status == EdgarStepStatus.completed:
            if step.result:
                if step.result.get("action") == "enriched":
                    enrichments_completed += 1
                elif step.result.get("action") == "enrichment_failed":
                    enrichments_failed += 1

    total_resolve = len([s for s in all_steps if s.step_type == EdgarStepType.resolve_cik])
    total_process = len([s for s in all_steps if s.step_type == EdgarStepType.process_filing])
    total_extract = len([s for s in all_steps if s.step_type == EdgarStepType.extract_company])
    total_enrich = len([s for s in all_steps if s.step_type == EdgarStepType.enrich_startup])

    current_startup = None
    current_filing = None
    for step in all_steps:
        if step.status == EdgarStepStatus.running:
            if step.params.get("startup_name"):
                current_startup = step.params["startup_name"]
            if step.params.get("filing_type"):
                current_filing = step.params["filing_type"]
            break

    summary = {
        "startups_total": total_resolve,
        "startups_scanned": startups_scanned,
        "ciks_matched": ciks_matched,
        "filings_found": filings_found,
        "filings_total": total_process,
        "filings_processed": filings_processed,
        "rounds_updated": rounds_updated,
        "rounds_created": rounds_created,
        "valuations_added": valuations_added,
    }
    if current_startup:
        summary["current_startup"] = current_startup
    if current_filing:
        summary["current_filing"] = current_filing

    if total_extract > 0 or filings_discovered > 0:
        summary["filings_discovered"] = filings_discovered
        summary["companies_extracted"] = companies_extracted
        summary["extract_total"] = total_extract
        summary["duplicates_skipped"] = duplicates_skipped
        summary["startups_created"] = startups_created
        summary["enrichments_completed"] = enrichments_completed
        summary["enrichments_failed"] = enrichments_failed
        summary["enrich_total"] = total_enrich

    job.progress_summary = summary
    job.updated_at = datetime.now(timezone.utc)

    has_pending_resolve = any(
        s.step_type == EdgarStepType.resolve_cik and s.status == EdgarStepStatus.pending
        for s in all_steps
    )
    has_pending_fetch = any(
        s.step_type == EdgarStepType.fetch_filings and s.status == EdgarStepStatus.pending
        for s in all_steps
    )
    has_pending_process = any(
        s.step_type == EdgarStepType.process_filing and s.status == EdgarStepStatus.pending
        for s in all_steps
    )
    has_pending_discover = any(
        s.step_type == EdgarStepType.discover_filings and s.status == EdgarStepStatus.pending
        for s in all_steps
    )
    has_pending_extract = any(
        s.step_type == EdgarStepType.extract_company and s.status == EdgarStepStatus.pending
        for s in all_steps
    )
    has_pending_add = any(
        s.step_type == EdgarStepType.add_startup and s.status == EdgarStepStatus.pending
        for s in all_steps
    )
    has_pending_enrich = any(
        s.step_type == EdgarStepType.enrich_startup and s.status == EdgarStepStatus.pending
        for s in all_steps
    )

    if has_pending_resolve:
        job.current_phase = EdgarJobPhase.resolving_ciks
    elif has_pending_fetch:
        job.current_phase = EdgarJobPhase.fetching_filings
    elif has_pending_process:
        job.current_phase = EdgarJobPhase.processing_filings
    elif has_pending_discover:
        job.current_phase = EdgarJobPhase.discovering
    elif has_pending_extract:
        job.current_phase = EdgarJobPhase.extracting
    elif has_pending_add:
        job.current_phase = EdgarJobPhase.adding
    elif has_pending_enrich:
        job.current_phase = EdgarJobPhase.enriching
    else:
        job.current_phase = EdgarJobPhase.complete

    await db.commit()


async def _execute_resolve_cik(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute resolve_cik step: search EDGAR + Claude verification."""
    startup_id = step.params["startup_id"]

    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    startup = result.scalar_one_or_none()
    if startup is None:
        step.result = {"error": "Startup not found"}
        raise Exception(f"Startup {startup_id} not found")

    cik = await resolve_cik(db, startup)

    if cik:
        startup.sec_cik = cik
        startup.edgar_last_scanned_at = datetime.now(timezone.utc)
        step.result = {"cik": cik, "startup_name": startup.name}

        next_order = await _get_next_sort_order(db, job.id)
        fetch_step = EdgarJobStep(
            job_id=job.id,
            step_type=EdgarStepType.fetch_filings,
            params={
                "startup_id": str(startup_id),
                "startup_name": startup.name,
                "cik": cik,
            },
            sort_order=next_order,
        )
        db.add(fetch_step)
        logger.info(f"Resolved CIK {cik} for {startup.name}")
    else:
        startup.edgar_last_scanned_at = datetime.now(timezone.utc)
        step.result = {"cik": None, "startup_name": startup.name}
        logger.info(f"No CIK match for {startup.name}")


async def _execute_fetch_filings(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute fetch_filings step: pull filing index for a CIK."""
    cik = step.params["cik"]
    startup_id = step.params["startup_id"]
    startup_name = step.params["startup_name"]

    filings = await edgar.get_filings(cik)

    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    startup = result.scalar_one_or_none()

    step.result = {
        "filings_count": len(filings),
        "filing_types": list(set(f.filing_type for f in filings)),
    }

    if filings:
        next_order = await _get_next_sort_order(db, job.id)
        for filing in filings:
            process_step = EdgarJobStep(
                job_id=job.id,
                step_type=EdgarStepType.process_filing,
                params={
                    "startup_id": str(startup_id),
                    "startup_name": startup_name,
                    "cik": cik,
                    "accession_number": filing.accession_number,
                    "filing_type": filing.filing_type,
                    "filing_date": filing.filing_date,
                    "primary_document": filing.primary_document,
                },
                sort_order=next_order,
            )
            db.add(process_step)
            next_order += 1

    logger.info(f"Found {len(filings)} filings for {startup_name} (CIK {cik})")


async def _execute_process_filing(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute process_filing step: download and parse one filing."""
    cik = step.params["cik"]
    startup_id = step.params["startup_id"]
    startup_name = step.params["startup_name"]
    accession = step.params["accession_number"]
    filing_type = step.params["filing_type"]
    filing_date = step.params["filing_date"]
    primary_doc = step.params["primary_document"]

    doc_text = await edgar.download_filing(cik, accession, primary_doc)

    filing_obj = edgar.EdgarFiling(
        accession_number=accession,
        filing_type=filing_type,
        filing_date=filing_date,
        primary_document=primary_doc,
        description="",
    )

    if filing_type in ("D", "D/A"):
        form_d_data = parse_form_d(doc_text)
        round_data = form_d_to_funding_round(form_d_data, filing_obj)
        merge_result = await merge_funding_round(db, startup_id, round_data)
        step.result = {
            **merge_result,
            "filing_type": filing_type,
            "amount": round_data.amount,
            "date": round_data.date,
            "valuation_added": bool(round_data.pre_money_valuation or round_data.post_money_valuation),
        }
        logger.info(f"Processed Form D for {startup_name}: {merge_result['action']}")

    elif filing_type in ("S-1", "S-1/A"):
        rounds = await parse_s1_html(doc_text, startup_name)
        actions = []
        valuations = 0
        for round_data in rounds:
            round_data.accession_number = accession
            merge_result = await merge_funding_round(db, startup_id, round_data)
            actions.append(merge_result)
            if round_data.pre_money_valuation or round_data.post_money_valuation:
                valuations += 1
        step.result = {
            "filing_type": filing_type,
            "rounds_extracted": len(rounds),
            "actions": actions,
            "valuation_added": valuations > 0,
        }
        logger.info(f"Processed S-1 for {startup_name}: {len(rounds)} rounds extracted")

    elif filing_type in ("10-K", "10-K/A"):
        metrics = await parse_10k_html(doc_text, startup_name)
        if metrics:
            result = await db.execute(select(Startup).where(Startup.id == startup_id))
            startup = result.scalar_one_or_none()
            if startup:
                if metrics.get("revenue") and not startup.revenue_estimate:
                    startup.revenue_estimate = metrics["revenue"]
                if metrics.get("employee_count") and not startup.employee_count:
                    startup.employee_count = metrics["employee_count"]
        step.result = {
            "filing_type": filing_type,
            "metrics": metrics,
            "valuation_added": False,
        }
        logger.info(f"Processed 10-K for {startup_name}: {metrics}")

    else:
        step.result = {"filing_type": filing_type, "action": "skipped", "reason": f"Unsupported type: {filing_type}"}


async def _execute_discover_filings(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute discover_filings step: search EFTS for Form D filings, generate extract steps."""
    from datetime import timedelta

    discover_days = step.params.get("discover_days", 365)
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=discover_days)).strftime("%Y-%m-%d")

    total_hits = 0
    qualifying = 0
    page_from = 0
    page_size = 100
    next_order = await _get_next_sort_order(db, job.id)

    while True:
        hits, total_count = await edgar.search_form_d_filings(
            start_date=start_date,
            end_date=end_date,
            page_from=page_from,
            page_size=page_size,
        )

        if not hits:
            break

        total_hits += len(hits)

        for hit in hits:
            extract_step = EdgarJobStep(
                job_id=job.id,
                step_type=EdgarStepType.extract_company,
                params={
                    "accession_number": hit.accession_number,
                    "entity_name": hit.entity_name,
                    "file_date": hit.file_date,
                    "cik": hit.cik,
                },
                sort_order=next_order,
            )
            db.add(extract_step)
            next_order += 1
            qualifying += 1

        page_from += page_size
        if page_from >= total_count:
            break

        if qualifying % 500 == 0:
            await db.flush()

    step.result = {
        "total_hits": total_hits,
        "extract_steps_created": qualifying,
        "date_range": f"{start_date} to {end_date}",
    }
    logger.info(f"Discovery: {total_hits} EFTS hits, {qualifying} extract steps created")


async def _execute_extract_company(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute extract_company step: download Form D XML, parse, filter, dedup, generate add_startup step."""
    accession = step.params["accession_number"]
    entity_name = step.params.get("entity_name", "")
    cik = step.params.get("cik")

    if not cik:
        cik = await edgar.get_cik_from_accession(accession)
        if not cik:
            step.result = {"action": "skipped", "reason": "Could not resolve CIK"}
            return

    company_info = await edgar.get_company_info(cik)
    sic_code = company_info.get("sic", "")

    if sic_code and sic_code not in SIC_WHITELIST:
        step.result = {"action": "skipped", "reason": f"SIC {sic_code} not in whitelist"}
        return

    filings = await edgar.get_filings(cik)
    target_filing = None
    for f in filings:
        if f.accession_number == accession:
            target_filing = f
            break

    if not target_filing:
        step.result = {"action": "skipped", "reason": "Filing not found in index"}
        return

    try:
        doc_text = await edgar.download_filing(cik, accession, target_filing.primary_document)
        form_d_data = parse_form_d(doc_text)
    except Exception as e:
        step.result = {"action": "skipped", "reason": f"Parse failed: {str(e)[:200]}"}
        return

    if not is_qualifying_filing(form_d_data, sic_code):
        step.result = {
            "action": "skipped",
            "reason": "Did not pass qualifying filters",
            "amount": form_d_data.total_amount_sold,
            "sic": sic_code,
            "entity_name": form_d_data.issuer_name or entity_name,
        }
        return

    issuer_name = form_d_data.issuer_name or entity_name
    amount = form_d_data.total_amount_sold or 0

    # Dedup check 1: CIK match
    existing_cik_result = await db.execute(
        select(Startup).where(Startup.sec_cik == cik)
    )
    existing_by_cik = existing_cik_result.scalar_one_or_none()
    if existing_by_cik:
        step.result = {
            "action": "duplicate",
            "reason": "CIK already in database",
            "existing_startup": existing_by_cik.name,
            "existing_id": str(existing_by_cik.id),
        }
        return

    # Dedup check 2: Name match
    dup = await find_duplicate(db, issuer_name)
    if dup:
        existing_result = await db.execute(select(Startup).where(Startup.id == dup["id"]))
        existing = existing_result.scalar_one_or_none()
        if existing and not existing.sec_cik:
            existing.sec_cik = cik
        step.result = {
            "action": "duplicate",
            "reason": "Name match in database",
            "existing_startup": dup["name"],
            "existing_id": dup["id"],
            "cik_updated": bool(existing and not existing.sec_cik),
        }
        return

    # Qualifying new company — generate add_startup step
    state = company_info.get("state_of_incorporation", "") or company_info.get("state", "")
    next_order = await _get_next_sort_order(db, job.id)
    add_step = EdgarJobStep(
        job_id=job.id,
        step_type=EdgarStepType.add_startup,
        params={
            "issuer_name": issuer_name,
            "cik": cik,
            "sic_code": sic_code,
            "sic_description": company_info.get("sic_description", ""),
            "state": state,
            "amount": amount,
            "date_of_first_sale": form_d_data.date_of_first_sale,
            "number_of_investors": form_d_data.number_of_investors,
            "accession_number": accession,
            "filing_date": step.params.get("file_date", ""),
        },
        sort_order=next_order,
    )
    db.add(add_step)

    step.result = {
        "action": "new_company",
        "issuer_name": issuer_name,
        "cik": cik,
        "amount": amount,
        "sic": sic_code,
    }
    logger.info(f"Discovery: new company candidate — {issuer_name} (CIK {cik}, ${amount:,.0f})")


async def _execute_add_startup(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute add_startup step: create Startup + FundingRound, generate enrich step."""
    from app.models.funding_round import StartupFundingRound
    from app.models.startup import StartupStage, StartupStatus
    from app.services.edgar_processor import _format_amount

    issuer_name = step.params["issuer_name"]
    cik = step.params["cik"]
    state = step.params.get("state", "")
    amount = step.params.get("amount", 0)
    date_of_first_sale = step.params.get("date_of_first_sale")
    filing_date = step.params.get("filing_date", "")
    accession = step.params.get("accession_number", "")
    sic_description = step.params.get("sic_description", "")

    stage_str = infer_stage_from_amount(amount)
    stage = StartupStage(stage_str)

    slug = slugify(issuer_name)
    existing_slug = await db.execute(select(Startup).where(Startup.slug == slug))
    if existing_slug.scalar_one_or_none():
        slug = f"{slug}-{cik}"

    startup = Startup(
        name=issuer_name,
        slug=slug,
        description=f"Discovered via SEC Form D filing. {sic_description}".strip(),
        stage=stage,
        status=StartupStatus.pending,
        location_state=state if state else None,
        location_country="US",
        sec_cik=cik,
    )
    db.add(startup)
    await db.flush()

    round_amount = _format_amount(amount) if amount else None
    round_date = date_of_first_sale or filing_date

    funding_round = StartupFundingRound(
        startup_id=startup.id,
        round_name=f"Form D ({round_date or 'undated'})",
        amount=round_amount,
        date=round_date,
        sort_order=0,
        data_source="edgar",
    )
    db.add(funding_round)

    next_order = await _get_next_sort_order(db, job.id)
    enrich_step = EdgarJobStep(
        job_id=job.id,
        step_type=EdgarStepType.enrich_startup,
        params={
            "startup_id": str(startup.id),
            "startup_name": issuer_name,
        },
        sort_order=next_order,
    )
    db.add(enrich_step)

    step.result = {
        "action": "created",
        "startup_id": str(startup.id),
        "startup_name": issuer_name,
        "stage": stage_str,
        "amount": round_amount,
    }
    logger.info(f"Discovery: created startup {issuer_name} (stage={stage_str}, CIK={cik})")


async def _execute_enrich_startup(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute enrich_startup step: run Perplexity enrichment pipeline."""
    startup_id = step.params["startup_id"]
    startup_name = step.params.get("startup_name", "")

    try:
        await run_enrichment_pipeline(startup_id)
        step.result = {
            "action": "enriched",
            "startup_name": startup_name,
        }
        logger.info(f"Discovery: enriched {startup_name}")
    except Exception as e:
        step.result = {
            "action": "enrichment_failed",
            "startup_name": startup_name,
            "error": str(e)[:200],
        }
        logger.warning(f"Discovery: enrichment failed for {startup_name}: {e}")


STEP_EXECUTORS = {
    EdgarStepType.resolve_cik: _execute_resolve_cik,
    EdgarStepType.fetch_filings: _execute_fetch_filings,
    EdgarStepType.process_filing: _execute_process_filing,
    EdgarStepType.discover_filings: _execute_discover_filings,
    EdgarStepType.extract_company: _execute_extract_company,
    EdgarStepType.add_startup: _execute_add_startup,
    EdgarStepType.enrich_startup: _execute_enrich_startup,
}

WORKER_PREFERENCES = {
    0: EdgarStepType.resolve_cik,
    1: EdgarStepType.resolve_cik,
    2: EdgarStepType.process_filing,
    3: EdgarStepType.process_filing,
}


async def _claim_next_step(db: AsyncSession, job_id: str, preferred_type: EdgarStepType | None = None) -> EdgarJobStep | None:
    """Atomically claim the next pending step using FOR UPDATE SKIP LOCKED."""
    if preferred_type is not None:
        result = await db.execute(
            select(EdgarJobStep)
            .where(EdgarJobStep.job_id == job_id)
            .where(EdgarJobStep.status == EdgarStepStatus.pending)
            .where(EdgarJobStep.step_type == preferred_type)
            .order_by(EdgarJobStep.sort_order)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        step = result.scalar_one_or_none()
        if step is not None:
            step.status = EdgarStepStatus.running
            await db.commit()
            return step

    result = await db.execute(
        select(EdgarJobStep)
        .where(EdgarJobStep.job_id == job_id)
        .where(EdgarJobStep.status == EdgarStepStatus.pending)
        .order_by(EdgarJobStep.sort_order)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    step = result.scalar_one_or_none()
    if step is not None:
        step.status = EdgarStepStatus.running
        await db.commit()
    return step


async def _worker_loop(job_id: str, worker_id: int, failure_event: asyncio.Event) -> None:
    """Single worker coroutine."""
    consecutive_failures = 0

    while not failure_event.is_set():
        async with async_session() as db:
            job_result = await db.execute(
                select(EdgarJob).where(EdgarJob.id == job_id)
            )
            job = job_result.scalar_one_or_none()
            if job is None:
                logger.error(f"[edgar-worker-{worker_id}] Job {job_id} not found, exiting")
                return

            if job.status in (EdgarJobStatus.paused, EdgarJobStatus.cancelled):
                logger.info(f"[edgar-worker-{worker_id}] Job {job_id} is {job.status.value}, exiting")
                return

            preferred = WORKER_PREFERENCES.get(worker_id)
            step = await _claim_next_step(db, job_id, preferred)

            if step is None:
                running_result = await db.execute(
                    select(func.count())
                    .select_from(EdgarJobStep)
                    .where(EdgarJobStep.job_id == job_id)
                    .where(EdgarJobStep.status == EdgarStepStatus.running)
                )
                running_count = running_result.scalar() or 0
                if running_count == 0:
                    return
                await asyncio.sleep(2)
                continue

            step_type = step.step_type
            executor = STEP_EXECUTORS.get(step_type)
            if executor is None:
                step.status = EdgarStepStatus.failed
                step.error = f"Unknown step type: {step_type}"
                step.completed_at = datetime.now(timezone.utc)
                await db.commit()
                continue

            try:
                await executor(db, step, job)
                step.status = EdgarStepStatus.completed
                step.completed_at = datetime.now(timezone.utc)
                consecutive_failures = 0
            except Exception as e:
                logger.exception(f"[edgar-worker-{worker_id}] Step {step.id} failed: {e}")
                step.status = EdgarStepStatus.failed
                step.error = str(e)[:500]
                step.completed_at = datetime.now(timezone.utc)
                consecutive_failures += 1

            await _update_progress(db, job)
            await db.commit()

            if consecutive_failures >= 3:
                failure_event.set()
                job.status = EdgarJobStatus.paused
                job.error = f"Worker {worker_id} paused job after 3 consecutive failures"
                job.updated_at = datetime.now(timezone.utc)
                await db.commit()
                logger.warning(f"[edgar-worker-{worker_id}] Paused job {job_id} after 3 consecutive failures")
                return

        delay = STEP_DELAYS.get(step_type, 1.0)
        await asyncio.sleep(delay)


async def run_edgar_worker(job_id: str) -> None:
    """Main entry point. Spawns 4 concurrent workers."""
    failure_event = asyncio.Event()

    workers = [
        asyncio.create_task(_worker_loop(job_id, i, failure_event))
        for i in range(CONCURRENCY)
    ]

    await asyncio.gather(*workers)

    async with async_session() as db:
        job_result = await db.execute(
            select(EdgarJob).where(EdgarJob.id == job_id)
        )
        job = job_result.scalar_one_or_none()
        if job and job.status == EdgarJobStatus.running:
            job.status = EdgarJobStatus.completed
            job.current_phase = EdgarJobPhase.complete
            job.completed_at = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            await _update_progress(db, job)
            await db.commit()
            logger.info(f"EDGAR job {job_id} completed")
