"""Shared fixtures for unit tests that need a test database."""

from unittest.mock import patch

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 -- register all models with metadata
from app.db import Base


@pytest_asyncio.fixture
async def test_session_factory():
    """Create an in-memory SQLite async engine and return a patched session factory.

    Patches ``app.db.async_session_factory`` so that any code importing it
    (e.g. AuditWriter) transparently uses the test database.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    with patch("app.db.async_session_factory", factory):
        yield factory

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
