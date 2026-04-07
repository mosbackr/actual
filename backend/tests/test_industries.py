import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.industry import Industry


@pytest_asyncio.fixture
async def industries(db: AsyncSession) -> list[Industry]:
    items = []
    for name, slug in [("Fintech", "fintech"), ("Healthcare", "healthcare")]:
        ind = Industry(id=uuid.uuid4(), name=name, slug=slug)
        db.add(ind)
        items.append(ind)
    await db.commit()
    return items


@pytest.mark.asyncio
async def test_list_industries(client: AsyncClient, industries: list[Industry]):
    resp = await client.get("/api/industries")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] in ["Fintech", "Healthcare"]


@pytest.mark.asyncio
async def test_list_stages(client: AsyncClient):
    resp = await client.get("/api/stages")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 6
    slugs = [s["value"] for s in data]
    assert "seed" in slugs
    assert "pre_seed" in slugs
