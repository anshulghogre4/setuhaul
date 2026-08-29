"""`GY-G1` (issue #67) tests for the section 7.5.2 gate/yard *read*.

Same `_session_with(...)` sequential-mock shape as `test_gate_yard_service.py` -- this is a sibling
tool, so the fixtures deliberately mirror that file's rather than inventing a second style.

Three things get direct coverage of their own because they are business rules rather than plumbing:
`derive_next_action` (`screens.md` section 3's state -> action table), `normalise_identifier` (the
match semantics, tested against the *real stored formats* from
`docs/database_docs/setuhaul_schema_and_seed.sql`), and the scope derivation (M15/NFR-019 -- the
one property a client must never be able to influence).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.services import gate_yard_reads

FACILITY = "FAC-JAI-01"
OTHER_FACILITY = "FAC-GGN-01"
SHIPMENT = "SHP1015"
PLATE = "RJ14GT4101"


def _gate_ctx(
    *, facility_id: str | None = FACILITY, role: RoleName = RoleName.WAREHOUSE_PLANNER
) -> ExecutionContext:
    return ExecutionContext(
        request_id="req-gate-read-1",
        auth_subject="sub-gate-read-1",
        user_id="USR-GATE-1",
        email="gate@setuhaul.com",
        full_name="Test Gate Officer",
        role_id="ROL003",
        role_name=role,
        facility_id=facility_id,
    )


def _session_returning(rows: list[dict]) -> AsyncMock:
    result = MagicMock()
    result.mappings.return_value.all.return_value = rows
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _row(**overrides) -> dict:
    base = {
        "shipment_id": SHIPMENT,
        "order_reference": "ORD-260804-015",
        "facility_id": FACILITY,
        "current_status": "WAITING",
        "registration_number": PLATE,
        "driver_name": "Rajesh Kumar",
        "carrier_name": "Rajasthan Roadlines",
        "checkin_id": "CHK1015",
        "queue_state": "WAITING_LATE",
        "queue_position": 2,
        "arrival_state": "LATE",
        "actual_dock_id": None,
        "gate_in_ts": datetime(2026, 8, 24, 12, 34, tzinfo=timezone.utc),
        "dock_in_ts": None,
        "unload_start_ts": None,
        "unload_end_ts": None,
        "gate_out_ts": None,
        "appointment_id": "APT1015",
        "appointment_status": "CONFIRMED",
        "appointment_dock_id": "DOCK-JAI-D5",
        "appointment_dock_code": "D5",
        "slot_start_ts": datetime(2026, 8, 24, 12, 30, tzinfo=timezone.utc),
        "slot_end_ts": datetime(2026, 8, 24, 13, 30, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------------------------
# normalise_identifier -- the match semantics, against the real stored formats.
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        # The mockup renders plates spaced ("RJ14 GH 2211"); `vehicles.registration_number` stores
        # them unspaced ("RJ14GT4101"). Both must reach the same needle or a plate search from what
        # the officer can physically read off the truck never matches.
        ("RJ14 GT 4101", "RJ14GT4101"),
        ("rj14gt4101", "RJ14GT4101"),
        ("RJ-14-GT-4101", "RJ14GT4101"),
        # order_reference is stored hyphenated.
        ("ORD-260804-015", "ORD260804015"),
        ("ord260804015", "ORD260804015"),
        ("shp1015", "SHP1015"),
        ("  SHP1015  ".strip(), "SHP1015"),
    ],
)
def test_normalise_identifier_collapses_every_real_stored_format_to_one_needle(typed, expected):
    assert gate_yard_reads.normalise_identifier(typed) == expected


# ---------------------------------------------------------------------------------------------
# derive_next_action -- screens.md section 3's state -> action table, row by row.
# ---------------------------------------------------------------------------------------------

_NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("queue_state", "gate_in", "unload_start", "unload_end", "gate_out", "expected"),
    [
        # `NOT_QUEUED` (no check-in yet) -> Gate in.
        (None, None, None, None, None, "GATE_IN"),
        ("NOT_QUEUED", None, None, None, None, "GATE_IN"),
        # WAITING_* -> Call to dock (all three, including the retry state).
        ("WAITING_EARLY", _NOW, None, None, None, "CALL_TO_DOCK"),
        ("WAITING_LATE", _NOW, None, None, None, "CALL_TO_DOCK"),
        ("WAITING_DOCK_UNAVAILABLE", _NOW, None, None, None, "CALL_TO_DOCK"),
        # CALLED_TO_DOCK -> Dock in.
        ("CALLED_TO_DOCK", _NOW, None, None, None, "DOCK_IN"),
        # IN_DOCK, no unload recorded -> Start unload; unload started -> End unload.
        ("IN_DOCK", _NOW, None, None, None, "START_UNLOAD"),
        ("IN_DOCK", _NOW, _NOW, None, None, "END_UNLOAD"),
        # COMPLETED -> Gate out.
        ("COMPLETED", _NOW, _NOW, _NOW, None, "GATE_OUT"),
        # Gated out already -> no button at all (edge-cases.md #6), from any state.
        ("COMPLETED", _NOW, _NOW, _NOW, _NOW, None),
        ("IN_DOCK", _NOW, None, None, _NOW, None),
    ],
)
def test_derive_next_action_matches_the_screens_state_to_action_table(
    queue_state, gate_in, unload_start, unload_end, gate_out, expected
):
    action = gate_yard_reads.derive_next_action(
        queue_state=queue_state,
        gate_in_ts=gate_in,
        unload_start_ts=unload_start,
        unload_end_ts=unload_end,
        gate_out_ts=gate_out,
    )
    assert action == expected
    # Never a code the kiosk has no button for.
    assert action is None or action in gate_yard_reads.NEXT_ACTIONS


def test_every_queue_state_the_writes_can_produce_has_a_derived_action():
    """No `facility_checkins.queue_state` may leave the kiosk with nothing to render.

    Driven off `gate_yard_service.QUEUE_STATES` (the live CHECK constraint's own value list) so a
    state added there later fails here rather than silently producing a blank screen.
    """
    from app.services.gate_yard_service import QUEUE_STATES

    for state in QUEUE_STATES:
        action = gate_yard_reads.derive_next_action(
            queue_state=state,
            gate_in_ts=_NOW,
            unload_start_ts=_NOW if state == "COMPLETED" else None,
            unload_end_ts=_NOW if state == "COMPLETED" else None,
            gate_out_ts=None,
        )
        assert action in gate_yard_reads.NEXT_ACTIONS, state


def test_derive_next_action_offers_gate_in_when_the_state_column_disagrees_with_the_timestamps():
    """A row with a queue_state but no `gate_in_ts` is not gated in.

    Every write except `record_gate_in` refuses such a row with `NOT_CHECKED_IN`
    (`gate_yard_service.py`), so offering anything else would hand the kiosk a button the server
    would then reject.
    """
    assert (
        gate_yard_reads.derive_next_action(
            queue_state="CALLED_TO_DOCK",
            gate_in_ts=None,
            unload_start_ts=None,
            unload_end_ts=None,
            gate_out_ts=None,
        )
        == "GATE_IN"
    )


# ---------------------------------------------------------------------------------------------
# search_gate_yard_trucks -- Flow 1's three branches.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_a_single_match_with_the_full_identity_card_shape():
    session = _session_returning([_row()])

    result = await gate_yard_reads.search_gate_yard_trucks(
        session, _gate_ctx(), query="RJ14 GT 4101"
    )

    assert result.code == "MATCH"
    assert result.match_count == 1
    assert result.truncated is False
    match = result.matches[0]
    # components.md section 3's card: identity, carrier, state, appointment interval with its dock.
    assert match.shipment_id == SHIPMENT
    assert match.registration_number == PLATE
    assert match.driver_name == "Rajesh Kumar"
    assert match.carrier_name == "Rajasthan Roadlines"
    assert match.queue_state == "WAITING_LATE"
    assert match.appointment_dock_code == "D5"
    assert match.slot_start_ts is not None and match.slot_end_ts is not None
    # flows-and-states.md Flow 5: the kiosk submits the *appointment's* dock, so the read has to
    # carry the id, not just the human-facing code.
    assert match.appointment_dock_id == "DOCK-JAI-D5"
    assert match.next_action == "CALL_TO_DOCK"


@pytest.mark.asyncio
async def test_search_normalises_the_typed_query_before_binding_it():
    session = _session_returning([_row()])

    await gate_yard_reads.search_gate_yard_trucks(session, _gate_ctx(), query="  rj14-gt-4101 ")

    params = session.execute.await_args.args[1]
    assert params["needle"] == PLATE
    # The raw query is echoed back for Flow 1.3's copy, but never bound.
    assert params["facility_id"] == FACILITY


@pytest.mark.asyncio
async def test_search_reports_no_match_as_a_result_not_an_error():
    """Flow 1.3 keeps the officer on the search screen; a 404 would not."""
    session = _session_returning([])

    result = await gate_yard_reads.search_gate_yard_trucks(session, _gate_ctx(), query=SHIPMENT)

    assert result.code == "NO_MATCH"
    assert result.matches == []
    assert result.match_count == 0
    assert result.query == SHIPMENT


@pytest.mark.asyncio
async def test_search_reports_multiple_matches_for_one_plate_on_two_live_shipments():
    """`screens.md` section 2's "a plate shared across trips" case, Flow 1.4's list."""
    session = _session_returning(
        [_row(), _row(shipment_id="SHP1099", checkin_id=None, queue_state=None, gate_in_ts=None)]
    )

    result = await gate_yard_reads.search_gate_yard_trucks(session, _gate_ctx(), query=PLATE)

    assert result.code == "MULTIPLE_MATCHES"
    assert result.match_count == 2
    assert [m.next_action for m in result.matches] == ["CALL_TO_DOCK", "GATE_IN"]


@pytest.mark.asyncio
async def test_search_caps_the_disambiguation_list_and_says_so():
    session = _session_returning([_row(shipment_id=f"SHP20{i:02d}") for i in range(12)])

    result = await gate_yard_reads.search_gate_yard_trucks(session, _gate_ctx(), query=PLATE)

    assert result.match_count == gate_yard_reads.MAX_MATCHES
    assert result.truncated is True


@pytest.mark.asyncio
async def test_search_returns_a_gated_out_truck_with_its_dwell_and_no_next_action():
    """`edge-cases.md` #6 -- the card still renders, the button does not."""
    gate_in = datetime(2026, 8, 24, 7, 35, tzinfo=timezone.utc)
    gate_out = gate_in + timedelta(minutes=82)
    session = _session_returning(
        [
            _row(
                queue_state="COMPLETED",
                gate_in_ts=gate_in,
                gate_out_ts=gate_out,
                unload_start_ts=gate_in + timedelta(minutes=20),
                unload_end_ts=gate_in + timedelta(minutes=70),
                current_status="COMPLETED",
            )
        ]
    )

    result = await gate_yard_reads.search_gate_yard_trucks(session, _gate_ctx(), query=SHIPMENT)

    match = result.matches[0]
    assert match.next_action is None
    assert match.dwell_min == pytest.approx(82.0)


@pytest.mark.asyncio
async def test_search_defaults_a_shipment_with_no_checkin_row_to_not_queued():
    session = _session_returning(
        [
            _row(
                checkin_id=None, queue_state=None, queue_position=None, arrival_state=None,
                gate_in_ts=None, current_status="IN_TRANSIT",
            )
        ]
    )

    result = await gate_yard_reads.search_gate_yard_trucks(session, _gate_ctx(), query=SHIPMENT)

    match = result.matches[0]
    assert match.queue_state == "NOT_QUEUED"
    assert match.checkin_id is None
    assert match.dwell_min is None
    assert match.next_action == "GATE_IN"


@pytest.mark.asyncio
async def test_search_bounds_results_to_recently_gated_out_trucks():
    """Without this bound an exact plate match returns every trip that vehicle ever made."""
    session = _session_returning([_row()])
    before = datetime.now(timezone.utc)

    await gate_yard_reads.search_gate_yard_trucks(session, _gate_ctx(), query=PLATE)

    cutoff = session.execute.await_args.args[1]["recent_cutoff"]
    expected = before - timedelta(hours=gate_yard_reads.RECENT_GATE_OUT_HOURS)
    assert abs((cutoff - expected).total_seconds()) < 5


# ---------------------------------------------------------------------------------------------
# Scope derivation -- M15 / NFR-019.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_scopes_a_facility_bound_officer_to_their_own_facility():
    session = _session_returning([_row()])

    result = await gate_yard_reads.search_gate_yard_trucks(session, _gate_ctx(), query=SHIPMENT)

    sql = str(session.execute.await_args.args[0])
    assert "s.destination_facility_id = :facility_id" in sql
    assert session.execute.await_args.args[1]["facility_id"] == FACILITY
    assert result.facility_id == FACILITY


@pytest.mark.asyncio
async def test_search_accepts_no_facility_argument_at_all():
    """M15: there is no client-supplied scope id for this tool to validate, by construction."""
    import inspect

    params = inspect.signature(gate_yard_reads.search_gate_yard_trucks).parameters
    assert "facility_id" not in params
    assert set(params) == {"session", "ctx", "query"}


@pytest.mark.asyncio
async def test_search_refuses_a_facility_bound_officer_with_no_mapped_facility():
    session = _session_returning([])

    with pytest.raises(AppError) as exc:
        await gate_yard_reads.search_gate_yard_trucks(
            session, _gate_ctx(facility_id=None), query=SHIPMENT
        )

    assert exc.value.code == "FORBIDDEN"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_lets_an_admin_reach_every_facility_matching_their_write_reach():
    """`assert_facility_write_scope` already lets ADMIN write at any facility; the read agrees."""
    session = _session_returning([_row(facility_id=OTHER_FACILITY)])

    result = await gate_yard_reads.search_gate_yard_trucks(
        session, _gate_ctx(facility_id=None, role=RoleName.ADMIN), query=SHIPMENT
    )

    sql = str(session.execute.await_args.args[0])
    assert "destination_facility_id = :facility_id" not in sql
    assert "facility_id" not in session.execute.await_args.args[1]
    assert result.facility_id is None
    assert result.matches[0].facility_id == OTHER_FACILITY


# ---------------------------------------------------------------------------------------------
# Input validation.
# ---------------------------------------------------------------------------------------------


def test_the_route_is_wired_behind_the_same_role_gate_as_the_five_writes():
    """`gate.py` had zero GET routes before this; the gate must not have widened to add one.

    Compares the resolved dependency callables rather than re-asserting the role list, so this
    stays true if the router's `GateCtx` annotation is ever narrowed further.
    """
    from app.api.v1.routers import gate as gate_router
    from app.main import create_app

    # Read off the router itself, not `app.routes`: FastAPI 0.141 keeps included routers wrapped
    # in `_IncludedRouter` rather than flattening their routes onto the app, so `app.routes` no
    # longer exposes them. The app's OpenAPI document is asserted separately below.
    routes = {(r.path, frozenset(r.methods)): r for r in gate_router.router.routes}
    search = routes[("/api/v1/gate/trucks", frozenset({"GET"}))]
    write = routes[("/api/v1/gate/shipments/{shipment_id}/gate-in", frozenset({"POST"}))]

    assert search.endpoint is gate_router.search_trucks
    read_gate = {d.call for d in search.dependant.dependencies}
    write_gate = {d.call for d in write.dependant.dependencies}
    assert read_gate == write_gate

    # M15 again, at the transport layer: no facility id is reachable as a query parameter.
    assert {p.name for p in search.dependant.query_params} == {"query"}

    paths = create_app().openapi()["paths"]
    assert "get" in paths["/api/v1/gate/trucks"]


@pytest.mark.parametrize("query", ["", "  ", "S", "!!", " - "])
@pytest.mark.asyncio
async def test_search_rejects_a_query_too_short_to_be_an_identifier(query):
    session = _session_returning([])

    with pytest.raises(AppError) as exc:
        await gate_yard_reads.search_gate_yard_trucks(session, _gate_ctx(), query=query)

    assert exc.value.code == "QUERY_TOO_SHORT"
    assert exc.value.status_code == 422
    session.execute.assert_not_awaited()
