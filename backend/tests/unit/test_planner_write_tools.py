"""E5.3 planner write tools -- issues #61, #62, #63, #65, #66.

`SOLUTION_DESIGN.md` section 7.5.1 / section 7.3 / D6 · `FR-PLN-001/002/003/006` ·
`UI-UX/03-planner-dock-board/flows-and-states.md` Flows 1, 2, 3, 6.

Split by issue below. The one test that is worth reading before the others is
`test_two_concurrent_confirms_produce_one_winner_and_one_already_actioned` -- section 9.2 #3 calls
this "the nastiest race in the design", and the ordering it asserts (lock, then status, then
displacement, then staleness) is the whole of the resolution.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.core.settings import get_settings
from app.scheduling import allocation, snapshot
from app.scheduling.allocation import (
    BulkConfirmCommand,
    ConfirmAppointmentCommand,
    CounterOfferCommand,
    HoldForInformationCommand,
    RejectAppointmentCommand,
    bulk_confirm,
    confirm_appointment,
    counter_offer,
    evaluate_safe_batch_predicates,
    hold_for_information,
    reject_appointment,
)
from app.services import planner_service

IST = ZoneInfo("Asia/Kolkata")


def _ops_ctx(facility_id: str = "FAC-JAI-01") -> ExecutionContext:
    return ExecutionContext(
        request_id="req",
        auth_subject="auth-planner",
        user_id="USR101",
        email="priya.mehta@setuhaul.com",
        full_name="Priya Mehta",
        role_id="ROL002",
        role_name=RoleName.WAREHOUSE_PLANNER,
        facility_id=facility_id,
    )


def _shipment(facility_id: str = "FAC-JAI-01") -> dict:
    return {
        "shipment_id": "SHP1002",
        "driver_id": "DRV002",
        "destination_facility_id": facility_id,
    }


def _snapshot(
    *,
    appointment_id: str = "APT021",
    conflicts: list[dict] | None = None,
    dock_blocks: list[dict] | None = None,
    status: str = "PENDING_CONFIRMATION",
) -> dict:
    interval_start = datetime(2026, 8, 16, 10, 0, tzinfo=IST)
    interval_end = interval_start + timedelta(minutes=60)
    conflicts = conflicts or []
    return {
        "appointment_id": appointment_id,
        "shipment_id": "SHP1002",
        "slot_id": "SLT021",
        "appointment_status": status,
        "is_current": 1,
        "facility_id": "FAC-JAI-01",
        "dock_id": "DOCK-JAI-D1",
        "interval_start": interval_start,
        "interval_end": interval_end,
        "interval_source": snapshot.INTERVAL_SOURCE_OCCUPANCY,
        "conflicts": conflicts,
        "dock_blocks": dock_blocks or [],
        "snapshot_hash": snapshot.planner_snapshot_hash(
            appointment_id=appointment_id,
            appointment_status=status,
            is_current=1,
            dock_id="DOCK-JAI-D1",
            interval_start=interval_start,
            interval_end=interval_end,
            interval_source=snapshot.INTERVAL_SOURCE_OCCUPANCY,
            conflict_ids=[str(c["appointment_id"]) for c in conflicts],
        ),
    }


# =================================================================================================
# Issue #61 -- the snapshot_hash contract
# =================================================================================================


_HASH_INPUTS = {
    "appointment_id": "APT021",
    "appointment_status": "PENDING_CONFIRMATION",
    "is_current": 1,
    "dock_id": "DOCK-JAI-D1",
    "interval_start": datetime(2026, 8, 16, 4, 30, tzinfo=timezone.utc),
    "interval_end": datetime(2026, 8, 16, 5, 30, tzinfo=timezone.utc),
    "interval_source": "dock_occupancy",
    "conflict_ids": [],
}


def test_snapshot_hash_matches_the_planner_queue_producer_byte_for_byte():
    """The drift guard the whole of issue #61 rests on -- now enforced by identity, not equality.

    `get_planner_queue` (#60) *produces* the token in `planner_service`; the write paths
    *recompute and compare* it in `scheduling/snapshot`. Two implementations of one digest is
    exactly the shape that silently diverges -- a deploy where they disagree would make every
    confirm return `SNAPSHOT_STALE` with no way to distinguish a real drift from a skew.

    Issue #88 folded the duplicate in: `planner_service._snapshot_hash` is now an import alias for
    `snapshot.planner_snapshot_hash`, so the `is` below is the stronger assertion -- equality could
    still pass against two copies that happen to agree today, while identity fails the moment
    anyone re-introduces a second implementation. The value equality is kept underneath it so the
    test still says what the contract *is*, not only where it lives.
    """
    assert planner_service._snapshot_hash is snapshot.planner_snapshot_hash, (
        "planner_service grew its own copy of the digest again -- issue #61's duplication, which "
        "#88 removed. Import `snapshot.planner_snapshot_hash`; do not reimplement it."
    )
    assert snapshot.planner_snapshot_hash(**_HASH_INPUTS) == planner_service._snapshot_hash(
        **_HASH_INPUTS
    )


def test_snapshot_hash_is_independent_of_how_the_driver_returned_the_timezone():
    """The same instant in `+05:30` and in UTC must hash identically.

    Postgres renders a timestamptz in the *session's* TimeZone setting, so without the UTC pin in
    `_build_snapshot` two connections would produce different tokens for an unchanged row.
    """
    utc_row = _snapshot_sql_row()
    ist_row = {
        **utc_row,
        "interval_start": utc_row["interval_start"].astimezone(IST),
        "interval_end": utc_row["interval_end"].astimezone(IST),
    }

    assert (
        snapshot._build_snapshot(utc_row)["snapshot_hash"]
        == snapshot._build_snapshot(ist_row)["snapshot_hash"]
    )


def _snapshot_sql_row(*, interval_conflicts: str = "[]", dock_blocks: str = "[]") -> dict:
    return {
        "appointment_id": "APT021",
        "shipment_id": "SHP1002",
        "slot_id": "SLT021",
        "appointment_status": "PENDING_CONFIRMATION",
        "is_current": 1,
        "facility_id": "FAC-JAI-01",
        "dock_id": "DOCK-JAI-D1",
        "occupancy_start": datetime(2026, 8, 16, 4, 30, tzinfo=timezone.utc),
        "interval_start": datetime(2026, 8, 16, 4, 30, tzinfo=timezone.utc),
        "interval_end": datetime(2026, 8, 16, 5, 30, tzinfo=timezone.utc),
        "interval_conflicts_json": interval_conflicts,
        "dock_block_conflicts_json": dock_blocks,
    }


def test_snapshot_hash_changes_when_a_third_party_claim_appears():
    clean = snapshot._build_snapshot(_snapshot_sql_row())
    contested = snapshot._build_snapshot(
        _snapshot_sql_row(
            interval_conflicts=json.dumps(
                [{"conflict_type": "INTERVAL_CONFLICT", "appointment_id": "APT-OTHER"}]
            )
        )
    )

    assert clean["snapshot_hash"] != contested["snapshot_hash"]


def test_snapshot_hash_ignores_a_dock_block_but_displacement_does_not():
    """The asymmetry is deliberate and is stated in `snapshot.displacement_conflicts`.

    The hash must stay byte-identical to the producer's, and the producer's `conflict_ids` carry
    only the overlapping-claim half. The dock-block leg therefore lives in the *displacement*
    check, which is a superset -- a confirm can be refused for a dock the planner took offline
    since render, which the queue row does not currently show.
    """
    blocked = _snapshot_sql_row(
        dock_blocks=json.dumps(
            [{"conflict_type": "DOCK_BLOCKED", "dock_event_id": "DSE-9", "event_type": "MANUAL_BLOCK"}]
        )
    )
    built = snapshot._build_snapshot(blocked)

    assert built["snapshot_hash"] == snapshot._build_snapshot(_snapshot_sql_row())["snapshot_hash"]
    assert [c["conflict_type"] for c in snapshot.displacement_conflicts(built)] == ["DOCK_BLOCKED"]


def test_batch_snapshot_hash_ignores_selection_order_but_not_membership():
    a = snapshot.batch_snapshot_hash({"APT1": "h1", "APT2": "h2"})
    b = snapshot.batch_snapshot_hash({"APT2": "h2", "APT1": "h1"})
    fewer = snapshot.batch_snapshot_hash({"APT1": "h1"})
    changed = snapshot.batch_snapshot_hash({"APT1": "h1", "APT2": "h2-moved"})

    assert a == b
    assert a != fewer
    assert a != changed


# =================================================================================================
# Issue #62 -- confirm_request's refusal taxonomy
# =================================================================================================


def _patch_confirm_context(monkeypatch, *, appointment: dict) -> AsyncMock:
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(allocation, "_shipment_for_status", AsyncMock(return_value=_shipment()))
    monkeypatch.setattr(allocation, "_locked_appointment", AsyncMock(return_value=appointment))
    monkeypatch.setattr(allocation, "_reread_appointment", AsyncMock(return_value={}))
    store = AsyncMock()
    monkeypatch.setattr(allocation, "store_idempotency", store)
    return store


_PENDING = {
    "appointment_id": "APT021",
    "shipment_id": "SHP1002",
    "slot_id": "SLT021",
    "appointment_status": "PENDING_CONFIRMATION",
    "is_current": 1,
}


@pytest.mark.asyncio
async def test_confirm_refuses_a_stale_snapshot_and_names_the_current_state(monkeypatch):
    """`flows-and-states.md` Flow 1 step 5 -- "never a silent retry with old context"."""
    session = AsyncMock()
    _patch_confirm_context(monkeypatch, appointment=dict(_PENDING))
    current = _snapshot()
    monkeypatch.setattr(
        allocation, "load_appointment_snapshot", AsyncMock(return_value=current)
    )

    with pytest.raises(AppError) as exc:
        await confirm_appointment(
            session,
            _ops_ctx(),
            shipment_id="SHP1002",
            command=ConfirmAppointmentCommand(
                appointment_id="APT021", snapshot_hash="what-the-planner-saw-a-minute-ago"
            ),
            idempotency_key="k",
        )

    assert exc.value.code == "SNAPSHOT_STALE"
    assert exc.value.status_code == 409
    drift = json.loads(exc.value.detail)
    assert drift["expected_snapshot_hash"] == "what-the-planner-saw-a-minute-ago"
    assert drift["current_snapshot_hash"] == current["snapshot_hash"]
    # The planner is told what the row is *now*, which is what makes a re-read possible.
    assert drift["current"]["dock_id"] == "DOCK-JAI-D1"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_refuses_displacement_before_it_ever_looks_at_staleness(monkeypatch):
    """section 7.3: "Confirming must never quietly hurt a third party."

    A new conflict changes the digest too, so if staleness were checked first
    `DISPLACEMENT_DETECTED` could never fire and the single most important field on the queue row
    would degrade into a generic "something moved". This asserts the ordering, not just the code:
    the supplied hash here is *correct* for the pre-conflict row and still loses to displacement.
    """
    session = AsyncMock()
    _patch_confirm_context(monkeypatch, appointment=dict(_PENDING))
    contested = _snapshot(
        conflicts=[{"conflict_type": "INTERVAL_CONFLICT", "appointment_id": "APT-OTHER"}]
    )
    monkeypatch.setattr(
        allocation, "load_appointment_snapshot", AsyncMock(return_value=contested)
    )

    with pytest.raises(AppError) as exc:
        await confirm_appointment(
            session,
            _ops_ctx(),
            shipment_id="SHP1002",
            command=ConfirmAppointmentCommand(
                appointment_id="APT021", snapshot_hash=contested["snapshot_hash"]
            ),
            idempotency_key="k",
        )

    assert exc.value.code == "DISPLACEMENT_DETECTED"
    assert "APT-OTHER" in exc.value.message
    assert json.loads(exc.value.detail)["conflicts"][0]["appointment_id"] == "APT-OTHER"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_already_actioned_outranks_both_new_refusals(monkeypatch):
    """A row somebody already actioned is decided, not stale (section 7.5.1's race resolution)."""
    session = AsyncMock()
    _patch_confirm_context(
        monkeypatch,
        appointment={**_PENDING, "appointment_status": "EXPIRED", "cancellation_reason": "D9"},
    )
    guard = AsyncMock()
    monkeypatch.setattr(allocation, "_snapshot_guard", guard)

    with pytest.raises(AppError) as exc:
        await confirm_appointment(
            session,
            _ops_ctx(),
            shipment_id="SHP1002",
            command=ConfirmAppointmentCommand(appointment_id="APT021", snapshot_hash="anything"),
            idempotency_key="k",
        )

    assert exc.value.code == "ALREADY_ACTIONED"
    guard.assert_not_awaited()


@pytest.mark.asyncio
async def test_snapshot_guard_runs_after_the_row_lock_never_before(monkeypatch):
    """Reading the snapshot before the `FOR UPDATE` would be a race of its own.

    Under READ COMMITTED the lock is what makes the values read the committed ones the write is
    about to act on (PostgreSQL "Transaction Isolation" 13.2.1).
    """
    session = AsyncMock()
    order: list[str] = []

    async def _locked(*_args, **_kwargs):
        order.append("lock")
        return dict(_PENDING)

    async def _load(*_args, **_kwargs):
        order.append("snapshot")
        return _snapshot()

    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(allocation, "_shipment_for_status", AsyncMock(return_value=_shipment()))
    monkeypatch.setattr(allocation, "_locked_appointment", _locked)
    monkeypatch.setattr(allocation, "load_appointment_snapshot", _load)
    monkeypatch.setattr(allocation, "_reread_appointment", AsyncMock(return_value={}))
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())

    await confirm_appointment(
        session,
        _ops_ctx(),
        shipment_id="SHP1002",
        command=ConfirmAppointmentCommand(
            appointment_id="APT021", snapshot_hash=_snapshot()["snapshot_hash"]
        ),
        idempotency_key="k",
    )

    assert order == ["lock", "snapshot"]


@pytest.mark.asyncio
async def test_confirm_without_a_warehouse_ref_preserves_the_stored_one(monkeypatch):
    """Issue #62's decision: the tool owes the field a default, and the default invents nothing.

    `AGENTS.md` forbids inventing operational data, so an omitted argument leaves whatever a
    warehouse integration already wrote -- hence `COALESCE`, not an overwrite with NULL and not a
    synthesised reference that would read as a real acknowledgement.
    """
    session = AsyncMock()
    _patch_confirm_context(monkeypatch, appointment=dict(_PENDING))
    monkeypatch.setattr(
        allocation, "load_appointment_snapshot", AsyncMock(return_value=_snapshot())
    )

    await confirm_appointment(
        session,
        _ops_ctx(),
        shipment_id="SHP1002",
        command=ConfirmAppointmentCommand(
            appointment_id="APT021", snapshot_hash=_snapshot()["snapshot_hash"]
        ),
        idempotency_key="k",
    )

    sql, params = _statement(session, "UPDATE public.appointments")
    assert "COALESCE(" in sql
    assert "warehouse_confirmation_ref" in sql
    assert params["warehouse_confirmation_ref"] is None


def _statement(session, needle: str) -> tuple[str, dict]:
    for call in session.execute.await_args_list:
        if len(call.args) > 1 and needle in str(call.args[0]):
            return str(call.args[0]), call.args[1]
    raise AssertionError(f"no statement containing {needle!r}")


@pytest.mark.asyncio
async def test_two_concurrent_confirms_produce_one_winner_and_one_already_actioned(monkeypatch):
    """section 9.2 #3, the nastiest race in the design, as a real contention test.

    The fake `_locked_appointment` takes an `asyncio.Lock` before returning the row and returns the
    *current* state, which is exactly what PostgreSQL guarantees for `SELECT ... FOR UPDATE` under
    READ COMMITTED: the loser is handed the updated version of the row. So the assertion is not
    "the code has an if-statement" -- it is that two genuinely interleaved callers cannot both
    write, and the loser is told which transition won.
    """
    lock = asyncio.Lock()
    row = dict(_PENDING)

    async def _locked(*_args, **_kwargs):
        await lock.acquire()
        return dict(row)

    async def _apply(*_args, **kwargs):
        # Models the committed UPDATE the winner performs.
        row["appointment_status"] = "CONFIRMED"

    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(allocation, "_shipment_for_status", AsyncMock(return_value=_shipment()))
    monkeypatch.setattr(allocation, "_locked_appointment", _locked)
    monkeypatch.setattr(allocation, "_apply_confirmation", _apply)
    monkeypatch.setattr(
        allocation, "load_appointment_snapshot", AsyncMock(return_value=_snapshot())
    )
    monkeypatch.setattr(allocation, "_reread_appointment", AsyncMock(return_value={}))
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())

    async def _attempt(key: str):
        try:
            return await confirm_appointment(
                AsyncMock(),
                _ops_ctx(),
                shipment_id="SHP1002",
                command=ConfirmAppointmentCommand(
                    appointment_id="APT021", snapshot_hash=_snapshot()["snapshot_hash"]
                ),
                idempotency_key=key,
            )
        finally:
            # The transaction ends either way -- commit or refusal -- and the row lock goes with it.
            if lock.locked():
                lock.release()

    results = await asyncio.gather(
        _attempt("planner-a"), _attempt("planner-b"), return_exceptions=True
    )

    winners = [r for r in results if not isinstance(r, BaseException)]
    losers = [r for r in results if isinstance(r, AppError)]
    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0].code == "ALREADY_ACTIONED"
    # section 7.5.1: the loser gets ALREADY_ACTIONED *with the winning transition named*.
    assert "CONFIRMED" in losers[0].message


