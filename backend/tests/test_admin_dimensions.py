import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimension import StartupDimension
from app.models.startup import Startup, StartupStage, StartupStatus
from app.models.template import DueDiligenceTemplate, TemplateDimension
from app.models.user import User
from tests.conftest import make_jwt_header


@pytest_asyncio.fixture
async def startup_for_dims(db: AsyncSession) -> Startup:
    s = Startup(
        id=uuid.uuid4(), name="DimTest Startup", slug="dimtest-startup",
        description="For dimension tests", stage=StartupStage.seed, status=StartupStatus.pending,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


@pytest_asyncio.fixture
async def template_for_apply(db: AsyncSession) -> DueDiligenceTemplate:
    t = DueDiligenceTemplate(id=uuid.uuid4(), name="FinTech", slug="fintech", description="FinTech eval")
    db.add(t)
    await db.flush()
    db.add_all([
        TemplateDimension(template_id=t.id, dimension_name="Regulatory Compliance",
            dimension_slug="regulatory-compliance", weight=2.0, sort_order=0),
        TemplateDimension(template_id=t.id, dimension_name="Market Fit",
            dimension_slug="market-fit", weight=1.0, sort_order=1),
    ])
    await db.commit()
    await db.refresh(t)
    return t


@pytest.mark.asyncio
async def test_apply_template(client: AsyncClient, admin_user: User,
    startup_for_dims: Startup, template_for_apply: DueDiligenceTemplate):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.post(f"/api/admin/startups/{startup_for_dims.id}/apply-template",
        json={"template_id": str(template_for_apply.id)}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["dimensions"]) == 2
    assert data["template_id"] == str(template_for_apply.id)


@pytest.mark.asyncio
async def test_get_dimensions(client: AsyncClient, admin_user: User, startup_for_dims: Startup, db: AsyncSession):
    db.add(StartupDimension(startup_id=startup_for_dims.id, dimension_name="Team",
        dimension_slug="team", weight=1.0, sort_order=0))
    await db.commit()
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get(f"/api/admin/startups/{startup_for_dims.id}/dimensions", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["dimension_name"] == "Team"


@pytest.mark.asyncio
async def test_update_dimensions(client: AsyncClient, admin_user: User, startup_for_dims: Startup):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.put(f"/api/admin/startups/{startup_for_dims.id}/dimensions",
        json={"dimensions": [
            {"dimension_name": "Scalability", "weight": 1.5, "sort_order": 0},
            {"dimension_name": "Unit Economics", "weight": 2.0, "sort_order": 1},
        ]}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["dimension_name"] == "Scalability"
    assert data[1]["dimension_slug"] == "unit-economics"


@pytest.mark.asyncio
async def test_apply_template_not_found(client: AsyncClient, admin_user: User, startup_for_dims: Startup):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.post(f"/api/admin/startups/{startup_for_dims.id}/apply-template",
        json={"template_id": str(uuid.uuid4())}, headers=headers)
    assert resp.status_code == 404
