"""Planner console tools -- SOLUTION_DESIGN.md section 7.5.1.

`get_planner_queue` (FR-PLN-010) plus the dock-blocking writes FR-PLN-007 / FR-PLN-008.

## The queue read (section 7.5.1 `get_planner_queue`, added for issue #60)

Section 7.3's whole thesis is a 30-second decision made without opening anything, which is only
possible if the row already carries every fact the decision needs. This function is the server
side of that: seven fields per row -- condensed receipt, displacement check, ETA confidence,
`latest_acceptable_ts`, TTL remaining, `snapshot_hash` -- ordered by section 7.3's composite
urgency rather than FIFO.

None of it is computed by the client. U48 ("the interface renders receipts, it never computes
them") is the reason: a client-side displacement check is the same hazard class as a client-side
safe-batch predicate, which section 7.5.1 calls "auto-confirmation wearing a button".

## The dock-blocking writes

Section 2's persona table lists "block docks" as a core planner job and section 7.5.1 gives it a
tool, but nothing in the live backend could write `dock_status_events` -- the table was read-only in
practice, populated only by the seed. That matters more than it looks: `dock_status_events` is D1's
declared single authority for dock availability (section 0.9 / section 6.2 #9), and both the
feasibility scan (`scheduling/feasibility.py:721`) and the locked revalidation
(`scheduling/allocation.py:1107`) already treat *any* overlapping event row as making a slot
unbookable. So a row written here takes effect on the booking path immediately, with no separate
publishing step -- which is exactly what UI-UX/03-planner-dock-board/flows-and-states.md Flow 8
assumes ("Stage 1 already reads `dock_status_events` live").

Scope: the facility is derived from the *dock*, never from the request (section 7.5 principle 1 /
M15). `dock_id` selects within the caller's scope and is validated against it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, resolve_clock
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.core.settings import get_settings
from app.repositories import facilities as facilities_repo
from app.repositories import operations as operations_repo
from app.repositories.scope import assert_facility_write_scope, resolve_facility_scope
from app.scheduling import holds
from app.scheduling import urgency as _urgency_policy
from app.scheduling.constraints import load_scheduling_constraints
from app.scheduling.urgency import QueueUrgency, composite_urgency, urgency_sort_key

# `claim_id` and the two source labels are imported, never re-implemented: `claim_id`'s output goes
# straight into `_snapshot_hash`, and `scheduling/snapshot.py` recomputes the same digest on the
# write path. A second copy here is exactly the drift that module exists to prevent.
from app.scheduling.snapshot import (
    CAPACITY_CONSUMING_STATES,
    CLAIM_SOURCE_APPOINTMENT,
    claim_id as _claim_id,
)

# The D9 TTL is imported, never re-declared: `expiry.py` is what actually expires these rows, so a
# second copy of "15" here could silently disagree with the clock the queue is counting down to.
from app.scheduling.expiry import DEFAULT_PENDING_TTL_MINUTES
from app.services.idempotency import lookup_idempotency, payload_hash, store_idempotency
from app.services.ids import new_id

# `dock_status_events.event_type` values that mean "this dock is unavailable". Read live from the
# CHECK constraint 2026-08-23: MAINTENANCE, BREAKDOWN, CAPACITY_REDUCTION, REOPENED, MANUAL_BLOCK.
# A planner-initiated block is MANUAL_BLOCK; the others are recorded by other actors or the seed.
MANUAL_BLOCK_EVENT_TYPE = "MANUAL_BLOCK"
BLOCKING_EVENT_TYPES = ("MAINTENANCE", "BREAKDOWN", "CAPACITY_REDUCTION", "MANUAL_BLOCK")

ACTIVE_APPOINTMENT_STATUSES = ("PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS")

# --- get_planner_queue (FR-PLN-010) -----------------------------------------------------------

DEFAULT_QUEUE_LIMIT = 50
MAX_QUEUE_LIMIT = 200

# section 7.3's composite ordering -- the policy, its two weights, its `QueueUrgency` shape and its
# tiebreaker -- moved to `scheduling/urgency.py` for issue #82 and imported back under the names
# this module already published. It moved because a *second* read needs the identical ordering:
# `escalation_service.get_pending_confirmations` shipped `ORDER BY booked_at ASC`, the pure FIFO
# section 7.3 rejects by name, and #82's assessment was that it must adopt this ordering rather
# than grow a second implementation of the same scheduling policy. Nothing about the calibration
# changed in the move; see that module for the full argument.
PHYSICALLY_WAITING_QUEUE_STATES = _urgency_policy.PHYSICALLY_WAITING_QUEUE_STATES
TTL_PRESSURE_MAX = _urgency_policy.TTL_PRESSURE_MAX
WAITING_BONUS = _urgency_policy.WAITING_BONUS

# Version tag on the `snapshot_hash` serialisation. `enforced` flipped to True once issue #62 landed
# the consumer half: `confirm_request` and `counter_offer` now recompute this digest under the row
# lock (`allocation._snapshot_guard`) and refuse with `SNAPSHOT_STALE` on drift, so a client that
# read `enforced: false` and skipped the argument would be refused by a mechanism the payload had
# told it was inactive. Understating the server is the more dangerous direction of the two.
#
# The note stays precise about *which* tools refuse rather than rounding up to "all of them",
# because two of the four §7.5.1/§7.5.3 names behave differently and a client planning a bulk flow
# needs to know it:
#   * `bulk_confirm` computes the composite digest and reports `snapshot_hash_matched`, but
#     deliberately does **not** refuse the batch (see its docstring: Flow 6 step 3 wants per-id
#     outcomes, and the five-predicate re-check is the stronger gate).
#   * `apply_schedule_proposal` is not implemented at all yet -- grepped 2026-08-31, it appears
#     only in docstrings -- so it cannot be said to enforce anything.
SNAPSHOT_ALGORITHM = "sha256/planner-queue-v1"
SNAPSHOT_NOT_ENFORCED_NOTE = (
    "snapshot_hash is validated on write: confirm_request and counter_offer recompute it under the "
    "row lock and refuse with SNAPSHOT_STALE on drift, after checking displacement. Always send the "
    "value the row carried. bulk_confirm compares the composite digest and reports "
    "snapshot_hash_matched but does not refuse on it; apply_schedule_proposal is not implemented."
)


class DockBlockResult(BaseModel):
    """Typed outcome for `block_dock` / `end_dock_block` (section 7.5 principle 2)."""

    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    code: str
    dock_id: str
    facility_id: str
    dock_status_event_id: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    reason: str | None = None
    # BLOCKED: the set FR-PLN-007 requires to be named. ALREADY_BLOCKED: the conflicting row.
    affected_appointments: list[dict[str, Any]] = Field(default_factory=list)
    affected_count: int = 0
    escalation_id: str | None = None
    conflicting_event: dict[str, Any] | None = None
    idempotency_key: str | None = None
    idempotent_replay: bool = False


class DockBlockImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    dock_id: str
    facility_id: str
    window_start: datetime
    window_end: datetime
    affected_appointments: list[dict[str, Any]] = Field(default_factory=list)
    affected_count: int = 0
    conflicting_event: dict[str, Any] | None = None


def _as_of() -> str:
    """ISO string for the response model only -- never bind into a timestamptz parameter."""
    return datetime.now(timezone.utc).isoformat()


def _coerce_ts(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


# =============================================================================================
# get_planner_queue -- section 7.5.1 / section 7.3 / FR-PLN-010
# =============================================================================================


class QueueReceipt(BaseModel):
    """Section 7.3's condensed receipt -- "the score terms in words".

    Terms are re-derived at read time with the *same definitions*
    `scheduling/feasibility.py::_rank_slot` uses when it ranks an option, so the receipt a planner
    reads and the score that produced the proposal cannot describe different things. They are not
    read back from a stored recommendation because none exists: nothing persists
    `ranking_factors` (grepped 2026-08-29 -- `recommendation_id` is a nullable column on
    `escalation_queue` and nowhere else).
    """

    model_config = ConfigDict(extra="forbid")

    priority_code: str
    lateness_minutes: int | None = None
    wait_after_eta_minutes: int | None = None
    dock_match: str | None = None
    text: str


class QueueDisplacement(BaseModel):
    """Section 7.3's "single most important field": would confirming this hurt a third party?"""

    model_config = ConfigDict(extra="forbid")

    status: str  # NONE | CONFLICT
    conflicts: list[dict[str, Any]] = Field(default_factory=list)


