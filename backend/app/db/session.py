import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.settings import Settings

logger = logging.getLogger(__name__)


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
            # Session-mode pooling caps the WHOLE database at a fixed global
            # connection budget (Supavisor's configured pool_size, currently 15 —
            # unlike transaction mode, which multiplexes many app connections onto
            # few backend ones). SQLAlchemy's unset defaults (pool_size=5,
            # max_overflow=10 => up to 15 per engine) let a single ECS task or
            # AgentCore container exhaust that entire global budget alone — this
            # was live-reproduced 2026-08-17 (EMAXCONNSESSION, every connection
            # attempt failing, including ad-hoc debug scripts). Kept small and
            # explicit so multiple concurrent ECS tasks and AgentCore Runtime
            # containers can share the 15-connection budget instead of one process
            # claiming all of it.
            pool_size=3,
            max_overflow=2,
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


async def release_transaction(session: AsyncSession) -> None:
    """End whatever implicit transaction the last statement opened, without holding the pooled
    connection idle-in-transaction for the rest of a long-running request (E4.4, issue #34).

    `get_db_session` yields one session for a whole FastAPI request, and SQLAlchemy's `AsyncSession`
    autobegins a transaction on first use -- for a driver chat turn, that meant the identity
    lookup's own SELECT opened a transaction that then sat idle-in-transaction for the entire LLM
    think-time (seconds), holding one of only `pool_size=3, max_overflow=2` connections the whole
    turn. The fix is shortening the *hold*, not raising `pool_size` (that would reproduce the
    2026-08-17 `EMAXCONNSESSION` incident this class's own comment documents): call this after
    identity resolution and after every read/write step of a turn, so each statement's transaction
    closes as soon as that statement is done, not whenever the request happens to end.

    Safe after both a read (nothing to commit; this just closes the transaction) and an
    already-committed write (a no-op). Falls back to rollback and never raises -- this is
    connection hygiene, not a business operation whose failure should break the caller's turn.
    """
    try:
        await session.commit()
    except Exception:  # noqa: BLE001
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            logger.warning("Failed to release DB transaction between turn steps", exc_info=True)
