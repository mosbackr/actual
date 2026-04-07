import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.industry import Industry
from app.models.skill import Skill
from app.models.user import User
from tests.conftest import make_jwt_header


@pytest_asyncio.fixture
async def industry_and_skill(db: AsyncSession):
    ind = Industry(id=uuid.uuid4(), name="Fintech", slug="fintech")
    skill = Skill(id=uuid.uuid4(), name="Go-to-Market Strategy", slug="go-to-market-strategy")
    db.add_all([ind, skill])
    await db.commit()
    await db.refresh(ind)
    await db.refresh(skill)
    return ind, skill


@pytest.mark.asyncio
async def test_apply_as_expert(client: AsyncClient, test_user: User, industry_and_skill):
    ind, skill = industry_and_skill
    headers = make_jwt_header(str(test_user.id), test_user.email, "user")
    resp = await client.post(
        "/api/experts/apply",
        json={
            "bio": "10 years in fintech consulting",
            "years_experience": 10,
            "industry_ids": [str(ind.id)],
            "skill_ids": [str(skill.id)],
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["application_status"] == "pending"
    assert data["bio"] == "10 years in fintech consulting"


@pytest.mark.asyncio
async def test_apply_unauthenticated(client: AsyncClient, industry_and_skill):
    ind, skill = industry_and_skill
    resp = await client.post(
        "/api/experts/apply",
        json={
            "bio": "test",
            "years_experience": 5,
            "industry_ids": [str(ind.id)],
            "skill_ids": [str(skill.id)],
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_check_application_status(client: AsyncClient, test_user: User, industry_and_skill):
    ind, skill = industry_and_skill
    headers = make_jwt_header(str(test_user.id), test_user.email, "user")
    # Apply first
    await client.post(
        "/api/experts/apply",
        json={
            "bio": "experienced",
            "years_experience": 8,
            "industry_ids": [str(ind.id)],
            "skill_ids": [str(skill.id)],
        },
        headers=headers,
    )
    # Check status
    resp = await client.get("/api/expert/applications/mine", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["application_status"] == "pending"
