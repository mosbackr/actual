import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_role
from app.db.session import get_db
from app.models.assignment import AssignmentStatus, StartupAssignment
from app.models.expert import ApplicationStatus, ExpertProfile
from app.models.startup import Startup
from app.models.user import User

router = APIRouter()


class AssignExpertIn(BaseModel):
    expert_id: str


@router.post("/api/admin/startups/{startup_id}/assign-expert", status_code=201)
async def assign_expert(
    startup_id: uuid.UUID,
    body: AssignExpertIn,
    admin: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    # Validate startup exists
    result = await db.execute(select(Startup).where(Startup.id == startup_id))
    startup = result.scalar_one_or_none()
    if startup is None:
        raise HTTPException(status_code=404, detail="Startup not found")

    # Validate expert exists and is approved
    expert_id = uuid.UUID(body.expert_id)
    result = await db.execute(select(ExpertProfile).where(ExpertProfile.id == expert_id))
    expert = result.scalar_one_or_none()
    if expert is None:
        raise HTTPException(status_code=404, detail="Expert not found")
    if expert.application_status != ApplicationStatus.approved:
        raise HTTPException(status_code=400, detail="Expert is not approved")

    assignment = StartupAssignment(
        id=uuid.uuid4(),
        startup_id=startup_id,
        expert_id=expert_id,
        assigned_by=admin.id,
    )
    db.add(assignment)
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


@router.get("/api/admin/startups/{startup_id}/assignments")
async def list_assignments(
    startup_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StartupAssignment).where(StartupAssignment.startup_id == startup_id)
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


@router.delete("/api/admin/assignments/{assignment_id}", status_code=204)
async def delete_assignment(
    assignment_id: uuid.UUID,
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StartupAssignment).where(StartupAssignment.id == assignment_id)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise HTTPException(status_code=404, detail="Assignment not found")
    await db.delete(assignment)
    await db.commit()


@router.get("/api/admin/experts")
async def list_approved_experts(
    _user: User = Depends(require_role("superadmin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ExpertProfile)
        .where(ExpertProfile.application_status == ApplicationStatus.approved)
        .options(selectinload(ExpertProfile.industries), selectinload(ExpertProfile.skills))
    )
    profiles = result.scalars().all()
    return [
        {
            "id": str(p.id),
            "user_id": str(p.user_id),
            "bio": p.bio,
            "years_experience": p.years_experience,
            "application_status": p.application_status.value,
            "industries": [i.name for i in p.industries],
            "skills": [s.name for s in p.skills],
            "created_at": p.created_at.isoformat(),
        }
        for p in profiles
    ]