# =================================================================================================
# Issue #63 -- counter_offer
# =================================================================================================


def _patch_counter_offer_context(monkeypatch, *, slot: dict | None, eligible: bool = True):
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(allocation, "_shipment_for_status", AsyncMock(return_value=_shipment()))
    monkeypatch.setattr(allocation, "_locked_appointment", AsyncMock(return_value=dict(_PENDING)))
    monkeypatch.setattr(allocation, "_snapshot_guard", AsyncMock(return_value=_snapshot()))
    monkeypatch.setattr(allocation, "_slot_at_dock_and_time", AsyncMock(return_value=slot))
    monkeypatch.setattr(
        allocation,
        "explain_slot_eligibility",
        AsyncMock(
            return_value=MagicMock(
                eligible=eligible,
                failure_code=None if eligible else "FACILITY_RULE_VIOLATION",
                message=None if eligible else "RULE005 forbids a new unload after 21:00.",
                checked_constraints=["RULE005"],
                explanation=["fits"],
            )
        ),
    )
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=True))
    monkeypatch.setattr(
        allocation,
        "_claim_dock_occupancy",
        AsyncMock(return_value={"dock_id": "DOCK-JAI-D2", "window": "[)"}),
    )
    monkeypatch.setattr(allocation, "_reread_appointment", AsyncMock(return_value={}))
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())
    monkeypatch.setattr(
        allocation, "load_appointment_snapshot", AsyncMock(return_value=_snapshot())
    )


