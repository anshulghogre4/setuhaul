"""The write site for `users.invite_accepted_at` (issue #73).

**Why this file exists at all.** `users.last_login_ts` is read in two places
(`account_service.get_account_profile`, `admin_user_service.list_users`) and written **nowhere in
the application** -- only `supabase/seed.sql` sets it. That is the entire reason the admin
console's pending-invitation badge was reported as permanently wrong: `last_login_ts IS NULL` was
the only available proxy and it is NULL forever for every post-seed user.

`invite_accepted_at` is a column of the same shape in the same table, so the risk of repeating
that defect is not hypothetical. These tests exist to pin the *writer*, not the schema:

  * that `get_execution_context` -- the FastAPI dependency every authenticated request resolves --
    stamps it on the first authenticated request an invited user makes,
  * that it does **not** stamp a seeded/pre-existing account (`invited_at IS NULL`),
  * that it does **not** re-stamp an already-accepted one, and
  * that a plain identity resolution costs no extra statement in the steady state.

If a future change moves the stamp to a client-called endpoint, or to something a caller can
forget, these tests fail -- which is the point.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import deps
from app.core.deps import get_execution_context
from app.core.settings import Settings

AUTH_SUBJECT = "11111111-2222-3333-4444-555555555555"


def _identity_row(**overrides):
    row = {
        "user_id": "USR-NEW-1",
        "email": "amit.d@setuhaul.com",
        "full_name": "amit.d",
        "role_id": "ROL003",
        "role_name": "WAREHOUSE_PLANNER",
        "driver_id": None,
        "facility_id": "FAC-JAI-01",
        "is_active": 1,
        "auth_user_id": AUTH_SUBJECT,
        "invited_at": "2026-08-30T09:00:00+00:00",
        "invite_accepted_at": None,
    }
    row.update(overrides)
    return row


def _session_returning(row) -> AsyncMock:
    """One mock session whose first `execute` answers the identity SELECT and whose subsequent
    calls answer nothing -- so `session.execute.call_args_list` is a faithful record of exactly
    how many statements identity resolution issued."""
    first = MagicMock()
    first.mappings.return_value.first.return_value = row
    blank = MagicMock()
    blank.mappings.return_value.first.return_value = None
    calls = {"n": 0}

    def _side_effect(*_a, **_k):
        calls["n"] += 1
        return first if calls["n"] == 1 else blank

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_side_effect)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


class _Verifier:
    def verify_access_token(self, _token: str) -> dict:
        return {"sub": AUTH_SUBJECT}


def _request() -> MagicMock:
    request = MagicMock()
    request.state.request_id = "req-1"
    return request


async def _resolve(session) -> object:
    return await get_execution_context(
        _request(), Settings(), _Verifier(), session, authorization=f"Bearer {'x' * 20}"
    )


def _statements(session) -> list[str]:
    return [str(call.args[0]) for call in session.execute.call_args_list]


@pytest.fixture(autouse=True)
def _no_op_release(monkeypatch):
    """`release_transaction` commits; nothing here needs a real commit, and stubbing it keeps the
    statement count in `session.execute` clean."""
    monkeypatch.setattr(deps, "release_transaction", AsyncMock())


@pytest.mark.asyncio
async def test_first_authenticated_request_stamps_invite_accepted_at():
    """The acceptance signal, observed rather than reported.

    A JWT whose `sub` matches this row's `auth_user_id` cannot exist until GoTrue itself accepted
    the invite token and issued a session, so reaching this dependency IS the acceptance.
    """
    session = _session_returning(_identity_row())
    ctx = await _resolve(session)

    assert ctx.user_id == "USR-NEW-1"
    statements = _statements(session)
    assert len(statements) == 2, statements
    update = session.execute.call_args_list[1]
    assert "UPDATE public.users SET invite_accepted_at" in str(update.args[0])
    assert update.args[1]["user_id"] == "USR-NEW-1"
    assert isinstance(update.args[1]["accepted_at"], datetime)
    assert update.args[1]["accepted_at"].tzinfo is not None


@pytest.mark.asyncio
async def test_the_update_is_also_guarded_in_sql_not_only_in_python():
    """Two concurrent first requests both read NULL. The WHERE predicate makes the loser a no-op
    instead of sliding the recorded acceptance instant forward."""
    session = _session_returning(_identity_row())
    await _resolve(session)
    assert "AND invite_accepted_at IS NULL" in str(session.execute.call_args_list[1].args[0])


@pytest.mark.asyncio
async def test_an_already_accepted_user_costs_no_extra_statement():
    """The steady state -- every request after the first, for the life of the account. Both guard
    columns ride the identity SELECT that already runs, so this must stay at one statement."""
    session = _session_returning(_identity_row(invite_accepted_at="2026-08-30T12:00:00+00:00"))
    await _resolve(session)
    assert len(_statements(session)) == 1


@pytest.mark.asyncio
async def test_a_seeded_account_is_never_stamped():
    """`invited_at IS NULL` means the account predates this console and was never invited through
    it. Stamping it would be meaningless, and it would violate the migration's own
    `users_accept_implies_invite_chk`."""
    session = _session_returning(_identity_row(invited_at=None))
    await _resolve(session)
    assert len(_statements(session)) == 1


@pytest.mark.asyncio
async def test_a_carrier_user_still_resolves_its_scope_and_gets_stamped():
    """The CARRIER branch issues its own `user_scopes` lookup between the SELECT and the stamp --
    checked so the extra statement did not land in the wrong order or displace the scope read."""
    session = _session_returning(
        _identity_row(role_name="CARRIER", facility_id=None, driver_id=None)
    )
    await _resolve(session)
    statements = _statements(session)
    assert len(statements) == 3, statements
    assert "public.user_scopes" in statements[1]
    assert "UPDATE public.users SET invite_accepted_at" in statements[2]


@pytest.mark.asyncio
async def test_a_disabled_user_is_refused_before_any_stamp_is_written():
    """A deactivated invitee must not have acceptance recorded on the way to a 403 -- the stamp
    would survive the refusal and quietly change what the Users tab renders."""
    from app.core.errors import AppError

    session = _session_returning(_identity_row(is_active=0))
    with pytest.raises(AppError) as exc:
        await _resolve(session)
    assert exc.value.code == "USER_DISABLED"
    assert len(_statements(session)) == 1
