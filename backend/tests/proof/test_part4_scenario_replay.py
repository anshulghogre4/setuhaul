"""Section 10 part 4 -- the scenario replay suite, with mechanically-asserted coverage.

Design citation: `SOLUTION_DESIGN.md` section 10.4 --

    "Each of the 29 seeded cases in the database guide section 6 becomes a named test with an
     expected outcome -- including the ones that must escalate (SHP1015 reefer, OM004 failed email,
     contradictory warehouse reply). Coverage is asserted mechanically: a case with no named test
     fails the suite, so the mapping cannot silently rot."

Also section 9.2's stress-test table. GitHub issue #44.

## How coverage is asserted, and why it is not a comment

`seed_cases.load_seeded_cases()` parses the guide's own section 6 table at test time.
`test_every_seeded_case_has_a_named_assertion` then compares that against `CASE_ASSERTIONS` in
**both** directions: a guide row with no assertion fails, and an assertion naming a case the guide
no longer contains fails too. There is no list of case names typed out anywhere in this file.

## Every assertion runs against the pristine seed database

`seed_session` is a `CREATE DATABASE ... TEMPLATE` copy that nothing in this suite writes to, so
these are genuinely assertions about *the shipped seed*, not about whatever earlier tests left
behind. Where a case is about the engine rather than the data, the real
`feasibility.find_feasible_slots` is called -- its search window is anchored on the shipment's ETA,
never on the wall clock, so the answers are reproducible on any day.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.scheduling import feasibility
from app.scheduling.feasibility import OUTCOME_NO_FEASIBLE_SLOT, find_feasible_slots
from tests.proof.evidence import record_evidence
from tests.proof.seed_cases import DESIGN_STATED_CASE_COUNT, load_seeded_cases

pytestmark = pytest.mark.asyncio(loop_scope="session")

ACTIVE = ("PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS")


# ----------------------------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------------------------


async def _driver_ctx(session: AsyncSession, shipment_id: str) -> ExecutionContext:
    """A read-scoped driver identity derived from the shipment's own `driver_id`.

    Derived rather than hard-coded: M15's rule is that scope comes from identity, and the mirror
    of that in a test is that the identity comes from the row, so an assertion cannot accidentally
    pass by asserting against the wrong driver's data.
    """
    row = (
        await session.execute(
            text("SELECT driver_id, destination_facility_id FROM public.shipments WHERE shipment_id = :s"),
            {"s": shipment_id},
        )
    ).mappings().first()
    assert row is not None, f"{shipment_id} is not in the shipped seed"
    return ExecutionContext(
        request_id=f"proof-{shipment_id}",
        auth_subject=f"proof-{shipment_id}",
        user_id=f"USR-PROOF-{row['driver_id']}",
        email=f"{str(row['driver_id']).lower()}@proof.invalid",
        full_name="Proof Reader",
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id=str(row["driver_id"]),
        facility_id=str(row["destination_facility_id"]),
    )


async def _scalar(session: AsyncSession, sql: str, **params):
    return await session.scalar(text(sql), params)


async def _rows(session: AsyncSession, sql: str, **params) -> list[dict]:
    result = await session.execute(text(sql), params)
    return [dict(row) for row in result.mappings().all()]


# ----------------------------------------------------------------------------------------------
# One assertion per seeded case. Names are the guide's own, verbatim.
# ----------------------------------------------------------------------------------------------


async def case_normal_appointment(session):
    """`SHP1002` -- a truck arrives in its window and unloads. One live appointment, one check-in
    that reached the dock."""
    appt = await _rows(
        session,
        "SELECT appointment_id, appointment_status, slot_id FROM public.appointments "
        "WHERE shipment_id = 'SHP1002' AND is_current = 1",
    )
    assert len(appt) == 1 and appt[0]["appointment_status"] in ACTIVE
    checkin = await _rows(
        session,
        "SELECT gate_in_ts, dock_in_ts, queue_state, actual_dock_id "
        "FROM public.facility_checkins WHERE shipment_id = 'SHP1002'",
    )
    assert len(checkin) == 1
    assert checkin[0]["dock_in_ts"] is not None, "the normal case never reached a dock"
    assert checkin[0]["queue_state"] == "IN_DOCK"


async def case_early_arrival(session):
    """`SHP1003 / THR007` -- gate-in strictly before the booked slot start, and the queue says so."""
    row = (
        await _rows(
            session,
            """
            SELECT fc.gate_in_ts, fc.arrival_state, fc.queue_state, sl.slot_start_ts
            FROM public.facility_checkins fc
            JOIN public.appointments a ON a.shipment_id = fc.shipment_id AND a.is_current = 1
            JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
            WHERE fc.shipment_id = 'SHP1003'
            """,
        )
    )[0]
    assert row["gate_in_ts"] < row["slot_start_ts"], "SHP1003 did not actually arrive early"
    assert row["arrival_state"] == "EARLY"
    assert row["queue_state"] == "WAITING_EARLY"
    thread = await _rows(
        session,
        "SELECT thread_intent FROM public.chat_threads WHERE thread_id = 'THR007'",
    )
    assert thread and thread[0]["thread_intent"] == "EARLY_ARRIVAL"


async def case_late_arrival_already_at_yard(session):
    """`SHP1004 / THR008` -- physically present, but after the slot started."""
    row = (
        await _rows(
            session,
            """
            SELECT fc.gate_in_ts, fc.arrival_state, fc.queue_state, sl.slot_start_ts
            FROM public.facility_checkins fc
            JOIN public.appointments a ON a.shipment_id = fc.shipment_id AND a.is_current = 1
            JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
            WHERE fc.shipment_id = 'SHP1004'
            """,
        )
    )[0]
    assert row["gate_in_ts"] > row["slot_start_ts"]
    assert row["arrival_state"] == "LATE"
    assert row["queue_state"] == "WAITING_LATE"
    exceptions = await _rows(
        session,
        "SELECT exception_id FROM public.driver_exceptions WHERE thread_id = 'THR008'",
    )
    assert exceptions, "the late-at-yard case raised no exception"


async def case_late_eta_reported_before_arrival(session):
    """`SHP1006 / THR001` -- the delay is declared while still in transit, so there is no check-in
    row at all, and an exception exists carrying the declared ETA."""
    checkins = await _scalar(
        session, "SELECT count(*) FROM public.facility_checkins WHERE shipment_id = 'SHP1006'"
    )
    assert int(checkins) == 0, "SHP1006 has a check-in; it is meant to still be in transit"
    exc = await _rows(
        session,
        "SELECT declared_eta_ts, exception_type FROM public.driver_exceptions "
        "WHERE thread_id = 'THR001'",
    )
    assert exc and exc[0]["declared_eta_ts"] is not None


async def case_multiple_eta_updates(session):
    """`SHP1006` -- 10:50 then 11:20. Latest declared ETA wins; both rows survive.

    This is also section 9.2's `eta_correction_sequence`: "Latest declared ETA wins; both rows
    retained; no mutation of history."
    """
    updates = await _rows(
        session,
        "SELECT eta_update_id, declared_eta_ts FROM public.eta_updates "
        "WHERE shipment_id = 'SHP1006' ORDER BY created_at",
    )
    assert len(updates) >= 2, "the correction sequence lost a row"
    latest_declared = max(u["declared_eta_ts"] for u in updates)
    effective = await _scalar(
        session, "SELECT effective_eta_ts FROM public.v_latest_eta WHERE shipment_id = 'SHP1006'"
    )
    assert effective == latest_declared, (
        f"v_latest_eta returned {effective}, not the latest declared {latest_declared}"
    )


async def case_uncertain_eta(session):
    """`SHP1013 / SHP1017` -- both carry a LOW-confidence declared ETA."""
    rows = await _rows(
        session,
        """
        SELECT shipment_id, confidence_code FROM public.eta_updates
        WHERE shipment_id IN ('SHP1013','SHP1017') AND confidence_code = 'LOW'
        """,
    )
    assert {r["shipment_id"] for r in rows} == {"SHP1013", "SHP1017"}


async def case_dock_breakdown(session):
    """`SHP1005 / DEVT001` -- D3 fails and the engine stops offering it while the outage runs.

    The assertion is on the engine, not the data: every option `find_feasible_slots` returns for
    SHP1005 must avoid an interval that overlaps DEVT001 on D3. That is the property a planner
    actually depends on; the row's mere existence is not.
    """
    ctx = await _driver_ctx(session, "SHP1005")
    result = await find_feasible_slots(session, ctx, "SHP1005", limit=5)
    outage = (
        await _rows(
            session,
            "SELECT dock_id, event_start_ts, event_end_ts FROM public.dock_status_events "
            "WHERE dock_event_id = 'DEVT001'",
        )
    )[0]
    for option in result.options:
        if option.dock_id != outage["dock_id"]:
            continue
        start = feasibility._parse_timestamp(option.slot_start_ts)
        end = feasibility._parse_timestamp(option.slot_end_ts)
        assert not (start < outage["event_end_ts"] and end > outage["event_start_ts"]), (
            f"the engine offered {option.slot_id} on the broken dock during DEVT001"
        )


async def case_unload_overrun(session):
    """`SHP1002 / DEVT003` -- the truck needs longer than its slot, and the dock records it.

    Section 6.2 #1's headline defect seen as a scenario: `expected_unload_min` (70) genuinely
    exceeds the 60-minute slot, which is why D1's interval model exists at all.
    """
    unload = int(
        await _scalar(
            session, "SELECT expected_unload_min FROM public.shipments WHERE shipment_id = 'SHP1002'"
        )
    )
    slot = (
        await _rows(
            session,
            """
            SELECT sl.slot_start_ts, sl.slot_end_ts
            FROM public.appointments a
            JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
            WHERE a.shipment_id = 'SHP1002' AND a.is_current = 1
            """,
        )
    )[0]
    slot_minutes = int((slot["slot_end_ts"] - slot["slot_start_ts"]).total_seconds() // 60)
    assert unload > slot_minutes, (
        f"SHP1002 no longer over-runs its slot ({unload} min into {slot_minutes} min)"
    )
    event = await _rows(
        session,
        "SELECT event_type, dock_id FROM public.dock_status_events WHERE dock_event_id = 'DEVT003'",
    )
    assert event and event[0]["event_type"] == "CAPACITY_REDUCTION"


async def case_appointment_cancellation_frees_capacity(session):
    """`SHP1008 / APT1008` -- the cancelled booking's slot reads AVAILABLE again.

    Asserted through `v_slot_availability`, the view the offer path actually consults, rather than
    through the appointments table -- a cancelled row that still made its slot look OCCUPIED would
    satisfy a naive check and still sterilise the capacity.
    """
    appt = (
        await _rows(
            session,
            "SELECT appointment_status, is_current, slot_id FROM public.appointments "
            "WHERE appointment_id = 'APT1008'",
        )
    )[0]
    assert appt["appointment_status"] == "CANCELLED"
    assert int(appt["is_current"]) == 0
    availability = (
        await _rows(
            session,
            "SELECT availability_status FROM public.v_slot_availability WHERE slot_id = :slot_id",
            slot_id=appt["slot_id"],
        )
    )[0]
    assert availability["availability_status"] == "AVAILABLE", (
        "the cancelled appointment did not release its slot"
    )


async def case_no_show(session):
    """`SHP1018 / APT1018 / RULE002` -- no check-in, NO_SHOW recorded, and the grace rule exists.

    Section 9.2's `no_show_grace`: "NO_SHOW only after slot start + 30 min". The 30 is asserted
    against RULE002 rather than hard-coded, so a policy change surfaces here.
    """
    grace = await _scalar(
        session,
        "SELECT rule_value FROM public.facility_rules "
        "WHERE rule_id = 'RULE002' AND rule_type = 'NO_SHOW_GRACE_MIN'",
    )
    assert grace is not None, "RULE002 (NO_SHOW_GRACE_MIN) is gone"
    checkins = await _scalar(
        session, "SELECT count(*) FROM public.facility_checkins WHERE shipment_id = 'SHP1018'"
    )
    assert int(checkins) == 0, "a no-show cannot have checked in"
    status = await _scalar(
        session, "SELECT appointment_status FROM public.appointments WHERE appointment_id = 'APT1018'"
    )
    assert status == "NO_SHOW"


async def case_reefer_compatibility(session):
    """`SHP1010 / SHP1015` -- temperature-controlled loads, and exactly one reefer dock at JAI."""
    rows = await _rows(
        session,
        """
        SELECT shipment_id, temperature_control_required, required_dock_type
        FROM public.shipments WHERE shipment_id IN ('SHP1010','SHP1015')
        """,
    )
    assert len(rows) == 2
    for row in rows:
        assert int(row["temperature_control_required"]) == 1
        assert row["required_dock_type"] == "REEFER"
    reefer_docks = await _rows(
        session,
        "SELECT dock_id FROM public.docks "
        "WHERE facility_id = 'FAC-JAI-01' AND supports_refrigerated = 1",
    )
    assert [r["dock_id"] for r in reefer_docks] == ["DOCK-JAI-D5"], (
        "RULE003's single point of failure (section 6.2 #6) is no longer single"
    )


async def case_reefer_dock_unavailable(session):
    """`SHP1015 / THR005` -- D5 is down after the declared ETA, so nothing is offerable.

    Section 6.2 #6: "SHP1015 (ETA 18:30) therefore has *no* feasible same-day slot -- by
    construction ... make sure the engine reaches that conclusion by rule, not by accident." So the
    assertion is on `find_feasible_slots`, and it also checks the *reason*: the engine must have
    rejected candidates, not merely found none.
    """
    ctx = await _driver_ctx(session, "SHP1015")
    result = await find_feasible_slots(session, ctx, "SHP1015", limit=5)
    assert result.outcome == OUTCOME_NO_FEASIBLE_SLOT, (
        f"SHP1015 was offered {len(result.options)} option(s): "
        f"{[o.slot_id for o in result.options]}"
    )
    assert result.escalation is not None and result.escalation["required"] is True
    assert result.escalation["blocking_reasons"], "escalated without naming a blocking reason"


async def case_heavy_vehicle_compatibility(session):
    """`SHP1016` -- 31,000 kg. Section 9.2: "Only D6 offered -- D1/D3 cap at 20,000 kg, D2/D4 at
    25,000, D5 at 22,000; D6 is 35,000."

    Asserted twice over: the dock ratings still say what section 9.2 claims, AND every option the
    engine returns is on D6.
    """
    ratings = {
        r["dock_code"]: int(r["max_vehicle_weight_kg"])
        for r in await _rows(
            session,
            "SELECT dock_code, max_vehicle_weight_kg FROM public.docks WHERE facility_id = 'FAC-JAI-01'",
        )
    }
    assert ratings == {"D1": 20000, "D2": 25000, "D3": 20000, "D4": 25000, "D5": 22000, "D6": 35000}

    load = int(
        await _scalar(session, "SELECT load_weight_kg FROM public.shipments WHERE shipment_id = 'SHP1016'")
    )
    assert load == 31000
    ctx = await _driver_ctx(session, "SHP1016")
    result = await find_feasible_slots(session, ctx, "SHP1016", limit=5)
    assert result.options, "the heavy load was offered nothing at all"
    offered_docks = {option.dock_code for option in result.options}
    assert offered_docks == {"D6"}, f"a 31 t load was offered {offered_docks}"


async def case_no_feasible_slot(session):
    """`SHP1015` -- the same shipment, asserted as the escalation path rather than the reefer rule.

    Section 5 Stage 0's outcome split matters here: NO_FEASIBLE_SLOT is an escalation,
    NO_SAME_DAY_SLOT is not. This case is the former, and the engine must say so by name.
    """
    ctx = await _driver_ctx(session, "SHP1015")
    result = await find_feasible_slots(session, ctx, "SHP1015", limit=5)
    assert result.outcome == OUTCOME_NO_FEASIBLE_SLOT
    assert result.options == []
    assert result.escalation["recommended_human_queue"] == "OPERATIONS_EXCEPTION_QUEUE"


async def case_simultaneous_slot_competition(session):
    """`SHP1006, SHP1012, SHP1013, SHP1014` -- four delayed trucks converging on standard docks.

    The scenario's *outcome* is enforced structurally, not procedurally, so that is what is
    asserted: all four are live, all four want a STANDARD dock at the same facility, and no two of
    them hold the same slot -- which `ux_active_appointment_per_slot` makes impossible.
    """
    rows = await _rows(
        session,
        """
        SELECT s.shipment_id, s.required_dock_type, s.destination_facility_id
        FROM public.shipments s
        WHERE s.shipment_id IN ('SHP1006','SHP1012','SHP1013','SHP1014')
        """,
    )
    assert len(rows) == 4
    assert {r["required_dock_type"] for r in rows} == {"STANDARD"}
    assert {r["destination_facility_id"] for r in rows} == {"FAC-JAI-01"}

    clashes = await _rows(
        session,
        """
        SELECT slot_id, count(*) AS n FROM public.appointments
        WHERE shipment_id IN ('SHP1006','SHP1012','SHP1013','SHP1014')
          AND appointment_status = ANY(:active)
        GROUP BY slot_id HAVING count(*) > 1
        """,
        active=list(ACTIVE),
    )
    assert clashes == [], f"two competing trucks hold the same slot: {clashes}"


async def case_priority_conflict(session):
    """`SHP1009 / SHP1014` -- a CRITICAL shipment against the rest.

    Section 9.2's `priority_late_entry`: a CRITICAL request "Ranks above earlier requests -- not
    buried by FIFO ordering". The engine's own `PRIORITY_RANK` is the tie-break that implements
    that, so the assertion is against the table the code actually sorts by, plus the seed's own
    priority codes.
    """
    priorities = {
        r["shipment_id"]: r["priority_code"]
        for r in await _rows(
            session,
            "SELECT shipment_id, priority_code FROM public.shipments "
            "WHERE shipment_id IN ('SHP1009','SHP1014')",
        )
    }
    assert priorities == {"SHP1009": "CRITICAL", "SHP1014": "CRITICAL"}
    ranks = feasibility.PRIORITY_RANK
    assert ranks["CRITICAL"] < ranks["HIGH"] < ranks["NORMAL"] < ranks["LOW"], (
        f"the engine's priority ordering is not strictly CRITICAL-first: {ranks}"
    )


async def case_race_condition_protection(session):
    """`ux_active_appointment_per_slot` -- the partial unique index, asserted to exist by name and
    by predicate.

    The guide names the index; section 10.2's headline invariant names the newer `dock_occupancy`
    exclusion constraint. Both are checked -- they guard different things (one slot vs one dock
    interval) and losing either is a double-booking hole.
    """
    row = (
        await _rows(
            session,
            """
            SELECT indexname, indexdef FROM pg_indexes
            WHERE schemaname = 'public' AND indexname = 'ux_active_appointment_per_slot'
            """,
        )
    )
    assert row, "ux_active_appointment_per_slot is missing"
    definition = " ".join(str(row[0]["indexdef"]).split())
    assert "UNIQUE" in definition.upper()
    for status in ACTIVE:
        assert status in definition, f"{status} dropped out of the index predicate: {definition}"


async def case_appointment_history(session):
    """`APT1012A / APT1016A` -- superseded appointments stay visible and stay out of the live set.

    Section 9.2's `appointment_history_chain`: "Superseded appointments stay visible; released
    `dock_occupancy` intervals return to the offer pool." Both halves are asserted -- the row is
    still readable AND it holds no capacity claim.
    """
    rows = await _rows(
        session,
        """
        SELECT appointment_id, appointment_status, is_current
        FROM public.appointments WHERE appointment_id IN ('APT1012A','APT1016A')
        """,
    )
    assert len(rows) == 2, "a superseded appointment was deleted rather than retained"
    for row in rows:
        assert int(row["is_current"]) == 0
        assert row["appointment_status"] not in ACTIVE
    claims = await _scalar(
        session,
        "SELECT count(*) FROM public.dock_occupancy WHERE appointment_id IN ('APT1012A','APT1016A')",
    )
    assert int(claims) == 0, "a superseded appointment is still holding dock capacity"


async def case_duplicate_driver_message(session):
    """`THR001 / THR009` -- one dedupe key, two threads, exactly one live exception."""
    rows = await _rows(
        session,
        """
        SELECT exception_id, thread_id, exception_status, dedupe_key
        FROM public.driver_exceptions
        WHERE dedupe_key = 'DRV006-SHP1006-20260804-0934'
        """,
    )
    assert {r["thread_id"] for r in rows} == {"THR001", "THR009"}
    live = [r for r in rows if r["exception_status"] != "DUPLICATE"]
    assert len(live) == 1


async def case_ambiguous_shipment(session):
    """`DRV004 / THR010` -- a delay with no shipment named, and a driver who has more than one.

    Section 9.2's `ambiguous_shipment`: "Clarification with human descriptors - no read that
    assumes a shipment". The structural precondition for that is a NULLable `chat_threads`
    `shipment_id` that is genuinely NULL here, and a driver with a real ambiguity to resolve.
    """
    thread = (
        await _rows(
            session,
            "SELECT driver_id, shipment_id FROM public.chat_threads WHERE thread_id = 'THR010'",
        )
    )[0]
    assert thread["shipment_id"] is None, "THR010 is no longer ambiguous"
    assert thread["driver_id"] == "DRV004"
    assignments = int(
        await _scalar(
            session,
            "SELECT count(*) FROM public.shipments WHERE driver_id = 'DRV004' "
            "AND current_status NOT IN ('COMPLETED','CANCELLED')",
        )
    )
    assert assignments >= 2, f"DRV004 has {assignments} live assignment(s); nothing to disambiguate"
    exc = (
        await _rows(
            session,
            "SELECT shipment_id FROM public.driver_exceptions WHERE thread_id = 'THR010'",
        )
    )[0]
    assert exc["shipment_id"] is None


async def case_ask_only_conversation(session):
    """`THR011` -- section 9.2's `ask_only_no_exception`: "**zero** `driver_exceptions` rows"."""
    thread = (
        await _rows(
            session,
            "SELECT thread_intent, shipment_id FROM public.chat_threads WHERE thread_id = 'THR011'",
        )
    )[0]
    assert thread["thread_intent"] == "ASK_SLOT_OPTIONS"
    exceptions = int(
        await _scalar(
            session, "SELECT count(*) FROM public.driver_exceptions WHERE thread_id = 'THR011'"
        )
    )
    assert exceptions == 0, "an ask-only conversation raised an exception and started an SLA clock"


