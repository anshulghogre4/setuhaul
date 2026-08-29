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
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, resolve_clock
from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.repositories import operations as operations_repo
from app.repositories.scope import assert_facility_write_scope, resolve_facility_scope
from app.scheduling.constraints import load_scheduling_constraints

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

# `facility_checkins.queue_state` values that mean "this driver is physically waiting at the gate"
# -- section 7.3's third ordering term, "queue_state in WAITING_*". Read off the live CHECK
# constraint (baseline migration line 220): NOT_QUEUED / WAITING_EARLY / WAITING_LATE /
# WAITING_DOCK_UNAVAILABLE / CALLED_TO_DOCK / IN_DOCK / COMPLETED. CALLED_TO_DOCK and IN_DOCK are
# deliberately excluded: that truck is being served, not burning detention in the yard, which is
# the metric section 13.1 asks this term to express.
PHYSICALLY_WAITING_QUEUE_STATES = ("WAITING_EARLY", "WAITING_LATE", "WAITING_DOCK_UNAVAILABLE")

# Section 7.3 names the three composite-urgency terms and their intent but assigns no weights, so
# these two numbers are an implementation choice and are stated as one rather than buried:
#
#   * TTL_PRESSURE_MAX = 1000 -- exactly one priority step in the shipped `ranking_policy`
#     (CRITICAL 4000 / HIGH 3000 / NORMAL 2000 / LOW 1000). A request that has burnt its whole D9
#     clock is therefore promoted by one band and no further: an expiring NORMAL ties a fresh HIGH
#     and can never outrank a fresh CRITICAL. That is what stops this being "pure TTL ordering",
#     which section 7.3 rejects for the same reason it rejects FIFO -- both bury the seeded SHP1014
#     case (CRITICAL, entered the queue late).
#   * WAITING_BONUS = 500 -- half a band. A driver physically waiting outranks a comparable one
#     still in transit, but never inverts a priority step on its own.
#
# Owner-reviewable: the calibration is defensible but it is not in any design document. The score
# and every term are returned per row (`PlannerQueueRow.urgency`) so the sort is inspectable
# instead of magic.
TTL_PRESSURE_MAX = 1000
WAITING_BONUS = 500

