import uuid
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.assignment import AssignmentStatus, StartupAssignment
from app.models.expert import ApplicationStatus, ExpertProfile
from app.models.startup import Startup, StartupStage, StartupStatus
from app.models.user import AuthProvider, User, UserRole
from tests.conftest import make_jwt_header

@pytest_asyncio.fixture
async def expert_with_assignment(db: AsyncSession):
    admin = User(id=uuid.uuid4(), email="assigner@example.com", name="Admin",
        auth_provider=AuthProvider.google, provider_id="g-admin2", role=UserRole.superadmin)
    expert_user = User(id=uuid.uuid4(), email="myexpert@example.com", name="My Expert",
        auth_provider=AuthProvider.github, provider_id="gh-expert", role=UserRole.expert)
    db.add_all([admin, expert_user])
    await db.flush()
    profile = ExpertProfile(id=uuid.uuid4(), user_id=expert_user.id, bio="Expert bio",
        years_experience=10, application_status=ApplicationStatus.approved)
    db.add(profile)
    await db.flush()
    startup = Startup(id=uuid.uuid4(), name="Assigned Startup", slug="assigned-startup",
        description="Test", stage=StartupStage.seed, status=StartupStatus.approved)
    db.add(startup)
    await db.flush()
    assignment = StartupAssignment(id=uuid.uuid4(), startup_id=startup.id, expert_id=profile.id, assigned_by=admin.id)
    db.add(assignment)
    await db.commit()
    await db.refresh(expert_user)
    await db.refresh(profile)
    await db.refresh(assignment)
    return expert_user, profile, assignment

@pytest.mark.asyncio
async def test_expert_list_assignments(client: AsyncClient, expert_with_assignment):
    user, profile, assignment = expert_with_assignment
    headers = make_jwt_header(str(user.id), user.email, "expert")
    resp = await client.get("/api/expert/assignments", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["id"] == str(assignment.id)

@pytest.mark.asyncio
async def test_expert_accept_assignment(client: AsyncClient, expert_with_assignment):
    user, profile, assignment = expert_with_assignment
    headers = make_jwt_header(str(user.id), user.email, "expert")
    resp = await client.put(f"/api/expert/assignments/{assignment.id}/accept", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"
    assert resp.json()["responded_at"] is not None

@pytest.mark.asyncio
async def test_expert_decline_assignment(client: AsyncClient, expert_with_assignment):
    user, profile, assignment = expert_with_assignment
    headers = make_jwt_header(str(user.id), user.email, "expert")
    resp = await client.put(f"/api/expert/assignments/{assignment.id}/decline", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "declined"

@pytest.mark.asyncio
async def test_non_expert_cannot_access(client: AsyncClient, test_user: User):
    headers = make_jwt_header(str(test_user.id), test_user.email, "user")
    resp = await client.get("/api/expert/assignments", headers=headers)
    assert resp.status_code == 403
