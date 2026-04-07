import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.industry import Industry
from app.models.startup import Startup, StartupStage, StartupStatus


@pytest_asyncio.fixture
async def sample_industry(db: AsyncSession) -> Industry:
    ind = Industry(id=uuid.uuid4(), name="Fintech", slug="fintech")
    db.add(ind)
    await db.commit()
    await db.refresh(ind)
    return ind


@pytest_asyncio.fixture
async def sample_startups(db: AsyncSession, sample_industry: Industry) -> list[Startup]:
    startups = []
    for i in range(3):
        s = Startup(
            id=uuid.uuid4(),
            name=f"Startup {i}",
            slug=f"startup-{i}",
            description=f"Description for startup {i}",
            stage=StartupStage.seed,
            status=StartupStatus.approved,
            ai_score=50.0 + i * 10,
        )
        s.industries.append(sample_industry)
        db.add(s)
        startups.append(s)
    # Add a pending startup that should NOT appear in public list
    pending = Startup(
        id=uuid.uuid4(),
        name="Pending Co",
        slug="pending-co",
        description="Not approved yet",
        stage=StartupStage.pre_seed,
        status=StartupStatus.pending,
    )
    db.add(pending)
    await db.commit()
    return startups


@pytest.mark.asyncio
async def test_list_startups(client: AsyncClient, sample_startups: list[Startup]):
    resp = await client.get("/api/startups")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3  # only approved startups
    assert len(data["items"]) == 3


@pytest.mark.asyncio
async def test_list_startups_filter_by_stage(client: AsyncClient, sample_startups: list[Startup]):
    resp = await client.get("/api/startups", params={"stage": "seed"})
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


@pytest.mark.asyncio
async def test_list_startups_filter_by_industry(client: AsyncClient, sample_startups: list[Startup], sample_industry: Industry):
    resp = await client.get("/api/startups", params={"industry": sample_industry.slug})
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


@pytest.mark.asyncio
async def test_list_startups_search(client: AsyncClient, sample_startups: list[Startup]):
    resp = await client.get("/api/startups", params={"q": "Startup 1"})
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_list_startups_sort_by_ai_score(client: AsyncClient, sample_startups: list[Startup]):
    resp = await client.get("/api/startups", params={"sort": "ai_score"})
    assert resp.status_code == 200
    items = resp.json()["items"]
    scores = [i["ai_score"] for i in items if i["ai_score"] is not None]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_get_startup_detail(client: AsyncClient, sample_startups: list[Startup]):
    resp = await client.get(f"/api/startups/{sample_startups[0].slug}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Startup 0"
    assert "media" in data
    assert "score_history" in data


@pytest.mark.asyncio
async def test_get_startup_not_found(client: AsyncClient):
    resp = await client.get("/api/startups/nonexistent")
    assert resp.status_code == 404
