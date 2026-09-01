"""`GET /api/v1/auth/me` -> `grants[]` (GitHub issue #52).

## What this file is really pinning

Issue #52 is titled "multi-role identity", and its own sub-issue 1 asks whether that is real. It is
not, and the schema is what says so:

  * `public.users.role_id TEXT NOT NULL` + a single `FOREIGN KEY(role_id) REFERENCES roles(role_id)`
    (baseline migration, `CREATE TABLE users`) -- one role per account, no join table.
  * `public.user_scopes(user_id, scope_type, scope_value)` with `UNIQUE (user_id, scope_type,
    scope_value)` and no per-user cap (`20260823090000_e23_identity_model.sql`), whose own comment
    says a user "can hold more than one scope row".

So "multi-role" is **one role, multiple facility/carrier scopes**, and these tests assert exactly
that: `role_name` is identical across every grant, and the length varies with *scope* count. A test
that ever needs two different `role_name`s in one response is a test asserting something the
database cannot store.

The other half is the rollback note's requirement -- `grants` is additive and `role_name` survives.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.routers import health_auth
from app.core.execution_context import ExecutionContext, RoleName
from app.services import auth_grants_service
from app.services.auth_grants_service import resolve_grants


def _ctx(**overrides) -> ExecutionContext:
    fields = {
        "request_id": "req-me-1",
        "auth_subject": "11111111-2222-3333-4444-555555555555",
        "user_id": "USR102",
        "email": "neha.b@setuhaul.com",
        "full_name": "Neha B",
        "role_id": "ROL003",
        "role_name": RoleName.WAREHOUSE_PLANNER,
        "driver_id": None,
        "facility_id": "FAC-JAI-01",
        "carrier_id": None,
        "is_active": True,
        "permissions": [],
    }
    fields.update(overrides)
    return ExecutionContext(**fields)


def _session(*, scope_values: list[str] | None = None, facility_rows: list[dict] | None = None):
    """A session whose first `execute` answers the user_scopes SELECT and whose second answers the
    facilities name lookup -- the only two statements `resolve_grants` can issue."""
    scopes_result = MagicMock()
    scopes_result.scalars.return_value.all.return_value = list(scope_values or [])
    names_result = MagicMock()
    names_result.mappings.return_value.all.return_value = list(facility_rows or [])

    session = AsyncMock()
    session.execute.side_effect = [scopes_result, names_result]
    return session


# ----------------------------------------------------------------------------------------------
# Sub-issue 1: one role, many scopes
# ----------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_multi_facility_planner_gets_one_grant_per_facility():
    """The case the role picker exists for, and the only multi-grant shape the schema can produce."""
    session = _session(
        scope_values=["FAC-GGN-01", "FAC-JAI-01"],
        facility_rows=[
            {"facility_id": "FAC-JAI-01", "facility_name": "SetuHaul Jaipur Distribution Centre"},
            {"facility_id": "FAC-GGN-01", "facility_name": "SetuHaul Gurugram Cross-Dock"},
        ],
    )

    grants = await resolve_grants(session, _ctx())

    assert len(grants) == 2
    # Sorted by id, so the picker's row order is stable between two sign-ins of the same account.
    assert [g["facility_id"] for g in grants] == ["FAC-GGN-01", "FAC-JAI-01"]
    assert [g["facility_name"] for g in grants] == [
        "SetuHaul Gurugram Cross-Dock",
        "SetuHaul Jaipur Distribution Centre",
    ]
    # THE sub-issue-1 assertion: many scopes, one role.
    assert {g["role_name"] for g in grants} == {"WAREHOUSE_PLANNER"}
    assert {g["scope_type"] for g in grants} == {"FACILITY"}


@pytest.mark.asyncio
async def test_the_users_facility_id_mirror_is_unioned_in_not_replaced():
    """`admin_user_service` mirrors only the FIRST facility into `users.facility_id`, and E2.3's
    backfill went the other way -- so a pre-E2.3 account can have the column and no scope row."""
    session = _session(scope_values=[], facility_rows=[])
    grants = await resolve_grants(session, _ctx(facility_id="FAC-JAI-01"))

    assert [g["facility_id"] for g in grants] == ["FAC-JAI-01"]
    assert grants[0]["scope_type"] == "FACILITY"


@pytest.mark.asyncio
async def test_a_facility_present_in_both_sources_is_not_duplicated():
    session = _session(
        scope_values=["FAC-JAI-01", "FAC-JAI-01"],
        facility_rows=[{"facility_id": "FAC-JAI-01", "facility_name": "SetuHaul Jaipur"}],
    )
    grants = await resolve_grants(session, _ctx(facility_id="FAC-JAI-01"))

    # A duplicate would also collide on RolePicker's `key={role}-{scopeLabel}` React key.
    assert len(grants) == 1


@pytest.mark.asyncio
async def test_a_facility_with_no_row_in_facilities_still_yields_a_grant_with_a_null_name():
    """An unresolvable name must not drop the grant -- the scope is real either way."""
    session = _session(scope_values=["FAC-XXX-99"], facility_rows=[])
    grants = await resolve_grants(session, _ctx(facility_id=None))

    assert len(grants) == 1
    assert grants[0]["facility_id"] == "FAC-XXX-99"
    assert grants[0]["facility_name"] is None


# ----------------------------------------------------------------------------------------------
# Per-role derivation rules
# ----------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_driver_gets_one_driver_grant_and_costs_zero_queries():
    """A driver DOES carry a FACILITY scope row (E2.3 backfilled one for every user with a
    non-NULL `users.facility_id`), and it is not reach: `ROLE_PERMISSIONS[DRIVER]` is entirely
    `*_self`/`*_own`. Rendering "Jaipur" for a driver would state a scope they do not have."""
    session = _session(scope_values=["FAC-JAI-01"])

    grants = await resolve_grants(
        session, _ctx(role_name=RoleName.DRIVER, role_id="ROL001", driver_id="DRV-001")
    )

    assert grants == [
        {
            "role_name": "DRIVER",
            "scope_type": "DRIVER",
            "facility_id": None,
            "facility_name": None,
            "carrier_id": None,
        }
    ]
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_carrier_scoped_transport_manager_gets_a_carrier_grant():
    """Issue #101: `carrier_id` is non-None only when a `user_scopes(scope_type='CARRIER')` row
    exists, so this is a real scope row rather than role seniority."""
    session = _session()

    grants = await resolve_grants(
        session,
        _ctx(role_name=RoleName.TRANSPORT_MANAGER, role_id="ROL006", facility_id=None,
             carrier_id="CAR-001"),
    )

    assert grants == [
        {
            "role_name": "TRANSPORT_MANAGER",
            "scope_type": "CARRIER",
            "facility_id": None,
            "facility_name": None,
            "carrier_id": "CAR-001",
        }
    ]
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_transport_manager_without_a_carrier_row_falls_through_to_global():
    """The other half of #101's guard: a role name on its own grants no carrier reach."""
    session = _session(scope_values=[])
    grants = await resolve_grants(
        session,
        _ctx(role_name=RoleName.TRANSPORT_MANAGER, role_id="ROL006", facility_id=None),
    )

    assert [g["scope_type"] for g in grants] == ["GLOBAL"]
    assert grants[0]["carrier_id"] is None


