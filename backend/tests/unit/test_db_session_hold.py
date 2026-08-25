"""E4.4 (issue #34, M4) tests: `release_transaction` and the three points it is wired into --
identity resolution (`get_execution_context`), the operational-context prefetch, and each tool
call inside a turn's round loop. Live end-to-end behaviour (a real Postgres connection actually
leaving `in_transaction()` state) was independently verified against production before writing
these -- see the CHANGELOG/handoff entry for this epic; these are the fast, repeatable unit-level
guards that keep it that way.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.session import release_transaction


# ---------------------------------------------------------------------------------------------
# release_transaction itself
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_transaction_commits_the_session():
    session = AsyncMock()
    await release_transaction(session)
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_release_transaction_falls_back_to_rollback_on_a_commit_failure():
    session = AsyncMock()
    session.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    await release_transaction(session)
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_transaction_never_raises_even_if_rollback_also_fails():
    session = AsyncMock()
    session.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    session.rollback = AsyncMock(side_effect=RuntimeError("rollback failed too"))
    # Must not raise -- this is connection hygiene, never a reason to fail the caller's turn.
    await release_transaction(session)


# ---------------------------------------------------------------------------------------------
# get_execution_context releases the identity-lookup transaction.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_execution_context_releases_the_transaction_after_identity_resolution(monkeypatch):
    from app.core import deps
    from app.core.execution_context import RoleName
    from app.core.settings import Settings

    class _FakeVerifier:
        def verify_access_token(self, _token):
            return {"sub": "auth-uuid-1"}

    session = AsyncMock()
    user_row = {
        "user_id": "USR001", "email": "d@setuhaul.com", "full_name": "Driver",
        "role_id": "ROL001", "role_name": "DRIVER", "driver_id": "DRV001",
        "facility_id": "FAC-JAI-01", "is_active": 1, "auth_user_id": "auth-uuid-1",
    }
    result = MagicMock()
    result.mappings.return_value.first.return_value = user_row
    session.execute = AsyncMock(return_value=result)

    request = MagicMock()
    request.state.request_id = "req-1"

    ctx = await deps.get_execution_context(
        request=request, settings=Settings(), verifier=_FakeVerifier(), session=session,
        authorization="Bearer sometoken",
    )

    assert ctx.role_name == RoleName.DRIVER
    session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------------------------
# _execute_tool_round releases the transaction after every tool call.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_tool_round_releases_the_transaction_after_each_tool_call():
    from app.assistant.run_assistant import TurnState, _execute_tool_round
    from app.assistant.observability import TurnLatency

    class _FakeTool:
        name = "get_my_shipment"
        args_schema = None

        async def ainvoke(self, _args, config=None):
            return '{"code": "OK"}'

    session = AsyncMock()
    tool_calls = [{"name": "get_my_shipment", "args": {}, "id": "call1"}]

    await _execute_tool_round(
        session=session, tool_calls=tool_calls, tool_map={"get_my_shipment": _FakeTool()},
        invoke_config=None, state=TurnState(), turn=TurnLatency(),
    )

    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_tool_round_releases_the_transaction_even_after_a_tool_error():
    from app.assistant.run_assistant import TurnState, _execute_tool_round
    from app.assistant.observability import TurnLatency

    class _FailingTool:
        name = "get_my_shipment"
        args_schema = None

        async def ainvoke(self, _args, config=None):
            raise RuntimeError("db exploded")

    session = AsyncMock()
    tool_calls = [{"name": "get_my_shipment", "args": {}, "id": "call1"}]

    await _execute_tool_round(
        session=session, tool_calls=tool_calls, tool_map={"get_my_shipment": _FailingTool()},
        invoke_config=None, state=TurnState(), turn=TurnLatency(),
    )

    # The transaction is released even though the tool itself raised -- a failed read/write must
    # not leave the connection idle-in-transaction any more than a successful one would.
    session.commit.assert_awaited_once()
