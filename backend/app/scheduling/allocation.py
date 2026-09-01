from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.core.settings import get_settings
from app.repositories.scope import assert_shipment_visible
from app.scheduling.constraints import load_scheduling_constraints
from app.scheduling.feasibility import (
    active_facility_rules,
    evaluate_candidate_slot,
    explain_slot_eligibility,
    find_feasible_slots,
)

# Underscore-prefixed on purpose in `feasibility`, imported here on purpose too: these are the
# *single* definitions of "inside the facility's operating window" and "the facility-local time of
# an instant" that Stage 1 uses when it ranks an option. `bulk_confirm`'s fourth safe-batch
# predicate (section 7.3: "start inside operating hours and before LAST_NEW_START_TIME") has to mean
# exactly what Stage 1 means by it, and a second copy here is precisely the drift that would let the
# batch path confirm something the individual path would refuse. Borrowing a private helper is the
# lesser evil; promoting them is a `feasibility.py` change and that file is not this pass's.
from app.scheduling.feasibility import (  # noqa: E402  (grouped with its own explanation)
    _facility_window_ok,
    _parse_local_time,
    _to_local,
)
from app.scheduling.snapshot import (
    batch_snapshot_hash,
    describe_snapshot_drift,
    displacement_conflicts,
    load_appointment_snapshot,
    load_appointment_snapshots,
)
from app.services import notification_outbox
from app.services.idempotency import lookup_idempotency, payload_hash, store_idempotency
from app.services.ids import new_id
from app.services.redis_memory import ConversationMemory

AUDIT_ACTION_BOOK_APPOINTMENT = "BOOK_APPOINTMENT"
AUDIT_ACTION_CANCEL_APPOINTMENT = "CANCEL_APPOINTMENT"
AUDIT_ACTION_CONFIRM_APPOINTMENT = "UPDATE"
AUDIT_ACTION_RESCHEDULE_APPOINTMENT = "RESCHEDULE_APPOINTMENT"
AUDIT_ACTION_REJECT_APPOINTMENT = "REJECT_APPOINTMENT"
AUDIT_ACTION_EXPIRE_APPOINTMENT = "EXPIRE_APPOINTMENT"
# E5.3 / issue #63: a counter-offer moves an appointment from one interval to another, which is
# structurally a reschedule, so it reuses that action_type. There is no COUNTER_OFFER value to use:
# `audit_logs_action_type_check` (migration 20260812010000, lines 46-52) admits a closed 13-value
# set and adding to it needs a migration this pass deliberately does not write. The discriminator
# lives in `new_value_json.transition` instead -- the same "generic action_type, specific payload"
# shape `gate_yard_service._write_audit` already uses for exactly this reason, and what makes
# section 7.3's "reject-with-counter-offer vs reject-flat" metric answerable today.
AUDIT_ACTION_COUNTER_OFFER = AUDIT_ACTION_RESCHEDULE_APPOINTMENT
AUDIT_TRANSITION_COUNTER_OFFERED = "COUNTER_OFFERED"
# Issue #64 / section 7.5.1 `hold_for_information`. Same "generic action_type, specific payload"
# shape as the counter-offer above, and for the identical reason: `audit_logs_action_type_check`
# admits a closed sixteen-value set (last set by migration 20260829134929, lines 290-296) and none
# of them is hold-for-information. The generic verb is `UPDATE` -- the transition really is an
# update of one column on an existing row, not a new lifecycle event -- and the discriminator lives
# in `new_value_json.transition`.
#
# `transition` rather than `event`: this module already established `transition` for the
# counter-offer, while `gate_yard_service`/`planner_service`/the admin console use `event`. Two
# names for one idea across the codebase is real (reported on #104 rather than fixed here, since
# converging them means touching four services' write paths); adding a *third* spelling, or writing
# both keys on this one row, would make it worse rather than better.
AUDIT_ACTION_HOLD_FOR_INFORMATION = "UPDATE"
AUDIT_TRANSITION_HELD_FOR_INFO = "HELD_FOR_INFO"
ACTIVE_APPOINTMENT_STATUSES = ("PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS")

# section 7.5.1's controlled vocabulary for `reject_request`, verbatim: *"`reason_code` is an enum
# precisely because it is rendered to the driver -- free prose here becomes an unreviewed
# customer-facing message."* Issue #66. Enforced with a 422 naming the supported set, which is
# exactly the shape `escalation_service.RESOLVE_REASON_CODES` / `CANCEL_REASON_CODES` already use --
# this was an inconsistency between two sibling flows, not a product-wide posture, so it is fixed by
# converging on the existing pattern rather than by inventing a third one.
REJECTION_REASON_CODES = frozenset(
    {"CAPACITY", "RULE_VIOLATION", "PRIORITY_CONFLICT", "SAFETY", "DATA_CONFLICT"}
)

# `Source: assumption, untested.` section 7.5.1 gives `counter_offer` a `reason_code` argument but
# never names its vocabulary, and no seeded case grounds one. Reusing the reject set is the
# defensible inference: a counter-offer's reason answers the same question a rejection's does ("why
# not the interval you asked for"), it is rendered to the same driver, and a second vocabulary for
# the same question would be two things to keep in sync. Stated here rather than silently assumed,
# the same epistemic-honesty posture `escalation_service`'s SLA budgets use.
COUNTER_OFFER_REASON_CODES = REJECTION_REASON_CODES

# section 7.3's five safe-batch predicates, named so a `bulk_confirm` outcome can say which one an
# id failed instead of only that it was skipped. section 7.5.1: the server re-evaluates all five
# *at press time*, "rather than trusting the client's selection" -- that re-check is what keeps D6's
# human authority real instead of ceremonial.
PREDICATE_ZERO_DISPLACEMENT = "ZERO_DISPLACEMENT"
PREDICATE_EXACT_DOCK_MATCH = "EXACT_DOCK_MATCH"
PREDICATE_ETA_CONFIDENCE_NOT_LOW = "ETA_CONFIDENCE_NOT_LOW"
PREDICATE_INSIDE_OPERATING_WINDOW = "INSIDE_HOURS_AND_BEFORE_LAST_NEW_START"
PREDICATE_NO_OPEN_ESCALATION = "NO_OPEN_ESCALATION"
SAFE_BATCH_PREDICATES = (
    PREDICATE_ZERO_DISPLACEMENT,
    PREDICATE_EXACT_DOCK_MATCH,
    PREDICATE_ETA_CONFIDENCE_NOT_LOW,
    PREDICATE_INSIDE_OPERATING_WINDOW,
    PREDICATE_NO_OPEN_ESCALATION,
)
# `escalation_queue.escalation_status` values that mean the case is still live. Terminal states are
# RESOLVED / CANCELLED (migration 20260823100000).
OPEN_ESCALATION_STATUSES = ("OPEN", "ACKNOWLEDGED", "IN_PROGRESS")
# `bulk_confirm` is a spike-clearing tool, not a bulk-mutation API. section 7.3's own load
# arithmetic caps a disruption spike at 20-35 requests inside 30 minutes, so a cap a little above
# that refuses an obviously-wrong call without ever refusing a real one.
MAX_BULK_CONFIRM_IDS = 50
ALLOCATION_UNIQUE_CONSTRAINTS = frozenset(
    {
        "ux_active_appointment_per_slot",
        "ux_current_active_appointment_per_shipment",
    }
)
# D1's real capacity invariant: EXCLUDE USING gist (dock_id WITH =, "window" WITH &&) on
# public.dock_occupancy. Verified live 2026-08-23 by reading pg_constraint -- contype 'x',
# name exactly as below. A partial unique index can only stop two rows claiming the *same*
# slot id; it cannot see a 75-minute unload booked at 11:00 colliding with a 12:00 booking,
# because those are different slot rows (SOLUTION_DESIGN.md section 5 Stage 3 / D1).
DOCK_OCCUPANCY_EXCLUSION_CONSTRAINT = "dock_occupancy_dock_id_window_excl"
# Every constraint here means the same thing to the caller: somebody else already holds this
# capacity, so refresh and retry. The two unique indexes stay as a belt-and-braces fast check
# while appointment_slots is still authoritative; SOLUTION_DESIGN.md section 5 Stage 3 says to
# keep them during migration and drop them only once dock_occupancy is the sole authority.
ALLOCATION_CONFLICT_CONSTRAINTS = ALLOCATION_UNIQUE_CONSTRAINTS | {
    DOCK_OCCUPANCY_EXCLUSION_CONSTRAINT
}


class RequestSlotCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=500)
    displayed_policy_version: str | None = Field(
        default=None,
        description="Policy version shown with the displayed option, if the client has it.",
    )
    displayed_recommendation_id: str | None = Field(default=None, max_length=100)
    client_message_id: str | None = Field(default=None, max_length=200)


class RequestSlotResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    status: str
    code: str
    shipment_id: str
    slot_id: str
    appointment_id: str | None = None
    policy_version: str
    appointment: dict[str, Any] | None = None
    conflict: dict[str, Any] | None = None
    refreshed_options: dict[str, Any] | None = None
    idempotency_key: str | None = None
    idempotent_replay: bool = False
    appointment_writes: int = 0
    # D2's `HELD` outcome (SOLUTION_DESIGN.md section 7.1, issue #53). All three are None on the
    # legacy single-phase path, so this stays a superset of the shape every existing caller,
    # stored idempotency response and test already reads -- adding the two-phase contract does not
    # invalidate a single replayed `SLOT_REQUESTED` row.
    hold_id: str | None = None
    hold_expires_at: str | None = None
    hold_ttl_seconds: int | None = None


class AppointmentRequestStatusResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    code: str
    shipment_id: str
    appointment_id: str | None = None
    appointment: dict[str, Any] | None = None
    history: list[dict[str, Any]]
    requires_human_confirmation: bool = False
    options_are_reserved: bool = False
    # Issue #83: a D2 hold has no `appointments` row (SS4), so it cannot be reported through
    # `appointment` and needs its own field. None whenever no live hold exists, which is always
    # true while TWO_PHASE_HOLD_ENABLED is off.
    hold: dict[str, Any] | None = None
    promise_state: str | None = None
    promise_state_source: str | None = None
    appointment_writes: int = 0


class CancelAppointmentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: str = Field(min_length=1, max_length=100)
    cancellation_reason: str = Field(min_length=1, max_length=500)
    client_message_id: str | None = Field(default=None, max_length=200)


class ConfirmAppointmentCommand(BaseModel):
    """section 7.5.1 `confirm_request` -- `appointment_id`, `snapshot_hash`, `Idempotency-Key`.

    **`warehouse_confirmation_ref` is optional, and that is a deliberate reversal** (issue #62).
    It shipped `required`, which would have blocked every confirm the planner console makes: the
    field appears in no design document, has no UI in any of the 30 planner artboards, and is not
    in section 7.5.1's three-argument list. It is a *warehouse's* external reference -- a WMS
    confirmation number -- so an inbound-integration field, not a planner input, and the planner
    console has no source for one. The column is nullable in the shipped schema
    (`20260805201923_setuhaul_baseline.sql:183`), so this is a contract fix, not a migration.

    Nothing is invented to fill the gap: when the argument is omitted the stored value is left
    exactly as it was (`COALESCE` in the UPDATE below), rather than stamping a synthesised
    reference that would read as a real warehouse acknowledgement. `AGENTS.md`: *"Never invent
    shipment, ETA, dock, appointment, capacity, or operational data."*
    """

    model_config = ConfigDict(extra="forbid")

    appointment_id: str = Field(min_length=1, max_length=100)
    # section 7.5 principle 3 -- required, exactly as `Idempotency-Key` already is on this route.
    # The router 400s without it; see `ConfirmAppointmentBody` in `routers/scheduling.py`.
    snapshot_hash: str = Field(min_length=1, max_length=128)
    warehouse_confirmation_ref: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class CounterOfferCommand(BaseModel):
    """section 7.5.1 `counter_offer` -- issue #63, `FR-PLN-002`, `flows-and-states.md` Flow 2.

    `dock_id` + `start_ts` rather than a `slot_id` because that is the catalog's own argument
    shape, and because the Board tab's picker hands the planner a point on a dock/time grid, not a
    slot row. The pair is resolved to an `appointment_slots` row server-side; an interval with no
    slot behind it is `INTERVAL_UNAVAILABLE`, not an invented slot.
    """

    model_config = ConfigDict(extra="forbid")

    appointment_id: str = Field(min_length=1, max_length=100)
    dock_id: str = Field(min_length=1, max_length=100)
    start_ts: datetime
    reason_code: str = Field(min_length=1, max_length=40)
    snapshot_hash: str = Field(min_length=1, max_length=128)
    note: str | None = Field(default=None, max_length=500)


class BulkConfirmCommand(BaseModel):
    """section 7.5.1 `bulk_confirm` -- issue #65, `FR-PLN-006`, `flows-and-states.md` Flow 6."""

    model_config = ConfigDict(extra="forbid")

    appointment_ids: list[str] = Field(min_length=1, max_length=MAX_BULK_CONFIRM_IDS)
    # The composite of the per-row hashes for exactly these ids -- see
    # `scheduling/snapshot.py::batch_snapshot_hash`.
    snapshot_hash: str = Field(min_length=1, max_length=128)
    warehouse_confirmation_ref: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class RescheduleAppointmentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: str = Field(min_length=1, max_length=100)
    new_slot_id: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    displayed_policy_version: str | None = Field(default=None, max_length=100)
    displayed_recommendation_id: str | None = Field(default=None, max_length=100)
    client_message_id: str | None = Field(default=None, max_length=200)


class RejectAppointmentCommand(BaseModel):
    """section 7.5.1 `reject_request` -- `appointment_id`, `reason_code`, `note?` (issue #66).

    The shipped field was `rejection_reason: str(min 1, max 500)` -- free prose, on a value that is
    rendered to the driver. Renamed to `reason_code` (the catalog's own argument name) and
    validated against `REJECTION_REASON_CODES` in the service, not here, so the refusal can name
    the supported set the way ops's sibling enums already do. `note` stays free text: it is the
    planner's internal annotation, not the customer-facing string.
    """

    model_config = ConfigDict(extra="forbid")

    appointment_id: str = Field(min_length=1, max_length=100)
    reason_code: str = Field(min_length=1, max_length=40)
    note: str | None = Field(default=None, max_length=500)


class ExpireAppointmentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: str = Field(min_length=1, max_length=100)
    expire_reason: str = Field(min_length=1, max_length=500)


class HoldForInformationCommand(BaseModel):
    """section 7.5.1 `hold_for_information` -- `appointment_id`, `question`, `Idempotency-Key`.

    Issue #64, `FR-PLN-004`, `03-planner-dock-board/flows-and-states.md` Flow 4.

    **The catalog's argument list is taken literally, and the two absences are the interesting
    part.** There is no `snapshot_hash` here, unlike `confirm_request`/`counter_offer`/
    `bulk_confirm`: section 7.5's principle 3 attaches that guard to *"anything that consumes
    capacity"*, and this tool consumes none -- the interval is already claimed by the
    `PENDING_CONFIRMATION` row and stays claimed either way. Adding one would have refused a
    planner whose queue row had merely re-rendered, for an action that cannot hurt a third party.
    There is likewise no `facility_id`: M15, and the shipment's facility is read server-side.

    `question` is mandatory (Flow 4 step 1: *"mandatory question field"*) and is deliberately free
    text rather than an enum, unlike `reject_request`'s `reason_code`. The distinction the design
    draws is about what reaches the driver as an unreviewed customer-facing string: a rejection's
    reason is *rendered* to the driver from a controlled vocabulary, whereas the whole point of a
    hold is that the planner has an actual question nobody enumerated in advance.
    """

    model_config = ConfigDict(extra="forbid")

    appointment_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=500)


