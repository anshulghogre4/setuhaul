"""E3.3 (issue #27) tests for the §7.5.6 carrier portal.

Zero CARRIER users exist in the live database, so none of this can be exercised end-to-end through
a real authenticated call yet. These tests therefore attack the two things that do not need live
data and are the ones that actually matter:

1. **Scope refusal** (`NFR-019`, issue #27's rollback note: "a cross-carrier id must be refused,
   not silently empty") -- including that a cross-carrier id and a nonexistent id are refused
   *identically*, since `UI-UX/05-carrier-portal/edge-cases.md` #1 forbids this surface from
   confirming or denying existence outside scope.
2. **The no-comparative-framing constraint** (`U28`,
   `UI-UX/00-foundations/auth-and-scoping.md`) -- checked structurally against the SQL and the
   response shapes rather than by eyeballing them, because the leak this rule exists to prevent
   is precisely the well-meaning "helpful context" field somebody adds later.
"""

from __future__ import annotations

import ast
import inspect
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.repositories import carrier as carrier_repo
from app.repositories.scope import assert_shipment_in_carrier_fleet, resolve_carrier_scope
from app.services import carrier_reads

OWN_CARRIER = "CAR001"
OTHER_CARRIER = "CAR002"
OWN_SHIPMENT = "SHP1015"
OTHER_SHIPMENT = "SHP2999"


def _ctx(role: RoleName = RoleName.CARRIER, *, carrier_id: str | None = OWN_CARRIER) -> ExecutionContext:
    return ExecutionContext(
        request_id="req-carrier-1",
        auth_subject="sub-carrier-1",
        user_id="USR-CAR-1",
        email="fleet@northstar.example",
        full_name="Fleet Manager",
        role_id="ROL-CARRIER",
        role_name=role,
        carrier_id=carrier_id,
    )


@pytest.fixture
def session() -> AsyncMock:
    """Never actually used -- every repository call is patched out in these tests."""
    return AsyncMock()


# ---------------------------------------------------------------------------------------------
# 1. Scope derivation (M15): the carrier id comes from identity, and there is no argument for it.
# ---------------------------------------------------------------------------------------------


def test_resolve_carrier_scope_returns_the_identitys_own_carrier():
    assert resolve_carrier_scope(_ctx()) == OWN_CARRIER


def test_resolve_carrier_scope_takes_no_client_supplied_carrier_id():
    """M15/§7.5.6: `never accepted as an argument` is enforced by the signature itself.

    If someone later adds a `requested_carrier_id` parameter, this test fails and the reviewer has
    to justify reintroducing the exact shape the rule forbids.
    """
    params = list(inspect.signature(resolve_carrier_scope).parameters)
    assert params == ["ctx"], f"resolve_carrier_scope grew a parameter: {params}"


def test_resolve_carrier_scope_refuses_an_unmapped_carrier_identity():
    with pytest.raises(AppError) as exc:
        resolve_carrier_scope(_ctx(carrier_id=None))
    assert exc.value.code == "CARRIER_UNMAPPED"
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", [r for r in RoleName if r is not RoleName.CARRIER])
def test_no_other_role_can_resolve_a_carrier_scope(role):
    """Including ADMIN and the two global-read personas.

    `has_global_read_scope` is facility reach, not carrier reach -- `can_read_carrier`'s docstring
    records that deliberately, and this asserts the tool layer honours it rather than quietly
    letting an ops persona read a carrier's fleet.
    """
    with pytest.raises(AppError) as exc:
        resolve_carrier_scope(_ctx(role, carrier_id=OWN_CARRIER))
    assert exc.value.code == "FORBIDDEN"
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------------------------
# 2. get_shipment_detail refuses -- and refuses identically for "missing" and "someone else's".
# ---------------------------------------------------------------------------------------------


def _refusal(shipment_carrier_id: str | None) -> tuple[str, int, str]:
    with pytest.raises(AppError) as exc:
        assert_shipment_in_carrier_fleet(_ctx(), shipment_carrier_id=shipment_carrier_id)
    return exc.value.code, exc.value.status_code, exc.value.message


def test_own_shipment_passes_the_fleet_check():
    assert_shipment_in_carrier_fleet(_ctx(), shipment_carrier_id=OWN_CARRIER)


