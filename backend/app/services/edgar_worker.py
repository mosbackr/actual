"""EDGAR batch worker: processes EDGAR job steps concurrently with rate limiting.

Same architecture as batch_worker.py:
- 4 concurrent workers (lower than batch's 6 — SEC rate limit is the bottleneck)
- Atomic step claiming with SELECT FOR UPDATE SKIP LOCKED
- Step chaining: resolve_cik -> fetch_filings -> process_filing
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
from app.services.edgar import (
    search_form_d_filings,
    search_s1_filings,
    search_10k_filings,
    search_form_c_filings,
    search_form_1a_filings,
)
from app.services.dedup import normalize_name, find_duplicate
from app.services.edgar_processor import (
    FormCData,
    Form1AData,
    form_d_to_funding_round,
    is_qualifying_filing,
    is_qualifying_form_c,
    is_qualifying_form_1a,
    infer_stage_from_amount,
    merge_funding_round,
    normalize_form_source,
    parse_form_c,
    parse_form_d,
    parse_form_1a_html,
    parse_s1_company_data,
    parse_s1_html,
    parse_10k_html,
    resolve_cik,
    SIC_WHITELIST,
    ENTITY_EXCLUDE_PATTERNS,
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

FORM_SEARCH_FUNCTIONS = {
    "D": search_form_d_filings,
    "S-1": search_s1_filings,
    "10-K": search_10k_filings,
    "C": search_form_c_filings,
    "1-A": search_form_1a_filings,
}

FORM_LABELS = {
    "D": "Form D",
    "S-1": "S-1",
    "10-K": "10-K",
    "C": "Form C",
    "1-A": "Form 1-A",
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


# ---------------------------------------------------------------------------
# Discovery mode: form-aware discover -> extract -> add -> enrich
# ---------------------------------------------------------------------------


async def _execute_discover_filings(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute discover_filings step: search EFTS for filings by form type, generate extract steps."""
    from datetime import timedelta

    form_type = step.params.get("form_type", "D")
    discover_days = step.params.get("discover_days", 365)
    end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = (datetime.now(timezone.utc) - timedelta(days=discover_days)).strftime("%Y-%m-%d")

    search_fn = FORM_SEARCH_FUNCTIONS.get(form_type)
    if search_fn is None:
        step.result = {"action": "skipped", "reason": f"Unknown form type: {form_type}"}
        return

    form_label = FORM_LABELS.get(form_type, form_type)

    total_hits = 0
    qualifying = 0
    page_from = 0
    page_size = 100
    next_order = await _get_next_sort_order(db, job.id)

    while True:
        hits, total_count = await search_fn(
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
                    "form_type": form_type,
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
        "form_type": form_type,
    }
    logger.info(f"Discovery ({form_label}): {total_hits} EFTS hits, {qualifying} extract steps created")


# ---------------------------------------------------------------------------
# Extract company: form-specific handlers with shared dedup/add helpers
# ---------------------------------------------------------------------------


async def _dedup_check(
    db: AsyncSession, step: EdgarJobStep, cik: str, issuer_name: str
) -> bool:
    """Check for duplicate startup by CIK then name. Returns True if dup found."""
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
        return True

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
        return True

    return False


async def _create_add_step(
    db: AsyncSession,
    step: EdgarJobStep,
    job: EdgarJob,
    issuer_name: str,
    cik: str,
    company_info: dict,
    sic_code: str,
    form_type: str,
    amount: float,
    extra_params: dict | None = None,
) -> None:
    """Create an add_startup step with standard params plus form-specific extras."""
    state = company_info.get("state_of_incorporation", "") or company_info.get("state", "")
    next_order = await _get_next_sort_order(db, job.id)

    params = {
        "issuer_name": issuer_name,
        "cik": cik,
        "sic_code": sic_code,
        "sic_description": company_info.get("sic_description", ""),
        "state": state,
        "amount": amount,
        "accession_number": step.params.get("accession_number", ""),
        "filing_date": step.params.get("file_date", ""),
        "form_type": form_type,
    }
    if extra_params:
        params.update(extra_params)

    add_step = EdgarJobStep(
        job_id=job.id,
        step_type=EdgarStepType.add_startup,
        params=params,
        sort_order=next_order,
    )
    db.add(add_step)


