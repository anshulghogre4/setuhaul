"""D2's HELD promise-state: `create_hold`, `confirm_held_slot`, and the migration behind them.

Issue #53. Design citation: `SOLUTION_DESIGN.md` section 0.8, section 4, section 7.1, section
7.5.4, D2, M5, M6, M9, M14, M15.

What these tests are actually pinning down, beyond "it runs":

* **M15** -- `confirm_held_slot` takes a hold id and *derives* the shipment from the held row. The
  test that matters here is the one where a driver presents a hold belonging to someone else and
  is refused; that is the hole a `shipment_id` argument would have opened.
* **Section 4's "Held != booked"** -- `create_hold` writes `appointment_id = NULL`, and the
  appointment row is created at confirm time, not hold time.
* **The no-gap invariant** -- confirm *flips* the existing `dock_occupancy` row rather than
  deleting and re-inserting it. A DELETE/INSERT pair would leave the interval momentarily
  unprotected by the exclusion constraint. Asserted on the SQL itself, because it is the kind of
  thing a later "tidy-up" would cheerfully break.
* **Section 0.8's lazy expiry** -- *"Never depend on the sweeper for correctness"*: the locking
  SELECT carries `expires_at > :now` in its own WHERE, so a lapsed hold is unconfirmable even if
  the sweeper has not run.
* **The migration and the code agree** -- the parity test at the bottom reads the migration file
  and asserts the DDL the Python actually depends on. This whole issue exists because code and
  schema drifted apart silently for three days; a test that fails when they drift again is the
  cheapest guard against a repeat.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling import holds

SNAPSHOT = datetime(2026, 8, 13, 6, 30, tzinfo=timezone.utc)

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase"
    / "migrations"
    / "20260829134929_d2_held_state_dock_occupancy.sql"
)


def _driver_ctx(driver_id: str = "DRV001") -> ExecutionContext:
    return ExecutionContext(
        request_id="req",
        auth_subject="auth-driver",
        user_id="USR001",
        email="ravi.kumar@setuhaul.example",
        full_name="Ravi Kumar",
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id=driver_id,
        facility_id="FAC-JAI-01",
    )


def _hold_row(**overrides) -> dict:
    row = {
        "occupancy_id": 42,
        "dock_id": "DCK-J1",
        "shipment_id": "SHP1002",
        "state": "HELD",
        "expires_at": SNAPSHOT + timedelta(seconds=60),
        "policy_version": "POL-1",
        "window": None,
        "window_start": SNAPSHOT + timedelta(hours=3),
        "slot_id": "SLT001",
        "facility_id": "FAC-JAI-01",
        "slot_start_ts": SNAPSHOT + timedelta(hours=3),
        "slot_end_ts": SNAPSHOT + timedelta(hours=4),
        "slot_status": "OPEN",
        "block_reason": None,
        "dock_code": "D1",
        "dock_type": "STANDARD",
        "supports_refrigerated": 0,
        "max_vehicle_weight_kg": 25000,
        "dock_status": "ACTIVE",
    }
    row.update(overrides)
    return row


def _shipment_row(driver_id: str = "DRV001") -> dict:
    return {
        "shipment_id": "SHP1002",
        "driver_id": driver_id,
        "vehicle_id": "VEH1",
        "destination_facility_id": "FAC-JAI-01",
        "priority_code": "NORMAL",
        "required_dock_type": "STANDARD",
        "temperature_control_required": 0,
        "load_weight_kg": 18000,
        "expected_unload_min": 60,
        "current_status": "IN_TRANSIT",
        "effective_eta_ts": (SNAPSHOT + timedelta(hours=2)).isoformat(),
        "eta_source": "DRIVER_DECLARED",
        "eta_confidence": "HIGH",
        "facility_id": "FAC-JAI-01",
        "timezone": "Asia/Kolkata",
        "open_time": "06:00",
        "close_time": "22:00",
        "active_flag": 1,
    }


def _confirm_session(
    *,
    hold: dict | None,
    epitaph: dict | None = None,
    shipment: dict | None = None,
) -> AsyncMock:
    """Scripted session for `confirm_held_slot`, keyed on each statement's distinguishing text."""
    session = AsyncMock()
    shipment_row = shipment if shipment is not None else _shipment_row()

    async def _execute(statement, params=None):
        sql = str(statement)
        result = MagicMock()
        if "FOR UPDATE OF o" in sql:
            result.mappings.return_value.first.return_value = hold
        elif "FROM public.dock_occupancy" in sql and "occupancy_id = :hold_id" in sql:
            result.mappings.return_value.first.return_value = epitaph
        elif "FROM public.shipments s" in sql:
            result.mappings.return_value.first.return_value = shipment_row
        elif "dock_status_events" in sql:
            result.mappings.return_value.first.return_value = None
        elif "UPDATE public.dock_occupancy" in sql:
            # Two callers read this statement's RETURNING differently: `confirm_held_slot`'s flip
            # takes `.first()` (it only needs "did a row change"), while `_expire_hold_row` takes
            # `.mappings().first()` because its audit row records the dock and shipment. Script
            # both so either path gets a real value rather than a MagicMock.
            result.first.return_value = (42,)
            result.mappings.return_value.first.return_value = {
                "occupancy_id": 42,
                "dock_id": "DCK-J1",
                "shipment_id": "SHP1002",
            }
        elif "FROM public.appointments a" in sql:
            result.mappings.return_value.first.return_value = {
                "appointment_id": "APT-NEW",
                "appointment_status": "PENDING_CONFIRMATION",
            }
        return result

    session.execute.side_effect = _execute
    return session


