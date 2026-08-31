"""Gate and yard writes -- SOLUTION_DESIGN.md section 7.5.2, FR-GATE-004 .. FR-GATE-008.

Before this module the gate/yard catalog had exactly one implemented capability, the *read*
`driver_reads.get_gate_and_queue_status` (driver_reads.py:294). Every write in section 7.5.2 was
absent, which is why `facility_checkins.gate_in_ts` -- the sequencer's release-time input and the
only source of *actual* arrival truth -- could never be populated by the product itself.

Three structural notes for anyone editing this file:

1. **Bind types are not interchangeable.** After E1.1's conversion
   (supabase/migrations/20260823060000_d1_correctness_bedrock.sql) every `facility_checkins`
   timestamp column here is `timestamptz`, so asyncpg requires a real `datetime` object; handing it
   an `.isoformat()` string raises `asyncpg.exceptions.DataError`. `audit_logs.created_at` is the
   mirror image -- still `text` -- and takes the ISO string. Same two-names-from-one-instant pattern
   as `allocation.py`'s note above `_as_of`. This exact class of bug already broke production once
   (issue #47); do not "simplify" it away.

2. **The write target is `facility_checkins`, not an event stream.** Section 7.5.2 says these tools
   should write an append-only `checkin_events` stream with `facility_checkins` as the derived
   current-state view (section 6.2 #4/#11). No such table exists in the live database (verified
   read-only 2026-08-23: `information_schema.tables` has no `checkin_events`), and issue #30's own
   rollback note scopes this work to "new write tools against existing tables". So each write
   mutates the single UNIQUE-per-shipment `facility_checkins` row and leaves an `audit_logs` row
   behind as the append-only trace. Introducing the real stream is a schema change and belongs in
   its own migration-bearing issue.

3. **Scope is derived, never accepted.** No function here takes a `facility_id` argument (M15 /
   NFR-019). The facility comes from the shipment's `destination_facility_id` and is then checked
   with `repositories.scope.assert_gate_write_scope` -- the gate-specific predicate (issue #79),
   not the shared `assert_facility_write_scope` these writes used before `GATE_OFFICER` existed.
   The two differ by exactly one role, and that separation is the point: see
   `assert_gate_write_scope`'s docstring.

4. **`officer_name` is a label, not an identity.** See `OFFICER_ATTRIBUTION_KEY` below before
   touching it. It is unverifiable free text and it decides nothing.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.repositories.scope import assert_gate_write_scope
from app.services.idempotency import lookup_idempotency, payload_hash, store_idempotency
from app.services.ids import new_id

ACTIVE_APPOINTMENT_STATUSES = ("PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS")

# `facility_checkins.queue_state` CHECK constraint, read live 2026-08-23. Kept as a constant so an
# INVALID_TRANSITION is raised by this module rather than surfacing as a raw CheckViolation.
QUEUE_STATES = (
    "NOT_QUEUED",
    "WAITING_EARLY",
    "WAITING_LATE",
    "WAITING_DOCK_UNAVAILABLE",
    "CALLED_TO_DOCK",
    "IN_DOCK",
    "COMPLETED",
)
WAITING_STATES = frozenset({"WAITING_EARLY", "WAITING_LATE", "WAITING_DOCK_UNAVAILABLE"})

# The server-side state machine section 7.5.2 requires ("enforced server-side, not by the kiosk").
# Derived from UI-UX/04-gate-yard-kiosk/screens.md section 3's state -> action table, restricted to
# the transitions `update_queue_state` itself owns: entering a dock (IN_DOCK), finishing an unload
# (COMPLETED) and gating in are owned by their own tools, so they are deliberately absent here and
# an attempt to reach them through this tool is an INVALID_TRANSITION, not a shortcut.
#
# CALLED_TO_DOCK -> WAITING_* is present because edge-cases.md #4 requires it: after DOCK_OCCUPIED
# "the officer's next kiosk action is naturally 'Call to dock' again", and that button is only
# offered from a waiting state.
QUEUE_TRANSITIONS: dict[str, frozenset[str]] = {
    "NOT_QUEUED": frozenset(WAITING_STATES),
    "WAITING_EARLY": frozenset(WAITING_STATES | {"CALLED_TO_DOCK"}) - {"WAITING_EARLY"},
    "WAITING_LATE": frozenset(WAITING_STATES | {"CALLED_TO_DOCK"}) - {"WAITING_LATE"},
    "WAITING_DOCK_UNAVAILABLE": frozenset(WAITING_STATES | {"CALLED_TO_DOCK"})
    - {"WAITING_DOCK_UNAVAILABLE"},
    "CALLED_TO_DOCK": frozenset(WAITING_STATES),
    # Terminal for this tool. IN_DOCK advances via record_unload_start_end; COMPLETED via
    # record_gate_out. Neither is reachable or leaveable through update_queue_state.
    "IN_DOCK": frozenset(),
    "COMPLETED": frozenset(),
}

# EARLY / ON_TIME boundary, in minutes before the booked slot start.
#
# **Calibrated, not documented.** Section 7.5.2 says `arrival_state` is "derived from the
# appointment and RULE001's 60-minute early limit" but never states the EARLY/ON_TIME boundary, and
# no seeded rule carries one. The five Layer A check-ins are the only ground truth, read live
# 2026-08-23 (minutes of gate_in relative to slot_start):
#     CHK1001 -25 EARLY · CHK1002 -2 ON_TIME · CHK1003 -40 EARLY · CHK1004 +25 LATE · CHK1005 +5 LATE
# So the boundary sits somewhere in (2, 25] and LATE begins the moment the slot start passes. 15 is
# the round value inside that interval. Note what this rules out: `facilities.checkin_grace_min` is
# 30 at FAC-JAI-01, which would have made CHK1001's -25 ON_TIME, so the grace column is *not* the
# boundary despite looking like it. RULE001's 60 is the *permitted* earliness limit, surfaced
# separately as `beyond_early_limit`, not the ON_TIME window.
ON_TIME_WINDOW_MIN = 15

# Fallback when a facility has no CHECKIN_EARLY_LIMIT_MIN rule. Only FAC-JAI-01 has RULE001 live
# (verified 2026-08-23), so the other five facilities would otherwise have no limit at all.
DEFAULT_EARLY_LIMIT_MIN = 60

AUDIT_ENTITY = "facility_checkins"

# ---------------------------------------------------------------------------------------------
# Officer attribution -- U111 / FR-GATE-001, issue #68.
#
# READ THIS BEFORE USING `officer_name` FOR ANYTHING.
#
# The kiosk is a shared device with no idle timeout (UI-UX/00-foundations/auth-and-scoping.md,
# "Session expiry"). Its Supabase Auth session is a GATE_OFFICER *device* account (issue #79), so
# `ctx.user_id` answers "which kiosk wrote this", never "which human was standing at it". U111's
# model is that the human types their name once per shift (Flow 0) and that label rides on every
# event of that shift -- "an attribute of the write, not as a re-asked credential"
# (04-gate-yard-kiosk/components.md section 1).
#
# **The label is client-supplied and unverifiable. Nobody proves it.** Somebody types a string at
# a booth. That is fine for attribution and disqualifying for anything else:
#
#   * AUTHORIZATION is `assert_gate_write_scope(ctx, facility_id)` in `_shipment_in_scope`, against
#     the verified token, and nothing else. No function in this module passes `officer_name` to a
#     scope check, a permission check, a row filter or a lookup key, and none ever should. A test
#     (`test_officer_name_cannot_influence_the_scope_decision`) fails if that changes.
#   * It is never written to `audit_logs.user_id`, which is a NOT NULL FK to `users` and means
#     "the authenticated principal". The label goes in `new_value_json` under its own key so the
#     verified column and the unverified label sit side by side and cannot be confused.
#   * `verified: False` is stored on every row rather than left for the reader to infer. OWASP's
#     *Logging Cheat Sheet* (cheatsheetseries.owasp.org, read 2026-08-31): event data from another
#     trust zone "may be missing, modified, forged, replayed and could be malicious -- it must
#     always be treated as untrusted data". `source` is stored for the same reason and anticipates
#     `edge-cases.md` #8's admin-console correction path, which would write a different source.
#
# **Absence is legal and must never cost an event.** A kiosk mid-shift-change, a device reloaded
# before Flow 0, an offline queue replayed later -- all can produce a write with no name. Every
# function here accepts `officer_name=None`, records `officer_name: null`, and proceeds. There is
# deliberately no fallback: `ctx.full_name` is the *device account's* name, and substituting it
# would invent an attribution nobody made. An event nobody signed is recorded as an event nobody
# signed. Historical rows written before this shipped carry no `officer_attribution` key at all,
# which is the honest distinction between "unnamed" and "predates naming" -- do not backfill them.
# ---------------------------------------------------------------------------------------------
OFFICER_ATTRIBUTION_KEY = "officer_attribution"

# Storage bound, applied by truncation rather than by rejection -- see `normalise_officer_name`.
OFFICER_NAME_MAX_LEN = 120

_OFFICER_NAME_WHITESPACE = re.compile(r"\s+")


def _officer_attribution(officer_name: str | None) -> dict[str, Any]:
    """The one shape an officer label is ever recorded in. Built here so no call site can vary it."""
    return {
        "officer_name": officer_name,
        "verified": False,
        "source": "KIOSK_SHIFT_SESSION",
    }


def normalise_officer_name(raw: str | None) -> str | None:
    """Clean a shift label for storage. **Never raises, never refuses.**

    Sanitising rather than validating is the deliberate choice, and it follows from the ordering of
    the requirements: FR-GATE-001 (stamp the officer) may not be allowed to defeat FR-GATE-004..008
    (record the event). The label is replayed on *every* write of a shift, so a validation rule that
    can reject it would not lose one arrival -- it would lose the whole shift's arrivals. There is
    therefore no `max_length` on the router's body field either; this function is the single
    authority and it truncates.

    Control characters are mapped to spaces before whitespace is collapsed, per OWASP's *Logging
    Cheat Sheet*: "Perform sanitization on all event data to prevent log injection attacks e.g.
    carriage return (CR), line feed (LF) and delimiter characters" (read 2026-08-31). Mapped to a
    space rather than deleted so a smuggled newline cannot silently join two words into one name.
    Structural injection into the record itself is separately impossible -- `_audit` writes through
    `json.dumps` into a bound parameter, never string concatenation -- but the stored value is read
    back by the admin audit console (FR-ADM-008), so it is cleaned at the point of writing.

    An empty or whitespace-only name normalises to `None`, which is the same state as "no name was
    sent": both mean nobody is attributable, and inventing a distinction between them would be
    fiction.
    """
    if raw is None:
        return None
    mapped = "".join(ch if ch.isprintable() else " " for ch in raw)
    cleaned = _OFFICER_NAME_WHITESPACE.sub(" ", mapped).strip()
    if not cleaned:
        return None
    # Truncation is echoed back on `GateEventResult.officer_name`, so it is visible to the kiosk
    # rather than a silent difference between what was typed and what was stored.
    return cleaned[:OFFICER_NAME_MAX_LEN].rstrip()


class GateEventResult(BaseModel):
    """Typed outcome for every section 7.5.2 write (principle 2 of section 7.5: never prose)."""

    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    code: str
    shipment_id: str
    facility_id: str
    checkin_id: str | None = None
    queue_state: str | None = None
    queue_position: int | None = None
    arrival_state: str | None = None
    actual_dock_id: str | None = None
    appointment_id: str | None = None
    # record_gate_in
    gate_in_ts: datetime | None = None
    minutes_from_slot_start: float | None = None
    early_limit_min: int | None = None
    beyond_early_limit: bool | None = None
    # record_dock_in
    expected_dock_id: str | None = None
    occupying_shipment_id: str | None = None
    # record_unload_start_end
    phase: str | None = None
    unload_start_ts: datetime | None = None
    unload_end_ts: datetime | None = None
    actual_unload_min: float | None = None
    expected_unload_min: int | None = None
    overrun_min: float | None = None
    # record_gate_out
    gate_out_ts: datetime | None = None
    dwell_min: float | None = None
    idempotency_key: str | None = None
    idempotent_replay: bool = False
    # The normalised shift label this request carried and, where an event was written, the one
    # recorded on it (U111 / issue #68). Echoed so truncation or whitespace-collapsing is visible to
    # the kiosk instead of being a silent difference. **Not proof of anything** -- see
    # OFFICER_ATTRIBUTION_KEY. On an idempotent replay this is the *first* caller's label, because
    # that is the one actually on the stored event; re-attributing a recorded fact to whoever
    # retried it would be a fabrication.
    officer_name: str | None = None


class UnloadPhase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: str = Field(pattern="^(START|END)$")
    ts: datetime | None = None


def _as_of() -> str:
    """ISO string for the response model only -- never bind this into a timestamptz parameter."""
    return datetime.now(timezone.utc).isoformat()


def _coerce_ts(ts: datetime | None) -> datetime:
    """Normalise a caller-supplied event time to an aware UTC datetime.

    A kiosk may post a local wall time without an offset; storing that as if it were UTC silently
    shifts every dwell and overrun calculation downstream, so a naive value is treated as UTC
    explicitly here rather than left to asyncpg's default.
    """
    if ts is None:
        return datetime.now(timezone.utc)
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


async def _shipment_in_scope(
    session: AsyncSession, ctx: ExecutionContext, shipment_id: str
) -> dict[str, Any]:
    """Load the shipment and prove the caller may write against its facility.

    The facility is read off the shipment, never off the request -- section 7.5's principle 1.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT shipment_id, destination_facility_id AS facility_id, driver_id,
                       expected_unload_min, current_status
                FROM public.shipments
                WHERE shipment_id = :shipment_id
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    if row is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    assert_gate_write_scope(ctx, str(row["facility_id"]))
    return dict(row)


