"""The three consuming read paths that could not see a D2 hold: issues #83, #84, #85.

#53 models a hold as a `dock_occupancy` row with `appointment_id IS NULL` and deliberately does
*not* add `HELD` to `appointments_appointment_status_check` (`SOLUTION_DESIGN.md` §4: *"Held is not
booked: no `appointments` row exists yet"*). Every read that derived a promise state from
`appointments.appointment_status` was therefore blind to holds -- a display gap on the driver and
carrier surfaces (#83, #85) and a **correctness** gap on the planner's displacement check (#84),
where the preview said "no displacement" about an interval PostgreSQL was already defending.

## What these tests can and cannot prove, stated because it decided their shape

They are mock-session tests, so **no constraint is ever evaluated** and no column is ever resolved.
That is exactly how the `_claim_dock_occupancy` `shipment_id` omission reached a migration dry run
undetected, so this module deliberately does not pretend otherwise. It covers three things a mock
*can* prove:

1. **Flag-off is byte-identical.** The statement issued with `TWO_PHASE_HOLD_ENABLED=false` is the
   one that shipped, character for character. This is the load-bearing safety property: the D2
   columns do not exist until the migration is applied, and PostgreSQL resolves column references
   at parse time, so a statement naming `o.state` on an unmigrated database fails outright rather
   than returning nothing.
2. **Flag-on assembles the right answer** from rows shaped like the ones the real query returns.
3. **Structural guards over the SQL text** -- the checks that survive a future edit, including the
   `shipment_id` class of bug the coordinator asked to be made un-repeatable.

The behaviour against a *real* exclusion constraint and real columns is proven separately, by a
throwaway-cluster run recorded in this change's report and by
`tests/integration/test_live_held_slot_lifecycle.py`.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.core.settings import get_settings
from app.repositories import carrier as carrier_repo
from app.repositories import operations as operations_repo
from app.scheduling import allocation, holds, snapshot
from app.services import carrier_reads, driver_reads, planner_service

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
REPO_ROOT = Path(__file__).resolve().parents[3]
D2_MIGRATION = (
    REPO_ROOT / "supabase" / "migrations" / "20260829134929_d2_held_state_dock_occupancy.sql"
)


@pytest.fixture
def flag_on(monkeypatch):
    """Turn the D2 two-phase path on for one test, and put the cache back afterwards.

    `get_settings` is `lru_cache`d, so the clear has to happen on both sides -- without the second
    one a later test in the same session would inherit this test's flag.
    """
    monkeypatch.setenv("TWO_PHASE_HOLD_ENABLED", "true")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("TWO_PHASE_HOLD_ENABLED", raising=False)
    get_settings.cache_clear()


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.setenv("TWO_PHASE_HOLD_ENABLED", "false")
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("TWO_PHASE_HOLD_ENABLED", raising=False)
    get_settings.cache_clear()


def _result(rows):
    m = MagicMock()
    m.mappings.return_value.all.return_value = rows
    m.mappings.return_value.first.return_value = rows[0] if rows else None
    return m


def _session(*row_sets):
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_result(r) for r in row_sets])
    return session


def _executed_sql(session, call=0) -> str:
    """The SQL text of one `session.execute` call, as the database would receive it."""
    return str(session.execute.await_args_list[call].args[0])


# =================================================================================================
# #84 -- the planner's displacement check. The correctness one.
# =================================================================================================


@pytest.mark.asyncio
async def test_occupancy_query_is_unchanged_with_the_flag_off(flag_off):
    """The safety property the whole gating design rests on.

    Not a style assertion: `dock_occupancy.state` does not exist until the D2 migration is applied.
    If this statement ever mentions it while the flag is off, every planner queue read on an
    unmigrated database becomes an `UndefinedColumn` error rather than a degraded answer.
    """
    session = _session([])
    await operations_repo.list_live_dock_occupancy(
        session, facility_id="FAC-JAI-01", range_start=NOW, range_end=NOW + timedelta(hours=2),
        active_statuses=["PENDING_CONFIRMATION"], include_holds=False,
    )
    sql = _executed_sql(session)
    assert "o.state" not in sql
    assert "o.expires_at" not in sql
    assert "o.shipment_id" not in sql
    assert "JOIN public.appointments a ON a.appointment_id = o.appointment_id" in sql
    assert "LEFT JOIN public.appointments" not in sql


@pytest.mark.asyncio
async def test_occupancy_query_left_joins_appointments_with_the_flag_on(flag_on):
    """#84's fix: the INNER JOIN is what made a hold invisible, so it has to stop being one."""
    session = _session([])
    await operations_repo.list_live_dock_occupancy(
        session, facility_id="FAC-JAI-01", range_start=NOW, range_end=NOW + timedelta(hours=2),
        active_statuses=["PENDING_CONFIRMATION"],
        include_holds=True, hold_states=list(snapshot.CAPACITY_CONSUMING_STATES),
    )
    sql = _executed_sql(session)
    assert "LEFT JOIN public.appointments a ON a.appointment_id = o.appointment_id" in sql
    assert "o.appointment_id IS NULL AND o.state = ANY(:hold_states)" in sql
    # A capacity claim must never vanish because a *display* column is NULL -- `shipment_id` ships
    # nullable (the D2 migration defers SET NOT NULL), so this join cannot be INNER.
    assert "LEFT JOIN public.shipments" in sql


