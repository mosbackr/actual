"""Batch worker: processes batch job steps concurrently with rate limiting."""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models.batch_job import (
    BatchJob,
    BatchJobPhase,
    BatchJobStatus,
    BatchJobStep,
    BatchStepStatus,
    BatchStepType,
)
from app.models.startup import Startup, StartupStatus
from app.services.batch_locations import STAGE_LABELS, format_location
from app.services.dedup import normalize_name
from app.services.enrichment import run_enrichment_pipeline
from app.services.scout import (
    SCOUT_SYSTEM_PROMPT,
    StartupCandidate,
    add_startups_to_triage,
    call_perplexity,
    clean_reply,
    extract_startups_from_response,
)

logger = logging.getLogger(__name__)

# Number of concurrent workers
CONCURRENCY = 3

# Delays in seconds after each step type
STEP_DELAYS = {
    BatchStepType.discover_investors: 2,
    BatchStepType.find_startups: 2,
    BatchStepType.add_to_triage: 2,
    BatchStepType.enrich: 2,
}

# System prompt for investor discovery (no startup JSON needed)
INVESTOR_DISCOVERY_PROMPT = """You are a venture capital research assistant.

When asked to find investors in a location, search thoroughly and return a JSON block with investor data.

IMPORTANT: You MUST include a JSON block in your response wrapped in ```json code fences:

```json
[
  {
    "name": "Fund or Group Name",
    "type": "vc|angel_group|accelerator",
    "focus": "Brief description of investment focus",
    "notable_partners": "Partner names if known",
    "deal_count": "Approximate number of deals if known"
  }
]
```

Rules:
- Be EXHAUSTIVE — find every firm, angel group, and accelerator you can
- Search multiple sources: Crunchbase, PitchBook, LinkedIn, AngelList, local startup ecosystem sites
- Include both well-known and smaller/newer firms
- If you're unsure about a field, use empty string
- After the JSON block, include a brief summary"""


