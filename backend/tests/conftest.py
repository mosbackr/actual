import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.session import get_db
from app.main import app as fastapi_app
from app.models.industry import Base
from app.models.user import AuthProvider, User, UserRole
import app.models  # noqa: F401

TEST_DB_URL = settings.database_url


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db(setup_db) -> AsyncGenerator[AsyncSession, None]:
    engine = setup_db
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(setup_db) -> AsyncGenerator[AsyncClient, None]:
    engine = setup_db
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    fastapi_app.dependency_overrides.clear()


def make_jwt_header(user_id: str, email: str = "test@test.com", role: str = "user") -> dict:
    """Create an Authorization header with a test JWT."""
    from jose import jwt as jose_jwt
    token = jose_jwt.encode(
        {"sub": user_id, "email": email, "role": role},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="testuser@example.com",
        name="Test User",
        auth_provider=AuthProvider.google,
        provider_id="google-123",
        role=UserRole.user,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        name="Admin User",
        auth_provider=AuthProvider.google,
        provider_id="google-admin",
        role=UserRole.superadmin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
