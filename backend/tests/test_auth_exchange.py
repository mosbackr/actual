import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AuthProvider, User, UserRole


@pytest.mark.asyncio
async def test_token_exchange_creates_new_user(client: AsyncClient):
    resp = await client.post("/api/auth/token", json={
        "email": "newuser@example.com",
        "name": "New User",
        "provider": "google",
        "provider_id": "google-new-123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["user"]["email"] == "newuser@example.com"
    assert data["user"]["role"] == "user"


@pytest.mark.asyncio
async def test_token_exchange_returns_existing_user(client: AsyncClient, admin_user: User):
    resp = await client.post("/api/auth/token", json={
        "email": admin_user.email,
        "name": admin_user.name,
        "provider": "google",
        "provider_id": "google-admin",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["id"] == str(admin_user.id)
    assert data["user"]["role"] == "superadmin"


@pytest.mark.asyncio
async def test_token_exchange_token_is_valid_jwt(client: AsyncClient):
    resp = await client.post("/api/auth/token", json={
        "email": "jwttest@example.com",
        "name": "JWT Test",
        "provider": "github",
        "provider_id": "gh-456",
    })
    token = resp.json()["token"]
    # Use the token to call /api/me
    me_resp = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "jwttest@example.com"


@pytest.mark.asyncio
async def test_token_exchange_missing_fields(client: AsyncClient):
    resp = await client.post("/api/auth/token", json={"email": "bad@example.com"})
    assert resp.status_code == 422