@pytest.mark.asyncio
async def test_an_admin_gets_one_global_grant_not_one_row_per_facility():
    """E2.3's migration states the rule: "global scope is the absence of a facility constraint,
    not a row naming every facility"."""
    session = _session(scope_values=[])
    grants = await resolve_grants(
        session, _ctx(role_name=RoleName.ADMIN, role_id="ROL008", facility_id=None)
    )

    assert len(grants) == 1
    assert grants[0]["scope_type"] == "GLOBAL"
    assert grants[0]["facility_id"] is None


@pytest.mark.asyncio
async def test_the_global_grant_predicate_is_has_global_read_scope_exactly():
    """Pinned against the enum rather than a hand-copied list, so adding a role to
    `has_global_read_scope` cannot silently diverge from what /auth/me reports."""
    for role in RoleName:
        if role in (RoleName.DRIVER,):
            continue
        ctx = _ctx(role_name=role, facility_id=None)
        grants = await resolve_grants(_session(scope_values=[]), ctx)
        expected = "GLOBAL" if ctx.has_global_read_scope else "NONE"
        assert grants[0]["scope_type"] == expected, role


@pytest.mark.asyncio
async def test_grants_is_never_empty_so_a_consumer_needs_no_length_check():
    session = _session(scope_values=[])
    grants = await resolve_grants(
        session, _ctx(role_name=RoleName.GATE_OFFICER, role_id="ROL010", facility_id=None)
    )

    assert len(grants) == 1
    assert grants[0]["scope_type"] == "NONE"


