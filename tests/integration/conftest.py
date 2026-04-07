"""Shared fixtures for integration tests.

Provides:
    db_engine -- async SQLAlchemy engine backed by an in-memory SQLite database.
    db_session -- async database session bound to the test engine.
    client -- httpx AsyncClient wired to the FastAPI app with the test DB override.
    admin_headers -- Authorization headers for an auto-admin user.
    auth_headers -- Authorization headers for a regular (non-admin) user.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Import all models to register them with Base.metadata
import app.models  # noqa: F401
from app.db import Base, get_db
from app.main import app as fastapi_app

TEST_DB_URL = "sqlite+aiosqlite://"


@pytest_asyncio.fixture
async def db_engine():
    """Create an in-memory SQLite async engine with all tables, then tear down after the test.

    Returns:
        AsyncEngine: A fully-initialised async SQLAlchemy engine.
    """
    engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Yield an async database session scoped to a single test.

    Args:
        db_engine: The async engine fixture providing the in-memory database.

    Returns:
        AsyncSession: A session connected to the test database.
    """
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session):
    """Provide an httpx AsyncClient configured to talk to the FastAPI app.

    The FastAPI dependency for ``get_db`` is overridden so that all requests
    use the test database session.

    Args:
        db_session: The async session fixture.

    Returns:
        AsyncClient: An HTTP client pointed at the test application.
    """

    async def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as c:
        yield c
    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_headers(client):
    """Register the first user (auto-admin) and return auth headers."""
    resp = await client.post(
        "/api/auth/register",
        json={
            "first_name": "Admin",
            "last_name": "User",
            "email": "admin@test.com",
            "password": "AdminPass1",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def auth_headers(client, admin_headers):
    """Register a second user (regular user) and return auth headers."""
    resp = await client.post(
        "/api/auth/register",
        json={
            "first_name": "Test",
            "last_name": "User",
            "email": "user@test.com",
            "password": "UserPass1",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