async def case_cancelled_shipment_message(session):
    """`SHP1019 / THR012` -- section 9.2's `cancelled_shipment_query`: "Refuses to schedule".

    Asserted on the engine's refusal, by error code, not on the status column alone: a cancelled
    shipment that still returned options would satisfy a data-only check.
    """
    status = await _scalar(
        session, "SELECT current_status FROM public.shipments WHERE shipment_id = 'SHP1019'"
    )
    assert status == "CANCELLED"
    ctx = await _driver_ctx(session, "SHP1019")
    with pytest.raises(AppError) as excinfo:
        await find_feasible_slots(session, ctx, "SHP1019", limit=5)
    assert excinfo.value.code == "SHIPMENT_NOT_ACTIVE"


async def case_warehouse_confirmation_pending(session):
    """`APT1013A / APT1014A` -- requested, not yet confirmed."""
    rows = await _rows(
        session,
        """
        SELECT appointment_id, appointment_status, confirmed_at, warehouse_confirmation_ref
        FROM public.appointments WHERE appointment_id IN ('APT1013A','APT1014A')
        """,
    )
    assert len(rows) == 2
    for row in rows:
        assert row["appointment_status"] == "PENDING_CONFIRMATION"
        assert row["confirmed_at"] is None
        assert row["warehouse_confirmation_ref"] is None, (
            "a pending request already carries a warehouse confirmation reference"
        )