_NEW_SLOT = {
    "slot_id": "SLT-NEW",
    "facility_id": "FAC-JAI-01",
    "dock_id": "DOCK-JAI-D2",
    "slot_start_ts": datetime(2026, 8, 16, 14, 0, tzinfo=IST),
    "slot_end_ts": datetime(2026, 8, 16, 15, 0, tzinfo=IST),
    "slot_status": "OPEN",
    "dock_code": "D2",
    "dock_type": "STANDARD",
    "dock_status": "ACTIVE",
}


def _counter_offer_command(**overrides) -> CounterOfferCommand:
    return CounterOfferCommand(
        **{
            "appointment_id": "APT021",
            "dock_id": "DOCK-JAI-D2",
            "start_ts": datetime(2026, 8, 16, 14, 0, tzinfo=IST),
            "reason_code": "CAPACITY",
            "snapshot_hash": _snapshot()["snapshot_hash"],
            **overrides,
        }
    )


@pytest.mark.asyncio
async def test_counter_offer_refuses_an_unsupported_reason_code_naming_the_set(monkeypatch):
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(allocation, "lookup_idempotency", lookup)

    with pytest.raises(AppError) as exc:
        await counter_offer(
            AsyncMock(),
            _ops_ctx(),
            shipment_id="SHP1002",
            command=_counter_offer_command(reason_code="because the dock looked busy"),
            idempotency_key="k",
        )

    assert exc.value.code == "INVALID_REASON_CODE"
    assert exc.value.status_code == 422
    assert "CAPACITY" in exc.value.detail
    # Refused before anything is read: a bad code must not burn the caller's Idempotency-Key.
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_counter_offer_refuses_an_interval_with_no_slot_behind_it(monkeypatch):
    session = AsyncMock()
    _patch_counter_offer_context(monkeypatch, slot=None)

    with pytest.raises(AppError) as exc:
        await counter_offer(
            session, _ops_ctx(), shipment_id="SHP1002",
            command=_counter_offer_command(), idempotency_key="k",
        )

    assert exc.value.code == "INTERVAL_UNAVAILABLE"
    assert json.loads(exc.value.detail)["failure_code"] == "SLOT_NOT_FOUND"
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_counter_offer_will_not_hand_out_a_stage_one_infeasible_interval(monkeypatch):
    """section 7.5.1: "a planner may not hand out an infeasible slot by hand"."""
    session = AsyncMock()
    _patch_counter_offer_context(monkeypatch, slot=dict(_NEW_SLOT), eligible=False)

    with pytest.raises(AppError) as exc:
        await counter_offer(
            session, _ops_ctx(), shipment_id="SHP1002",
            command=_counter_offer_command(), idempotency_key="k",
        )

    assert exc.value.code == "INTERVAL_UNAVAILABLE"
    assert json.loads(exc.value.detail)["failure_code"] == "FACILITY_RULE_VIOLATION"
    allocation._release_dock_occupancy.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_counter_offer_moves_the_claim_release_before_reclaim(monkeypatch):
    """Moving 11:00 to 11:30 on the same dock overlaps itself, so the old claim must go first --
    otherwise D1's exclusion constraint rejects the planner's own counter-offer."""
    session = AsyncMock()
    order: list[str] = []
    _patch_counter_offer_context(monkeypatch, slot=dict(_NEW_SLOT))

    async def _release(*_a, **_k):
        order.append("release")
        return True

    async def _claim(*_a, **_k):
        order.append("claim")
        return {"dock_id": "DOCK-JAI-D2", "window": "[)"}

    monkeypatch.setattr(allocation, "_release_dock_occupancy", _release)
    monkeypatch.setattr(allocation, "_claim_dock_occupancy", _claim)

    result = await counter_offer(
        session, _ops_ctx(), shipment_id="SHP1002",
        command=_counter_offer_command(), idempotency_key="k",
    )

    assert result.code == "COUNTER_OFFERED"
    assert order == ["release", "claim"]
    assert result.offered_options[0]["slot_id"] == "SLT-NEW"
    _sql, params = _statement(session, "SET slot_id = :slot_id")
    assert params["slot_id"] == "SLT-NEW"
    # The D9 clock is deliberately untouched -- `booked_at` is the TTL anchor.
    assert "booked_at" not in params
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_counter_offer_audit_row_carries_the_counter_offered_discriminator(monkeypatch):
    """`audit_logs.action_type` has no COUNTER_OFFER value, so the discriminator is in the payload.

    Without it, section 7.3's "reject-with-counter-offer vs reject-flat" metric and Flow 2's
    "awaiting driver" micro-state have nothing to key on.
    """
    session = AsyncMock()
    _patch_counter_offer_context(monkeypatch, slot=dict(_NEW_SLOT))

    await counter_offer(
        session, _ops_ctx(), shipment_id="SHP1002",
        command=_counter_offer_command(note="offered D2 instead"), idempotency_key="k",
    )

    _sql, params = _statement(session, "INSERT INTO public.audit_logs")
    payload = json.loads(params["new_value_json"])
    assert params["action_type"] == allocation.AUDIT_ACTION_COUNTER_OFFER
    assert payload["transition"] == "COUNTER_OFFERED"
    assert payload["reason_code"] == "CAPACITY"
    assert payload["slot_id"] == "SLT-NEW"
    # audit_logs.created_at was never converted by E1.1 and must stay a string bind.
    assert isinstance(params["created_at"], str)


