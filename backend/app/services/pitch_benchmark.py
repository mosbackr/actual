import logging
import statistics
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pitch_session import PitchBenchmark, PitchSession, PitchSessionStatus

logger = logging.getLogger(__name__)

SCORE_DIMENSIONS = [
    "pitch_clarity",
    "financial_rigor",
    "q_and_a_handling",
    "investor_engagement",
    "fact_accuracy",
    "overall",
]


async def calculate_benchmarks(session_id: uuid.UUID, db: AsyncSession) -> dict:
    """
    Compare this pitch's scores against aggregate and update benchmark table.
    Returns percentile rankings per dimension.
    """
    result = await db.execute(select(PitchSession).where(PitchSession.id == session_id))
    ps = result.scalar_one_or_none()
    if ps is None or not ps.scores:
        return {}

    scores = ps.scores
    percentiles = {}

    for dimension in SCORE_DIMENSIONS:
        score = scores.get(dimension)
        if score is None:
            continue

        # Get all completed sessions' scores for this dimension
        all_result = await db.execute(
            select(PitchSession).where(
                PitchSession.status == PitchSessionStatus.complete,
                PitchSession.scores.isnot(None),
                PitchSession.id != session_id,
            )
        )
        all_sessions = all_result.scalars().all()
        all_scores = []
        for s in all_sessions:
            if s.scores and dimension in s.scores:
                all_scores.append(s.scores[dimension])

        # Add current score
        all_scores.append(score)

        if len(all_scores) < 2:
            percentiles[dimension] = 50  # Not enough data
            continue

        # Calculate percentile
        below = sum(1 for s in all_scores if s < score)
        percentile = int((below / len(all_scores)) * 100)
        percentiles[dimension] = percentile

        # Update benchmark table
        sorted_scores = sorted(all_scores)
        n = len(sorted_scores)
        p25_idx = max(0, int(n * 0.25) - 1)
        p75_idx = min(n - 1, int(n * 0.75))

        benchmark_result = await db.execute(
            select(PitchBenchmark).where(
                PitchBenchmark.dimension == dimension,
                PitchBenchmark.stage.is_(None),
                PitchBenchmark.industry.is_(None),
            )
        )
        benchmark = benchmark_result.scalar_one_or_none()

        if benchmark is None:
            benchmark = PitchBenchmark(
                dimension=dimension,
                stage=None,
                industry=None,
            )
            db.add(benchmark)

        benchmark.sample_count = n
        benchmark.mean_score = round(statistics.mean(all_scores), 1)
        benchmark.median_score = round(statistics.median(all_scores), 1)
        benchmark.p25 = round(sorted_scores[p25_idx], 1)
        benchmark.p75 = round(sorted_scores[p75_idx], 1)

    # Store percentiles on the session
    ps.benchmark_percentiles = percentiles
    await db.commit()

    return percentiles