@pytest.fixture(autouse=True)
def _stub_collaborators(monkeypatch):
    """Neutralise the shared helpers so each test exercises `holds.py`'s own logic.

    `evaluate_candidate_slot` is Stage 1 and has its own suite; here it is stubbed to "feasible"
    except where a test overrides it, so a failure in this module points at the hold path rather
    than at a constraint rule.
    """
    monkeypatch.setattr(holds, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(
        holds, "evaluate_candidate_slot", lambda **kwargs: ({"option_rank": 1}, None)
    )
    monkeypatch.setattr(holds.allocation, "_store_request_idempotency", AsyncMock())
    monkeypatch.setattr(
        holds.allocation,
        "_reread_appointment",
        AsyncMock(return_value={"appointment_id": "APT-NEW", "appointment_status": "PENDING_CONFIRMATION"}),
    )


# --------------------------------------------------------------------------------------
# M15 -- scope is derived from the held row, never from an argument
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_refuses_a_hold_belonging_to_another_driver():
    """The whole reason `hold_id` is the only argument (section 7.5 principle 1).

    If this tool accepted a `shipment_id`, the natural implementation would scope-check the id the
    caller sent while converting the capacity named by the hold -- and a driver could commit
    somebody else's reserved interval. Here the shipment is read off the hold and checked against
    the authenticated driver, so a mismatch is a 403 rather than a booking.
    """
    session = _confirm_session(hold=_hold_row(), shipment=_shipment_row(driver_id="DRV-OTHER"))

    with pytest.raises(AppError) as exc:
        await holds.confirm_held_slot(
            session, _driver_ctx("DRV001"), hold_id="42", idempotency_key="idem-1"
        )

    assert exc.value.code == "FORBIDDEN"
    assert exc.value.status_code == 403
    assert not [
        call
        for call in session.execute.await_args_list
        if "INSERT INTO public.appointments" in str(call.args[0])
    ]


@pytest.mark.asyncio
async def test_confirm_takes_only_a_hold_id_and_never_a_scope_argument():
    """A signature test, deliberately: M15 is a contract, not an implementation detail."""
    import inspect

    params = set(inspect.signature(holds.confirm_held_slot).parameters)

    assert "hold_id" in params
    for forbidden in ("shipment_id", "facility_id", "carrier_id", "driver_id", "dock_id"):
        assert forbidden not in params, (
            f"`{forbidden}` must not be an argument: section 7.5's first principle is that scope is "
            "derived from the authenticated identity, never accepted from the caller."
        )


# --------------------------------------------------------------------------------------
# Section 0.8 -- expiry is lazy first, swept second
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_locks_only_a_live_hold_and_checks_the_ttl_itself():
    """"Never depend on the sweeper for correctness -- only for hygiene" (section 0.8)."""
    session = _confirm_session(hold=_hold_row())

    await holds.confirm_held_slot(
        session, _driver_ctx(), hold_id="42", idempotency_key="idem-1"
    )

    sql = next(
        str(call.args[0])
        for call in session.execute.await_args_list
        if "FOR UPDATE OF o" in str(call.args[0])
    )
    assert "o.state = 'HELD'" in sql
    assert "o.expires_at > :now" in sql
    # No SKIP LOCKED here, unlike the sweeper: a driver's confirm silently no-opping because a row
    # was momentarily locked would be a bug (see `holds.py`'s note on the asymmetry).
    assert "SKIP LOCKED" not in sql


@pytest.mark.asyncio
async def test_confirm_reports_a_lapsed_hold_as_expired_rather_than_missing():
    """Section 0.8's driver-facing promise: "that hold lapsed, here are current options"."""
    session = _confirm_session(
        hold=None,
        epitaph={"occupancy_id": 42, "state": "HELD", "expires_at": SNAPSHOT, "shipment_id": "SHP1002"},
    )

    result = await holds.confirm_held_slot(
        session, _driver_ctx(), hold_id="42", idempotency_key="idem-1"
    )

    assert result.code == "HOLD_EXPIRED"
    assert result.appointment_writes == 0
    assert result.appointment_id is None
    assert "lapsed" in (result.conflict or {})["message"]


@pytest.mark.asyncio
async def test_confirm_reports_an_already_converted_hold_distinctly_from_a_lapsed_one():
    """A hold the driver already committed is a different fact from one that ran out of time."""
    session = _confirm_session(
        hold=None,
        epitaph={
            "occupancy_id": 42,
            "state": "PENDING_CONFIRMATION",
            "expires_at": None,
            "shipment_id": "SHP1002",
        },
    )

    result = await holds.confirm_held_slot(
        session, _driver_ctx(), hold_id="42", idempotency_key="idem-1"
    )

    assert result.code == "HOLD_ALREADY_ACTIONED"
    assert "PENDING_CONFIRMATION" in (result.conflict or {})["message"]


@pytest.mark.asyncio
async def test_confirm_raises_not_found_for_a_hold_that_never_existed():
    session = _confirm_session(hold=None, epitaph=None)

    with pytest.raises(AppError) as exc:
        await holds.confirm_held_slot(
            session, _driver_ctx(), hold_id="999", idempotency_key="idem-1"
        )

    assert exc.value.code == "HOLD_NOT_FOUND"
    assert exc.value.status_code == 404


@pytest.mark.parametrize("bad_id", ["hold-abc", "", "42abc", "  "])
@pytest.mark.asyncio
async def test_confirm_refuses_a_non_numeric_hold_id_without_touching_the_database(bad_id):
    """`occupancy_id` is `bigint`, and asyncpg refuses to coerce a str into one.

    Caught by the first real-PostgreSQL run of the integration suite, not by any mocked test:
    binding `'22'` to that parameter raises `asyncpg.exceptions.DataError: invalid input for query
    argument $1: '22' ('str' object cannot be interpreted as an integer)`. Ids stay strings at the
    tool boundary (an LLM argument is a string whatever the schema says), so a hallucinated
    `"hold-abc"` must become a clean HOLD_NOT_FOUND the model can narrate, never a 500.
    """
    session = _confirm_session(hold=None, epitaph=None)

    with pytest.raises(AppError) as exc:
        await holds.confirm_held_slot(
            session, _driver_ctx(), hold_id=bad_id, idempotency_key="idem-1"
        )

    assert exc.value.code == "HOLD_NOT_FOUND"
    assert not [
        call for call in session.execute.await_args_list if "dock_occupancy" in str(call.args[0])
    ], "a malformed id must be rejected before any query is issued"


# --------------------------------------------------------------------------------------
# Section 7.1 -- "produces PENDING_CONFIRMATION", on the same row, with no gap
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_creates_the_appointment_and_flips_the_same_occupancy_row():
    session = _confirm_session(hold=_hold_row())

    result = await holds.confirm_held_slot(
        session, _driver_ctx(), hold_id="42", idempotency_key="idem-1"
    )

    assert result.status == "PENDING_CONFIRMATION"
    assert result.code == "SLOT_REQUESTED"
    assert result.appointment_writes == 1
    assert result.shipment_id == "SHP1002"

    appointment_sql = next(
        str(call.args[0])
        for call in session.execute.await_args_list
        if "INSERT INTO public.appointments" in str(call.args[0])
    )
    # D6/M7: this tool reaches PENDING_CONFIRMATION and stops. Nothing here may write CONFIRMED.
    assert "'PENDING_CONFIRMATION'" in appointment_sql
    assert "CONFIRMED" not in appointment_sql.replace("PENDING_CONFIRMATION", "")

    flip_sql = next(
        str(call.args[0])
        for call in session.execute.await_args_list
        if "UPDATE public.dock_occupancy" in str(call.args[0])
    )
    assert "SET state = 'PENDING_CONFIRMATION'" in flip_sql
    assert "appointment_id = :appointment_id" in flip_sql
    assert "expires_at = NULL" in flip_sql
    assert "state = 'HELD'" in flip_sql, "the race guard against the sweeper must stay"


@pytest.mark.asyncio
async def test_confirm_never_deletes_and_reinserts_the_capacity_claim():
    """The no-gap invariant, asserted on the statements actually issued.

    A DELETE+INSERT would release the interval for the instant between the two statements. Under
    the exclusion constraint that instant is enough for a competing `create_hold` to win capacity
    that was already promised -- so this is a correctness assertion, not a style one.
    """
    session = _confirm_session(hold=_hold_row())

    await holds.confirm_held_slot(
        session, _driver_ctx(), hold_id="42", idempotency_key="idem-1"
    )

    statements = [str(call.args[0]) for call in session.execute.await_args_list]
    occupancy_writes = [s for s in statements if "dock_occupancy" in s and "SELECT" not in s]
    assert occupancy_writes, "the hold must actually be converted"
    for sql in occupancy_writes:
        assert "DELETE" not in sql.upper()
        assert "INSERT INTO public.dock_occupancy" not in sql


@pytest.mark.asyncio
async def test_confirm_releases_the_hold_when_revalidation_fails(monkeypatch):
    """Section 7.1's "revalidates inside the transaction" -- and cleans up when it refuses.

    A hold the driver can no longer use must not keep sterilising capacity for the rest of its TTL.
    """

    class _Reason:
        failure_code = "DOCK_UNAVAILABLE"
        message = "That dock went out of service."

    monkeypatch.setattr(holds, "evaluate_candidate_slot", lambda **kwargs: (None, _Reason()))
    session = _confirm_session(hold=_hold_row())

    result = await holds.confirm_held_slot(
        session, _driver_ctx(), hold_id="42", idempotency_key="idem-1"
    )

    assert result.code == "SLOT_CONFLICT_REFRESH_REQUIRED"
    assert result.appointment_writes == 0
    assert not [
        call
        for call in session.execute.await_args_list
        if "INSERT INTO public.appointments" in str(call.args[0])
    ]
    expire_sql = next(
        str(call.args[0])
        for call in session.execute.await_args_list
        if "UPDATE public.dock_occupancy" in str(call.args[0])
    )
    assert "SET state = 'EXPIRED'" in expire_sql


@pytest.mark.asyncio
async def test_confirm_replays_idempotently_without_a_second_appointment(monkeypatch):
    """M9: "duplicates and retries cannot double-act"."""
    stored = {
        "as_of": SNAPSHOT.isoformat(),
        "status": "PENDING_CONFIRMATION",
        "code": "SLOT_REQUESTED",
        "hold_id": "42",
        "shipment_id": "SHP1002",
        "appointment_id": "APT-FIRST",
        "appointment_writes": 1,
    }
    monkeypatch.setattr(holds, "lookup_idempotency", AsyncMock(return_value={"response": stored}))
    session = _confirm_session(hold=_hold_row())

    result = await holds.confirm_held_slot(
        session, _driver_ctx(), hold_id="42", idempotency_key="idem-1"
    )

    assert result.idempotent_replay is True
    assert result.appointment_id == "APT-FIRST"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirm_audits_the_transition_naming_the_hold_it_came_from():
    """M14: "who, what, when, which policy version, which tool call"."""
    session = _confirm_session(hold=_hold_row())

    await holds.confirm_held_slot(
        session, _driver_ctx(), hold_id="42", idempotency_key="idem-1", note="on my way"
    )

    audit = next(
        call.args[1]
        for call in session.execute.await_args_list
        if "INSERT INTO public.audit_logs" in str(call.args[0])
    )
    assert audit["user_id"] == "USR001"
    assert audit["action_type"] == holds.AUDIT_ACTION_CONFIRM_HOLD
    old_value = json.loads(audit["old_value_json"])
    new_value = json.loads(audit["new_value_json"])
    assert old_value["state"] == "HELD"
    assert new_value["status"] == "PENDING_CONFIRMATION"
    assert new_value["hold_id"] == "42"
    assert new_value["note"] == "on my way"


# --------------------------------------------------------------------------------------
# Section 4 -- "Held != booked: no `appointments` row exists yet"
# --------------------------------------------------------------------------------------


def _dock_occupancy_insert(session) -> tuple[str, dict]:
    """The one `INSERT INTO public.dock_occupancy` statement a mocked session was handed.

    Selected by content rather than by list position. These tests used to index `[0]`, which was
    correct until issue #97 added a lazy-expiry UPDATE ahead of the INSERT -- at which point the
    assertions silently began describing a different statement. Matching on what the statement
    *is* cannot rot that way.
    """
    matches = [
        (str(call.args[0]), call.args[1])
        for call in session.execute.await_args_list
        if "INSERT INTO public.dock_occupancy" in str(call.args[0])
    ]
    assert len(matches) == 1, f"expected exactly one dock_occupancy INSERT, got {len(matches)}"
    return matches[0]


@pytest.mark.asyncio
async def test_create_hold_writes_no_appointment_and_stamps_the_ttl():
    session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "occupancy_id": 42,
        "dock_id": "DCK-J1",
        "window": None,
        "expires_at": SNAPSHOT + timedelta(seconds=90),
    }
    # Issue #97 put a lazy-expiry UPDATE ahead of the INSERT; nothing lapsed is the common case.
    result.mappings.return_value.all.return_value = []
    session.execute.return_value = result

    await holds.create_hold(
        session,
        shipment_id="SHP1002",
        slot_id="SLT001",
        policy_version="POL-1",
        ttl_seconds=90,
        now=SNAPSHOT,
        actor_user_id="USR001",
    )

    # By content rather than by position -- see `_dock_occupancy_insert`.
    insert_sql, params = _dock_occupancy_insert(session)
    assert "INSERT INTO public.dock_occupancy" in insert_sql
    assert "'HELD'" in insert_sql
    # The NULL is section 4 expressed in SQL. A hold that carried an appointment_id would be a
    # booking wearing a different state name.
    assert "NULL" in insert_sql

    assert params["expires_at"] == SNAPSHOT + timedelta(seconds=90)
    # asyncpg encodes timestamptz with its datetime codec and raises DataError on a str.
    assert isinstance(params["expires_at"], datetime)