class HoldForInformationResult(BaseModel):
    """Typed outcome for `hold_for_information` -- `HELD_FOR_INFO` + `new_deadline`.

    Separate from `AppointmentTransitionResult` because this transition changes no
    `appointment_status`: the row stays `PENDING_CONFIRMATION` throughout (section 4's promise
    lifecycle has no paused state, and inventing one would need a migration and a widened
    `appointments_appointment_status_check`). What changes is the deadline, so the deadline is what
    the result is shaped around.
    """

    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    # Unchanged by construction, returned so a caller never has to infer it: a held request is
    # still a pending request.
    status: str = "PENDING_CONFIRMATION"
    code: str = "HELD_FOR_INFO"
    shipment_id: str
    appointment_id: str
    question: str
    # section 7.5.1's named return value.
    new_deadline: str
    # What the deadline was before the extension, so the UI can show what the hold actually bought
    # and an audit reader can reconstruct it without recomputing `booked_at + ttl` themselves.
    previous_deadline: str
    extension_minutes: int
    # The one-shot cap, made explicit in the success response rather than only in the refusal: a
    # planner who just used the hold needs the Hold affordance to go Disabled immediately
    # (`components.md` section 1's rule, `edge-cases.md` #6 -- prevention over error handling), and
    # a client that has to infer "used" from the presence of `new_deadline` would be guessing.
    hold_used: bool = True
    appointment: dict[str, Any] | None = None
    idempotency_key: str
    idempotent_replay: bool = False
    appointment_writes: int = 1


class AppointmentTransitionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    status: str
    code: str
    shipment_id: str
    appointment_id: str
    appointment: dict[str, Any] | None = None
    idempotency_key: str
    idempotent_replay: bool = False
    appointment_writes: int = 1
    # The token the caller should carry into its *next* write on this row. Present on success so a
    # planner acting twice in a row (confirm, then something else) never has to re-read the queue
    # just to obtain a fresh hash.
    snapshot_hash: str | None = None


class CounterOfferResult(BaseModel):
    """Typed outcome for `counter_offer` (section 7.5 principle 2 -- never prose)."""

    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    code: str
    shipment_id: str
    appointment_id: str
    reason_code: str
    # section 7.5.1: "COUNTER_OFFERED + the new option set sent to the driver". A planner picks one
    # interval on the board, so the offered set is that one interval -- returned as a list because
    # the catalog says "set" and because a future multi-pick would not change the shape.
    offered_options: list[dict[str, Any]] = Field(default_factory=list)
    appointment: dict[str, Any] | None = None
    idempotency_key: str
    idempotent_replay: bool = False
    appointment_writes: int = 0
    snapshot_hash: str | None = None


class BulkConfirmOutcome(BaseModel):
    """One id's result inside a `bulk_confirm` -- section 7.5.1's "per-id outcome list"."""

    model_config = ConfigDict(extra="forbid")

    appointment_id: str
    shipment_id: str | None = None
    code: str
    detail: str | None = None
    # Which of section 7.3's five predicates this id failed, empty when it passed all five. Named
    # rather than counted so Flow 6 step 4's "SHP1013 no longer eligible" toast has something real
    # to say.
    failed_predicates: list[str] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    snapshot_hash: str | None = None


class BulkConfirmResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    code: str = "BULK_CONFIRM_COMPLETED"
    requested: int
    confirmed: int
    skipped: int
    # False means the board moved between selection and press. It does not by itself refuse the
    # batch -- see `bulk_confirm`'s docstring for why, and for the fork that decision leaves open.
    snapshot_hash_matched: bool
    expected_snapshot_hash: str
    current_snapshot_hash: str
    outcomes: list[BulkConfirmOutcome]
    idempotency_key: str
    idempotent_replay: bool = False
    appointment_writes: int = 0


# Bind types are not interchangeable, and getting one wrong is a hard runtime failure rather than a
# silent coercion. After E1.1's conversion
# (supabase/migrations/20260823060000_d1_correctness_bedrock.sql:44) every `appointments` timestamp
# column touched below -- booked_at, confirmed_at, cancelled_at, updated_at -- is `timestamptz`, and
# asyncpg 0.31.0 encodes a timestamptz parameter with its datetime codec only: handing it a `str`
# raises `asyncpg.exceptions.DataError: invalid input for query argument $1 ... (expected a
# datetime.date or datetime.datetime instance, got 'str')`. `audit_logs.created_at` is the opposite
# case -- still `text`, never converted -- so it takes the ISO string and would raise the mirror-image
# DataError if given a datetime. Both directions verified live 2026-08-23 with a read-only bind probe.
# So every transition below derives two names from one instant: `now` for the timestamptz binds,
# `now_iso` for the text ones. Same pattern as expiry.py:270.
def _as_of() -> str:
    """Wall clock as an ISO string, for the `as_of` field of a *response model* only.

    Never bind this into a SQL parameter for one of the converted columns -- see the note above.
    """
    return datetime.now(timezone.utc).isoformat()


def _assert_driver_scope(ctx: ExecutionContext, shipment: dict[str, Any]) -> None:
    if not ctx.is_driver or not ctx.driver_id:
        raise AppError("Only the assigned driver may request a slot.", code="FORBIDDEN", status_code=403)
    if shipment["driver_id"] != ctx.driver_id:
        raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)


def _assert_shipment_scope(
    ctx: ExecutionContext, shipment: dict[str, Any], *, require_write: bool = False
) -> None:
    """Driver/operator/global scoping for a single shipment.

    `require_write=True` is mandatory for callers that mutate an appointment (cancel, reschedule).
    The global tier then demands `is_admin` — write authority — rather than mere global visibility,
    so TRANSPORT_MANAGER / REGIONAL_OPERATIONS_HEAD (global *read-only* personas) can still see a
    cross-facility appointment but cannot cancel or reschedule it. Read callers pass the default.

    E2.2 (issue #22): the rule itself now lives once in `repositories.scope`; this stays only as
    the adapter that unpacks a shipment row for the many call sites in this module.
    """
    assert_shipment_visible(
        ctx,
        shipment_driver_id=shipment["driver_id"],
        shipment_facility_id=shipment["destination_facility_id"],
        require_write=require_write,
    )


def _assert_ops_scope(ctx: ExecutionContext, shipment: dict[str, Any]) -> None:
    """Write-side gate for confirm/reject/expire and the ops branch of request_slot.

    `is_admin` here is deliberate and must stay: this helper only guards mutations, so the
    global tier needs write authority. Do not relax it to `has_global_read_scope`.
    """
    if ctx.is_operator:
        if shipment["destination_facility_id"] != ctx.facility_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
        return
    if ctx.is_admin:
        return
    raise AppError("Only operations or admin may confirm appointments.", code="FORBIDDEN", status_code=403)


def appointment_request_status_code(status: str | None) -> tuple[str, bool]:
    if status is None:
        return "NO_APPOINTMENT_REQUEST", False
    normalized = status.upper()
    if normalized == "PENDING_CONFIRMATION":
        return "APPOINTMENT_PENDING_CONFIRMATION", True
    if normalized == "CONFIRMED":
        return "APPOINTMENT_CONFIRMED", False
    if normalized == "IN_PROGRESS":
        return "APPOINTMENT_IN_PROGRESS", False
    if normalized == "REJECTED":
        return "APPOINTMENT_REJECTED", False
    if normalized == "EXPIRED":
        return "APPOINTMENT_EXPIRED", False
    if normalized == "CANCELLED":
        return "APPOINTMENT_CANCELLED", False
    if normalized == "COMPLETED":
        return "APPOINTMENT_COMPLETED", False
    if normalized == "NO_SHOW":
        return "APPOINTMENT_NO_SHOW", False
    return "APPOINTMENT_STATUS_UNKNOWN", False


def _resolve_promise_state(
    status: Any, hold: dict[str, Any] | None
) -> tuple[str | None, str | None]:
    """Promise-state precedence for a status read (issue #83).

    Same three rules, and the same reasons, as
    `services/driver_reads.resolve_promise_state`: an active appointment outranks a live hold
    (reachable -- `confirm_held_slot` has an IntegrityError branch for exactly that overlap), a live
    hold outranks any non-active appointment, and otherwise the appointment answers. Duplicated
    rather than imported because `services/` sits *above* `scheduling/` in this codebase's layering
    and importing upward would invert it; the two are kept honest by
    `tests/unit/test_held_slot_lifecycle.py`, which asserts they agree case for case.
    """
    from app.scheduling import holds  # local: breaks the allocation <-> holds import cycle

    if status is not None and str(status) in ACTIVE_APPOINTMENT_STATUSES:
        return str(status), holds.PROMISE_STATE_SOURCE_APPOINTMENT
    if hold is not None:
        return holds.HOLD_PROMISE_STATE, holds.PROMISE_STATE_SOURCE_HOLD
    if status is not None:
        return str(status), holds.PROMISE_STATE_SOURCE_APPOINTMENT
    return None, None


def _already_actioned_error(
    appointment: dict[str, Any], *, attempted: str
) -> AppError:
    """The loser-facing half of SOLUTION_DESIGN.md section 7.5.1's race resolution.

    section 7.5.1 requires that when `confirm_request` and the D9 expiry sweeper hit the same row,
    *"the loser gets `ALREADY_ACTIONED` with the winning transition named"* -- section 9.2 #3 calls
    this the nastiest race in the design precisely because both actors believe they acted. A generic
    INVALID_APPOINTMENT_TRANSITION told the planner only that the click failed, not that a sweeper
    had released the interval a moment earlier, which is the difference between "refresh" and a
    reason.

    Costs no extra query: the winning status and its reason are already on the row the caller's
    `SELECT ... FOR UPDATE` returned. Under READ COMMITTED that is the *updated* version left behind
    by whoever committed first (PostgreSQL "Transaction Isolation" 13.2.1 -- SELECT FOR UPDATE locks
    and returns the updated row), which is exactly why the winner is readable here at all.
    """
    winner = str(appointment.get("appointment_status") or "UNKNOWN")
    reason = appointment.get("cancellation_reason")
    detail = f" Reason recorded: {reason}" if reason else ""
    return AppError(
        f"Cannot {attempted} this appointment: it is already {winner}.{detail}",
        code="ALREADY_ACTIONED",
        status_code=409,
    )


def _assert_reason_code(reason_code: str, allowed: frozenset[str], *, tool: str) -> str:
    """Enforce a controlled vocabulary, naming the supported set in the refusal.

    Same shape as `escalation_service.resolve_escalation` / `cancel_escalation` -- 422,
    `INVALID_REASON_CODE`, `detail` listing what is accepted. Deliberately not a pydantic `Literal`
    on the command: FastAPI would return a generic `VALIDATION_ERROR` that does not enumerate the
    vocabulary, and this project already answers this exact question one way on the ops surface
    (issue #66 is about the two siblings disagreeing, so the fix is to converge, not to add a third
    style).
    """
    normalised = reason_code.strip().upper()
    if normalised not in allowed:
        raise AppError(
            f"Unsupported reason_code '{reason_code}' for {tool}.",
            code="INVALID_REASON_CODE",
            status_code=422,
            detail=f"Supported: {', '.join(sorted(allowed))}.",
        )
    return normalised


def _snapshot_stale_error(snapshot: dict[str, Any], *, expected_hash: str) -> AppError:
    """section 7.5.1's `SNAPSHOT_STALE`, carrying what the row is *now*.

    `flows-and-states.md` Flow 1 step 5: the row re-renders with current data and the planner
    re-reads before deciding again -- *"never a silent retry with old context"*. A bare 409 would
    make a silent retry the obvious client behaviour, which is precisely what that line forbids, so
    the drift description travels in `detail`.
    """
    drift = describe_snapshot_drift(snapshot, expected_hash=expected_hash)
    return AppError(
        "The queue row changed since it was rendered; re-read it before deciding again.",
        code="SNAPSHOT_STALE",
        status_code=409,
        detail=json.dumps(drift, default=str),
    )


def _displacement_error(conflicts: list[dict[str, Any]], *, attempted: str) -> AppError:
    """section 7.5.1's `DISPLACEMENT_DETECTED` -- refuses, and names what appeared.

    Checked *before* `SNAPSHOT_STALE` on every path that checks both. The displacement set is
    inside the snapshot digest (see `scheduling/snapshot.py`), so a new conflict changes the hash
    too; if staleness were tested first this code could never fire and section 7.3's single most
    important field -- *"Confirming must never quietly hurt a third party"* -- would degrade into a
    generic "something moved".
    """
    named = ", ".join(
        str(conflict.get("appointment_id") or conflict.get("dock_event_id") or "?")
        for conflict in conflicts
    )
    return AppError(
        f"Cannot {attempted}: a conflict appeared on this dock interval since the row was "
        f"rendered ({named}).",
        code="DISPLACEMENT_DETECTED",
        status_code=409,
        detail=json.dumps({"reason_code": "DISPLACEMENT_DETECTED", "conflicts": conflicts}, default=str),
    )


async def _snapshot_guard(
    session: AsyncSession,
    *,
    appointment_id: str,
    expected_hash: str,
    attempted: str,
    actor_user_id: str,
) -> dict[str, Any]:
    """The section 7.5 principle-3 gate shared by `confirm_request` and `counter_offer`.

    Must be called **after** `_locked_appointment` has taken the row `FOR UPDATE`, and inside the
    same transaction: under READ COMMITTED that lock is what makes the values read here the
    committed ones the write is about to act on (PostgreSQL "Transaction Isolation" 13.2.1). Called
    before the lock it would be a race of its own.

    Costs one round trip. Returns the recomputed snapshot so the caller can hand its fresh
    `snapshot_hash` back in the success response.

    `actor_user_id` is threaded through for issue #98's lazy expiry inside
    `load_appointment_snapshot`, which needs an author for the `EXPIRE_HOLD` audit row it may
    write. It is required rather than defaulted so a future caller cannot opt out of it.
    """
    snapshot = await load_appointment_snapshot(
        session, appointment_id, actor_user_id=actor_user_id
    )
    if snapshot is None:
        raise AppError("Appointment not found.", code="APPOINTMENT_NOT_FOUND", status_code=404)
    conflicts = displacement_conflicts(snapshot)
    if conflicts:
        raise _displacement_error(conflicts, attempted=attempted)
    if snapshot["snapshot_hash"] != expected_hash:
        raise _snapshot_stale_error(snapshot, expected_hash=expected_hash)
    return snapshot