class QueueEta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_eta_ts: datetime | None = None
    confidence: str | None = None
    source: str | None = None


class QueueTtl(BaseModel):
    """The D9 clock, derived rather than stored (see `scheduling/expiry.py`'s own note)."""

    model_config = ConfigDict(extra="forbid")

    deadline_ts: datetime
    remaining_seconds: int
    expired: bool


class QueueGateState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queue_state: str | None = None
    queue_position: int | None = None
    gate_in_ts: datetime | None = None
    physically_waiting: bool = False


class PlannerQueueRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: str
    shipment_id: str
    slot_id: str
    appointment_status: str
    booking_source: str
    booked_at: datetime
    order_reference: str | None = None

    driver_id: str | None = None
    driver_name: str | None = None
    carrier_id: str | None = None
    carrier_name: str | None = None

    facility_id: str
    dock_id: str
    dock_code: str | None = None
    dock_type: str | None = None
    interval_start: datetime
    interval_end: datetime
    # "dock_occupancy" when D1's authority answered; "appointment_slot_derived" when this
    # appointment holds no claim and the window had to be recomputed. Never silently identical.
    interval_source: str

    receipt: QueueReceipt
    displacement: QueueDisplacement
    eta: QueueEta
    latest_acceptable_ts: str | None = None
    latest_acceptable_exception_id: str | None = None
    # None means "no limit on file, or one that could not be parsed" -- deliberately three-valued
    # rather than defaulting to False, because "we checked and it is fine" and "we could not check"
    # are different facts (the same distinction State 17 protects for the block-dock preview).
    latest_acceptable_breached: bool | None = None
    ttl: QueueTtl
    gate: QueueGateState
    urgency: QueueUrgency
    snapshot_hash: str


class PlannerQueueSnapshotInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: str
    enforced: bool
    note: str


class PlannerQueue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    scope: dict[str, Any]
    policy_version: str
    ttl_minutes: int
    horizon_hours: int | None = None
    limit: int
    limit_reached: bool
    ordering: dict[str, Any]
    snapshot: PlannerQueueSnapshotInfo
    count: int
    items: list[PlannerQueueRow] = Field(default_factory=list)