async def _active_appointment(session: AsyncSession, shipment_id: str) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.appointment_status, sl.slot_id, sl.dock_id,
                       sl.slot_start_ts, sl.slot_end_ts, d.dock_code
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                JOIN public.docks d ON d.dock_id = sl.dock_id
                WHERE a.shipment_id = :shipment_id
                  AND a.is_current = 1
                  AND a.appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                ORDER BY sl.slot_start_ts ASC
                LIMIT 1
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _locked_checkin(session: AsyncSession, shipment_id: str) -> dict[str, Any] | None:
    """The truck's current-state row, locked.

    `FOR UPDATE` is what makes edge-cases.md #5 (two devices racing the same truck) resolve as a
    clean INVALID_TRANSITION rather than a lost update: the second transaction blocks, then re-reads
    the row the winner left behind (PostgreSQL 13.2.1, READ COMMITTED).
    """
    row = (
        await session.execute(
            text(
                """
                SELECT checkin_id, shipment_id, facility_id, gate_in_ts, yard_queue_enter_ts,
                       dock_in_ts, unload_start_ts, unload_end_ts, gate_out_ts, arrival_state,
                       queue_state, queue_position, actual_dock_id, notes, updated_at
                FROM public.facility_checkins
                WHERE shipment_id = :shipment_id
                FOR UPDATE
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _early_limit_min(session: AsyncSession, facility_id: str) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT rule_value
                FROM public.facility_rules
                WHERE facility_id = :facility_id
                  AND rule_type = 'CHECKIN_EARLY_LIMIT_MIN'
                  AND active_flag = 1
                LIMIT 1
                """
            ),
            {"facility_id": facility_id},
        )
    ).mappings().first()
    if row is None:
        return DEFAULT_EARLY_LIMIT_MIN
    try:
        return int(str(row["rule_value"]).strip())
    except (TypeError, ValueError):
        return DEFAULT_EARLY_LIMIT_MIN