def test_cross_carrier_and_missing_shipment_are_refused_identically():
    """`edge-cases.md` #1: never confirms or denies whether the shipment exists outside scope."""
    cross_carrier = _refusal(OTHER_CARRIER)
    missing = _refusal(None)
    assert cross_carrier == missing, "refusals differ -- response code leaks existence"
    assert cross_carrier[0] == "FORBIDDEN"
    assert cross_carrier[1] == 403


@pytest.mark.asyncio
async def test_get_shipment_detail_succeeds_for_an_own_shipment(session, monkeypatch):
    monkeypatch.setattr(
        carrier_repo,
        "get_fleet_shipment",
        AsyncMock(return_value={"shipment_id": OWN_SHIPMENT, "carrier_id": OWN_CARRIER}),
    )
    monkeypatch.setattr(carrier_repo, "list_shipment_history", AsyncMock(return_value=[]))

    payload = await carrier_reads.get_shipment_detail(session, _ctx(), OWN_SHIPMENT)
    assert payload["shipment"]["shipment_id"] == OWN_SHIPMENT
    assert payload["scope"] == {"carrier_id": OWN_CARRIER, "read_only": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("shipment_id", [OTHER_SHIPMENT, "SHP-DOES-NOT-EXIST"])
async def test_get_shipment_detail_refuses_rather_than_returning_empty(
    session, monkeypatch, shipment_id
):
    """The repository scopes in SQL, so both cases arrive as `None` -- and both must raise.

    Explicitly asserts a raise rather than an empty/None payload: issue #27's rollback note calls
    silent emptiness the failure mode to test hardest.
    """
    monkeypatch.setattr(carrier_repo, "get_fleet_shipment", AsyncMock(return_value=None))
    history = AsyncMock(return_value=[])
    monkeypatch.setattr(carrier_repo, "list_shipment_history", history)

    with pytest.raises(AppError) as exc:
        await carrier_reads.get_shipment_detail(session, _ctx(), shipment_id)
    assert exc.value.code == "FORBIDDEN"
    assert exc.value.status_code == 403
    # And the refusal happens before any further data is fetched.
    history.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_shipment_detail_refuses_a_cross_carrier_row_even_if_the_query_returned_one(
    session, monkeypatch
):
    """Defence in depth: the SQL predicate is not the only thing standing between the two carriers.

    Simulates a future refactor that drops `AND s.carrier_id = :carrier_id` from the query. The
    service-tier assertion must still refuse.
    """
    monkeypatch.setattr(
        carrier_repo,
        "get_fleet_shipment",
        AsyncMock(return_value={"shipment_id": OTHER_SHIPMENT, "carrier_id": OTHER_CARRIER}),
    )
    with pytest.raises(AppError) as exc:
        await carrier_reads.get_shipment_detail(session, _ctx(), OTHER_SHIPMENT)
    assert exc.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_every_carrier_read_refuses_a_non_carrier_role(session, monkeypatch):
    """All five tools, not just the detail one -- the gate is per-tool, not per-surface."""
    monkeypatch.setattr(carrier_repo, "count_active_shipments", AsyncMock(return_value=0))
    ops_ctx = _ctx(RoleName.OPERATIONS_EXECUTIVE, carrier_id=None)
    calls = [
        carrier_reads.get_fleet_overview(session, ops_ctx),
        carrier_reads.list_fleet_shipments(session, ops_ctx),
        carrier_reads.get_shipment_detail(session, ops_ctx, OWN_SHIPMENT),
        carrier_reads.list_fleet_exceptions(session, ops_ctx),
        carrier_reads.get_carrier_on_time_performance(session, ops_ctx),
    ]
    for coro in calls:
        with pytest.raises(AppError) as exc:
            await coro
        assert exc.value.code == "FORBIDDEN"


# ---------------------------------------------------------------------------------------------
# 3. No comparative framing (U28) -- checked structurally, not by inspection.
# ---------------------------------------------------------------------------------------------

# Vocabulary that would signal a comparative or cross-carrier field had appeared in a response.
_COMPARATIVE_KEY_TOKENS = (
    "rank",
    "benchmark",
    "percentile",
    "peer",
    "average",
    "median",
    "competitor",
    "other_carrier",
    "all_carrier",
    "cross_carrier",
    "carriers_",
    "facility_total",
    "total_at_facility",
    "industry",
)


def _all_keys(payload) -> list[str]:
    if isinstance(payload, dict):
        keys = list(payload)
        for value in payload.values():
            keys += _all_keys(value)
        return keys
    if isinstance(payload, list):
        return [k for item in payload for k in _all_keys(item)]
    return []


def _assert_no_comparative_framing(payload) -> None:
    for key in _all_keys(payload):
        lowered = key.lower()
        for token in _COMPARATIVE_KEY_TOKENS:
            assert token not in lowered, f"comparative field '{key}' in a carrier response (U28)"


@pytest.mark.asyncio
async def test_fleet_overview_returns_own_figures_with_an_own_vs_own_delta(session, monkeypatch):
    monkeypatch.setattr(carrier_repo, "count_active_shipments", AsyncMock(return_value=18))
    monkeypatch.setattr(carrier_repo, "count_open_exceptions", AsyncMock(return_value=3))
    totals = AsyncMock(side_effect=[{"arrivals": 100, "on_time": 91}, {"arrivals": 80, "on_time": 71}])
    monkeypatch.setattr(carrier_repo, "get_on_time_totals", totals)

    payload = await carrier_reads.get_fleet_overview(session, _ctx())

    assert payload["active_shipment_count"] == 18
    assert payload["open_exception_count"] == 3
    on_time = payload["on_time_performance"]
    assert on_time["percent"] == 91.0
    assert on_time["previous_percent"] == 88.8
    # 91.0 - 88.8; the only comparison on this surface is this carrier against its own past.
    assert on_time["delta_percentage_points"] == 2.2
    _assert_no_comparative_framing(payload)

    # The two windows must partition cleanly, or the delta counts an arrival twice.
    current_kwargs = totals.await_args_list[0].kwargs
    prior_kwargs = totals.await_args_list[1].kwargs
    assert prior_kwargs["window_end"] == current_kwargs["window_start"]
    span = current_kwargs["window_end"] - current_kwargs["window_start"]
    assert span == timedelta(days=30)


@pytest.mark.asyncio
async def test_fleet_overview_reports_unknown_rather_than_zero_when_there_were_no_arrivals(
    session, monkeypatch
):
    monkeypatch.setattr(carrier_repo, "count_active_shipments", AsyncMock(return_value=0))
    monkeypatch.setattr(carrier_repo, "count_open_exceptions", AsyncMock(return_value=0))
    monkeypatch.setattr(
        carrier_repo, "get_on_time_totals", AsyncMock(return_value={"arrivals": 0, "on_time": 0})
    )
    payload = await carrier_reads.get_fleet_overview(session, _ctx())
    assert payload["on_time_performance"]["percent"] is None
    assert payload["on_time_performance"]["delta_percentage_points"] is None


@pytest.mark.asyncio
async def test_on_time_performance_series_is_own_data_only(session, monkeypatch):
    monkeypatch.setattr(
        carrier_repo, "get_on_time_totals", AsyncMock(return_value={"arrivals": 10, "on_time": 9})
    )
    day = datetime(2026, 8, 20, tzinfo=timezone.utc)
    monkeypatch.setattr(
        carrier_repo,
        "get_on_time_daily_series",
        AsyncMock(return_value=[{"day": day, "arrivals": 4, "on_time": 4}]),
    )
    payload = await carrier_reads.get_carrier_on_time_performance(session, _ctx())
    assert payload["percent"] == 90.0
    assert payload["series"] == [{"day": day, "arrivals": 4, "percent": 100.0}]
    _assert_no_comparative_framing(payload)


@pytest.mark.asyncio
async def test_on_time_performance_refuses_an_undesigned_window(session):
    with pytest.raises(AppError) as exc:
        await carrier_reads.get_carrier_on_time_performance(session, _ctx(), "365d")
    assert exc.value.code == "WINDOW_UNSUPPORTED"
    assert exc.value.status_code == 400


# ---------------------------------------------------------------------------------------------
# 4. list_fleet_shipments: filter validation and the three distinct empty states (FR-CAR-006).
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fleet_shipments_returns_rows_for_the_callers_own_carrier(session, monkeypatch):
    listed = AsyncMock(return_value=[{"shipment_id": OWN_SHIPMENT, "has_open_exception": False}])
    monkeypatch.setattr(carrier_repo, "list_fleet_shipments", listed)
    payload = await carrier_reads.list_fleet_shipments(session, _ctx())
    assert payload["items"][0]["shipment_id"] == OWN_SHIPMENT
    assert payload["empty_reason"] is None
    _assert_no_comparative_framing(payload)
    # The repository is called with the identity's carrier, positionally -- not with anything a
    # client supplied.
    assert listed.await_args.args[1] == OWN_CARRIER


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ever", "status_filter", "expected"),
    [
        (0, None, "NONE_YET"),
        (7, None, "NONE_RIGHT_NOW"),
        (7, "CONFIRMED", "NO_MATCH_FOR_FILTER"),
    ],
)
async def test_fleet_shipments_distinguishes_the_three_empty_states(
    session, monkeypatch, ever, status_filter, expected
):
    """`FR-CAR-006` / `edge-cases.md` #5 -- three different copy strings need three signals."""
    monkeypatch.setattr(carrier_repo, "list_fleet_shipments", AsyncMock(return_value=[]))
    monkeypatch.setattr(carrier_repo, "count_shipments_ever", AsyncMock(return_value=ever))
    payload = await carrier_reads.list_fleet_shipments(session, _ctx(), status_filter)
    assert payload["empty_reason"] == expected


