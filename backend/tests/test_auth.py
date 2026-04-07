import pytest
from httpx import AsyncClient

from app.models.user import User
from tests.conftest import make_jwt_header


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_authenticated(client: AsyncClient, test_user: User):
    headers = make_jwt_header(str(test_user.id), test_user.email, test_user.role.value)
    resp = await client.get("/api/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "testuser@example.com"
    assert data["role"] == "user"


@pytest.mark.asyncio
async def test_admin_endpoint_requires_superadmin(client: AsyncClient, test_user: User):
    headers = make_jwt_header(str(test_user.id), test_user.email, "user")
    resp = await client.get("/api/admin/users", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_endpoint_allows_superadmin(client: AsyncClient, admin_user: User):
    headers = make_jwt_header(str(admin_user.id), admin_user.email, "superadmin")
    resp = await client.get("/api/admin/users", headers=headers)
    assert resp.status_code == 200