def classify_arrival(minutes_from_slot_start: float) -> str:
    """EARLY / ON_TIME / LATE from signed minutes relative to the booked slot start.

    Pure and exported so the boundary is unit-testable against the five Layer A rows directly --
    see ON_TIME_WINDOW_MIN for the calibration those rows produced.
    """
    if minutes_from_slot_start > 0:
        return "LATE"
    if minutes_from_slot_start >= -ON_TIME_WINDOW_MIN:
        return "ON_TIME"
    return "EARLY"


async def _audit(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    entity_id: str,
    action_type: str,
    old_value: dict[str, Any],
    new_value: dict[str, Any],
    officer_name: str | None,
    now_iso: str,
) -> None:
    """Append-only trace for one gate/yard event.

    `action_type` is restricted to the live `audit_logs_action_type_check` enum (read 2026-08-23),
    which has no gate-specific verbs -- so gate events record as CREATE/UPDATE and carry their real
    verb in `new_value_json.event`. Widening that CHECK would be a migration, out of scope here.

    `officer_name` is **keyword-only and has no default, deliberately** (issue #68): the compiler,
    not a reviewer, is what stops a seventh gate event being added without U111's stamp. Passing
    `None` is a legal and meaningful answer -- it records that nobody was named -- but it has to be
    passed. The attribution is merged in here rather than at the seven call sites so every gate
    event carries exactly one shape, under one key, and none of them can spell it differently or
    flatten it in among the entity's own field deltas.

    Why `new_value_json` and not a column: `audit_logs` has no attribution column, this table's
    `user_id` is a NOT NULL FK to `users` and already means something else, and `new_value_json` is
    already this module's established home for per-event detail the fixed schema has no column for
    (`"event": "GATE_IN"`, `"deviation"`, `"occupying_shipment_id"`). So U111 costs no migration.
    """
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id,
              old_value_json, new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :user_id, :action_type, :entity_name, :entity_id,
              :old_value_json, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"),
            "user_id": ctx.user_id,
            "action_type": action_type,
            "entity_name": AUDIT_ENTITY,
            "entity_id": entity_id,
            "old_value_json": json.dumps(old_value, default=str),
            "new_value_json": json.dumps(
                {**new_value, OFFICER_ATTRIBUTION_KEY: _officer_attribution(officer_name)},
                default=str,
            ),
            "created_at": now_iso,
        },
    )