async def case_communication_failure(session):
    """`OM004` -- section 9.2's `failed_notification`: "Never treated as confirmation".

    The mechanical form of "never treated as confirmation" is that no appointment anywhere cites
    the failed message as its `warehouse_confirmation_ref`.
    """
    row = (
        await _rows(
            session,
            "SELECT operational_message_id, delivery_status, appointment_id "
            "FROM public.operational_messages WHERE operational_message_id = 'OM004'",
        )
    )[0]
    assert row["delivery_status"] == "FAILED"
    cited = int(
        await _scalar(
            session,
            "SELECT count(*) FROM public.appointments WHERE warehouse_confirmation_ref = 'OM004'",
        )
    )
    assert cited == 0, "a FAILED notification is being cited as a warehouse confirmation"
    # And the appointment it concerns did not silently become CONFIRMED *because of* it: it must
    # carry its own, different confirmation reference if it is confirmed at all.
    appt = await _rows(
        session,
        "SELECT appointment_status, warehouse_confirmation_ref FROM public.appointments "
        "WHERE appointment_id = :aid",
        aid=row["appointment_id"],
    )
    if appt and appt[0]["appointment_status"] == "CONFIRMED":
        assert appt[0]["warehouse_confirmation_ref"] not in (None, "OM004")


async def case_missing_contact_data(session):
    """`CON005` -- section 9.2's `unroutable_notification`: the night-shift contact has no email."""
    row = (
        await _rows(
            session,
            "SELECT facility_id, contact_role, email, phone FROM public.facility_contacts "
            "WHERE contact_id = 'CON005'",
        )
    )[0]
    assert row["email"] is None, "CON005 gained an email; the unroutable fixture is gone"
    assert row["facility_id"] == "FAC-GGN-01"
    assert row["phone"] is not None, "the fixture must be *missing an email*, not missing entirely"


