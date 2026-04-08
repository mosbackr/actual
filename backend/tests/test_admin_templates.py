import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import DueDiligenceTemplate, TemplateDimension
from app.models.user import User
from app.utils import slugify
from tests.conftest import make_jwt_header


@pytest_asyncio.fixture
async def sample_template(db: AsyncSession) -> DueDiligenceTemplate:
    t = DueDiligenceTemplate(
        id=uuid.uuid4(),
        name="SaaS",
        slug="saas",
        description="SaaS startup evaluation",
    )
    db.add(t)
    await db.flush()
    dims = [
        TemplateDimension(
            template_id=t.id,
            dimension_name="Market Size",
            dimension_slug="market-size",
            weight=1.5,
            sort_order=0,
        ),
        TemplateDimension(
            template_id=t.id,
            dimension_name="Technical Moat",
            dimension_slug="technical-moat",
            weight=1.0,
            sort_order=1,
        ),
    ]
    db.add_all(dims)
    await db.commit()
    await db.refresh(t)
    return t


@pytest.mark.asyncio
async def test_list_templates(client: AsyncClient, admin_user: User, sample_template: DueDiligenceTemplate):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get("/api/admin/dd-templates", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(t["slug"] == "saas" for t in data)


@pytest.mark.asyncio
async def test_create_template(client: AsyncClient, admin_user: User):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.post("/api/admin/dd-templates", json={
        "name": "BioTech",
        "description": "Biotech startup evaluation",
        "dimensions": [
            {"dimension_name": "Regulatory Path", "weight": 2.0, "sort_order": 0},
            {"dimension_name": "Clinical Pipeline", "weight": 1.5, "sort_order": 1},
        ],
    }, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "BioTech"
    assert data["slug"] == "biotech"
    assert len(data["dimensions"]) == 2
    assert data["dimensions"][0]["dimension_slug"] == "regulatory-path"


@pytest.mark.asyncio
async def test_get_template(client: AsyncClient, admin_user: User, sample_template: DueDiligenceTemplate):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get(f"/api/admin/dd-templates/{sample_template.id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "SaaS"
    assert len(data["dimensions"]) == 2


@pytest.mark.asyncio
async def test_update_template(client: AsyncClient, admin_user: User, sample_template: DueDiligenceTemplate):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.put(f"/api/admin/dd-templates/{sample_template.id}", json={
        "name": "SaaS Updated",
        "description": "Updated description",
        "dimensions": [
            {"dimension_name": "Revenue Model", "weight": 2.0, "sort_order": 0},
        ],
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "SaaS Updated"
    assert len(data["dimensions"]) == 1
    assert data["dimensions"][0]["dimension_name"] == "Revenue Model"


@pytest.mark.asyncio
async def test_delete_template(client: AsyncClient, admin_user: User, sample_template: DueDiligenceTemplate):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.delete(f"/api/admin/dd-templates/{sample_template.id}", headers=headers)
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_delete_template_in_use(
    client: AsyncClient, admin_user: User, sample_template: DueDiligenceTemplate, db: AsyncSession
):
    from app.models.startup import Startup, StartupStage, StartupStatus
    s = Startup(
        id=uuid.uuid4(), name="TestCo", slug="testco", description="Test",
        stage=StartupStage.seed, status=StartupStatus.pending,
        template_id=sample_template.id,
    )
    db.add(s)
    await db.commit()
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.delete(f"/api/admin/dd-templates/{sample_template.id}", headers=headers)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_non_admin_cannot_access_templates(client: AsyncClient, test_user: User):
    headers = make_jwt_header(str(test_user.id), test_user.email, "user")
    resp = await client.get("/api/admin/dd-templates", headers=headers)
    assert resp.status_code == 403