async def _project_shipment_status(session: AsyncSession, shipment_id: str, status: str) -> None:
    """Keep `shipments.current_status` consistent with the check-in it was just derived from.

    Section 6.2 #11 records the defect this closes: `shipments.current_status` and
    `facility_checkins.queue_state` both carry WAITING/IN_DOCK with no stated precedence, so "is
    this truck in a dock?" has two answers that can disagree. The stated resolution is that the
    check-in stream is authoritative and `current_status` becomes a *derived projection*. Until a
    real derived view exists, the projection is written here, inside the same transaction as the
    event it projects -- one writer, never two independent ones.
    """
    await session.execute(
        text(
            """
            UPDATE public.shipments
            SET current_status = :status, updated_at = :updated_at
            WHERE shipment_id = :shipment_id
            """
        ),
        {"status": status, "updated_at": datetime.now(timezone.utc), "shipment_id": shipment_id},
    )


async def record_gate_in(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    ts: datetime | None,
    idempotency_key: str,
    officer_name: str | None = None,
) -> GateEventResult:
    """FR-GATE-004 / section 7.5.2 `record_gate_in`.

    Returns GATE_IN_RECORDED + computed `arrival_state`, or ALREADY_CHECKED_IN / NO_ACTIVE_APPOINTMENT.
    `Idempotency-Key` is required because section 7.5.2 names it on this tool specifically (the other
    four gate tools do not carry one in the catalog, and none is invented for them here).

    `officer_name` (FR-GATE-001) defaults to `None` because "nobody was named" is a designed, legal
    outcome, not an oversight -- see OFFICER_ATTRIBUTION_KEY. It authorises nothing.
    """
    route = f"POST /api/v1/gate/shipments/{shipment_id}/gate-in"
    officer = normalise_officer_name(officer_name)
    event_ts = _coerce_ts(ts)
    # `officer` is deliberately NOT in the request hash. The hash exists to catch "same key, genuinely
    # different command", and the shift label is neither part of the command's identity nor of its
    # effect -- the truck, the time and the facility are. Including it would turn the exact case a
    # kiosk produces at a shift boundary (officer A taps, the network drops, officer B retries the
    # queued key) into a hard IDEMPOTENCY_PAYLOAD_MISMATCH that loses a real arrival, which is the one
    # outcome this whole surface is built to prevent. The replay instead returns the stored response,
    # so the event keeps officer A's label -- the honest answer, since officer A is who wrote it.
    req_hash = payload_hash({"shipment_id": shipment_id, "ts": event_ts})
    replay = await lookup_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if replay is not None:
        return GateEventResult.model_validate({**replay["response"], "idempotent_replay": True})

    shipment = await _shipment_in_scope(session, ctx, shipment_id)
    facility_id = str(shipment["facility_id"])

    appointment = await _active_appointment(session, shipment_id)
    if appointment is None:
        # edge-cases.md #2: a genuine walk-in or an upstream data problem. Nothing is written --
        # a check-in row with no appointment has no arrival_state to compute and would strand the
        # truck in a state the kiosk has no action for.
        result = GateEventResult(
            as_of=_as_of(),
            code="NO_ACTIVE_APPOINTMENT",
            shipment_id=shipment_id,
            facility_id=facility_id,
            idempotency_key=idempotency_key,
            officer_name=officer,
        )
        await store_idempotency(
            session, key=idempotency_key, user_id=ctx.user_id, route=route,
            request_hash=req_hash, response=result.model_dump(), status_code=409,
        )
        await session.commit()
        return result

    existing = await _locked_checkin(session, shipment_id)
    if existing is not None and existing["gate_in_ts"] is not None:
        result = GateEventResult(
            as_of=_as_of(),
            code="ALREADY_CHECKED_IN",
            shipment_id=shipment_id,
            facility_id=facility_id,
            checkin_id=str(existing["checkin_id"]),
            gate_in_ts=existing["gate_in_ts"],
            arrival_state=existing["arrival_state"],
            queue_state=existing["queue_state"],
            queue_position=existing["queue_position"],
            appointment_id=str(appointment["appointment_id"]),
            idempotency_key=idempotency_key,
            officer_name=officer,
        )
        await store_idempotency(
            session, key=idempotency_key, user_id=ctx.user_id, route=route,
            request_hash=req_hash, response=result.model_dump(), status_code=409,
        )
        await session.commit()
        return result

    slot_start: datetime = appointment["slot_start_ts"]
    minutes_from_slot_start = (event_ts - slot_start).total_seconds() / 60.0
    arrival_state = classify_arrival(minutes_from_slot_start)
    early_limit = await _early_limit_min(session, facility_id)
    beyond_early_limit = minutes_from_slot_start < -float(early_limit)
    # A truck that arrived after its slot start is waiting *late*; anything at or before it is
    # waiting for a slot that has not opened yet. Matches the seeded pairs exactly (CHK1003
    # EARLY/WAITING_EARLY, CHK1004 LATE/WAITING_LATE) and gives every gated-in truck a state the
    # screens.md section 3 table has a next action for.
    queue_state = "WAITING_LATE" if minutes_from_slot_start > 0 else "WAITING_EARLY"

    checkin_id = str(existing["checkin_id"]) if existing else new_id("CHK")
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    if existing is None:
        await session.execute(
            text(
                """
                INSERT INTO public.facility_checkins (
                  checkin_id, shipment_id, facility_id, gate_in_ts, yard_queue_enter_ts,
                  arrival_state, queue_state, updated_at
                ) VALUES (
                  :checkin_id, :shipment_id, :facility_id, :gate_in_ts, :gate_in_ts,
                  :arrival_state, :queue_state, :updated_at
                )
                """
            ),
            {
                "checkin_id": checkin_id, "shipment_id": shipment_id, "facility_id": facility_id,
                "gate_in_ts": event_ts, "arrival_state": arrival_state,
                "queue_state": queue_state, "updated_at": now,
            },
        )
    else:
        await session.execute(
            text(
                """
                UPDATE public.facility_checkins
                SET gate_in_ts = :gate_in_ts, yard_queue_enter_ts = :gate_in_ts,
                    arrival_state = :arrival_state, queue_state = :queue_state, updated_at = :updated_at
                WHERE checkin_id = :checkin_id
                """
            ),
            {
                "checkin_id": checkin_id, "gate_in_ts": event_ts, "arrival_state": arrival_state,
                "queue_state": queue_state, "updated_at": now,
            },
        )

    await _project_shipment_status(session, shipment_id, "AT_GATE")
    await _audit(
        session, ctx, entity_id=checkin_id, action_type="CREATE",
        old_value={"queue_state": existing["queue_state"] if existing else None},
        new_value={
            "event": "GATE_IN", "gate_in_ts": event_ts, "arrival_state": arrival_state,
            "queue_state": queue_state, "appointment_id": appointment["appointment_id"],
        },
        officer_name=officer,
        now_iso=now_iso,
    )

    result = GateEventResult(
        as_of=_as_of(), code="GATE_IN_RECORDED", shipment_id=shipment_id, facility_id=facility_id,
        checkin_id=checkin_id, gate_in_ts=event_ts, arrival_state=arrival_state,
        queue_state=queue_state, appointment_id=str(appointment["appointment_id"]),
        expected_dock_id=str(appointment["dock_id"]),
        minutes_from_slot_start=round(minutes_from_slot_start, 2),
        early_limit_min=early_limit, beyond_early_limit=beyond_early_limit,
        idempotency_key=idempotency_key, officer_name=officer,
    )
    await store_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route,
        request_hash=req_hash, response=result.model_dump(),
    )
    await session.commit()
    return result