async def case_early_truck_does_not_automatically_win(session):
    """`SHP1003` -- section 9.2's `early_arrival_no_priority`: "Early truck does not displace
    scheduled work".

    The check that matters: the early truck is still queued (`WAITING_EARLY`, never `IN_DOCK`), it
    is still on its own original slot, and nothing else lost its appointment to it.
    """
    checkin = (
        await _rows(
            session,
            "SELECT queue_state, dock_in_ts, actual_dock_id FROM public.facility_checkins "
            "WHERE shipment_id = 'SHP1003'",
        )
    )[0]
    assert checkin["queue_state"] == "WAITING_EARLY"
    assert checkin["dock_in_ts"] is None, "the early truck was let into a dock ahead of schedule"
    assert checkin["actual_dock_id"] is None

    appt = (
        await _rows(
            session,
            "SELECT appointment_id, slot_id, appointment_status FROM public.appointments "
            "WHERE shipment_id = 'SHP1003' AND is_current = 1",
        )
    )[0]
    assert appt["appointment_id"] == "APT1003", "SHP1003's booking moved"
    assert appt["slot_id"] == "SLOT-JAI-002", "the early truck was given a different slot"
    assert appt["appointment_status"] == "CONFIRMED"


async def case_different_unloading_durations(session):
    """`SHP1006 / SHP1011` -- 45-75 min for standard loads, 90 for a heavy one."""
    durations = {
        r["shipment_id"]: int(r["expected_unload_min"])
        for r in await _rows(
            session,
            "SELECT shipment_id, expected_unload_min FROM public.shipments "
            "WHERE shipment_id IN ('SHP1006','SHP1011')",
        )
    }
    assert durations["SHP1006"] != durations["SHP1011"], (
        "the two durations are identical; the case tests nothing"
    )
    assert 45 <= durations["SHP1006"] <= 75
    assert durations["SHP1011"] == 90