async def _extract_form_d(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob,
    cik: str, company_info: dict, sic_code: str, entity_name: str,
) -> None:
    """Extract company from a Form D filing."""
    accession = step.params["accession_number"]

    # SIC whitelist filter
    if sic_code and sic_code not in SIC_WHITELIST:
        step.result = {"action": "skipped", "reason": f"SIC {sic_code} not in whitelist"}
        return

    # Find filing in index
    filings = await edgar.get_filings(cik)
    target_filing = None
    for f in filings:
        if f.accession_number == accession:
            target_filing = f
            break

    if not target_filing:
        step.result = {"action": "skipped", "reason": "Filing not found in index"}
        return

    # Download and parse
    try:
        doc_text = await edgar.download_filing(cik, accession, target_filing.primary_document)
        form_d_data = parse_form_d(doc_text)
    except Exception as e:
        step.result = {"action": "skipped", "reason": f"Parse failed: {str(e)[:200]}"}
        return

    # Qualify
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

    # Dedup
    if await _dedup_check(db, step, cik, issuer_name):
        return

    # Create add step
    await _create_add_step(
        db, step, job, issuer_name, cik, company_info, sic_code,
        form_type="D", amount=amount,
        extra_params={
            "date_of_first_sale": form_d_data.date_of_first_sale,
            "number_of_investors": form_d_data.number_of_investors,
        },
    )

    step.result = {
        "action": "new_company",
        "issuer_name": issuer_name,
        "cik": cik,
        "amount": amount,
        "sic": sic_code,
        "form_type": "D",
    }
    logger.info(f"Discovery (Form D): new company candidate — {issuer_name} (CIK {cik}, ${amount:,.0f})")


async def _extract_s1(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob,
    cik: str, company_info: dict, sic_code: str, entity_name: str,
) -> None:
    """Extract company from an S-1 filing. No SIC filter — every S-1 is a real company."""
    accession = step.params["accession_number"]
    issuer_name = company_info.get("name", "") or entity_name

    # Dedup
    if await _dedup_check(db, step, cik, issuer_name):
        return

    # Find filing in index
    filings = await edgar.get_filings(cik)
    target_filing = None
    for f in filings:
        if f.accession_number == accession:
            target_filing = f
            break

    if not target_filing:
        step.result = {"action": "skipped", "reason": "Filing not found in index"}
        return

    # Download and parse company data
    try:
        doc_text = await edgar.download_filing(cik, accession, target_filing.primary_document)
        parsed_data = await parse_s1_company_data(doc_text, issuer_name)
    except Exception as e:
        step.result = {"action": "skipped", "reason": f"Parse failed: {str(e)[:200]}"}
        return

    amount = 0  # S-1 amount is typically unknown at discovery

    # Create add step with parsed data
    await _create_add_step(
        db, step, job, issuer_name, cik, company_info, sic_code,
        form_type="S-1", amount=amount,
        extra_params={"parsed_data": parsed_data},
    )

    step.result = {
        "action": "new_company",
        "issuer_name": issuer_name,
        "cik": cik,
        "amount": amount,
        "sic": sic_code,
        "form_type": "S-1",
    }
    logger.info(f"Discovery (S-1): new company candidate — {issuer_name} (CIK {cik})")


async def _extract_10k(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob,
    cik: str, company_info: dict, sic_code: str, entity_name: str,
) -> None:
    """Extract company from a 10-K filing. Applies SIC whitelist."""
    accession = step.params["accession_number"]

    # SIC whitelist filter
    if sic_code and sic_code not in SIC_WHITELIST:
        step.result = {"action": "skipped", "reason": f"SIC {sic_code} not in whitelist"}
        return

    issuer_name = company_info.get("name", "") or entity_name

    # Dedup
    if await _dedup_check(db, step, cik, issuer_name):
        return

    # Find filing in index
    filings = await edgar.get_filings(cik)
    target_filing = None
    for f in filings:
        if f.accession_number == accession:
            target_filing = f
            break

    if not target_filing:
        step.result = {"action": "skipped", "reason": "Filing not found in index"}
        return

    # Download and parse
    try:
        doc_text = await edgar.download_filing(cik, accession, target_filing.primary_document)
        parsed_data = await parse_10k_html(doc_text, issuer_name)
    except Exception as e:
        step.result = {"action": "skipped", "reason": f"Parse failed: {str(e)[:200]}"}
        return

    amount = 0  # 10-K does not have a raise amount

    # Create add step with parsed data
    await _create_add_step(
        db, step, job, issuer_name, cik, company_info, sic_code,
        form_type="10-K", amount=amount,
        extra_params={"parsed_data": parsed_data},
    )

    step.result = {
        "action": "new_company",
        "issuer_name": issuer_name,
        "cik": cik,
        "amount": amount,
        "sic": sic_code,
        "form_type": "10-K",
    }
    logger.info(f"Discovery (10-K): new company candidate — {issuer_name} (CIK {cik})")