async def update_queue_state(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    queue_state: str,
    queue_position: int | None = None,
    officer_name: str | None = None,
) -> GateEventResult:
    """FR-GATE-005 / section 7.5.2 `update_queue_state`.

    Call-to-dock is this tool targeting CALLED_TO_DOCK, not a separate action
    (UI-UX/04-gate-yard-kiosk/flows-and-states.md Flow 4). No `Idempotency-Key`: the catalog does
    not name one, and the transition table itself makes a repeat call a no-op-shaped
    INVALID_TRANSITION rather than a duplicate write.

    `officer_name` (FR-GATE-001) is an unverified label and authorises nothing --
    see OFFICER_ATTRIBUTION_KEY.
    """
    officer = normalise_officer_name(officer_name)
    target = queue_state.upper().strip()
    if target not in QUEUE_STATES:
        raise AppError(
            f"Unknown queue state '{queue_state}'.", code="INVALID_QUEUE_STATE", status_code=422
        )
    if queue_position is not None and queue_position <= 0:
        # Mirrors facility_checkins_queue_position_check rather than letting the DB raise.
        raise AppError("queue_position must be positive.", code="INVALID_QUEUE_POSITION", status_code=422)

    shipment = await _shipment_in_scope(session, ctx, shipment_id)
    facility_id = str(shipment["facility_id"])
    checkin = await _locked_checkin(session, shipment_id)
    if checkin is None or checkin["gate_in_ts"] is None:
        raise AppError(
            "Truck has not been gated in.", code="NOT_CHECKED_IN", status_code=409
        )

    current = str(checkin["queue_state"] or "NOT_QUEUED")
    if target not in QUEUE_TRANSITIONS.get(current, frozenset()):
        # edge-cases.md #3: the kiosk re-fetches and re-renders the now-correct one action rather
        # than retrying, so the current state is named in the response, not just refused.
        return GateEventResult(
            as_of=_as_of(), code="INVALID_TRANSITION", shipment_id=shipment_id,
            facility_id=facility_id, checkin_id=str(checkin["checkin_id"]),
            queue_state=current, queue_position=checkin["queue_position"],
            arrival_state=checkin["arrival_state"], officer_name=officer,
        )

    now = datetime.now(timezone.utc)
    # A position only means something while the truck is queued; carrying it into CALLED_TO_DOCK
    # would leave a stale ordinal on a truck that is no longer in the queue.
    new_position = queue_position if target in WAITING_STATES else None
    await session.execute(
        text(
            """
            UPDATE public.facility_checkins
            SET queue_state = :queue_state, queue_position = :queue_position, updated_at = :updated_at
            WHERE checkin_id = :checkin_id
            """
        ),
        {
            "queue_state": target, "queue_position": new_position,
            "updated_at": now, "checkin_id": checkin["checkin_id"],
        },
    )
    await _project_shipment_status(session, shipment_id, "WAITING")
    await _audit(
        session, ctx, entity_id=str(checkin["checkin_id"]), action_type="UPDATE",
        old_value={"queue_state": current, "queue_position": checkin["queue_position"]},
        new_value={"event": "QUEUE_STATE", "queue_state": target, "queue_position": new_position},
        officer_name=officer,
        now_iso=now.isoformat(),
    )
    await session.commit()
    return GateEventResult(
        as_of=_as_of(), code="QUEUE_UPDATED", shipment_id=shipment_id, facility_id=facility_id,
        checkin_id=str(checkin["checkin_id"]), queue_state=target, queue_position=new_position,
        arrival_state=checkin["arrival_state"], officer_name=officer,
    )