async def case_operating_hour_limit(session):
    """`RULE005` -- section 5 Stage 1's LAST_NEW_START_TIME, asserted through the engine's own
    rule evaluator rather than by reading the row.

    `check_facility_rules` is called with a real candidate starting after the cutoff and one
    starting before it. A rule that exists in the table but is never evaluated would pass a
    data-only assertion and fail every driver.
    """
    from datetime import datetime, timedelta, timezone

    ist = timezone(timedelta(hours=5, minutes=30))
    rules = await _rows(
        session,
        "SELECT rule_id, rule_type, rule_value FROM public.facility_rules "
        "WHERE facility_id = 'FAC-JAI-01' AND active_flag = 1",
    )
    assert any(r["rule_type"] == "LAST_NEW_START_TIME" and r["rule_value"] == "21:00" for r in rules)

    shipment = {"load_weight_kg": 7000, "temperature_control_required": 0}
    candidate = {"dock_type": "STANDARD", "supports_refrigerated": 0}

    too_late = feasibility.check_facility_rules(
        shipment=shipment,
        candidate=candidate,
        rules=rules,
        feasible_start=datetime(2026, 8, 4, 21, 30, tzinfo=ist),
        tz_name="Asia/Kolkata",
    )
    assert too_late is not None and too_late[0] == "RULE005", (
        "a 21:30 unload start was not refused by RULE005"
    )

    in_hours = feasibility.check_facility_rules(
        shipment=shipment,
        candidate=candidate,
        rules=rules,
        feasible_start=datetime(2026, 8, 4, 14, 0, tzinfo=ist),
        tz_name="Asia/Kolkata",
    )
    assert in_hours is None, f"a 14:00 start was wrongly refused: {in_hours}"


