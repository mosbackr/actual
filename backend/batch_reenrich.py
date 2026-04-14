"""Batch re-enrichment script for startups missing website or logo.

Run inside backend container:
  python batch_reenrich.py
"""

import asyncio
import logging
import sys

from sqlalchemy import select, or_, text

from app.db.session import async_session
from app.models.startup import EnrichmentStatus, Startup, StartupStatus
from app.services.enrichment import run_enrichment_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Process this many concurrently (respect Perplexity rate limits)
CONCURRENCY = 3
# Delay between launching batches (seconds)
BATCH_DELAY = 2


async def main():
    # Fetch all approved startups missing website or logo
    async with async_session() as db:
        result = await db.execute(
            select(Startup.id, Startup.name)
            .where(Startup.status == StartupStatus.approved)
            .where(
                or_(
                    Startup.website_url.is_(None),
                    Startup.website_url == "",
                    Startup.logo_url.is_(None),
                    Startup.logo_url == "",
                )
            )
            .where(Startup.enrichment_status != EnrichmentStatus.running)
            .order_by(Startup.created_at)
        )
        rows = result.all()

    total = len(rows)
    logger.info("Found %d startups to re-enrich", total)

    success = 0
    failed = 0

    for i in range(0, total, CONCURRENCY):
        batch = rows[i : i + CONCURRENCY]
        batch_num = i // CONCURRENCY + 1
        total_batches = (total + CONCURRENCY - 1) // CONCURRENCY

        logger.info(
            "Batch %d/%d — processing %d startups (%d/%d done, %d failed)",
            batch_num,
            total_batches,
            len(batch),
            success,
            total,
            failed,
        )

        tasks = []
        for startup_id, name in batch:
            logger.info("  Starting: %s (%s)", name, startup_id)
            tasks.append(run_enrichment_pipeline(str(startup_id)))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (startup_id, name), result in zip(batch, results):
            if isinstance(result, Exception):
                failed += 1
                logger.error("  FAILED: %s — %s", name, result)
            else:
                success += 1
                logger.info("  OK: %s", name)

        if i + CONCURRENCY < total:
            await asyncio.sleep(BATCH_DELAY)

    logger.info(
        "DONE — %d/%d enriched successfully, %d failed", success, total, failed
    )


if __name__ == "__main__":
    asyncio.run(main())
