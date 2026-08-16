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
            # DATABASE_URL must point at Supabase's Supavisor SESSION-mode pooler
            # (port 5432), not transaction-mode (6543). In transaction mode,
            # Supavisor can silently swap which physical Postgres backend a
            # connection is routed to between statements without resetting session
            # state, so prepared statements from an unrelated earlier client can
            # still be sitting on that backend — every asyncpg connection always
            # tries to prepare its own handshake/query statements as
            # "__asyncpg_stmt_1__" etc, so this collided deterministically
            # (DuplicatePreparedStatementError) regardless of statement_cache_size
            # or SQLAlchemy-level pooling. Session mode gives each pooled
            # SQLAlchemy connection one stable dedicated backend for its whole
            # lifetime, which is what makes prepared statements safe again.
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
