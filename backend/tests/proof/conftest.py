"""Fixtures and the production-safety guard for the section 10 proof suite.

Design citation: `SOLUTION_DESIGN.md` section 10, section 9.1 (deterministic clock), D16 (backup
before anything destructive). GitHub issue #44.

## The guard, and why it is not paranoia

Every other test directory in this repo either mocks the session or is explicitly gated behind
`SETUHAUL_RUN_LIVE_DB_TESTS=1` against the real database. This one writes -- 50 competing
`request_slot` calls, replayed exceptions, booked appointments -- so "accidentally pointed at
production" is not a degraded run, it is an incident.

Two independent checks, because one is a single point of failure:

1. `run_proof_suite.py` overwrites `DATABASE_URL` and every Supabase/Upstash credential in the
   child environment before pytest starts (OS environment beats a dotenv file in pydantic-settings
   -- verified against the pinned 2.15.0's own documentation, 2026-09-01).
2. This module re-derives the answer from scratch and refuses to collect a single test unless the
   two proof URLs are loopback, carry the orchestrator's own database names, and match the port the
   orchestrator says it opened. A URL pointing anywhere else aborts the session with a message
   naming what was wrong.

The guard runs at import time rather than in a fixture on purpose: a fixture only protects the
tests that request it.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests.proof.evidence import EVIDENCE

# --------------------------------------------------------------------------------------------
# Guard
# --------------------------------------------------------------------------------------------

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}
_ALLOWED_DBS = {"setuhaul_proof_seed", "setuhaul_proof_work"}


NOT_ORCHESTRATED = (
    "the section 10 proof suite needs its own throwaway PostgreSQL cluster; run it through its "
    "orchestrator:  uv run --frozen python docs/scripts/run_proof_suite.py"
)


def _require_throwaway(url: str, *, name: str) -> str:
    """Empty when the variable is simply absent; RuntimeError when it is present but dangerous.

    The two cases are deliberately NOT the same. Absent means "someone ran bare `pytest` and this
    directory got collected along with everything else" -- the honest response is a reported skip
    naming the orchestrator, not a collection error that breaks an unrelated run (`pyproject.toml`
    sets `testpaths = ["tests"]`, so a bare `pytest` really does reach here; CI is scoped to
    `tests/unit` and never does). Present-but-wrong means someone has pointed a suite that fires 50
    competing writes at a database it did not create, and that must abort loudly and immediately.
    """
    if not url:
        return ""
    parsed = urlparse(url)
    problems: list[str] = []
    if (parsed.hostname or "") not in _LOOPBACK:
        problems.append(f"host {parsed.hostname!r} is not loopback")
    dbname = (parsed.path or "").lstrip("/")
    if dbname not in _ALLOWED_DBS:
        problems.append(f"database {dbname!r} is not one this suite creates")
    expected_port = os.environ.get("SETUHAUL_PROOF_PORT", "")
    if expected_port and str(parsed.port or "") != expected_port:
        problems.append(f"port {parsed.port} is not the orchestrator's port {expected_port}")
    if problems:
        raise RuntimeError(
            f"REFUSING TO RUN: {name} does not look like a throwaway cluster "
            f"({'; '.join(problems)}). The section 10 suite writes to the database it is pointed "
            "at and must never be run against production."
        )
    return url


SEED_URL = _require_throwaway(os.environ.get("SETUHAUL_PROOF_SEED_URL", ""), name="SETUHAUL_PROOF_SEED_URL")
WORK_URL = _require_throwaway(os.environ.get("SETUHAUL_PROOF_WORK_URL", ""), name="SETUHAUL_PROOF_WORK_URL")
ORCHESTRATED = bool(SEED_URL and WORK_URL)


def pytest_collection_modifyitems(config, items):  # noqa: ANN001, ARG001
    """Skip -- visibly, with the reason -- rather than error when there is no cluster.

    Never silently absent: `-rs` (or the orchestrator's own runs, which always have a cluster)
    reports the reason verbatim, so "the proof suite did not run" can never be mistaken for "the
    proof suite passed".
    """
    if ORCHESTRATED:
        return
    marker = pytest.mark.skip(reason=NOT_ORCHESTRATED)
    for item in items:
        item.add_marker(marker)


def _async(url: str) -> str:
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


# --------------------------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def proof_settings():
    """Force `get_settings()` to resolve the throwaway cluster, and prove it did.

    `Settings` is `lru_cache`d and reads this repo's real `.env.local`, so the cache is cleared
    first and the resolved value is then asserted rather than assumed -- the whole point of the
    guard above is that nothing here is taken on trust.
    """
    from app.core.settings import get_settings

    if not ORCHESTRATED:
        pytest.skip(NOT_ORCHESTRATED)
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.database_url == WORK_URL, (
        "get_settings() did not resolve the throwaway cluster: "
        f"{settings.database_url!r} != {WORK_URL!r}"
    )
    assert settings.two_phase_hold_enabled is True, (
        "Section 10.1's 1-HELD/49-conflict split is the D2 two-phase contract; the flag is off."
    )
    yield settings
    get_settings.cache_clear()


# --------------------------------------------------------------------------------------------
# Engines and sessions
# --------------------------------------------------------------------------------------------


def _make_engine(url: str, *, pool_size: int, max_overflow: int):
    return create_async_engine(
        _async(url),
        pool_pre_ping=True,
        # asyncpg prepares its own handshake statements per connection; the live app disables the
        # cache because of Supavisor, and matching it here keeps the suite exercising the same
        # driver configuration production runs.
        connect_args={"statement_cache_size": 0},
        pool_size=pool_size,
        max_overflow=max_overflow,
    )


# Every async fixture and every async test in this package is pinned to ONE session-scoped event
# loop (`loop_scope="session"`, plus `pytestmark = pytest.mark.asyncio(loop_scope="session")` at the
# top of each test module). This is not a style preference: asyncpg binds a connection to the loop
# that created it, so a session-scoped engine consumed from pytest-asyncio's default *function*
# scoped loop raises "attached to a different loop" on the second test. pytest-asyncio 1.4.0 sets
# a fixture's loop scope from `asyncio_default_fixture_loop_scope`, which this repo's
# `backend/pyproject.toml` does not set, so it is declared per fixture here instead -- keeping the
# change local to `tests/proof/` rather than altering config the rest of the suite shares.


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def seed_engine():
    """Read path onto the pristine `CREATE DATABASE ... TEMPLATE` copy of the shipped seed."""
    engine = _make_engine(SEED_URL, pool_size=5, max_overflow=5)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def work_engine():
    """Write path. Sized for section 10.1's 50 genuinely simultaneous sessions."""
    engine = _make_engine(WORK_URL, pool_size=60, max_overflow=20)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def seed_session(seed_engine) -> AsyncSession:
    factory = async_sessionmaker(seed_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest.fixture(scope="session")
def work_sessionmaker(work_engine):
    """A factory, not a session: section 10.1 needs 50 *distinct* sessions, not one shared one.

    Session-scoped so that part 1's own session-scoped `race` fixture -- which must run the 50-way
    race exactly once -- can depend on it without a pytest ScopeMismatch.
    """
    return async_sessionmaker(work_engine, expire_on_commit=False)


@pytest_asyncio.fixture(loop_scope="session")
async def work_session(work_sessionmaker) -> AsyncSession:
    async with work_sessionmaker() as session:
        yield session


# --------------------------------------------------------------------------------------------
# Deterministic time
# --------------------------------------------------------------------------------------------

# Section 9.1: "Every test must inject `now` rather than read the wall clock, or the entire suite
# starts failing the day after it is written." The seeded cases all sit on 2026-08-04 IST, so that
# is the instant every seed-relative assertion is evaluated at.
SEED_DAY = datetime(2026, 8, 4, 9, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))


@pytest.fixture(scope="session")
def seed_clock():
    from app.core.clock import FrozenClock

    return FrozenClock(SEED_DAY)


# --------------------------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------------------------

# The store lives in `tests/proof/evidence.py`, not here -- see that module's docstring for why a
# dict defined in this file would have been a *different* dict from the one the test modules write
# to. Only the reporting hook belongs in conftest.
def pytest_terminal_summary(terminalreporter, exitstatus, config):  # noqa: ANN001, ARG001
    if not EVIDENCE:
        return
    terminalreporter.write_sep("=", "SOLUTION_DESIGN.md section 10 -- measured evidence")
    width = max(len(key) for key in EVIDENCE)
    for key in sorted(EVIDENCE):
        terminalreporter.write_line(f"  {key.ljust(width)}  {EVIDENCE[key]}")