@pytest.mark.asyncio
async def test_create_hold_uses_the_same_interval_expression_as_the_booking_claim():
    """A hold and the booking it becomes must mean the *same* interval.

    If the two expressions differed, `confirm_held_slot` would convert a hold on one range into an
    appointment on another, and the exclusion constraint would have been protecting the wrong
    interval for the whole TTL. Pinned character-for-character against
    `allocation._claim_dock_occupancy`, which itself mirrors the E1.1 backfill.
    """
    from app.scheduling import allocation

    def _interval(source: str) -> str:
        match = re.search(r"tstzrange\((.*?)'\[\)'\s*\)", source, re.S)
        assert match, "interval expression not found"
        return re.sub(r"\s+", " ", match.group(1)).strip()

    session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = {
        "occupancy_id": 1, "dock_id": "D", "window": None, "expires_at": SNAPSHOT,
    }
    result.mappings.return_value.all.return_value = []
    session.execute.return_value = result
    await holds.create_hold(
        session, shipment_id="S", slot_id="L", policy_version="P",
        ttl_seconds=90, now=SNAPSHOT, actor_user_id="U",
    )
    hold_sql, _ = _dock_occupancy_insert(session)

    claim_session = AsyncMock()
    claim_result = MagicMock()
    claim_result.mappings.return_value.first.return_value = None
    claim_result.mappings.return_value.all.return_value = []
    claim_session.execute.return_value = claim_result
    await allocation._claim_dock_occupancy(
        claim_session,
        appointment_id="A",
        shipment_id="S",
        slot_id="L",
        now=SNAPSHOT,
        actor_user_id="U",
    )
    claim_sql, _ = _dock_occupancy_insert(claim_session)

    assert _interval(hold_sql) == _interval(claim_sql)

    # Issue #97's third copy of the same expression. The lazy-expiry UPDATE both paths now run
    # first has to ask about *the interval the INSERT below it would take*, or it would clear the
    # wrong rows -- so it is pinned to the same expression here rather than trusted to stay in step.
    for owner in (session, claim_session):
        lazy_sql = next(
            str(call.args[0])
            for call in owner.execute.await_args_list
            if "UPDATE public.dock_occupancy o" in str(call.args[0])
        )
        assert _interval(lazy_sql) == _interval(hold_sql)