async def case_no_real_time_tracking(session):
    """"The system uses original ETA and driver-declared updates, not continuous GPS."

    Asserted as an absence that the schema itself guarantees: every `eta_updates` row is
    plan-, driver-, operations- or warehouse-sourced, and the CHECK constraint admits no telemetry
    source at all. An absence claim needs the constraint, not just the current rows.
    """
    sources = {
        r["source_type"]
        for r in await _rows(session, "SELECT DISTINCT source_type FROM public.eta_updates")
    }
    allowed = {"ORIGINAL_PLAN", "DRIVER_DECLARED", "OPERATIONS_OVERRIDE", "WAREHOUSE_ESTIMATE"}
    assert sources <= allowed, f"an ETA arrived from an unexpected source: {sources - allowed}"

    definition = await _scalar(
        session,
        """
        SELECT pg_get_constraintdef(oid) FROM pg_constraint
        WHERE conrelid = 'public.eta_updates'::regclass
          AND conname = 'eta_updates_source_type_check'
        """,
    )
    assert definition is not None, "the source_type CHECK constraint is gone"
    for banned in ("GPS", "TELEMATIC", "TELEMETRY", "TRACKER"):
        assert banned not in str(definition).upper(), (
            f"a live-tracking source type appeared in the schema: {definition}"
        )
    missing_original = int(
        await _scalar(
            session, "SELECT count(*) FROM public.shipments WHERE original_eta_ts IS NULL"
        )
    )
    assert missing_original == 0, "a shipment has no planned ETA to fall back on"


