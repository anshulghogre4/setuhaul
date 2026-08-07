from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.settings import Settings


def _normalize_async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


class Database:
    def __init__(self) -> None:
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None

    def configure(self, settings: Settings) -> None:
        if not settings.database_url:
            self.engine = None
            self.session_factory = None
            return
        self.engine = create_async_engine(
            _normalize_async_url(settings.database_url),
            pool_pre_ping=True,
            # Supabase transaction pooler (PgBouncer) rejects named prepared statements.
            connect_args={"statement_cache_size": 0},
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        if self.session_factory is None:
            raise RuntimeError("Database is not configured.")
        async with self.session_factory() as session:
            yield session

    async def ping(self) -> bool:
        if self.engine is None:
            return False
        async with self.engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True

    async def dispose(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()


db = Database()