# --------------------------------------------------------------------------------------
# The migration and the code must not drift apart again
# --------------------------------------------------------------------------------------


def test_migration_declares_every_column_and_constraint_the_code_depends_on():
    """This issue exists because code and schema drifted silently. This is the guard.

    `expiry.py` carried a hand-written comment for three days describing columns that did not
    exist. Every assertion below names something `holds.py` or the migration's own header depends
    on being true.
    """
    sql = MIGRATION.read_text(encoding="utf-8")

    for column in ("shipment_id", "state", "expires_at", "policy_version"):
        assert f"ADD COLUMN IF NOT EXISTS {column}" in sql, f"dock_occupancy.{column} missing"

    # A hold has no appointment; the column must be nullable or `create_hold` cannot insert.
    assert "ALTER COLUMN appointment_id DROP NOT NULL" in sql

    # The constraint name is hardcoded in `allocation.py` and matched on to translate an
    # ExclusionViolationError into SLOT_CONFLICT_REFRESH_REQUIRED. If the migration ever let
    # Postgres auto-name it, every real capacity race would surface as a raw 500.
    assert "ADD CONSTRAINT dock_occupancy_dock_id_window_excl" in sql
    assert allocation_constraint_name() in sql

    # Section 0.8's partial predicate, without which a swept hold would keep blocking capacity.
    assert "EXCLUDE USING gist (dock_id WITH =, \"window\" WITH &&)" in sql
    assert "WHERE (state IN ('HELD','PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS'))" in sql

    # #64's column, and the guard that stops a non-HELD row being swept as a lapsed hold.
    assert "ALTER TABLE public.appointments" in sql
    assert "ADD COLUMN IF NOT EXISTS expires_at timestamptz" in sql
    assert "dock_occupancy_held_shape_check" in sql


