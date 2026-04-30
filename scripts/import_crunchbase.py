"""Import Crunchbase CSV into the startups table with dedup."""
import asyncio
import csv
import re

from sqlalchemy import func, select

from app.db.session import async_session
from app.models.startup import (
    EntityType,
    EnrichmentStatus,
    Startup,
    StartupStage,
    StartupStatus,
)

STAGE_MAP = {
    "pre-seed": "pre_seed",
    "pre_seed": "pre_seed",
    "seed": "seed",
    "series a": "series_a",
    "series b": "series_b",
    "series c": "series_c",
    "series d": "growth",
    "series e": "growth",
    "series f": "growth",
    "growth": "growth",
    "late stage": "growth",
    "ipo": "public",
    "public": "public",
}


def slugify(name):
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def parse_location(loc):
    if not loc:
        return None, None, None
    parts = [p.strip() for p in loc.split(",")]
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    elif len(parts) == 2:
        return parts[0], None, parts[1]
    return parts[0], None, None


def format_funding(raw):
    if not raw:
        return None
    try:
        amt = int(float(raw))
        if amt >= 1_000_000:
            return f"${amt // 1_000_000}M"
        elif amt >= 1_000:
            return f"${amt // 1_000}K"
        return f"${amt}"
    except (ValueError, TypeError):
        return None


async def main():
    rows = []
    with open("/app/crunchbase-mich.csv", "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"Read {len(rows)} rows from CSV")

    async with async_session() as db:
        created = 0
        skipped_dup = 0
        skipped_closed = 0

        for row in rows:
            name = row.get("Organization Name", "").strip()
            if not name:
                continue

            # Skip closed companies
            op_status = row.get("Operating Status", "").strip().lower()
            if op_status in ("closed", "inactive"):
                skipped_closed += 1
                continue

            # Dedup by name (case-insensitive)
            existing = await db.execute(
                select(Startup).where(func.lower(Startup.name) == name.lower())
            )
            if existing.scalar_one_or_none():
                skipped_dup += 1
                continue

            # Also check slug
            slug = slugify(name)
            slug_check = await db.execute(
                select(Startup).where(Startup.slug == slug)
            )
            if slug_check.scalar_one_or_none():
                slug = f"{slug}-{created}"
                # Check again
                slug_check2 = await db.execute(
                    select(Startup).where(Startup.slug == slug)
                )
                if slug_check2.scalar_one_or_none():
                    skipped_dup += 1
                    continue

            # Parse stage
            last_funding = row.get("Last Funding Type", "").strip().lower()
            stage = STAGE_MAP.get(last_funding, "seed")

            # Parse location
            city, state, country = parse_location(
                row.get("Headquarters Location", "")
            )

            # Crunchbase URL
            cb_url = row.get("Organization Name URL", "")

            # Total funding
            total_funding = format_funding(
                row.get("Total Equity Funding Amount (in USD)", "")
            )

            # Employee count
            employees = row.get("Number of Employees", "").strip() or None

            # Lead investors
            lead_investors = row.get("Lead Investors", "").strip() or None

            startup = Startup(
                name=name,
                slug=slug,
                description=row.get("Description", "") or f"{name} startup",
                stage=StartupStage(stage),
                status=StartupStatus.approved,
                entity_type=EntityType.startup,
                enrichment_status=EnrichmentStatus.none,
                location_city=city,
                location_state=state,
                location_country=country or "United States",
                total_funding=total_funding,
                employee_count=employees,
                crunchbase_url=cb_url or None,
                form_sources=["crunchbase"],
                data_sources={
                    "name": "crunchbase",
                    "description": "crunchbase",
                    "stage": "crunchbase",
                    "total_funding": "crunchbase",
                },
            )
            db.add(startup)
            created += 1

            if created % 50 == 0:
                print(f"  Progress: {created} created...")

        await db.commit()
        print(
            f"Done: {created} created, {skipped_dup} duplicates skipped, "
            f"{skipped_closed} closed/inactive skipped"
        )


asyncio.run(main())