@pytest.mark.asyncio
async def test_fleet_shipments_does_not_pay_for_the_lifetime_count_on_the_common_path(
    session, monkeypatch
):
    monkeypatch.setattr(carrier_repo, "list_fleet_shipments", AsyncMock(return_value=[{"a": 1}]))
    ever = AsyncMock(return_value=0)
    monkeypatch.setattr(carrier_repo, "count_shipments_ever", ever)
    await carrier_reads.list_fleet_shipments(session, _ctx())
    ever.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("unsupported", "expected_phrase"),
    [
        # SHOWN is refused unconditionally: it is a presentation-only state with no persisted
        # counterpart anywhere in the product, so no flag can make it answerable (issue #87).
        ("SHOWN", "no persisted counterpart"),
        # HELD is refused only while `TWO_PHASE_HOLD_ENABLED` is off, so this case PINS the
        # flag off below rather than reading the live default -- the default flipped to True on
        # 2026-08-31 and a test that inherits it silently tests a different product. The flag-on
        # path is covered in `test_held_read_paths.py`, beside the rest of the D2 read work.
        ("HELD", "TWO_PHASE_HOLD_ENABLED"),
    ],
)
async def test_fleet_shipments_refuses_promise_states_it_cannot_answer(
    session, unsupported, expected_phrase, monkeypatch
):
    monkeypatch.setattr(carrier_reads.holds, "hold_reads_enabled", lambda: False)
    """Refused with a stated reason, not answered with a misleading empty list.

    Same discipline `scheduling/expiry.py` applies to D2's HELD sweep: report the gap, never
    silently return "you have none of those". Issue #87 split the single reason these two used to
    share, because they are not the same refusal -- one is permanent and one is a flag away.
    """
    with pytest.raises(AppError) as exc:
        await carrier_reads.list_fleet_shipments(session, _ctx(), unsupported)
    assert exc.value.code == "FILTER_UNSUPPORTED"
    assert exc.value.status_code == 400
    assert expected_phrase in exc.value.detail