def _extract_investors_from_response(text: str) -> list[str]:
    """Extract investor names from Perplexity's response."""
    json_match = re.search(r"```json\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if isinstance(data, list):
                return [item["name"] for item in data if isinstance(item, dict) and item.get("name")]
        except (json.JSONDecodeError, KeyError):
            pass

    array_match = re.search(r"\[\s*\{.*?\}\s*\]", text, re.DOTALL)
    if array_match:
        try:
            data = json.loads(array_match.group(0))
            if isinstance(data, list):
                return [item["name"] for item in data if isinstance(item, dict) and item.get("name")]
        except (json.JSONDecodeError, KeyError):
            pass

    return []


async def _get_next_sort_order(db: AsyncSession, job_id) -> int:
    """Get the next available sort_order for a job."""
    result = await db.execute(
        select(func.coalesce(func.max(BatchJobStep.sort_order), 0))
        .where(BatchJobStep.job_id == job_id)
    )
    return (result.scalar() or 0) + 1


async def _update_progress(db: AsyncSession, job: BatchJob):
    """Recalculate and update the job's progress_summary from step data."""
    steps = await db.execute(
        select(BatchJobStep).where(BatchJobStep.job_id == job.id)
    )
    all_steps = steps.scalars().all()

    locations_completed = 0
    investors_found = 0
    startups_found = 0
    startups_added = 0
    startups_skipped = 0
    startups_enriched = 0
    startups_enrich_failed = 0

    for step in all_steps:
        if step.step_type == BatchStepType.discover_investors and step.status == BatchStepStatus.completed:
            locations_completed += 1
            if step.result and "investors" in step.result:
                investors_found += len(step.result["investors"])
        elif step.step_type == BatchStepType.find_startups and step.status == BatchStepStatus.completed:
            if step.result and "startups" in step.result:
                startups_found += len(step.result["startups"])
        elif step.step_type == BatchStepType.add_to_triage and step.status == BatchStepStatus.completed:
            if step.result:
                startups_added += len(step.result.get("created", []))
                startups_skipped += len(step.result.get("skipped", []))
        elif step.step_type == BatchStepType.enrich:
            if step.status == BatchStepStatus.completed:
                startups_enriched += 1
            elif step.status == BatchStepStatus.failed:
                startups_enrich_failed += 1

    # Find current step info
    current_step = None
    for step in all_steps:
        if step.status == BatchStepStatus.running:
            current_step = step
            break

    summary = {
        "locations_total": len([s for s in all_steps if s.step_type == BatchStepType.discover_investors]),
        "locations_completed": locations_completed,
        "investors_found": investors_found,
        "startups_found": startups_found,
        "startups_added": startups_added,
        "startups_skipped_duplicate": startups_skipped,
        "startups_enriched": startups_enriched,
        "startups_enrich_failed": startups_enrich_failed,
    }

    if current_step and current_step.params:
        p = current_step.params
        if p.get("city"):
            loc_str = f"{p['city']}, {p.get('state') or p.get('country', '')}"
            summary["current_location"] = loc_str
        if p.get("stage"):
            summary["current_stage"] = p["stage"]
        if p.get("investor"):
            summary["current_investor"] = p["investor"]
        if p.get("startup_name"):
            summary["current_startup"] = p["startup_name"]

    job.progress_summary = summary
    job.updated_at = datetime.now(timezone.utc)

    # Update current_phase based on what's running
    has_pending_discover = any(
        s.step_type == BatchStepType.discover_investors and s.status == BatchStepStatus.pending
        for s in all_steps
    )
    has_pending_find = any(
        s.step_type == BatchStepType.find_startups and s.status == BatchStepStatus.pending
        for s in all_steps
    )
    has_pending_enrich = any(
        s.step_type == BatchStepType.enrich and s.status == BatchStepStatus.pending
        for s in all_steps
    )

    if has_pending_discover:
        job.current_phase = BatchJobPhase.discovering_investors
    elif has_pending_find:
        job.current_phase = BatchJobPhase.finding_startups
    elif has_pending_enrich:
        job.current_phase = BatchJobPhase.enriching
    else:
        job.current_phase = BatchJobPhase.complete

    await db.commit()


async def _execute_discover_investors(
    db: AsyncSession, step: BatchJobStep, job: BatchJob
) -> None:
    """Execute a discover_investors step: call Perplexity to find investors in a location+stage."""
    params = step.params
    city = params["city"]
    state = params.get("state")
    country = params["country"]
    stage = params["stage"]
    stage_label = STAGE_LABELS.get(stage, stage)
    location_str = f"{city}, {state}" if state else f"{city}, {country}"

    refresh_days = job.refresh_days
    if refresh_days:
        prompt = (
            f"Find all {stage_label} venture capital firms, angel investor groups, and startup accelerators "
            f"that have made investments in {location_str} in the last {refresh_days} days.\n\n"
            f"Return EVERY firm you can find — include fund name, notable partners, investment focus, "
            f"and approximate deal count. Be thorough and search multiple sources."
        )
    else:
        prompt = (
            f"Find all {stage_label} venture capital firms, angel investor groups, and startup accelerators "
            f"that are actively investing in {location_str}.\n\n"
            f"Return EVERY firm you can find — include fund name, notable partners, investment focus, "
            f"and approximate deal count. Be thorough and search multiple sources."
        )

    data = await call_perplexity(INVESTOR_DISCOVERY_PROMPT, prompt)
    if data is None:
        raise Exception(f"Perplexity API failed for {location_str} / {stage_label}")

    raw_content = data["choices"][0]["message"]["content"]
    investors = _extract_investors_from_response(raw_content)
    reply = clean_reply(raw_content)

    step.result = {
        "investors": investors,
        "scout_reply": reply[:2000],
    }

    # Generate find_startups steps for each investor
    if investors:
        # Check which investors already have find_startups steps in this job
        existing_steps = await db.execute(
            select(BatchJobStep)
            .where(BatchJobStep.job_id == job.id)
            .where(BatchJobStep.step_type == BatchStepType.find_startups)
        )
        existing_investors = set()
        for s in existing_steps.scalars().all():
            if s.params.get("investor"):
                existing_investors.add(normalize_name(s.params["investor"]))

        # For refresh runs, also check previous batch jobs
        if job.job_type.value == "refresh":
            prev_steps = await db.execute(
                select(BatchJobStep)
                .where(BatchJobStep.job_id != job.id)
                .where(BatchJobStep.step_type == BatchStepType.find_startups)
                .where(BatchJobStep.status == BatchStepStatus.completed)
            )
            for s in prev_steps.scalars().all():
                if s.params.get("investor"):
                    existing_investors.add(normalize_name(s.params["investor"]))

        next_order = await _get_next_sort_order(db, job.id)
        for inv_name in investors:
            if normalize_name(inv_name) in existing_investors:
                continue
            new_step = BatchJobStep(
                job_id=job.id,
                step_type=BatchStepType.find_startups,
                params={
                    "investor": inv_name,
                    "stage": stage,
                    "city": city,
                    "state": state,
                    "country": country,
                },
                sort_order=next_order,
            )
            db.add(new_step)
            next_order += 1

    logger.info(f"Discovered {len(investors)} investors in {location_str} ({stage_label})")


async def _execute_find_startups(
    db: AsyncSession, step: BatchJobStep, job: BatchJob
) -> None:
    """Execute a find_startups step: call Perplexity to find portfolio companies for an investor."""
    params = step.params
    investor = params["investor"]
    stage = params["stage"]
    stage_label = STAGE_LABELS.get(stage, stage)

    refresh_days = job.refresh_days
    if refresh_days:
        prompt = (
            f"Find all startup investments made by {investor} at the {stage_label} stage "
            f"in the last {refresh_days} days. List every new portfolio company you can find with their details."
        )
    else:
        prompt = (
            f"Find all startup investments made by {investor} at the {stage_label} stage. "
            f"List every portfolio company you can find with their details."
        )

    data = await call_perplexity(SCOUT_SYSTEM_PROMPT, prompt)
    if data is None:
        raise Exception(f"Perplexity API failed for investor {investor}")

    raw_content = data["choices"][0]["message"]["content"]
    startups_raw = extract_startups_from_response(raw_content)
    reply = clean_reply(raw_content)

    # Validate candidates
    valid_candidates = []
    for s in startups_raw:
        try:
            candidate = StartupCandidate(**s)
            valid_candidates.append(candidate.model_dump())
        except Exception:
            continue

    step.result = {
        "startups": valid_candidates,
        "scout_reply": reply[:2000],
    }

    # Generate add_to_triage step if we found startups
    if valid_candidates:
        next_order = await _get_next_sort_order(db, job.id)
        triage_step = BatchJobStep(
            job_id=job.id,
            step_type=BatchStepType.add_to_triage,
            params={
                "startup_candidates": valid_candidates,
                "source_investor": investor,
            },
            sort_order=next_order,
        )
        db.add(triage_step)

    logger.info(f"Found {len(valid_candidates)} startups from {investor} ({stage_label})")


async def _execute_add_to_triage(
    db: AsyncSession, step: BatchJobStep, job: BatchJob
) -> None:
    """Execute an add_to_triage step: add startup candidates to DB with dedup."""
    params = step.params
    candidates_data = params.get("startup_candidates", [])
    source_investor = params.get("source_investor", "")

    candidates = []
    for c in candidates_data:
        try:
            candidates.append(StartupCandidate(**c))
        except Exception:
            continue

    if not candidates:
        step.result = {"created": [], "skipped": []}
        return

    result = await add_startups_to_triage(db, candidates)

    step.result = result

    # Generate enrich steps for each created startup
    if result["created"]:
        next_order = await _get_next_sort_order(db, job.id)
        for startup_info in result["created"]:
            enrich_step = BatchJobStep(
                job_id=job.id,
                step_type=BatchStepType.enrich,
                params={
                    "startup_id": startup_info["id"],
                    "startup_name": startup_info["name"],
                    "source_investor": source_investor,
                },
                sort_order=next_order,
            )
            db.add(enrich_step)
            next_order += 1

    logger.info(
        f"Triage: added {len(result['created'])}, skipped {len(result['skipped'])} from {source_investor}"
    )


async def _execute_enrich(
    db: AsyncSession, step: BatchJobStep, job: BatchJob
) -> None:
    """Execute an enrich step: approve startup and run enrichment pipeline."""
    params = step.params
    startup_id = params["startup_id"]

    # Load startup and set to approved
    result = await db.execute(
        select(Startup).where(Startup.id == startup_id)
    )
    startup = result.scalar_one_or_none()

    if startup is None:
        step.result = {"error": "Startup not found"}
        raise Exception(f"Startup {startup_id} not found")

    if startup.enrichment_status and startup.enrichment_status.value == "complete":
        step.result = {"ai_score": startup.ai_score, "enrichment_status": "already_complete"}
        logger.info(f"Skipping enrichment for {startup.name} — already complete")
        return

    # Set to approved so enrichment can run
    startup.status = StartupStatus.approved
    await db.commit()

    # Run enrichment (it creates its own DB session)
    await run_enrichment_pipeline(startup_id)

    # Re-fetch to get updated data
    await db.refresh(startup)
    step.result = {
        "ai_score": startup.ai_score,
        "enrichment_status": startup.enrichment_status.value if startup.enrichment_status else "unknown",
    }

    logger.info(f"Enriched {startup.name} — AI score: {startup.ai_score}")


# Map step types to executor functions
STEP_EXECUTORS = {
    BatchStepType.discover_investors: _execute_discover_investors,
    BatchStepType.find_startups: _execute_find_startups,
    BatchStepType.add_to_triage: _execute_add_to_triage,
    BatchStepType.enrich: _execute_enrich,
}


async def _claim_next_step(db: AsyncSession, job_id: str) -> BatchJobStep | None:
    """Atomically claim the next pending step using FOR UPDATE SKIP LOCKED."""
    result = await db.execute(
        select(BatchJobStep)
        .where(BatchJobStep.job_id == job_id)
        .where(BatchJobStep.status == BatchStepStatus.pending)
        .order_by(BatchJobStep.sort_order)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    step = result.scalar_one_or_none()
    if step is not None:
        step.status = BatchStepStatus.running
        await db.commit()
    return step


async def _worker_loop(job_id: str, worker_id: int, failure_event: asyncio.Event) -> None:
    """Single worker coroutine that claims and processes steps."""
    consecutive_failures = 0

    while not failure_event.is_set():
        async with async_session() as db:
            # Check job status
            job_result = await db.execute(
                select(BatchJob).where(BatchJob.id == job_id)
            )
            job = job_result.scalar_one_or_none()
            if job is None:
                logger.error(f"[worker-{worker_id}] Batch job {job_id} not found, exiting")
                return

            if job.status in (BatchJobStatus.paused, BatchJobStatus.cancelled):
                logger.info(f"[worker-{worker_id}] Batch job {job_id} is {job.status.value}, exiting")
                return

            # Claim next step atomically
            step = await _claim_next_step(db, job_id)

            if step is None:
                # No steps available — either all done or other workers have them
                # Check if there are any running steps (other workers still going)
                running_result = await db.execute(
                    select(func.count())
                    .select_from(BatchJobStep)
                    .where(BatchJobStep.job_id == job_id)
                    .where(BatchJobStep.status == BatchStepStatus.running)
                )
                running_count = running_result.scalar() or 0
                if running_count == 0:
                    # Nothing pending, nothing running — we're done
                    return
                # Other workers still going, wait and check for new steps they generate
                await asyncio.sleep(2)
                continue

            # Execute step
            step_type = step.step_type
            executor = STEP_EXECUTORS.get(step_type)
            if executor is None:
                step.status = BatchStepStatus.failed
                step.error = f"Unknown step type: {step_type}"
                step.completed_at = datetime.now(timezone.utc)
                await db.commit()
                continue

            try:
                await executor(db, step, job)
                step.status = BatchStepStatus.completed
                step.completed_at = datetime.now(timezone.utc)
                consecutive_failures = 0
            except Exception as e:
                logger.exception(f"[worker-{worker_id}] Step {step.id} failed: {e}")
                step.status = BatchStepStatus.failed
                step.error = str(e)[:500]
                step.completed_at = datetime.now(timezone.utc)
                consecutive_failures += 1

            # Update progress
            await _update_progress(db, job)
            await db.commit()

            # Check consecutive failures
            if consecutive_failures >= 3:
                failure_event.set()
                job.status = BatchJobStatus.paused
                job.error = f"Worker {worker_id} paused job after 3 consecutive failures — check API key/limits"
                job.updated_at = datetime.now(timezone.utc)
                await db.commit()
                logger.warning(f"[worker-{worker_id}] Paused job {job_id} after 3 consecutive failures")
                return

        # Rate limiting delay
        delay = STEP_DELAYS.get(step_type, 5)
        await asyncio.sleep(delay)


async def run_batch_worker(job_id: str) -> None:
    """Main entry point. Spawns concurrent workers that claim steps from the queue.

    This runs as a background task, creating its own DB sessions.
    """
    failure_event = asyncio.Event()

    # Spawn N concurrent workers
    workers = [
        asyncio.create_task(_worker_loop(job_id, i, failure_event))
        for i in range(CONCURRENCY)
    ]

    # Wait for all workers to finish
    await asyncio.gather(*workers)

    # Mark job complete if it wasn't paused/cancelled
    async with async_session() as db:
        job_result = await db.execute(
            select(BatchJob).where(BatchJob.id == job_id)
        )
        job = job_result.scalar_one_or_none()
        if job and job.status == BatchJobStatus.running:
            job.status = BatchJobStatus.completed
            job.current_phase = BatchJobPhase.complete
            job.completed_at = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            await _update_progress(db, job)
            await db.commit()
            logger.info(f"Batch job {job_id} completed")