async def _live_dock_occupant(
    session: AsyncSession, *, dock_id: str, shipment_id: str
) -> str | None:
    """The shipment physically in this dock right now, if any.

    Physical truth, not booked truth: a truck is in the dock once `dock_in_ts` is set and until its
    unload ends or it gates out. Section 7.5.2 calls DOCK_OCCUPIED "a real operational catch, not a
    theoretical one", which is precisely the check the booking tables cannot make.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT shipment_id
                FROM public.facility_checkins
                WHERE actual_dock_id = :dock_id
                  AND shipment_id <> :shipment_id
                  AND dock_in_ts IS NOT NULL
                  AND unload_end_ts IS NULL
                  AND gate_out_ts IS NULL
                LIMIT 1
                """
            ),
            {"dock_id": dock_id, "shipment_id": shipment_id},
        )
    ).mappings().first()
    return str(row["shipment_id"]) if row else None


async def record_dock_in(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    dock_id: str,
    ts: datetime | None = None,
    officer_name: str | None = None,
) -> GateEventResult:
    """FR-GATE-006 / section 7.5.2 `record_dock_in`.

    DOCK_MISMATCH is a *deviation, not an error*: the arrival is still recorded against the dock
    the truck actually reached, and the confirmed dock is named alongside it. DOCK_OCCUPIED is the
    opposite -- nothing is recorded, and the truck is returned to WAITING_DOCK_UNAVAILABLE so the
    kiosk's state -> action table offers "Call to dock" again (edge-cases.md #4).

    `officer_name` (FR-GATE-001) is an unverified label and authorises nothing -- see
    OFFICER_ATTRIBUTION_KEY. Note in particular that it does **not** relax the mismatch check: a
    deviation is a deviation whoever recorded it, and the label only says who was standing there.
    """
    officer = normalise_officer_name(officer_name)
    shipment = await _shipment_in_scope(session, ctx, shipment_id)
    facility_id = str(shipment["facility_id"])
    event_ts = _coerce_ts(ts)

    dock = (
        await session.execute(
            text("SELECT dock_id, facility_id, dock_code FROM public.docks WHERE dock_id = :dock_id"),
            {"dock_id": dock_id},
        )
    ).mappings().first()
    if dock is None:
        raise AppError("Dock not found.", code="DOCK_NOT_FOUND", status_code=404)
    if str(dock["facility_id"]) != facility_id:
        # The dock id selects *within* the caller's scope; it can never move the write to another
        # facility (section 7.5 principle 1).
        raise AppError("Dock is not at this shipment's facility.", code="FORBIDDEN", status_code=403)

    checkin = await _locked_checkin(session, shipment_id)
    if checkin is None or checkin["gate_in_ts"] is None:
        raise AppError("Truck has not been gated in.", code="NOT_CHECKED_IN", status_code=409)
    current = str(checkin["queue_state"] or "NOT_QUEUED")
    if current != "CALLED_TO_DOCK":
        return GateEventResult(
            as_of=_as_of(), code="INVALID_TRANSITION", shipment_id=shipment_id,
            facility_id=facility_id, checkin_id=str(checkin["checkin_id"]),
            queue_state=current, arrival_state=checkin["arrival_state"], officer_name=officer,
        )

    now = datetime.now(timezone.utc)
    occupant = await _live_dock_occupant(session, dock_id=dock_id, shipment_id=shipment_id)
    if occupant is not None:
        await session.execute(
            text(
                """
                UPDATE public.facility_checkins
                SET queue_state = 'WAITING_DOCK_UNAVAILABLE', updated_at = :updated_at
                WHERE checkin_id = :checkin_id
                """
            ),
            {"updated_at": now, "checkin_id": checkin["checkin_id"]},
        )
        await _audit(
            session, ctx, entity_id=str(checkin["checkin_id"]), action_type="UPDATE",
            old_value={"queue_state": current},
            new_value={
                "event": "DOCK_IN_REFUSED", "dock_id": dock_id,
                "queue_state": "WAITING_DOCK_UNAVAILABLE", "occupying_shipment_id": occupant,
            },
            officer_name=officer,
            now_iso=now.isoformat(),
        )
        await session.commit()
        return GateEventResult(
            as_of=_as_of(), code="DOCK_OCCUPIED", shipment_id=shipment_id, facility_id=facility_id,
            checkin_id=str(checkin["checkin_id"]), queue_state="WAITING_DOCK_UNAVAILABLE",
            arrival_state=checkin["arrival_state"], actual_dock_id=None,
            expected_dock_id=dock_id, occupying_shipment_id=occupant, officer_name=officer,
        )

    appointment = await _active_appointment(session, shipment_id)
    expected_dock_id = str(appointment["dock_id"]) if appointment else None
    mismatch = expected_dock_id is not None and expected_dock_id != dock_id

    await session.execute(
        text(
            """
            UPDATE public.facility_checkins
            SET dock_in_ts = :dock_in_ts, actual_dock_id = :dock_id,
                queue_state = 'IN_DOCK', queue_position = NULL, updated_at = :updated_at
            WHERE checkin_id = :checkin_id
            """
        ),
        {
            "dock_in_ts": event_ts, "dock_id": dock_id,
            "updated_at": now, "checkin_id": checkin["checkin_id"],
        },
    )
    await _project_shipment_status(session, shipment_id, "IN_DOCK")
    await _audit(
        session, ctx, entity_id=str(checkin["checkin_id"]), action_type="UPDATE",
        old_value={"queue_state": current, "actual_dock_id": checkin["actual_dock_id"]},
        new_value={
            "event": "DOCK_IN", "dock_in_ts": event_ts, "actual_dock_id": dock_id,
            "expected_dock_id": expected_dock_id, "deviation": mismatch,
        },
        officer_name=officer,
        now_iso=now.isoformat(),
    )
    await session.commit()
    return GateEventResult(
        as_of=_as_of(), code="DOCK_MISMATCH" if mismatch else "DOCK_IN_RECORDED",
        shipment_id=shipment_id, facility_id=facility_id, checkin_id=str(checkin["checkin_id"]),
        queue_state="IN_DOCK", arrival_state=checkin["arrival_state"], actual_dock_id=dock_id,
        expected_dock_id=expected_dock_id, officer_name=officer,
        appointment_id=str(appointment["appointment_id"]) if appointment else None,
    )