@pytest.mark.asyncio
async def test_counter_offer_translates_the_exclusion_violation_to_interval_unavailable(monkeypatch):
    """The race is decided by Postgres, not by the pre-check above it."""
    session = AsyncMock()
    _patch_counter_offer_context(monkeypatch, slot=dict(_NEW_SLOT))
    monkeypatch.setattr(
        allocation,
        "_claim_dock_occupancy",
        AsyncMock(
            side_effect=IntegrityError(
                "INSERT INTO public.dock_occupancy",
                {},
                Exception(
                    'conflicting key value violates exclusion constraint '
                    '"dock_occupancy_dock_id_window_excl"'
                ),
            )
        ),
    )

    with pytest.raises(AppError) as exc:
        await counter_offer(
            session, _ops_ctx(), shipment_id="SHP1002",
            command=_counter_offer_command(), idempotency_key="k",
        )

    assert exc.value.code == "INTERVAL_UNAVAILABLE"
    assert "dock_occupancy_dock_id_window_excl" in exc.value.detail
    session.rollback.assert_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_counter_offer_refuses_a_naive_start_ts_rather_than_guessing_a_zone(monkeypatch):
    session = AsyncMock()
    _patch_counter_offer_context(monkeypatch, slot=dict(_NEW_SLOT))

    with pytest.raises(AppError) as exc:
        await counter_offer(
            session, _ops_ctx(), shipment_id="SHP1002",
            command=_counter_offer_command(start_ts=datetime(2026, 8, 16, 14, 0)),
            idempotency_key="k",
        )

    assert json.loads(exc.value.detail)["failure_code"] == "START_TS_NOT_TIMEZONE_AWARE"


# =================================================================================================
# Issue #65 -- bulk_confirm and the five safe-batch predicates
# =================================================================================================


def _predicate_inputs(**overrides) -> dict:
    return {
        "appointment_id": "APT021",
        "shipment_id": "SHP1002",
        "appointment_status": "PENDING_CONFIRMATION",
        "is_current": 1,
        "destination_facility_id": "FAC-JAI-01",
        "required_dock_type": "STANDARD",
        "expected_unload_min": 45,
        "dock_type": "STANDARD",
        "facility_id": "FAC-JAI-01",
        "timezone": "Asia/Kolkata",
        "open_time": "06:00:00",
        "close_time": "22:00:00",
        "eta_confidence": "HIGH",
        "open_escalation_count": 0,
        "last_new_start_rules_json": json.dumps(
            [
                {
                    "rule_id": "RULE005",
                    "rule_type": "LAST_NEW_START_TIME",
                    "rule_value": "21:00:00",
                    "effective_from": "2026-01-01",
                    "effective_to": None,
                }
            ]
        ),
        **overrides,
    }


def test_safe_batch_passes_a_row_that_satisfies_all_five():
    assert evaluate_safe_batch_predicates(inputs=_predicate_inputs(), snapshot=_snapshot()) == []