def _minutes_between(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


def _parse_text_timestamp(value: Any) -> datetime | None:
    """Parse an ISO string that is still a `text` column, tolerating anything unparseable.

    `driver_exceptions.latest_acceptable_ts` was **not** converted by the E1.1/D1 migration --
    that migration named six tables and `driver_exceptions` is not one of them
    (`20260823060000_d1_correctness_bedrock.sql` step 3). Casting it in SQL would abort the whole
    queue read on a single malformed row, which is the wrong failure for a screen whose entire job
    is being available during a spike, so it is parsed here and a failure degrades one field.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return _coerce_ts(value)
    try:
        return _coerce_ts(datetime.fromisoformat(str(value)))
    except ValueError:
        return None


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Half-open interval overlap -- the same thing `tstzrange(..., '[)') &&` means.

    Strict on both sides, so two abutting windows do not overlap: PostgreSQL's `&&` is "have any
    elements in common", and adjacency is the separate `-|-` operator. Matching that exactly
    matters because the `EXCLUDE USING gist` constraint on `dock_occupancy` is what actually
    decides whether two claims can coexist -- a Python check that disagreed would flag a
    displacement the database considers legal.
    """
    return a_start < b_end and b_start < a_end


def _conflicts_for(
    row: dict[str, Any],
    interval_start: datetime,
    interval_end: datetime,
    live_occupancy: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Other live claims this request's interval would collide with on the same dock.

    For a row that holds its own `dock_occupancy` claim this is always empty, and that is a
    guarantee rather than a coincidence: the exclusion constraint already refused any overlapping
    claim at booking time. The check earns its place on the rows that hold *no* claim -- the E1.1
    backfill's D12 worklist cases and anything whose claim was released -- where confirming really
    could land on top of another truck.

    Since issue #84 the set handed in may include D2 holds (`appointment_id IS NULL`), which is why
    the self-exclusion below is guarded on `is not None`: a queue row is always an appointment, so a
    hold can never *be* this row, and the shipped `str(None) == str(appointment_id)` comparison
    would merely have been an accidental never-match.
    """
    conflicts: list[dict[str, Any]] = []
    for occupancy in live_occupancy:
        if str(occupancy["dock_id"]) != str(row["dock_id"]):
            continue
        occupancy_appointment_id = occupancy.get("appointment_id")
        if (
            occupancy_appointment_id is not None
            and str(occupancy_appointment_id) == str(row["appointment_id"])
        ):
            continue
        other_start = _coerce_ts(occupancy["window_start"])
        other_end = _coerce_ts(occupancy["window_end"])
        if not _overlaps(interval_start, interval_end, other_start, other_end):
            continue
        conflicts.append(
            {
                "claim_id": _claim_id(occupancy),
                "claim_source": occupancy.get("claim_source", CLAIM_SOURCE_APPOINTMENT),
                "appointment_id": occupancy_appointment_id,
                "shipment_id": occupancy["shipment_id"],
                "order_reference": occupancy.get("order_reference"),
                "appointment_status": occupancy["appointment_status"],
                "hold_expires_at": occupancy.get("hold_expires_at"),
                "window_start": other_start,
                "window_end": other_end,
            }
        )
    return conflicts


def _build_receipt(
    row: dict[str, Any], interval_start: datetime, effective_eta: datetime | None
) -> QueueReceipt:
    """Section 7.3's worked example is `"CRITICAL - 70 min late - exact dock - 0 min wait"`."""
    priority_code = str(row.get("priority_code") or "NORMAL")
    original_eta = _parse_text_timestamp(row.get("original_eta_ts"))
    lateness = None
    wait = None
    if effective_eta is not None:
        if original_eta is not None:
            lateness = max(0, _minutes_between(original_eta, effective_eta))
        wait = max(0, _minutes_between(effective_eta, interval_start))
    dock_match = None
    if row.get("required_dock_type") and row.get("dock_type"):
        # Mirrors `_rank_slot`'s `exact_dock_type_match`: a required type of ANY on a STANDARD dock
        # is "compatible", not "exact" -- that is the distinction the P_dock penalty encodes and
        # the one the bulk-confirm safe-batch predicate turns on.
        dock_match = (
            "exact" if str(row["required_dock_type"]) == str(row["dock_type"]) else "compatible"
        )
    terms = [priority_code]
    if lateness is not None:
        terms.append(f"{lateness} min late")
    if dock_match is not None:
        terms.append(f"{dock_match} dock")
    if wait is not None:
        terms.append(f"{wait} min wait")
    return QueueReceipt(
        priority_code=priority_code,
        lateness_minutes=lateness,
        wait_after_eta_minutes=wait,
        dock_match=dock_match,
        text=" · ".join(terms),
    )


def _snapshot_hash(
    *,
    appointment_id: str,
    appointment_status: str,
    is_current: Any,
    dock_id: str,
    interval_start: datetime,
    interval_end: datetime,
    interval_source: str,
    conflict_ids: list[str],
) -> str:
    """A stable digest of exactly the facts a confirm must re-check before it commits.

    Scope, deliberately: identity + lifecycle state + the authoritative interval + the
    displacement set. **Not** the TTL, the ETA or anything else that moves on a wall clock -- a
    hash that changed every second would make every confirm stale and turn issue #61's refusal
    into noise. The point of a snapshot guard is "the capacity you looked at changed", not
    "time passed".

    Not a security boundary and not signed: the server recomputes this from its own rows on the
    write path (when #61 builds that path), so a forged value can only ever cause a comparison to
    fail, never to pass on data the server did not itself produce.
    """
    canonical = json.dumps(
        {
            "v": 1,
            "appointment_id": appointment_id,
            "appointment_status": appointment_status,
            "is_current": int(is_current) if is_current is not None else None,
            "dock_id": dock_id,
            "interval_start": interval_start.isoformat(),
            "interval_end": interval_end.isoformat(),
            "interval_source": interval_source,
            "conflicts": sorted(conflict_ids),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# `scheduling/urgency.composite_urgency` under this module's own historical name (issue #82). Kept
# as an alias rather than renamed at the ~15 call/patch sites so the move stays a move: existing
# tests that monkeypatch or assert on `planner_service._urgency` keep working, and the diff shows
# no behaviour change to review.
_urgency = composite_urgency


async def get_planner_queue(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    facility_id: str | None = None,
    horizon_hours: int | None = None,
    limit: int = DEFAULT_QUEUE_LIMIT,
    clock: Clock | None = None,
) -> PlannerQueue:
    """Section 7.5.1 `get_planner_queue` / FR-PLN-010 -- the read every other planner flow needs.

    `facility_id` is a *request*, never the answer (section 7.5 principle 1 / M15): it goes
    through `resolve_facility_scope`, so an operator may only ever pass their own facility and a
    global-read persona uses it to narrow. `require_facility=True` because this surface is
    deliberately single-facility -- `03-planner-dock-board/screens.md` section 1 states the
    switcher is one facility, "not 'All facilities'", since section 7.3's load arithmetic and D5's
    sequencer are both per-facility. An unscoped cross-facility queue would also silently break
    the composite ordering, which compares requests competing for the same docks.

    Two queries, never N+1: the candidate rows, then every live claim in the facility across the
    bounding window those rows span. The displacement check is then pure Python over that set.

    `clock` is section 9.1's injected clock, for the same reason `sweep_expired_appointments`
    takes one -- the TTL column is the whole point of this read and a test that could not pin
    `now` would be asserting against the wall clock.
    """
    scope_facility = resolve_facility_scope(ctx, facility_id, require_facility=True)
    if scope_facility is None:  # pragma: no cover - require_facility=True already guarantees this
        # Not an `assert`: `python -O` strips those, and this is the only thing standing between
        # a mis-scoped identity and an unfiltered cross-facility read.
        raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
    now = resolve_clock(clock).now()
    effective_limit = max(1, min(int(limit), MAX_QUEUE_LIMIT))
    horizon_end = (
        now + timedelta(hours=horizon_hours) if horizon_hours and horizon_hours > 0 else None
    )

    rows = await operations_repo.list_planner_queue_rows(
        session,
        facility_id=scope_facility,
        horizon_end=horizon_end,
        limit=effective_limit,
    )

    intervals: dict[str, tuple[datetime, datetime]] = {}
    for row in rows:
        intervals[str(row["appointment_id"])] = (
            _coerce_ts(row["interval_start"]),
            _coerce_ts(row["interval_end"]),
        )

    # One bounding window covering every candidate interval. Skipped entirely when the queue is
    # empty -- an empty queue costs exactly one query, which is the common case for four of the
    # five coordinators at any given moment.
    live_occupancy: list[dict[str, Any]] = []
    if intervals:
        range_start = min(start for start, _ in intervals.values())
        range_end = max(end for _, end in intervals.values())

        # ------------------------------------------------------------------------------------
        # Issue #98, the read half. A GET that writes -- deliberately, and here is the argument.
        # ------------------------------------------------------------------------------------
        #
        # `list_live_dock_occupancy` below carries no `expires_at > now()` term, because its job is
        # to predict what the exclusion constraint will refuse and that constraint has no time term
        # (#84; the repository function argues it at length). Since #97 the *claim* path lazily
        # expires colliding dead holds, so this read could show a `CONFLICT` -- and put that dead
        # hold's id into `snapshot_hash` -- for capacity the very next write would release.
        #
        # Owner decision (b) on #98 is to make the table true rather than to make the read
        # disagree with the constraint. It has to happen on *this* side too, not only in
        # `snapshot.load_appointment_snapshots`: `conflict_ids` feeds the digest, so a queue row
        # rendered with a dead hold in it and a write path that expired the same hold would
        # produce two different hashes and turn every first confirm into `SNAPSHOT_STALE`. Fixing
        # one side alone converts a permanent `DISPLACEMENT_DETECTED` into a permanent-until-
        # re-render staleness refusal, which is not the fix.
        #
        # Same appointment ids, same statement as the write path uses, so the two cannot drift.
        # The commit is real rather than deferred: without it the flip is rolled back when the
        # request's session closes, the rows stay HELD for the next reader, and the audit trail
        # claims an expiry that did not happen. It costs no read consistency -- under READ
        # COMMITTED each statement already takes its own snapshot, so the two SELECTs either side
        # of it were never a consistent pair to begin with (PostgreSQL "Transaction Isolation"
        # 13.2.1). Safe here specifically because the sole caller is the router
        # (`api/v1/routers/planner.py`), which has nothing uncommitted in flight.
        if get_settings().two_phase_hold_enabled:
            await holds.expire_lapsed_holds_for_appointments(
                session,
                appointment_ids=list(intervals),
                now=now,
                actor_user_id=ctx.user_id,
            )
            await session.commit()

        live_occupancy = await operations_repo.list_live_dock_occupancy(
            session,
            facility_id=scope_facility,
            range_start=range_start,
            range_end=range_end,
            active_statuses=list(ACTIVE_APPOINTMENT_STATUSES),
            # Issue #84: a D2 hold consumes capacity with no `appointments` row to join to, so
            # with the flag on the displacement check has to read `dock_occupancy` directly or it
            # reports "no displacement" for an interval PostgreSQL will refuse. Off, the query is
            # the one that shipped -- and it has to be, because the columns do not exist until the
            # D2 migration is applied.
            include_holds=get_settings().two_phase_hold_enabled,
            hold_states=list(CAPACITY_CONSUMING_STATES),
        )

    constraints = load_scheduling_constraints()
    priority_scores = constraints.ranking_policy.priority_scores
    ttl_total_seconds = DEFAULT_PENDING_TTL_MINUTES * 60

    items: list[PlannerQueueRow] = []
    for row in rows:
        appointment_id = str(row["appointment_id"])
        interval_start, interval_end = intervals[appointment_id]
        interval_source = (
            "dock_occupancy" if row.get("occupancy_start") is not None else "appointment_slot_derived"
        )
        conflicts = _conflicts_for(row, interval_start, interval_end, live_occupancy)

        booked_at = _coerce_ts(row["booked_at"])
        deadline = booked_at + timedelta(minutes=DEFAULT_PENDING_TTL_MINUTES)
        remaining_seconds = int((deadline - now).total_seconds())

        queue_state = row.get("queue_state")
        physically_waiting = str(queue_state or "") in PHYSICALLY_WAITING_QUEUE_STATES

        effective_eta = _parse_text_timestamp(row.get("effective_eta_ts"))
        latest_acceptable = _parse_text_timestamp(row.get("latest_acceptable_ts"))
        # screens.md section 2 states the driver's own limit as a rule, not just a column:
        # "confirming past it creates a new exception". The comparison is against the interval
        # *start* -- the limit is the latest arrival the driver can accept, not the latest moment
        # their unload may finish.
        breached = None if latest_acceptable is None else interval_start > latest_acceptable

        items.append(
            PlannerQueueRow(
                appointment_id=appointment_id,
                shipment_id=str(row["shipment_id"]),
                slot_id=str(row["slot_id"]),
                appointment_status=str(row["appointment_status"]),
                booking_source=str(row["booking_source"]),
                booked_at=booked_at,
                order_reference=row.get("order_reference"),
                driver_id=row.get("driver_id"),
                driver_name=row.get("driver_name"),
                carrier_id=row.get("carrier_id"),
                carrier_name=row.get("carrier_name"),
                facility_id=str(row["facility_id"]),
                dock_id=str(row["dock_id"]),
                dock_code=row.get("dock_code"),
                dock_type=row.get("dock_type"),
                interval_start=interval_start,
                interval_end=interval_end,
                interval_source=interval_source,
                receipt=_build_receipt(row, interval_start, effective_eta),
                displacement=QueueDisplacement(
                    status="CONFLICT" if conflicts else "NONE", conflicts=conflicts
                ),
                eta=QueueEta(
                    effective_eta_ts=effective_eta,
                    confidence=row.get("eta_confidence"),
                    source=row.get("eta_source"),
                ),
                latest_acceptable_ts=(
                    str(row["latest_acceptable_ts"])
                    if row.get("latest_acceptable_ts") is not None
                    else None
                ),
                latest_acceptable_exception_id=row.get("limit_exception_id"),
                latest_acceptable_breached=breached,
                ttl=QueueTtl(
                    deadline_ts=deadline,
                    remaining_seconds=remaining_seconds,
                    expired=remaining_seconds <= 0,
                ),
                gate=QueueGateState(
                    queue_state=queue_state,
                    queue_position=row.get("queue_position"),
                    gate_in_ts=_parse_text_timestamp(row.get("gate_in_ts")),
                    physically_waiting=physically_waiting,
                ),
                urgency=_urgency(
                    priority_code=str(row.get("priority_code") or "NORMAL"),
                    priority_scores=priority_scores,
                    ttl_remaining_seconds=remaining_seconds,
                    ttl_total_seconds=ttl_total_seconds,
                    physically_waiting=physically_waiting,
                ),
                snapshot_hash=_snapshot_hash(
                    appointment_id=appointment_id,
                    appointment_status=str(row["appointment_status"]),
                    is_current=row.get("is_current"),
                    dock_id=str(row["dock_id"]),
                    interval_start=interval_start,
                    interval_end=interval_end,
                    interval_source=interval_source,
                    conflict_ids=[str(c["claim_id"]) for c in conflicts],
                ),
            )
        )

    # Highest urgency first, `appointment_id` ascending as the stable tiebreaker. The key lives in
    # `scheduling/urgency.py` alongside the score since issue #82, so the ops console's pending
    # list cannot adopt this metric and then sort by it differently.
    items.sort(key=lambda item: urgency_sort_key(item.urgency.score, item.appointment_id))

    return PlannerQueue(
        as_of=now.isoformat(),
        scope={"facility_id": scope_facility, "read_only": True},
        policy_version=constraints.policy_version,
        ttl_minutes=DEFAULT_PENDING_TTL_MINUTES,
        horizon_hours=horizon_hours,
        limit=effective_limit,
        # True means "there may be more pending requests than this page shows" -- the client must
        # not render "N pending" from `count` alone when this is set.
        limit_reached=len(rows) >= effective_limit,
        ordering={
            "rule": "composite_urgency",
            "terms": ["ttl_remaining", "priority_code", "physically_waiting"],
            "weights": {
                "priority_scores": priority_scores,
                "ttl_pressure_max": TTL_PRESSURE_MAX,
                "waiting_bonus": WAITING_BONUS,
            },
            "tiebreaker": "appointment_id",
        },
        snapshot=PlannerQueueSnapshotInfo(
            algorithm=SNAPSHOT_ALGORITHM,
            enforced=True,
            note=SNAPSHOT_NOT_ENFORCED_NOTE,
        ),
        count=len(items),
        items=items,
    )


async def _dock_in_scope(
    session: AsyncSession, ctx: ExecutionContext, dock_id: str
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT dock_id, facility_id, dock_code, dock_status
                FROM public.docks
                WHERE dock_id = :dock_id
                """
            ),
            {"dock_id": dock_id},
        )
    ).mappings().first()
    if row is None:
        raise AppError("Dock not found.", code="DOCK_NOT_FOUND", status_code=404)
    assert_facility_write_scope(ctx, str(row["facility_id"]))
    return dict(row)


async def _overlapping_block(
    session: AsyncSession, *, dock_id: str, window_start: datetime, window_end: datetime
) -> dict[str, Any] | None:
    """An existing unavailability event overlapping the proposed window.

    Half-open overlap (`start < other_end AND (other_end IS NULL OR other_end > start)`) matches the
    predicate the feasibility scan already uses, so "blocked" means the same thing to this tool and
    to Stage 1. An open-ended event (`event_end_ts IS NULL`) overlaps everything after its start.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT dock_event_id, dock_id, event_type, event_start_ts, event_end_ts, reason
                FROM public.dock_status_events
                WHERE dock_id = :dock_id
                  AND event_type = ANY(:blocking_types)
                  AND event_start_ts < :window_end
                  AND (event_end_ts IS NULL OR event_end_ts > :window_start)
                ORDER BY event_start_ts ASC
                LIMIT 1
                """
            ),
            {
                "dock_id": dock_id,
                "blocking_types": list(BLOCKING_EVENT_TYPES),
                "window_start": window_start,
                "window_end": window_end,
            },
        )
    ).mappings().first()
    return dict(row) if row else None


# Same two-literal shape, and the same reason, as
# `repositories/operations.py::_LIVE_DOCK_OCCUPANCY_SQL`: with the D2 flag off this must be the
# statement that shipped, because `o.state` / `o.shipment_id` do not exist until the D2 migration is
# applied and PostgreSQL resolves column names at parse time.
_AFFECTED_APPOINTMENTS_SQL = """
                SELECT o.occupancy_id, o.appointment_id, o.dock_id,
                       lower(o."window") AS window_start,
                       upper(o."window") AS window_end,
                       a.appointment_status, a.shipment_id,
                       s.driver_id, s.priority_code, s.load_weight_kg
                FROM public.dock_occupancy o
                JOIN public.appointments a ON a.appointment_id = o.appointment_id
                JOIN public.shipments s ON s.shipment_id = a.shipment_id
                WHERE o.dock_id = :dock_id
                  AND a.appointment_status = ANY(:active_statuses)
                  AND o."window" && tstzrange(:window_start, :window_end, '[)')
                ORDER BY lower(o."window") ASC
"""

_AFFECTED_APPOINTMENTS_WITH_HOLDS_SQL = """
                SELECT o.occupancy_id, o.appointment_id, o.dock_id,
                       lower(o."window") AS window_start,
                       upper(o."window") AS window_end,
                       COALESCE(a.appointment_status, o.state) AS appointment_status,
                       COALESCE(a.shipment_id, o.shipment_id) AS shipment_id,
                       CASE WHEN o.appointment_id IS NULL
                            THEN 'dock_occupancy_hold' ELSE 'appointments'
                       END AS claim_source,
                       o.expires_at AS hold_expires_at,
                       s.driver_id, s.priority_code, s.load_weight_kg
                FROM public.dock_occupancy o
                LEFT JOIN public.appointments a ON a.appointment_id = o.appointment_id
                LEFT JOIN public.shipments s
                  ON s.shipment_id = COALESCE(a.shipment_id, o.shipment_id)
                WHERE o.dock_id = :dock_id
                  AND o."window" && tstzrange(:window_start, :window_end, '[)')
                  AND (
                        a.appointment_status = ANY(:active_statuses)
                     OR (o.appointment_id IS NULL AND o.state = ANY(:hold_states))
                  )
                ORDER BY lower(o."window") ASC
"""


async def _affected_appointments(
    session: AsyncSession, *, dock_id: str, window_start: datetime, window_end: datetime
) -> list[dict[str, Any]]:
    """The live dock-time intervals the proposed block would strand.

    Reads `dock_occupancy` -- D1's true-interval table -- not `appointment_slots`, because a 75-min
    unload booked into a 60-min slot occupies time the slot row cannot see (section 6.2 #1). The
    status filter lives on `appointments`; `dock_occupancy` carries no status column of its own
    (verified live 2026-08-23), so the join is what restricts the set to the
    CONFIRMED / PENDING_CONFIRMATION / IN_PROGRESS rows section 7.5.1 names.

    **Issue #84's second blind spot.** That last sentence stopped being true once D2 landed: a hold
    is a `dock_occupancy` row with `appointment_id IS NULL`, so the INNER JOIN above dropped it, and
    FR-PLN-007's "names affected appointments *before* committing" quietly excluded every driver
    holding a slot on the dock being taken offline. Their hold is not deleted by `block_dock`
    (nothing here deletes claims -- that is what makes it a `CAPACITY_EVENT_CASCADE`), so an unnamed
    hold means a driver whose confirm is about to fail with nobody having been told.

    The hold predicate deliberately carries no `expires_at > now()` filter, for the reason
    `repositories/operations.py::list_live_dock_occupancy` sets out: a lapsed-but-unswept hold still
    occupies the interval as far as the exclusion constraint is concerned, and this list is a
    statement about occupied dock time.
    """
    include_holds = get_settings().two_phase_hold_enabled
    params: dict[str, Any] = {
        "dock_id": dock_id,
        "active_statuses": list(ACTIVE_APPOINTMENT_STATUSES),
        "window_start": window_start,
        "window_end": window_end,
    }
    if include_holds:
        params["hold_states"] = list(CAPACITY_CONSUMING_STATES)
    sql = (
        _AFFECTED_APPOINTMENTS_WITH_HOLDS_SQL if include_holds else _AFFECTED_APPOINTMENTS_SQL
    )
    rows = (await session.execute(text(sql), params)).mappings().all()
    return [dict(row) for row in rows]


async def get_dock_block_impact(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    dock_id: str,
    window_start: datetime,
    window_end: datetime,
) -> DockBlockImpact:
    """The preview behind FR-PLN-007's "names affected appointments **before** committing".

    UI-UX/03-planner-dock-board/flows-and-states.md Flow 7 step 2 requires the affected set to fetch
    live as the form's dock and time fields complete, "not deferred to submission". Section 7.5.1's
    catalog names no tool for that read, so this is an addition to the catalog rather than an
    implementation of it -- flagged deliberately rather than folded in silently. It is a pure read;
    `block_dock` re-computes the same set inside its own transaction and never trusts this result.
    """
    dock = await _dock_in_scope(session, ctx, dock_id)
    start = _coerce_ts(window_start)
    end = _coerce_ts(window_end)
    if end <= start:
        raise AppError("window_end must be after window_start.", code="INVALID_WINDOW", status_code=422)
    affected = await _affected_appointments(
        session, dock_id=dock_id, window_start=start, window_end=end
    )
    conflicting = await _overlapping_block(
        session, dock_id=dock_id, window_start=start, window_end=end
    )
    return DockBlockImpact(
        as_of=_as_of(), dock_id=dock_id, facility_id=str(dock["facility_id"]),
        window_start=start, window_end=end,
        affected_appointments=affected, affected_count=len(affected),
        conflicting_event=conflicting,
    )


async def _open_capacity_cascade(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    facility_id: str,
    dock_event_id: str,
    dock_id: str,
    affected: list[dict[str, Any]],
    now_iso: str,
) -> str | None:
    """One CAPACITY_EVENT_CASCADE row per block, never one per stranded appointment.

    Flow 7 step 4 is explicit: the escalation "is created server-side, not by this UI", and surfaces
    "as a single capacity-incident row (U65), not N separate escalations, regardless of how many
    appointments this block stranded".

    Deliberately not routed through `escalation_service.escalate_exception`: that function's
    dedupe key is `shipment:day:type`, which would fold two different blocks on the same day into
    one incident and split one block across N shipments into N rows -- the opposite of what U65
    asks for. Keying on the dock event id instead makes the incident 1:1 with the block that caused
    it. `escalation_queue.shipment_id` is NOT NULL, so the first affected shipment is the row's
    anchor and the full set lives in `payload_json`.
    """
    if not affected:
        return None
    anchor = affected[0]
    escalation_id = new_id("ESC")
    payload = {
        "reason": "Dock block overlaps live appointments.",
        "dock_id": dock_id,
        "dock_status_event_id": dock_event_id,
        "affected_count": len(affected),
        "affected_appointments": [
            {
                # `claim_id` names a stranded D2 hold, which has no appointment id (issue #84).
                # `appointment_id` is kept alongside it and stays exactly what it was for a booked
                # claim, so nothing already reading this payload has to change.
                "claim_id": _claim_id(item),
                "claim_source": item.get("claim_source", CLAIM_SOURCE_APPOINTMENT),
                "appointment_id": item["appointment_id"],
                "shipment_id": item["shipment_id"],
                "appointment_status": item["appointment_status"],
                "hold_expires_at": item.get("hold_expires_at"),
                "window_start": item["window_start"],
                "window_end": item["window_end"],
            }
            for item in affected
        ],
    }
    row = (
        await session.execute(
            text(
                """
                INSERT INTO public.escalation_queue (
                  escalation_id, shipment_id, facility_id, driver_id, escalation_type,
                  escalation_status, severity_code, policy_version, recommendation_id,
                  payload_json, dedupe_key, created_at, updated_at, resolved_at, resolved_by_user_id
                ) VALUES (
                  :escalation_id, :shipment_id, :facility_id, :driver_id, 'CAPACITY_EVENT_CASCADE',
                  'OPEN', 'HIGH', NULL, NULL,
                  :payload_json, :dedupe_key, :created_at, :updated_at, NULL, NULL
                )
                -- Issue #96: index_predicate, not a row filter. It must match
                -- `escalation_queue_dedupe_key_active_uidx` (migration 20260901120000) exactly or
                -- PostgreSQL cannot infer the now-partial unique index and this INSERT raises
                -- 42P10 ("no unique or exclusion constraint matching the ON CONFLICT
                -- specification"). Semantically it also means a cascade whose escalation a
                -- coordinator has already resolved opens a fresh case rather than silently
                -- overwriting the closed one's payload -- the same rule #96 established for
                -- escalate_exception, applied to the one other DO UPDATE on this table.
                ON CONFLICT (dedupe_key) WHERE escalation_status NOT IN ('RESOLVED', 'CANCELLED')
                DO UPDATE
                SET payload_json = EXCLUDED.payload_json, updated_at = EXCLUDED.updated_at
                RETURNING escalation_id
                """
            ),
            {
                "escalation_id": escalation_id,
                "shipment_id": anchor["shipment_id"],
                "facility_id": facility_id,
                "driver_id": anchor.get("driver_id"),
                "payload_json": json.dumps(payload, default=str),
                "dedupe_key": f"{dock_event_id}:CAPACITY_EVENT_CASCADE",
                "created_at": now_iso,
                "updated_at": now_iso,
            },
        )
    ).mappings().one()
    del ctx  # scope was already proven by the caller's _dock_in_scope
    return str(row["escalation_id"])


async def block_dock(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    dock_id: str,
    window_start: datetime,
    window_end: datetime,
    reason: str,
    idempotency_key: str,
) -> DockBlockResult:
    """FR-PLN-007 / section 7.5.1 `block_dock`.

    BLOCKED writes the `dock_status_events` row and returns the affected set; ALREADY_BLOCKED names
    the conflicting existing block so the planner can adjust their window instead of guessing
    (Flow 7 step 5). `Idempotency-Key` is required -- section 7.5.1 names it on this tool.
    """
    route = f"POST /api/v1/planner/docks/{dock_id}/block"
    start = _coerce_ts(window_start)
    end = _coerce_ts(window_end)
    if end <= start:
        # Mirrors dock_status_events_check (event_end_ts > event_start_ts) rather than letting the
        # database raise a CheckViolation the planner cannot read.
        raise AppError("window_end must be after window_start.", code="INVALID_WINDOW", status_code=422)
    req_hash = payload_hash(
        {"dock_id": dock_id, "window_start": start, "window_end": end, "reason": reason}
    )
    replay = await lookup_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if replay is not None:
        return DockBlockResult.model_validate({**replay["response"], "idempotent_replay": True})

    dock = await _dock_in_scope(session, ctx, dock_id)
    facility_id = str(dock["facility_id"])

    conflicting = await _overlapping_block(
        session, dock_id=dock_id, window_start=start, window_end=end
    )
    if conflicting is not None:
        result = DockBlockResult(
            as_of=_as_of(), code="ALREADY_BLOCKED", dock_id=dock_id, facility_id=facility_id,
            window_start=start, window_end=end, reason=reason,
            conflicting_event=conflicting, idempotency_key=idempotency_key,
        )
        await store_idempotency(
            session, key=idempotency_key, user_id=ctx.user_id, route=route,
            request_hash=req_hash, response=result.model_dump(), status_code=409,
        )
        await session.commit()
        return result

    affected = await _affected_appointments(
        session, dock_id=dock_id, window_start=start, window_end=end
    )
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    dock_event_id = new_id("DEVT")
    await session.execute(
        text(
            """
            INSERT INTO public.dock_status_events (
              dock_event_id, dock_id, event_type, event_start_ts, event_end_ts, reason, created_at
            ) VALUES (
              :dock_event_id, :dock_id, :event_type, :event_start_ts, :event_end_ts, :reason, :created_at
            )
            """
        ),
        {
            "dock_event_id": dock_event_id,
            "dock_id": dock_id,
            "event_type": MANUAL_BLOCK_EVENT_TYPE,
            # timestamptz columns -> datetime binds. `created_at` is the odd one out: it is still
            # `text` on this table (never converted by E1.1), so it takes the ISO string and would
            # raise a DataError if given a datetime. Verified live 2026-08-23.
            "event_start_ts": start,
            "event_end_ts": end,
            "reason": reason,
            "created_at": now_iso,
        },
    )
    escalation_id = await _open_capacity_cascade(
        session, ctx, facility_id=facility_id, dock_event_id=dock_event_id, dock_id=dock_id,
        affected=affected, now_iso=now_iso,
    )
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id,
              old_value_json, new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :user_id, 'CREATE', 'dock_status_events', :entity_id,
              NULL, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"), "user_id": ctx.user_id, "entity_id": dock_event_id,
            "new_value_json": json.dumps(
                {
                    "event": "BLOCK_DOCK", "dock_id": dock_id, "event_start_ts": start,
                    "event_end_ts": end, "reason": reason, "affected_count": len(affected),
                    "escalation_id": escalation_id,
                },
                default=str,
            ),
            "created_at": now_iso,
        },
    )

    result = DockBlockResult(
        as_of=_as_of(), code="BLOCKED", dock_id=dock_id, facility_id=facility_id,
        dock_status_event_id=dock_event_id, window_start=start, window_end=end, reason=reason,
        affected_appointments=affected, affected_count=len(affected), escalation_id=escalation_id,
        idempotency_key=idempotency_key,
    )
    await store_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route,
        request_hash=req_hash, response=result.model_dump(),
    )
    await session.commit()
    return result


async def end_dock_block(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    dock_status_event_id: str,
) -> DockBlockResult:
    """FR-PLN-008 / section 7.5.1 `end_dock_block`.

    UNBLOCKED closes the window at now; NOT_BLOCKED covers both "already ended elsewhere" (Flow 8's
    stated cause) and "this event was never a block". No `Idempotency-Key`: section 7.5.1 names none
    for this tool, and none is invented -- the second call is naturally NOT_BLOCKED rather than a
    duplicate write.
    """
    event = (
        await session.execute(
            text(
                """
                SELECT e.dock_event_id, e.dock_id, e.event_type, e.event_start_ts, e.event_end_ts,
                       e.reason, d.facility_id
                FROM public.dock_status_events e
                JOIN public.docks d ON d.dock_id = e.dock_id
                WHERE e.dock_event_id = :dock_event_id
                FOR UPDATE OF e
                """
            ),
            {"dock_event_id": dock_status_event_id},
        )
    ).mappings().first()
    if event is None:
        raise AppError("Dock status event not found.", code="NOT_FOUND", status_code=404)
    facility_id = str(event["facility_id"])
    assert_facility_write_scope(ctx, facility_id)

    now = datetime.now(timezone.utc)
    already_ended = event["event_end_ts"] is not None and event["event_end_ts"] <= now
    if str(event["event_type"]) not in BLOCKING_EVENT_TYPES or already_ended:
        return DockBlockResult(
            as_of=_as_of(), code="NOT_BLOCKED", dock_id=str(event["dock_id"]),
            facility_id=facility_id, dock_status_event_id=dock_status_event_id,
            window_start=event["event_start_ts"], window_end=event["event_end_ts"],
            reason=event["reason"],
        )

    # Truncating to `now` rather than deleting keeps the outage history intact: the hours the dock
    # really was down stay recorded, and only the *future* part of the window is released. Deleting
    # the row would rewrite history and make a past booking look as though it had never been
    # blocked. The CHECK (event_end_ts > event_start_ts) forbids truncating a block that has not
    # started yet, so one that is still entirely in the future is ended at its own start instead.
    new_end = now if now > event["event_start_ts"] else event["event_start_ts"]
    if new_end == event["event_start_ts"]:
        await session.execute(
            text("DELETE FROM public.dock_status_events WHERE dock_event_id = :dock_event_id"),
            {"dock_event_id": dock_status_event_id},
        )
        new_end = None
    else:
        await session.execute(
            text(
                """
                UPDATE public.dock_status_events
                SET event_end_ts = :event_end_ts
                WHERE dock_event_id = :dock_event_id
                """
            ),
            {"event_end_ts": new_end, "dock_event_id": dock_status_event_id},
        )
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id,
              old_value_json, new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :user_id, 'UPDATE', 'dock_status_events', :entity_id,
              :old_value_json, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"), "user_id": ctx.user_id, "entity_id": dock_status_event_id,
            "old_value_json": json.dumps({"event_end_ts": event["event_end_ts"]}, default=str),
            "new_value_json": json.dumps(
                {"event": "END_DOCK_BLOCK", "event_end_ts": new_end}, default=str
            ),
            "created_at": now.isoformat(),
        },
    )
    await session.commit()
    return DockBlockResult(
        as_of=_as_of(), code="UNBLOCKED", dock_id=str(event["dock_id"]), facility_id=facility_id,
        dock_status_event_id=dock_status_event_id, window_start=event["event_start_ts"],
        window_end=new_end, reason=event["reason"],
    )


# --- get_dock_board (E5.3 states 2/22, issue #53's `dockBoardEnabled` third gate) --------------

# `03-planner-dock-board/screens.md` section 3 and `stitch-prompts.md` section 8 both fix the axis at
# "four hours, or until closing time, whichever comes sooner". Four is the design's number, not a
# tunable, so it is a constant here rather than a settings key; the query parameter below can only
# NARROW it, so a caller cannot widen the board past what the design bounds.
BOARD_HORIZON_HOURS = 4
BOARD_HORIZON_ROLLING = "ROLLING_WINDOW"
BOARD_HORIZON_FACILITY_CLOSE = "FACILITY_CLOSE"


class BoardDock(BaseModel):
    """One lane. Every dock in the facility appears, occupied or not.

    `stitch-prompts.md` section 8's empty variant is explicit that a quiet facility still renders
    *"the lanes, still labelled"* rather than a blank panel, which is only possible if the dock list
    is independent of the occupancy list.
    """

    model_config = ConfigDict(extra="forbid")

    dock_id: str
    dock_code: str
    dock_type: str | None = None
    dock_status: str | None = None
    supports_refrigerated: bool | None = None
    max_vehicle_weight_kg: int | None = None


class BoardBar(BaseModel):
    """One occupied interval on one lane.

    `state` is the value `components.md` section 3's nine-row mapping table keys off, and it is
    reported verbatim rather than pre-classified into a bar treatment: the design's own rule is that
    *"a new `dock_occupancy` state added later gets a mapping-table row, not a bespoke branch"*, and
    a server that collapsed nine values into three would move that table out of the one file the
    rule points at.

    `claim_source` distinguishes an appointment-backed claim from a D2 hold, because the two are
    different facts about the same lane -- the hold is the only one with an `expires_at`, and it is
    the only one whose bar is drawn dashed.
    """

    model_config = ConfigDict(extra="forbid")

    occupancy_id: str
    dock_id: str
    state: str
    claim_source: str
    appointment_id: str | None = None
    shipment_id: str | None = None
    order_reference: str | None = None
    window_start: datetime
    window_end: datetime
    hold_expires_at: datetime | None = None


class BoardBlock(BaseModel):
    """An outage window. D1 (section 0.9 point 9) makes `dock_status_events` the single authority for
    availability, so the board draws its hatch from this and never from
    `appointment_slots.slot_status = 'BLOCKED'`, which section 0.9 already records as disagreeing.
    """

    model_config = ConfigDict(extra="forbid")

    dock_event_id: str
    dock_id: str
    event_type: str
    event_start_ts: datetime
    # NULL means open-ended -- the dock is out until someone ends the block. The client clamps it to
    # the horizon rather than the server inventing an end instant that no row asserts.
    event_end_ts: datetime | None = None
    reason: str | None = None


class DockBoard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    facility_id: str
    facility_name: str | None = None
    timezone: str | None = None
    horizon_start: datetime
    horizon_end: datetime
    horizon_end_reason: str
    docks: list[BoardDock]
    bars: list[BoardBar]
    blocks: list[BoardBlock]
    # The board cannot draw a HELD bar on a deploy where the D2 path is off, and saying so in the
    # payload is what lets the client render an honest legend instead of a state that can never
    # appear. Same "never silently identical" discipline as the queue's `interval_source`.
    holds_enabled: bool


def _board_horizon_end(
    now: datetime, *, timezone_name: str | None, close_time: Any, requested_hours: int | None
) -> tuple[datetime, str]:
    """`(horizon_end, reason)` -- four hours, or facility close, whichever is sooner.

    The close-time clamp is computed here rather than left to the client for the reason U48 states
    generally and `screens.md` section 3 states for this axis specifically: the facility's timezone
    and `close_time` are server facts, and a browser deriving "when does Jaipur shut" from a local
    clock is exactly the wrong-day hazard the dated-interval rule exists against. `ZoneInfo` and the
    `time.fromisoformat` parse mirror `scheduling/feasibility.py::_facility_window_ok` rather than
    being re-derived, so "closed" means one thing on both the board and the booking path.

    A malformed or absent `close_time`/`timezone` falls back to the rolling window rather than
    raising: a board that renders four hours is a smaller failure than a board that renders nothing,
    and the reason field says which of the two bounds was used.
    """
    rolling_hours = BOARD_HORIZON_HOURS
    if requested_hours is not None and 0 < requested_hours < BOARD_HORIZON_HOURS:
        # Narrowing only. A caller cannot widen past the design's bound.
        rolling_hours = requested_hours
    rolling_end = now + timedelta(hours=rolling_hours)
    if not timezone_name or close_time is None:
        return rolling_end, BOARD_HORIZON_ROLLING
    try:
        tz = ZoneInfo(str(timezone_name))
        closes_at = time.fromisoformat(str(close_time).strip())
    except (ValueError, ZoneInfoNotFoundError):
        return rolling_end, BOARD_HORIZON_ROLLING
    local_now = now.astimezone(tz)
    close_local = datetime.combine(local_now.date(), closes_at, tzinfo=tz)
    close_utc = close_local.astimezone(timezone.utc)
    # Only clamp when close is genuinely ahead of now: a board opened after closing time keeps its
    # rolling window rather than collapsing to a zero-width axis with no lanes to read.
    if now < close_utc < rolling_end:
        return close_utc, BOARD_HORIZON_FACILITY_CLOSE
    return rolling_end, BOARD_HORIZON_ROLLING


async def _board_blocks(
    session: AsyncSession, *, facility_id: str, window_start: datetime, window_end: datetime
) -> list[BoardBlock]:
    """Outage windows overlapping the horizon, for every dock in the facility.

    Same half-open overlap predicate as `_overlapping_block` (and as the feasibility scan), so a
    hatch appears on the board exactly when Stage 1 would refuse the interval -- a board that
    disagreed with the booking path about what is blocked would be worse than no board.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT e.dock_event_id, e.dock_id, e.event_type, e.event_start_ts,
                       e.event_end_ts, e.reason
                FROM public.dock_status_events e
                JOIN public.docks d ON d.dock_id = e.dock_id
                WHERE d.facility_id = :facility_id
                  AND e.event_type = ANY(:blocking_types)
                  AND e.event_start_ts < :window_end
                  AND (e.event_end_ts IS NULL OR e.event_end_ts > :window_start)
                ORDER BY e.dock_id ASC, e.event_start_ts ASC
                """
            ),
            {
                "facility_id": facility_id,
                "blocking_types": list(BLOCKING_EVENT_TYPES),
                "window_start": window_start,
                "window_end": window_end,
            },
        )
    ).mappings().all()
    return [
        BoardBlock(
            dock_event_id=str(row["dock_event_id"]),
            dock_id=str(row["dock_id"]),
            event_type=str(row["event_type"]),
            event_start_ts=_coerce_ts(row["event_start_ts"]),
            event_end_ts=_coerce_ts(row["event_end_ts"]) if row["event_end_ts"] else None,
            reason=row.get("reason"),
        )
        for row in rows
    ]


async def get_dock_board(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    facility_id: str | None = None,
    horizon_hours: int | None = None,
    clock: Clock | None = None,
) -> DockBoard:
    """The Board tab's at-rest occupancy view (`03-planner-dock-board/screens.md` section 3).

    Not in section 7.5.1's tool catalog, and flagged as an addition rather than quietly folded in --
    the same discipline `get_dock_block_impact` states for itself. It is a pure read composed from
    three existing authorities and adds no new one: `docks` for the lanes,
    `repositories/operations.py::list_live_dock_occupancy` for the bars (D1's single overlap truth,
    made hold-aware by issue #84) and `dock_status_events` for the outage hatches (D1's single
    availability authority).

    **`facility_id` is a narrowing request, never a scope assertion** (section 7.5 principle 1 /
    M15): it goes through `resolve_facility_scope`, so a `WAREHOUSE_PLANNER` may only ever name
    their own facility and an `ADMIN`'s global read scope is what the parameter exists for.
    `require_facility=True` for the same reason `get_planner_queue` uses it -- `screens.md` section 1
    fixes this surface at one facility, never "All facilities".

    **The occupancy read reuses the queue's, deliberately.** Building a second board-specific
    occupancy query would mean two answers to "what is on this dock right now", and issue #84 is
    precisely what happens when a second one drifts: its INNER JOIN to `appointments` made every D2
    hold invisible, so the displacement preview said "nobody would be hurt" about capacity the
    database was already defending. One query, one answer, on both the queue's displacement check
    and the board's bars.

    `include_holds` follows `TWO_PHASE_HOLD_ENABLED` rather than being always-on, because
    `dock_occupancy.state` does not exist until the D2 migration is applied and PostgreSQL resolves
    column references at parse time -- naming it on an unmigrated database fails the whole read.
    The flag's value is returned as `holds_enabled` so the client can say a HELD bar is currently
    unrenderable rather than silently drawing a legend entry nothing can fill.
    """
    scope_facility = resolve_facility_scope(ctx, facility_id, require_facility=True)
    if scope_facility is None:  # pragma: no cover - require_facility=True already guarantees this
        raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)

    now = resolve_clock(clock).now()
    facility = (
        await session.execute(
            text(
                """
                SELECT facility_id, facility_name, timezone, close_time
                FROM public.facilities
                WHERE facility_id = :facility_id
                """
            ),
            {"facility_id": scope_facility},
        )
    ).mappings().first()
    horizon_end, horizon_reason = _board_horizon_end(
        now,
        timezone_name=facility["timezone"] if facility else None,
        close_time=facility["close_time"] if facility else None,
        requested_hours=horizon_hours,
    )

    docks = await facilities_repo.list_docks(session, scope_facility)
    holds_enabled = get_settings().two_phase_hold_enabled
    occupancy = await operations_repo.list_live_dock_occupancy(
        session,
        facility_id=scope_facility,
        range_start=now,
        range_end=horizon_end,
        active_statuses=list(ACTIVE_APPOINTMENT_STATUSES),
        include_holds=holds_enabled,
        hold_states=list(CAPACITY_CONSUMING_STATES),
    )
    blocks = await _board_blocks(
        session, facility_id=scope_facility, window_start=now, window_end=horizon_end
    )

    bars = [
        BoardBar(
            occupancy_id=str(row["occupancy_id"]),
            dock_id=str(row["dock_id"]),
            state=str(row["appointment_status"]),
            # The flag-off statement has no `claim_source` column at all (it INNER-joins
            # `appointments`, so every row it can return is appointment-backed by construction).
            # Defaulting rather than requiring it keeps this function working against both shapes.
            claim_source=str(row.get("claim_source") or CLAIM_SOURCE_APPOINTMENT),
            appointment_id=str(row["appointment_id"]) if row.get("appointment_id") else None,
            shipment_id=str(row["shipment_id"]) if row.get("shipment_id") else None,
            order_reference=row.get("order_reference"),
            window_start=_coerce_ts(row["window_start"]),
            window_end=_coerce_ts(row["window_end"]),
            hold_expires_at=(
                _coerce_ts(row["hold_expires_at"]) if row.get("hold_expires_at") else None
            ),
        )
        for row in occupancy
    ]

    return DockBoard(
        as_of=_as_of(),
        facility_id=scope_facility,
        facility_name=facility["facility_name"] if facility else None,
        timezone=facility["timezone"] if facility else None,
        horizon_start=now,
        horizon_end=horizon_end,
        horizon_end_reason=horizon_reason,
        docks=[
            BoardDock(
                dock_id=str(dock["dock_id"]),
                dock_code=str(dock["dock_code"]),
                dock_type=dock.get("dock_type"),
                dock_status=dock.get("dock_status"),
                supports_refrigerated=(
                    bool(dock["supports_refrigerated"])
                    if dock.get("supports_refrigerated") is not None
                    else None
                ),
                max_vehicle_weight_kg=dock.get("max_vehicle_weight_kg"),
            )
            for dock in docks
        ],
        bars=bars,
        blocks=blocks,
        holds_enabled=holds_enabled,
    )


__all__ = [
    "BLOCKING_EVENT_TYPES",
    "BOARD_HORIZON_HOURS",
    "DEFAULT_QUEUE_LIMIT",
    "MANUAL_BLOCK_EVENT_TYPE",
    "MAX_QUEUE_LIMIT",
    "PHYSICALLY_WAITING_QUEUE_STATES",
    "SNAPSHOT_ALGORITHM",
    "BoardBar",
    "BoardBlock",
    "BoardDock",
    "DockBlockImpact",
    "DockBlockResult",
    "DockBoard",
    "PlannerQueue",
    "PlannerQueueRow",
    "block_dock",
    "end_dock_block",
    "get_dock_block_impact",
    "get_dock_board",
    "get_planner_queue",
]