@pytest.mark.asyncio
async def test_occupancy_query_does_not_filter_holds_on_expiry(flag_on):
    """Deliberately *not* `expires_at > now()`, and this test exists to stop someone "fixing" it.

    §0.8 mandates that filter for reads that answer *"what promise does this party have"*. This
    query answers *"what will PostgreSQL refuse"*, and the exclusion constraint's predicate is
    `WHERE (state IN (...))` with no time term -- verified empirically against PostgreSQL 18.3 on
    2026-08-29, where a hold whose TTL lapsed ten minutes earlier still raised
    `dock_occupancy_dock_id_window_excl`. Adding the filter here re-creates #84 in miniature.
    """
    session = _session([])
    await operations_repo.list_live_dock_occupancy(
        session, facility_id="FAC-JAI-01", range_start=NOW, range_end=NOW + timedelta(hours=2),
        active_statuses=["PENDING_CONFIRMATION"],
        include_holds=True, hold_states=list(snapshot.CAPACITY_CONSUMING_STATES),
    )
    sql = _executed_sql(session)
    assert "expires_at >" not in sql


def _queue_row(appointment_id="APT1", dock_id="DOCK-JAI-D1"):
    start = NOW + timedelta(hours=1)
    end = start + timedelta(minutes=75)
    return {
        "appointment_id": appointment_id, "shipment_id": "SHP1", "slot_id": "SLOT1",
        "appointment_status": "PENDING_CONFIRMATION", "booking_source": "DRIVER_CHAT",
        "is_current": 1, "booked_at": NOW - timedelta(minutes=5), "order_reference": "ORD1",
        "driver_id": "DRV1", "carrier_id": "CAR1", "priority_code": "NORMAL",
        "required_dock_type": "STANDARD", "expected_unload_min": 60, "original_eta_ts": start,
        "driver_name": "R", "carrier_name": "C", "facility_id": "FAC-JAI-01",
        "slot_start_ts": start, "slot_end_ts": end, "dock_id": dock_id, "dock_code": "D1",
        "dock_type": "STANDARD",
        # No claim of its own -- the E1.1/D12 case `_conflicts_for` exists for, and the only shape
        # in which another live claim can legitimately overlap this request's interval.
        "occupancy_start": None, "occupancy_end": None,
        "interval_start": start, "interval_end": end,
        "effective_eta_ts": start, "eta_confidence": "HIGH", "eta_source": "DRIVER_DECLARED",
        "queue_state": None, "queue_position": None, "gate_in_ts": None,
        "limit_exception_id": None, "latest_acceptable_ts": None,
    }


def _hold_occupancy(occupancy_id=77, dock_id="DOCK-JAI-D1"):
    start = NOW + timedelta(hours=1, minutes=10)
    return {
        "occupancy_id": occupancy_id, "dock_id": dock_id, "appointment_id": None,
        "window_start": start, "window_end": start + timedelta(minutes=60),
        "shipment_id": "SHP-OTHER", "appointment_status": "HELD",
        "claim_source": "dock_occupancy_hold",
        "hold_expires_at": NOW + timedelta(seconds=90), "order_reference": None,
    }


@pytest.mark.asyncio
async def test_displacement_names_a_hold_that_would_refuse_the_confirm(flag_on, monkeypatch):
    """#84 end to end through the service: the preview must stop lying.

    Before this, `_conflicts_for` never saw the hold, so the row rendered `displacement: NONE`
    while the database would have refused the write on `dock_occupancy_dock_id_window_excl`.
    """
    monkeypatch.setattr(operations_repo, "list_planner_queue_rows",
                        AsyncMock(return_value=[_queue_row()]))
    monkeypatch.setattr(operations_repo, "list_live_dock_occupancy",
                        AsyncMock(return_value=[_hold_occupancy()]))
    from app.core.clock import FrozenClock

    queue = await planner_service.get_planner_queue(
        session=AsyncMock(), ctx=_planner_ctx(), facility_id="FAC-JAI-01", clock=FrozenClock(NOW)
    )
    row = queue.items[0]
    assert row.displacement.status == "CONFLICT"
    conflict = row.displacement.conflicts[0]
    assert conflict["claim_id"] == "hold:77"
    assert conflict["claim_source"] == "dock_occupancy_hold"
    assert conflict["appointment_status"] == "HELD"
    # The countdown a planner needs to judge whether to wait it out rather than displace it.
    assert conflict["hold_expires_at"] is not None


@pytest.mark.asyncio
async def test_a_hold_never_self_excludes_a_queue_row(flag_on, monkeypatch):
    """`_conflicts_for`'s self-exclusion compares appointment ids, and a hold has none.

    Guards the `str(None) == str(appointment_id)` shape: it happened to be a never-match, but only
    by accident, and a future `or ""` normalisation there would silently drop every hold.
    """
    monkeypatch.setattr(operations_repo, "list_planner_queue_rows",
                        AsyncMock(return_value=[_queue_row()]))
    monkeypatch.setattr(operations_repo, "list_live_dock_occupancy",
                        AsyncMock(return_value=[_hold_occupancy(), _hold_occupancy(occupancy_id=78)]))
    from app.core.clock import FrozenClock

    queue = await planner_service.get_planner_queue(
        session=AsyncMock(), ctx=_planner_ctx(), facility_id="FAC-JAI-01", clock=FrozenClock(NOW)
    )
    ids = sorted(c["claim_id"] for c in queue.items[0].displacement.conflicts)
    # Two *distinct* holds, not one: before `claim_id` both hashed as the literal "None".
    assert ids == ["hold:77", "hold:78"]