def allocation_unique_constraint_name(exc: IntegrityError) -> str | None:
    """Name the allocation constraint an IntegrityError came from, or None if unrelated.

    Covers both allocation guards and D1's dock_occupancy exclusion constraint: asyncpg raises
    ExclusionViolationError (SQLSTATE 23P01) for the latter, which subclasses
    IntegrityConstraintViolationError and is therefore translated to the same
    sqlalchemy.exc.IntegrityError as a unique violation (verified against the pinned
    SQLAlchemy 2.0.51 asyncpg dialect, _asyncpg_error_translate). One caller, one mapping --
    a second error-handling path would be a second thing to keep in sync.

    The string fallback is not belt-and-braces, it is the path that actually fires in
    production: that same dialect rebuilds its DBAPI error from only a message string
    ("%s: %s" % (type(error), error)) and copies over sqlstate but *not* constraint_name, so
    exc.orig has no constraint_name attribute under asyncpg. Postgres puts the constraint name
    in the primary message for both shapes -- 'duplicate key value violates unique constraint
    "..."' and 'conflicting key value violates exclusion constraint "..."'
    (src/backend/executor/execIndexing.c) -- so matching the message is reliable. The attribute
    check is kept first for drivers that do preserve it.
    """
    orig = getattr(exc, "orig", None)
    constraint_name = getattr(orig, "constraint_name", None)
    if constraint_name in ALLOCATION_CONFLICT_CONSTRAINTS:
        return str(constraint_name)
    message = str(exc)
    for name in ALLOCATION_CONFLICT_CONSTRAINTS:
        if name in message:
            return name
    return None


async def _reread_appointment(session: AsyncSession, appointment_id: str) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.shipment_id, a.slot_id, a.appointment_status,
                       a.booking_source, a.is_current, a.booked_at, a.confirmed_at,
                       a.cancelled_at, a.cancellation_reason, a.replaced_appointment_id,
                       a.warehouse_confirmation_ref, a.updated_at,
                       sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                WHERE a.appointment_id = :appointment_id
                """
            ),
            {"appointment_id": appointment_id},
        )
    ).mappings().first()
    return dict(row) if row else None


def replay_claim_is_active(appointment: dict[str, Any] | None) -> bool:
    if not appointment:
        return False
    status = str(appointment.get("appointment_status") or "")
    try:
        current = int(appointment.get("is_current") or 0)
    except (TypeError, ValueError):
        current = 0
    return status in ACTIVE_APPOINTMENT_STATUSES and current == 1


async def _store_request_idempotency(
    session: AsyncSession,
    *,
    persist: bool,
    key: str,
    user_id: str,
    route: str,
    request_hash: str,
    response: dict[str, Any],
    status_code: int,
) -> None:
    await store_idempotency(
        session,
        key=key,
        user_id=user_id,
        route=route,
        request_hash=request_hash,
        response=response,
        status_code=status_code,
    )
    if persist:
        await session.commit()


async def _locked_appointment(
    session: AsyncSession,
    *,
    shipment_id: str,
    appointment_id: str,
) -> dict[str, Any] | None:
    """Lock one appointment row for a transition. No status predicate, deliberately.

    `expiry.py`'s docstring explains why the predicate is absent: when the D9 sweeper commits first,
    this must still lock and return the *updated* row so `confirm_appointment` can refuse with
    `ALREADY_ACTIONED` naming the winning transition, rather than finding nothing and 404-ing.

    `expires_at` joined the projection with issue #64. It is the one-shot marker for
    `hold_for_information` -- the migration that added it says so in its own words
    (`20260829134929_d2_held_state_dock_occupancy.sql:252-256`: *"`expires_at IS NOT NULL` **is**
    the HOLD_ALREADY_USED marker. No separate boolean, no counter"*) -- and reading it here rather
    than in a second statement is what makes the cap race-proof: it arrives under the same
    `FOR UPDATE` as the status, so two planners pressing Hold at once serialise on the row lock and
    the loser re-reads a non-NULL value. A separate unlocked read could let both through.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT appointment_id, shipment_id, slot_id, appointment_status,
                       booking_source, is_current, booked_at, confirmed_at,
                       cancelled_at, cancellation_reason, replaced_appointment_id,
                       warehouse_confirmation_ref, updated_at, expires_at
                FROM public.appointments
                WHERE shipment_id = :shipment_id
                  AND appointment_id = :appointment_id
                FOR UPDATE
                """
            ),
            {"shipment_id": shipment_id, "appointment_id": appointment_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _shipment_for_status(session: AsyncSession, shipment_id: str) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT shipment_id, driver_id, destination_facility_id
                FROM public.shipments
                WHERE shipment_id = :shipment_id
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _appointment_request_status_row(
    session: AsyncSession,
    *,
    shipment_id: str,
    appointment_id: str | None,
) -> dict[str, Any] | None:
    params: dict[str, Any] = {"shipment_id": shipment_id}
    appointment_filter = ""
    if appointment_id:
        appointment_filter = "AND a.appointment_id = :appointment_id"
        params["appointment_id"] = appointment_id
    row = (
        await session.execute(
            text(
                f"""
                SELECT a.appointment_id, a.shipment_id, a.slot_id, a.appointment_status,
                       a.booking_source, a.is_current, a.booked_at, a.confirmed_at,
                       a.cancelled_at, a.cancellation_reason, a.replaced_appointment_id,
                       a.warehouse_confirmation_ref, a.updated_at,
                       sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts,
                       d.dock_code, d.dock_type
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                LEFT JOIN public.docks d ON d.dock_id = sl.dock_id
                WHERE a.shipment_id = :shipment_id
                  {appointment_filter}
                ORDER BY
                  CASE
                    WHEN a.is_current = 1
                     AND a.appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                    THEN 0
                    ELSE 1
                  END,
                  a.updated_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            params,
        )
    ).mappings().first()
    return dict(row) if row else None


async def _appointment_request_history(session: AsyncSession, shipment_id: str) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT appointment_id, shipment_id, slot_id, appointment_status,
                       booking_source, is_current, booked_at, confirmed_at,
                       cancelled_at, cancellation_reason, replaced_appointment_id,
                       warehouse_confirmation_ref, updated_at
                FROM public.appointments
                WHERE shipment_id = :shipment_id
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 10
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _active_appointment_for_slot(session: AsyncSession, slot_id: str) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT appointment_id, shipment_id, slot_id, appointment_status, is_current, updated_at
                FROM public.appointments
                WHERE slot_id = :slot_id
                  AND appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"slot_id": slot_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _current_active_appointment_for_shipment(session: AsyncSession, shipment_id: str) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT appointment_id, shipment_id, slot_id, appointment_status, is_current, updated_at
                FROM public.appointments
                WHERE shipment_id = :shipment_id
                  AND is_current = 1
                  AND appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                ORDER BY updated_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _claim_dock_occupancy(
    session: AsyncSession,
    *,
    appointment_id: str,
    shipment_id: str,
    slot_id: str,
    now: datetime,
    actor_user_id: str,
) -> dict[str, Any] | None:
    """Write the D1 capacity claim for an appointment, inside the caller's transaction.

    This row -- not the SELECT ... FOR UPDATE above it -- is what actually decides a
    concurrent race: public.dock_occupancy carries
    EXCLUDE USING gist (dock_id WITH =, "window" WITH &&), so Postgres admits exactly one
    overlapping claim per dock and the loser gets an IntegrityError to translate
    (SOLUTION_DESIGN.md section 5 Stage 3). It must therefore be inserted in the same
    transaction that creates the appointment; committing an appointment without its claim
    would leave the interval unprotected.

    The window is computed in SQL, not in Python, and deliberately mirrors the E1.1 backfill
    expression character for character (supabase/migrations/20260823060000_d1_correctness_
    bedrock.sql:218): dock_id and slot_start_ts from appointment_slots, expected_unload_min
    from shipments, plus a 15-minute changeover buffer, half-open '[)'. Verified 2026-08-23:
    this expression reproduces all 613 backfilled windows exactly. If the two ever disagreed,
    the backfilled rows and newly booked rows would mean different things by "occupied". (The
    buffer is a flat 15 minutes because that is what the backfill used; making it
    per-facility is still an open D1 decision, so there is no knob to thread through yet.)

    The NOT EXISTS guard makes the claim idempotent per appointment_id. It does not weaken
    the race: competing callers always carry different freshly minted appointment ids, so
    both still reach the exclusion constraint. It exists so the reschedule restore path can
    re-claim without having to know whether its own release was already rolled back.

    `shipment_id` is written into the row, not merely used to join (added 2026-08-29). D2's
    migration (20260829134929) adds that column because a HELD claim has no appointment yet, so
    `appointment_id` alone can no longer identify what a row is holding capacity for. Omitting it
    here was proven -- against a throwaway cluster replaying this repo's own chain -- to break
    `request_slot` (the legacy path, reached only when two_phase_hold_enabled is False),
    `reschedule_appointment` and `counter_offer` the moment that migration commits, and to do so
    as a raw 500: `allocation_unique_constraint_name` matches on the names in
    ALLOCATION_CONFLICT_CONSTRAINTS, and a NOT NULL violation message contains none of them, so
    the IntegrityError re-raises untranslated. The column ships nullable precisely so this code
    can land first; a follow-up migration asserts NOT NULL once it has.

    `now` and `actor_user_id` exist only for the lazy-expiry step below (issue #97). They are
    required rather than defaulted so that a future fourth call site cannot quietly opt out of it
    and reintroduce the defect: a caller that has an appointment to claim for always has both.

    Returns the claimed row, or None when this appointment already holds a claim.
    """
    # Issue #97, the write half of the shared liveness predicate. The exclusion constraint's
    # predicate carries no time term, so a `HELD` row whose TTL lapsed still refuses this INSERT
    # even though §0.8 says a lapsed hold reserves nothing -- and with no sweeper running it can
    # refuse it indefinitely. Flipping the dead rows first, in this same transaction, is what makes
    # the table say what §0.8 means. `occupancy.py` carries the full argument; this call is a
    # no-op (one indexed statement, zero rows) on every path where nothing has lapsed.
    from app.scheduling import holds  # local: breaks the allocation <-> holds import cycle

    if holds.hold_reads_enabled():
        await holds.expire_lapsed_holds_on_interval(
            session,
            slot_id=slot_id,
            shipment_id=shipment_id,
            now=now,
            actor_user_id=actor_user_id,
        )
    row = (
        await session.execute(
            text(
                """
                INSERT INTO public.dock_occupancy (dock_id, appointment_id, shipment_id, "window")
                SELECT sl.dock_id,
                       :appointment_id,
                       :shipment_id,
                       tstzrange(
                           sl.slot_start_ts,
                           sl.slot_start_ts
                             + ((s.expected_unload_min + 15) || ' minutes')::interval,
                           '[)'
                       )
                FROM public.appointment_slots sl
                JOIN public.shipments s ON s.shipment_id = :shipment_id
                WHERE sl.slot_id = :slot_id
                  AND NOT EXISTS (
                      SELECT 1
                      FROM public.dock_occupancy o
                      WHERE o.appointment_id = :appointment_id
                  )
                RETURNING dock_id, "window"
                """
            ),
            {
                "appointment_id": appointment_id,
                "shipment_id": shipment_id,
                "slot_id": slot_id,
            },
        )
    ).mappings().first()
    return dict(row) if row else None


async def _release_dock_occupancy(session: AsyncSession, appointment_id: str) -> bool:
    """Drop an appointment's D1 capacity claim, inside the caller's transaction.

    Mandatory on every transition out of PENDING_CONFIRMATION/CONFIRMED/IN_PROGRESS. The
    shipped dock_occupancy table has no `state` column, so unlike the predicated
    EXCLUDE in SOLUTION_DESIGN.md section 0.8 there is nothing that makes a cancelled
    claim stop blocking -- deletion is the only release. Skip it and a cancelled or rejected
    appointment silently blocks its dock interval forever, while find_feasible_slots (which
    still reads appointments, not dock_occupancy) keeps offering the slot: every retry would
    then lose the race to a ghost.

    Returns True only if a claim was really deleted. Not every active appointment has one --
    the E1.1 backfill escalated 42 genuinely overlapping appointments to the D12 worklist
    instead of claiming for them -- and the reschedule restore path needs to tell the
    difference, so that a failed reschedule puts back exactly what it took and never invents
    a claim that would then fail the exclusion constraint on an interval nobody owned.
    """
    released = (
        await session.execute(
            text(
                """
                DELETE FROM public.dock_occupancy
                WHERE appointment_id = :appointment_id
                RETURNING occupancy_id
                """
            ),
            {"appointment_id": appointment_id},
        )
    ).first()
    return released is not None


async def _conflict_result(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    slot_id: str,
    policy_version: str,
    reason_code: str,
    message: str,
    idempotency_key: str,
) -> RequestSlotResult:
    refreshed = await find_feasible_slots(session, ctx, shipment_id, limit=5)
    return RequestSlotResult(
        as_of=_as_of(),
        status="CONFLICTED",
        code="SLOT_CONFLICT_REFRESH_REQUIRED",
        shipment_id=shipment_id,
        slot_id=slot_id,
        policy_version=policy_version,
        conflict={"reason_code": reason_code, "message": message},
        refreshed_options=refreshed.model_dump(),
        idempotency_key=idempotency_key,
        appointment_writes=0,
    )


async def _stale_recommendation_result(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    slot_id: str,
    policy_version: str,
    idempotency_key: str,
    message: str,
) -> RequestSlotResult:
    refreshed = await find_feasible_slots(session, ctx, shipment_id, limit=5)
    return RequestSlotResult(
        as_of=_as_of(),
        status="CONFLICTED",
        code="SLOT_OPTIONS_STALE",
        shipment_id=shipment_id,
        slot_id=slot_id,
        policy_version=policy_version,
        conflict={"reason_code": "SLOT_OPTIONS_STALE", "message": message},
        refreshed_options=refreshed.model_dump(),
        idempotency_key=idempotency_key,
        appointment_writes=0,
    )


async def _validate_displayed_recommendation(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    slot_id: str,
    displayed_policy_version: str | None,
    displayed_recommendation_id: str | None,
    idempotency_key: str,
) -> RequestSlotResult | None:
    constraints = load_scheduling_constraints()
    if displayed_policy_version and displayed_policy_version != constraints.policy_version:
        return await _stale_recommendation_result(
            session, ctx, shipment_id=shipment_id, slot_id=slot_id,
            policy_version=constraints.policy_version, idempotency_key=idempotency_key,
            message="The displayed scheduling policy is no longer current.",
        )
    redis_stale = False
    try:
        redis_stale = ConversationMemory(get_settings()).is_recommendation_stale(
            user_id=ctx.user_id, shipment_id=shipment_id
        )
    except Exception:  # noqa: BLE001
        pass
    if not displayed_recommendation_id:
        if redis_stale:
            return await _stale_recommendation_result(
                session, ctx, shipment_id=shipment_id, slot_id=slot_id,
                policy_version=constraints.policy_version, idempotency_key=idempotency_key,
                message="Displayed slot options are stale; use the refreshed recommendation.",
            )
        return None
    refreshed = await find_feasible_slots(session, ctx, shipment_id, limit=5)
    if refreshed.recommendation_id != displayed_recommendation_id:
        return await _stale_recommendation_result(
            session, ctx, shipment_id=shipment_id, slot_id=slot_id,
            policy_version=constraints.policy_version, idempotency_key=idempotency_key,
            message="Displayed slot options are stale; use the refreshed recommendation.",
        )
    if redis_stale:
        # #108: the displayed id MATCHES the recommendation recomputed this instant, so the
        # reply is provably from the current list -- the Redis flag (set by an ETA update)
        # has served its purpose and must clear here, not refuse. Refusing on the flag alone
        # was section 9.2 race 4's "re-presented" promise failing on its second half: with
        # two-phase holds on, the only clearing site was unreachable and one ETA update
        # locked the shipment out of booking for the key's 24h TTL. The no-id branch above
        # still refuses on the flag: without an id there is no proof of which list was seen.
        try:
            ConversationMemory(get_settings()).clear_recommendation_stale(
                user_id=ctx.user_id, shipment_id=shipment_id
            )
        except Exception:  # noqa: BLE001
            pass
    return None