@pytest.mark.asyncio
async def test_a_gate_officer_gets_exactly_one_facility_grant():
    """`GATE_OFFICER_SINGLE_FACILITY` (422) caps this role at one facility server-side; the grants
    list must not imply the kiosk could ever choose between two."""
    session = _session(
        scope_values=["FAC-JAI-01"],
        facility_rows=[{"facility_id": "FAC-JAI-01", "facility_name": "SetuHaul Jaipur"}],
    )
    grants = await resolve_grants(
        session, _ctx(role_name=RoleName.GATE_OFFICER, role_id="ROL010", facility_id="FAC-JAI-01")
    )

    assert len(grants) == 1
    assert grants[0]["scope_type"] == "FACILITY"


# ----------------------------------------------------------------------------------------------
# M15: no client input reaches scope derivation
# ----------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scope_derivation_binds_only_the_contexts_own_user_id():
    """`resolve_grants` takes no argument a caller controls. This asserts the *query* honours that
    too -- the only bound value is the user id the verified token resolved to."""
    session = _session(scope_values=["FAC-JAI-01"], facility_rows=[])
    await resolve_grants(session, _ctx(user_id="USR102", facility_id=None))

    scopes_call = session.execute.await_args_list[0]
    assert scopes_call.args[1] == {"user_id": "USR102"}
    sql = str(scopes_call.args[0])
    assert "scope_type = 'FACILITY'" in sql
    assert ":user_id" in sql


def test_resolve_grants_signature_accepts_no_caller_supplied_scope():
    """A structural guard on M15: if someone ever adds a `facility_id`/`role` parameter here, the
    endpoint could start honouring a client-chosen scope. Fail at that moment, not in review."""
    import inspect

    params = list(inspect.signature(resolve_grants).parameters)
    assert params == ["session", "ctx"]


# ----------------------------------------------------------------------------------------------
# The endpoint: additive, per issue #52's own rollback note
# ----------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auth_me_returns_grants_alongside_the_unchanged_role_name(monkeypatch):
    """"no existing /auth/me consumer behaviour changes unless a grants[] field is added alongside
    the existing role_name" -- issue #52's rollback note, asserted."""
    request = MagicMock()
    request.state.request_id = "req-me-9"
    ctx = _ctx(permissions=["operations:read_facility"])

    async def _fake_grants(_session, _ctx):
        return [{"role_name": "WAREHOUSE_PLANNER", "scope_type": "FACILITY",
                 "facility_id": "FAC-JAI-01", "facility_name": "SetuHaul Jaipur",
                 "carrier_id": None}]

    monkeypatch.setattr(health_auth, "resolve_grants", _fake_grants)

    body = await health_auth.auth_me(request, ctx, AsyncMock())
    data = body["data"]

    # Every pre-#52 field, unchanged.
    for key in ("user_id", "email", "full_name", "role_id", "role_name", "driver_id",
                "facility_id", "permissions", "scope"):
        assert key in data
    assert data["role_name"] == RoleName.WAREHOUSE_PLANNER
    assert data["scope"]["type"] == "facility"
    # ...plus the new one.
    assert data["grants"] == await _fake_grants(None, None)


def test_the_endpoint_declares_no_request_body_or_query_parameter():
    """`grants` must be derived, never selected: /auth/me stays a zero-argument read."""
    from app.core.settings import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    spec = create_app().openapi()["paths"]["/api/v1/auth/me"]["get"]

    assert "requestBody" not in spec
    # The Authorization header is the only input, and it is a credential, not a scope selector.
    assert [p["name"] for p in spec.get("parameters", [])] == ["authorization"]


def test_scope_type_constants_match_the_user_scopes_check_constraint():
    """GLOBAL/NONE are deliberately NOT scope_type values -- that column's CHECK allows only
    FACILITY/CARRIER/DRIVER. Guards against someone "tidying up" by writing one of them to a row."""
    assert {
        auth_grants_service.SCOPE_FACILITY,
        auth_grants_service.SCOPE_CARRIER,
        auth_grants_service.SCOPE_DRIVER,
    } == {"FACILITY", "CARRIER", "DRIVER"}
    assert auth_grants_service.SCOPE_GLOBAL not in {"FACILITY", "CARRIER", "DRIVER"}
    assert auth_grants_service.SCOPE_NONE not in {"FACILITY", "CARRIER", "DRIVER"}