async def _extract_form_c(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob,
    cik: str, company_info: dict, sic_code: str, entity_name: str,
) -> None:
    """Extract company from a Form C filing (Regulation Crowdfunding)."""
    accession = step.params["accession_number"]

    # Find filing in index
    filings = await edgar.get_filings(cik)
    target_filing = None
    for f in filings:
        if f.accession_number == accession:
            target_filing = f
            break

    if not target_filing:
        step.result = {"action": "skipped", "reason": "Filing not found in index"}
        return

    # Download and parse XML
    try:
        doc_text = await edgar.download_filing(cik, accession, target_filing.primary_document)
        form_c_data = parse_form_c(doc_text)
    except Exception as e:
        step.result = {"action": "skipped", "reason": f"Parse failed: {str(e)[:200]}"}
        return

    # Qualify
    if not is_qualifying_form_c(form_c_data):
        step.result = {
            "action": "skipped",
            "reason": "Did not pass Form C qualifying filters",
            "target_amount": form_c_data.target_amount,
            "entity_name": form_c_data.company_name or entity_name,
        }
        return

    issuer_name = form_c_data.company_name or entity_name
    amount = form_c_data.target_amount or form_c_data.maximum_amount or 0

    # Dedup
    if await _dedup_check(db, step, cik, issuer_name):
        return

    # Build parsed_data from Form C fields
    parsed_data = {
        "description": form_c_data.description,
        "business_plan": form_c_data.business_plan,
        "employee_count": form_c_data.employee_count,
        "revenue": (
            f"${form_c_data.revenue_most_recent:,.0f}"
            if form_c_data.revenue_most_recent
            else None
        ),
        "founders": [
            {"name": o["name"], "title": o.get("title")}
            for o in form_c_data.officers
        ] if form_c_data.officers else [],
    }

    # Create add step
    await _create_add_step(
        db, step, job, issuer_name, cik, company_info, sic_code,
        form_type="C", amount=amount,
        extra_params={"parsed_data": parsed_data},
    )

    step.result = {
        "action": "new_company",
        "issuer_name": issuer_name,
        "cik": cik,
        "amount": amount,
        "sic": sic_code,
        "form_type": "C",
    }
    logger.info(f"Discovery (Form C): new company candidate — {issuer_name} (CIK {cik}, ${amount:,.0f})")


async def _extract_form_1a(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob,
    cik: str, company_info: dict, sic_code: str, entity_name: str,
) -> None:
    """Extract company from a Form 1-A filing (Regulation A). Uses Claude for HTML parsing."""
    accession = step.params["accession_number"]

    # Find filing in index
    filings = await edgar.get_filings(cik)
    target_filing = None
    for f in filings:
        if f.accession_number == accession:
            target_filing = f
            break

    if not target_filing:
        step.result = {"action": "skipped", "reason": "Filing not found in index"}
        return

    # Download and parse HTML via Claude
    try:
        doc_text = await edgar.download_filing(cik, accession, target_filing.primary_document)
        form_1a_data = await parse_form_1a_html(doc_text, entity_name)
    except Exception as e:
        step.result = {"action": "skipped", "reason": f"Parse failed: {str(e)[:200]}"}
        return

    # Qualify
    if not is_qualifying_form_1a(form_1a_data):
        step.result = {
            "action": "skipped",
            "reason": "Did not pass Form 1-A qualifying filters",
            "offering_amount": form_1a_data.offering_amount,
            "entity_name": form_1a_data.company_name or entity_name,
        }
        return

    issuer_name = form_1a_data.company_name or entity_name
    amount = form_1a_data.offering_amount or 0

    # Dedup
    if await _dedup_check(db, step, cik, issuer_name):
        return

    # Build parsed_data from Form 1-A fields
    parsed_data = {
        "description": form_1a_data.description,
        "business_model": form_1a_data.business_model,
        "employee_count": form_1a_data.employee_count,
        "revenue": form_1a_data.revenue,
        "founders": [
            {"name": o["name"], "title": o.get("title")}
            for o in form_1a_data.officers
        ] if form_1a_data.officers else [],
    }

    # Create add step
    await _create_add_step(
        db, step, job, issuer_name, cik, company_info, sic_code,
        form_type="1-A", amount=amount,
        extra_params={"parsed_data": parsed_data},
    )

    step.result = {
        "action": "new_company",
        "issuer_name": issuer_name,
        "cik": cik,
        "amount": amount,
        "sic": sic_code,
        "form_type": "1-A",
    }
    logger.info(f"Discovery (Form 1-A): new company candidate — {issuer_name} (CIK {cik}, ${amount:,.0f})")