async def get_appointment_request_status(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    appointment_id: str | None = None,
) -> AppointmentRequestStatusResult:
    shipment = await _shipment_for_status(session, shipment_id)
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    _assert_shipment_scope(ctx, shipment)

    appointment = await _appointment_request_status_row(
        session,
        shipment_id=shipment_id,
        appointment_id=appointment_id,
    )
    history = await _appointment_request_history(session, shipment_id)

    # Issue #83. `_appointment_request_status_row` starts `FROM public.appointments`, so for a
    # shipment whose only promise is a hold it returns nothing at all and this tool answered
    # `NO_APPOINTMENT_REQUEST` -- "you have not asked for a slot" -- to a driver the system had just
    # told a slot was reserved for them. The hold cannot be LEFT JOINed into that query for the same
    # reason: there is no appointments row to hang the join off. It is a second read, skipped
    # entirely (no query at all) while the D2 flag is off.
    from app.scheduling import holds  # local: breaks the allocation <-> holds import cycle

    hold = await holds.live_hold_for_shipment(
        session, shipment_id=shipment_id, now=datetime.now(timezone.utc)
    )
    status = appointment["appointment_status"] if appointment else None
    promise_state, promise_state_source = _resolve_promise_state(status, hold)

    if promise_state_source == holds.PROMISE_STATE_SOURCE_HOLD:
        # `SLOT_HELD` rather than a new code: it is exactly what `holds.HoldResult.code` already
        # returns when the hold is taken, so the status read and the write that created it name the
        # same state. `requires_human_confirmation` is False because a hold is waiting on the
        # *driver* to confirm within its TTL, not on a planner -- D6's human gate is a property of
        # PENDING_CONFIRMATION and must not be claimed here.
        code, requires_confirmation = "SLOT_HELD", False
    else:
        code, requires_confirmation = appointment_request_status_code(
            str(status) if status else None
        )

    return AppointmentRequestStatusResult(
        as_of=_as_of(),
        code=code,
        shipment_id=shipment_id,
        appointment_id=appointment["appointment_id"] if appointment else appointment_id,
        appointment=appointment,
        history=history,
        requires_human_confirmation=requires_confirmation,
        hold=hold,
        promise_state=promise_state,
        promise_state_source=promise_state_source,
    )


async def cancel_appointment(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    command: CancelAppointmentCommand,
    idempotency_key: str,
) -> AppointmentTransitionResult:
    route = (
        f"POST /api/v1/shipments/{shipment_id}/appointments/"
        f"{command.appointment_id}/cancel"
    )
    req_hash = payload_hash({"shipment_id": shipment_id, **command.model_dump()})
    replay = await lookup_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
    )
    if replay is not None:
        return AppointmentTransitionResult.model_validate(
            {**replay["response"], "idempotent_replay": True}
        )

    shipment = await _shipment_for_status(session, shipment_id)
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    _assert_shipment_scope(ctx, shipment, require_write=True)

    appointment = await _locked_appointment(
        session,
        shipment_id=shipment_id,
        appointment_id=command.appointment_id,
    )
    if appointment is None:
        raise AppError("Appointment not found.", code="APPOINTMENT_NOT_FOUND", status_code=404)
    old_status = str(appointment["appointment_status"])
    if old_status not in ACTIVE_APPOINTMENT_STATUSES:
        raise AppError(
            f"Cannot cancel appointment from {old_status}.",
            code="INVALID_APPOINTMENT_TRANSITION",
            status_code=409,
        )

    # One instant, two representations -- see the bind-type note above `_as_of`.
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    await session.execute(
        text(
            """
            UPDATE public.appointments
            SET appointment_status = 'CANCELLED',
                is_current = 0,
                cancelled_at = :cancelled_at,
                cancellation_reason = :cancellation_reason,
                updated_at = :updated_at
            WHERE appointment_id = :appointment_id
            """
        ),
        {
            "appointment_id": command.appointment_id,
            "cancelled_at": now,
            "cancellation_reason": command.cancellation_reason,
            "updated_at": now,
        },
    )
    # Same transaction as the cancellation: the dock interval must become bookable again the
    # instant the appointment stops occupying it, or the next request_slot loses to a ghost.
    await _release_dock_occupancy(session, command.appointment_id)
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id,
              old_value_json, new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :user_id, :action_type, 'appointments', :entity_id,
              :old_value_json, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"),
            "user_id": ctx.user_id,
            "action_type": AUDIT_ACTION_CANCEL_APPOINTMENT,
            "entity_id": command.appointment_id,
            "old_value_json": json.dumps(
                {"status": old_status, "is_current": appointment["is_current"]},
                default=str,
            ),
            "new_value_json": json.dumps(
                {
                    "status": "CANCELLED",
                    "is_current": 0,
                    "cancellation_reason": command.cancellation_reason,
                },
                default=str,
            ),
            "created_at": now_iso,
        },
    )
    updated = await _reread_appointment(session, command.appointment_id)
    result = AppointmentTransitionResult(
        as_of=_as_of(),
        status="CANCELLED",
        code="APPOINTMENT_CANCELLED",
        shipment_id=shipment_id,
        appointment_id=command.appointment_id,
        appointment=updated,
        idempotency_key=idempotency_key,
    )
    # #94: cancellation notifies the driver, enqueued in the same transaction (section 4).
    await notification_outbox.enqueue_notification(
        session,
        event_type=notification_outbox.APPOINTMENT_CANCELLED,
        appointment_id=command.appointment_id,
    )
    await store_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
        response=result.model_dump(),
    )
    await session.commit()
    result.appointment = await _reread_appointment(session, command.appointment_id)
    return result


async def _apply_confirmation(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    appointment_id: str,
    old_status: str,
    now: datetime,
    warehouse_confirmation_ref: str | None,
    note: str | None,
) -> None:
    """The PENDING_CONFIRMATION -> CONFIRMED write plus its audit row, inside the caller's txn.

    Extracted so `confirm_request` and `bulk_confirm` are literally the same write (issue #65). A
    second copy for the batch path is how the two would eventually disagree about what confirming
    means -- and the batch path is the one nobody watches row by row.

    No `dock_occupancy` change: CONFIRMED is an *active* status, so the claim the appointment took
    at PENDING_CONFIRMATION keeps standing exactly as it is. (Contrast `_ops_pending_transition`,
    where REJECTED/EXPIRED must release it.)

    `COALESCE(:warehouse_confirmation_ref, warehouse_confirmation_ref)`: the argument is optional
    (see `ConfirmAppointmentCommand`), and omitting it must not blank a reference a warehouse
    integration already wrote.
    """
    now_iso = now.isoformat()
    await session.execute(
        text(
            """
            UPDATE public.appointments
            SET appointment_status = 'CONFIRMED',
                confirmed_at = :confirmed_at,
                warehouse_confirmation_ref = COALESCE(
                    :warehouse_confirmation_ref, warehouse_confirmation_ref
                ),
                updated_at = :updated_at
            WHERE appointment_id = :appointment_id
            """
        ),
        {
            "appointment_id": appointment_id,
            "confirmed_at": now,
            "warehouse_confirmation_ref": warehouse_confirmation_ref,
            "updated_at": now,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id,
              old_value_json, new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :user_id, :action_type, 'appointments', :entity_id,
              :old_value_json, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"),
            "user_id": ctx.user_id,
            "action_type": AUDIT_ACTION_CONFIRM_APPOINTMENT,
            "entity_id": appointment_id,
            "old_value_json": json.dumps({"status": old_status}, default=str),
            "new_value_json": json.dumps(
                {
                    "status": "CONFIRMED",
                    "warehouse_confirmation_ref": warehouse_confirmation_ref,
                    "note": note,
                },
                default=str,
            ),
            # Deliberately still a string: audit_logs.created_at was never converted by E1.1.
            "created_at": now_iso,
        },
    )

    # #94: the confirmed-appointment notification, enqueued in the SAME transaction as the
    # status write and its audit row -- one seam covers confirm_request AND bulk_confirm,
    # which both converge here. Never raises, never commits (see notification_outbox).
    await notification_outbox.enqueue_notification(
        session,
        event_type=notification_outbox.APPOINTMENT_CONFIRMED,
        appointment_id=appointment_id,
    )


async def confirm_appointment(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    command: ConfirmAppointmentCommand,
    idempotency_key: str,
) -> AppointmentTransitionResult:
    route = (
        f"POST /api/v1/shipments/{shipment_id}/appointments/"
        f"{command.appointment_id}/confirm"
    )
    req_hash = payload_hash({"shipment_id": shipment_id, **command.model_dump()})
    replay = await lookup_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
    )
    if replay is not None:
        return AppointmentTransitionResult.model_validate(
            {**replay["response"], "idempotent_replay": True}
        )

    shipment = await _shipment_for_status(session, shipment_id)
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    _assert_ops_scope(ctx, shipment)

    appointment = await _locked_appointment(
        session,
        shipment_id=shipment_id,
        appointment_id=command.appointment_id,
    )
    if appointment is None:
        raise AppError("Appointment not found.", code="APPOINTMENT_NOT_FOUND", status_code=404)
    old_status = str(appointment["appointment_status"])
    if old_status != "PENDING_CONFIRMATION":
        # The D9 sweeper (or another planner) got here first. section 7.5.1 requires this to be
        # distinguishable by code and to name the winner, not to read as a generic bad transition.
        #
        # Deliberately still the FIRST refusal, ahead of the two E5.3 added below: a row somebody
        # already actioned is not "stale", it is decided, and section 7.5.1 names ALREADY_ACTIONED
        # as the answer to that exact race. Reordering these would tell a planner who lost the race
        # to the sweeper that their screen was out of date, which is true but not the point.
        raise _already_actioned_error(appointment, attempted="confirm")

    # section 7.5 principle 3 / issue #61. Inside the lock, after the status check: displacement
    # first, then staleness -- see `_displacement_error`.
    snapshot = await _snapshot_guard(
        session,
        appointment_id=command.appointment_id,
        expected_hash=command.snapshot_hash,
        attempted="confirm",
        actor_user_id=ctx.user_id,
    )

    # One instant, two representations -- see the bind-type note above `_as_of`.
    now = datetime.now(timezone.utc)
    await _apply_confirmation(
        session,
        ctx,
        appointment_id=command.appointment_id,
        old_status=old_status,
        now=now,
        warehouse_confirmation_ref=command.warehouse_confirmation_ref,
        note=command.note,
    )
    updated = await _reread_appointment(session, command.appointment_id)
    result = AppointmentTransitionResult(
        as_of=_as_of(),
        status="CONFIRMED",
        code="APPOINTMENT_CONFIRMED",
        shipment_id=shipment_id,
        appointment_id=command.appointment_id,
        appointment=updated,
        idempotency_key=idempotency_key,
        snapshot_hash=snapshot["snapshot_hash"],
    )
    await store_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
        response=result.model_dump(),
    )
    await session.commit()
    result.appointment = await _reread_appointment(session, command.appointment_id)
    return result


async def _request_slot_as_hold(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    slot_id: str,
    policy_version: str,
    now: datetime,
    idempotency_key: str,
    route: str,
    req_hash: str,
    persist: bool,
) -> RequestSlotResult:
    """Phase one of section 7.1's two-phase `request_slot`: take a D2 hold instead of booking.

    Kept in this module rather than `holds.py` only because it is the *tail* of `request_slot` --
    it reuses that function's already-computed eligibility verdict and its conflict/idempotency
    helpers. The hold's own semantics (the interval expression, the audit row, the NULL
    appointment_id) live in `holds.create_hold`; this is the adapter between the two.

    `holds` is imported here rather than at module scope because `holds` imports *this* module (for
    the shared scope helpers, the constraint-name translation and `_reread_appointment`) -- the same
    one-directional-import-plus-local-import shape `expiry.py` already uses against this module.
    """
    from app.scheduling import holds  # local: breaks the allocation <-> holds import cycle

    ttl_seconds = get_settings().held_slot_ttl_seconds
    try:
        hold = await holds.create_hold(
            session,
            shipment_id=shipment_id,
            slot_id=slot_id,
            policy_version=policy_version,
            ttl_seconds=ttl_seconds,
            now=now,
            actor_user_id=ctx.user_id,
        )
    except IntegrityError as exc:
        constraint_name = allocation_unique_constraint_name(exc)
        if constraint_name is None:
            raise
        await session.rollback()
        # The loser of a genuine D1 race, and the reason a hold is a `dock_occupancy` row at all:
        # two drivers picking the same interval within seconds contend on the exclusion constraint
        # here, at hold time, instead of both being shown an option that only one can book
        # (section 4, "It absorbs the 'two drivers pick the same slot within seconds' case").
        result = await _conflict_result(
            session,
            ctx,
            shipment_id=shipment_id,
            slot_id=slot_id,
            policy_version=policy_version,
            reason_code="POSTGRES_UNIQUE_ALLOCATION_CONFLICT",
            message=(
                "PostgreSQL rejected the hold because another active claim already holds this "
                f"capacity (constraint {constraint_name})."
            ),
            idempotency_key=idempotency_key,
        )
        await _store_request_idempotency(
            session, persist=persist, key=idempotency_key, user_id=ctx.user_id, route=route,
            request_hash=req_hash, response=result.model_dump(), status_code=409,
        )
        return result

    if hold is None:
        raise AppError(
            "Could not hold dock capacity for the selected slot.",
            code="DOCK_OCCUPANCY_HOLD_FAILED",
            status_code=500,
        )

    result = RequestSlotResult(
        as_of=_as_of(),
        status="HELD",
        code="SLOT_HELD",
        shipment_id=shipment_id,
        slot_id=slot_id,
        # No appointment exists yet, and saying so explicitly matters: section 4's "Held != booked"
        # is exactly what the driver-facing wording must not blur.
        appointment_id=None,
        policy_version=policy_version,
        hold_id=str(hold["occupancy_id"]),
        hold_expires_at=hold["expires_at"].isoformat()
        if isinstance(hold["expires_at"], datetime)
        else str(hold["expires_at"]),
        hold_ttl_seconds=ttl_seconds,
        idempotency_key=idempotency_key,
        appointment_writes=0,
    )
    await _store_request_idempotency(
        session, persist=persist, key=idempotency_key, user_id=ctx.user_id, route=route,
        request_hash=req_hash, response=result.model_dump(), status_code=200,
    )
    result.idempotent_replay = False
    # #108: the two-phase success path must clear the Redis stale flag exactly as the
    # single-phase site below does -- this was the ONLY clearing call's unreachable twin,
    # and without it one ETA update left every later request_slot refusing
    # SLOT_OPTIONS_STALE for the key's 24h TTL (section 9.2 race 4's re-present promise,
    # broken on its second half). A successful claim from the re-presented list is
    # precisely the moment staleness has served its purpose.
    try:
        ConversationMemory(get_settings()).clear_recommendation_stale(
            user_id=ctx.user_id, shipment_id=shipment_id
        )
    except Exception:  # noqa: BLE001
        pass
    return result