async def record_unload_start_end(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    phase: str,
    ts: datetime | None = None,
    officer_name: str | None = None,
) -> GateEventResult:
    """FR-GATE-007 / section 7.5.2 `record_unload_start_end`.

    On END the overrun delta against `shipments.expected_unload_min` is returned -- the trigger for
    the DEVT003-style re-sequence and the input to churn pricing. Positive means the unload ran
    longer than planned; the sign is preserved rather than clamped, because an unload that finished
    early is equally an input to the sequencer.

    START and END may legitimately carry **different** officer names -- an unload can straddle a
    shift change -- so each phase records its own label rather than one being copied onto the other.
    `officer_name` (FR-GATE-001) is unverified and authorises nothing; see OFFICER_ATTRIBUTION_KEY.
    """
    officer = normalise_officer_name(officer_name)
    target_phase = phase.upper().strip()
    if target_phase not in {"START", "END"}:
        raise AppError("phase must be START or END.", code="INVALID_PHASE", status_code=422)

    shipment = await _shipment_in_scope(session, ctx, shipment_id)
    facility_id = str(shipment["facility_id"])
    event_ts = _coerce_ts(ts)
    checkin = await _locked_checkin(session, shipment_id)
    if checkin is None or checkin["gate_in_ts"] is None:
        raise AppError("Truck has not been gated in.", code="NOT_CHECKED_IN", status_code=409)

    current = str(checkin["queue_state"] or "NOT_QUEUED")
    now = datetime.now(timezone.utc)

    if target_phase == "START":
        if current != "IN_DOCK" or checkin["unload_start_ts"] is not None:
            return GateEventResult(
                as_of=_as_of(), code="INVALID_TRANSITION", shipment_id=shipment_id,
                facility_id=facility_id, checkin_id=str(checkin["checkin_id"]),
                queue_state=current, phase=target_phase,
                unload_start_ts=checkin["unload_start_ts"], officer_name=officer,
            )
        await session.execute(
            text(
                """
                UPDATE public.facility_checkins
                SET unload_start_ts = :ts, updated_at = :updated_at
                WHERE checkin_id = :checkin_id
                """
            ),
            {"ts": event_ts, "updated_at": now, "checkin_id": checkin["checkin_id"]},
        )
        await _audit(
            session, ctx, entity_id=str(checkin["checkin_id"]), action_type="UPDATE",
            old_value={"unload_start_ts": None},
            new_value={"event": "UNLOAD_START", "unload_start_ts": event_ts},
            officer_name=officer,
            now_iso=now.isoformat(),
        )
        await session.commit()
        return GateEventResult(
            as_of=_as_of(), code="RECORDED", shipment_id=shipment_id, facility_id=facility_id,
            checkin_id=str(checkin["checkin_id"]), queue_state=current, phase="START",
            unload_start_ts=event_ts, officer_name=officer,
        )

    if checkin["unload_start_ts"] is None or checkin["unload_end_ts"] is not None:
        return GateEventResult(
            as_of=_as_of(), code="INVALID_TRANSITION", shipment_id=shipment_id,
            facility_id=facility_id, checkin_id=str(checkin["checkin_id"]),
            queue_state=current, phase=target_phase,
            unload_start_ts=checkin["unload_start_ts"], unload_end_ts=checkin["unload_end_ts"],
            officer_name=officer,
        )

    unload_start: datetime = checkin["unload_start_ts"]
    actual_unload_min = (event_ts - unload_start).total_seconds() / 60.0
    expected_unload_min = int(shipment["expected_unload_min"])
    overrun_min = actual_unload_min - expected_unload_min
    await session.execute(
        text(
            """
            UPDATE public.facility_checkins
            SET unload_end_ts = :ts, queue_state = 'COMPLETED', updated_at = :updated_at
            WHERE checkin_id = :checkin_id
            """
        ),
        {"ts": event_ts, "updated_at": now, "checkin_id": checkin["checkin_id"]},
    )
    await _audit(
        session, ctx, entity_id=str(checkin["checkin_id"]), action_type="UPDATE",
        old_value={"queue_state": current, "unload_end_ts": None},
        new_value={
            "event": "UNLOAD_END", "unload_end_ts": event_ts, "queue_state": "COMPLETED",
            "actual_unload_min": round(actual_unload_min, 2), "overrun_min": round(overrun_min, 2),
        },
        officer_name=officer,
        now_iso=now.isoformat(),
    )
    await session.commit()
    return GateEventResult(
        as_of=_as_of(), code="RECORDED", shipment_id=shipment_id, facility_id=facility_id,
        checkin_id=str(checkin["checkin_id"]), queue_state="COMPLETED", phase="END",
        unload_start_ts=unload_start, unload_end_ts=event_ts,
        actual_unload_min=round(actual_unload_min, 2), expected_unload_min=expected_unload_min,
        overrun_min=round(overrun_min, 2), officer_name=officer,
    )


