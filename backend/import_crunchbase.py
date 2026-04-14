"""Import Crunchbase funding rounds CSV into the database.

Run inside backend container:
  python import_crunchbase.py
"""

import asyncio
import csv
import logging
import re
import sys
import uuid

from sqlalchemy import select

from app.db.session import async_session
from app.models.funding_round import StartupFundingRound
from app.models.startup import Startup, StartupStage, StartupStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

CSV_PATH = "/data/funding-rounds-2-7-2026.csv"

STAGE_MAP = {
    "Pre-Seed": StartupStage.pre_seed,
    "Angel": StartupStage.pre_seed,
    "Seed": StartupStage.seed,
    "Convertible Note": StartupStage.seed,
    "Series A": StartupStage.series_a,
    "Series B": StartupStage.series_b,
    "Series C": StartupStage.series_c,
    "Series D": StartupStage.growth,
    "Series E": StartupStage.growth,
    "Series F": StartupStage.growth,
    "Series G": StartupStage.growth,
    "Series H": StartupStage.growth,
    "Venture - Series Unknown": StartupStage.seed,
    "Funding Round": StartupStage.seed,
    "Corporate Round": StartupStage.series_a,
    "Private Equity": StartupStage.growth,
    "Post-IPO Equity": StartupStage.public,
    "Post-IPO Debt": StartupStage.public,
    "Post-IPO Secondary": StartupStage.public,
    "Debt Financing": StartupStage.series_a,
    "Grant": StartupStage.pre_seed,
    "Non-equity Assistance": StartupStage.pre_seed,
    "Initial Coin Offering": StartupStage.seed,
    "Product Crowdfunding": StartupStage.pre_seed,
    "Equity Crowdfunding": StartupStage.seed,
    "Secondary Market": StartupStage.growth,
}


def slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")[:200]


def format_amount(usd: str) -> str | None:
    if not usd:
        return None
    try:
        val = float(usd)
    except ValueError:
        return None
    if val >= 1_000_000_000:
        return f"${val / 1_000_000_000:.1f}B"
    if val >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    if val >= 1_000:
        return f"${val / 1_000:.0f}K"
    return f"${val:.0f}"


async def main():
    # Parse CSV and group by org
    orgs: dict[str, list[dict]] = {}
    with open(CSV_PATH) as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["Organization Name"].strip()
            if not name:
                continue
            if name not in orgs:
                orgs[name] = []
            orgs[name].append(row)

    logger.info("Parsed %d unique orgs from CSV", len(orgs))

    # Get existing names from DB
    async with async_session() as db:
        result = await db.execute(select(Startup.name))
        existing = {r[0].lower() for r in result.all()}

        # Also grab existing slugs
        result = await db.execute(select(Startup.slug))
        existing_slugs = {r[0] for r in result.all()}

    to_import = {name: rounds for name, rounds in orgs.items() if name.lower() not in existing}
    logger.info("To import: %d (skipping %d already in DB)", len(to_import), len(orgs) - len(to_import))

    # Step 1: Create all startups first
    startup_ids = {}  # name -> (startup_id, rounds)
    created = 0
    async with async_session() as db:
        for name, rounds in to_import.items():
            best_stage = StartupStage.seed
            for r in rounds:
                ft = r.get("Funding Type", "")
                if ft in STAGE_MAP:
                    mapped = STAGE_MAP[ft]
                    if list(StartupStage).index(mapped) > list(StartupStage).index(best_stage):
                        best_stage = mapped

            slug = slugify(name)
            if slug in existing_slugs:
                slug = f"{slug}-{uuid.uuid4().hex[:6]}"
            existing_slugs.add(slug)

            cb_url = rounds[0].get("Organization Name URL", "")
            sid = uuid.uuid4()

            startup = Startup(
                id=sid,
                name=name,
                slug=slug,
                description="Discovered via Crunchbase funding data.",
                stage=best_stage,
                status=StartupStatus.pending,
                crunchbase_url=cb_url if cb_url else None,
            )
            db.add(startup)
            startup_ids[name] = (sid, rounds)
            created += 1

            if created % 200 == 0:
                logger.info("Created %d/%d startups...", created, len(to_import))

        await db.commit()
        logger.info("Committed %d startups", created)

    # Step 2: Add funding rounds
    async with async_session() as db:
        fr_count = 0
        for name, (sid, rounds) in startup_ids.items():
            for idx, r in enumerate(sorted(rounds, key=lambda x: x.get("Announced Date", ""))):
                amount_usd = r.get("Money Raised (in USD)", "")
                fr = StartupFundingRound(
                    id=uuid.uuid4(),
                    startup_id=sid,
                    round_name=r.get("Funding Type", "Unknown"),
                    amount=format_amount(amount_usd),
                    date=r.get("Announced Date", ""),
                    data_source="crunchbase",
                    sort_order=idx,
                )
                db.add(fr)
                fr_count += 1

        await db.commit()
        logger.info("Committed %d funding rounds", fr_count)

    logger.info("DONE — created %d startups as pending", created)


if __name__ == "__main__":
    asyncio.run(main())
