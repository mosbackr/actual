import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expert import ExpertProfile
from app.models.industry import Industry
from app.models.skill import Skill
from app.models.startup import Startup, StartupStage, StartupStatus
from app.models.user import AuthProvider, User, UserRole
from tests.conftest import make_jwt_header


@pytest_asyncio.fixture
async def pending_startup(db: AsyncSession) -> Startup:
    s = Startup(
        id=uuid.uuid4(),
        name="Pending Startup",
        slug="pending-startup",
        description="Awaiting review",
        stage=StartupStage.seed,
        status=StartupStatus.pending,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest_asyncio.fixture
async def expert_applicant(db: AsyncSession) -> tuple[User, ExpertProfile]:
    user = User(
        id=uuid.uuid4(),
        email="applicant@example.com",
        name="Expert Applicant",
        auth_provider=AuthProvider.linkedin,
        provider_id="li-123",
        role=UserRole.user,
    )
    db.add(user)
    await db.flush()
    profile = ExpertProfile(
        id=uuid.uuid4(),
        user_id=user.id,
        bio="10 years in fintech",
        years_experience=10,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(user)
    await db.refresh(profile)
    return user, profile


@pytest.mark.asyncio
async def test_admin_pipeline(client: AsyncClient, admin_user: User, pending_startup: Startup):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get("/api/admin/startups/pipeline", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(s["slug"] == "pending-startup" for s in data)


@pytest.mark.asyncio
async def test_admin_approve_startup(client: AsyncClient, admin_user: User, pending_startup: Startup):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.put(
        f"/api/admin/startups/{pending_startup.id}",
        json={"status": "approved"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_admin_reject_startup(client: AsyncClient, admin_user: User, pending_startup: Startup):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.put(
        f"/api/admin/startups/{pending_startup.id}",
        json={"status": "rejected"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_admin_enrich_startup(client: AsyncClient, admin_user: User, pending_startup: Startup):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.put(
        f"/api/admin/startups/{pending_startup.id}",
        json={"description": "Updated description", "status": "approved"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["description"] == "Updated description"


@pytest.mark.asyncio
async def test_admin_list_expert_applications(client: AsyncClient, admin_user: User, expert_applicant):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get("/api/admin/experts/applications", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_admin_approve_expert(client: AsyncClient, admin_user: User, expert_applicant):
    user, profile = expert_applicant
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.put(f"/api/admin/experts/{profile.id}/approve", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["application_status"] == "approved"


@pytest.mark.asyncio
async def test_admin_reject_expert(client: AsyncClient, admin_user: User, expert_applicant):
    user, profile = expert_applicant
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.put(f"/api/admin/experts/{profile.id}/reject", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["application_status"] == "rejected"


@pytest.mark.asyncio
async def test_non_admin_cannot_access_pipeline(client: AsyncClient, test_user: User):
    headers = make_jwt_header(str(test_user.id), test_user.email, "user")
    resp = await client.get("/api/admin/startups/pipeline", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_pipeline_enriched(
    client: AsyncClient, admin_user: User, pending_startup: Startup, db: AsyncSession,
):
    """Pipeline response includes industry tags, assignment_count, dimensions_configured."""
    from app.models.industry import Industry
    from app.models.startup import startup_industries

    ind = Industry(id=uuid.uuid4(), name="TestInd", slug="testind")
    db.add(ind)
    await db.flush()
    await db.execute(startup_industries.insert().values(
        startup_id=pending_startup.id, industry_id=ind.id,
    ))
    await db.commit()

    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get("/api/admin/startups/pipeline", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    item = next(s for s in data if s["id"] == str(pending_startup.id))
    assert "industries" in item
    assert "assignment_count" in item
    assert "dimensions_configured" in item
    assert len(item["industries"]) == 1


@pytest.mark.asyncio
async def test_admin_users_filter_by_role(client: AsyncClient, admin_user: User, test_user: User):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get("/api/admin/users?role=superadmin", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert all(u["role"] == "superadmin" for u in data)
    assert any(u["id"] == str(admin_user.id) for u in data)