@pytest.mark.asyncio
async def test_fleet_shipments_has_open_exception_filter_narrows_membership_only(
    session, monkeypatch
):
    listed = AsyncMock(return_value=[])
    monkeypatch.setattr(carrier_repo, "list_fleet_shipments", listed)
    monkeypatch.setattr(carrier_repo, "count_shipments_ever", AsyncMock(return_value=1))
    await carrier_reads.list_fleet_shipments(session, _ctx(), "has_open_exception")
    assert listed.await_args.kwargs["only_with_open_exception"] is True
    # Renamed from `appointment_status` by issue #87: with holds on this value is filtered against
    # the *computed* promise state, and HELD is not an appointment status at all.
    assert listed.await_args.kwargs["promise_state"] is None


@pytest.mark.asyncio
async def test_fleet_exceptions_returns_this_carriers_items(session, monkeypatch):
    monkeypatch.setattr(
        carrier_repo,
        "list_open_exceptions",
        AsyncMock(return_value=[{"reference_id": "EXC-1", "status": "OPEN"}]),
    )
    payload = await carrier_reads.list_fleet_exceptions(session, _ctx())
    assert payload["items"][0]["reference_id"] == "EXC-1"
    _assert_no_comparative_framing(payload)


# ---------------------------------------------------------------------------------------------
# 5. Structural guards over the SQL itself -- the checks that survive a future edit.
# ---------------------------------------------------------------------------------------------