def test_two_holds_do_not_collapse_in_the_snapshot_digest():
    """The reason `claim_id` exists rather than reusing `appointment_id`.

    `conflicts` is inside the digest, so if two different holds both serialised as `"None"` the
    hash would not change when one was replaced by another -- a real capacity drift the planner
    would never be told about.
    """
    one = snapshot.planner_snapshot_hash(
        appointment_id="APT1", appointment_status="PENDING_CONFIRMATION", is_current=1,
        dock_id="D", interval_start=NOW, interval_end=NOW + timedelta(hours=1),
        interval_source=snapshot.INTERVAL_SOURCE_OCCUPANCY, conflict_ids=["hold:77"],
    )
    other = snapshot.planner_snapshot_hash(
        appointment_id="APT1", appointment_status="PENDING_CONFIRMATION", is_current=1,
        dock_id="D", interval_start=NOW, interval_end=NOW + timedelta(hours=1),
        interval_source=snapshot.INTERVAL_SOURCE_OCCUPANCY, conflict_ids=["hold:78"],
    )
    assert one != other


def test_claim_id_is_unchanged_for_an_appointment_backed_claim():
    """Why the digest of a hold-free queue is byte-identical before and after #84."""
    assert snapshot.claim_id({"appointment_id": "APT9", "occupancy_id": 5}) == "APT9"
    assert snapshot.claim_id({"appointment_id": None, "occupancy_id": 5}) == "hold:5"


def test_the_write_path_and_the_producer_name_a_hold_identically():
    """The hash coupling, which is the part of #84 most likely to be broken by a later edit.

    `planner_service` produces the digest and `scheduling/snapshot` recomputes it under the row
    lock. If only one of them learned about holds, every confirm on a contested dock would return
    `SNAPSHOT_STALE` with no way to tell a real drift from a skew -- an outage of the throughput
    path. They share one `claim_id` implementation precisely so this cannot drift.
    """
    assert planner_service._claim_id is snapshot.claim_id


def test_snapshot_sql_left_joins_and_uses_is_distinct_from_when_holds_are_on():
    """`o.appointment_id <> t.appointment_id` is NULL for a hold -- i.e. filtered out.

    This is the subtlest half of #84: the self-exclusion predicate would have silently removed
    every hold from the write-path refusal set even after the join was widened.
    """
    with_holds = snapshot._snapshot_sql(include_holds=True)
    assert "LEFT JOIN public.appointments oa" in with_holds
    assert "o.appointment_id IS DISTINCT FROM t.appointment_id" in with_holds
    assert "o.state = ANY(:capacity_states)" in with_holds

    without = snapshot._snapshot_sql(include_holds=False)
    assert "o.state" not in without
    assert "JOIN public.appointments oa ON oa.appointment_id = o.appointment_id" in without
    assert "IS DISTINCT FROM" not in without


@pytest.mark.asyncio
async def test_block_dock_impact_names_a_stranded_hold(flag_on):
    """FR-PLN-007 names the affected set *before* committing -- and a hold is affected.

    `block_dock` deletes no claims (that is what makes it a `CAPACITY_EVENT_CASCADE`), so an
    unnamed hold is a driver whose confirm is about to fail with nobody having been told.
    """
    dock = {"dock_id": "DOCK-JAI-D1", "facility_id": "FAC-JAI-01", "dock_code": "D1",
            "dock_status": "ACTIVE"}
    affected = [{
        "occupancy_id": 77, "appointment_id": None, "dock_id": "DOCK-JAI-D1",
        "window_start": NOW, "window_end": NOW + timedelta(hours=1),
        "appointment_status": "HELD", "shipment_id": "SHP-OTHER",
        "claim_source": "dock_occupancy_hold", "hold_expires_at": NOW + timedelta(seconds=90),
        "driver_id": "DRV9", "priority_code": "NORMAL", "load_weight_kg": 100,
    }]
    session = _session([dock], affected, [])
    impact = await planner_service.get_dock_block_impact(
        session, _planner_ctx(), dock_id="DOCK-JAI-D1",
        window_start=NOW, window_end=NOW + timedelta(hours=2),
    )
    assert impact.affected_count == 1
    assert impact.affected_appointments[0]["claim_source"] == "dock_occupancy_hold"
    sql = _executed_sql(session, call=1)
    assert "LEFT JOIN public.appointments a" in sql


@pytest.mark.asyncio
async def test_block_dock_impact_sql_is_unchanged_with_the_flag_off(flag_off):
    dock = {"dock_id": "DOCK-JAI-D1", "facility_id": "FAC-JAI-01", "dock_code": "D1",
            "dock_status": "ACTIVE"}
    session = _session([dock], [], [])
    await planner_service.get_dock_block_impact(
        session, _planner_ctx(), dock_id="DOCK-JAI-D1",
        window_start=NOW, window_end=NOW + timedelta(hours=2),
    )
    sql = _executed_sql(session, call=1)
    assert "o.state" not in sql
    assert "JOIN public.appointments a ON a.appointment_id = o.appointment_id" in sql


def _planner_ctx():
    from app.core.execution_context import ExecutionContext, RoleName

    return ExecutionContext(
        request_id="r", auth_subject="s", user_id="USR101", email="p@x.com", full_name="P",
        role_id="ROL003", role_name=RoleName.WAREHOUSE_PLANNER, facility_id="FAC-JAI-01",
    )


def _driver_ctx():
    from app.core.execution_context import ExecutionContext, RoleName

    return ExecutionContext(
        request_id="r", auth_subject="s", user_id="USR001", email="d@x.com", full_name="D",
        role_id="ROL001", role_name=RoleName.DRIVER, driver_id="DRV1", facility_id="FAC-JAI-01",
    )


# =================================================================================================
# #83 -- driver chat
# =================================================================================================


