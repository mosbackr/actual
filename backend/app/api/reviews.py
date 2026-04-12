import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_current_user_or_none
from app.db.session import get_db
from app.models.review import ReviewType, ReviewVote, StartupReview, VoteType
from app.models.startup import Startup
from app.models.user import User, UserRole

router = APIRouter()


class ReviewIn(BaseModel):
    overall_score: float
    dimension_scores: dict | None = None
    comment: str | None = None


class VoteIn(BaseModel):
    vote_type: str  # "up" or "down"


def _review_dict(review: StartupReview, current_user_vote: str | None = None) -> dict:
    return {
        "id": str(review.id),
        "startup_id": str(review.startup_id),
        "user_id": str(review.user_id),
        "user_name": review.user.name if review.user else None,
        "review_type": review.review_type.value,
        "overall_score": review.overall_score,
        "dimension_scores": review.dimension_scores,
        "comment": review.comment,
        "upvotes": review.upvotes,
        "downvotes": review.downvotes,
        "current_user_vote": current_user_vote,
        "created_at": review.created_at.isoformat(),
    }


@router.get("/api/startups/{slug}/reviews")
async def get_reviews(
    slug: str,
    review_type: str | None = None,
    user: User | None = Depends(get_current_user_or_none),
    db: AsyncSession = Depends(get_db),
):
    """Get reviews for a startup. Optionally filter by review_type (contributor/community)."""
    result = await db.execute(select(Startup).where(Startup.slug == slug))
    startup = result.scalar_one_or_none()
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")

    query = (
        select(StartupReview)
        .where(StartupReview.startup_id == startup.id)
        .options(selectinload(StartupReview.user))
        .order_by(StartupReview.created_at.desc())
    )
    if review_type:
        query = query.where(StartupReview.review_type == review_type)

    result = await db.execute(query)
    reviews = result.scalars().all()

    # Get current user's votes if authenticated
    user_votes: dict[str, str] = {}
    if user:
        vote_result = await db.execute(
            select(ReviewVote).where(
                ReviewVote.review_id.in_([r.id for r in reviews]),
                ReviewVote.user_id == user.id,
            )
        )
        for vote in vote_result.scalars().all():
            user_votes[str(vote.review_id)] = vote.vote_type.value

    return [_review_dict(r, user_votes.get(str(r.id))) for r in reviews]


@router.post("/api/startups/{slug}/reviews", status_code=201)
async def create_review(
    slug: str,
    body: ReviewIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a review. Contributors create contributor reviews, regular users create community reviews."""
    result = await db.execute(select(Startup).where(Startup.slug == slug))
    startup = result.scalar_one_or_none()
    if not startup:
        raise HTTPException(status_code=404, detail="Startup not found")

    if body.overall_score < 0 or body.overall_score > 100:
        raise HTTPException(status_code=400, detail="Score must be between 0 and 100")

    # Determine review type based on user role
    if user.role in (UserRole.expert, UserRole.superadmin):
        review_type = ReviewType.contributor
    else:
        review_type = ReviewType.community

    # Check if user already reviewed this startup in this category
    existing = await db.execute(
        select(StartupReview).where(
            StartupReview.startup_id == startup.id,
            StartupReview.user_id == user.id,
            StartupReview.review_type == review_type,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="You already reviewed this startup")

    review = StartupReview(
        id=uuid.uuid4(),
        startup_id=startup.id,
        user_id=user.id,
        review_type=review_type,
        overall_score=body.overall_score,
        dimension_scores=body.dimension_scores,
        comment=body.comment,
    )
    db.add(review)

    # Recalculate aggregate score
    await _update_aggregate_score(db, startup, review_type)

    await db.commit()

    # Re-fetch with user loaded
    result = await db.execute(
        select(StartupReview)
        .where(StartupReview.id == review.id)
        .options(selectinload(StartupReview.user))
    )
    review = result.scalar_one()
    return _review_dict(review)


@router.post("/api/reviews/{review_id}/vote")
async def vote_on_review(
    review_id: uuid.UUID,
    body: VoteIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Vote on a review. Contributors vote on contributor reviews, users on community reviews."""
    if body.vote_type not in ("up", "down"):
        raise HTTPException(status_code=400, detail="vote_type must be 'up' or 'down'")

    result = await db.execute(
        select(StartupReview)
        .where(StartupReview.id == review_id)
        .options(selectinload(StartupReview.user))
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # Check permission: contributors vote on contributor reviews, users on community reviews
    is_contributor = user.role in (UserRole.expert, UserRole.superadmin)
    if review.review_type == ReviewType.contributor and not is_contributor:
        raise HTTPException(status_code=403, detail="Only contributors can vote on contributor reviews")
    if review.review_type == ReviewType.community and is_contributor:
        # Contributors CAN read community reviews but voting is for community members
        # Actually let's allow contributors to also be community members
        pass

    # Check for existing vote
    existing = await db.execute(
        select(ReviewVote).where(
            ReviewVote.review_id == review_id,
            ReviewVote.user_id == user.id,
        )
    )
    existing_vote = existing.scalar_one_or_none()

    new_vote_type = VoteType.up if body.vote_type == "up" else VoteType.down

    if existing_vote:
        if existing_vote.vote_type == new_vote_type:
            # Same vote = remove it (toggle off)
            if existing_vote.vote_type == VoteType.up:
                review.upvotes = max(0, review.upvotes - 1)
            else:
                review.downvotes = max(0, review.downvotes - 1)
            await db.delete(existing_vote)
        else:
            # Different vote = switch
            if existing_vote.vote_type == VoteType.up:
                review.upvotes = max(0, review.upvotes - 1)
                review.downvotes += 1
            else:
                review.downvotes = max(0, review.downvotes - 1)
                review.upvotes += 1
            existing_vote.vote_type = new_vote_type
    else:
        # New vote
        vote = ReviewVote(
            id=uuid.uuid4(),
            review_id=review_id,
            user_id=user.id,
            vote_type=new_vote_type,
        )
        db.add(vote)
        if new_vote_type == VoteType.up:
            review.upvotes += 1
        else:
            review.downvotes += 1

    await db.commit()

    # Get user's current vote state after commit
    vote_result = await db.execute(
        select(ReviewVote).where(
            ReviewVote.review_id == review_id,
            ReviewVote.user_id == user.id,
        )
    )
    current_vote = vote_result.scalar_one_or_none()

    return _review_dict(review, current_vote.vote_type.value if current_vote else None)


async def _update_aggregate_score(db: AsyncSession, startup: Startup, review_type: ReviewType):
    """Recalculate aggregate score for a startup based on all reviews of a given type."""
    result = await db.execute(
        select(func.avg(StartupReview.overall_score))
        .where(
            StartupReview.startup_id == startup.id,
            StartupReview.review_type == review_type,
        )
    )
    avg_score = result.scalar()

    if review_type == ReviewType.contributor:
        startup.expert_score = round(avg_score, 1) if avg_score else None
    else:
        startup.user_score = round(avg_score, 1) if avg_score else None