def test_safe_batch_fails_on_displacement():
    contested = _snapshot(
        conflicts=[{"conflict_type": "INTERVAL_CONFLICT", "appointment_id": "APT-OTHER"}]
    )
    assert evaluate_safe_batch_predicates(inputs=_predicate_inputs(), snapshot=contested) == [
        allocation.PREDICATE_ZERO_DISPLACEMENT
    ]


def test_safe_batch_fails_on_a_dock_block_even_though_the_hash_is_unchanged():
    blocked = _snapshot(dock_blocks=[{"conflict_type": "DOCK_BLOCKED", "dock_event_id": "DSE-9"}])
    assert allocation.PREDICATE_ZERO_DISPLACEMENT in evaluate_safe_batch_predicates(
        inputs=_predicate_inputs(), snapshot=blocked
    )


@pytest.mark.parametrize("required,actual", [("ANY", "STANDARD"), ("STANDARD", "HEAVY")])
def test_safe_batch_requires_an_exact_dock_type_match_not_mere_compatibility(required, actual):
    """section 7.3: "exact dock-type match (no `P_dock` penalty applied)".

    `required_dock_type = ANY` is *compatible* with every dock and exact with none, so it never
    qualifies for the safe batch -- Stage 2 would apply `compatible_but_not_exact_dock_penalty` to
    it, which is precisely the signal this predicate reads.
    """
    failed = evaluate_safe_batch_predicates(
        inputs=_predicate_inputs(required_dock_type=required, dock_type=actual),
        snapshot=_snapshot(),
    )
    assert allocation.PREDICATE_EXACT_DOCK_MATCH in failed


@pytest.mark.parametrize("confidence", ["LOW", None, ""])
def test_safe_batch_fails_low_or_absent_eta_confidence(confidence):
    """Absent confidence is not high confidence -- failing open here would put SHP1013 in the batch."""
    failed = evaluate_safe_batch_predicates(
        inputs=_predicate_inputs(eta_confidence=confidence), snapshot=_snapshot()
    )
    assert allocation.PREDICATE_ETA_CONFIDENCE_NOT_LOW in failed


def test_safe_batch_fails_a_start_after_last_new_start_time():
    late = _snapshot()
    late["interval_start"] = datetime(2026, 8, 16, 21, 30, tzinfo=IST)
    late["interval_end"] = datetime(2026, 8, 16, 21, 55, tzinfo=IST)
    failed = evaluate_safe_batch_predicates(inputs=_predicate_inputs(), snapshot=late)

    assert allocation.PREDICATE_INSIDE_OPERATING_WINDOW in failed


def test_safe_batch_fails_a_start_outside_operating_hours():
    early = _snapshot()
    early["interval_start"] = datetime(2026, 8, 16, 4, 0, tzinfo=IST)
    early["interval_end"] = datetime(2026, 8, 16, 5, 0, tzinfo=IST)
    failed = evaluate_safe_batch_predicates(inputs=_predicate_inputs(), snapshot=early)

    assert allocation.PREDICATE_INSIDE_OPERATING_WINDOW in failed


def test_safe_batch_fails_a_shipment_with_an_open_escalation():
    failed = evaluate_safe_batch_predicates(
        inputs=_predicate_inputs(open_escalation_count=1), snapshot=_snapshot()
    )
    assert allocation.PREDICATE_NO_OPEN_ESCALATION in failed


def _bulk_session(rows: dict[str, dict]) -> AsyncMock:
    """A session whose per-id locking SELECT returns the row for the bound appointment_id."""
    session = AsyncMock()

    async def _execute(statement, params=None):
        result = MagicMock()
        if params and "FOR UPDATE" in str(statement):
            result.mappings.return_value.first.return_value = rows.get(params["appointment_id"])
        else:
            result.mappings.return_value.first.return_value = None
        return result

    session.execute.side_effect = _execute
    return session


@pytest.mark.asyncio
async def test_bulk_confirm_locks_rows_in_sorted_id_order(monkeypatch):
    """Deadlock avoidance, not tidiness: two coordinators clearing an overlapping spike must not be
    able to take the same rows in opposite orders."""
    ids = ["APT-C", "APT-A", "APT-B"]
    rows = {i: {**_PENDING, "appointment_id": i} for i in ids}
    session = _bulk_session(rows)
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(allocation, "_safe_batch_inputs", AsyncMock(return_value={}))
    monkeypatch.setattr(allocation, "load_appointment_snapshots", AsyncMock(return_value={}))
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())

    await bulk_confirm(
        session,
        _ops_ctx(),
        command=BulkConfirmCommand(appointment_ids=ids, snapshot_hash="h"),
        idempotency_key="k",
    )

    locked_order = [
        call.args[1]["appointment_id"]
        for call in session.execute.await_args_list
        if len(call.args) > 1 and "FOR UPDATE" in str(call.args[0])
    ]
    assert locked_order == ["APT-A", "APT-B", "APT-C"]


@pytest.mark.asyncio
async def test_bulk_confirm_reevaluates_the_predicates_and_skips_only_the_failing_ids(monkeypatch):
    """D6's whole point: the rules select, a human presses, **the server re-checks at press time**.

    Both ids were selected by the client. One has since picked up an open escalation, so the server
    refuses it -- Flow 6 step 4's "5 confirmed, 1 skipped" with the reason named, never a silent
    partial success and never a blanket refusal of the batch.
    """
    ids = ["APT-A", "APT-B"]
    rows = {i: {**_PENDING, "appointment_id": i} for i in ids}
    session = _bulk_session(rows)
    snapshots = {i: _snapshot(appointment_id=i) for i in ids}
    inputs = {
        "APT-A": _predicate_inputs(appointment_id="APT-A"),
        "APT-B": _predicate_inputs(appointment_id="APT-B", open_escalation_count=2),
    }
    applied: list[str] = []

    async def _apply(_session, _ctx, *, appointment_id, **_kwargs):
        applied.append(appointment_id)

    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(allocation, "_safe_batch_inputs", AsyncMock(return_value=inputs))
    monkeypatch.setattr(allocation, "load_appointment_snapshots", AsyncMock(return_value=snapshots))
    monkeypatch.setattr(allocation, "_apply_confirmation", _apply)
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())

    result = await bulk_confirm(
        session,
        _ops_ctx(),
        command=BulkConfirmCommand(
            appointment_ids=ids,
            snapshot_hash=snapshot.batch_snapshot_hash(
                {i: s["snapshot_hash"] for i, s in snapshots.items()}
            ),
        ),
        idempotency_key="k",
    )

    assert applied == ["APT-A"]
    assert result.confirmed == 1
    assert result.skipped == 1
    assert result.snapshot_hash_matched is True
    by_id = {o.appointment_id: o for o in result.outcomes}
    assert by_id["APT-A"].code == "CONFIRMED"
    assert by_id["APT-B"].code == "NOT_ELIGIBLE"
    assert by_id["APT-B"].failed_predicates == [allocation.PREDICATE_NO_OPEN_ESCALATION]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_bulk_confirm_reports_snapshot_drift_without_refusing_the_whole_batch(monkeypatch):
    """The documented reading of section 7.5.1's single-hash-for-a-list argument.

    A hard refusal would make the spike-clearing path unusable in exactly the conditions it exists
    for, since during a spike some row in a 30-row selection has almost always moved. The
    authoritative gate is the predicate re-check; the composite is reported so the UI can say the
    board moved. **Owner fork** -- see `bulk_confirm`'s docstring.
    """
    rows = {"APT-A": {**_PENDING, "appointment_id": "APT-A"}}
    session = _bulk_session(rows)
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "_safe_batch_inputs",
        AsyncMock(return_value={"APT-A": _predicate_inputs(appointment_id="APT-A")}),
    )
    monkeypatch.setattr(
        allocation,
        "load_appointment_snapshots",
        AsyncMock(return_value={"APT-A": _snapshot(appointment_id="APT-A")}),
    )
    monkeypatch.setattr(allocation, "_apply_confirmation", AsyncMock())
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())

    result = await bulk_confirm(
        session,
        _ops_ctx(),
        command=BulkConfirmCommand(appointment_ids=["APT-A"], snapshot_hash="a-stale-composite"),
        idempotency_key="k",
    )

    assert result.snapshot_hash_matched is False
    assert result.expected_snapshot_hash == "a-stale-composite"
    assert result.current_snapshot_hash != "a-stale-composite"
    assert result.confirmed == 1