@pytest.mark.asyncio
async def test_live_hold_read_issues_no_query_at_all_with_the_flag_off(flag_off):
    """Flag-off is not "returns nothing" -- it is "never asks", which is the only safe answer.

    Asking would name `o.state` on a database where the D2 migration may not be applied, and that
    is an `UndefinedColumn` failure of the whole enclosing read, not an empty result.
    """
    session = AsyncMock()
    result = await holds.live_hold_for_shipment(session, shipment_id="SHP1", now=NOW)
    assert result is None
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_live_hold_read_applies_the_lazy_expiry_check(flag_on):
    """§0.8: *"Never depend on the sweeper for correctness -- only for hygiene."*

    The mirror image of `test_occupancy_query_does_not_filter_holds_on_expiry`: a *promise* read
    must drop a lapsed hold, because telling a driver "reserved for you" about one is a lie.
    """
    session = _session([])
    await holds.live_hold_for_shipment(session, shipment_id="SHP1", now=NOW)
    sql = _executed_sql(session)
    assert "o.state = 'HELD'" in sql
    assert "o.expires_at > :now" in sql


@pytest.mark.asyncio
async def test_live_hold_read_returns_the_countdown_the_ui_needs(flag_on):
    """E5.1's HELD screens need `hold_id` and a countdown; U48 says the server computes it."""
    row = {
        "occupancy_id": 77, "dock_id": "DOCK-JAI-D1", "shipment_id": "SHP1", "state": "HELD",
        "expires_at": NOW + timedelta(seconds=60), "window_start": NOW, "window_end": NOW,
        "slot_id": "SLOT1", "facility_id": "FAC-JAI-01", "slot_start_ts": NOW,
        "slot_end_ts": NOW, "dock_code": "D1", "dock_type": "STANDARD",
    }
    hold = await holds.live_hold_for_shipment(_session([row]), shipment_id="SHP1", now=NOW)
    assert hold["hold_id"] == "77"  # the same key `confirm_held_slot` takes as its argument
    assert hold["expires_in_seconds"] == 60


@pytest.mark.asyncio
async def test_current_appointment_surfaces_a_hold(flag_on, monkeypatch):
    """#83: a driver mid-hold used to get `appointment: null` -- "you have no promise" -- moments
    after being told a slot was reserved for them for 90 seconds."""
    monkeypatch.setattr(driver_reads, "get_shipment_details", AsyncMock(return_value={}))
    hold = {"hold_id": "77", "expires_at": NOW + timedelta(seconds=90), "expires_in_seconds": 90}
    monkeypatch.setattr(driver_reads.holds, "live_hold_for_shipment",
                        AsyncMock(return_value=hold))
    payload = await driver_reads.get_current_appointment(_session([]), _driver_ctx(), "SHP1")
    assert payload["hold"]["hold_id"] == "77"
    assert payload["promise_state"] == "HELD"
    assert payload["promise_state_source"] == "dock_occupancy_hold"


@pytest.mark.asyncio
async def test_current_appointment_is_unchanged_when_no_hold_exists(flag_off, monkeypatch):
    """The flag-off contract: same appointment, same shape, `hold` simply absent."""
    monkeypatch.setattr(driver_reads, "get_shipment_details", AsyncMock(return_value={}))
    row = {"appointment_id": "APT1", "appointment_status": "PENDING_CONFIRMATION"}
    payload = await driver_reads.get_current_appointment(_session([row]), _driver_ctx(), "SHP1")
    assert payload["appointment"]["appointment_id"] == "APT1"
    assert payload["hold"] is None
    assert payload["promise_state"] == "PENDING_CONFIRMATION"
    assert payload["promise_state_source"] == "appointments"


@pytest.mark.parametrize(
    ("status", "has_hold", "expected_state", "expected_source"),
    [
        # Rule 1: an active appointment outranks a live hold. Reachable, not hypothetical --
        # `confirm_held_slot` has an IntegrityError branch for exactly this overlap.
        ("PENDING_CONFIRMATION", True, "PENDING_CONFIRMATION", "appointments"),
        ("CONFIRMED", True, "CONFIRMED", "appointments"),
        # Rule 2: a live hold outranks a *non*-active appointment.
        ("CANCELLED", True, "HELD", "dock_occupancy_hold"),
        ("EXPIRED", True, "HELD", "dock_occupancy_hold"),
        (None, True, "HELD", "dock_occupancy_hold"),
        # Rule 3: otherwise the appointment answers, exactly as before this issue.
        ("CANCELLED", False, "CANCELLED", "appointments"),
        (None, False, None, None),
    ],
)
def test_promise_state_precedence_is_the_same_in_both_implementations(
    status, has_hold, expected_state, expected_source
):
    """`services/` may not import from `scheduling/` upward, so the rule exists twice.

    That is a deliberate layering choice rather than an oversight, and this is the test that keeps
    the two copies honest -- case for case, not by inspection.
    """
    hold = {"hold_id": "77"} if has_hold else None
    appointment = {"appointment_status": status} if status else None

    assert driver_reads.resolve_promise_state(appointment, hold) == (expected_state, expected_source)
    assert allocation._resolve_promise_state(status, hold) == (expected_state, expected_source)


@pytest.mark.asyncio
async def test_request_status_reports_a_hold_instead_of_no_appointment_request(flag_on, monkeypatch):
    """The second #83 path. `_appointment_request_status_row` starts `FROM public.appointments`,
    so for a shipment whose only promise is a hold it returned nothing and this tool answered
    `NO_APPOINTMENT_REQUEST` -- the most misleading answer available."""
    monkeypatch.setattr(allocation, "_shipment_for_status",
                        AsyncMock(return_value={"shipment_id": "SHP1", "driver_id": "DRV1",
                                                "destination_facility_id": "FAC-JAI-01"}))
    monkeypatch.setattr(allocation, "_appointment_request_status_row", AsyncMock(return_value=None))
    monkeypatch.setattr(allocation, "_appointment_request_history", AsyncMock(return_value=[]))
    monkeypatch.setattr(holds, "live_hold_for_shipment",
                        AsyncMock(return_value={"hold_id": "77",
                                                "expires_at": NOW + timedelta(seconds=90)}))
    result = await allocation.get_appointment_request_status(
        AsyncMock(), _driver_ctx(), shipment_id="SHP1"
    )
    assert result.code == "SLOT_HELD"
    assert result.hold["hold_id"] == "77"
    assert result.promise_state == "HELD"
    # A hold waits on the *driver*, inside its TTL -- not on a planner. D6's human gate belongs to
    # PENDING_CONFIRMATION and must not be claimed here.
    assert result.requires_human_confirmation is False