def _resolve_sql_text(node: ast.expr) -> str:
    """Reconstruct the real runtime string a `text(...)` argument node evaluates to.

    Plain `ast.unparse` prints the *name* of an interpolated variable, not its value -- so a
    properly `:carrier_id`-scoped query built from a shared fragment constant (e.g.
    `count_open_exceptions`'s `f"...({_OPEN_EXCEPTION_ITEMS_SQL})..."`, the fix for the 73-vs-75
    count/list mismatch this file's own tests exist to catch) would `ast.unparse` to literal text
    that never contains `:carrier_id` at all, even though the query that actually runs does. This
    resolves each interpolated module-level constant (`_OPEN_EXCEPTION_ITEMS_SQL`,
    `_HAS_OPEN_EXCEPTION_SQL`) to its real value before the guard checks anything, so sharing one
    SQL fragment across two queries doesn't look like an unscoped query. A local variable (a
    conditional WHERE-clause fragment like `inner_filter`/`outer_filter`) isn't a module attribute
    and resolves to an opaque placeholder instead -- fine here, since every function that
    interpolates one also has `:carrier_id` in its own literal text, independent of that fragment.

    Only handles the shapes this module's queries actually use. Anything else raises deliberately:
    a silently-wrong resolution would defeat the point of the guard.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant):
                parts.append(str(value.value))
            elif isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name):
                name = value.value.id
                if hasattr(carrier_repo, name):
                    parts.append(str(getattr(carrier_repo, name)))
                else:
                    parts.append(f"<{name}>")
            else:
                raise AssertionError(f"unsupported f-string segment in carrier.py SQL: {ast.dump(value)}")
        return "".join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _resolve_sql_text(node.left) + _resolve_sql_text(node.right)
    raise AssertionError(f"unsupported SQL argument shape in carrier.py: {ast.dump(node)}")


def _sql_literals() -> list[str]:
    """Every `text(...)` argument in `repositories/carrier.py`, fully resolved to real SQL text."""
    source = inspect.getsource(carrier_repo)
    tree = ast.parse(source)
    literals = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "text":
            literals.append(_resolve_sql_text(node.args[0]))
    return literals


def test_every_carrier_query_is_carrier_scoped():
    """No query in the carrier repository may run without a `:carrier_id` predicate (`M15`).

    This is the guard that catches a future "just one more helpful aggregate" query added without
    the scope predicate -- the exact failure `auth-and-scoping.md` says arrives later through a
    well-meaning addition.
    """
    literals = _sql_literals()
    assert len(literals) == 9, f"expected 9 carrier queries, found {len(literals)}"
    for sql in literals:
        assert ":carrier_id" in sql, f"unscoped carrier query:\n{sql[:400]}"


def test_carrier_sql_never_selects_internal_escalation_mechanics():
    """`components.md` §3 / §7.5.6: status only -- no owner, SLA clock, stepper, or free text."""
    forbidden = (
        "payload_json",
        "resolved_by_user_id",
        "policy_version",
        "recommendation_id",
        "queue_position",
        "cancellation_reason",
        "resolution_note",
        "dedupe_key",
        "severity_code",
    )
    source = inspect.getsource(carrier_repo)
    # Strip comments/docstrings' prose mentions -- only SQL text is being policed here.
    sql_blob = "\n".join(_sql_literals())
    for column in forbidden:
        assert column not in sql_blob, f"'{column}' selected by a carrier query"
    assert "carrier_id" in source  # sanity: the guard is reading the right module


def test_carrier_sql_contains_no_cross_carrier_aggregate():
    """No `count`/`avg` in this repository may sit outside a carrier predicate (`U28`).

    A facility-wide total is the inference leak `auth-and-scoping.md` names explicitly: a carrier
    who knows the facility total and their own share can derive everyone else's.
    """
    aggregate = re.compile(r"\b(count|avg|sum)\s*\(", re.IGNORECASE)
    for sql in _sql_literals():
        if aggregate.search(sql):
            assert ":carrier_id" in sql, f"aggregate without a carrier predicate:\n{sql[:400]}"
        # And nothing may group by a facility, which is how a per-facility total would appear.
        assert "group by f.facility_id" not in sql.lower()
        assert "group by facility_id" not in sql.lower()