@pytest.mark.asyncio
async def test_bulk_confirm_refuses_a_foreign_facility_id_per_row(monkeypatch):
    """Scope is derived per id from the verified identity (M15), never from the request."""
    rows = {"APT-X": {**_PENDING, "appointment_id": "APT-X"}}
    session = _bulk_session(rows)
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "_safe_batch_inputs",
        AsyncMock(
            return_value={
                "APT-X": _predicate_inputs(
                    appointment_id="APT-X", destination_facility_id="FAC-GGN-01"
                )
            }
        ),
    )
    monkeypatch.setattr(
        allocation,
        "load_appointment_snapshots",
        AsyncMock(return_value={"APT-X": _snapshot(appointment_id="APT-X")}),
    )
    apply = AsyncMock()
    monkeypatch.setattr(allocation, "_apply_confirmation", apply)
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())

    result = await bulk_confirm(
        session,
        _ops_ctx(facility_id="FAC-JAI-01"),
        command=BulkConfirmCommand(appointment_ids=["APT-X"], snapshot_hash="h"),
        idempotency_key="k",
    )

    assert result.outcomes[0].code == "OUT_OF_SCOPE"
    assert result.confirmed == 0
    apply.assert_not_awaited()


@pytest.mark.asyncio
async def test_bulk_confirm_reports_a_row_the_sweeper_already_took(monkeypatch):
    rows = {"APT-A": {**_PENDING, "appointment_id": "APT-A", "appointment_status": "EXPIRED"}}
    session = _bulk_session(rows)
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(
        allocation,
        "_safe_batch_inputs",
        AsyncMock(return_value={"APT-A": _predicate_inputs(appointment_id="APT-A")}),
    )
    monkeypatch.setattr(
        allocation,
        "load_appointment_snapshots",
        AsyncMock(return_value={"APT-A": _snapshot(appointment_id="APT-A", status="EXPIRED")}),
    )
    apply = AsyncMock()
    monkeypatch.setattr(allocation, "_apply_confirmation", apply)
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())

    result = await bulk_confirm(
        session,
        _ops_ctx(),
        command=BulkConfirmCommand(appointment_ids=["APT-A"], snapshot_hash="h"),
        idempotency_key="k",
    )

    assert result.outcomes[0].code == "ALREADY_ACTIONED"
    apply.assert_not_awaited()


def test_bulk_confirm_caps_the_batch_size():
    with pytest.raises(ValidationError):
        BulkConfirmCommand(
            appointment_ids=[f"APT{i}" for i in range(allocation.MAX_BULK_CONFIRM_IDS + 1)],
            snapshot_hash="h",
        )


# =================================================================================================
# Issue #66 -- reject_request's enforced enum
# =================================================================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("reason_code", sorted(allocation.REJECTION_REASON_CODES))
async def test_reject_accepts_every_code_in_the_design_vocabulary(monkeypatch, reason_code):
    transition = AsyncMock()
    monkeypatch.setattr(allocation, "_ops_pending_transition", transition)

    await reject_appointment(
        AsyncMock(),
        _ops_ctx(),
        shipment_id="SHP1002",
        command=RejectAppointmentCommand(appointment_id="APT021", reason_code=reason_code),
        idempotency_key="k",
    )

    assert transition.await_args.kwargs["reason"] == reason_code


@pytest.mark.asyncio
async def test_reject_refuses_free_prose_with_a_422_naming_the_supported_set(monkeypatch):
    """section 7.5.1: free prose here becomes an unreviewed customer-facing message.

    The 422-naming-the-set shape is copied deliberately from `escalation_service`'s two sibling
    enums -- issue #66 is about planner and ops disagreeing, so the fix converges rather than
    adding a third style.
    """
    transition = AsyncMock()
    monkeypatch.setattr(allocation, "_ops_pending_transition", transition)

    with pytest.raises(AppError) as exc:
        await reject_appointment(
            AsyncMock(),
            _ops_ctx(),
            shipment_id="SHP1002",
            command=RejectAppointmentCommand(
                appointment_id="APT021", reason_code="no room at the inn"
            ),
            idempotency_key="k",
        )

    assert exc.value.code == "INVALID_REASON_CODE"
    assert exc.value.status_code == 422
    for code in allocation.REJECTION_REASON_CODES:
        assert code in exc.value.detail
    transition.assert_not_awaited()


@pytest.mark.asyncio
async def test_reject_normalises_case_but_still_refuses_anything_outside_the_set(monkeypatch):
    transition = AsyncMock()
    monkeypatch.setattr(allocation, "_ops_pending_transition", transition)

    await reject_appointment(
        AsyncMock(), _ops_ctx(), shipment_id="SHP1002",
        command=RejectAppointmentCommand(appointment_id="APT021", reason_code=" capacity "),
        idempotency_key="k",
    )

    assert transition.await_args.kwargs["reason"] == "CAPACITY"