@pytest.mark.asyncio
async def test_request_status_is_unchanged_with_no_hold(flag_off, monkeypatch):
    monkeypatch.setattr(allocation, "_shipment_for_status",
                        AsyncMock(return_value={"shipment_id": "SHP1", "driver_id": "DRV1",
                                                "destination_facility_id": "FAC-JAI-01"}))
    monkeypatch.setattr(allocation, "_appointment_request_status_row",
                        AsyncMock(return_value={"appointment_id": "APT1",
                                                "appointment_status": "PENDING_CONFIRMATION"}))
    monkeypatch.setattr(allocation, "_appointment_request_history", AsyncMock(return_value=[]))
    result = await allocation.get_appointment_request_status(
        AsyncMock(), _driver_ctx(), shipment_id="SHP1"
    )
    assert result.code == "APPOINTMENT_PENDING_CONFIRMATION"
    assert result.requires_human_confirmation is True
    assert result.hold is None


# =================================================================================================
# #85 -- carrier portal
# =================================================================================================


@pytest.mark.asyncio
async def test_carrier_sql_is_unchanged_with_the_flag_off(flag_off):
    session = _session([])
    await carrier_repo.list_fleet_shipments(session, "CAR001", include_holds=False)
    sql = _executed_sql(session)
    assert "appt.appointment_status AS promise_state," in sql
    assert "dock_occupancy" not in sql

    session2 = _session([])
    await carrier_repo.get_fleet_shipment(session2, "CAR001", "SHP1", include_holds=False)
    assert "dock_occupancy" not in _executed_sql(session2)


@pytest.mark.asyncio
async def test_carrier_sql_joins_the_hold_with_the_flag_on(flag_on):
    """#85: `promise_state` was a bare alias of `appointments.appointment_status`, and the D2
    migration deliberately never adds 'HELD' there, so a carrier could not see a hold however the
    frontend flag was set -- exactly as `carrier/lib/flags.ts` predicted."""
    for call in (
        lambda s: carrier_repo.list_fleet_shipments(s, "CAR001", include_holds=True),
        lambda s: carrier_repo.get_fleet_shipment(s, "CAR001", "SHP1", include_holds=True),
    ):
        session = _session([])
        await call(session)
        sql = _executed_sql(session)
        assert "public.dock_occupancy o" in sql
        assert "o.state = 'HELD'" in sql
        # A promise read, so §0.8's lazy expiry check is mandatory here.
        assert "o.expires_at > now()" in sql
        assert "THEN 'HELD'" in sql
        assert "hold.expires_at AS hold_expires_at" in sql
        # M15: the hold is joined *inside* the already carrier-scoped statement, never fetched by
        # a query of its own that could reach outside the fleet.
        assert ":carrier_id" in sql


def test_carrier_hold_sql_never_leaks_internal_mechanics():
    """`components.md` §3 forbids internal mechanics on this surface; `policy_version` is one.

    The existing repository-wide guard only inspects `text(...)` literals, and the hold leg is an
    interpolated fragment, so it needs its own assertion.
    """
    for fragment in carrier_repo._hold_sql(True):
        for forbidden in ("policy_version", "payload_json", "dedupe_key", "severity_code"):
            assert forbidden not in fragment


# =================================================================================================
# The `shipment_id` class of bug -- a guard that does not need a database to fire.
# =================================================================================================


