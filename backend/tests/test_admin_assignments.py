import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.assignment import StartupAssignment, AssignmentStatus
from app.models.expert import ApplicationStatus, ExpertProfile
from app.models.startup import Startup, StartupStage, StartupStatus
from app.models.user import AuthProvider, User, UserRole
from tests.conftest import make_jwt_header

@pytest_asyncio.fixture
async def approved_expert(db: AsyncSession) -> tuple[User, ExpertProfile]:
    user = User(id=uuid.uuid4(), email="expert@example.com", name="Expert User",
        auth_provider=AuthProvider.linkedin, provider_id="li-expert", role=UserRole.expert)
    db.add(user)
    await db.flush()
    profile = ExpertProfile(id=uuid.uuid4(), user_id=user.id, bio="Domain expert",
        years_experience=15, application_status=ApplicationStatus.approved)
    db.add(profile)
    await db.commit()
    await db.refresh(user)
    await db.refresh(profile)
    return user, profile

@pytest_asyncio.fixture
async def assignable_startup(db: AsyncSession) -> Startup:
    s = Startup(id=uuid.uuid4(), name="Assignable Co", slug="assignable-co",
        description="For assignment tests", stage=StartupStage.series_a, status=StartupStatus.approved)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s

@pytest.mark.asyncio
async def test_assign_expert(client: AsyncClient, admin_user: User, approved_expert: tuple, assignable_startup: Startup):
    _, profile = approved_expert
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.post(f"/api/admin/startups/{assignable_startup.id}/assign-expert",
        json={"expert_id": str(profile.id)}, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["expert_id"] == str(profile.id)

@pytest.mark.asyncio
async def test_list_assignments(client: AsyncClient, admin_user: User, approved_expert: tuple, assignable_startup: Startup, db: AsyncSession):
    _, profile = approved_expert
    db.add(StartupAssignment(startup_id=assignable_startup.id, expert_id=profile.id, assigned_by=admin_user.id))
    await db.commit()
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get(f"/api/admin/startups/{assignable_startup.id}/assignments", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

@pytest.mark.asyncio
async def test_delete_assignment(client: AsyncClient, admin_user: User, approved_expert: tuple, assignable_startup: Startup, db: AsyncSession):
    _, profile = approved_expert
    assignment = StartupAssignment(id=uuid.uuid4(), startup_id=assignable_startup.id, expert_id=profile.id, assigned_by=admin_user.id)
    db.add(assignment)
    await db.commit()
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.delete(f"/api/admin/assignments/{assignment.id}", headers=headers)
    assert resp.status_code == 204

@pytest.mark.asyncio
async def test_list_approved_experts(client: AsyncClient, admin_user: User, approved_expert: tuple):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get("/api/admin/experts", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["application_status"] == "approved"