@pytest.mark.asyncio
async def test_reject_writes_the_code_to_cancellation_reason_and_the_note_only_to_the_audit(
    monkeypatch,
):
    """`cancellation_reason` is what the *next* actor reads back (`_already_actioned_error`) and
    what a driver-facing renderer resolves to copy, so the enum -- not the planner's prose -- is
    what lands there."""
    session = AsyncMock()
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(allocation, "_shipment_for_status", AsyncMock(return_value=_shipment()))
    monkeypatch.setattr(allocation, "_locked_appointment", AsyncMock(return_value=dict(_PENDING)))
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=True))
    monkeypatch.setattr(allocation, "_reread_appointment", AsyncMock(return_value={}))
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())

    await reject_appointment(
        session,
        _ops_ctx(),
        shipment_id="SHP1002",
        command=RejectAppointmentCommand(
            appointment_id="APT021",
            reason_code="RULE_VIOLATION",
            note="RULE005 -- told the driver we will re-offer at 06:00.",
        ),
        idempotency_key="k",
    )

    _sql, update_params = _statement(session, "UPDATE public.appointments")
    assert update_params["reason"] == "RULE_VIOLATION"
    _sql, audit_params = _statement(session, "INSERT INTO public.audit_logs")
    payload = json.loads(audit_params["new_value_json"])
    assert payload["reason"] == "RULE_VIOLATION"
    assert payload["note"].startswith("RULE005")


@pytest.mark.asyncio
async def test_reject_idempotency_hash_covers_the_note_not_just_the_code(monkeypatch):
    """Narrowing `reason` to five values without this would quietly weaken replay protection.

    `reason` used to be free prose and carried nearly all of a reject's entropy. Now that it is one
    of five enum values, two rejects differing only in their note would hash identically -- so
    reusing an Idempotency-Key with a changed payload would silently replay the first response
    instead of raising IDEMPOTENCY_PAYLOAD_MISMATCH.
    """
    seen: list[str] = []

    async def _lookup(_session, *, key, user_id, route, request_hash):
        seen.append(request_hash)
        return None

    monkeypatch.setattr(allocation, "lookup_idempotency", _lookup)
    monkeypatch.setattr(allocation, "_shipment_for_status", AsyncMock(return_value=_shipment()))
    monkeypatch.setattr(allocation, "_locked_appointment", AsyncMock(return_value=dict(_PENDING)))
    monkeypatch.setattr(allocation, "_release_dock_occupancy", AsyncMock(return_value=True))
    monkeypatch.setattr(allocation, "_reread_appointment", AsyncMock(return_value={}))
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())

    for note in ("re-offering at 06:00", "escalating to the regional head"):
        await reject_appointment(
            AsyncMock(),
            _ops_ctx(),
            shipment_id="SHP1002",
            command=RejectAppointmentCommand(
                appointment_id="APT021", reason_code="CAPACITY", note=note
            ),
            idempotency_key="same-key",
        )

    assert len(seen) == 2
    assert seen[0] != seen[1]


# =================================================================================================
# Issue #64 -- hold_for_information (section 7.5.1, FR-PLN-004, Flow 4)
# =================================================================================================

# `booked_at` fixes the derived D9 deadline, so `previous_deadline` is a value these tests can
# predict exactly rather than an approximation of "about now".
_BOOKED_AT = datetime(2026, 8, 16, 9, 0, tzinfo=timezone.utc)
_HELD_PENDING = {**_PENDING, "booked_at": _BOOKED_AT, "expires_at": None}