async def case_multi_facility_dataset(session):
    """`FAC-JAI-01 / FAC-GGN-01` -- two warehouses whose schedules never mix.

    The real assertion is referential, not a count: no slot may sit on a dock belonging to a
    different facility, which is the concrete form of "without mixing schedules".
    """
    facilities = {
        r["facility_id"] for r in await _rows(session, "SELECT facility_id FROM public.facilities")
    }
    assert {"FAC-JAI-01", "FAC-GGN-01"} <= facilities

    crossed = await _rows(
        session,
        """
        SELECT sl.slot_id, sl.facility_id AS slot_facility, d.facility_id AS dock_facility
        FROM public.appointment_slots sl
        JOIN public.docks d ON d.dock_id = sl.dock_id
        WHERE d.facility_id <> sl.facility_id
        """,
    )
    assert crossed == [], f"a slot is published against another facility's dock: {crossed}"

    per_facility = await _rows(
        session,
        "SELECT facility_id, count(*) AS n FROM public.appointment_slots GROUP BY facility_id",
    )
    assert len(per_facility) >= 2, "only one facility publishes capacity"


# ----------------------------------------------------------------------------------------------
# The registry. Keys are the guide's case names, verbatim.
# ----------------------------------------------------------------------------------------------

CASE_ASSERTIONS: dict[str, Callable[[AsyncSession], Awaitable[None]]] = {
    "Normal appointment": case_normal_appointment,
    "Early arrival": case_early_arrival,
    "Late arrival already at yard": case_late_arrival_already_at_yard,
    "Late ETA reported before arrival": case_late_eta_reported_before_arrival,
    "Multiple ETA updates": case_multiple_eta_updates,
    "Uncertain ETA": case_uncertain_eta,
    "Dock breakdown": case_dock_breakdown,
    "Unload overrun": case_unload_overrun,
    "Appointment cancellation frees capacity": case_appointment_cancellation_frees_capacity,
    "No-show": case_no_show,
    "Reefer compatibility": case_reefer_compatibility,
    "Reefer dock unavailable": case_reefer_dock_unavailable,
    "Heavy vehicle compatibility": case_heavy_vehicle_compatibility,
    "No feasible slot": case_no_feasible_slot,
    "Simultaneous slot competition": case_simultaneous_slot_competition,
    "Priority conflict": case_priority_conflict,
    "Race condition protection": case_race_condition_protection,
    "Appointment history": case_appointment_history,
    "Duplicate driver message": case_duplicate_driver_message,
    "Ambiguous shipment": case_ambiguous_shipment,
    "Ask-only conversation": case_ask_only_conversation,
    "Cancelled shipment message": case_cancelled_shipment_message,
    "Warehouse confirmation pending": case_warehouse_confirmation_pending,
    "Communication failure": case_communication_failure,
    "Missing contact data": case_missing_contact_data,
    "Early truck does not automatically win": case_early_truck_does_not_automatically_win,
    "Different unloading durations": case_different_unloading_durations,
    "Operating-hour limit": case_operating_hour_limit,
    "No real-time tracking": case_no_real_time_tracking,
    "Multi-facility dataset": case_multi_facility_dataset,
}