def _dock_occupancy_inserts() -> list[tuple[str, str]]:
    """(file, column-list) for every `INSERT INTO public.dock_occupancy` in the application."""
    found = []
    for path in sorted((REPO_ROOT / "backend" / "app").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(
            r"INSERT\s+INTO\s+public\.dock_occupancy\s*\(([^)]*)\)", source, re.IGNORECASE
        ):
            found.append((path.name, match.group(1)))
    return found


def test_every_dock_occupancy_insert_names_shipment_id():
    """The regression guard for the omission that reached a migration dry run undetected.

    `_claim_dock_occupancy` took `shipment_id` as a parameter, used it only in its JOIN, and never
    wrote the column. No mock-session test could catch that -- `AsyncMock` evaluates no constraint
    -- and the database will not catch it either right now, because the D2 migration deliberately
    *defers* `SET NOT NULL` so it can be applied ahead of the code that populates it. Between those
    two deploys the only thing standing between a silent NULL and production is this assertion.

    It is a semantic requirement, not just a schema one: D2 makes `dock_occupancy` the single
    overlap truth for both bookings and holds, and a claim that cannot say *what* it is holding
    capacity for is unusable to `confirm_held_slot`'s M15 scope derivation and to every read fixed
    by issues #83/#84/#85.
    """
    inserts = _dock_occupancy_inserts()
    assert inserts, "no dock_occupancy INSERT found -- this guard is silently vacuous"
    for filename, columns in inserts:
        normalised = {c.strip().strip('"') for c in columns.split(",")}
        assert "shipment_id" in normalised, (
            f"{filename}: an INSERT INTO public.dock_occupancy omits shipment_id. Every capacity "
            f"claim must name the shipment it holds capacity for. Columns were: {sorted(normalised)}"
        )


def test_the_d2_migration_adds_no_dock_occupancy_column_this_guard_has_not_considered():
    """Forces the *next* added column through the same review, rather than letting it slip.

    The `shipment_id` bug was not a typo -- it was a new required column that no existing test knew
    to look for. Pinning the set here means adding another one fails loudly and whoever adds it has
    to decide, explicitly, whether every INSERT must now write it.
    """
    sql = D2_MIGRATION.read_text(encoding="utf-8")
    added = set(re.findall(r"ADD COLUMN IF NOT EXISTS\s+(\w+)", sql))
    # `appointments.expires_at` (issue #64, step 7) is on a different table and is not a claim
    # column, so it is expected in this set but is not subject to the INSERT rule above.
    assert added == {"shipment_id", "state", "expires_at", "policy_version"}, (
        "The D2 migration's dock_occupancy columns changed. Decide whether every "
        "INSERT INTO public.dock_occupancy must now write the new one, then update this test."
    )


def test_holds_capacity_states_mirror_the_migrations_exclusion_predicate():
    """If these ever drifted, the application would reason about capacity the database does not
    actually reserve -- and #84's displacement preview would go back to lying."""
    sql = D2_MIGRATION.read_text(encoding="utf-8")
    # Anchored on the DDL that creates the constraint, not on the first `WHERE (state IN (...))`
    # in the file -- the migration's header discusses the predicate in prose using an ellipsis, and
    # matching that instead would make this test pass against a comment.
    predicate = re.search(
        r"ADD CONSTRAINT dock_occupancy_dock_id_window_excl.*?WHERE \(state IN \(([^)]*)\)\)",
        sql,
        re.DOTALL,
    )
    assert predicate, "the exclusion constraint's predicate is no longer where this test looks"
    states = {s.strip().strip("'") for s in predicate.group(1).split(",")}
    assert states == set(holds.CAPACITY_CONSUMING_STATES)
    assert states == set(snapshot.CAPACITY_CONSUMING_STATES)


# =================================================================================================
# #86 -- the driver `/context` prefetch. The third driver-side read, found while #83 was landing.
#
# #83 fixed `get_current_appointment` and `get_appointment_request_status`, both tool-facing. This
# one is the payload behind `GET /api/v1/driver/context` *and* the block `run_assistant.py` pastes
# into every turn's system prompt. Leaving it blind meant the chat's opening context would say "no
# appointment" about a shipment the very next tool call reported as HELD -- the same driver, the
# same shipment, two answers inside one turn.
# =================================================================================================


def _snapshot_row_sets(appointment_status="CANCELLED", hold_rows=None):
    """The five result sets `load_driver_operational_snapshot` consumes, in issue order.

    Written as a list rather than a fixture so each test can say exactly how many `execute` calls
    it expects -- which is the whole point of the flag-off assertion below.
    """
    driver = [{"driver_id": "DRV1", "driver_name": "R", "phone": None, "licence_number": None,
               "home_base_city": "Jaipur", "driver_status": "ACTIVE"}]
    shipments = [{"shipment_id": "SHP1", "order_reference": "ORD1",
                  "destination_facility_id": "FAC-JAI-01", "current_status": "IN_TRANSIT",
                  "latest_eta_ts": None, "original_eta_ts": None, "priority_code": "NORMAL",
                  "updated_at": None}]
    appointment = (
        [{"appointment_id": "APT1", "shipment_id": "SHP1", "slot_id": "SLOT1",
          "appointment_status": appointment_status, "is_current": 1}]
        if appointment_status else []
    )
    facility = [{"facility_id": "FAC-JAI-01", "facility_name": "Jaipur DC"}]
    latest_eta = []
    row_sets = [driver, shipments, appointment, facility, latest_eta]
    if hold_rows is not None:
        row_sets.append(hold_rows)
    return row_sets


def _live_hold_row():
    """A row shaped like the one `live_hold_for_shipment`'s real SELECT returns.

    `expires_at` is relative to the **wall clock**, not this module's frozen `NOW`. That is not
    laziness: unlike `get_current_appointment`, the two context compositions take no injected
    clock and read `datetime.now(timezone.utc)` themselves (the shape `get_current_appointment`
    already uses at line 221), so a frozen expiry would make `expires_in_seconds` clamp to 0 and
    the countdown assertion below would pass vacuously against a hold that has already lapsed.
    """
    now = datetime.now(timezone.utc)
    return {
        "occupancy_id": 77, "dock_id": "DOCK-JAI-D1", "shipment_id": "SHP1", "state": "HELD",
        "expires_at": now + timedelta(seconds=90), "window_start": now, "window_end": now,
        "slot_id": "SLOT1", "facility_id": "FAC-JAI-01", "slot_start_ts": now,
        "slot_end_ts": now, "dock_code": "D1", "dock_type": "STANDARD",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "compose",
    [driver_reads.get_driver_operational_context, driver_reads.get_driver_context_payload],
    ids=["prefetch", "rest_context"],
)
async def test_driver_context_issues_no_extra_query_with_the_flag_off(flag_off, compose):
    """Flag-off costs exactly the five statements the snapshot always issued -- not six.

    The same safety property #83 established, applied to the third read: `live_hold_for_shipment`
    returns None without touching the session, so an unmigrated database never sees `o.state`
    named at all. A sixth `execute` here would mean the guard had been bypassed.
    """
    session = _session(*_snapshot_row_sets())
    payload = await compose(session, _driver_ctx())
    assert session.execute.await_count == 5
    assert payload["current_hold"] is None
    assert payload["promise_state"] == "CANCELLED"
    assert payload["promise_state_source"] == "appointments"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "compose",
    [driver_reads.get_driver_operational_context, driver_reads.get_driver_context_payload],
    ids=["prefetch", "rest_context"],
)
async def test_driver_context_surfaces_a_hold_with_the_flag_on(flag_on, compose):
    """#86 proper: a driver mid-hold whose last appointment was CANCELLED reads HELD, not CANCELLED.

    Deliberately *not* monkeypatched -- the real `live_hold_for_shipment` runs, so this also proves
    the sixth statement is genuinely issued and that it is the hold query.
    """
    session = _session(*_snapshot_row_sets(hold_rows=[_live_hold_row()]))
    payload = await compose(session, _driver_ctx())
    assert session.execute.await_count == 6
    hold_sql = _executed_sql(session, call=5)
    assert "public.dock_occupancy o" in hold_sql
    assert "o.state = 'HELD'" in hold_sql
    assert "o.expires_at > :now" in hold_sql  # section 0.8's lazy expiry check, never the sweeper
    assert payload["current_hold"]["hold_id"] == "77"
    assert payload["current_hold"]["expires_in_seconds"] > 0
    assert payload["promise_state"] == "HELD"
    assert payload["promise_state_source"] == "dock_occupancy_hold"
    # The appointment is still reported verbatim beside the hold rather than being overwritten by
    # it -- section 4's "held is not booked" survives into the payload, not just into
    # `promise_state`.
    assert payload["current_appointment"]["appointment_status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_the_two_driver_context_compositions_cannot_disagree(flag_on):
    """The asymmetry #86 is actually about, asserted rather than assumed.

    `GET /api/v1/driver/context` and the assistant prefetch are two compositions over one snapshot.
    Fixing only one would have left the surface and the model describing the same shipment
    differently, which is worse than both being blind.
    """
    # One row object, fed to both -- `_live_hold_row` is wall-clock-relative, so building it twice
    # would make the two payloads differ by microseconds for a reason that has nothing to do with
    # what this test is asserting.
    hold_row = _live_hold_row()
    prefetch = await driver_reads.get_driver_operational_context(
        _session(*_snapshot_row_sets(hold_rows=[hold_row])), _driver_ctx()
    )
    rest = await driver_reads.get_driver_context_payload(
        _session(*_snapshot_row_sets(hold_rows=[hold_row])), _driver_ctx()
    )
    for key in ("current_appointment", "current_hold", "promise_state", "promise_state_source"):
        assert prefetch[key] == rest[key], f"{key} differs between the two driver context reads"


@pytest.mark.asyncio
async def test_the_prefetch_puts_the_promise_ahead_of_the_shipment_lists(flag_on):
    """Ordering guard, and not a style one: `run_assistant.py` embeds `json.dumps(...)[:4000]`.

    Measured against the live database 2026-08-31 for the busiest real driver (13 shipments): the
    payload serialises to 7468 characters, and before this change `current_appointment` sat at
    offset 6616 -- already cut from the model's prompt, before #86 added a hold field after it. The
    two shipment *lists* are what make the payload long, so the single-value promise fields go
    first and the truncation lands on the repetitive tail instead of the load-bearing facts.

    Asserted on offsets rather than on `list(payload)` so it fails for the reason that matters --
    a field falling past the cut -- rather than merely because a key moved.
    """
    payload = await driver_reads.get_driver_operational_context(
        _session(*_snapshot_row_sets(hold_rows=[_live_hold_row()])), _driver_ctx()
    )
    blob = json.dumps(payload, default=str)
    for key in ("current_appointment", "current_hold", "promise_state"):
        assert blob.index(f'"{key}"') < blob.index('"shipments"'), f"{key} sits after the lists"
        assert blob.index(f'"{key}"') < 4000, f"{key} falls past run_assistant's 4000-char cut"


@pytest.mark.asyncio
async def test_driver_context_asks_for_no_hold_when_there_is_no_primary_shipment(flag_on):
    """A driver with no shipments has nothing to hold, so the hold read is skipped entirely.

    The same guard the snapshot's own three per-shipment reads already sit behind -- worth pinning
    because the flag-on cost of this issue is "one extra lookup when there is a shipment", and an
    unguarded call would silently make it "one extra lookup always", including for the empty case.
    """
    session = _session([{"driver_id": "DRV1", "driver_name": "R", "phone": None,
                         "licence_number": None, "home_base_city": "Jaipur",
                         "driver_status": "ACTIVE"}], [])
    payload = await driver_reads.get_driver_context_payload(session, _driver_ctx())
    assert session.execute.await_count == 2
    assert payload["current_hold"] is None
    assert payload["promise_state"] is None


# =================================================================================================
# #87 -- the carrier status filter. #85 made the read *derive* a hold; this is filtering by one.
# =================================================================================================


def _carrier_ctx():
    from app.core.execution_context import ExecutionContext, RoleName

    return ExecutionContext(
        request_id="r", auth_subject="s", user_id="USR900", email="c@x.com", full_name="C",
        role_id="ROL006", role_name=RoleName.CARRIER, carrier_id="CAR001",
    )


@pytest.mark.asyncio
async def test_carrier_status_filter_sql_is_unchanged_with_the_flag_off(flag_off):
    """The byte-identical property, applied to the filter as well as the projection.

    With holds off the predicate stays in the inner select against the raw column, on the same
    `:appointment_status` bind name it always used. Nothing forces that -- the legacy projection
    still aliases `promise_state`, so an outer predicate would compile and mean the same thing --
    but "unchanged" is a far cheaper property to keep true on an unmigrated database than
    "equivalent", and this is the statement that has to survive one.
    """
    session = _session([])
    await carrier_repo.list_fleet_shipments(
        session, "CAR001", promise_state="CONFIRMED", include_holds=False
    )
    sql = _executed_sql(session)
    assert "AND appt.appointment_status = :appointment_status" in sql
    assert "t.promise_state" not in sql
    assert "dock_occupancy" not in sql
    assert session.execute.await_args.args[1]["appointment_status"] == "CONFIRMED"

    exception_only = _session([])
    await carrier_repo.list_fleet_shipments(
        exception_only, "CAR001", only_with_open_exception=True, include_holds=False
    )
    # The exact outer clause that shipped, not a reassembled equivalent of it.
    assert "WHERE t.has_open_exception" in _executed_sql(exception_only)


@pytest.mark.asyncio
async def test_carrier_status_filter_moves_to_the_computed_state_with_the_flag_on(flag_on):
    """#87: `appt.appointment_status` structurally cannot express HELD, so the filter leaves it.

    A hold is a `dock_occupancy` row with no appointment at all (section 4), which is exactly why
    filtering the raw column could only ever return an empty list for HELD. The predicate moves to
    the outer select, where `promise_state` is the value #85's CASE actually computed.
    """
    session = _session([])
    await carrier_repo.list_fleet_shipments(
        session, "CAR001", promise_state="HELD", include_holds=True
    )
    sql = _executed_sql(session)
    assert "WHERE t.promise_state = :promise_state" in sql
    assert "AND appt.appointment_status = :appointment_status" not in sql
    assert "public.dock_occupancy o" in sql
    # M15 still holds: the hold is joined inside the already-scoped statement, and the scope
    # predicate is not something the new filter may displace.
    assert ":carrier_id" in sql
    assert "WHERE s.carrier_id = :carrier_id" in sql
    params = session.execute.await_args.args[1]
    assert params["promise_state"] == "HELD"
    assert "appointment_status" not in params


@pytest.mark.asyncio
async def test_carrier_held_and_exception_filters_compose_rather_than_replace(flag_on):
    """Both filters are membership-only (Flow 2), so combining them must AND, not overwrite."""
    session = _session([])
    await carrier_repo.list_fleet_shipments(
        session, "CAR001", promise_state="HELD", only_with_open_exception=True, include_holds=True
    )
    assert (
        "WHERE t.promise_state = :promise_state AND t.has_open_exception"
        in _executed_sql(session)
    )


@pytest.mark.asyncio
async def test_carrier_unfiltered_read_has_no_outer_clause_at_all(flag_off):
    """No filter means no outer WHERE, exactly as before -- an empty clause is not the same text."""
    session = _session([])
    await carrier_repo.list_fleet_shipments(session, "CAR001", include_holds=False)
    sql = _executed_sql(session)
    assert "WHERE t." not in sql


@pytest.mark.asyncio
async def test_carrier_service_refuses_held_with_the_flag_off(flag_off, monkeypatch):
    """Refused with a reason that names the flag, not answered with a misleading empty list.

    "You have no held shipments" and "this system cannot currently tell you about holds" are
    different statements, and only the second one is true while the flag is off.
    """
    listed = AsyncMock(return_value=[])
    monkeypatch.setattr(carrier_repo, "list_fleet_shipments", listed)
    with pytest.raises(AppError) as exc:
        await carrier_reads.list_fleet_shipments(AsyncMock(), _carrier_ctx(), "HELD")
    assert exc.value.status_code == 400
    assert exc.value.code == "FILTER_UNSUPPORTED"
    assert "TWO_PHASE_HOLD_ENABLED" in exc.value.detail
    listed.assert_not_awaited()  # refused before any query, not after an empty one


@pytest.mark.asyncio
async def test_carrier_service_answers_held_with_the_flag_on(flag_on, monkeypatch):
    """The close condition for #87: HELD reaches the repository as a promise-state filter."""
    listed = AsyncMock(return_value=[{"shipment_id": "SHP1", "promise_state": "HELD"}])
    monkeypatch.setattr(carrier_repo, "list_fleet_shipments", listed)
    payload = await carrier_reads.list_fleet_shipments(AsyncMock(), _carrier_ctx(), "held")
    assert listed.await_args.kwargs["promise_state"] == "HELD"
    assert listed.await_args.kwargs["include_holds"] is True
    assert payload["status_filter"] == "HELD"
    assert payload["items"][0]["promise_state"] == "HELD"


@pytest.mark.asyncio
async def test_carrier_shown_stays_refused_even_with_the_flag_on(flag_on):
    """SHOWN is refused on purpose and the flag does not change that (issue #87's third condition).

    Sections 0.8/4 define SHOWN as what `find_feasible_slots` returned to one caller: it reserves
    nothing and writes no row anywhere in the product, so there is no table to select from.
    Inventing a mapping -- "no appointment and no hold", say -- would answer with every shipment
    that has never been offered anything, which is not what a carrier clicking "Shown" is asking.
    Refusing is the honest answer until the design gives the state a representation.
    """
    with pytest.raises(AppError) as exc:
        await carrier_reads.list_fleet_shipments(AsyncMock(), _carrier_ctx(), "SHOWN")
    assert exc.value.code == "FILTER_UNSUPPORTED"
    assert "no persisted counterpart" in exc.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", ["on", "off"])
async def test_carrier_unknown_filter_message_matches_what_the_flag_allows(flag, request):
    """The "supported filters" list must not promise HELD while HELD is being refused.

    A message that enumerates a value the very next request would 400 on is worse than no message.
    """
    request.getfixturevalue("flag_on" if flag == "on" else "flag_off")
    with pytest.raises(AppError) as exc:
        await carrier_reads.list_fleet_shipments(AsyncMock(), _carrier_ctx(), "NOT_A_STATE")
    assert exc.value.code == "FILTER_UNSUPPORTED"
    assert ("HELD" in exc.value.detail) is (flag == "on")
    assert "SHOWN" not in exc.value.detail