# Version tag on the `snapshot_hash` serialisation. Issue #61 owns the *enforcement* half (the
# `SNAPSHOT_STALE` refusal on confirm_request / counter_offer / bulk_confirm / apply_schedule_
# proposal); this producer-side value exists so that work has something real to formalise rather
# than a field to add to a shipped response later. Nothing consumes it yet, and the payload says so
# (`PlannerQueue.snapshot.enforced = False`) so no client mistakes its presence for a guarantee.
SNAPSHOT_ALGORITHM = "sha256/planner-queue-v1"
SNAPSHOT_NOT_ENFORCED_NOTE = (
    "snapshot_hash is produced but not yet validated on write: no tool accepts or refuses on it. "
    "Optimistic concurrency (SNAPSHOT_STALE / SNAPSHOT_DRIFT) is issue #61, which spans "
    "confirm_request, counter_offer, bulk_confirm and apply_schedule_proposal."
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


class QueueUrgency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int
    priority_score: int
    ttl_pressure: int
    waiting_bonus: int


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
    """
    conflicts: list[dict[str, Any]] = []
    for occupancy in live_occupancy:
        if str(occupancy["dock_id"]) != str(row["dock_id"]):
            continue
        if str(occupancy["appointment_id"]) == str(row["appointment_id"]):
            continue
        other_start = _coerce_ts(occupancy["window_start"])
        other_end = _coerce_ts(occupancy["window_end"])
        if not _overlaps(interval_start, interval_end, other_start, other_end):
            continue
        conflicts.append(
            {
                "appointment_id": occupancy["appointment_id"],
                "shipment_id": occupancy["shipment_id"],
                "order_reference": occupancy.get("order_reference"),
                "appointment_status": occupancy["appointment_status"],
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


def _urgency(
    *,
    priority_code: str,
    priority_scores: dict[str, int],
    ttl_remaining_seconds: int,
    ttl_total_seconds: int,
    physically_waiting: bool,
) -> QueueUrgency:
    """Section 7.3's composite urgency as one inspectable number.

    A *score*, not a lexicographic sort, because section 7.3 rejects both pure FIFO and pure TTL
    ordering by name -- either one buries the seeded SHP1014 case. See `TTL_PRESSURE_MAX` /
    `WAITING_BONUS` above for the calibration and why those two numbers are stated rather than
    tuned in silence.
    """
    priority_score = priority_scores.get(
        priority_code, priority_scores.get("UNKNOWN", 500)
    )
    if ttl_total_seconds <= 0:
        burnt = 1.0
    else:
        burnt = 1.0 - (ttl_remaining_seconds / ttl_total_seconds)
    burnt = min(1.0, max(0.0, burnt))
    ttl_pressure = int(round(TTL_PRESSURE_MAX * burnt))
    waiting_bonus = WAITING_BONUS if physically_waiting else 0
    return QueueUrgency(
        score=priority_score + ttl_pressure + waiting_bonus,
        priority_score=priority_score,
        ttl_pressure=ttl_pressure,
        waiting_bonus=waiting_bonus,
    )


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
        live_occupancy = await operations_repo.list_live_dock_occupancy(
            session,
            facility_id=scope_facility,
            range_start=range_start,
            range_end=range_end,
            active_statuses=list(ACTIVE_APPOINTMENT_STATUSES),
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
                    conflict_ids=[str(c["appointment_id"]) for c in conflicts],
                ),
            )
        )

    # Highest urgency first, `appointment_id` ascending as the stable tiebreaker -- the same
    # "no randomness, deterministic tiebreaker" posture `ranking_policy.ordered_factors` ends on.
    # A stable order matters more here than it looks: U19 freezes the sort while a row has focus,
    # and a sort that could reorder equal-scoring rows between two polls would move a row out from
    # under a planner mid-decision.
    items.sort(key=lambda item: (-item.urgency.score, item.appointment_id))

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
            enforced=False,
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


async def _affected_appointments(
    session: AsyncSession, *, dock_id: str, window_start: datetime, window_end: datetime
) -> list[dict[str, Any]]:
    """The live dock-time intervals the proposed block would strand.

    Reads `dock_occupancy` -- D1's true-interval table -- not `appointment_slots`, because a 75-min
    unload booked into a 60-min slot occupies time the slot row cannot see (section 6.2 #1). The
    status filter lives on `appointments`; `dock_occupancy` carries no status column of its own
    (verified live 2026-08-23), so the join is what restricts the set to the
    CONFIRMED / PENDING_CONFIRMATION / IN_PROGRESS rows section 7.5.1 names.
    """
    rows = (
        await session.execute(
            text(
                """
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
            ),
            {
                "dock_id": dock_id,
                "active_statuses": list(ACTIVE_APPOINTMENT_STATUSES),
                "window_start": window_start,
                "window_end": window_end,
            },
        )
    ).mappings().all()
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
                "appointment_id": item["appointment_id"],
                "shipment_id": item["shipment_id"],
                "appointment_status": item["appointment_status"],
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
                ON CONFLICT (dedupe_key) DO UPDATE
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


__all__ = [
    "BLOCKING_EVENT_TYPES",
    "DEFAULT_QUEUE_LIMIT",
    "MANUAL_BLOCK_EVENT_TYPE",
    "MAX_QUEUE_LIMIT",
    "PHYSICALLY_WAITING_QUEUE_STATES",
    "SNAPSHOT_ALGORITHM",
    "DockBlockImpact",
    "DockBlockResult",
    "PlannerQueue",
    "PlannerQueueRow",
    "block_dock",
    "end_dock_block",
    "get_dock_block_impact",
    "get_planner_queue",
]