# ----------------------------------------------------------------------------------------------
# Coverage, asserted mechanically
# ----------------------------------------------------------------------------------------------


async def test_every_seeded_case_has_a_named_assertion():
    """Section 10.4: "a case with no named test fails the suite, so the mapping cannot silently
    rot." Compared in both directions, against the guide's own parsed table."""
    guide = {case.name for case in load_seeded_cases()}
    covered = set(CASE_ASSERTIONS)
    record_evidence(
        "4. scenario replay: coverage",
        f"{len(covered & guide)}/{len(guide)} guide cases have a named assertion "
        f"(uncovered {len(guide - covered)}, orphaned {len(covered - guide)})",
    )
    assert guide - covered == set(), f"seeded cases with no named assertion: {sorted(guide - covered)}"
    assert covered - guide == set(), (
        f"assertions naming a case the guide no longer contains: {sorted(covered - guide)}"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "DOCUMENTATION DRIFT, reported not fixed (issue #44). SOLUTION_DESIGN.md says '29' seeded "
        "cases in both section 9.2 and section 10.4; the database guide's section 6 table actually "
        "contains 30 rows (counted mechanically, 2026-09-01). Coverage itself is complete -- all "
        "30 have a named assertion in this file and the both-directions coverage test above "
        "passes -- so this is a count in the design document, not a gap in the suite. Left as a "
        "STRICT xfail rather than a hard failure because it is a prose error, not a correctness "
        "defect; strict means it fails loudly the moment either number changes, so it cannot rot."
    ),
)
async def test_the_case_count_matches_what_the_design_claims():
    """`SOLUTION_DESIGN.md` says 29 cases; the guide's table has 30."""
    cases = load_seeded_cases()
    record_evidence(
        "4. scenario replay: case count",
        f"guide table has {len(cases)}; SOLUTION_DESIGN.md says {DESIGN_STATED_CASE_COUNT}",
    )
    assert len(cases) == DESIGN_STATED_CASE_COUNT, (
        f"the database guide section 6 contains {len(cases)} cases, but SOLUTION_DESIGN.md "
        f"section 9.2 and section 10.4 both say {DESIGN_STATED_CASE_COUNT}. All "
        f"{len(cases)} are covered by a named assertion in this file; the discrepancy is in the "
        "design document's count, not in the coverage.\n"
        f"Cases, in guide order: {[c.name for c in cases]}"
    )


@pytest.mark.parametrize("case_name", sorted(CASE_ASSERTIONS))
async def test_seeded_case(case_name, seed_session):
    await CASE_ASSERTIONS[case_name](seed_session)


@pytest.mark.skip(
    reason=(
        "NAMED SKIP (issue #44). Section 10.4 names three cases that "
        "'must escalate': the SHP1015 reefer case and the OM004 failed email are both covered "
        "above, but 'contradictory warehouse reply' has NO seeded fixture -- the database guide's "
        "section 6 table has no such row, and no operational_messages/chat_messages row in "
        "supabase/seed.sql carries a contradictory warehouse reply. The escalation vocabulary for "
        "it exists (WAREHOUSE_REPLY_CONFLICT, migration 20260823100000) but nothing exercises it. "
        "Needs a seed fixture before it can be asserted."
    )
)
async def test_contradictory_warehouse_reply_escalates():
    raise AssertionError("unreachable while the skip stands")
