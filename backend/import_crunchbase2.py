"""Import Crunchbase company profiles CSV (4-13-2026 format).

Run inside backend container:
  python import_crunchbase2.py
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

CSV_PATH = "/data/crunchbase-4-13-2026.csv"

STAGE_MAP = {
    "Pre-Seed": StartupStage.pre_seed,
    "Angel": StartupStage.pre_seed,
    "Seed": StartupStage.seed,
    "Series A": StartupStage.series_a,
    "Series B": StartupStage.series_b,
    "Series C": StartupStage.series_c,
    "Series D": StartupStage.growth,
    "Series E": StartupStage.growth,
    "Series F": StartupStage.growth,
    "Series G": StartupStage.growth,
    "Series H": StartupStage.growth,
    "Venture - Series Unknown": StartupStage.seed,
    "Corporate Round": StartupStage.series_a,
    "Private Equity": StartupStage.growth,
    "Post-IPO Equity": StartupStage.public,
    "Post-IPO Debt": StartupStage.public,
    "Debt Financing": StartupStage.series_a,
    "Grant": StartupStage.pre_seed,
    "Convertible Note": StartupStage.seed,
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


def parse_location(loc: str) -> tuple[str | None, str | None, str | None]:
    """Parse 'City, State, Country' into components."""
    if not loc:
        return None, None, None
    parts = [p.strip() for p in loc.split(",")]
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    if len(parts) == 2:
        return parts[0], None, parts[1]
    return None, None, parts[0]


async def main():
    # Parse CSV
    with open(CSV_PATH) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    logger.info("Parsed %d rows from CSV", len(rows))

    # Dedupe by name
    seen = {}
    for row in rows:
        name = row["Organization Name"].strip()
        if name and name not in seen:
            seen[name] = row

    logger.info("Unique companies: %d", len(seen))

    # Get existing names and slugs from DB
    async with async_session() as db:
        result = await db.execute(select(Startup.name))
        existing_names = {r[0].lower() for r in result.all()}
        result = await db.execute(select(Startup.slug))
        existing_slugs = {r[0] for r in result.all()}

    to_import = {n: r for n, r in seen.items() if n.lower() not in existing_names}
    logger.info("To import: %d (skipping %d already in DB)", len(to_import), len(seen) - len(to_import))

    # Step 1: Create startups
    startup_rounds = {}  # name -> (startup_id, row)
    created = 0
    async with async_session() as db:
        for name, row in to_import.items():
            # Stage
            funding_type = row.get("Last Funding Type", "") or row.get("Last Equity Funding Type", "")
            stage = STAGE_MAP.get(funding_type, StartupStage.seed)

            # Slug
            slug = slugify(name)
            if slug in existing_slugs:
                slug = f"{slug}-{uuid.uuid4().hex[:6]}"
            existing_slugs.add(slug)

            # Location
            city, state, country = parse_location(row.get("Headquarters Location", ""))

            # Description
            desc = row.get("Description", "").strip()
            if not desc:
                desc = "Discovered via Crunchbase."

            # CB URL
            cb_url = row.get("Organization Name URL", "")

            # Total funding
            total_funding = format_amount(row.get("Total Equity Funding Amount (in USD)", ""))

            # Employee count
            emp = row.get("Number of Employees", "")

            sid = uuid.uuid4()
            startup = Startup(
                id=sid,
                name=name,
                slug=slug,
                description=desc,
                stage=stage,
                status=StartupStatus.pending,
                location_city=city,
                location_state=state,
                location_country=country or "US",
                crunchbase_url=cb_url if cb_url else None,
                total_funding=total_funding,
                employee_count=emp if emp else None,
            )
            db.add(startup)
            startup_rounds[name] = (sid, row)
            created += 1

            if created % 200 == 0:
                logger.info("Created %d/%d startups...", created, len(to_import))

        await db.commit()
        logger.info("Committed %d startups", created)

    # Step 2: Add funding rounds from last funding data
    async with async_session() as db:
        fr_count = 0
        for name, (sid, row) in startup_rounds.items():
            funding_type = row.get("Last Funding Type", "")
            amount_usd = row.get("Last Funding Amount (in USD)", "")
            lead = row.get("Lead Investors", "")

            if funding_type:
                fr = StartupFundingRound(
                    id=uuid.uuid4(),
                    startup_id=sid,
                    round_name=funding_type,
                    amount=format_amount(amount_usd),
                    lead_investor=lead if lead else None,
                    data_source="crunchbase",
                    sort_order=0,
                )
                db.add(fr)
                fr_count += 1

        await db.commit()
        logger.info("Committed %d funding rounds", fr_count)

    # Step 3: Approve all
    async with async_session() as db:
        from sqlalchemy import update
        await db.execute(
            update(Startup)
            .where(Startup.id.in_([sid for sid, _ in startup_rounds.values()]))
            .values(status=StartupStatus.approved)
        )
        await db.commit()
        logger.info("Approved all %d startups", created)

    logger.info("DONE — %d companies imported and approved", created)


if __name__ == "__main__":
    asyncio.run(main())