def _patch_hold_context(monkeypatch, *, appointment: dict | None = None):
    monkeypatch.setattr(allocation, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(allocation, "_shipment_for_status", AsyncMock(return_value=_shipment()))
    monkeypatch.setattr(
        allocation,
        "_locked_appointment",
        AsyncMock(return_value=dict(appointment if appointment is not None else _HELD_PENDING)),
    )
    monkeypatch.setattr(allocation, "_reread_appointment", AsyncMock(return_value={}))
    monkeypatch.setattr(allocation, "store_idempotency", AsyncMock())


_HOLD_QUESTION = "Is the reefer unit actually running? The manifest says ambient."


def _hold_command(**overrides) -> HoldForInformationCommand:
    return HoldForInformationCommand(
        **{"appointment_id": "APT021", "question": _HOLD_QUESTION, **overrides}
    )


@pytest.mark.asyncio
async def test_hold_extends_the_deadline_by_one_further_d9_ttl_and_returns_it(monkeypatch):
    """section 7.5.1: "HELD_FOR_INFO + new_deadline".

    The extension is D9's own `pending_confirmation_ttl_minutes`, not a second invented number --
    asserted against `get_settings()` rather than a hard-coded 15, so re-tuning the TTL cannot
    leave this tool silently on the old value.
    """
    session = AsyncMock()
    _patch_hold_context(monkeypatch)
    ttl = get_settings().pending_confirmation_ttl_minutes

    before = datetime.now(timezone.utc)
    result = await hold_for_information(
        session, _ops_ctx(), shipment_id="SHP1002",
        command=_hold_command(), idempotency_key="k",
    )
    after = datetime.now(timezone.utc)

    assert result.code == "HELD_FOR_INFO"
    # The promise state is untouched: section 4 has no paused state, and a hold is not a transition.
    assert result.status == "PENDING_CONFIRMATION"
    assert result.extension_minutes == ttl
    assert result.hold_used is True
    # `previous_deadline` is the *derived* one -- booked_at + ttl -- exactly as
    # `expiry.py::_pending_candidates`' ELSE branch computes it.
    assert result.previous_deadline == (_BOOKED_AT + timedelta(minutes=ttl)).isoformat()
    new_deadline = datetime.fromisoformat(result.new_deadline)
    assert before + timedelta(minutes=ttl) <= new_deadline <= after + timedelta(minutes=ttl)
    # ...and the row really carries it, as a datetime bind: appointments.expires_at is timestamptz
    # and asyncpg refuses to coerce a str (the DataError expiry.py documents).
    _sql, params = _statement(session, "SET expires_at = :expires_at")
    assert params["expires_at"] == new_deadline
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_second_hold_on_the_same_request_is_refused_as_hold_already_used(monkeypatch):
    """section 7.5.1's cap, verbatim: "Pauses the D9 clock exactly once per request; a second call
    returns HOLD_ALREADY_USED. Without that cap, hold for info becomes an unbounded way to sit on
    capacity."

    The marker is `expires_at IS NOT NULL`, which is the migration's own stated design
    (20260829134929...sql:252-256) -- no separate boolean, no counter.
    """
    session = AsyncMock()
    already = datetime(2026, 8, 16, 9, 20, tzinfo=timezone.utc)
    _patch_hold_context(monkeypatch, appointment={**_HELD_PENDING, "expires_at": already})

    with pytest.raises(AppError) as exc:
        await hold_for_information(
            session, _ops_ctx(), shipment_id="SHP1002",
            command=_hold_command(), idempotency_key="k",
        )

    assert exc.value.code == "HOLD_ALREADY_USED"
    assert exc.value.status_code == 409
    assert json.loads(exc.value.detail)["current_deadline"] == already.isoformat()
    # Nothing written: a refused second hold must not extend the deadline it just refused to extend.
    session.commit.assert_not_awaited()
    with pytest.raises(AssertionError):
        _statement(session, "SET expires_at = :expires_at")


@pytest.mark.asyncio
async def test_the_update_carries_its_own_once_only_and_still_pending_predicates(monkeypatch):
    """Belt-and-braces under a lock we already hold, but the invariant belongs where PostgreSQL can
    enforce it: this statement can never extend a request that stopped being pending, nor spend a
    second extension, even if a future caller reaches it by another route."""
    session = AsyncMock()
    _patch_hold_context(monkeypatch)

    await hold_for_information(
        session, _ops_ctx(), shipment_id="SHP1002",
        command=_hold_command(), idempotency_key="k",
    )

    sql, _params = _statement(session, "SET expires_at = :expires_at")
    assert "appointment_status = 'PENDING_CONFIRMATION'" in sql
    assert "expires_at IS NULL" in sql


@pytest.mark.asyncio
async def test_hold_on_a_row_the_sweeper_already_took_is_already_actioned(monkeypatch):
    """Same race, same answer as confirm/reject: the D9 sweeper can win while the planner is still
    typing the question, and the loser is told which transition won (section 7.5.1)."""
    session = AsyncMock()
    _patch_hold_context(
        monkeypatch,
        appointment={
            **_HELD_PENDING,
            "appointment_status": "EXPIRED",
            "cancellation_reason": "PENDING_CONFIRMATION expired unactioned (D9, 15-minute TTL)",
        },
    )

    with pytest.raises(AppError) as exc:
        await hold_for_information(
            session, _ops_ctx(), shipment_id="SHP1002",
            command=_hold_command(), idempotency_key="k",
        )

    assert exc.value.code == "ALREADY_ACTIONED"
    assert "EXPIRED" in exc.value.message
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_audit_row_reconstructs_the_whole_hold_from_itself(monkeypatch):
    """M14: who paused it, what they asked, both deadlines, and that the one extension is spent.

    `action_type` stays the generic `UPDATE` because `audit_logs_action_type_check` admits a closed
    sixteen-value set with no hold-for-information verb -- the same constraint `counter_offer`
    works within, and the same reason the discriminator lives in the payload.
    """
    session = AsyncMock()
    _patch_hold_context(monkeypatch)

    result = await hold_for_information(
        session, _ops_ctx(), shipment_id="SHP1002",
        command=_hold_command(), idempotency_key="k",
    )

    _sql, params = _statement(session, "INSERT INTO public.audit_logs")
    payload = json.loads(params["new_value_json"])
    assert params["action_type"] == allocation.AUDIT_ACTION_HOLD_FOR_INFORMATION == "UPDATE"
    assert payload["transition"] == allocation.AUDIT_TRANSITION_HELD_FOR_INFO == "HELD_FOR_INFO"
    assert payload["question"] == _HOLD_QUESTION
    assert payload["new_deadline"] == result.new_deadline
    assert payload["previous_deadline"] == result.previous_deadline
    assert payload["hold_used"] is True
    assert json.loads(params["old_value_json"])["expires_at"] is None
    # audit_logs.created_at was never converted by E1.1 and must stay a string bind.
    assert isinstance(params["created_at"], str)


@pytest.mark.asyncio
async def test_hold_derives_scope_from_the_shipment_and_refuses_another_facility(monkeypatch):
    """M15 / section 7.5 principle 1: no scope id is accepted from the caller, and a planner scoped
    to Jaipur cannot hold a Gurgaon request by naming its shipment."""
    session = AsyncMock()
    _patch_hold_context(monkeypatch)
    monkeypatch.setattr(
        allocation,
        "_shipment_for_status",
        AsyncMock(return_value=_shipment(facility_id="FAC-GGN-01")),
    )

    with pytest.raises(AppError) as exc:
        await hold_for_information(
            session, _ops_ctx(facility_id="FAC-JAI-01"), shipment_id="SHP1002",
            command=_hold_command(), idempotency_key="k",
        )

    assert exc.value.status_code == 403
    session.commit.assert_not_awaited()


def test_the_command_refuses_a_client_supplied_deadline_or_snapshot_hash():
    """The catalog gives this tool three arguments and no duration. A client that could choose how
    long the hold buys would have the unbounded sit-on-capacity the cap exists to prevent; and a
    `snapshot_hash` is deliberately absent because this consumes no capacity (section 7.5's
    principle 3 attaches that guard to writes that do)."""
    for extra in (
        {"new_deadline": "2026-08-16T10:00:00+00:00"},
        {"extension_minutes": 600},
        {"snapshot_hash": "abc"},
    ):
        with pytest.raises(ValidationError):
            HoldForInformationCommand(appointment_id="APT021", question="why?", **extra)


@pytest.mark.asyncio
async def test_a_retried_hold_replays_the_stored_response_rather_than_extending_twice(monkeypatch):
    """M9. A retry is not a second extension -- and because the cap is `expires_at IS NOT NULL`, a
    replay that fell through to the write path would come back HOLD_ALREADY_USED and turn a network
    retry into a user-visible refusal."""
    session = AsyncMock()
    _patch_hold_context(monkeypatch)
    stored = {
        "as_of": "2026-08-16T09:05:00+00:00",
        "shipment_id": "SHP1002",
        "appointment_id": "APT021",
        "question": _HOLD_QUESTION,
        "new_deadline": "2026-08-16T09:20:00+00:00",
        "previous_deadline": "2026-08-16T09:15:00+00:00",
        "extension_minutes": 15,
        "idempotency_key": "k",
    }
    monkeypatch.setattr(
        allocation, "lookup_idempotency", AsyncMock(return_value={"response": stored})
    )

    result = await hold_for_information(
        session, _ops_ctx(), shipment_id="SHP1002",
        command=_hold_command(), idempotency_key="k",
    )

    assert result.idempotent_replay is True
    assert result.new_deadline == "2026-08-16T09:20:00+00:00"
    session.execute.assert_not_awaited()


def test_the_hold_route_is_registered_on_the_planner_rest_surface_only():
    """Where section 7.5.1 puts this tool, checked rather than assumed.

    It is a *planner console* affordance (section 7.5.1, Flow 4, keyboard `H`), and section 7.5.4
    enumerates the driver LLM allowlist in full -- twelve tools, `hold_for_information` not among
    them. So there must be a REST route and there must **not** be an assistant tool: an LLM able to
    pause a request's D9 clock on the driver's behalf is exactly the authority D6 withholds.
    """
    from app.assistant.tools import build_driver_tools
    from app.main import app

    path = "/api/v1/shipments/{shipment_id}/appointments/{appointment_id}/hold-for-information"
    assert "post" in app.openapi()["paths"][path]

    tool_names = {
        tool.name
        for tool in build_driver_tools(
            session=AsyncMock(), ctx=_ops_ctx(), thread_id="THR-TEST"
        )
    }
    assert "hold_for_information" not in tool_names