# Dispatcher map for extract_company by form type
_EXTRACT_HANDLERS = {
    "D": _extract_form_d,
    "S-1": _extract_s1,
    "10-K": _extract_10k,
    "C": _extract_form_c,
    "1-A": _extract_form_1a,
}


async def _execute_extract_company(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute extract_company step: dispatch to form-specific handler."""
    accession = step.params["accession_number"]
    entity_name = step.params.get("entity_name", "")
    cik = step.params.get("cik")
    form_type = step.params.get("form_type", "D")

    if not cik:
        cik = await edgar.get_cik_from_accession(accession)
        if not cik:
            step.result = {"action": "skipped", "reason": "Could not resolve CIK"}
            return

    company_info = await edgar.get_company_info(cik)
    sic_code = company_info.get("sic", "")

    handler = _EXTRACT_HANDLERS.get(form_type)
    if handler is None:
        step.result = {"action": "skipped", "reason": f"Unknown form type: {form_type}"}
        return

    await handler(db, step, job, cik, company_info, sic_code, entity_name)


# ---------------------------------------------------------------------------
# Add startup: form-aware with provenance tracking
# ---------------------------------------------------------------------------


async def _is_real_startup(name: str) -> bool:
    """Use Perplexity to check if an entity name is an actual startup/operating company."""
    from app.services.enrichment import _call_perplexity

    prompt = (
        f"Is \"{name}\" the name of an operating startup or technology company that builds products or services? "
        f"Or is it an investment fund, SPV, holding company, real estate entity, LP, venture fund, or financial vehicle?\n\n"
        f"Reply with ONLY one word: STARTUP or FUND"
    )

    try:
        raw = await _call_perplexity(
            [{"role": "user", "content": prompt}],
            timeout=30,
        )
        return "STARTUP" in raw.upper().split()[0] if raw.strip() else False
    except Exception as e:
        logger.warning(f"Startup classification failed for {name}: {e}")
        return True  # On failure, assume startup so we don't lose real ones


async def _execute_add_startup(
    db: AsyncSession, step: EdgarJobStep, job: EdgarJob
) -> None:
    """Execute add_startup step: create Startup + FundingRound with provenance, generate enrich step."""
    from app.models.founder import StartupFounder
    from app.models.funding_round import StartupFundingRound
    from app.models.startup import EntityType, StartupStage, StartupStatus
    from app.services.edgar_processor import _format_amount

    issuer_name = step.params["issuer_name"]
    cik = step.params["cik"]
    state = step.params.get("state", "")
    amount = step.params.get("amount", 0)
    date_of_first_sale = step.params.get("date_of_first_sale")
    filing_date = step.params.get("filing_date", "")
    accession = step.params.get("accession_number", "")
    sic_description = step.params.get("sic_description", "")
    sic_code = step.params.get("sic_code", "")
    form_type = step.params.get("form_type", "D")
    parsed_data = step.params.get("parsed_data") or {}

    source_key = normalize_form_source(form_type)
    form_label = FORM_LABELS.get(form_type, form_type)

    # Classification: S-1, 10-K, Form C -> always real startup (skip check)
    # Form D, 1-A -> Perplexity check
    if form_type in ("D", "1-A"):
        is_startup = await _is_real_startup(issuer_name)
    else:
        is_startup = True  # S-1, 10-K, Form C are virtually all startups

    entity_type = EntityType.startup if is_startup else EntityType.fund

    # Stage: 10-K filers are public companies
    if form_type == "10-K":
        stage_str = "public"
    else:
        stage_str = infer_stage_from_amount(amount)
    stage = StartupStage(stage_str)

    slug = slugify(issuer_name)
    existing_slug = await db.execute(select(Startup).where(Startup.slug == slug))
    if existing_slug.scalar_one_or_none():
        slug = f"{slug}-{cik}"

    description = f"Discovered via SEC {form_label} filing. {sic_description}".strip()
    # Override description from parsed_data if available
    if parsed_data.get("description"):
        description = parsed_data["description"]

    startup = Startup(
        name=issuer_name,
        slug=slug,
        description=description,
        stage=stage,
        status=StartupStatus.pending,
        location_state=state if state else None,
        location_country="US",
        sec_cik=cik,
        form_sources=[source_key],
        entity_type=entity_type,
        enrichment_status="complete" if not is_startup else "none",
    )
    db.add(startup)
    await db.flush()

    # Build data_sources: track which fields came from the filing
    data_sources: dict = {}

    # Apply parsed_data fields to the startup with provenance tracking
    if parsed_data.get("description"):
        # Already set above in description
        data_sources["description"] = source_key

    if parsed_data.get("business_model"):
        startup.business_model = parsed_data["business_model"]
        data_sources["business_model"] = source_key

    if parsed_data.get("employee_count"):
        startup.employee_count = parsed_data["employee_count"]
        data_sources["employee_count"] = source_key

    if parsed_data.get("revenue"):
        startup.revenue_estimate = parsed_data["revenue"]
        data_sources["revenue_estimate"] = source_key

    if parsed_data.get("total_funding"):
        startup.total_funding = parsed_data["total_funding"]
        data_sources["total_funding"] = source_key

    # Save founders/officers from parsed_data
    if parsed_data.get("founders"):
        for i, founder_data in enumerate(parsed_data["founders"]):
            if founder_data.get("name"):
                founder = StartupFounder(
                    startup_id=startup.id,
                    name=founder_data["name"],
                    title=founder_data.get("title"),
                    is_founder=True,
                    sort_order=i,
                )
                db.add(founder)
        data_sources["founders"] = source_key

    # Funding rounds from parsed_data
    funding_rounds_created = False
    if parsed_data.get("funding_rounds"):
        for i, round_info in enumerate(parsed_data["funding_rounds"]):
            if isinstance(round_info, dict) and (round_info.get("amount") or round_info.get("round_name")):
                funding_round = StartupFundingRound(
                    startup_id=startup.id,
                    round_name=round_info.get("round_name") or f"{form_label} ({round_info.get('date') or 'undated'})",
                    amount=round_info.get("amount"),
                    date=round_info.get("date"),
                    pre_money_valuation=round_info.get("pre_money_valuation"),
                    post_money_valuation=round_info.get("post_money_valuation"),
                    lead_investor=round_info.get("lead_investor"),
                    other_investors=round_info.get("other_investors"),
                    sort_order=i,
                    data_source="edgar",
                )
                db.add(funding_round)
                funding_rounds_created = True
        if funding_rounds_created:
            data_sources["funding_rounds"] = source_key

    # If no funding_rounds from parsed_data and amount > 0, create a single funding round (Form D behavior)
    if not funding_rounds_created and amount and amount > 0:
        round_amount = _format_amount(amount)
        round_date = date_of_first_sale or filing_date

        funding_round = StartupFundingRound(
            startup_id=startup.id,
            round_name=f"{form_label} ({round_date or 'undated'})",
            amount=round_amount,
            date=round_date,
            sort_order=0,
            data_source="edgar",
        )
        db.add(funding_round)
        data_sources["funding_rounds"] = source_key

    # Also track business_plan for Form C if present
    if parsed_data.get("business_plan") and not startup.description:
        startup.description = parsed_data["business_plan"]
        data_sources["description"] = source_key

    # Clean up None values from data_sources
    data_sources = {k: v for k, v in data_sources.items() if v is not None}
    startup.data_sources = data_sources

    step.result = {
        "action": "created",
        "startup_id": str(startup.id),
        "startup_name": issuer_name,
        "stage": stage_str,
        "amount": _format_amount(amount) if amount else None,
        "form_type": form_type,
        "entity_type": entity_type.value,
    }

    # Only enrich actual startups — skip funds to save Perplexity credits
    if is_startup:
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

    logger.info(
        f"Discovery ({form_label}): created startup {issuer_name} "
        f"(stage={stage_str}, CIK={cik}, sources={list(data_sources.keys())})"
    )


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