async def request_slot(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    slot_id: str,
    command: RequestSlotCommand,
    idempotency_key: str,
    persist: bool = True,
) -> RequestSlotResult:
    constraints = load_scheduling_constraints()
    route = f"POST /api/v1/shipments/{shipment_id}/slots/{slot_id}/request"
    req_hash = payload_hash(
        {
            "shipment_id": shipment_id,
            "slot_id": slot_id,
            **command.model_dump(),
        }
    )

    replay = await lookup_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
    )
    if replay is not None:
        result = RequestSlotResult.model_validate({**replay["response"], "idempotent_replay": True})
        if result.code == "SLOT_REQUESTED" and result.appointment_id:
            existing = await _reread_appointment(session, result.appointment_id)
            if replay_claim_is_active(existing):
                return result
            await session.execute(
                text("DELETE FROM public.idempotency_requests WHERE idempotency_key = :key"),
                {"key": idempotency_key},
            )
        else:
            return result

    # One instant, two representations -- see the bind-type note above `_as_of`. `now` also becomes
    # this appointment's `booked_at`, which is the anchor D9's 15-minute TTL is measured from
    # (expiry.py compares `booked_at < deadline`), so it has to be a real timestamptz value and not a
    # string the sweeper's comparison would have to cast.
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    shipment = (
        await session.execute(
            text(
                """
                SELECT s.shipment_id, s.driver_id, s.vehicle_id, s.destination_facility_id,
                       s.priority_code, s.required_dock_type, s.temperature_control_required,
                       s.load_weight_kg, s.expected_unload_min, s.current_status,
                       le.effective_eta_ts, le.eta_source, le.eta_confidence,
                       f.facility_id, f.timezone, f.open_time, f.close_time, f.active_flag
                FROM public.shipments s
                JOIN public.v_latest_eta le ON le.shipment_id = s.shipment_id
                JOIN public.facilities f ON f.facility_id = s.destination_facility_id
                WHERE s.shipment_id = :shipment_id
                FOR UPDATE OF s
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    shipment_data = dict(shipment)
    if ctx.is_driver:
        _assert_driver_scope(ctx, shipment_data)
    else:
        _assert_ops_scope(ctx, shipment_data)
    if int(shipment_data["active_flag"]) != 1:
        raise AppError("Destination facility is not active.", code="FACILITY_UNAVAILABLE", status_code=409)
    if shipment_data["current_status"] in ("COMPLETED", "CANCELLED"):
        raise AppError("Shipment is not eligible for slot request.", code="SHIPMENT_NOT_ACTIVE", status_code=409)

    stale = await _validate_displayed_recommendation(
        session,
        ctx,
        shipment_id=shipment_id,
        slot_id=slot_id,
        displayed_policy_version=command.displayed_policy_version,
        displayed_recommendation_id=command.displayed_recommendation_id,
        idempotency_key=idempotency_key,
    )
    if stale is not None:
        await _store_request_idempotency(
            session, persist=persist, key=idempotency_key, user_id=ctx.user_id, route=route,
            request_hash=req_hash, response=stale.model_dump(), status_code=409,
        )
        return stale

    active_for_shipment = await _current_active_appointment_for_shipment(session, shipment_id)
    if active_for_shipment:
        result = await _conflict_result(
            session,
            ctx,
            shipment_id=shipment_id,
            slot_id=slot_id,
            policy_version=constraints.policy_version,
            reason_code="ACTIVE_APPOINTMENT_EXISTS",
            message="Shipment already has an active current appointment. Use reschedule flow next.",
            idempotency_key=idempotency_key,
        )
        await _store_request_idempotency(
            session,
            persist=persist,
            key=idempotency_key,
            user_id=ctx.user_id,
            route=route,
            request_hash=req_hash,
            response=result.model_dump(),
            status_code=409,
        )
        return result

    slot = (
        await session.execute(
            text(
                """
                SELECT sl.slot_id, sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts,
                       sl.slot_status, sl.block_reason, d.dock_code, d.dock_type,
                       d.supports_refrigerated, d.max_vehicle_weight_kg, d.dock_status
                FROM public.appointment_slots sl
                JOIN public.docks d ON d.dock_id = sl.dock_id
                WHERE sl.slot_id = :slot_id
                  AND sl.facility_id = :facility_id
                FOR UPDATE OF sl
                """
            ),
            {"slot_id": slot_id, "facility_id": shipment_data["destination_facility_id"]},
        )
    ).mappings().first()
    if slot is None:
        raise AppError("Slot not found for shipment facility.", code="SLOT_NOT_FOUND", status_code=404)

    active_for_slot = await _active_appointment_for_slot(session, slot_id)
    dock_event = (
        await session.execute(
            text(
                """
                SELECT dock_event_id
                FROM public.dock_status_events
                WHERE dock_id = :dock_id
                  AND event_start_ts < :slot_end_ts
                  AND (event_end_ts IS NULL OR event_end_ts > :slot_start_ts)
                ORDER BY event_start_ts DESC
                LIMIT 1
                """
            ),
            {
                "dock_id": slot["dock_id"],
                "slot_start_ts": slot["slot_start_ts"],
                "slot_end_ts": slot["slot_end_ts"],
            },
        )
    ).mappings().first()

    candidate = dict(slot)
    candidate["active_appointment_id"] = active_for_slot["appointment_id"] if active_for_slot else None
    candidate["active_dock_event_id"] = dock_event["dock_event_id"] if dock_event else None
    option, reason = evaluate_candidate_slot(
        shipment=shipment_data,
        facility=shipment_data,
        eta_dt=datetime.fromisoformat(str(shipment_data["effective_eta_ts"])),
        candidate=candidate,
        checked_constraints=sorted(constraints.hard_constraint_ids()),
    )
    if option is None:
        result = await _conflict_result(
            session,
            ctx,
            shipment_id=shipment_id,
            slot_id=slot_id,
            policy_version=constraints.policy_version,
            reason_code=reason.failure_code if reason else "SLOT_NOT_FEASIBLE",
            message=reason.message if reason else "Selected slot is no longer feasible.",
            idempotency_key=idempotency_key,
        )
        await _store_request_idempotency(
            session,
            persist=persist,
            key=idempotency_key,
            user_id=ctx.user_id,
            route=route,
            request_hash=req_hash,
            response=result.model_dump(),
            status_code=409,
        )
        return result

    # ---- D2's two-phase contract (SOLUTION_DESIGN.md section 7.1, issue #53) -------------------
    # Section 7.1: "`request_slot` -- now a two-phase contract. Under D2 it ... returns one of three
    # typed outcomes: `HELD` + `hold_expires_at` (90 s) ... `SLOT_CONFLICT_REFRESH_REQUIRED` ...
    # `SLOT_OPTIONS_STALE`." Everything above this line -- scope, staleness, the active-appointment
    # guard, Stage 1 feasibility -- is identical for both phases and is deliberately not duplicated
    # in `holds.py`; only the *terminal write* differs. Below the flag, the legacy single-phase
    # path continues to commit straight to PENDING_CONFIRMATION, byte for byte as before.
    if get_settings().two_phase_hold_enabled:
        return await _request_slot_as_hold(
            session,
            ctx,
            shipment_id=shipment_id,
            slot_id=slot_id,
            policy_version=constraints.policy_version,
            now=now,
            idempotency_key=idempotency_key,
            route=route,
            req_hash=req_hash,
            persist=persist,
        )

    appointment_id = new_id("APT")
    audit_id = new_id("AUD")
    try:
        await session.execute(
            text(
                """
                INSERT INTO public.appointments (
                  appointment_id, shipment_id, slot_id, appointment_status, booking_source,
                  is_current, booked_at, confirmed_at, cancelled_at, cancellation_reason,
                  replaced_appointment_id, warehouse_confirmation_ref, updated_at
                ) VALUES (
                  :appointment_id, :shipment_id, :slot_id, 'PENDING_CONFIRMATION', 'DRIVER_CHAT',
                  1, :booked_at, NULL, NULL, NULL, NULL, NULL, :updated_at
                )
                """
            ),
            {
                "appointment_id": appointment_id,
                "shipment_id": shipment_id,
                "slot_id": slot_id,
                "booked_at": now,
                "updated_at": now,
            },
        )
        # The capacity claim goes in the same transaction as the appointment, immediately
        # after it (the FK needs the appointment row to exist first). This insert is the
        # concurrency decision; everything above it is a fast-path pre-check.
        claim = await _claim_dock_occupancy(
            session,
            appointment_id=appointment_id,
            shipment_id=shipment_id,
            slot_id=slot_id,
            now=now,
            actor_user_id=ctx.user_id,
        )
        if claim is None:
            # Unreachable for a freshly minted appointment_id, and deliberately loud rather
            # than tolerated: silently committing an appointment whose dock interval was
            # never claimed is the exact failure mode dock_occupancy exists to prevent.
            raise AppError(
                "Could not claim dock capacity for the appointment.",
                code="DOCK_OCCUPANCY_CLAIM_FAILED",
                status_code=500,
            )
        await session.execute(
            text(
                """
                INSERT INTO public.audit_logs (
                  audit_id, user_id, action_type, entity_name, entity_id,
                  old_value_json, new_value_json, ip_address, user_agent, created_at
                ) VALUES (
                  :audit_id, :user_id, :action_type, 'appointments', :entity_id,
                  NULL, :new_value_json, NULL, NULL, :created_at
                )
                """
            ),
            {
                "audit_id": audit_id,
                "user_id": ctx.user_id,
                "action_type": AUDIT_ACTION_BOOK_APPOINTMENT,
                "entity_id": appointment_id,
                "new_value_json": json.dumps(
                    {
                        "shipment_id": shipment_id,
                        "slot_id": slot_id,
                        "status": "PENDING_CONFIRMATION",
                        "policy_version": constraints.policy_version,
                        "displayed_policy_version": command.displayed_policy_version,
                        "note": command.note,
                        # Which dock interval this booking actually took, straight from the
                        # claim Postgres accepted -- so the audit trail records the capacity
                        # decision, not just the slot id the driver tapped.
                        "dock_id": claim["dock_id"],
                        "occupancy_window": claim["window"],
                    },
                    default=str,
                ),
                "created_at": now_iso,
            },
        )
        await session.flush()
    except IntegrityError as exc:
        constraint_name = allocation_unique_constraint_name(exc)
        if constraint_name is None:
            raise
        await session.rollback()
        result = await _conflict_result(
            session,
            ctx,
            shipment_id=shipment_id,
            slot_id=slot_id,
            policy_version=constraints.policy_version,
            # One reason_code for all three constraints on purpose: to the caller they mean the
            # same thing (someone else holds this capacity, refresh and retry), and the
            # user-facing code stays SLOT_CONFLICT_REFRESH_REQUIRED either way. The constraint
            # name in the message is what distinguishes an exact-slot double-book from a true
            # interval overlap when reading the trail back.
            reason_code="POSTGRES_UNIQUE_ALLOCATION_CONFLICT",
            message=(
                "PostgreSQL rejected the appointment claim because another active claim "
                f"already holds this capacity (constraint {constraint_name})."
            ),
            idempotency_key=idempotency_key,
        )
        await _store_request_idempotency(
            session,
            persist=persist,
            key=idempotency_key,
            user_id=ctx.user_id,
            route=route,
            request_hash=req_hash,
            response=result.model_dump(),
            status_code=409,
        )
        return result

    appointment = await _reread_appointment(session, appointment_id)
    result = RequestSlotResult(
        as_of=_as_of(),
        status="PENDING_CONFIRMATION",
        code="SLOT_REQUESTED",
        shipment_id=shipment_id,
        slot_id=slot_id,
        appointment_id=appointment_id,
        policy_version=constraints.policy_version,
        appointment=appointment,
        idempotency_key=idempotency_key,
        appointment_writes=1,
    )
    await _store_request_idempotency(
        session,
        persist=persist,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
        response=result.model_dump(),
        status_code=200,
    )
    if persist:
        final_appointment = await _reread_appointment(session, appointment_id)
        result.appointment = final_appointment
    result.idempotent_replay = False
    try:
        ConversationMemory(get_settings()).clear_recommendation_stale(
            user_id=ctx.user_id, shipment_id=shipment_id
        )
    except Exception:  # noqa: BLE001
        pass
    return result


async def _ops_pending_transition(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    appointment_id: str,
    target_status: str,
    reason: str,
    action_type: str,
    idempotency_key: str,
    note: str | None = None,
) -> AppointmentTransitionResult:
    route = f"POST /api/v1/shipments/{shipment_id}/appointments/{appointment_id}/{target_status.lower()}"
    # `note` joined the hash in E5.3 (issue #66) and it is not cosmetic. `reason` used to be free
    # prose, so it carried nearly all of a reject's entropy; now it is one of five enum values, and
    # two rejects differing only in their note would hash identically. Reusing an Idempotency-Key
    # with a changed payload must raise IDEMPOTENCY_PAYLOAD_MISMATCH, not silently replay the first
    # call's response -- narrowing the vocabulary without this would have quietly weakened that.
    req_hash = payload_hash(
        {
            "shipment_id": shipment_id,
            "appointment_id": appointment_id,
            "reason": reason,
            "note": note,
        }
    )
    replay = await lookup_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if replay is not None:
        return AppointmentTransitionResult.model_validate({**replay["response"], "idempotent_replay": True})
    shipment = await _shipment_for_status(session, shipment_id)
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    _assert_ops_scope(ctx, shipment)
    appointment = await _locked_appointment(
        session, shipment_id=shipment_id, appointment_id=appointment_id
    )
    if appointment is None:
        raise AppError("Appointment not found.", code="APPOINTMENT_NOT_FOUND", status_code=404)
    if appointment["appointment_status"] != "PENDING_CONFIRMATION":
        # Same race as confirm, same answer: the manual ops expire/reject buttons contend with the
        # D9 sweeper on exactly the same rows, so the loser is told who won here too.
        raise _already_actioned_error(appointment, attempted=target_status.lower())
    # One instant, two representations -- see the bind-type note above `_as_of`.
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    await session.execute(
        text(
            """
            UPDATE public.appointments
            SET appointment_status = :status, is_current = 0,
                cancellation_reason = :reason, updated_at = :updated_at
            WHERE appointment_id = :appointment_id
            """
        ),
        {"status": target_status, "reason": reason, "updated_at": now, "appointment_id": appointment_id},
    )
    # REJECTED and EXPIRED both stop occupying the dock, so the claim goes with them.
    await _release_dock_occupancy(session, appointment_id)
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id,
              old_value_json, new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :user_id, :action_type, 'appointments', :entity_id,
              :old_value_json, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"), "user_id": ctx.user_id, "action_type": action_type,
            "entity_id": appointment_id,
            "old_value_json": json.dumps({"status": "PENDING_CONFIRMATION"}),
            # `reason` is the controlled code (issue #66); `note` is the planner's own free text and
            # stays here in the audit trail only -- it never reaches `cancellation_reason`, which is
            # the driver-facing field the enum exists to protect.
            "new_value_json": json.dumps(
                {"status": target_status, "reason": reason, "note": note}
            ),
            "created_at": now_iso,
        },
    )
    # #94: REJECTED/EXPIRED both notify the driver from this one seam; the status->event
    # map lives in notification_outbox so no vocabulary leaks into allocation.
    await notification_outbox.enqueue_for_transition(
        session,
        target_status=target_status,
        appointment_id=appointment_id,
        shipment_id=shipment_id,
        reason=reason,
    )
    result = AppointmentTransitionResult(
        as_of=_as_of(), status=target_status, code=f"APPOINTMENT_{target_status}",
        shipment_id=shipment_id, appointment_id=appointment_id,
        appointment=await _reread_appointment(session, appointment_id), idempotency_key=idempotency_key,
    )
    await store_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route,
        request_hash=req_hash, response=result.model_dump()
    )
    await session.commit()
    result.appointment = await _reread_appointment(session, appointment_id)
    return result


async def reject_appointment(
    session: AsyncSession, ctx: ExecutionContext, *, shipment_id: str,
    command: RejectAppointmentCommand, idempotency_key: str
) -> AppointmentTransitionResult:
    """section 7.5.1 `reject_request` / `FR-PLN-003`. Issue #66.

    The vocabulary check happens here, before anything is read or locked: an unsupported
    `reason_code` is a client mistake, not a state conflict, so it must not consume a row lock or
    burn the caller's `Idempotency-Key` on a stored 422.

    What lands in `appointments.cancellation_reason` is the code itself, not prose. That column is
    what `_already_actioned_error` reads back to tell the *next* actor why the row is gone, and
    what a driver-facing renderer will resolve to copy -- section 7.5.1's whole reason for making
    this an enum. The planner's free-text `note` is audit-only and deliberately never reaches it.
    """
    reason_code = _assert_reason_code(
        command.reason_code, REJECTION_REASON_CODES, tool="reject_request"
    )
    return await _ops_pending_transition(
        session, ctx, shipment_id=shipment_id, appointment_id=command.appointment_id,
        target_status="REJECTED", reason=reason_code,
        action_type=AUDIT_ACTION_REJECT_APPOINTMENT, idempotency_key=idempotency_key,
        note=command.note,
    )


async def expire_appointment(
    session: AsyncSession, ctx: ExecutionContext, *, shipment_id: str,
    command: ExpireAppointmentCommand, idempotency_key: str
) -> AppointmentTransitionResult:
    return await _ops_pending_transition(
        session, ctx, shipment_id=shipment_id, appointment_id=command.appointment_id,
        target_status="EXPIRED", reason=command.expire_reason,
        action_type=AUDIT_ACTION_EXPIRE_APPOINTMENT, idempotency_key=idempotency_key,
    )


async def reschedule_appointment(
    session: AsyncSession, ctx: ExecutionContext, *, shipment_id: str,
    command: RescheduleAppointmentCommand, idempotency_key: str
) -> RequestSlotResult:
    route = f"POST /api/v1/shipments/{shipment_id}/appointments/{command.appointment_id}/reschedule"
    req_hash = payload_hash({"shipment_id": shipment_id, **command.model_dump()})
    replay = await lookup_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if replay is not None:
        return RequestSlotResult.model_validate({**replay["response"], "idempotent_replay": True})
    shipment = await _shipment_for_status(session, shipment_id)
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    _assert_shipment_scope(ctx, shipment, require_write=True)
    stale = await _validate_displayed_recommendation(
        session, ctx, shipment_id=shipment_id, slot_id=command.new_slot_id,
        displayed_policy_version=command.displayed_policy_version,
        displayed_recommendation_id=command.displayed_recommendation_id,
        idempotency_key=idempotency_key,
    )
    if stale is not None:
        await store_idempotency(
            session, key=idempotency_key, user_id=ctx.user_id, route=route,
            request_hash=req_hash, response=stale.model_dump(), status_code=409
        )
        await session.commit()
        return stale
    # Verify the requested replacement remains among the fresh options before
    # retiring the current claim. The subsequent request_slot performs locked
    # revalidation and PostgreSQL remains the final concurrency authority.
    options = await find_feasible_slots(session, ctx, shipment_id, limit=10)
    if command.new_slot_id not in {option.slot_id for option in options.options}:
        conflict = await _conflict_result(
            session, ctx, shipment_id=shipment_id, slot_id=command.new_slot_id,
            policy_version=options.policy_version, reason_code="SLOT_NOT_FEASIBLE",
            message="Replacement slot is no longer a fresh feasible option.", idempotency_key=idempotency_key,
        )
        await store_idempotency(
            session, key=idempotency_key, user_id=ctx.user_id, route=route,
            request_hash=req_hash, response=conflict.model_dump(), status_code=409,
        )
        await session.commit()
        return conflict
    old = await _locked_appointment(
        session, shipment_id=shipment_id, appointment_id=command.appointment_id
    )
    if old is None:
        raise AppError("Appointment not found.", code="APPOINTMENT_NOT_FOUND", status_code=404)
    if old["appointment_status"] not in ACTIVE_APPOINTMENT_STATUSES:
        raise AppError("Appointment is not active.", code="INVALID_APPOINTMENT_TRANSITION", status_code=409)
    # timestamptz bind -- see the note above `_as_of`. Only the datetime form is needed on this
    # path: the one text column reschedule writes (`audit_logs.created_at`, further down) is written
    # after the nested `request_slot` call returns, so it takes its own fresh instant rather than
    # reusing this one.
    now = datetime.now(timezone.utc)
    prior_status = str(old["appointment_status"])
    await session.execute(
        text(
            """
            UPDATE public.appointments
            SET appointment_status = 'CANCELLED', is_current = 0, cancelled_at = :updated_at,
                cancellation_reason = :reason, updated_at = :updated_at
            WHERE appointment_id = :appointment_id
            """
        ),
        {"appointment_id": command.appointment_id, "updated_at": now, "reason": "Replaced by reschedule"},
    )
    # Release before the new claim, not after: moving 11:00 -> 11:30 on the same dock overlaps
    # itself, so holding the old claim would make the exclusion constraint reject the driver's
    # own reschedule. Restored below if the new claim does not land.
    released_old_claim = await _release_dock_occupancy(session, command.appointment_id)
    # Recommendation freshness was already validated above against the true
    # pre-cancel snapshot, and new_slot_id was already confirmed to be a live
    # feasible option. Do not re-pass displayed_recommendation_id/policy_version
    # here: cancelling the old appointment just freed its slot back into the
    # candidate pool, so a fresh find_feasible_slots inside request_slot's own
    # staleness check would almost always disagree with the pre-cancel hash and
    # incorrectly reject every reschedule as SLOT_OPTIONS_STALE. Concurrency
    # safety still comes from request_slot's row lock and the DB unique
    # constraints, not from this hash comparison.
    result = await request_slot(
        session, ctx, shipment_id=shipment_id, slot_id=command.new_slot_id,
        command=RequestSlotCommand(
            note=command.note, displayed_policy_version=None,
            displayed_recommendation_id=None,
            client_message_id=command.client_message_id,
        ),
        idempotency_key=f"{idempotency_key}:claim",
        persist=False,
    )
    if result.code != "SLOT_REQUESTED":
        await session.execute(
            text(
                """
                UPDATE public.appointments
                SET appointment_status = :status, is_current = 1,
                    cancelled_at = NULL, cancellation_reason = NULL, updated_at = :updated_at
                WHERE appointment_id = :appointment_id
                """
            ),
            {
                "status": prior_status,
                # timestamptz, not a string -- see the note above `_as_of`. A fresh instant rather
                # than `now`: this restore happens after the failed nested request_slot, and the
                # row's updated_at should say when it was put back, not when it was taken.
                "updated_at": datetime.now(timezone.utc),
                "appointment_id": command.appointment_id,
            },
        )
        # The old appointment is active again, so it must hold its claim again -- but only if
        # it held one before, otherwise this would invent a claim on an interval nobody owned.
        # Two shapes of failure reach here: request_slot's IntegrityError branch already called
        # session.rollback(), which undid the release too, and the claim's NOT EXISTS guard
        # makes this a no-op then; a non-rollback conflict (stale options, slot no longer
        # feasible) leaves the release standing, and this is what puts the claim back. Without
        # it a restored appointment would sit on an unprotected dock interval.
        if released_old_claim:
            await _claim_dock_occupancy(
                session,
                appointment_id=command.appointment_id,
                shipment_id=shipment_id,
                slot_id=str(old["slot_id"]),
                # A fresh instant, matching the restore UPDATE just above: this is happening now,
                # not at the moment the reschedule was attempted, and issue #97's lazy expiry must
                # judge liveness against the clock the restore is actually running on.
                now=datetime.now(timezone.utc),
                actor_user_id=ctx.user_id,
            )
        await store_idempotency(
            session, key=idempotency_key, user_id=ctx.user_id, route=route,
            request_hash=req_hash, response=result.model_dump(), status_code=409,
        )
        await session.commit()
        return result
    await session.execute(
        text("UPDATE public.appointments SET replaced_appointment_id = :old_id WHERE appointment_id = :new_id"),
        {"old_id": command.appointment_id, "new_id": result.appointment_id},
    )
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id,
              old_value_json, new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :user_id, :action_type, 'appointments', :entity_id,
              :old_value_json, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"), "user_id": ctx.user_id,
            "action_type": AUDIT_ACTION_RESCHEDULE_APPOINTMENT, "entity_id": result.appointment_id,
            "old_value_json": json.dumps({"appointment_id": command.appointment_id, "status": old["appointment_status"]}),
            "new_value_json": json.dumps({"appointment_id": result.appointment_id, "slot_id": command.new_slot_id}),
            # Deliberately still a string: audit_logs.created_at was never converted by E1.1 and
            # would raise the mirror-image DataError if handed a datetime. Verified live 2026-08-23.
            "created_at": _as_of(),
        },
    )
    await store_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route,
        request_hash=req_hash, response=result.model_dump()
    )
    await session.commit()
    result.appointment = await _reread_appointment(session, str(result.appointment_id))
    return result


# =================================================================================================
# counter_offer -- section 7.5.1 / FR-PLN-002 / flows-and-states.md Flow 2 (issue #63)
# =================================================================================================


async def _slot_at_dock_and_time(
    session: AsyncSession, *, facility_id: str, dock_id: str, start_ts: datetime
) -> dict[str, Any] | None:
    """Resolve the Board tab's (dock, time) pick to an `appointment_slots` row.

    section 7.5.1 gives `counter_offer` `dock_id` + `start_ts`, not a `slot_id`, because that is
    what a dock/time grid hands the planner. The live schema is slot-based, so the pair has to
    resolve to a real slot row -- and when it does not, the honest answer is
    `INTERVAL_UNAVAILABLE`, never a slot conjured to fit the click.

    `facility_id` is the *shipment's* destination facility, derived server-side, never a client
    argument (M15) -- so a planner cannot counter-offer a dock at a facility the shipment is not
    going to, however the board was rendered.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT sl.slot_id, sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts,
                       sl.slot_status, d.dock_code, d.dock_type, d.dock_status
                FROM public.appointment_slots sl
                JOIN public.docks d ON d.dock_id = sl.dock_id
                WHERE sl.facility_id = :facility_id
                  AND sl.dock_id = :dock_id
                  AND sl.slot_start_ts = :start_ts
                LIMIT 1
                """
            ),
            {"facility_id": facility_id, "dock_id": dock_id, "start_ts": start_ts},
        )
    ).mappings().first()
    return dict(row) if row else None


def _interval_unavailable_error(
    *, dock_id: str, start_ts: datetime, failure_code: str, message: str
) -> AppError:
    """section 7.5.1's `INTERVAL_UNAVAILABLE`.

    Flow 2: the board *"re-renders that interval occupied, banner stays, pick again"* -- so the
    refusal has to name which interval and why, or the planner has nothing to re-render.
    """
    return AppError(
        message,
        code="INTERVAL_UNAVAILABLE",
        status_code=409,
        detail=json.dumps(
            {
                "reason_code": "INTERVAL_UNAVAILABLE",
                "failure_code": failure_code,
                "dock_id": dock_id,
                "start_ts": start_ts.isoformat(),
                "message": message,
            },
            default=str,
        ),
    )


async def counter_offer(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    command: CounterOfferCommand,
    idempotency_key: str,
) -> CounterOfferResult:
    """section 7.5.1 `counter_offer` -- the affordance that keeps the conversation alive.

    section 7.3: *"Reject without an alternative is a dead end -- the driver is pushed back to a
    phone call, which is the failure mode the product exists to remove."*

    ## What this actually writes, and the honest limit of it

    The appointment **moves to the counter-offered slot and stays `PENDING_CONFIRMATION`**, with
    its `dock_occupancy` claim released from the old interval and re-taken on the new one inside
    one transaction. Reserving is not optional: if the offered interval were merely *shown*, another
    booking could take it before the driver replies and the planner's offer would have been a lie --
    exactly the mis-promise this product exists to remove.

    **What it cannot do yet, stated plainly.** `flows-and-states.md` Flow 2 wants the queue row to
    show a distinct *"awaiting driver"* micro-state, and D2's four-state lifecycle
    (`SHOWN -> HELD -> PENDING_CONFIRMATION -> CONFIRMED`) is where that would live. The live
    `appointments_appointment_status_check` admits no such value (migration 20260812010000), and
    issue #53's migration for it is written but **not applied**. So the micro-state is derivable
    rather than stored: a `PENDING_CONFIRMATION` row whose most recent `audit_logs` entry carries
    `new_value_json.transition = 'COUNTER_OFFERED'`. That is queryable today and needs no schema
    change; it is not as good as a column, and it is flagged rather than papered over.

    **The D9 clock is deliberately not reset.** `booked_at` is the anchor `expiry.py` measures the
    15-minute TTL from, and rewriting it would both hand the planner an unbounded way to sit on
    capacity and corrupt the request's own history. A counter-offer therefore inherits whatever TTL
    remains. **Owner fork, still open and now sharper:** if a counter-offer should buy the driver
    fresh time, `appointments.expires_at` is where that happens -- and since issue #64 shipped,
    `hold_for_information` already writes that column and treats `expires_at IS NOT NULL` as the
    marker that the one permitted extension is spent. So resolving this fork by having
    `counter_offer` write the same column is *not* a one-line change: the two writers would need a
    real discriminator first (see `hold_for_information`'s docstring). Left untouched here rather
    than half-resolved.

    ## Round trips, counted rather than assumed

    Idempotency lookup, shipment read, locking read, snapshot recompute, slot resolve, Stage-1
    revalidation (3), release, update, claim, audit, snapshot recompute, idempotency store. Thirteen
    on the success path, for an action section 7.3's own load arithmetic puts at a handful per
    coordinator per hour. Stage 1 is reused via `explain_slot_eligibility` rather than re-queried
    inline precisely because a second copy of the eligibility guard is how a planner ends up able to
    hand out by hand something the driver path would have refused.
    """
    reason_code = _assert_reason_code(
        command.reason_code, COUNTER_OFFER_REASON_CODES, tool="counter_offer"
    )
    route = (
        f"POST /api/v1/shipments/{shipment_id}/appointments/"
        f"{command.appointment_id}/counter-offer"
    )
    req_hash = payload_hash({"shipment_id": shipment_id, **command.model_dump()})
    replay = await lookup_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if replay is not None:
        return CounterOfferResult.model_validate({**replay["response"], "idempotent_replay": True})

    shipment = await _shipment_for_status(session, shipment_id)
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    _assert_ops_scope(ctx, shipment)
    facility_id = str(shipment["destination_facility_id"])

    appointment = await _locked_appointment(
        session, shipment_id=shipment_id, appointment_id=command.appointment_id
    )
    if appointment is None:
        raise AppError("Appointment not found.", code="APPOINTMENT_NOT_FOUND", status_code=404)
    if str(appointment["appointment_status"]) != "PENDING_CONFIRMATION":
        raise _already_actioned_error(appointment, attempted="counter-offer")

    await _snapshot_guard(
        session,
        appointment_id=command.appointment_id,
        expected_hash=command.snapshot_hash,
        attempted="counter-offer",
        actor_user_id=ctx.user_id,
    )

    start_ts = command.start_ts
    if start_ts.tzinfo is None:
        # A naive `start_ts` would be encoded by asyncpg as if it were in the session zone and
        # silently match the wrong slot. Refuse instead of guessing which zone the board meant.
        raise _interval_unavailable_error(
            dock_id=command.dock_id,
            start_ts=start_ts.replace(tzinfo=timezone.utc),
            failure_code="START_TS_NOT_TIMEZONE_AWARE",
            message="start_ts must carry a timezone offset.",
        )

    slot = await _slot_at_dock_and_time(
        session, facility_id=facility_id, dock_id=command.dock_id, start_ts=start_ts
    )
    if slot is None:
        raise _interval_unavailable_error(
            dock_id=command.dock_id,
            start_ts=start_ts,
            failure_code="SLOT_NOT_FOUND",
            message=(
                "No slot exists on that dock at that start time for the shipment's destination "
                "facility."
            ),
        )
    new_slot_id = str(slot["slot_id"])
    if new_slot_id == str(appointment["slot_id"]):
        raise _interval_unavailable_error(
            dock_id=command.dock_id,
            start_ts=start_ts,
            failure_code="SAME_INTERVAL",
            message="The counter-offered interval is the one already requested.",
        )

    # section 7.5.1: "Revalidates the proposed interval through Stage 1 -- a planner may not hand
    # out an infeasible slot by hand." This is the full Stage-1 guard, facility rules and the
    # driver's own acceptable window included, not the reduced one `request_slot` runs.
    eligibility = await explain_slot_eligibility(
        session,
        ctx,
        shipment_id,
        new_slot_id,
        # This runs BEFORE the release below, so the appointment's own claim overlaps the interval
        # it is being moved onto whenever the move is a small shift on the same dock. Excluding it
        # is the same self-overlap problem `reschedule_appointment` solves by releasing first --
        # counter_offer cannot do that, because it must know the new interval is feasible before it
        # gives up the one it holds (issue #97 made this visible by teaching the read path about
        # dock_occupancy at all).
        exclude_appointment_id=command.appointment_id,
    )
    if not eligibility.eligible:
        raise _interval_unavailable_error(
            dock_id=command.dock_id,
            start_ts=start_ts,
            failure_code=eligibility.failure_code or "SLOT_NOT_FEASIBLE",
            message=eligibility.message or "The proposed interval is not feasible.",
        )

    now = datetime.now(timezone.utc)
    try:
        # Release before claiming, for the reason `reschedule_appointment` gives: moving 11:00 to
        # 11:30 on the same dock overlaps itself, so holding the old claim would make D1's
        # exclusion constraint reject the planner's own counter-offer.
        await _release_dock_occupancy(session, command.appointment_id)
        await session.execute(
            text(
                """
                UPDATE public.appointments
                SET slot_id = :slot_id, updated_at = :updated_at
                WHERE appointment_id = :appointment_id
                """
            ),
            {
                "slot_id": new_slot_id,
                "updated_at": now,
                "appointment_id": command.appointment_id,
            },
        )
        claim = await _claim_dock_occupancy(
            session,
            appointment_id=command.appointment_id,
            shipment_id=shipment_id,
            slot_id=new_slot_id,
            now=now,
            actor_user_id=ctx.user_id,
        )
        if claim is None:
            raise AppError(
                "Could not claim dock capacity for the counter-offered interval.",
                code="DOCK_OCCUPANCY_CLAIM_FAILED",
                status_code=500,
            )
        await session.execute(
            text(
                """
                INSERT INTO public.audit_logs (
                  audit_id, user_id, action_type, entity_name, entity_id,
                  old_value_json, new_value_json, ip_address, user_agent, created_at
                ) VALUES (
                  :audit_id, :user_id, :action_type, 'appointments', :entity_id,
                  :old_value_json, :new_value_json, NULL, NULL, :created_at
                )
                """
            ),
            {
                "audit_id": new_id("AUD"),
                "user_id": ctx.user_id,
                "action_type": AUDIT_ACTION_COUNTER_OFFER,
                "entity_id": command.appointment_id,
                "old_value_json": json.dumps(
                    {"slot_id": appointment["slot_id"], "status": "PENDING_CONFIRMATION"},
                    default=str,
                ),
                "new_value_json": json.dumps(
                    {
                        # The discriminator that makes this row distinguishable from a driver's
                        # reschedule -- see AUDIT_ACTION_COUNTER_OFFER for why action_type cannot
                        # carry it.
                        "transition": AUDIT_TRANSITION_COUNTER_OFFERED,
                        "slot_id": new_slot_id,
                        "dock_id": str(slot["dock_id"]),
                        "reason_code": reason_code,
                        "note": command.note,
                        "occupancy_window": claim["window"],
                    },
                    default=str,
                ),
                "created_at": now.isoformat(),
            },
        )
        await session.flush()
    except IntegrityError as exc:
        constraint_name = allocation_unique_constraint_name(exc)
        if constraint_name is None:
            raise
        await session.rollback()
        raise _interval_unavailable_error(
            dock_id=command.dock_id,
            start_ts=start_ts,
            failure_code="POSTGRES_ALLOCATION_CONFLICT",
            message=(
                "PostgreSQL rejected the counter-offer because another active claim already holds "
                f"this capacity (constraint {constraint_name})."
            ),
        ) from exc

    refreshed = await load_appointment_snapshot(
        session, command.appointment_id, actor_user_id=ctx.user_id
    )
    result = CounterOfferResult(
        as_of=_as_of(),
        code="COUNTER_OFFERED",
        shipment_id=shipment_id,
        appointment_id=command.appointment_id,
        reason_code=reason_code,
        offered_options=[
            {
                "slot_id": new_slot_id,
                "facility_id": facility_id,
                "dock_id": str(slot["dock_id"]),
                "dock_code": str(slot["dock_code"]),
                "dock_type": str(slot["dock_type"]),
                "slot_start_ts": slot["slot_start_ts"],
                "slot_end_ts": slot["slot_end_ts"],
                "occupancy_window": claim["window"],
                "checked_constraints": eligibility.checked_constraints,
                "explanation": eligibility.explanation,
            }
        ],
        appointment=await _reread_appointment(session, command.appointment_id),
        idempotency_key=idempotency_key,
        appointment_writes=1,
        snapshot_hash=refreshed["snapshot_hash"] if refreshed else None,
    )
    await store_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route,
        request_hash=req_hash, response=result.model_dump(),
    )
    await session.commit()
    result.appointment = await _reread_appointment(session, command.appointment_id)
    return result


# =================================================================================================
# hold_for_information -- section 7.5.1 / FR-PLN-004 / Flow 4 (issue #64)
# =================================================================================================


def _derived_pending_deadline(booked_at: Any, *, ttl_minutes: int) -> datetime | None:
    """The D9 deadline a request has when nothing has extended it: `booked_at + ttl`.

    Computed here rather than read from a column because that is exactly what the schema says:
    *"NULL means the ordinary derived deadline (booked_at + PENDING_CONFIRMATION_TTL_MINUTES)
    applies"* (`COMMENT ON COLUMN public.appointments.expires_at`,
    `20260829134929_d2_held_state_dock_occupancy.sql:266-269`). `expiry.py::_pending_candidates`
    implements the same rule in SQL; this is the Python half of one rule, not a second rule.

    Returns None for a row with no `booked_at` at all, which the caller reports rather than
    guessing a deadline for -- an appointment with no booking instant has no D9 clock to pause.
    """
    if booked_at is None:
        return None
    if isinstance(booked_at, datetime):
        anchor = booked_at
    else:
        try:
            anchor = datetime.fromisoformat(str(booked_at))
        except ValueError:
            return None
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    return anchor + timedelta(minutes=ttl_minutes)


async def hold_for_information(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    shipment_id: str,
    command: HoldForInformationCommand,
    idempotency_key: str,
) -> HoldForInformationResult:
    """section 7.5.1 `hold_for_information` -- buy the driver time to answer, exactly once.

    The catalog row, in full: *"`HELD_FOR_INFO` + `new_deadline`. **Pauses the D9 clock exactly
    once** per request; a second call returns `HOLD_ALREADY_USED`. Without that cap, 'hold for info'
    becomes an unbounded way to sit on capacity."*

    ## "Pauses the clock" is implemented as one bounded extension, and that is a decision

    A literal pause -- stop the clock, resume it when the driver replies -- is not representable
    against this schema and, more importantly, is the thing the catalog's own second sentence
    forbids. There is one column (`appointments.expires_at`) and it holds a deadline, not a
    remaining duration; and the sweeper's precedence rule is that NULL means *"the derived
    `booked_at + ttl` deadline applies"* (`expiry.py`), so NULL cannot be overloaded to mean
    "paused" -- a paused row would read as one whose original 15 minutes had already lapsed. An
    indefinite pause is also exactly the unbounded sit-on-capacity the design names as the reason
    the cap exists.

    So: **`new_deadline = now + one further D9 TTL`**, and the one-shot cap is what bounds the total.
    The extension is not a new invented number -- it is `pending_confirmation_ttl_minutes`, D9's own
    15 minutes, read from settings so the two cannot drift. Worst case for a held request is
    therefore two D9 windows rather than one, which is bounded, explainable to a planner ("this buys
    another fifteen minutes"), and sourced.

    The alternative considered and rejected: `new_deadline = now + whatever remained`. It is a truer
    "pause" of the instant, but it makes the tool useless precisely when it matters -- a planner who
    holds a request with 40 seconds left buys the driver 40 seconds to answer a question. Recorded
    here rather than silently chosen, in the same posture as `COUNTER_OFFER_REASON_CODES` above.

    ## The one-shot cap, and why it needs no new column

    `expires_at IS NOT NULL` **is** the marker, which is the migration's own stated design
    (`20260829134929...sql:252-256`). It is read under the same `SELECT ... FOR UPDATE` as the
    status (`_locked_appointment`), so the cap survives two planners pressing Hold simultaneously:
    they serialise on the row lock, and under READ COMMITTED the loser re-evaluates against the
    committed version and sees a non-NULL deadline (PostgreSQL "Transaction Isolation" 13.2.1).

    **Coupling worth naming:** if the owner ever resolves the #63/#64 fork by letting `counter_offer`
    buy fresh time through this same column, `expires_at IS NOT NULL` stops meaning "the hold was
    used" and this guard has to become a real discriminator (an audit-trail probe for
    `transition = 'HELD_FOR_INFO'`, or a column). Today nothing else writes it -- verified by grep
    across `app/` -- so the marker is unambiguous.

    ## What this does *not* do, stated plainly

    The `question` reaches the audit trail and nothing else. Flow 4 step 4 has the driver answering
    in `01-driver-chat/`, and there is no path from here to the driver: no writer for
    `operational_messages` or `notifications` exists anywhere in this codebase (grepped
    2026-09-02 -- `notification_service` reads only), and `reject_request`'s own *"+ driver
    notification"* is equally unimplemented today. Holding a request therefore pauses the clock and
    records the question for a human to relay; it does not deliver it. Recorded as a real gap rather
    than papered over with an invented delivery.

    Likewise, the queue row's Paused rendering (`components.md` section 3) needs `expires_at` to
    reach `get_planner_queue`, which lives in `planner_service.py` -- not this pass's file. The data
    is in the row and in this result; the read that surfaces it to the board is a follow-up.

    ## Round trips

    Idempotency lookup, shipment read, locking read, update, audit insert, re-read, idempotency
    store. Seven, for an action section 7.3 puts at a handful per planner per hour.
    """
    route = (
        f"POST /api/v1/shipments/{shipment_id}/appointments/"
        f"{command.appointment_id}/hold-for-information"
    )
    req_hash = payload_hash({"shipment_id": shipment_id, **command.model_dump()})
    replay = await lookup_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if replay is not None:
        # M9. Unlike `confirm_request`'s replay branch there is nothing to re-check: the extension
        # is single-use by construction, so a genuine re-run could only produce HOLD_ALREADY_USED.
        # Returning the stored success is the honest answer to "the same call, twice".
        return HoldForInformationResult.model_validate(
            {**replay["response"], "idempotent_replay": True}
        )

    shipment = await _shipment_for_status(session, shipment_id)
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    _assert_ops_scope(ctx, shipment)

    appointment = await _locked_appointment(
        session, shipment_id=shipment_id, appointment_id=command.appointment_id
    )
    if appointment is None:
        raise AppError("Appointment not found.", code="APPOINTMENT_NOT_FOUND", status_code=404)
    if str(appointment["appointment_status"]) != "PENDING_CONFIRMATION":
        # Same race, same answer as confirm/reject/expire: the D9 sweeper may have taken this row
        # while the planner was typing the question.
        raise _already_actioned_error(appointment, attempted="hold for information")

    existing_deadline = appointment.get("expires_at")
    if existing_deadline is not None:
        raise AppError(
            "This request has already been held for information once; the D9 clock can only be "
            "paused once per request.",
            code="HOLD_ALREADY_USED",
            status_code=409,
            detail=json.dumps(
                {
                    "reason_code": "HOLD_ALREADY_USED",
                    "appointment_id": command.appointment_id,
                    # `.isoformat()`, never `default=str`: `str(datetime)` emits a space where
                    # ISO-8601 wants a `T`, so a refusal and the success response that preceded it
                    # would disagree on the spelling of the same instant. Every timestamp this tool
                    # emits -- response, audit row, refusal -- goes through isoformat for that
                    # reason.
                    "current_deadline": (
                        existing_deadline.isoformat()
                        if isinstance(existing_deadline, datetime)
                        else str(existing_deadline)
                    ),
                }
            ),
        )

    ttl_minutes = get_settings().pending_confirmation_ttl_minutes
    previous_deadline = _derived_pending_deadline(
        appointment.get("booked_at"), ttl_minutes=ttl_minutes
    )
    if previous_deadline is None:
        # A PENDING row with no readable `booked_at` has no D9 clock, so there is nothing to pause
        # and nothing honest to report as `previous_deadline`. Refusing beats inventing one.
        raise AppError(
            "This request has no booking instant, so it has no D9 deadline to pause.",
            code="NO_PENDING_DEADLINE",
            status_code=409,
        )

    now = datetime.now(timezone.utc)
    new_deadline = now + timedelta(minutes=ttl_minutes)
    now_iso = now.isoformat()

    await session.execute(
        text(
            """
            UPDATE public.appointments
            SET expires_at = :expires_at, updated_at = :updated_at
            WHERE appointment_id = :appointment_id
              AND appointment_status = 'PENDING_CONFIRMATION'
              AND expires_at IS NULL
            """
        ),
        # The two extra predicates are belt-and-braces under a lock we already hold, and they are
        # the invariant written down where PostgreSQL will enforce it: this statement can never
        # extend a request that stopped being pending, nor spend a second extension.
        {
            "expires_at": new_deadline,
            "updated_at": now,
            "appointment_id": command.appointment_id,
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id,
              old_value_json, new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :user_id, :action_type, 'appointments', :entity_id,
              :old_value_json, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"),
            "user_id": ctx.user_id,
            "action_type": AUDIT_ACTION_HOLD_FOR_INFORMATION,
            "entity_id": command.appointment_id,
            "old_value_json": json.dumps(
                {
                    "status": "PENDING_CONFIRMATION",
                    # NULL before, which is the whole of the one-shot marker's before-state.
                    "expires_at": None,
                    "derived_deadline": previous_deadline.isoformat(),
                }
            ),
            # M14: reconstructable from this row alone -- who paused it, what they asked, what the
            # deadline was before and after, and that the one permitted extension is now spent.
            # Timestamps are `.isoformat()` rather than `default=str`, so the audit row spells an
            # instant exactly the way the API response does (`str(datetime)` uses a space instead
            # of the ISO `T`, which would make the two disagree textually about one moment).
            "new_value_json": json.dumps(
                {
                    "transition": AUDIT_TRANSITION_HELD_FOR_INFO,
                    "status": "PENDING_CONFIRMATION",
                    "question": command.question,
                    "previous_deadline": previous_deadline.isoformat(),
                    "new_deadline": new_deadline.isoformat(),
                    "extension_minutes": ttl_minutes,
                    "hold_used": True,
                }
            ),
            "created_at": now_iso,
        },
    )

    result = HoldForInformationResult(
        as_of=_as_of(),
        shipment_id=shipment_id,
        appointment_id=command.appointment_id,
        question=command.question,
        new_deadline=new_deadline.isoformat(),
        previous_deadline=previous_deadline.isoformat(),
        extension_minutes=ttl_minutes,
        appointment=await _reread_appointment(session, command.appointment_id),
        idempotency_key=idempotency_key,
    )
    await store_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route,
        request_hash=req_hash, response=result.model_dump(),
    )
    await session.commit()
    result.appointment = await _reread_appointment(session, command.appointment_id)
    return result


# =================================================================================================
# bulk_confirm -- section 7.5.1 / section 7.3 / D6 / FR-PLN-006 / Flow 6 (issue #65)
# =================================================================================================


async def _safe_batch_inputs(
    session: AsyncSession, appointment_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """One round trip for every input section 7.3's five safe-batch predicates need.

    Deliberately one statement for the whole batch rather than per id: this is the only part of
    `bulk_confirm` that is a genuine N+1 risk, and unlike the row locks (which must be taken one at
    a time in a fixed order) nothing here needs sequencing.

    `LAST_NEW_START_TIME` rules come back as JSON rather than pre-filtered in SQL because
    `facility_rules.effective_from/effective_to` are still TEXT with two live shapes (a bare date
    from the seed, a full offset-bearing timestamp from the demo overlay) -- `active_facility_rules`
    is the one function that reads both correctly, and re-deriving that comparison in SQL would be a
    second answer to the same question.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id,
                       a.shipment_id,
                       a.appointment_status,
                       a.is_current,
                       s.destination_facility_id,
                       s.required_dock_type,
                       s.expected_unload_min,
                       d.dock_type,
                       sl.facility_id,
                       f.timezone,
                       f.open_time,
                       f.close_time,
                       le.eta_confidence,
                       (SELECT count(*)
                          FROM public.escalation_queue e
                         WHERE e.shipment_id = a.shipment_id
                           AND e.escalation_status = ANY(:open_escalation_statuses)
                       ) AS open_escalation_count,
                       (SELECT coalesce(json_agg(json_build_object(
                                 'rule_id', fr.rule_id,
                                 'rule_type', fr.rule_type,
                                 'rule_value', fr.rule_value,
                                 'effective_from', fr.effective_from,
                                 'effective_to', fr.effective_to))::text, '[]')
                          FROM public.facility_rules fr
                         WHERE fr.facility_id = f.facility_id
                           AND fr.active_flag = 1
                           AND fr.rule_type = 'LAST_NEW_START_TIME'
                       ) AS last_new_start_rules_json
                  FROM public.appointments a
                  JOIN public.shipments s ON s.shipment_id = a.shipment_id
                  JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                  JOIN public.docks d ON d.dock_id = sl.dock_id
                  JOIN public.facilities f ON f.facility_id = sl.facility_id
                  LEFT JOIN public.v_latest_eta le ON le.shipment_id = a.shipment_id
                 WHERE a.appointment_id = ANY(:appointment_ids)
                """
            ),
            {
                "appointment_ids": list(appointment_ids),
                "open_escalation_statuses": list(OPEN_ESCALATION_STATUSES),
            },
        )
    ).mappings().all()
    return {str(row["appointment_id"]): dict(row) for row in rows}


def evaluate_safe_batch_predicates(
    *,
    inputs: dict[str, Any],
    snapshot: dict[str, Any],
) -> list[str]:
    """Return the names of section 7.3's five predicates this row **fails**. Empty means eligible.

    Pure, and exported without an underscore, because this is the sentence D6 turns on: *"the rules
    select the batch, a human presses the button, and the server re-checks the predicates at press
    time rather than at render time."* A predicate function that cannot be unit-tested on its own is
    a predicate nobody checks.

    Predicate-by-predicate, with the two judgement calls stated:

    1. **Zero displacement** -- no overlapping live claim and no dock block over the interval. Uses
       the same `displacement_conflicts` set `confirm_request` refuses on, so bulk and individual
       confirm cannot disagree about what a conflict is.
    2. **Exact dock-type match** -- `required_dock_type == dock_type`, i.e. section 5 Stage 2's
       `exact_dock_type_match`, the flag that decides whether `compatible_but_not_exact_dock_penalty`
       applies. A shipment whose `required_dock_type` is `ANY` therefore never qualifies for the safe
       batch: it is *compatible*, not *exact*, and section 7.3 asks for exact.
    3. **ETA confidence is not LOW** -- and a **NULL confidence also fails**. Absent confidence is
       not the same as high confidence, and section 7.3's own grounding case (SHP1013/MSG005, `LOW`)
       is "do not confirm -- ask first". Failing open here would put exactly that row in the batch.
    4. **Inside operating hours and before `LAST_NEW_START_TIME`** -- evaluated through Stage 1's own
       helpers against the D1-authoritative interval, not the slot row.
    5. **No open escalation on the shipment** -- `escalation_queue` in OPEN / ACKNOWLEDGED /
       IN_PROGRESS.
    """
    failed: list[str] = []

    if displacement_conflicts(snapshot):
        failed.append(PREDICATE_ZERO_DISPLACEMENT)

    if str(inputs.get("required_dock_type") or "") != str(inputs.get("dock_type") or ""):
        failed.append(PREDICATE_EXACT_DOCK_MATCH)

    confidence = str(inputs.get("eta_confidence") or "").upper()
    if confidence in {"", "LOW"}:
        failed.append(PREDICATE_ETA_CONFIDENCE_NOT_LOW)

    tz_name = str(inputs["timezone"])
    interval_start = snapshot["interval_start"]
    interval_end = snapshot["interval_end"]
    inside_window = _facility_window_ok(
        interval_start,
        interval_end,
        tz_name=tz_name,
        open_time=str(inputs["open_time"]),
        close_time=str(inputs["close_time"]),
    )
    if inside_window:
        rules = json.loads(str(inputs.get("last_new_start_rules_json") or "[]"))
        local_start = _to_local(interval_start, tz_name)
        for rule in active_facility_rules(rules, at=interval_start, tz_name=tz_name):
            try:
                cutoff = _parse_local_time(str(rule.get("rule_value") or ""))
            except ValueError:
                continue
            # Strictly after, matching `check_facility_rules`: a start exactly at RULE005's cutoff
            # is still permitted.
            if local_start.time() > cutoff:
                inside_window = False
                break
    if not inside_window:
        failed.append(PREDICATE_INSIDE_OPERATING_WINDOW)

    if int(inputs.get("open_escalation_count") or 0) > 0:
        failed.append(PREDICATE_NO_OPEN_ESCALATION)

    return failed


async def bulk_confirm(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    command: BulkConfirmCommand,
    idempotency_key: str,
) -> BulkConfirmResult:
    """section 7.5.1 `bulk_confirm` -- how throughput is recovered without breaking D6.

    ## The one thing that makes this legitimate

    section 7.5.1: *"A client-side-only predicate check would be auto-confirmation wearing a
    button."* Every one of section 7.3's five predicates is therefore re-evaluated **here**, at
    press time, from current rows -- `evaluate_safe_batch_predicates` -- and any id that fails one is
    skipped with the failing predicate named. Nothing about the client's selection is trusted beyond
    the list of ids.

    ## Lock ordering, and why it is not incidental

    Rows are locked one at a time in **sorted `appointment_id` order**. Two coordinators clearing an
    overlapping spike would otherwise be able to take the same two rows in opposite orders and
    deadlock; a fixed global order makes that impossible. It is a loop rather than one
    `WHERE ... = ANY(...) ORDER BY ... FOR UPDATE` statement on purpose: the planner is free to
    choose a bitmap heap scan for a small `ANY()` list, in which case rows are locked in *scan*
    order and the ORDER BY provides no ordering guarantee at all. At section 7.3's own batch size
    (20-35 in a spike, capped at `MAX_BULK_CONFIRM_IDS`) the extra round trips are the cheaper half
    of that trade.

    ## Partial success is the contract, not a compromise

    Flow 6 step 4: *"never a silent partial success. A skipped row stays in the queue, visibly, for
    individual review."* One transaction, one commit; skipped ids are simply never written.

    ## The `snapshot_hash` reading, stated because it is a judgement call

    section 7.5.1 gives this tool a **single** `snapshot_hash` for a **list** of ids, so it is
    computed as the composite of the per-row hashes (`snapshot.batch_snapshot_hash`). A mismatch is
    reported (`snapshot_hash_matched = False`) but **does not refuse the batch**, because Flow 6
    step 3 explicitly wants per-id outcomes when eligibility changed between selection and click,
    and because during a spike -- the only time this tool is used -- some row in a 30-row selection
    has almost always moved. Refusing the whole batch on that would make the spike-clearing path
    unusable in exactly the conditions it exists for. The authoritative gate is the five-predicate
    re-check, which is strictly stronger than a hash compare: it refuses on what is true *now*, not
    on whether anything changed. **Owner fork:** if the batch should hard-refuse on drift instead,
    that is a one-line change here and a real UX decision, not an implementation detail.
    """
    route = "POST /api/v1/appointments/bulk-confirm"
    req_hash = payload_hash(command.model_dump())
    replay = await lookup_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if replay is not None:
        return BulkConfirmResult.model_validate({**replay["response"], "idempotent_replay": True})

    requested_ids = sorted({str(appointment_id) for appointment_id in command.appointment_ids})

    locked: dict[str, dict[str, Any]] = {}
    for appointment_id in requested_ids:
        row = (
            await session.execute(
                text(
                    """
                    SELECT appointment_id, shipment_id, slot_id, appointment_status,
                           booking_source, is_current, booked_at, confirmed_at,
                           cancelled_at, cancellation_reason, replaced_appointment_id,
                           warehouse_confirmation_ref, updated_at
                    FROM public.appointments
                    WHERE appointment_id = :appointment_id
                    FOR UPDATE
                    """
                ),
                {"appointment_id": appointment_id},
            )
        ).mappings().first()
        if row is not None:
            locked[appointment_id] = dict(row)

    found_ids = sorted(locked)
    inputs = await _safe_batch_inputs(session, found_ids)
    snapshots = await load_appointment_snapshots(
        session, found_ids, actor_user_id=ctx.user_id
    )

    current_batch_hash = batch_snapshot_hash(
        {appointment_id: snapshot["snapshot_hash"] for appointment_id, snapshot in snapshots.items()}
    )

    now = datetime.now(timezone.utc)
    outcomes: list[BulkConfirmOutcome] = []
    confirmed = 0

    for appointment_id in requested_ids:
        appointment = locked.get(appointment_id)
        if appointment is None:
            outcomes.append(
                BulkConfirmOutcome(
                    appointment_id=appointment_id,
                    code="NOT_FOUND",
                    detail="No appointment with this id.",
                )
            )
            continue

        row_inputs = inputs.get(appointment_id)
        snapshot = snapshots.get(appointment_id)
        shipment_id = str(appointment["shipment_id"])
        if row_inputs is None or snapshot is None:
            # Unreachable while the two reads above cover the same ids; loud rather than tolerated,
            # because silently skipping here would look identical to a legitimate skip.
            outcomes.append(
                BulkConfirmOutcome(
                    appointment_id=appointment_id,
                    shipment_id=shipment_id,
                    code="NOT_FOUND",
                    detail="Appointment context could not be resolved.",
                )
            )
            continue

        # Scope from the verified identity, per id, never from the request (M15). A planner's own
        # queue can only ever surface their own facility, so a foreign id here means a bad client --
        # it is refused for that id rather than failing the whole batch.
        try:
            _assert_ops_scope(
                ctx,
                {"destination_facility_id": row_inputs["destination_facility_id"]},
            )
        except AppError:
            outcomes.append(
                BulkConfirmOutcome(
                    appointment_id=appointment_id,
                    shipment_id=shipment_id,
                    code="OUT_OF_SCOPE",
                    detail="Appointment is outside the caller's facility scope.",
                )
            )
            continue

        status = str(appointment["appointment_status"])
        if status != "PENDING_CONFIRMATION":
            outcomes.append(
                BulkConfirmOutcome(
                    appointment_id=appointment_id,
                    shipment_id=shipment_id,
                    code="ALREADY_ACTIONED",
                    detail=f"Already {status}.",
                    snapshot_hash=snapshot["snapshot_hash"],
                )
            )
            continue

        conflicts = displacement_conflicts(snapshot)
        failed = evaluate_safe_batch_predicates(inputs=row_inputs, snapshot=snapshot)
        if failed:
            # DISPLACEMENT_DETECTED is reported as its own code when displacement is the *reason*,
            # so the batch summary and the individual-confirm refusal use the same vocabulary for
            # the same event (section 7.5.1 lists it as a distinct outcome, not as a predicate
            # failure).
            code = "DISPLACEMENT_DETECTED" if PREDICATE_ZERO_DISPLACEMENT in failed else "NOT_ELIGIBLE"
            outcomes.append(
                BulkConfirmOutcome(
                    appointment_id=appointment_id,
                    shipment_id=shipment_id,
                    code=code,
                    detail=f"Failed safe-batch predicates: {', '.join(failed)}.",
                    failed_predicates=failed,
                    conflicts=conflicts,
                    snapshot_hash=snapshot["snapshot_hash"],
                )
            )
            continue

        await _apply_confirmation(
            session,
            ctx,
            appointment_id=appointment_id,
            old_status=status,
            now=now,
            warehouse_confirmation_ref=command.warehouse_confirmation_ref,
            note=command.note,
        )
        confirmed += 1
        outcomes.append(
            BulkConfirmOutcome(
                appointment_id=appointment_id,
                shipment_id=shipment_id,
                code="CONFIRMED",
                snapshot_hash=snapshot["snapshot_hash"],
            )
        )

    result = BulkConfirmResult(
        as_of=_as_of(),
        requested=len(requested_ids),
        confirmed=confirmed,
        skipped=len(requested_ids) - confirmed,
        snapshot_hash_matched=current_batch_hash == command.snapshot_hash,
        expected_snapshot_hash=command.snapshot_hash,
        current_snapshot_hash=current_batch_hash,
        outcomes=outcomes,
        idempotency_key=idempotency_key,
        appointment_writes=confirmed,
    )
    await store_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route,
        request_hash=req_hash, response=result.model_dump(),
    )
    await session.commit()
    return result