async def record_gate_out(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    ts: datetime | None = None,
    officer_name: str | None = None,
) -> GateEventResult:
    """FR-GATE-008 / section 7.5.2 `record_gate_out`.

    `officer_name` (FR-GATE-001) is an unverified label and authorises nothing -- see
    OFFICER_ATTRIBUTION_KEY. Gate-out is very often a *different* officer from gate-in on a long
    dwell, which is precisely why the label belongs on the event rather than on the check-in row.

    Dwell is `gate_out_ts - gate_in_ts`, exactly as section 7.5.2 states -- the whole time the truck
    was on site, not just its time in the dock. Verified against the seeded Layer A pair CHK1001
    (gate_in 2026-08-04T07:35+05:30, gate_out 08:50+05:30 -> 75 min), read live 2026-08-23; the same
    subtraction over all 397 live gated-out rows reproduces their stored intervals.
    """
    officer = normalise_officer_name(officer_name)
    shipment = await _shipment_in_scope(session, ctx, shipment_id)
    facility_id = str(shipment["facility_id"])
    event_ts = _coerce_ts(ts)
    checkin = await _locked_checkin(session, shipment_id)
    if checkin is None or checkin["gate_in_ts"] is None:
        raise AppError("Truck has not been gated in.", code="NOT_CHECKED_IN", status_code=409)
    if checkin["gate_out_ts"] is not None:
        # edge-cases.md #6: a terminal truck re-searched. The fact is restated, not re-recorded.
        gate_in: datetime = checkin["gate_in_ts"]
        return GateEventResult(
            as_of=_as_of(), code="ALREADY_GATED_OUT", shipment_id=shipment_id,
            facility_id=facility_id, checkin_id=str(checkin["checkin_id"]),
            queue_state=checkin["queue_state"], gate_in_ts=gate_in,
            gate_out_ts=checkin["gate_out_ts"], officer_name=officer,
            dwell_min=round((checkin["gate_out_ts"] - gate_in).total_seconds() / 60.0, 2),
        )

    now = datetime.now(timezone.utc)
    gate_in = checkin["gate_in_ts"]
    dwell_min = (event_ts - gate_in).total_seconds() / 60.0
    await session.execute(
        text(
            """
            UPDATE public.facility_checkins
            SET gate_out_ts = :ts, queue_state = 'COMPLETED', queue_position = NULL,
                updated_at = :updated_at
            WHERE checkin_id = :checkin_id
            """
        ),
        {"ts": event_ts, "updated_at": now, "checkin_id": checkin["checkin_id"]},
    )
    await _project_shipment_status(session, shipment_id, "COMPLETED")
    await _audit(
        session, ctx, entity_id=str(checkin["checkin_id"]), action_type="UPDATE",
        old_value={"queue_state": checkin["queue_state"], "gate_out_ts": None},
        new_value={
            "event": "GATE_OUT", "gate_out_ts": event_ts, "queue_state": "COMPLETED",
            "dwell_min": round(dwell_min, 2),
        },
        officer_name=officer,
        now_iso=now.isoformat(),
    )
    await session.commit()
    return GateEventResult(
        as_of=_as_of(), code="COMPLETED", shipment_id=shipment_id, facility_id=facility_id,
        checkin_id=str(checkin["checkin_id"]), queue_state="COMPLETED", gate_in_ts=gate_in,
        gate_out_ts=event_ts, dwell_min=round(dwell_min, 2), officer_name=officer,
        arrival_state=checkin["arrival_state"], actual_dock_id=checkin["actual_dock_id"],
    )


__all__ = [
    "DEFAULT_EARLY_LIMIT_MIN",
    "GateEventResult",
    "OFFICER_ATTRIBUTION_KEY",
    "OFFICER_NAME_MAX_LEN",
    "ON_TIME_WINDOW_MIN",
    "QUEUE_TRANSITIONS",
    "UnloadPhase",
    "classify_arrival",
    "normalise_officer_name",
    "record_dock_in",
    "record_gate_in",
    "record_gate_out",
    "record_unload_start_end",
    "update_queue_state",
]
