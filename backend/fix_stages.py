"""One-off script: infer correct stage from funding rounds already in the DB."""

import asyncio
import re

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.models.startup import Startup, StartupStage
from app.models.funding_round import StartupFundingRound


# Map funding round names → correct stage
ROUND_TO_STAGE: list[tuple[re.Pattern, StartupStage]] = [
    (re.compile(r"ipo|post.ipo|public", re.I), StartupStage.public),
    (re.compile(r"series\s*[d-z]|growth|late|mezzanine|private.equity", re.I), StartupStage.growth),
    (re.compile(r"series\s*c", re.I), StartupStage.series_c),
    (re.compile(r"series\s*b", re.I), StartupStage.series_b),
    (re.compile(r"series\s*a", re.I), StartupStage.series_a),
    (re.compile(r"seed|angel|pre.seed|accelerator|incubator", re.I), StartupStage.seed),
]

# Stage ordering for "highest wins"
STAGE_ORDER = {
    StartupStage.pre_seed: 0,
    StartupStage.seed: 1,
    StartupStage.series_a: 2,
    StartupStage.series_b: 3,
    StartupStage.series_c: 4,
    StartupStage.growth: 5,
    StartupStage.public: 6,
}


def infer_stage(round_name: str) -> StartupStage | None:
    for pattern, stage in ROUND_TO_STAGE:
        if pattern.search(round_name):
            return stage
    return None


async def main():
    async with async_session() as db:
        # Get all startups with their funding rounds
        result = await db.execute(
            select(Startup.id, Startup.name, Startup.stage)
        )
        startups = result.all()

        updated = 0
        unchanged = 0
        no_rounds = 0

        for startup_id, name, current_stage in startups:
            # Get funding rounds for this startup
            rounds_result = await db.execute(
                select(StartupFundingRound.round_name)
                .where(StartupFundingRound.startup_id == startup_id)
            )
            rounds = rounds_result.scalars().all()

            if not rounds:
                no_rounds += 1
                continue

            # Find the highest stage from all rounds
            best_stage = None
            best_order = -1
            for round_name in rounds:
                stage = infer_stage(round_name)
                if stage and STAGE_ORDER[stage] > best_order:
                    best_stage = stage
                    best_order = STAGE_ORDER[stage]

            if best_stage is None:
                continue

            # Only upgrade, never downgrade
            if STAGE_ORDER[best_stage] > STAGE_ORDER.get(current_stage, -1) and best_stage != current_stage:
                print(f"  {name}: {current_stage.value} -> {best_stage.value}  (rounds: {', '.join(rounds)})")
                await db.execute(
                    Startup.__table__.update()
                    .where(Startup.id == startup_id)
                    .values(stage=best_stage)
                )
                updated += 1
            else:
                unchanged += 1

        await db.commit()
        print(f"\nDone. Updated: {updated}, Already correct: {unchanged}, No funding rounds: {no_rounds}")


if __name__ == "__main__":
    asyncio.run(main())
