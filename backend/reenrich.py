"""Re-enrich all startups (or a filtered subset).

Usage:
    python reenrich.py                    # all enriched startups
    python reenrich.py --status approved  # only approved
    python reenrich.py --limit 50         # first 50
    python reenrich.py --dry-run          # just show what would be re-enriched
    python reenrich.py --delay 5          # seconds between each (rate limiting)
"""

import argparse
import asyncio
import logging
import time

from sqlalchemy import select, func

from app.db.session import async_session
from app.models.startup import EnrichmentStatus, Startup, StartupStatus
from app.services.enrichment import run_enrichment_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="Re-enrich startups")
    parser.add_argument("--status", choices=["approved", "featured", "pending", "all"], default="all",
                        help="Only re-enrich startups with this status (default: all)")
    parser.add_argument("--limit", type=int, default=0, help="Max startups to process (0 = no limit)")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between enrichments (rate limiting)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be re-enriched without doing it")
    parser.add_argument("--failed-only", action="store_true", help="Only re-enrich previously failed startups")
    parser.add_argument("--never-enriched", action="store_true", help="Only enrich startups that were never enriched")
    args = parser.parse_args()

    async with async_session() as db:
        query = select(Startup.id, Startup.name, Startup.stage, Startup.enrichment_status, Startup.status)

        if args.status != "all":
            query = query.where(Startup.status == StartupStatus(args.status))

        if args.failed_only:
            query = query.where(Startup.enrichment_status == EnrichmentStatus.failed)
        elif args.never_enriched:
            query = query.where(Startup.enrichment_status.in_([EnrichmentStatus.none, None]))

        query = query.order_by(Startup.created_at.asc())

        if args.limit > 0:
            query = query.limit(args.limit)

        result = await db.execute(query)
        startups = result.all()

        # Count total
        count_q = select(func.count(Startup.id))
        if args.status != "all":
            count_q = count_q.where(Startup.status == StartupStatus(args.status))
        total_in_db = (await db.execute(count_q)).scalar() or 0

    logger.info("Found %d startups to re-enrich (out of %d total)", len(startups), total_in_db)

    if args.dry_run:
        for sid, name, stage, enrichment, status in startups:
            print(f"  {name} | stage={stage.value} | enrichment={enrichment.value} | status={status.value}")
        print(f"\nDry run: {len(startups)} startups would be re-enriched")
        return

    succeeded = 0
    failed = 0

    for i, (sid, name, stage, enrichment, status) in enumerate(startups, 1):
        logger.info("[%d/%d] Re-enriching: %s (current stage: %s)", i, len(startups), name, stage.value)
        try:
            await run_enrichment_pipeline(str(sid))
            succeeded += 1
            logger.info("[%d/%d] Done: %s", i, len(startups), name)
        except Exception as e:
            failed += 1
            logger.error("[%d/%d] Failed: %s — %s", i, len(startups), name, e)

        if i < len(startups) and args.delay > 0:
            await asyncio.sleep(args.delay)

    logger.info("Re-enrichment complete. Succeeded: %d, Failed: %d, Total: %d", succeeded, failed, len(startups))


if __name__ == "__main__":
    asyncio.run(main())
