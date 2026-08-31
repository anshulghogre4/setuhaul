"""E3.4 (issue #28, M3) tests for the SS7.5.7 admin console: users/roles, facility rules,
policy simulate/publish, and audit.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.core.settings import Settings
from app.services import admin_governance_service, admin_user_service

FACILITY = "FAC-JAI-01"


def _admin_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="r", auth_subject="s", user_id="USR-ADMIN-1", email="admin@setuhaul.com",
        full_name="Admin", role_id="ROL008", role_name=RoleName.ADMIN,
    )


def _non_admin_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="r", auth_subject="s", user_id="USR-OPS-1", email="ops@setuhaul.com",
        full_name="Ops", role_id="ROL002", role_name=RoleName.OPERATIONS_EXECUTIVE, facility_id=FACILITY,
    )


def _session_with(*results) -> AsyncMock:
    mocks = []
    for r in results:
        m = MagicMock()
        if isinstance(r, list):
            m.mappings.return_value.all.return_value = r
            # #72's multi-facility validation reads `.scalars().all()` (one `= ANY(:ids)` round
            # trip for the whole multi-select), so a list result has to answer both accessors.
            m.scalars.return_value.all.return_value = r
        else:
            m.mappings.return_value.first.return_value = r
            m.mappings.return_value.one.return_value = r
            m.scalars.return_value.all.return_value = []
        mocks.append(m)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=mocks)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _settings() -> Settings:
    return Settings(supabase_url="https://proj.supabase.co", supabase_service_role_key="service-key-not-real")


@pytest.fixture(autouse=True)
def _no_idempotency_replay(monkeypatch):
    monkeypatch.setattr(admin_user_service, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(admin_user_service, "store_idempotency", AsyncMock())
    monkeypatch.setattr(admin_governance_service, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(admin_governance_service, "store_idempotency", AsyncMock())


# ---------------------------------------------------------------------------------------------
# Role gate -- every admin tool refuses a non-admin, checked once as a representative sample.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_users_refuses_a_non_admin():
    session = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_user_service.list_users(session, _non_admin_ctx())
    assert exc.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_simulate_policy_weights_refuses_a_non_admin():
    session = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_governance_service.simulate_policy_weights(
            session, _non_admin_ctx(), weights={},
            window_start=datetime.now(timezone.utc), window_end=datetime.now(timezone.utc) + timedelta(days=7),
        )
    assert exc.value.code == "FORBIDDEN"


# ---------------------------------------------------------------------------------------------
# invite_user / Supabase Auth Admin API proxy
# ---------------------------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text

    def json(self):
        return self._json


class _FakeAsyncClient:
    calls: list[dict] = []
    post_response: _FakeResponse = _FakeResponse(json_body={"id": "auth-uuid-1"})
    delete_response: _FakeResponse = _FakeResponse()

    def __init__(self, *_a, **_k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def post(self, url, **kwargs):
        _FakeAsyncClient.calls.append({"method": "post", "url": url, **kwargs})
        return _FakeAsyncClient.post_response

    async def delete(self, url, **kwargs):
        _FakeAsyncClient.calls.append({"method": "delete", "url": url, **kwargs})
        return _FakeAsyncClient.delete_response


@pytest.fixture(autouse=True)
def _reset_fake_client():
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.post_response = _FakeResponse(json_body={"id": "auth-uuid-1"})
    _FakeAsyncClient.delete_response = _FakeResponse()
    yield


@pytest.mark.asyncio
async def test_invite_user_creates_the_auth_identity_and_the_local_row_together(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with(
        [FACILITY],  # _validate_scope facility existence check (ANY(:ids) -> scalars)
        {"role_id": "ROL003"},  # _resolve_role_id
        None,  # INSERT users
        None,  # DELETE user_scopes
        None,  # INSERT user_scopes
        None,  # INSERT audit_logs
    )

    result = await admin_user_service.invite_user(
        session, _admin_ctx(), _settings(), email="new.planner@setuhaul.com", role="WAREHOUSE_PLANNER", scope=FACILITY,
    )

    assert result["code"] == "INVITED"
    invite_call = next(c for c in _FakeAsyncClient.calls if c["method"] == "post")
    assert invite_call["url"].endswith("/auth/v1/invite")
    assert invite_call["json"] == {"email": "new.planner@setuhaul.com"}


@pytest.mark.asyncio
async def test_invite_user_rejects_an_unknown_role_before_calling_auth():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_user_service.invite_user(
            session, _admin_ctx(), _settings(), email="x@setuhaul.com", role="SUPERUSER", scope=None,
        )
    assert exc.value.code == "INVALID_ROLE"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_invite_user_requires_a_scope_for_a_facility_scoped_role():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_user_service.invite_user(
            session, _admin_ctx(), _settings(), email="x@setuhaul.com", role="WAREHOUSE_PLANNER", scope=None,
        )
    assert exc.value.code == "SCOPE_REQUIRED"


@pytest.mark.asyncio
async def test_invite_user_rejects_a_facility_that_does_not_exist():
    session = _session_with([])  # facility existence check matches nothing
    with pytest.raises(AppError) as exc:
        await admin_user_service.invite_user(
            session, _admin_ctx(), _settings(), email="x@setuhaul.com", role="WAREHOUSE_PLANNER", scope="FAC-GHOST",
        )
    assert exc.value.code == "INVALID_SCOPE"


@pytest.mark.asyncio
async def test_invite_user_accepts_a_global_role_with_no_scope(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    # ADMIN is a global role: _validate_scope returns immediately with no DB call, so
    # resolve_role_id + INSERT users + the scope-table DELETE (which then returns without an
    # INSERT, since a global role holds no scope rows) + INSERT audit_logs run.
    session = _session_with({"role_id": "ROL008"}, None, None, None)
    result = await admin_user_service.invite_user(
        session, _admin_ctx(), _settings(), email="admin2@setuhaul.com", role="ADMIN", scope=None,
    )
    assert result["code"] == "INVITED"


@pytest.mark.asyncio
async def test_invite_user_reports_auth_failure_without_touching_postgres(monkeypatch):
    import httpx
    _FakeAsyncClient.post_response = _FakeResponse(status_code=422, text="email already registered")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    # validate_scope's facility check, then resolve_role_id -- both run before the Auth call.
    session = _session_with([FACILITY], {"role_id": "ROL003"})

    with pytest.raises(AppError) as exc:
        await admin_user_service.invite_user(
            session, _admin_ctx(), _settings(), email="dup@setuhaul.com", role="WAREHOUSE_PLANNER", scope=FACILITY,
        )
    assert exc.value.code == "AUTH_INVITE_FAILED"


# ---------------------------------------------------------------------------------------------
# update_user / deactivate / reactivate
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_user_changes_role_and_scope():
    session = _session_with(
        {"user_id": "USR1", "role_name": "OPERATIONS_EXECUTIVE"},  # existing user + current role
        [FACILITY],  # facility existence check
        {"role_id": "ROL005"},  # _resolve_role_id
        None,  # UPDATE users
        None,  # DELETE user_scopes
        None,  # INSERT user_scopes
    )
    result = await admin_user_service.update_user(session, _admin_ctx(), user_id="USR1", role="FACILITY_MANAGER", scope=FACILITY)
    assert result["code"] == "UPDATED"
    assert result["scope_values"] == [FACILITY]


@pytest.mark.asyncio
async def test_update_user_raises_not_found():
    session = _session_with(None)
    with pytest.raises(AppError) as exc:
        await admin_user_service.update_user(session, _admin_ctx(), user_id="USR-GHOST")
    assert exc.value.code == "NOT_FOUND"


# ---------------------------------------------------------------------------------------------
# A-G4 / issue #72 -- multi-facility scope through user_scopes.
# ---------------------------------------------------------------------------------------------


def test_normalize_scope_accepts_a_string_a_list_or_nothing():
    assert admin_user_service.normalize_scope(None) == []
    assert admin_user_service.normalize_scope(FACILITY) == [FACILITY]
    assert admin_user_service.normalize_scope([FACILITY, "FAC-GGN-01"]) == [FACILITY, "FAC-GGN-01"]
    # user_scopes carries UNIQUE (user_id, scope_type, scope_value): a form that submits the same
    # facility twice must not reach the INSERT as two rows.
    assert admin_user_service.normalize_scope([FACILITY, " " + FACILITY + " ", ""]) == [FACILITY]


@pytest.mark.asyncio
async def test_invite_user_writes_one_user_scopes_row_per_facility(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    facilities = [FACILITY, "FAC-GGN-01"]
    session = _session_with(
        facilities,  # both facilities exist
        {"role_id": "ROL002"},  # _resolve_role_id
        None,  # INSERT users
        None,  # DELETE user_scopes
        None,  # INSERT user_scopes
        None,  # INSERT audit_logs
    )

    result = await admin_user_service.invite_user(
        session, _admin_ctx(), _settings(), email="neha@setuhaul.com",
        role="OPERATIONS_EXECUTIVE", scope=facilities,
    )

    assert result["code"] == "INVITED"
    assert result["scope_values"] == facilities

    # The users row keeps the first facility as the single-valued mirror every not-yet-consolidated
    # scope check still reads.
    users_insert = session.execute.call_args_list[2]
    assert "INSERT INTO public.users" in str(users_insert.args[0])
    assert users_insert.args[1]["facility_id"] == FACILITY

    # ...and user_scopes carries both, which is what screens.md's "Jaipur, Gurugram" row needs.
    scopes_insert = session.execute.call_args_list[4]
    assert "INSERT INTO public.user_scopes" in str(scopes_insert.args[0])
    assert scopes_insert.args[1]["scope_values"] == facilities
    assert scopes_insert.args[1]["stype"] == "FACILITY"
    assert len(scopes_insert.args[1]["scope_ids"]) == 2


@pytest.mark.asyncio
async def test_invite_user_names_every_missing_facility_at_once():
    session = _session_with([FACILITY])  # only one of the two submitted facilities exists
    with pytest.raises(AppError) as exc:
        await admin_user_service.invite_user(
            session, _admin_ctx(), _settings(), email="x@setuhaul.com",
            role="OPERATIONS_EXECUTIVE", scope=[FACILITY, "FAC-GHOST"],
        )
    assert exc.value.code == "INVALID_SCOPE"
    assert "FAC-GHOST" in exc.value.message


@pytest.mark.asyncio
async def test_invite_user_refuses_multiple_scopes_for_a_single_valued_role():
    """A DRIVER user *is* one driver -- more than one id is a caller error, refused by name rather
    than silently truncated to the first entry."""
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_user_service.invite_user(
            session, _admin_ctx(), _settings(), email="d@setuhaul.com",
            role="DRIVER", scope=["DRV001", "DRV002"],
        )
    assert exc.value.code == "SCOPE_NOT_MULTI_VALUED"
    session.execute.assert_not_awaited()


# ---------------------------------------------------------------------------------------------
# GATE_OFFICER is facility-scoped but single-facility (owner-decided 2026-09-01).
#
# The combination that produced this: #79 put GATE_OFFICER into FACILITY_SCOPED_ROLES, and #72 had
# already made every FACILITY scope multi-valued -- so a device-bound kiosk role became
# multi-facility-capable without anyone deciding it should be. These tests pin the cap AND pin that
# it is a carve-out for one role, not a re-narrowing of #72.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invite_user_accepts_a_single_facility_gate_officer(monkeypatch):
    """The whole path, not just the validator: users.facility_id (what get_execution_context
    actually resolves the kiosk's scope from) and exactly one FACILITY user_scopes row."""
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with(
        [FACILITY],  # facility existence check
        {"role_id": "ROL009"},  # _resolve_role_id
        None,  # INSERT users
        None,  # DELETE user_scopes
        None,  # INSERT user_scopes
        None,  # INSERT audit_logs
    )

    result = await admin_user_service.invite_user(
        session, _admin_ctx(), _settings(), email="gate.jai@setuhaul.com",
        role="GATE_OFFICER", scope=FACILITY,
    )

    assert result["code"] == "INVITED"
    assert result["scope_values"] == [FACILITY]

    users_insert = session.execute.call_args_list[2]
    assert "INSERT INTO public.users" in str(users_insert.args[0])
    assert users_insert.args[1]["facility_id"] == FACILITY
    assert users_insert.args[1]["driver_id"] is None

    scopes_insert = session.execute.call_args_list[4]
    assert "INSERT INTO public.user_scopes" in str(scopes_insert.args[0])
    assert scopes_insert.args[1]["stype"] == "FACILITY"
    assert scopes_insert.args[1]["scope_values"] == [FACILITY]

    # ...and the audit row records the granted scope, not just the role (FR-ADM-009).
    audit_insert = session.execute.call_args_list[5]
    assert json.loads(audit_insert.args[1]["new_value_json"])["scope"] == [FACILITY]


@pytest.mark.asyncio
async def test_invite_user_refuses_a_multi_facility_gate_officer():
    """auth-and-scoping.md:66-68 -- the gate session's facility is the DEVICE's. Two facilities on
    one kiosk account is authority the surface can never exercise, so it is refused by name."""
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_user_service.invite_user(
            session, _admin_ctx(), _settings(), email="gate@setuhaul.com",
            role="GATE_OFFICER", scope=[FACILITY, "FAC-GGN-01"],
        )
    assert exc.value.code == "GATE_OFFICER_SINGLE_FACILITY"
    assert exc.value.status_code == 422
    # Refused before any round trip, like SCOPE_NOT_MULTI_VALUED -- and before the Supabase Auth
    # call, so no orphaned auth identity is created for a request that was never going to land.
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_user_refuses_a_multi_facility_gate_officer():
    """The cap has to hold on the edit path too: a gate officer invited with one facility must not
    be widened to two afterwards, which is a scope-only edit away."""
    session = _session_with({"user_id": "USR1", "role_name": "GATE_OFFICER"})
    with pytest.raises(AppError) as exc:
        await admin_user_service.update_user(
            session, _admin_ctx(), user_id="USR1", scope=[FACILITY, "FAC-GGN-01"],
        )
    assert exc.value.code == "GATE_OFFICER_SINGLE_FACILITY"
    # Only the role re-read happened; no UPDATE and no scope rewrite.
    assert len(session.execute.call_args_list) == 1


@pytest.mark.asyncio
async def test_update_user_accepts_a_single_facility_gate_officer():
    session = _session_with(
        {"user_id": "USR1", "role_name": "GATE_OFFICER"},
        [FACILITY],  # facility existence check
        None,  # UPDATE users
        None,  # DELETE user_scopes
        None,  # INSERT user_scopes
    )
    result = await admin_user_service.update_user(session, _admin_ctx(), user_id="USR1", scope=FACILITY)
    assert result["scope_values"] == [FACILITY]
    assert session.execute.call_args_list[2].args[1]["facility_id"] == FACILITY
    assert session.execute.call_args_list[4].args[1]["scope_values"] == [FACILITY]


@pytest.mark.parametrize(
    "role",
    sorted(admin_user_service.FACILITY_SCOPED_ROLES - {RoleName.GATE_OFFICER}, key=lambda r: r.value),
)
@pytest.mark.asyncio
async def test_every_other_facility_role_stays_multi_valued(role):
    """The guard against over-correcting #72. Written over the live set rather than a hardcoded
    list, so a facility role added later is covered by this test the day it is added -- and so a
    future edit that caps the whole set instead of the one role fails here."""
    session = _session_with([FACILITY, "FAC-GGN-01"])
    await admin_user_service._validate_scope(session, role, [FACILITY, "FAC-GGN-01"])


@pytest.mark.asyncio
async def test_list_users_renders_a_single_facility_gate_officer():
    """The rendering half: a capped role still flows through list_users like any facility role --
    one entry in the Scope column's array, not a special case the frontend has to know about."""
    rows = [
        {
            "user_id": "USR-GATE-1", "full_name": "Gate Kiosk (Jaipur)",
            "email": "gate.jai@setuhaul.com", "role_name": "GATE_OFFICER",
            "facility_id": FACILITY, "driver_id": None, "is_active": 1, "last_login_ts": None,
            "invited_at": None, "invite_accepted_at": None, "removed_at": None,
            "scoped_facility_ids": [FACILITY],
        },
    ]
    session = _session_with(rows)
    result = await admin_user_service.list_users(session, _admin_ctx())
    assert result["items"][0]["scoped_facility_ids"] == [FACILITY]
    assert result["items"][0]["lifecycle_state"] == admin_user_service.LIFECYCLE_ACTIVE


@pytest.mark.asyncio
async def test_invite_user_writes_a_driver_scope_row(monkeypatch):
    """Pre-#72 only CARRIER got a user_scopes row, so a driver invited through this console was
    inconsistent with every driver E2.3's migration backfilled."""
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with(
        {"driver_id": "DRV001"},  # driver existence check
        {"role_id": "ROL001"},
        None, None, None, None,
    )
    await admin_user_service.invite_user(
        session, _admin_ctx(), _settings(), email="ravi@setuhaul.com", role="DRIVER", scope="DRV001",
    )
    scopes_insert = session.execute.call_args_list[4]
    assert scopes_insert.args[1]["stype"] == "DRIVER"
    assert scopes_insert.args[1]["scope_values"] == ["DRV001"]


@pytest.mark.asyncio
async def test_update_user_applies_a_scope_only_edit_against_the_stored_role():
    """flows-and-states.md Flow 2: adding a second facility to a user whose role isn't changing.
    Pre-#72 this returned UPDATED having changed nothing at all."""
    facilities = [FACILITY, "FAC-GGN-01"]
    session = _session_with(
        {"user_id": "USR1", "role_name": "OPERATIONS_EXECUTIVE"},
        facilities,  # facility existence check
        None,  # UPDATE users
        None,  # DELETE user_scopes
        None,  # INSERT user_scopes
    )

    result = await admin_user_service.update_user(session, _admin_ctx(), user_id="USR1", scope=facilities)

    assert result["scope_values"] == facilities
    # No _resolve_role_id call: the role came from the database, not from the request payload.
    assert not any("FROM public.roles WHERE role_name" in str(c.args[0]) for c in session.execute.call_args_list)
    update_call = session.execute.call_args_list[2]
    assert update_call.args[1]["scope_write"] is True
    assert update_call.args[1]["role_id"] is None
    assert update_call.args[1]["facility_id"] == FACILITY
    assert session.execute.call_args_list[4].args[1]["scope_values"] == facilities


@pytest.mark.asyncio
async def test_update_user_with_no_role_and_no_scope_leaves_the_mirror_columns_alone():
    session = _session_with({"user_id": "USR1", "role_name": "OPERATIONS_EXECUTIVE"}, None)
    result = await admin_user_service.update_user(session, _admin_ctx(), user_id="USR1")
    assert result["code"] == "UPDATED"
    update_call = session.execute.call_args_list[1]
    assert update_call.args[1]["scope_write"] is False
    # No scope rewrite at all -- the UPDATE is the last statement.
    assert len(session.execute.call_args_list) == 2


@pytest.mark.asyncio
async def test_update_user_role_change_clears_every_stale_scope_type():
    session = _session_with(
        {"user_id": "USR1", "role_name": "OPERATIONS_EXECUTIVE"},
        {"role_id": "ROL008"},  # ADMIN: global, so _validate_scope makes no DB call
        None,  # UPDATE users
        None,  # DELETE user_scopes
    )
    await admin_user_service.update_user(session, _admin_ctx(), user_id="USR1", role="ADMIN")
    delete_call = session.execute.call_args_list[3]
    assert "DELETE FROM public.user_scopes" in str(delete_call.args[0])
    assert delete_call.args[1]["types"] == list(admin_user_service.MANAGED_SCOPE_TYPES)
    # A global role holds no scope rows at all -- the DELETE is the last statement, no INSERT.
    assert len(session.execute.call_args_list) == 4


@pytest.mark.asyncio
async def test_list_users_returns_scoped_facility_ids_and_filters_on_them():
    rows = [
        {
            "user_id": "USR1", "full_name": "Neha B.", "email": "neha@setuhaul.com",
            "role_name": "OPERATIONS_EXECUTIVE", "facility_id": FACILITY, "driver_id": None,
            "is_active": 1, "last_login_ts": None,
            "scoped_facility_ids": [FACILITY, "FAC-GGN-01"],
        },
    ]
    session = _session_with(rows)
    result = await admin_user_service.list_users(session, _admin_ctx(), None, "FAC-GGN-01")

    assert result["items"][0]["scoped_facility_ids"] == [FACILITY, "FAC-GGN-01"]
    sql = str(session.execute.call_args.args[0])
    # The filter must match on either side of the mirror: a user whose primary facility_id is
    # Jaipur but who also holds a Gurugram scope row has to appear under a Gurugram filter.
    assert "u.facility_id = :facility_filter OR EXISTS" in sql
    assert session.execute.call_args.args[1]["facility_filter"] == "FAC-GGN-01"


@pytest.mark.asyncio
async def test_list_users_falls_back_to_the_primary_facility_when_no_scope_row_exists():
    """A row predating E2.3's backfill has no user_scopes row; rendering an empty Scope cell for a
    user who genuinely has one facility would be a regression, not honesty."""
    rows = [
        {
            "user_id": "USR2", "full_name": "Ramesh K.", "email": "ramesh@setuhaul.com",
            "role_name": "OPERATIONS_EXECUTIVE", "facility_id": FACILITY, "driver_id": None, "is_active": 1, "last_login_ts": None,
            "scoped_facility_ids": [],
        },
    ]
    session = _session_with(rows)
    result = await admin_user_service.list_users(session, _admin_ctx())
    assert result["items"][0]["scoped_facility_ids"] == [FACILITY]


@pytest.mark.asyncio
async def test_deactivate_then_reactivate_user():
    session = _session_with({"user_id": "USR1", "is_active": 0})
    result = await admin_user_service.deactivate_user(session, _admin_ctx(), "USR1")
    assert result["code"] == "DEACTIVATED"

    session2 = _session_with({"user_id": "USR1", "is_active": 1})
    result2 = await admin_user_service.reactivate_user(session2, _admin_ctx(), "USR1")
    assert result2["code"] == "REACTIVATED"


# ---------------------------------------------------------------------------------------------
# remove_user
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_user_requires_an_idempotency_key():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_user_service.remove_user(session, _admin_ctx(), _settings(), user_id="USR1", idempotency_key="")
    assert exc.value.code == "IDEMPOTENCY_KEY_REQUIRED"


@pytest.mark.asyncio
async def test_remove_user_deletes_the_auth_identity_and_deactivates_locally(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with(
        {"user_id": "USR1", "auth_user_id": "auth-uuid-1", "active_escalation_count": 0}, None, None
    )

    result = await admin_user_service.remove_user(session, _admin_ctx(), _settings(), user_id="USR1", idempotency_key="rm-1")

    assert result["code"] == "REMOVED"
    delete_call = next(c for c in _FakeAsyncClient.calls if c["method"] == "delete")
    assert "auth-uuid-1" in delete_call["url"]


@pytest.mark.asyncio
async def test_remove_user_treats_an_already_gone_auth_identity_as_success(monkeypatch):
    import httpx
    _FakeAsyncClient.delete_response = _FakeResponse(status_code=404)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with(
        {"user_id": "USR1", "auth_user_id": "auth-uuid-gone", "active_escalation_count": 0}, None, None
    )

    result = await admin_user_service.remove_user(session, _admin_ctx(), _settings(), user_id="USR1", idempotency_key="rm-2")
    assert result["code"] == "REMOVED"


# ---------------------------------------------------------------------------------------------
# A-G8 / issue #76 -- the escalation count behind edge-cases.md #1's confirmation copy.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_removal_impact_counts_owned_active_escalations():
    owned = [
        {"escalation_id": "ESC1", "shipment_id": "SHP1", "facility_id": FACILITY,
         "escalation_status": "ACKNOWLEDGED", "severity_code": "HIGH", "total_count": 2},
        {"escalation_id": "ESC2", "shipment_id": "SHP2", "facility_id": FACILITY,
         "escalation_status": "IN_PROGRESS", "severity_code": "MEDIUM", "total_count": 2},
    ]
    session = _session_with({"user_id": "USR1", "full_name": "Neha B.", "email": "neha@setuhaul.com", "is_active": 1}, owned)

    result = await admin_user_service.get_user_removal_impact(session, _admin_ctx(), user_id="USR1")

    # edge-cases.md #1's locked copy: "This user owns 2 active escalations".
    assert result["active_escalation_count"] == 2
    assert [e["escalation_id"] for e in result["active_escalations"]] == ["ESC1", "ESC2"]
    # `total_count` is a query mechanism, not part of the contract.
    assert "total_count" not in result["active_escalations"][0]
    assert result["is_self"] is False

    escalation_sql = str(session.execute.call_args_list[1].args[0])
    assert "owner_user_id = :uid" in escalation_sql
    assert session.execute.call_args_list[1].args[1]["terminal"] == ["RESOLVED", "CANCELLED"]


@pytest.mark.asyncio
async def test_get_user_removal_impact_reports_zero_for_an_unowning_user():
    session = _session_with({"user_id": "USR1", "full_name": "X", "email": "x@setuhaul.com", "is_active": 1}, [])
    result = await admin_user_service.get_user_removal_impact(session, _admin_ctx(), user_id="USR1")
    assert result["active_escalation_count"] == 0
    assert result["active_escalations"] == []


@pytest.mark.asyncio
async def test_get_user_removal_impact_flags_the_callers_own_account():
    """Flow 4: Remove is Hidden on the signed-in admin's own account -- stated by the server."""
    session = _session_with({"user_id": "USR-ADMIN-1", "full_name": "Admin", "email": "admin@setuhaul.com", "is_active": 1}, [])
    result = await admin_user_service.get_user_removal_impact(session, _admin_ctx(), user_id="USR-ADMIN-1")
    assert result["is_self"] is True


@pytest.mark.asyncio
async def test_get_user_removal_impact_raises_not_found():
    session = _session_with(None)
    with pytest.raises(AppError) as exc:
        await admin_user_service.get_user_removal_impact(session, _admin_ctx(), user_id="USR-GHOST")
    assert exc.value.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_get_user_removal_impact_refuses_a_non_admin():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_user_service.get_user_removal_impact(session, _non_admin_ctx(), user_id="USR1")
    assert exc.value.code == "FORBIDDEN"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_user_recounts_owned_escalations_inside_its_own_transaction(monkeypatch):
    """The preview is advisory; the number recorded in the audit log and returned to the caller is
    the one read inside the removing transaction."""
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with(
        {"user_id": "USR1", "auth_user_id": "auth-uuid-1", "active_escalation_count": 2}, None, None
    )

    result = await admin_user_service.remove_user(
        session, _admin_ctx(), _settings(), user_id="USR1", idempotency_key="rm-3"
    )

    assert result["active_escalation_count"] == 2
    read_sql = str(session.execute.call_args_list[0].args[0])
    assert "public.escalation_queue" in read_sql
    assert "owner_user_id = u.user_id" in read_sql

    audit_params = session.execute.call_args_list[2].args[1]
    assert '"orphaned_active_escalations": 2' in audit_params["new_value_json"]


# ---------------------------------------------------------------------------------------------
# facility rules
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_facility_rule_rejects_an_unregistered_rule_type():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_governance_service.create_facility_rule(
            session, _admin_ctx(), facility_id=FACILITY, rule_type="MADE_UP_RULE", rule_value="1",
        )
    assert exc.value.code == "INVALID_RULE_TYPE"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_facility_rule_accepts_a_registered_rule_type():
    session = _session_with({
        "rule_id": "RULE1", "facility_id": FACILITY, "rule_type": "NO_SHOW_GRACE_MIN",
        "rule_value": "15", "effective_from": None, "effective_to": None,
    })
    result = await admin_governance_service.create_facility_rule(
        session, _admin_ctx(), facility_id=FACILITY, rule_type="no_show_grace_min", rule_value="15",
    )
    assert result["code"] == "CREATED"


@pytest.mark.asyncio
async def test_update_facility_rule_raises_not_found():
    session = _session_with(None)
    with pytest.raises(AppError) as exc:
        await admin_governance_service.update_facility_rule(session, _admin_ctx(), rule_id="RULE-GHOST")
    assert exc.value.code == "NOT_FOUND"


# ---------------------------------------------------------------------------------------------
# simulate_policy_weights -- the formula-parity guard.
# ---------------------------------------------------------------------------------------------


def test_score_formula_matches_feasibility_pys_rank_slot_exactly():
    """The drift guard `admin_governance_service.py`'s own docstring promises: this module
    duplicates feasibility.py's scoring formula rather than importing it (deliberately, to avoid
    touching the live booking hot path) -- this test pins the two to the same output so a future
    edit to either without the other is caught, not silently diverging."""
    from app.scheduling.feasibility import _rank_slot

    shipment = {
        "shipment_id": "SHP-TEST", "priority_code": "HIGH",
        "original_eta_ts": "2026-08-25T10:00:00+00:00", "required_dock_type": "STANDARD",
    }
    eta_dt = datetime(2026, 8, 25, 10, 30, tzinfo=timezone.utc)
    candidate = {"dock_type": "STANDARD", "slot_id": "SLOT-TEST"}
    feasible_start = datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)
    feasible_end = datetime(2026, 8, 25, 11, 45, tzinfo=timezone.utc)
    slot_end = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)

    live_score, _ = _rank_slot(
        shipment=shipment, eta_dt=eta_dt, candidate=candidate,
        feasible_start=feasible_start, feasible_end=feasible_end, slot_end=slot_end,
    )

    from app.scheduling.constraints import load_scheduling_constraints
    policy = load_scheduling_constraints().ranking_policy
    weights = policy.score_weights
    priority_scores = policy.priority_scores or admin_governance_service.DEFAULT_PRIORITY_SCORES

    lateness_minutes = max(0, int((eta_dt - datetime.fromisoformat(shipment["original_eta_ts"])).total_seconds() // 60))
    wait_after_eta_minutes = max(0, int((feasible_start - eta_dt).total_seconds() // 60))
    fit_slack_minutes = max(0, int((slot_end - feasible_end).total_seconds() // 60))

    copied_score = admin_governance_service._score(
        priority_code="HIGH", lateness_minutes=lateness_minutes, wait_after_eta_minutes=wait_after_eta_minutes,
        fit_slack_minutes=fit_slack_minutes, exact_dock_type_match=True, weights=weights, priority_scores=priority_scores,
    )

    assert copied_score == live_score


@pytest.mark.asyncio
async def test_publish_policy_version_requires_an_idempotency_key():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_governance_service.publish_policy_version(session, _admin_ctx(), weights={"lateness_per_minute": 4}, idempotency_key="")
    assert exc.value.code == "IDEMPOTENCY_KEY_REQUIRED"


@pytest.mark.asyncio
async def test_publish_policy_version_clears_the_prior_active_row_first():
    session = _session_with(
        {"policy_version_id": "POLV-1", "published_by_user_id": "USR-ADMIN-9", "published_at": None},
        None,  # UPDATE clear prior active
        None,  # INSERT new version
    )
    result = await admin_governance_service.publish_policy_version(
        session, _admin_ctx(), weights={"lateness_per_minute": 5}, idempotency_key="pub-1",
        based_on_version_id="POLV-1",
    )
    assert result["code"] == "PUBLISHED"
    assert result["superseded_version_id"] == "POLV-1"
    clear_sql = str(session.execute.call_args_list[1].args[0])
    assert "is_active = 0" in clear_sql


# ---------------------------------------------------------------------------------------------
# A-G7 / issue #75 -- version-conflict detection on publish_policy_version.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_policy_version_locks_the_active_row_before_deciding():
    """edge-cases.md #3's race is only decidable if the baseline read serialises against the other
    admin's write -- a plain SELECT would let both publishes read the same pre-state."""
    session = _session_with({"policy_version_id": "POLV-1", "published_by_user_id": "U", "published_at": None}, None, None)
    await admin_governance_service.publish_policy_version(
        session, _admin_ctx(), weights={}, idempotency_key="pub-lock", based_on_version_id="POLV-1"
    )
    baseline_sql = str(session.execute.call_args_list[0].args[0])
    assert "is_active = 1" in baseline_sql
    assert "FOR UPDATE" in baseline_sql


@pytest.mark.asyncio
async def test_publish_policy_version_refuses_without_a_baseline_when_one_is_active():
    """An optional guard is not a guard: omitting the argument must not restore the pre-#75
    silent-overwrite behaviour."""
    session = _session_with({"policy_version_id": "POLV-1", "published_by_user_id": "U", "published_at": None})
    with pytest.raises(AppError) as exc:
        await admin_governance_service.publish_policy_version(
            session, _admin_ctx(), weights={"lateness_per_minute": 5}, idempotency_key="pub-2"
        )
    assert exc.value.code == "BASE_VERSION_REQUIRED"
    assert exc.value.status_code == 422
    assert "POLV-1" in exc.value.detail
    # Nothing was written: the UPDATE/INSERT never ran.
    assert len(session.execute.call_args_list) == 1


@pytest.mark.asyncio
async def test_publish_policy_version_refuses_a_stale_baseline_with_already_actioned():
    """Admin A simulated against POLV-1; Admin B published POLV-2 first. edge-cases.md #3: refuse
    with a named conflict, same shape as confirm_request's ALREADY_ACTIONED."""
    session = _session_with({"policy_version_id": "POLV-2", "published_by_user_id": "USR-ADMIN-B", "published_at": None})
    with pytest.raises(AppError) as exc:
        await admin_governance_service.publish_policy_version(
            session, _admin_ctx(), weights={"lateness_per_minute": 5}, idempotency_key="pub-3",
            based_on_version_id="POLV-1",
        )
    assert exc.value.code == "ALREADY_ACTIONED"
    assert exc.value.status_code == 409
    # The winning version is named, not just "the click failed".
    assert "POLV-2" in exc.value.message
    assert "POLV-1" in exc.value.detail and "USR-ADMIN-B" in exc.value.detail
    assert len(session.execute.call_args_list) == 1


@pytest.mark.asyncio
async def test_publish_policy_version_treats_a_vanished_active_row_as_a_conflict():
    """The genuinely simultaneous case: the loser's FOR UPDATE re-check finds no active row at all
    because the winner cleared it, so a supplied baseline can no longer be current."""
    session = _session_with(
        None,  # SELECT ... FOR UPDATE -> nothing active
        {"policy_version_id": "POLV-9", "published_by_user_id": "USR-ADMIN-B", "published_at": None},
    )
    with pytest.raises(AppError) as exc:
        await admin_governance_service.publish_policy_version(
            session, _admin_ctx(), weights={}, idempotency_key="pub-4", based_on_version_id="POLV-1",
        )
    assert exc.value.code == "ALREADY_ACTIONED"
    assert "POLV-9" in exc.value.message


@pytest.mark.asyncio
async def test_publish_policy_version_allows_the_first_ever_publish_with_no_baseline():
    session = _session_with(None, None, None)  # nothing active, then UPDATE + INSERT
    result = await admin_governance_service.publish_policy_version(
        session, _admin_ctx(), weights={"lateness_per_minute": 5}, idempotency_key="pub-5"
    )
    assert result["code"] == "PUBLISHED"
    assert result["superseded_version_id"] is None


@pytest.mark.asyncio
async def test_publish_policy_version_hashes_the_baseline_into_the_idempotency_payload(monkeypatch):
    """Same key, same weights, a different baseline is a different request -- otherwise a replay
    could return a success that was decided against a version the caller never saw."""
    captured = {}

    async def _capture(session, *, key, user_id, route, request_hash, response, **kw):
        captured["hash"] = request_hash

    monkeypatch.setattr(admin_governance_service, "store_idempotency", _capture)
    session = _session_with({"policy_version_id": "POLV-1", "published_by_user_id": "U", "published_at": None}, None, None)
    # A real engine key, not a placeholder: since A-G1/#69 `publish_policy_version` refuses any
    # weight key the ranking engine does not read, so `{"w": 1}` is now a 422 rather than a
    # publishable payload. The property under test (baseline is inside the request hash) is
    # unchanged.
    weights = {"lateness_per_minute": 4}
    await admin_governance_service.publish_policy_version(
        session, _admin_ctx(), weights=weights, idempotency_key="pub-6", based_on_version_id="POLV-1"
    )
    from app.services.idempotency import payload_hash

    assert captured["hash"] == payload_hash({"weights": weights, "based_on_version_id": "POLV-1"})
    assert captured["hash"] != payload_hash({"weights": weights, "based_on_version_id": "POLV-2"})


# ---------------------------------------------------------------------------------------------
# get_active_policy_version -- the read the baseline argument needs.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_active_policy_version_returns_the_row_and_the_live_engine_weights():
    from app.scheduling.constraints import load_scheduling_constraints

    live_weights = dict(load_scheduling_constraints().ranking_policy.score_weights)
    session = _session_with({
        "policy_version_id": "POLV-1", "weights_json": json.dumps(live_weights),
        "published_at": "2026-08-29T00:00:00+00:00", "published_by_user_id": "USR-ADMIN-1",
    })
    result = await admin_governance_service.get_active_policy_version(session, _admin_ctx())
    assert result["active_version"]["policy_version_id"] == "POLV-1"
    assert result["live_weights"] == live_weights
    assert result["engine_matches_active_version"] is True


@pytest.mark.asyncio
async def test_get_active_policy_version_states_when_the_engine_and_the_published_version_differ():
    """publish_policy_version deliberately does not rewrite constraints.json, so these two can
    legitimately disagree -- the read says so rather than letting the UI imply otherwise."""
    session = _session_with({
        "policy_version_id": "POLV-2", "weights_json": json.dumps({"lateness_per_minute": 999}),
        "published_at": "2026-08-29T00:00:00+00:00", "published_by_user_id": "USR-ADMIN-1",
    })
    result = await admin_governance_service.get_active_policy_version(session, _admin_ctx())
    assert result["engine_matches_active_version"] is False


@pytest.mark.asyncio
async def test_get_active_policy_version_handles_a_system_that_has_never_published():
    session = _session_with(None)
    result = await admin_governance_service.get_active_policy_version(session, _admin_ctx())
    assert result["active_version"] is None
    assert result["engine_matches_active_version"] is False


@pytest.mark.asyncio
async def test_get_active_policy_version_refuses_a_non_admin():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_governance_service.get_active_policy_version(session, _non_admin_ctx())
    assert exc.value.code == "FORBIDDEN"
    session.execute.assert_not_awaited()


# ---------------------------------------------------------------------------------------------
# audit log
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_audit_log_applies_the_actor_filter():
    session = _session_with([])
    await admin_governance_service.get_audit_log(session, _admin_ctx(), actor="USR1")
    params = session.execute.call_args.args[1]
    assert params["actor"] == "USR1"


@pytest.mark.asyncio
async def test_export_audit_log_returns_csv_with_a_header_row():
    rows = [{"audit_id": "AUD1", "user_id": "USR1", "action_type": "CREATE", "entity_name": "users", "entity_id": "USR2", "created_at": "2026-08-25T00:00:00+00:00"}]
    session = _session_with(rows)
    csv_text = await admin_governance_service.export_audit_log(session, _admin_ctx())
    assert csv_text.splitlines()[0] == "audit_id,user_id,action_type,entity_name,entity_id,created_at"
    assert "AUD1" in csv_text


# ---------------------------------------------------------------------------------------------
# User lifecycle state -- issues #73 (pending invitation) and #81 (removed vs deactivated).
# Migration: supabase/migrations/20260831132101_users_invite_lifecycle.sql (NOT applied).
# ---------------------------------------------------------------------------------------------


def test_derive_lifecycle_state_precedence():
    """The precedence order IS the logic, so each rung is pinned separately.

    Written as a table because the interesting cases are the overlaps: a removed user is also
    is_active = 0, and an invited-then-deactivated user matches two rungs. Getting either
    precedence backwards produces a plausible-looking but wrong badge.
    """
    d = admin_user_service.derive_lifecycle_state
    ts = "2026-08-31T10:00:00+00:00"

    # Seeded/pre-existing account: never invited through this console, so ACTIVE -- not pending.
    assert d({"is_active": 1, "invited_at": None, "invite_accepted_at": None, "removed_at": None}) == "ACTIVE"
    # Invited, never seen making an authenticated request.
    assert d({"is_active": 1, "invited_at": ts, "invite_accepted_at": None, "removed_at": None}) == "INVITED"
    # Invited and accepted -- the stamp get_execution_context writes.
    assert d({"is_active": 1, "invited_at": ts, "invite_accepted_at": ts, "removed_at": None}) == "ACTIVE"
    # Deactivated beats invited: re-inviting an account an admin switched off is the opposite of
    # intent, so the row must not render a Resend action.
    assert d({"is_active": 0, "invited_at": ts, "invite_accepted_at": None, "removed_at": None}) == "DEACTIVATED"
    # Removed beats deactivated: remove_user sets BOTH, and this is the whole of issue #81.
    assert d({"is_active": 0, "invited_at": None, "invite_accepted_at": None, "removed_at": ts}) == "REMOVED"
    # A caller that selected a narrower column list degrades, it does not raise.
    assert d({"is_active": 1}) == "ACTIVE"


def test_removed_and_deactivated_are_distinguishable_from_the_same_is_active_value():
    """Issue #81 stated directly: before removed_at existed, these two rows were byte-identical."""
    deactivated = {"is_active": 0, "invited_at": None, "invite_accepted_at": None, "removed_at": None}
    removed = {"is_active": 0, "invited_at": None, "invite_accepted_at": None, "removed_at": "2026-08-31T10:00:00+00:00"}
    assert deactivated["is_active"] == removed["is_active"]
    assert admin_user_service.derive_lifecycle_state(deactivated) != admin_user_service.derive_lifecycle_state(removed)


@pytest.mark.asyncio
async def test_list_users_hides_removed_users_by_default_and_tags_every_row():
    rows = [
        {
            "user_id": "USR1", "full_name": "Neha B.", "email": "neha@setuhaul.com",
            "role_name": "OPERATIONS_EXECUTIVE", "facility_id": FACILITY, "driver_id": None,
            "is_active": 1, "last_login_ts": None,
            "invited_at": "2026-08-30T09:00:00+00:00", "invite_accepted_at": None, "removed_at": None,
            "scoped_facility_ids": [FACILITY],
        },
    ]
    session = _session_with(rows)
    result = await admin_user_service.list_users(session, _admin_ctx())

    assert result["items"][0]["lifecycle_state"] == "INVITED"
    # edge-cases.md #8: a genuinely removed user does not reappear in the default list.
    assert "u.removed_at IS NULL" in str(session.execute.call_args.args[0])


@pytest.mark.asyncio
async def test_list_users_include_removed_drops_the_filter():
    session = _session_with([])
    await admin_user_service.list_users(session, _admin_ctx(), include_removed=True)
    assert "u.removed_at IS NULL" not in str(session.execute.call_args.args[0])


@pytest.mark.asyncio
async def test_invite_user_stamps_invited_at_in_the_same_insert_that_creates_the_row(monkeypatch):
    """The write site for #73's first stamp. A users row created by this tool WITHOUT an invite
    stamp would render as ACTIVE forever, indistinguishable from a seeded account."""
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with(
        [FACILITY], {"role_id": "ROL003"}, None, None, None, None,
    )

    await admin_user_service.invite_user(
        session, _admin_ctx(), _settings(), email="p@setuhaul.com", role="WAREHOUSE_PLANNER", scope=FACILITY,
    )

    users_insert = session.execute.call_args_list[2]
    assert "INSERT INTO public.users" in str(users_insert.args[0])
    assert "invited_at" in str(users_insert.args[0])
    invited_at = users_insert.args[1]["invited_at"]
    # A datetime, not the ISO string created_at takes: asyncpg refuses a str for a timestamptz
    # bind rather than coercing it, so this assertion is load-bearing, not stylistic.
    assert isinstance(invited_at, datetime)
    assert invited_at.tzinfo is not None


@pytest.mark.asyncio
async def test_remove_user_stamps_removed_at_alongside_is_active_zero(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with(
        {"user_id": "USR1", "auth_user_id": "auth-uuid-1", "active_escalation_count": 0}, None, None
    )

    await admin_user_service.remove_user(
        session, _admin_ctx(), _settings(), user_id="USR1", idempotency_key="rm-2"
    )

    update = session.execute.call_args_list[1]
    sql = str(update.args[0])
    assert "is_active = 0" in sql and "removed_at = COALESCE(removed_at, :removed_at)" in sql
    assert isinstance(update.args[1]["removed_at"], datetime)


@pytest.mark.asyncio
async def test_reactivate_user_refuses_a_removed_user():
    """A removed user's Supabase Auth identity is already DELETEd, so is_active = 1 would restore
    a row that looks active and can never log in. The discriminator is what makes this refusable."""
    session = _session_with(None, {"removed_at": "2026-08-31T10:00:00+00:00"})
    with pytest.raises(AppError) as exc:
        await admin_user_service.reactivate_user(session, _admin_ctx(), "USR1")
    assert exc.value.code == "USER_REMOVED"
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_reactivate_user_still_reports_not_found_for_an_unknown_user():
    """The extra error-path SELECT exists to keep 404 and 409 distinct -- pinned so a later
    simplification cannot collapse them into one misleading answer."""
    session = _session_with(None, None)
    with pytest.raises(AppError) as exc:
        await admin_user_service.reactivate_user(session, _admin_ctx(), "USR-GHOST")
    assert exc.value.code == "NOT_FOUND"


def _pending_row(**overrides):
    row = {
        "user_id": "USR1", "email": "amit.d@setuhaul.com", "auth_user_id": "auth-uuid-1",
        "is_active": 1, "invited_at": "2026-08-30T09:00:00+00:00",
        "invite_accepted_at": None, "removed_at": None,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_resend_invite_posts_to_gotrue_and_restamps_invited_at(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with(_pending_row(), None, None)

    result = await admin_user_service.resend_invite(
        session, _admin_ctx(), _settings(), user_id="USR1"
    )

    assert result["code"] == "INVITE_RESENT"
    post = next(c for c in _FakeAsyncClient.calls if c["method"] == "post")
    # Same endpoint as the original invite -- GoTrue has no separate resend for invites, and its
    # sendInvite regenerates the confirmation token, which is what fixes an expired link.
    assert post["url"].endswith("/auth/v1/invite")
    assert post["json"] == {"email": "amit.d@setuhaul.com"}
    update = session.execute.call_args_list[1]
    assert "invited_at = :invited_at" in str(update.args[0])
    assert isinstance(update.args[1]["invited_at"], datetime)


def test_resend_invite_never_takes_an_email_from_the_caller():
    """M15: the address a Supabase Auth invite goes to is read from the stored row, so this tool
    cannot be used to mail an arbitrary address."""
    import inspect
    params = inspect.signature(admin_user_service.resend_invite).parameters
    assert "email" not in params
    assert "user_id" in params


@pytest.mark.asyncio
async def test_resend_invite_refuses_an_already_accepted_user(monkeypatch):
    """Refused locally BEFORE the HTTP call: GoTrue 422s an invite for a confirmed address, and
    invite_accepted_at IS NULL is this system's own record of the same fact."""
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with(_pending_row(invite_accepted_at="2026-08-30T12:00:00+00:00"))

    with pytest.raises(AppError) as exc:
        await admin_user_service.resend_invite(session, _admin_ctx(), _settings(), user_id="USR1")
    assert exc.value.code == "NOT_PENDING_INVITE"
    assert _FakeAsyncClient.calls == []


@pytest.mark.asyncio
async def test_resend_invite_surfaces_gotrue_email_rate_limiting_by_name(monkeypatch):
    """sendInvite returns 429 over_email_send_rate_limit -- the realistic failure of a Resend
    button an impatient admin presses repeatedly, so it must not read as a generic refusal."""
    import httpx
    _FakeAsyncClient.post_response = _FakeResponse(status_code=429, text="over_email_send_rate_limit")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with(_pending_row())

    with pytest.raises(AppError) as exc:
        await admin_user_service.resend_invite(session, _admin_ctx(), _settings(), user_id="USR1")
    assert exc.value.code == "AUTH_EMAIL_RATE_LIMITED"
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_revoke_invite_deletes_the_auth_identity_and_marks_the_row_removed(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with(_pending_row(), None, None)

    result = await admin_user_service.revoke_invite(
        session, _admin_ctx(), _settings(), user_id="USR1", idempotency_key="rv-1"
    )

    assert result["code"] == "INVITE_REVOKED"
    delete_call = next(c for c in _FakeAsyncClient.calls if c["method"] == "delete")
    assert "auth-uuid-1" in delete_call["url"]
    update = session.execute.call_args_list[1]
    assert "removed_at = COALESCE(removed_at, :removed_at)" in str(update.args[0])
    # A distinct audit event, not REMOVE_USER -- "we withdrew an unused invite" and "we removed a
    # working colleague" are different facts about the organisation (FR-ADM-009).
    audit = session.execute.call_args_list[2]
    assert json.loads(audit.args[1]["new_value_json"])["event"] == "REVOKE_INVITE"


@pytest.mark.asyncio
async def test_revoke_invite_requires_an_idempotency_key():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_user_service.revoke_invite(
            session, _admin_ctx(), _settings(), user_id="USR1", idempotency_key=" "
        )
    assert exc.value.code == "IDEMPOTENCY_KEY_REQUIRED"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoke_invite_refuses_a_never_invited_user_before_deleting_anything(monkeypatch):
    """Protects the admin acting on a stale list: a row that is not a pending invitation must not
    be silently full-removed by a Revoke button that was correct when the page rendered."""
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with(_pending_row(invited_at=None))

    with pytest.raises(AppError) as exc:
        await admin_user_service.revoke_invite(
            session, _admin_ctx(), _settings(), user_id="USR1", idempotency_key="rv-2"
        )
    assert exc.value.code == "NOT_PENDING_INVITE"
    assert _FakeAsyncClient.calls == []


@pytest.mark.asyncio
async def test_resend_and_revoke_both_refuse_a_non_admin():
    session = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_user_service.resend_invite(session, _non_admin_ctx(), _settings(), user_id="USR1")
    assert exc.value.code == "FORBIDDEN"
    with pytest.raises(AppError) as exc:
        await admin_user_service.revoke_invite(
            session, _non_admin_ctx(), _settings(), user_id="USR1", idempotency_key="k"
        )
    assert exc.value.code == "FORBIDDEN"


# ---------------------------------------------------------------------------------------------
# list_facilities (A-G10, issue #78)
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_facilities_returns_every_facility_with_its_active_flag():
    """The whole point of #78: a facility with no users and no rules must still be selectable.

    So this asserts the query is unfiltered and unlimited -- either a `WHERE` on `active_flag` or a
    `LIMIT` would silently recreate the incompleteness the endpoint exists to remove.
    """
    rows = [
        {"facility_id": "FAC-GGN-01", "facility_name": "Gurugram Cross-Dock", "city": "Gurugram", "active_flag": 1},
        {"facility_id": FACILITY, "facility_name": "Jaipur DC", "city": "Jaipur", "active_flag": 1},
        {"facility_id": "FAC-IDR-01", "facility_name": "Indore DC", "city": "Indore", "active_flag": 0},
    ]
    session = _session_with(rows)
    result = await admin_user_service.list_facilities(session, _admin_ctx())

    assert [item["facility_id"] for item in result["items"]] == [
        "FAC-GGN-01", FACILITY, "FAC-IDR-01",
    ]
    # active_flag is carried, not filtered: the Users tab's filter must still be able to name a
    # closed facility that users are scoped to, while the invite form must not offer one as a new
    # assignment. Two answers, one read.
    assert result["items"][2]["active_flag"] == 0
    assert result["source"] == "postgresql"

    sql = str(session.execute.call_args.args[0])
    assert "FROM public.facilities" in sql
    assert "ORDER BY facility_name" in sql
    assert "active_flag =" not in sql
    assert "LIMIT" not in sql


@pytest.mark.asyncio
async def test_list_facilities_takes_no_client_supplied_scope():
    """M15. The read has no arguments at all, so there is no id a caller could smuggle in; the
    role gate on `ctx` is the entire authorisation decision."""
    session = _session_with([])
    await admin_user_service.list_facilities(session, _admin_ctx())
    # One statement, and it is bound with no parameters -- nothing from the caller reaches the SQL.
    assert len(session.execute.call_args_list) == 1
    assert len(session.execute.call_args.args) == 1


@pytest.mark.asyncio
async def test_list_facilities_refuses_a_non_admin():
    session = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_user_service.list_facilities(session, _non_admin_ctx())
    assert exc.value.code == "FORBIDDEN"


def test_the_facilities_route_is_wired_behind_the_same_gate_as_its_sibling_reads():
    """`GET /admin/facilities` is a new public entry point, so its gate is asserted structurally.

    Compares the resolved dependency callables against `GET /admin/users` rather than re-asserting
    `RoleName.ADMIN` by name, so this stays true if `AdminCtx` is ever narrowed further. Reads off
    the router rather than `app.routes` for the reason `test_gate_yard_reads.py` records: FastAPI
    0.141 keeps included routers wrapped rather than flattening their routes onto the app.
    """
    from app.api.v1.routers import admin as admin_router
    from app.main import create_app

    routes = {(r.path, frozenset(r.methods)): r for r in admin_router.router.routes}
    facilities = routes[("/api/v1/admin/facilities", frozenset({"GET"}))]
    users = routes[("/api/v1/admin/users", frozenset({"GET"}))]

    assert facilities.endpoint is admin_router.facilities
    assert {d.call for d in facilities.dependant.dependencies} == {
        d.call for d in users.dependant.dependencies
    }
    # M15 at the transport layer: no facility id -- or anything else -- is reachable as a query
    # parameter, so there is nothing a caller could supply to widen what this read returns.
    assert facilities.dependant.query_params == []

    paths = create_app().openapi()["paths"]
    assert "get" in paths["/api/v1/admin/facilities"]
