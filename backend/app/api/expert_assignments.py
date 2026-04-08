import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.db.session import get_db
from app.models.assignment import AssignmentStatus, StartupAssignment
from app.models.expert import ExpertProfile
from app.models.user import User

router = APIRouter()


@router.get("/api/expert/assignments")
async def list_my_assignments(
    user: User = Depends(require_role("expert")),
    db: AsyncSession = Depends(get_db),
):
    # Find the expert profile for this user
    result = await db.execute(
        select(ExpertProfile).where(ExpertProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Expert profile not found")

    result = await db.execute(
        select(StartupAssignment).where(StartupAssignment.expert_id == profile.id)
    )
    assignments = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "startup_id": str(a.startup_id),
            "expert_id": str(a.expert_id),
            "assigned_by": str(a.assigned_by),
            "status": a.status.value,
            "assigned_at": a.assigned_at.isoformat(),
            "responded_at": a.responded_at.isoformat() if a.responded_at else None,
        }
        for a in assignments
    ]


@router.put("/api/expert/assignments/{assignment_id}/accept")
async def accept_assignment(
    assignment_id: uuid.UUID,
    user: User = Depends(require_role("expert")),
    db: AsyncSession = Depends(get_db),
):
    # Find the expert profile for this user
    result = await db.execute(
        select(ExpertProfile).where(ExpertProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Expert profile not found")

    result = await db.execute(
        select(StartupAssignment).where(StartupAssignment.id == assignment_id)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if assignment.expert_id != profile.id:
        raise HTTPException(status_code=403, detail="Not your assignment")

    assignment.status = AssignmentStatus.accepted
    assignment.responded_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(assignment)

    return {
        "id": str(assignment.id),
        "startup_id": str(assignment.startup_id),
        "expert_id": str(assignment.expert_id),
        "assigned_by": str(assignment.assigned_by),
        "status": assignment.status.value,
        "assigned_at": assignment.assigned_at.isoformat(),
        "responded_at": assignment.responded_at.isoformat() if assignment.responded_at else None,
    }


@router.put("/api/expert/assignments/{assignment_id}/decline")
async def decline_assignment(
    assignment_id: uuid.UUID,
    user: User = Depends(require_role("expert")),
    db: AsyncSession = Depends(get_db),
):
    # Find the expert profile for this user
    result = await db.execute(
        select(ExpertProfile).where(ExpertProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Expert profile not found")

    result = await db.execute(
        select(StartupAssignment).where(StartupAssignment.id == assignment_id)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if assignment.expert_id != profile.id:
        raise HTTPException(status_code=403, detail="Not your assignment")

    assignment.status = AssignmentStatus.declined
    assignment.responded_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(assignment)

    return {
        "id": str(assignment.id),
        "startup_id": str(assignment.startup_id),
        "expert_id": str(assignment.expert_id),
        "assigned_by": str(assignment.assigned_by),
        "status": assignment.status.value,
        "assigned_at": assignment.assigned_at.isoformat(),
        "responded_at": assignment.responded_at.isoformat() if assignment.responded_at else None,
    }