def allocation_constraint_name() -> str:
    from app.scheduling.allocation import DOCK_OCCUPANCY_EXCLUSION_CONSTRAINT

    return DOCK_OCCUPANCY_EXCLUSION_CONSTRAINT


def test_migration_does_not_add_held_to_the_appointments_status_check():
    """A design decision worth a test, because the issue text asked for the opposite.

    Section 4: "Held != booked: no `appointments` row exists yet." A hold is a `dock_occupancy` row
    and nothing else, so 'HELD' in `appointments_appointment_status_check` would be a value no code
    path can produce -- and one that every active-status enumeration in the codebase
    (`ACTIVE_APPOINTMENT_STATUSES`, `v_slot_availability`, `v_inbound_operational_state`,
    `planner_service`) would silently ignore. If a later change adds it, this test should fail and
    force the discussion rather than let the two models coexist.
    """
    # Comment lines are stripped before the check: the migration's header *discusses* this
    # constraint at length (explaining why it is deliberately left alone), and matching that prose
    # would make the test assert the opposite of what it means. Only executable DDL counts.
    executable = "\n".join(
        line for line in MIGRATION.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("--")
    )

    assert "appointments_appointment_status_check" not in executable
    assert "'HELD'" not in executable.split("ALTER TABLE public.appointments")[-1]
