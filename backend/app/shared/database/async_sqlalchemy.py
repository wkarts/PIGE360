from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


class AsyncSqlAlchemyDatabase:
    """Adapter oficial para PostgreSQL 16+; não é instanciado no teste SQLite local."""

    def __init__(self, url: str, *, pool_size: int = 10, max_overflow: int = 20):
        if not url.startswith("postgresql+asyncpg://"):
            raise ValueError("O adapter de produção exige postgresql+asyncpg://")
        self.engine: AsyncEngine = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            async with session.begin():
                yield session

    async def dispose(self) -> None:
        await self.engine.dispose()
