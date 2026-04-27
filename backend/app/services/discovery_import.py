import csv
import io
import logging
import re
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models.discovery import DiscoveryBatchJob
from app.models.investor import BatchJobStatus
from app.models.startup import ClassificationStatus, Startup, StartupStatus

logger = logging.getLogger(__name__)


def _generate_slug(name: str) -> str:
    """Generate a URL-safe slug from a company name with random suffix."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    suffix = uuid.uuid4().hex[:6]
    return f"{slug}-{suffix}"


def _parse_date(date_str: str) -> date | None:
    """Parse common date formats from CSV: MM/DD/YYYY, YYYY-MM-DD, etc."""
    if not date_str or not date_str.strip():
        return None
    date_str = date_str.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


# Common CSV column name mappings (lowercase)
COLUMN_MAP = {
    # file number
    "file_number": "file_number",
    "filenumber": "file_number",
    "file number": "file_number",
    "entity_file_number": "file_number",
    "file_num": "file_number",
    # entity name
    "entity_name": "entity_name",
    "entityname": "entity_name",
    "entity name": "entity_name",
    "name": "entity_name",
    "company_name": "entity_name",
    "company name": "entity_name",
    # entity type
    "entity_type": "entity_type",
    "entitytype": "entity_type",
    "entity type": "entity_type",
    "type": "entity_type",
    # filed date
    "filed_date": "filed_date",
    "fileddate": "filed_date",
    "filed date": "filed_date",
    "file_date": "filed_date",
    "date": "filed_date",
    "incorporation_date": "filed_date",
    "formation_date": "filed_date",
    # state
    "state": "state",
    "jurisdiction": "state",
    # status
    "status": "status",
    "entity_status": "status",
}

# Entity types that are C-corps (case-insensitive matching)
C_CORP_TYPES = {
    "corporation",
    "general corporation",
    "corp",
    "c corp",
    "c-corp",
    "stock corporation",
    "domestic corporation",
    "foreign corporation",
}


def _normalize_columns(headers: list[str]) -> dict[str, str]:
    """Map CSV headers to canonical column names."""
    mapping = {}
    for header in headers:
        key = header.strip().lower()
        if key in COLUMN_MAP:
            mapping[header] = COLUMN_MAP[key]
    return mapping


async def import_csv(csv_content: str, job_id: str) -> None:
    """Parse a CSV string and import Delaware C-corp filings into the startups table."""
    db_factory = async_session

    reader = csv.DictReader(io.StringIO(csv_content))
    if not reader.fieldnames:
        async with db_factory() as db:
            job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
            if job:
                job.status = BatchJobStatus.failed.value
                job.error = "CSV has no headers"
                await db.commit()
        return

    col_map = _normalize_columns(list(reader.fieldnames))
    rows = list(reader)

    # Update job total
    async with db_factory() as db:
        job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
        if not job:
            return
        job.status = BatchJobStatus.running.value
        job.total_items = len(rows)
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

    created = 0
    skipped = 0

    for idx, row in enumerate(rows):
        # Map columns
        mapped = {}
        for csv_col, canonical in col_map.items():
            mapped[canonical] = row.get(csv_col, "").strip()

        entity_name = mapped.get("entity_name", "")
        file_number = mapped.get("file_number", "")
        entity_type = mapped.get("entity_type", "").lower()
        filed_date_str = mapped.get("filed_date", "")

        if not entity_name or not file_number:
            skipped += 1
            continue

        # Filter to C-corps only
        if entity_type and entity_type not in C_CORP_TYPES:
            skipped += 1
            continue

        filed_date = _parse_date(filed_date_str)

        async with db_factory() as db:
            # Check for pause
            job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
            if job and job.status == BatchJobStatus.paused.value:
                logger.info(f"Import job {job_id} paused at row {idx}")
                return

            # Deduplicate on file_number
            existing = await db.execute(
                select(Startup).where(Startup.delaware_file_number == file_number)
            )
            if existing.scalar_one_or_none():
                skipped += 1
            else:
                startup = Startup(
                    name=entity_name,
                    slug=_generate_slug(entity_name),
                    description="",
                    stage="pre_seed",
                    status=StartupStatus.discovered,
                    location_country="US",
                    discovery_source="delaware",
                    delaware_corp_name=entity_name,
                    delaware_file_number=file_number,
                    delaware_filed_at=filed_date,
                    classification_status=ClassificationStatus.unclassified,
                )
                db.add(startup)
                await db.commit()
                created += 1

            # Update progress
            job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
            if job:
                job.processed_items = idx + 1
                job.items_created = created
                job.current_item_name = entity_name
                await db.commit()

        if (idx + 1) % 500 == 0:
            logger.info(f"Import progress: {idx + 1}/{len(rows)}, created={created}, skipped={skipped}")

    # Mark complete
    async with db_factory() as db:
        job = await db.get(DiscoveryBatchJob, uuid.UUID(job_id))
        if job:
            job.status = BatchJobStatus.completed.value
            job.completed_at = datetime.now(timezone.utc)
            job.items_created = created
            await db.commit()

    logger.info(f"Import complete: {created} created, {skipped} skipped out of {len(rows)} rows")
