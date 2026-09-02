"""The facility sequencer -- SOLUTION_DESIGN.md section 5 Stage 4 / section 5.1 / section 7.5.3.

GitHub issues #49 (the engine and its three tools), #54 (section 7.5.5's ops delegate), #69's
remaining half (`P_churn`, which lives in this objective and nowhere else).

Design citation, per contract element:

| This module | Design |
|---|---|
| one facility, 4 h or `close_time` | section 5.1 "Run scope" |
| release = `gate_in_ts` else effective ETA | section 5.1's job table, "Release *r_j*" |
| processing = `expected_unload_min + 15` | section 5.1's job table / D10 |
| eligible docks = Stage-1 survivors | section 5.1's job table, "Eligible docks *M_j*" |
| in-progress unloads pinned | section 5.1's job table, "Fixed tasks" |
| outage windows as unavailability | section 5.1's job table, "Machine downtime" |
| the objective, term for term | section 5.1 "Objective -- one currency with Stage 2" + "Pricing churn" |
| score-ordered greedy + local improvement | section 5.1 "Algorithm", steps 1-5 |
| diff, not a schedule | section 5.1 "What the planner actually receives (D5)" |
| all-or-nothing apply | section 5.1's first apply rule |
| snapshot-guarded apply | section 5.1's second apply rule |
| one active run per facility | section 5.1 "Debounce" |
| the sequencer proposes, a planner applies | D5 |

Requirements: `ARCHITECTURE/REQUIREMENTS.md` FR-SYS-016 (facility sequencer with
proposal-and-approve), FR-SYS-019 (capacity-incident batching -- one incident, not N escalations),
FR-OPS-004 (ops triages an incident and requests a proposal), FR-PLN-009 (planner reviews and
applies, all-or-nothing), FR-SYS-042 (`scheduling_runs` as a decision-receipt observability layer),
NFR-006 (zero double-booked capacity), NFR-007 (determinism -- byte-identical proposal for the same
snapshot and policy version).

## The one rule that shapes every line below: this module invents no capacity rule

Every hard constraint the sequencer applies is evaluated by
`scheduling/feasibility.py::evaluate_candidate_slot` -- the same function `find_feasible_slots`,
`explain_slot_eligibility` and `allocation.request_slot`'s revalidation all call. Every overlap
question is answered against `repositories/operations.py::list_live_dock_occupancy`, D1's single
"what is on this dock" read (issue #84's fix), plus the claim window
`scheduling/occupancy.py::claim_window_sql` defines. Every write goes through
`allocation._release_dock_occupancy` / `allocation._claim_dock_occupancy`, the same pair
`counter_offer` uses. There is no second definition of *occupied*, *eligible* or *claimed* anywhere
in this file, because issues #84, #88, #97 and #98 are all one recurring failure -- a second copy of
a predicate that drifted from the first -- and a whole new engine is the easiest place in this
codebase to commit it again.

The two private imports from `allocation.py` are deliberate for exactly that reason, and follow the
precedent `allocation.py` itself set when it imported `feasibility._facility_window_ok` rather than
restating it: *"a second copy here is precisely the drift that would let the batch path confirm
something the individual path would refuse."* Section 5.1's own framing -- the sequencer's proposal
must be applicable by the ordinary write path -- is only true if it literally is the ordinary write
path.

## The objective, exactly as section 5.1 writes it

    minimise Sigma_j [ w_j * max(0, start_j - d_j)      # lateness against the promise
                     + 6 * (start_j - r_j)              # driver waiting  (Stage 2: -6/min)
                     + 25 * [dock_j not exact match] ]  # fallback dock   (Stage 2: -25)
           + P_churn * |{ j : promise communicated AND |start_j - promised_j| > 15 min }|

and section 5.1's own instruction about the coefficients: *"Use the same coefficients with inverted
sign -- the sequencer minimises exactly what Stage 2 maximises."* So **none of 6, 25 or the priority
weights is written down in this file.** They are read from `constraints.json`'s `score_weights` and
`priority_scores` -- the same object `feasibility._rank_slot` reads -- and inverted. Hard-coding
them would recreate the exact contradiction section 5.1 opens by warning about: *"If the per-driver
ranker maximises a utility and the sequencer minimises an unrelated cost, the two will recommend
different things and the planner sees the system contradict itself."*

Two of the four terms are not even recomputed here: `wait_after_eta_minutes` and the exact-dock
flag come straight out of the `ranking_factors` receipt `_rank_slot` already produced for the
candidate, so the waiting and fallback-dock costs are *arithmetically* the Stage-2 terms with the
sign flipped, not merely modelled on them. `test_scheduling_sequencer.py` pins that identity.

**The fifth term, D7's fairness penalty**, is the same trick again: `ranking_factors
['fairness_penalty']` is Stage 2's own signed `w_fairness * carrier_concentration` (issue #69), and
the sequencer's cost is its literal negation. `w_fairness` is expected NEGATIVE when enabled, so the
negation is a non-negative cost; at the shipped `w_fairness = 0` the term is exactly 0 and the
objective is byte-identical to section 5.1's four-term formula. This is why the sequencer needed no
new fairness plumbing at all -- #69 built it in the ranker, and one currency means one term.

**`P_churn` is this module's own**, and it is the half of #69 that could not be built before the
sequencer existed. Section 5.1: *"Set `P_churn` ~ **30 weighted-minute-equivalents per moved
promise**... A move must pay for itself. The 15-minute epsilon matches the D11 grid, so sub-grid
jitter never counts as churn. `P_churn` lives in `policy_versions` alongside the Stage-2 weights
(D7) and is stamped on every run."* It is therefore a real `score_weights` key in
`constraints.json`, which is what un-refuses it in `admin_governance_service._validate_weight_keys`
(that allowlist is derived from the file, so adding the key here is the whole of #69's remainder on
the admin side).

### Two definitional choices the design leaves to the implementation, stated rather than buried

1. **`start_j` is the CLAIM start, not the unload start, for lateness and churn; and the unload
   start for waiting.** They differ: `_claim_dock_occupancy` reserves from `slot_start_ts` for
   `expected_unload_min + 15`, while a truck arriving after `slot_start_ts` begins unloading at
   `max(release, slot_start)`. Lateness against a promise and churn are about *the appointment the
   driver was given* -- a slot start -- so they use it; waiting is about the person in the cab, so
   it uses the unload start, which is exactly what Stage 2 already measures. Using one for both
   would make the objective disagree either with the promise or with the driver.

2. **"Promise communicated" means `appointment_status IN ('CONFIRMED','IN_PROGRESS')`.** Section 4's
   lifecycle is what grounds it: confirmation is the transition that notifies the driver
   (`notification_outbox.APPOINTMENT_CONFIRMED` is enqueued there and nowhere else), while a
   `PENDING_CONFIRMATION` row is a request the warehouse has not yet accepted -- section 5.1's own
   diff example marks exactly such a row *"(not yet communicated)"*. Moving an uncommunicated
   request costs nothing in trust, which is why it must not be priced as churn.

## What is deliberately NOT built, named rather than left to be discovered

* **The 30-60 s trigger-coalescing window** (section 5.1 "Debounce"). Its other half -- one active
  run per facility -- is a database constraint (see the migration). The window has nothing to
  coalesce: section 5.1's seven event-driven recompute triggers have no producer in this system, so
  every run is asked for by a human today.
* **CP-SAT.** Section 5.1 explicitly sequences this: *"Start rule-based (the brief explicitly allows
  this)... upgrade to OR-Tools CP-SAT only if you have time. Keep the interface identical so the
  engine is swappable."* `_search` below is the seam: it takes a scope and returns placements, and
  nothing above it knows how they were chosen.
* **An escalation per unplaceable job.** Section 5.1's cascade line says an unplaceable shipment
  goes to escalation; section 7.4's cascade rule says one incident must not become N escalations,
  and this run is already attached to one. Unplaceable jobs are named in the proposal with their
  Stage-1 failure code instead. Flagged as an owner fork on #49 rather than decided here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.core.settings import get_settings
from app.repositories import operations as operations_repo
from app.repositories import scheduling_runs as runs_repo
from app.repositories.scope import (
    assert_facility_visible,
    assert_facility_write_scope,
    resolve_facility_scope_with_user_scopes,
)
from app.scheduling.constraints import load_scheduling_constraints
from app.scheduling.feasibility import (
    CANCELLED_SHIPMENT_STATUSES,
    INACTIVE_EXCEPTION_STATUSES,
    WEIGHT_FAIRNESS,
    FeasibleSlotOption,
    _to_local,
    evaluate_candidate_slot,
)
from app.scheduling.occupancy import CAPACITY_CONSUMING_STATES, CHANGEOVER_BUFFER_MINUTES
from app.scheduling.snapshot import batch_snapshot_hash, load_appointment_snapshots
from app.services import notification_outbox
from app.services.idempotency import lookup_idempotency, payload_hash, store_idempotency
from app.services.ids import new_id

# ---------------------------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------------------------

#: The two `trigger_reason` values with a real producer -- see the migration's own comment on why
#: section 5.1's seven event-driven triggers are absent from the CHECK constraint.
TRIGGER_CAPACITY_INCIDENT = "CAPACITY_INCIDENT"  # section 7.5.5's `request_sequencer_proposal`
TRIGGER_PLANNER_REQUESTED = "PLANNER_REQUESTED"  # planner Flow 9's "self-triggered" origin
TRIGGER_REASONS = frozenset({TRIGGER_CAPACITY_INCIDENT, TRIGGER_PLANNER_REQUESTED})

STATUS_PROPOSED = "PROPOSED"
STATUS_APPLIED = "APPLIED"
STATUS_SUPERSEDED = "SUPERSEDED"

SUPERSEDED_HORIZON_PASSED = "HORIZON_PASSED"
SUPERSEDED_SNAPSHOT_DRIFT = "SNAPSHOT_DRIFT"
SUPERSEDED_PARTIALLY_INFEASIBLE = "PARTIALLY_INFEASIBLE"

#: Section 5.1's churn epsilon: *"The 15-minute epsilon matches the D11 grid, so sub-grid jitter
#: never counts as churn."* D11 is the 15-minute start grid, so this is that decision's number and
#: not an independent one -- if the grid ever changes, this follows it.
CHURN_EPSILON_MINUTES = 15

#: `constraints.json` key for section 5.1's churn price. Named here for the same reason
#: `feasibility.WEIGHT_FAIRNESS` is named there: two modules read it and a string literal in each is
#: how they drift.
WEIGHT_CHURN = "P_churn"

#: Appointment statuses whose promise has been communicated to the driver -- see the module
#: docstring's definitional note 2.
COMMUNICATED_STATUSES = frozenset({"CONFIRMED", "IN_PROGRESS"})

#: Statuses a run may move a promise from. `IN_PROGRESS` is absent on purpose: section 5.1 pins
#: in-progress unloads as fixed tasks, and a truck on a dock cannot be re-sequenced by a proposal.
MOVABLE_STATUSES = frozenset({"PENDING_CONFIRMATION", "CONFIRMED"})

#: `facility_checkins.queue_state` values that mean the truck is physically on a dock, i.e. a fixed
#: task even if its appointment row has not reached IN_PROGRESS yet. Section 5.1's job table sources
#: fixed tasks from exactly this column and value.
IN_DOCK_QUEUE_STATE = "IN_DOCK"

#: Section 7.3's load arithmetic puts a disruption spike at 20-35 requests inside 30 minutes, and a
#: 4-hour horizon at one facility carries roughly 10-12 trucks per dock per day (section 0's own
#: arithmetic). A cap comfortably above both refuses a runaway scope without ever refusing a real
#: one, and keeps the O(jobs^2) pairwise-swap pass below bounded by construction.
MAX_JOBS = 80

#: How far past `horizon_end` a placement made *inside* the horizon can still occupy dock time, and
#: therefore how far past it the occupancy read must look for conflicts.
#:
#: A slot starting one minute before the horizon closes still takes `expected_unload_min` plus
#: D10's 15-minute changeover, so the run's own writes reach beyond its own window. An occupancy
#: read bounded at `horizon_end` would not see a claim beginning just after it, and the proposal
#: would be built on capacity the D1 exclusion constraint then refuses -- found exactly that way by
#: `tests/proof/test_part12_sequencer.py`, not reasoned about in advance.
#:
#: 8 hours is a deliberate over-estimate rather than `max(expected_unload_min)` over the job set:
#: the read is one indexed range scan at one facility either way, and a bound derived from the job
#: set would silently shrink whenever the job set did. `Source: assumption, untested` on the exact
#: figure -- no design line fixes a maximum unload duration; the seeded values run to 90 minutes.
MAX_CLAIM_SPILL_MINUTES = 8 * 60

#: Candidate slots scanned per run. Same bound and the same reasoning as
#: `find_feasible_slots`' own LIMIT 500: a 4-hour window at the busiest facility is well inside it,
#: and an unbounded scan is how a proposal turns into a table scan.
MAX_CANDIDATE_SLOTS = 500

#: Section 5 Stage 2's default priority weights, used only if `constraints.json` somehow carries
#: none. Identical to `feasibility._rank_slot`'s own fallback, which is where the numbers come from.
_DEFAULT_PRIORITY_SCORES = {"CRITICAL": 4000, "HIGH": 3000, "NORMAL": 2000, "LOW": 1000, "UNKNOWN": 500}

#: Audit vocabulary. `audit_logs_action_type_check` admits a closed set (last set by migration
#: 20260829134929), so the specific event rides in `new_value_json.transition` -- the same "generic
#: action_type, specific payload" shape `allocation.AUDIT_ACTION_COUNTER_OFFER` and
#: `gate_yard_service._write_audit` already use, for the same reason.
AUDIT_ACTION_MOVE = "RESCHEDULE_APPOINTMENT"
AUDIT_ACTION_PLACE = "BOOK_APPOINTMENT"
AUDIT_TRANSITION_MOVED = "SEQUENCER_MOVED"
AUDIT_TRANSITION_PLACED = "SEQUENCER_PLACED"

#: `appointments.booking_source` for a placement this engine created. A designed value in the
#: shipped baseline schema (20260805201923:175), not a new one -- the CHECK admits
#: PLANNER / DRIVER_CHAT / WAREHOUSE / SCHEDULING_TOOL / MANUAL_OVERRIDE, and a proposal applied by
#: a planner is precisely a scheduling tool's booking rather than a driver's chat.
BOOKING_SOURCE_SEQUENCER = "SCHEDULING_TOOL"

RELEASE_SOURCE_GATE_IN = "GATE_IN"
RELEASE_SOURCE_ETA = "ETA"


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def _minutes(start: datetime, end: datetime) -> int:
    """Whole minutes from `start` to `end`, signed. Same truncating arithmetic as
    `feasibility._minutes_between`, so the two never disagree about a 90-second gap."""
    return int((end.timestamp() - start.timestamp()) // 60)


def claim_window(start: datetime, unload_min: int) -> tuple[datetime, datetime]:
    """The interval a claim on this slot would occupy: start, plus unload, plus D10's buffer.

    The Python mirror of `occupancy.claim_window_sql`, and it reuses that module's own
    `CHANGEOVER_BUFFER_MINUTES` rather than a second 15 -- one constant, two renderings. This is the
    interval the greedy pass must keep disjoint per dock, and it is deliberately **not** the
    published slot window: a 75-minute unload booked into a 60-minute slot overruns it, which is
    section 6.2 #1 and the entire reason D1 exists. Reasoning about slot windows here would let the
    sequencer propose two placements PostgreSQL's exclusion constraint then refuses.

    `tests/unit/test_scheduling_sequencer.py` pins this against the SQL fragment's own text.
    """
    return start, start + timedelta(minutes=unload_min + CHANGEOVER_BUFFER_MINUTES)


def _overlaps(a: tuple[datetime, datetime], b: tuple[datetime, datetime]) -> bool:
    """Half-open overlap, matching `tstzrange(..., '[)')` and the `&&` operator the D1 exclusion
    constraint uses. Two abutting windows do not overlap -- PostgreSQL "Range Functions and
    Operators": `&&` is "have any elements in common", adjacency is the separate `-|-`. Same
    predicate as `planner_service._overlaps`, which answers this question for the queue's
    displacement check."""
    return a[0] < b[1] and b[0] < a[1]


# ---------------------------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------------------------


class ObjectiveValues(BaseModel):
    """Section 5.1's objective, term by term, so a planner can see what a proposal is buying.

    Every term is reported even when it is zero -- the same rule `_rank_slot`'s `ranking_factors`
    follows since issue #69: *"'the fairness term contributed nothing' and 'there is no fairness
    term' must be distinguishable by reading the receipt."*
    """

    model_config = ConfigDict(extra="forbid")

    policy_version: str
    lateness_cost: int = 0
    waiting_cost: int = 0
    fallback_dock_cost: int = 0
    churn_cost: int = 0
    fairness_cost: int = 0
    total_cost: int = 0

    #: Section 5.1's `P_churn` multiplicand: promises communicated AND moved by more than the
    #: 15-minute epsilon. This is D7's "count of promises the Sequencer moved" -- issue #69's
    #: `P_churn`, which had no source until this module existed.
    churn_count: int = 0
    #: Every moved placement, communicated or not. `churn_count <= promises_moved` always.
    promises_moved: int = 0

    placements: int = 0
    unchanged_count: int = 0
    newly_placed_count: int = 0
    unplaceable_count: int = 0

    #: Section 5.1's own headline line ("Effect: total driver waiting -85 min"): the proposal's
    #: total driver waiting, and the change against what the current schedule would produce.
    waiting_minutes_total: int = 0
    waiting_minutes_delta: int = 0

    #: The coefficients this run was scored with, stamped on the run per D7 / section 5 Stage 2
    #: ("stamp the version onto every decision"). Stored so a proposal read a month later can be
    #: re-derived even if the live policy has moved on.
    coefficients: dict[str, Any] = Field(default_factory=dict)


class PlacementView(BaseModel):
    """One job's row in the section 5.1 diff."""

    model_config = ConfigDict(extra="forbid")

    shipment_id: str
    appointment_id: str | None = None
    order_reference: str | None = None
    priority_code: str
    carrier_id: str | None = None

    dock_id: str
    dock_code: str
    slot_id: str
    #: The promised interval: the slot the driver is (or would be) given.
    start_ts: str
    end_ts: str
    #: The D1 interval a claim actually reserves -- start + unload + D10's buffer. Rendered on the
    #: planner's board, which draws claims and not slots.
    claim_start_ts: str
    claim_end_ts: str

    #: Where the job is today, for a `moved` row. `None` for `newly_placed`.
    previous_slot_id: str | None = None
    previous_dock_id: str | None = None
    previous_dock_code: str | None = None
    previous_start_ts: str | None = None
    #: Signed minutes the promise moves by. Negative means earlier.
    delta_minutes: int | None = None

    #: Section 5.1's own annotation on a moved row: "(not yet communicated)" vs "(communicated --
    #: driver will be notified)". `is_churn` is the second one AND past the 15-minute epsilon, i.e.
    #: exactly what `P_churn` counts.
    communicated: bool = False
    is_churn: bool = False
    #: A fixed task (section 5.1): an in-progress unload pins its dock and cannot be moved.
    pinned: bool = False

    release_ts: str
    release_source: str
    wait_minutes: int = 0
    lateness_minutes: int = 0
    exact_dock_match: bool = True
    cost: int = 0


class UnplaceableView(BaseModel):
    """A job Stage 1 could not place anywhere in the horizon, with the constraint that refused it.

    Section 5.1's example row: *"Unplaceable: SHP1015 -- no compatible reefer interval before close
    -> escalation."* The failure code and message come straight from
    `evaluate_candidate_slot`'s own `InfeasibleSlotReason`, so the sequencer explains a refusal in
    the same vocabulary the driver path does rather than inventing a second one.
    """

    model_config = ConfigDict(extra="forbid")

    shipment_id: str
    order_reference: str | None = None
    priority_code: str
    release_ts: str
    release_source: str
    failure_code: str
    message: str
    candidates_considered: int = 0


class ProposalDiff(BaseModel):
    """Section 5.1: *"What the planner actually receives (D5) -- a diff, not a schedule."*"""

    model_config = ConfigDict(extra="forbid")

    unchanged: list[PlacementView] = Field(default_factory=list)
    moved: list[PlacementView] = Field(default_factory=list)
    newly_placed: list[PlacementView] = Field(default_factory=list)
    unplaceable: list[UnplaceableView] = Field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "unchanged": len(self.unchanged),
            "moved": len(self.moved),
            "newly_placed": len(self.newly_placed),
            "unplaceable": len(self.unplaceable),
        }


class HorizonView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_ts: str
    end_ts: str
    end_reason: str


class SchedulingRunResult(BaseModel):
    """`propose_facility_schedule` and `get_scheduling_run` return the same shape.

    Section 7.5.3 defines `get_scheduling_run` as returning "the stored run: input snapshot,
    proposal, objective values, explanation -- replayable a month later", and
    `propose_facility_schedule` as returning "a `scheduling_run_id`, the section 5.1 diff, objective
    values, `snapshot_hash`". One model for both is not a shortcut: a planner reviewing a proposal
    an hour after it was computed must see the identical object the requester saw, or the review is
    of something else.
    """

    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    code: str = "PROPOSED"
    scheduling_run_id: str
    facility_id: str
    facility_name: str | None = None
    trigger_reason: str
    escalation_id: str | None = None
    status: str
    policy_version: str
    snapshot_hash: str
    horizon: HorizonView
    counts: dict[str, int] = Field(default_factory=dict)
    diff: ProposalDiff
    objective: ObjectiveValues
    explanation: str
    requested_by_user_id: str | None = None
    created_at: str | None = None
    applied_at: str | None = None
    applied_by_user_id: str | None = None
    notifications_enqueued: int | None = None
    superseded_at: str | None = None
    superseded_reason: str | None = None
    #: Section 5 Stage 4's "input snapshot": the job set and its section 5.1 parameters, stored so
    #: the run is replayable.
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    #: Only on `RUN_ALREADY_ACTIVE` -- which run is in the way.
    active_run: dict[str, Any] | None = None


class ApplyResult(BaseModel):
    """Section 7.5.3's `apply_schedule_proposal` outcomes, as a discriminated result.

    Section 7.5 principle 2: *"Typed outcomes, never prose. 'It worked' and 'it didn't' must be
    distinguishable by code, not by reading a sentence."*
    """

    model_config = ConfigDict(extra="forbid")

    as_of: str
    code: str
    scheduling_run_id: str
    status: str
    #: Section 7.5.3: `APPLIED` returns "+ notification batch id". One apply is one batch, and the
    #: run id already identifies it uniquely -- so the batch id IS the run id rather than a second
    #: identifier that could disagree with it.
    notification_batch_id: str | None = None
    notifications_enqueued: int = 0
    moved: int = 0
    newly_placed: int = 0
    unchanged: int = 0
    #: Populated on `SNAPSHOT_DRIFT`: what the digest is now, and which appointments moved under
    #: the planner. Flow 9 step 4 requires the overlay to state this plainly.
    drift: dict[str, Any] | None = None
    #: Populated on `PARTIALLY_INFEASIBLE`: every placement that failed revalidation, named.
    #: Flow 9 step 5: "explains which constraint made the whole proposal invalid".
    infeasible: list[dict[str, Any]] = Field(default_factory=list)
    idempotency_key: str | None = None
    idempotent_replay: bool = False


# ---------------------------------------------------------------------------------------------
# Scope -- section 5.1's job set and parameters, read once and shared by propose and apply
# ---------------------------------------------------------------------------------------------


@dataclass
class Job:
    """One inbound shipment needing dock time, with section 5.1's five job parameters resolved."""

    shipment: dict[str, Any]
    #: r_j -- `gate_in_ts` if the truck has arrived, else the effective ETA (section 5.1).
    release: datetime
    release_source: str
    #: d_j -- the current appointment's start, if any.
    due: datetime | None
    #: w_j -- the priority weight (section 5 Stage 2's 4000/3000/2000/1000).
    weight: int
    appointment_id: str | None
    appointment_status: str | None
    current_slot_id: str | None
    current_dock_id: str | None
    current_dock_code: str | None
    current_start: datetime | None
    pinned: bool
    communicated: bool
    driver_window: dict[str, Any]
    #: The D1 claim this job holds **right now**, straight from `dock_occupancy`, or `None` when it
    #: holds none. Two jobs in the shipped seed legitimately have none -- the E1.1 backfill put
    #: `REQUIRES_TIME_RESOLUTION` appointments on the D12 worklist instead of claiming for them.
    #:
    #: `_search` seeds this into its occupied map and lifts it only while considering this job's own
    #: placement. That is the difference between "this run may move you" and "this capacity is
    #: free": a job the search cannot place keeps its claim, so the interval must go on blocking
    #: everyone else. Excluding it unconditionally is what made the proof suite's first apply hit
    #: `dock_occupancy_dock_id_window_excl` on a proposal the search believed was conflict-free.
    current_claim: tuple[datetime, datetime] | None = None
    current_claim_dock: str | None = None
    #: Feasible placements, computed once by `_evaluate_jobs` and reused by every pass of the
    #: search. Keyed by slot id.
    options: dict[str, FeasibleSlotOption] = field(default_factory=dict)
    #: The Stage-1 refusal seen most often across the candidate set, for an unplaceable row.
    first_refusal: tuple[str, str] | None = None
    candidates_considered: int = 0

    @property
    def shipment_id(self) -> str:
        return str(self.shipment["shipment_id"])

    @property
    def unload_min(self) -> int:
        return int(self.shipment["expected_unload_min"])


@dataclass
class Scope:
    """Everything one run reasons over. Built once per propose and once per apply."""

    facility: dict[str, Any]
    facility_rules: list[dict[str, Any]]
    horizon_start: datetime
    horizon_end: datetime
    horizon_end_reason: str
    jobs: list[Job]
    #: Claim intervals this run may not touch: external bookings, live D2 holds, and fixed tasks.
    #: Keyed by dock id. Section 5.1's "Fixed tasks" and "Machine downtime" both land here.
    blocked: dict[str, list[tuple[datetime, datetime]]]
    candidates: list[dict[str, Any]]
    truncated_jobs: bool = False


def _job_weight(priority_code: str, priority_scores: dict[str, int]) -> int:
    return int(priority_scores.get(priority_code, priority_scores.get("UNKNOWN", 500)))


def _resolve_horizon(
    *,
    facility: dict[str, Any],
    now: datetime,
    requested_end: datetime | None,
) -> tuple[datetime, datetime, str]:
    """Section 5.1's run scope: *"rolling horizon of 4 hours or to `close_time`, whichever is
    sooner."*

    Computed by `planner_service._board_horizon_end`, not by a second implementation, because the
    planner's dock board draws its axis from that function and a proposal whose horizon disagreed
    with the board it is rendered on would be unreviewable. That helper also carries the
    facility-local `close_time` parse and its `ZoneInfo` fallbacks, which are exactly the
    wrong-day hazards U48 exists against.

    Imported locally rather than at module scope: `planner_service` imports `scheduling.expiry`,
    which imports `scheduling.allocation`, so a top-level import here would put a service module in
    this package's import graph and hand a future `planner_service` -> `sequencer` import (for the
    board's "[ Review proposal (N) ]" count) a real cycle. Same hook shape
    `allocation._claim_dock_occupancy` uses for `holds`.

    `horizon_end?` is section 7.5.3's own optional argument and can only ever **narrow**: a caller
    who could widen it past four hours would be planning on driver-declared ETAs that section 5.1
    calls "false precision", and reading a different horizon from the board's.
    """
    from app.services.planner_service import _board_horizon_end

    horizon_end, reason = _board_horizon_end(
        now,
        timezone_name=facility.get("timezone"),
        close_time=facility.get("close_time"),
        requested_hours=None,
    )
    if requested_end is not None:
        if requested_end.tzinfo is None:
            raise AppError(
                "horizon_end must carry a timezone offset.",
                code="INVALID_HORIZON",
                status_code=422,
            )
        if requested_end <= now:
            raise AppError(
                "horizon_end must be in the future.", code="INVALID_HORIZON", status_code=422
            )
        if requested_end < horizon_end:
            horizon_end, reason = requested_end, "CALLER_NARROWED"
    return now, horizon_end, reason


async def _load_facility(session: AsyncSession, facility_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The facility row plus its active rules, in one round trip.

    Byte-identical shape to `find_feasible_slots`' own facility read (including the correlated
    `facility_rules` aggregate) because `evaluate_candidate_slot` consumes both and must be handed
    exactly what it is handed on the driver path. Section 5 Stage 1's *"rule absence is permission,
    not inheritance"* is why the aggregate is scoped strictly to this `facility_id`.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT f.facility_id, f.facility_name, f.timezone, f.open_time, f.close_time,
                       f.active_flag,
                       (SELECT coalesce(json_agg(json_build_object(
                                 'rule_id', fr.rule_id,
                                 'rule_type', fr.rule_type,
                                 'rule_value', fr.rule_value,
                                 'effective_from', fr.effective_from,
                                 'effective_to', fr.effective_to))::text, '[]')
                          FROM public.facility_rules fr
                         WHERE fr.facility_id = f.facility_id
                           AND fr.active_flag = 1) AS facility_rules_json
                FROM public.facilities f
                WHERE f.facility_id = :facility_id
                """
            ),
            {"facility_id": facility_id},
        )
    ).mappings().first()
    if row is None or not int(row["active_flag"]):
        raise AppError("Facility is not active.", code="FACILITY_UNAVAILABLE", status_code=409)
    facility = dict(row)
    rules = json.loads(str(facility.pop("facility_rules_json") or "[]"))
    return facility, rules


_JOB_SET_SQL = """
SELECT s.shipment_id, s.order_reference, s.driver_id, s.carrier_id,
       s.destination_facility_id, s.priority_code, s.required_dock_type,
       s.temperature_control_required, s.load_weight_kg, s.expected_unload_min,
       s.current_status, s.original_eta_ts, s.latest_eta_ts,
       le.effective_eta_ts, le.eta_source, le.eta_confidence,
       fc.gate_in_ts, fc.queue_state,
       a.appointment_id, a.appointment_status, a.slot_id,
       sl.dock_id, d.dock_code, sl.slot_start_ts, sl.slot_end_ts,
       (SELECT max(de.earliest_acceptable_ts::timestamptz)
          FROM public.driver_exceptions de
         WHERE de.shipment_id = s.shipment_id
           AND de.exception_status NOT IN :inactive_exception_statuses
           AND de.earliest_acceptable_ts IS NOT NULL) AS driver_earliest_acceptable_ts,
       (SELECT min(de.latest_acceptable_ts::timestamptz)
          FROM public.driver_exceptions de
         WHERE de.shipment_id = s.shipment_id
           AND de.exception_status NOT IN :inactive_exception_statuses
           AND de.latest_acceptable_ts IS NOT NULL) AS driver_latest_acceptable_ts
  FROM public.shipments s
  JOIN public.v_latest_eta le ON le.shipment_id = s.shipment_id
  LEFT JOIN public.facility_checkins fc ON fc.shipment_id = s.shipment_id
  LEFT JOIN public.appointments a
         ON a.shipment_id = s.shipment_id
        AND a.is_current = 1
        AND a.appointment_status = ANY(:active_statuses)
  LEFT JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
  LEFT JOIN public.docks d ON d.dock_id = sl.dock_id
 WHERE s.destination_facility_id = :facility_id
   AND s.current_status <> ALL(:inactive_shipment_statuses)
   AND (
         -- Already placed inside the horizon: a candidate to leave alone or to move.
         (sl.slot_start_ts >= :horizon_start AND sl.slot_start_ts < :horizon_end)
         -- Or needing dock time inside the horizon and holding no active appointment at all:
         -- section 5.1's "newly placed". `gate_in_ts` wins over the ETA here for the same reason
         -- it wins as the release time -- an arrived truck is available now whatever the plan said.
      OR (a.appointment_id IS NULL
          AND COALESCE(fc.gate_in_ts, le.effective_eta_ts::timestamptz) < :horizon_end
          AND COALESCE(fc.gate_in_ts, le.effective_eta_ts::timestamptz)
              >= :horizon_start - interval '12 hours')
       )
 ORDER BY s.shipment_id
 LIMIT :max_jobs
"""


async def _load_jobs(
    session: AsyncSession,
    *,
    facility_id: str,
    horizon_start: datetime,
    horizon_end: datetime,
    priority_scores: dict[str, int],
) -> tuple[list[Job], bool]:
    """Section 5.1's job set: *"Job j -- an inbound shipment needing dock time"*.

    Two populations in one scan, because they are two halves of one diff:

    * shipments whose current appointment starts inside the horizon -- the `unchanged` / `moved`
      candidates;
    * shipments with **no** active appointment whose release lands inside the horizon -- the
      `newly placed` / `unplaceable` candidates.

    The second arm's 12-hour lower bound is the one number here without a design citation, and it is
    marked as such: `Source: assumption, untested`. It exists so an overdue truck that should have
    arrived this morning is still a job this afternoon (which is precisely the section 7.3 scenario
    -- SHP-202 "late and waiting"), while a shipment whose ETA passed three days ago is stale data
    rather than a job. No design line fixes the value; it is stated rather than presented as policy.

    `LIMIT :max_jobs` is one more than `MAX_JOBS` at the call site, so truncation is *detected*
    rather than silently applied -- a proposal computed over a truncated job set would double-book
    against the jobs it never saw, so the run reports it instead.
    """
    rows = (
        await session.execute(
            text(_JOB_SET_SQL).bindparams(
                bindparam("inactive_exception_statuses", expanding=True)
            ),
            {
                "facility_id": facility_id,
                "horizon_start": horizon_start,
                "horizon_end": horizon_end,
                "active_statuses": ["PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS"],
                "inactive_shipment_statuses": sorted(CANCELLED_SHIPMENT_STATUSES),
                "inactive_exception_statuses": list(INACTIVE_EXCEPTION_STATUSES),
                "max_jobs": MAX_JOBS + 1,
            },
        )
    ).mappings().all()

    truncated = len(rows) > MAX_JOBS
    jobs: list[Job] = []
    for row in rows[:MAX_JOBS]:
        data = dict(row)
        gate_in = data.get("gate_in_ts")
        effective_eta = _coerce_dt(data.get("effective_eta_ts"))
        if gate_in is not None:
            release, release_source = _coerce_dt(gate_in), RELEASE_SOURCE_GATE_IN
        else:
            release, release_source = effective_eta, RELEASE_SOURCE_ETA
        if release is None:
            # A shipment with neither a gate-in nor a resolvable ETA has no release time, so there
            # is no instant from which "earliest feasible start" means anything. Skipped rather
            # than defaulted to `now`, which would invent an arrival.
            continue
        status = data.get("appointment_status")
        start = _coerce_dt(data.get("slot_start_ts"))
        jobs.append(
            Job(
                shipment=data,
                release=release,
                release_source=release_source,
                due=start,
                weight=_job_weight(str(data.get("priority_code") or "NORMAL"), priority_scores),
                appointment_id=data.get("appointment_id"),
                appointment_status=status,
                current_slot_id=data.get("slot_id"),
                current_dock_id=data.get("dock_id"),
                current_dock_code=data.get("dock_code"),
                current_start=start,
                # Section 5.1's fixed tasks, from both of the columns that can assert one.
                pinned=(
                    status == "IN_PROGRESS"
                    or str(data.get("queue_state") or "") == IN_DOCK_QUEUE_STATE
                ),
                communicated=str(status or "") in COMMUNICATED_STATUSES,
                driver_window={
                    "earliest_acceptable_ts": data.get("driver_earliest_acceptable_ts"),
                    "latest_acceptable_ts": data.get("driver_latest_acceptable_ts"),
                },
            )
        )
    return jobs, truncated


def _coerce_dt(value: Any) -> datetime | None:
    """Accept a real `timestamptz` (asyncpg hands back `datetime`) or an ISO string, UTC-pinned.

    `v_latest_eta.effective_eta_ts` is a view expression over columns migration 20260823060000
    converted, and `eta_updates.declared_eta_ts` is one of them -- but the view has been observed
    to hand back either shape depending on the branch that produced the value, which is why
    `feasibility._coerce_timestamp` exists too. Naive values are treated as UTC, matching
    `snapshot._coerce_ts`.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def _load_candidates(
    session: AsyncSession, *, facility_id: str, horizon_start: datetime, horizon_end: datetime
) -> list[dict[str, Any]]:
    """Every publishable interval in the horizon, in the row shape `evaluate_candidate_slot` eats.

    Deliberately the same projection and the same two LEFT JOINs as `find_feasible_slots`' own
    candidate scan, minus its per-shipment capacity LATERAL. That join binds `:unload_min`, so it
    can only answer for one shipment; this scan serves every job in the run, so the overlap question
    is answered once, for the whole facility, by `list_live_dock_occupancy` -- D1's single
    "what is on this dock" read since issue #84 -- and tested in Python. Exactly the shape
    `planner_service.get_planner_queue` uses for the same reason: *"one query for the whole page
    instead of N."*

    `active_appointment_id` is kept and is load-bearing: it is how `evaluate_candidate_slot` refuses
    a slot another booking already holds. `_evaluate_jobs` nulls it for slots held by a job in this
    run's own set, because a claim this proposal may release is not an obstacle to this proposal.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT sl.slot_id, sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts,
                       sl.slot_status, sl.block_reason, d.dock_code, d.dock_type,
                       d.supports_refrigerated, d.max_vehicle_weight_kg, d.dock_status,
                       a.appointment_id AS active_appointment_id,
                       de.dock_event_id AS active_dock_event_id
                  FROM public.appointment_slots sl
                  JOIN public.docks d ON d.dock_id = sl.dock_id
                  LEFT JOIN public.appointments a
                    ON a.slot_id = sl.slot_id
                   AND a.appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                  LEFT JOIN public.dock_status_events de
                    ON de.dock_id = sl.dock_id
                   AND de.event_type = ANY(:blocking_types)
                   AND de.event_start_ts < sl.slot_end_ts
                   AND (de.event_end_ts IS NULL OR de.event_end_ts > sl.slot_start_ts)
                 WHERE sl.facility_id = :facility_id
                   AND sl.slot_start_ts >= :horizon_start
                   AND sl.slot_start_ts < :horizon_end
                 ORDER BY sl.slot_start_ts, sl.slot_id
                 LIMIT :limit
                """
            ),
            {
                "facility_id": facility_id,
                "horizon_start": horizon_start,
                "horizon_end": horizon_end,
                # Filtering to the four genuinely blocking types via `snapshot.BLOCKING_EVENT_TYPES`
                # -- the ONE vocabulary every consumer now shares. (Historical note: when this was
                # written the driver path's join carried no event_type filter; that divergence was
                # #109, fixed 2026-09-02 across feasibility, allocation's pre-check, the hold path
                # and planner_service's duplicate tuple.)
                "blocking_types": list(_blocking_event_types()),
                "limit": MAX_CANDIDATE_SLOTS,
            },
        )
    ).mappings().all()
    return [dict(row) for row in rows]


def _blocking_event_types() -> tuple[str, ...]:
    """`dock_status_events.event_type` values that mean the dock is unavailable.

    Imported from `snapshot.py` rather than restated: it is the same tuple the planner queue's
    displacement check and the board's outage hatches use, and "blocked" has to mean one thing
    across the proposal, the board and the refusal.
    """
    from app.scheduling.snapshot import BLOCKING_EVENT_TYPES

    return BLOCKING_EVENT_TYPES


async def _load_blocked_intervals(
    session: AsyncSession,
    *,
    facility_id: str,
    horizon_start: datetime,
    horizon_end: datetime,
    job_appointment_ids: set[str],
) -> tuple[
    dict[str, list[tuple[datetime, datetime]]],
    dict[str, tuple[str, datetime, datetime]],
]:
    """Claim intervals this run must plan around, per dock.

    Read through `repositories/operations.py::list_live_dock_occupancy` -- the same call
    `get_planner_queue`'s displacement check and `get_dock_board`'s bars both make. Issue #84 is
    what happens when a second occupancy query is written: its INNER JOIN to `appointments` made
    every D2 hold invisible, so *"the displacement preview said 'nobody would be hurt' about
    capacity the database was already defending."* A sequencer with its own occupancy query would
    reproduce that at facility scale.

    Returns **two** maps, and the split is the correction the proof suite forced:

    * `blocked` -- intervals this run may not touch under any circumstance. Other bookings, live D2
      holds (`appointment_id IS NULL`), in-progress unloads (section 5.1's fixed tasks).
    * `movable_claims` -- the claims of jobs this run *may* move, keyed by appointment id. These are
      **not** simply dropped: `_search` seeds them into its occupied map and lifts each one only
      while deciding that job's own placement. A claim the run does not end up releasing is still a
      claim, and treating "movable" as "already free" is what let a proposal be built on capacity
      the database was still defending -- caught by `test_part12_sequencer.py`'s apply hitting
      `dock_occupancy_dock_id_window_excl`, which is the same class of defect as #84 (a read that
      disagreed with what PostgreSQL would refuse).

    The occupancy window is widened past `horizon_end` by the longest claim any job in this run
    could take, because a placement starting inside the horizon can end outside it: a 06:30 slot
    with a 75-minute unload occupies dock time until 08:00, and a claim beginning at 07:15 would
    conflict with it while sitting entirely outside an un-widened read.
    """
    rows = await operations_repo.list_live_dock_occupancy(
        session,
        facility_id=facility_id,
        range_start=horizon_start,
        range_end=horizon_end + timedelta(minutes=MAX_CLAIM_SPILL_MINUTES),
        active_statuses=["PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS"],
        include_holds=get_settings().two_phase_hold_enabled,
        hold_states=list(CAPACITY_CONSUMING_STATES),
    )
    blocked: dict[str, list[tuple[datetime, datetime]]] = {}
    movable_claims: dict[str, tuple[str, datetime, datetime]] = {}
    for row in rows:
        start = _coerce_dt(row["window_start"])
        end = _coerce_dt(row["window_end"])
        if start is None or end is None:  # pragma: no cover - both are NOT NULL in the range type
            continue
        dock_id = str(row["dock_id"])
        appointment_id = row.get("appointment_id")
        if appointment_id is not None and str(appointment_id) in job_appointment_ids:
            movable_claims[str(appointment_id)] = (dock_id, start, end)
            continue
        blocked.setdefault(dock_id, []).append((start, end))
    return blocked, movable_claims


async def _carrier_concentration(
    session: AsyncSession, *, facility_id: str, horizon_start: datetime, horizon_end: datetime
) -> dict[tuple[str, str], int]:
    """D7's fairness input, keyed `(carrier_id, facility-local date)` -- issue #69's quantity.

    Issued **only when `w_fairness` is non-zero**, the same gate `find_feasible_slots` and
    `simulate_policy_weights` both apply, and for the same reason: at the shipped `w_fairness = 0`
    the term is arithmetically absent, so paying a round trip to multiply by zero would be pure
    cost. One grouped read for the whole run rather than one per (job, candidate) pair, which at
    80 jobs x 500 candidates would be a scan wearing a preview's clothes.

    `AT TIME ZONE <name>` on a `timestamptz` yields the facility-local wall clock, which is what
    makes this a local calendar day -- the same definition `feasibility.py` uses, so the sequencer
    and the per-driver ranker measure the same quantity rather than two similar-sounding ones.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT other.carrier_id AS carrier_id,
                       to_char(sl.slot_start_ts AT TIME ZONE f.timezone, 'YYYY-MM-DD') AS local_date,
                       CAST(count(*) AS integer) AS held_count
                  FROM public.appointments a
                  JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                  JOIN public.shipments other ON other.shipment_id = a.shipment_id
                  JOIN public.facilities f ON f.facility_id = sl.facility_id
                 WHERE a.is_current = 1
                   AND a.appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                   AND sl.facility_id = :facility_id
                   AND sl.slot_start_ts >= :horizon_start - interval '1 day'
                   AND sl.slot_start_ts < :horizon_end + interval '1 day'
                 GROUP BY 1, 2
                """
            ),
            {
                "facility_id": facility_id,
                "horizon_start": horizon_start,
                "horizon_end": horizon_end,
            },
        )
    ).mappings().all()
    return {
        (str(row["carrier_id"]), str(row["local_date"])): int(row["held_count"]) for row in rows
    }


async def build_scope(
    session: AsyncSession,
    *,
    facility_id: str,
    now: datetime,
    requested_end: datetime | None = None,
    frozen_horizon: tuple[datetime, datetime, str] | None = None,
) -> Scope:
    """Assemble section 5.1's run scope. Five reads, counted rather than assumed.

    facility+rules · job set · candidate slots · live occupancy · (fairness, only when enabled).

    `frozen_horizon` is what the **apply** path passes: the horizon stored on the run, not a fresh
    one. This is the load-bearing half of the snapshot guard. Recomputing the window from a new
    `now` would shift the job set every second, so every apply would report `SNAPSHOT_DRIFT` merely
    because time had passed -- the exact noise `snapshot.py`'s module docstring rules out for the
    per-appointment digest (*"A hash that changed every second would make every confirm stale"*).
    Freezing the window is how that rule survives being applied to a whole facility.
    """
    facility, rules = await _load_facility(session, facility_id)
    if frozen_horizon is not None:
        horizon_start, horizon_end, horizon_reason = frozen_horizon
    else:
        horizon_start, horizon_end, horizon_reason = _resolve_horizon(
            facility=facility, now=now, requested_end=requested_end
        )

    policy = load_scheduling_constraints().ranking_policy
    priority_scores = policy.priority_scores or _DEFAULT_PRIORITY_SCORES

    jobs, truncated = await _load_jobs(
        session,
        facility_id=facility_id,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        priority_scores=priority_scores,
    )
    candidates = await _load_candidates(
        session, facility_id=facility_id, horizon_start=horizon_start, horizon_end=horizon_end
    )
    # A pinned job's claim is an obstacle, not a movable promise, so it stays in the blocked set;
    # every other job's claim is excluded because the proposal may release it.
    movable_appointment_ids = {
        str(job.appointment_id)
        for job in jobs
        if job.appointment_id is not None and not job.pinned
    }
    blocked, movable_claims = await _load_blocked_intervals(
        session,
        facility_id=facility_id,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        job_appointment_ids=movable_appointment_ids,
    )
    # Hand each movable job the claim it actually holds, so `_search` can seed it and lift it only
    # for that job's own decision. See `Job.current_claim`.
    for job in jobs:
        held = movable_claims.get(str(job.appointment_id)) if job.appointment_id else None
        if held is not None:
            job.current_claim_dock, job.current_claim = held[0], (held[1], held[2])

    concentration: dict[tuple[str, str], int] = {}
    if policy.score_weights.get(WEIGHT_FAIRNESS, 0):
        concentration = await _carrier_concentration(
            session,
            facility_id=facility_id,
            horizon_start=horizon_start,
            horizon_end=horizon_end,
        )

    scope = Scope(
        facility=facility,
        facility_rules=rules,
        horizon_start=horizon_start,
        horizon_end=horizon_end,
        horizon_end_reason=horizon_reason,
        jobs=jobs,
        blocked=blocked,
        candidates=candidates,
        truncated_jobs=truncated,
    )
    _evaluate_jobs(scope, concentration=concentration)
    return scope


def movable_slot_ids_of(scope: Scope) -> set[str]:
    """Slots currently held by a job this run may move -- i.e. slots whose claim is *releasable*.

    **One rule, two phases, and that is the whole reason this is a function.** `_evaluate_jobs`
    needs it at propose time and `apply_schedule_proposal`'s revalidation needs it at apply time,
    and the two must agree exactly or the apply refuses placements the proposal legitimately made:

      * at propose, a candidate slot occupied by a movable job is *not* an obstacle, because the
        proposal may take that job off it;
      * at apply, the claims have already been released (step 5) but `appointments.slot_id` still
        points at the old slot until each UPDATE lands, so the candidate scan's
        `active_appointment_id` is stale by construction for exactly the same set of slots.

    Getting this wrong is not theoretical: the first run of `tests/proof/test_part12_sequencer.py`
    caught it as a `PARTIALLY_INFEASIBLE` on a proposal that was perfectly feasible -- job A moving
    into job B's old slot while B moved elsewhere, which is the *normal* shape of a re-sequence, not
    an edge case. Two similar-looking inline set comprehensions were what produced it, which is the
    same drift #84/#88/#97 each record for a different predicate.

    Pinned jobs are excluded: a fixed task's slot is an obstacle, because nothing may move it.
    """
    return {
        str(job.current_slot_id)
        for job in scope.jobs
        if job.current_slot_id is not None and not job.pinned
    }


def _evaluate_jobs(scope: Scope, *, concentration: dict[tuple[str, str], int]) -> None:
    """Stage 1 for every (job, candidate) pair -- section 5.1's "Eligible docks *M_j*".

    One call per pair into `evaluate_candidate_slot`, the shared eligibility guard. Nothing here
    decides eligibility; this function only supplies the four inputs that make the shared guard
    answer the *sequencer's* question rather than the driver path's:

    * **`eta_dt = job.release`** -- section 5.1's release rule, *"`gate_in_ts` if the truck has
      arrived, else effective ETA"*, and the sentence that follows it: *"A sequencer that keeps
      using planned ETA for an arrived truck will leave a truck idling in the yard beside an empty
      dock."* `find_feasible_slots` passes the ETA here because a driver asking for options has not
      arrived; a sequencer must pass the release or section 7.3's own scenario is unsolvable.
    * **`active_appointment_id` nulled for this run's own movable claims** -- see `_load_candidates`.
    * **the driver's acceptable window**, which section 5.1's hard-constraint list does not name but
      which is already a Stage-1 invariant on the driver path. Proposing an interval a driver has
      explicitly declared unacceptable would produce a promise the product exists to avoid making;
      honouring it costs nothing because the values ride on the job-set query already.
    * **D7's concentration**, keyed by the candidate's own local date (issue #69).

    A job that is pinned gets no options at all: a fixed task is not a placement decision.

    ## Cost, counted rather than assumed

    This is the only quadratic step in the module: jobs x candidates calls into
    `evaluate_candidate_slot`. **It issues zero queries** -- every input was fetched by
    `build_scope`'s five reads, which is the whole reason the candidate scan is facility-wide
    instead of per-shipment. The real numbers, from section 0's own arithmetic and section 5.1's
    run scope: a 4-hour horizon at the busiest facility is ~4 intervals/hour x 4 hours x 6 docks =
    ~96 candidates, against ~10-20 jobs, so ~1-2k in-process calls per proposal. `MAX_JOBS` (80) and
    `MAX_CANDIDATE_SLOTS` (500) bound the pathological case at 40k, which is still one human-
    triggered action at a 5-concurrent-user scale (NFR-016) -- they are guards against a runaway
    scope, not the expected shape. Nothing here is memoised or parallelised, deliberately: that
    would be machinery for a load this product does not have.
    """
    tz_name = str(scope.facility["timezone"])
    movable_slot_ids = movable_slot_ids_of(scope)
    checked = sorted(load_scheduling_constraints().hard_constraint_ids())

    for job in scope.jobs:
        if job.pinned:
            continue
        carrier_id = str(job.shipment.get("carrier_id") or "")
        by_local_date: dict[str, int] | None = None
        if concentration:
            # The job's own current appointment is inside the grouped count, so it is subtracted
            # back out on its own date -- the same correction `simulate_policy_weights` makes, for
            # the same reason: a carrier must not be penalised for the booking being re-decided.
            own_date = (
                _to_local(job.current_start, tz_name).date().isoformat()
                if job.current_start is not None
                else ""
            )
            by_local_date = {}
            for (row_carrier, local_date), count in concentration.items():
                if row_carrier != carrier_id:
                    continue
                by_local_date[local_date] = max(
                    0, count - (1 if local_date == own_date else 0)
                )
        for candidate in scope.candidates:
            slot_id = str(candidate["slot_id"])
            probe = dict(candidate)
            if (
                probe.get("active_appointment_id") is not None
                and slot_id in movable_slot_ids
            ):
                probe["active_appointment_id"] = None
            job.candidates_considered += 1
            option, reason = evaluate_candidate_slot(
                shipment=job.shipment,
                facility=scope.facility,
                eta_dt=job.release,
                candidate=probe,
                checked_constraints=checked,
                facility_rules=scope.facility_rules,
                driver_window=job.driver_window,
                carrier_concentration_by_local_date=by_local_date,
            )
            if option is not None:
                job.options[slot_id] = option
            elif reason is not None and job.first_refusal is None:
                job.first_refusal = (reason.failure_code, reason.message)


# ---------------------------------------------------------------------------------------------
# The objective -- section 5.1, term for term
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Coefficients:
    """Section 5.1's coefficients, read from `constraints.json` and sign-inverted.

    *"Use the same coefficients with inverted sign -- the sequencer minimises exactly what Stage 2
    maximises."* Every value below is `abs()` of, or a direct read from, `score_weights`; none is a
    literal in this file. `priority_scores` supplies `w_j`.
    """

    wait_per_minute: int
    fallback_dock: int
    churn: int
    fairness: int
    priority_scores: dict[str, int]

    @classmethod
    def from_policy(cls) -> "Coefficients":
        policy = load_scheduling_constraints().ranking_policy
        weights = policy.score_weights
        return cls(
            # Stage 2: `wait_after_eta_per_minute: -6` -> section 5.1's `6·(start_j − r_j)`.
            wait_per_minute=abs(int(weights.get("wait_after_eta_per_minute", -6))),
            # Stage 2: `compatible_but_not_exact_dock_penalty: -25` -> section 5.1's `25·[...]`.
            fallback_dock=abs(int(weights.get("compatible_but_not_exact_dock_penalty", -25))),
            # Section 5.1 "Pricing churn": ~30 weighted-minute-equivalents per moved promise.
            # Read, never defaulted silently -- 30 appears here only as the design's own number for
            # a database that predates the key.
            churn=int(weights.get(WEIGHT_CHURN, 30)),
            # D7's term. Kept signed: the inversion happens in `placement_cost`, so the sign
            # convention lives in exactly one place.
            fairness=int(weights.get(WEIGHT_FAIRNESS, 0)),
            priority_scores=dict(policy.priority_scores or _DEFAULT_PRIORITY_SCORES),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "wait_per_minute": self.wait_per_minute,
            "fallback_dock": self.fallback_dock,
            WEIGHT_CHURN: self.churn,
            WEIGHT_FAIRNESS: self.fairness,
            "priority_scores": self.priority_scores,
            "churn_epsilon_minutes": CHURN_EPSILON_MINUTES,
        }


@dataclass
class Placement:
    """One job assigned to one candidate interval, with its cost decomposed."""

    job: Job
    option: FeasibleSlotOption
    slot_id: str
    dock_id: str
    dock_code: str
    start: datetime
    slot_end: datetime
    claim: tuple[datetime, datetime]

    lateness_cost: int = 0
    waiting_cost: int = 0
    fallback_dock_cost: int = 0
    churn_cost: int = 0
    fairness_cost: int = 0
    wait_minutes: int = 0
    lateness_minutes: int = 0
    is_churn: bool = False
    exact_dock: bool = True

    @property
    def total(self) -> int:
        return (
            self.lateness_cost
            + self.waiting_cost
            + self.fallback_dock_cost
            + self.churn_cost
            + self.fairness_cost
        )

    @property
    def moved(self) -> bool:
        return self.job.current_slot_id is not None and self.slot_id != self.job.current_slot_id


def placement_cost(job: Job, option: FeasibleSlotOption, coeff: Coefficients) -> Placement:
    """Section 5.1's objective for one placement. **The whole formula lives here and nowhere else.**

        w_j * max(0, start_j - d_j) + 6*(start_j - r_j) + 25*[not exact dock]
        + P_churn * [communicated and |start_j - promised_j| > 15 min]
        + (-w_fairness * carrier_concentration)                      # D7, issue #69

    Two of the five terms are **not recomputed**: `wait_after_eta_minutes` and `fairness_penalty`
    are lifted straight out of the `ranking_factors` receipt `feasibility._rank_slot` produced for
    this very candidate. That is what makes section 5.1's *"one currency with Stage 2"* an identity
    rather than a resemblance -- the sequencer's waiting cost is arithmetically Stage 2's waiting
    term with the sign flipped, computed by Stage 2's own code, and the same for fairness.

    `start_j` differs by term, deliberately (module docstring, note 1): lateness and churn measure
    the *promise*, so they use the slot start the driver is given; waiting measures the *person*, so
    it uses the unload start Stage 2 already computed as `wait_after_eta_minutes` off the release.

    The fairness inversion is literal: `ranking_factors['fairness_penalty']` is Stage 2's signed
    `w_fairness * concentration`, and this is its negation. With the expected-negative `w_fairness`
    that is a non-negative cost; at the shipped `0` it is exactly `0` and the four-term formula
    section 5.1 writes down is what runs.
    """
    factors = option.ranking_factors
    start = _parse_iso(option.slot_start_ts)
    slot_end = _parse_iso(option.slot_end_ts)

    lateness_minutes = 0
    if job.due is not None:
        lateness_minutes = max(0, _minutes(job.due, start))

    wait_minutes = int(factors.get("wait_after_eta_minutes", 0))
    exact_dock = str(factors.get("dock_match")) == "exact"

    is_churn = False
    if job.communicated and job.current_start is not None:
        is_churn = abs(_minutes(job.current_start, start)) > CHURN_EPSILON_MINUTES

    return Placement(
        job=job,
        option=option,
        slot_id=option.slot_id,
        dock_id=option.dock_id,
        dock_code=option.dock_code,
        start=start,
        slot_end=slot_end,
        claim=claim_window(start, job.unload_min),
        lateness_cost=job.weight * lateness_minutes,
        waiting_cost=coeff.wait_per_minute * wait_minutes,
        fallback_dock_cost=0 if exact_dock else coeff.fallback_dock,
        churn_cost=coeff.churn if is_churn else 0,
        fairness_cost=-int(factors.get("fairness_penalty", 0)),
        wait_minutes=wait_minutes,
        lateness_minutes=lateness_minutes,
        is_churn=is_churn,
        exact_dock=exact_dock,
    )


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------------------------
# The search -- section 5.1's five algorithm steps
# ---------------------------------------------------------------------------------------------


def _job_order(jobs: list[Job]) -> list[Job]:
    """Section 5.1 step 2: *"Order jobs by Stage-2 score, descending."*

    A job's Stage-2 score is a property of a (job, slot) pair, so the job's score is taken as its
    **best** candidate's -- the score it would achieve if it got its first choice. Deterministic
    tie-break on `shipment_id`, which is section 5.1 step 5's own rule and Stage 2's
    (`stable_tiebreaker`, `shipment_id + slot_id`). Zero randomness, NFR-007.
    """
    def key(job: Job) -> tuple[int, str]:
        best = max((option.rank_score for option in job.options.values()), default=-(10**9))
        return (-best, job.shipment_id)

    return sorted(jobs, key=key)


def _feasible_placements(
    job: Job, coeff: Coefficients, taken: dict[str, list[tuple[datetime, datetime]]]
) -> list[Placement]:
    """Every placement this job could take right now, cheapest first.

    Section 5.1 step 3: *"place each job at the earliest feasible start on the eligible dock with
    the lowest marginal cost."* Ordered by `(cost, start, dock_id, slot_id)` -- cost decides, and
    "earliest" is the tie-break, which is the only reading under which both halves of that sentence
    can hold at once.

    `taken` carries both the immovable world (`Scope.blocked`) and the placements this pass has
    already made, which is what keeps the proposal internally non-overlapping. The interval tested
    is the **claim** window, not the slot window -- see `claim_window`.
    """
    out: list[Placement] = []
    for option in job.options.values():
        placement = placement_cost(job, option, coeff)
        if any(_overlaps(placement.claim, busy) for busy in taken.get(placement.dock_id, ())):
            continue
        out.append(placement)
    out.sort(key=lambda p: (p.total, p.start, p.dock_id, p.slot_id))
    return out


def _search(scope: Scope, coeff: Coefficients) -> dict[str, Placement]:
    """Section 5.1's algorithm, steps 1-5. Returns `{shipment_id: Placement}`.

    1. **Freeze fixed tasks and downtime windows** -- already done: `Scope.blocked` carries live
       claims the run may not touch, and `_load_candidates`' dock-event join removed slots on a
       dock that is out.
    2. **Order jobs by Stage-2 score, descending** -- `_job_order`.
    3. **Greedy insertion** -- each job takes its lowest-marginal-cost feasible placement.
    4. **Local improvement** -- single-job reinsertion, then pairwise swaps, *"accepted only when
       the total cost improves by more than the churn any move incurs."* Churn is a term of the cost
       function, so a strict improvement in the total **is** that condition, priced rather than
       estimated. Each pass runs once, in id order: bounded, deterministic, and enough at a scope
       section 0's arithmetic caps near 30 trucks.
    5. **Deterministic tie-break on `(shipment_id, dock_id)`** -- in `_job_order` and in
       `_feasible_placements`' sort key. NFR-007: the same snapshot and policy version produce a
       byte-identical proposal, which `tests/proof/test_part12_sequencer.py` asserts by running the
       whole search twice.

    This function is section 5.1's stated CP-SAT seam: *"The CP-SAT upgrade is a drop-in because
    search is separated from objective."* Everything above it works on `Placement` objects and
    knows nothing about how they were chosen.
    """
    taken: dict[str, list[tuple[datetime, datetime]]] = {
        dock_id: list(intervals) for dock_id, intervals in scope.blocked.items()
    }
    # Step 1, second half: every claim that exists right now is occupied until this run decides
    # otherwise -- including the claims of jobs it is allowed to move. A movable claim is lifted
    # only while its own job is being placed (below), and a job the search cannot place therefore
    # keeps it. See `Job.current_claim` for the defect this shape fixes.
    for job in scope.jobs:
        if job.current_claim is not None and job.current_claim_dock is not None:
            taken.setdefault(job.current_claim_dock, []).append(job.current_claim)

    placements: dict[str, Placement] = {}

    # --- step 3: greedy insertion ------------------------------------------------------------
    for job in _job_order([j for j in scope.jobs if not j.pinned]):
        free = _lift_own_claim(taken, job)
        options = _feasible_placements(job, coeff, free)
        if not options:
            # Unplaceable. `taken` is left untouched, so this job's own claim (if it has one) goes
            # on blocking every later job -- which is the truth, because nothing will release it.
            continue
        chosen = options[0]
        placements[job.shipment_id] = chosen
        taken = free
        taken.setdefault(chosen.dock_id, []).append(chosen.claim)

    # --- step 4a: single-job reinsertion ------------------------------------------------------
    for shipment_id in sorted(placements):
        current = placements[shipment_id]
        without = _taken_without(taken, current)
        alternatives = _feasible_placements(current.job, coeff, without)
        if alternatives and alternatives[0].total < current.total:
            placements[shipment_id] = alternatives[0]
            taken = without
            taken.setdefault(alternatives[0].dock_id, []).append(alternatives[0].claim)

    # --- step 4b: pairwise swaps --------------------------------------------------------------
    ids = sorted(placements)
    for i, left_id in enumerate(ids):
        for right_id in ids[i + 1:]:
            left, right = placements.get(left_id), placements.get(right_id)
            if left is None or right is None:
                continue
            swapped = _try_swap(left, right, coeff, taken)
            if swapped is None:
                continue
            new_left, new_right, new_taken = swapped
            placements[left_id], placements[right_id] = new_left, new_right
            taken = new_taken

    return placements


def _lift_own_claim(
    taken: dict[str, list[tuple[datetime, datetime]]], job: Job
) -> dict[str, list[tuple[datetime, datetime]]]:
    """A copy of the occupied map with this job's *existing* claim removed.

    "Movable" means the run may release this interval when it applies -- so while deciding where
    this job goes, its own claim must not block it (moving 11:00 to 11:30 on the same dock overlaps
    itself, the hazard `counter_offer` and `reschedule_appointment` both document). It is removed
    from a **copy**, so that if the job turns out to be unplaceable the caller's map still carries
    the claim nothing is going to release.
    """
    if job.current_claim is None or job.current_claim_dock is None:
        return {dock_id: list(intervals) for dock_id, intervals in taken.items()}
    copy = {dock_id: list(intervals) for dock_id, intervals in taken.items()}
    intervals = copy.get(job.current_claim_dock)
    if intervals and job.current_claim in intervals:
        intervals.remove(job.current_claim)
    return copy


def _taken_without(
    taken: dict[str, list[tuple[datetime, datetime]]], placement: Placement
) -> dict[str, list[tuple[datetime, datetime]]]:
    """A copy of the occupied map with one placement's own claim lifted out.

    Removing exactly one occurrence, not every equal interval: two docks can legitimately carry the
    same window, and `list.remove` on the dock's own list is the narrowest correct operation.
    """
    copy = {dock_id: list(intervals) for dock_id, intervals in taken.items()}
    intervals = copy.get(placement.dock_id)
    if intervals and placement.claim in intervals:
        intervals.remove(placement.claim)
    return copy


def _try_swap(
    left: Placement, right: Placement, coeff: Coefficients, taken: dict[str, list[tuple[datetime, datetime]]]
) -> tuple[Placement, Placement, dict[str, list[tuple[datetime, datetime]]]] | None:
    """Section 5.1 step 4's pairwise swap: does exchanging two jobs' intervals cost less?

    Both must be feasible in the other's slot -- Stage 1 already answered that when
    `_evaluate_jobs` filled `job.options`, so a missing key is a real eligibility refusal (a reefer
    load cannot take a standard dock) and not a lookup failure. Both claim windows are recomputed,
    because two jobs with different `expected_unload_min` occupy different amounts of the same
    slot, and the overlap check is run against the map with **both** original claims lifted out.

    Accepted only on a strict improvement of the pair's total, which -- because churn is a term --
    is section 5.1's *"improves by more than the churn any move incurs"*.
    """
    left_option = left.job.options.get(right.slot_id)
    right_option = right.job.options.get(left.slot_id)
    if left_option is None or right_option is None:
        return None

    new_left = placement_cost(left.job, left_option, coeff)
    new_right = placement_cost(right.job, right_option, coeff)
    if new_left.total + new_right.total >= left.total + right.total:
        return None

    free = _taken_without(_taken_without(taken, left), right)
    for candidate in (new_left, new_right):
        if any(_overlaps(candidate.claim, busy) for busy in free.get(candidate.dock_id, ())):
            return None
    if _overlaps(new_left.claim, new_right.claim) and new_left.dock_id == new_right.dock_id:
        return None

    free.setdefault(new_left.dock_id, []).append(new_left.claim)
    free.setdefault(new_right.dock_id, []).append(new_right.claim)
    return new_left, new_right, free


# ---------------------------------------------------------------------------------------------
# Diff and objective assembly
# ---------------------------------------------------------------------------------------------


def _placement_view(placement: Placement) -> PlacementView:
    job = placement.job
    delta = (
        _minutes(job.current_start, placement.start) if job.current_start is not None else None
    )
    return PlacementView(
        shipment_id=job.shipment_id,
        appointment_id=job.appointment_id,
        order_reference=job.shipment.get("order_reference"),
        priority_code=str(job.shipment.get("priority_code") or "NORMAL"),
        carrier_id=job.shipment.get("carrier_id"),
        dock_id=placement.dock_id,
        dock_code=placement.dock_code,
        slot_id=placement.slot_id,
        start_ts=placement.start.isoformat(),
        end_ts=placement.slot_end.isoformat(),
        claim_start_ts=placement.claim[0].isoformat(),
        claim_end_ts=placement.claim[1].isoformat(),
        previous_slot_id=job.current_slot_id,
        previous_dock_id=job.current_dock_id,
        previous_dock_code=job.current_dock_code,
        previous_start_ts=job.current_start.isoformat() if job.current_start else None,
        delta_minutes=delta,
        communicated=job.communicated,
        is_churn=placement.is_churn,
        pinned=job.pinned,
        release_ts=job.release.isoformat(),
        release_source=job.release_source,
        wait_minutes=placement.wait_minutes,
        lateness_minutes=placement.lateness_minutes,
        exact_dock_match=placement.exact_dock,
        cost=placement.total,
    )


def _pinned_view(job: Job) -> PlacementView:
    """A fixed task's row in the `unchanged` bucket.

    Section 5.1 pins in-progress unloads rather than excluding them, and the diff has to show them
    or a planner reading "Unchanged 9" would be reading a number that silently omits the trucks
    currently on the docks.
    """
    start = job.current_start or job.release
    return PlacementView(
        shipment_id=job.shipment_id,
        appointment_id=job.appointment_id,
        order_reference=job.shipment.get("order_reference"),
        priority_code=str(job.shipment.get("priority_code") or "NORMAL"),
        carrier_id=job.shipment.get("carrier_id"),
        dock_id=str(job.current_dock_id or ""),
        dock_code=str(job.current_dock_code or ""),
        slot_id=str(job.current_slot_id or ""),
        start_ts=start.isoformat(),
        end_ts=claim_window(start, job.unload_min)[1].isoformat(),
        claim_start_ts=start.isoformat(),
        claim_end_ts=claim_window(start, job.unload_min)[1].isoformat(),
        previous_slot_id=job.current_slot_id,
        previous_dock_id=job.current_dock_id,
        previous_dock_code=job.current_dock_code,
        previous_start_ts=job.current_start.isoformat() if job.current_start else None,
        delta_minutes=0,
        communicated=job.communicated,
        is_churn=False,
        pinned=True,
        release_ts=job.release.isoformat(),
        release_source=job.release_source,
    )


def build_diff(scope: Scope, placements: dict[str, Placement]) -> ProposalDiff:
    """Section 5.1's four buckets, from the job set and the search's output.

    A job with an existing appointment and the same slot is `unchanged`; a different slot is
    `moved`; no prior appointment is `newly placed`; no feasible placement at all is `unplaceable`.
    Pinned jobs are `unchanged` by construction (a fixed task was never a decision).
    """
    diff = ProposalDiff()
    for job in sorted(scope.jobs, key=lambda j: j.shipment_id):
        if job.pinned:
            diff.unchanged.append(_pinned_view(job))
            continue
        placement = placements.get(job.shipment_id)
        if placement is None:
            code, message = job.first_refusal or (
                "NO_CANDIDATE_SLOTS",
                "No candidate interval exists on any eligible dock inside the horizon.",
            )
            diff.unplaceable.append(
                UnplaceableView(
                    shipment_id=job.shipment_id,
                    order_reference=job.shipment.get("order_reference"),
                    priority_code=str(job.shipment.get("priority_code") or "NORMAL"),
                    release_ts=job.release.isoformat(),
                    release_source=job.release_source,
                    failure_code=code,
                    message=message,
                    candidates_considered=job.candidates_considered,
                )
            )
            continue
        view = _placement_view(placement)
        if job.current_slot_id is None:
            diff.newly_placed.append(view)
        elif placement.moved:
            diff.moved.append(view)
        else:
            diff.unchanged.append(view)
    return diff


def build_objective(
    placements: dict[str, Placement], diff: ProposalDiff, coeff: Coefficients
) -> ObjectiveValues:
    """Sum section 5.1's objective over the proposal, and compute its headline effect line.

    `waiting_minutes_delta` is section 5.1's own *"Effect: total driver waiting -85 min"*: the
    proposal's total waiting against what the **current** schedule produces for the same jobs.
    Computed only over jobs the proposal places AND that already had a promise, because a newly
    placed job has no current waiting to compare against and folding it in would report an
    improvement that is really just new work being scheduled.

    There is no `overtime` figure, and its absence is deliberate rather than missing: section 5.1
    lists `LAST_NEW_START_TIME` (RULE005) as a **hard** constraint, enforced by Stage 1 through
    `check_facility_rules`, so a proposal containing overtime is unrepresentable. Reporting a
    metric that is structurally always zero would be theatre.
    """
    policy = load_scheduling_constraints()
    objective = ObjectiveValues(
        policy_version=policy.policy_version, coefficients=coeff.as_dict()
    )
    current_waiting = 0
    proposed_waiting = 0
    for placement in placements.values():
        objective.lateness_cost += placement.lateness_cost
        objective.waiting_cost += placement.waiting_cost
        objective.fallback_dock_cost += placement.fallback_dock_cost
        objective.churn_cost += placement.churn_cost
        objective.fairness_cost += placement.fairness_cost
        objective.waiting_minutes_total += placement.wait_minutes
        if placement.is_churn:
            objective.churn_count += 1
        if placement.moved:
            objective.promises_moved += 1
            job = placement.job
            if job.current_start is not None:
                current_waiting += max(0, _minutes(job.release, job.current_start))
                proposed_waiting += placement.wait_minutes

    objective.total_cost = (
        objective.lateness_cost
        + objective.waiting_cost
        + objective.fallback_dock_cost
        + objective.churn_cost
        + objective.fairness_cost
    )
    objective.placements = len(placements)
    counts = diff.counts
    objective.unchanged_count = counts["unchanged"]
    objective.newly_placed_count = counts["newly_placed"]
    objective.unplaceable_count = counts["unplaceable"]
    objective.waiting_minutes_delta = proposed_waiting - current_waiting
    return objective


def build_explanation(scope: Scope, diff: ProposalDiff, objective: ObjectiveValues) -> str:
    """Section 5.1's own rendering of a proposal, as one line.

    The design writes it as: *"Unchanged 9 · Moved 2 · Newly placed 3 · Unplaceable 1 ... Effect:
    total driver waiting -85 min · promises moved 1 · overtime 0."* Templated, never generated --
    `UI-UX/00-foundations/voice-and-tone.md`:8, *"Sentences that declare operational state are
    templated."* -- and stored on the run so `get_scheduling_run` replays the same sentence a month
    later rather than re-deriving it from numbers that may since have been re-interpreted.
    """
    counts = diff.counts
    delta = objective.waiting_minutes_delta
    sign = "+" if delta > 0 else ""
    return (
        f"{scope.facility.get('facility_name') or scope.facility['facility_id']} · horizon "
        f"{_to_local(scope.horizon_start, str(scope.facility['timezone'])):%H:%M}-"
        f"{_to_local(scope.horizon_end, str(scope.facility['timezone'])):%H:%M} · "
        f"Unchanged {counts['unchanged']} · Moved {counts['moved']} · "
        f"Newly placed {counts['newly_placed']} · Unplaceable {counts['unplaceable']}. "
        f"Effect: total driver waiting {sign}{delta} min · "
        f"promises moved {objective.promises_moved} · "
        f"communicated promises moved {objective.churn_count}."
    )


def build_input_snapshot(scope: Scope) -> dict[str, Any]:
    """Section 5 Stage 4's "input snapshot" -- the job set and its section 5.1 parameters.

    Every column of section 5.1's job table is here (release and its source, processing time,
    eligible dock count, due date, weight, fixed-task flag), plus the candidate and blocked-interval
    counts the search actually saw. That is what makes the run *replayable* in the sense section
    7.5.3 asks for: a reviewer a month later can see not only what was proposed but what the
    proposal was allowed to choose from.
    """
    return {
        "facility_id": scope.facility["facility_id"],
        "timezone": scope.facility.get("timezone"),
        "horizon_start": scope.horizon_start.isoformat(),
        "horizon_end": scope.horizon_end.isoformat(),
        "horizon_end_reason": scope.horizon_end_reason,
        "candidate_slots": len(scope.candidates),
        "blocked_dock_intervals": sum(len(v) for v in scope.blocked.values()),
        "facility_rules": [rule.get("rule_id") for rule in scope.facility_rules],
        "job_set_truncated": scope.truncated_jobs,
        "jobs": [
            {
                "shipment_id": job.shipment_id,
                "appointment_id": job.appointment_id,
                "appointment_status": job.appointment_status,
                "priority_code": job.shipment.get("priority_code"),
                "carrier_id": job.shipment.get("carrier_id"),
                "release_ts": job.release.isoformat(),
                "release_source": job.release_source,
                "processing_minutes": job.unload_min + CHANGEOVER_BUFFER_MINUTES,
                "due_ts": job.due.isoformat() if job.due else None,
                "weight": job.weight,
                "eligible_slots": len(job.options),
                "pinned": job.pinned,
                "communicated": job.communicated,
            }
            for job in sorted(scope.jobs, key=lambda j: j.shipment_id)
        ],
    }


# ---------------------------------------------------------------------------------------------
# The snapshot guard
# ---------------------------------------------------------------------------------------------


async def compute_run_snapshot_hash(
    session: AsyncSession, scope: Scope, *, actor_user_id: str
) -> tuple[str, dict[str, str]]:
    """Section 5.1: *"the proposal carries a `snapshot_hash`; on apply, revalidate and re-run on
    drift. Same staleness discipline as section 7.1 -- one mechanism, used consistently."*

    **One mechanism, literally.** The per-row digests come from
    `snapshot.load_appointment_snapshots` -- the same function `confirm_request`, `counter_offer`
    and `bulk_confirm` recompute under their row locks -- and they are composed by
    `snapshot.batch_snapshot_hash`, the composer `bulk_confirm` already uses for its multi-row
    token. Nothing about the digest is invented here; this function only decides *which rows* are
    in the set.

    A job with **no** active appointment is keyed `shipment:<id>` with a constant marker, and that
    is load-bearing rather than filler: it makes the job set's own membership part of the digest,
    so a shipment gaining an appointment (someone booked it while the planner was reviewing) or
    losing one is itself drift. Without it, the newly-placed half of a proposal could be applied
    against a facility where those shipments had already been placed by hand.

    The `shipment:` prefix cannot collide with an appointment id: `services/ids.py` mints those as
    `APT-<hex>`, and the seeded ones are `APT####`.

    What the digest deliberately does **not** cover, and why that is not a hole: an ETA that moves
    without changing job-set membership, and a dock going out of service. Both are caught by the
    apply's Stage-1 revalidation as `PARTIALLY_INFEASIBLE` instead -- and dock blocks are excluded
    from `snapshot_hash` by `snapshot.py`'s own deliberate design, because a block that changed
    every digest in the facility would mass-refuse in-flight confirms with `SNAPSHOT_STALE` and turn
    a targeted refusal into a facility-wide one. Capacity membership is the digest's job;
    feasibility is the revalidation's.
    """
    appointment_ids = [
        str(job.appointment_id) for job in scope.jobs if job.appointment_id is not None
    ]
    snapshots = await load_appointment_snapshots(
        session, appointment_ids, actor_user_id=actor_user_id
    )
    row_hashes: dict[str, str] = {
        appointment_id: snapshot["snapshot_hash"]
        for appointment_id, snapshot in snapshots.items()
    }
    for job in scope.jobs:
        if job.appointment_id is None:
            row_hashes[f"shipment:{job.shipment_id}"] = "NO_ACTIVE_APPOINTMENT"
    return batch_snapshot_hash(row_hashes), row_hashes


# ---------------------------------------------------------------------------------------------
# section 7.5.3 -- propose_facility_schedule
# ---------------------------------------------------------------------------------------------


async def propose_facility_schedule(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    facility_id: str | None = None,
    horizon_end: datetime | None = None,
    trigger_reason: str = TRIGGER_PLANNER_REQUESTED,
    escalation_id: str | None = None,
    now: datetime | None = None,
) -> SchedulingRunResult:
    """Section 7.5.3's `propose_facility_schedule`.

    Returns a `scheduling_run_id`, the section 5.1 diff, objective values and a `snapshot_hash`, or
    refuses with `RUN_ALREADY_ACTIVE` -- *"one run per facility, serialised -- section 5.1's
    debounce rule expressed as a return value."*

    **Scope is derived, never argued (M15 / section 7.5 principle 1).** `facility_id` goes through
    `resolve_facility_scope_with_user_scopes`, so it can only ever *narrow* a global-read persona's
    view or name a facility the server itself grants this user (their `users.facility_id` mirror or
    a `user_scopes` FACILITY row -- issue #106). A planner cannot re-sequence a facility they do not
    hold, however the request was shaped. `require_facility=True` because a proposal is
    per-facility by section 5.1's own run scope; there is no "all facilities" run.

    **This writes nothing but the run.** No `dock_occupancy` row, no `appointments` row, no
    notification -- D5: *"No automatic re-promising. Sequencer output is a reviewable artifact,
    never a silent write."* The only side effects are the lazy supersede of expired proposals (see
    `runs_repo.supersede_expired_runs`) and, when the D2 flag is on, the lapsed-hold expiry
    `load_appointment_snapshots` performs for its own correctness (issue #98).
    """
    if trigger_reason not in TRIGGER_REASONS:
        raise AppError(
            f"Unsupported trigger_reason '{trigger_reason}'.",
            code="INVALID_TRIGGER_REASON",
            status_code=422,
            detail=f"Supported: {', '.join(sorted(TRIGGER_REASONS))}.",
        )
    scope_facility = await resolve_facility_scope_with_user_scopes(
        session, ctx, facility_id, require_facility=True
    )
    if scope_facility is None:  # pragma: no cover - require_facility=True guarantees this
        raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
    # A proposal is a decision about a facility's capacity, so it takes the WRITE tier rather than
    # the read one: `has_global_read_scope` personas (TRANSPORT_MANAGER, REGIONAL_OPERATIONS_HEAD)
    # can see every facility and must not be able to queue work for one. Same split
    # `repositories/scope.py`'s own docstring insists on ("Do not merge them").
    assert_facility_write_scope(ctx, scope_facility)

    moment = now or datetime.now(timezone.utc)

    # Retire proposals whose horizon has passed BEFORE trying to insert -- otherwise a dead run
    # holds the facility's one active slot forever. See `supersede_expired_runs` for why a partial
    # index cannot do this itself.
    await runs_repo.supersede_expired_runs(session, facility_id=scope_facility, now=moment)

    scope = await build_scope(
        session, facility_id=scope_facility, now=moment, requested_end=horizon_end
    )
    coeff = Coefficients.from_policy()
    placements = _search(scope, coeff)
    diff = build_diff(scope, placements)
    objective = build_objective(placements, diff, coeff)
    explanation = build_explanation(scope, diff, objective)
    snapshot_hash, _ = await compute_run_snapshot_hash(session, scope, actor_user_id=ctx.user_id)

    run_id = new_id("SR")
    stored = await runs_repo.insert_proposed_run(
        session,
        scheduling_run_id=run_id,
        facility_id=scope_facility,
        trigger_reason=trigger_reason,
        requested_by_user_id=ctx.user_id,
        escalation_id=escalation_id,
        horizon_start=scope.horizon_start,
        horizon_end=scope.horizon_end,
        horizon_end_reason=scope.horizon_end_reason,
        policy_version=objective.policy_version,
        snapshot_hash=snapshot_hash,
        input_snapshot=build_input_snapshot(scope),
        proposal=json.loads(diff.model_dump_json()),
        objective=json.loads(objective.model_dump_json()),
        explanation=explanation,
    )
    if stored is None:
        # The database refused, which is section 7.5.3's `RUN_ALREADY_ACTIVE`. Read the incumbent
        # so the refusal can name it -- a typed outcome that does not say *which* run is in the way
        # would send the planner hunting.
        active = await runs_repo.active_run_for_facility(session, facility_id=scope_facility)
        await session.commit()
        return SchedulingRunResult(
            as_of=_as_of(),
            code="RUN_ALREADY_ACTIVE",
            scheduling_run_id=str(active["scheduling_run_id"]) if active else "",
            facility_id=scope_facility,
            facility_name=scope.facility.get("facility_name"),
            trigger_reason=trigger_reason,
            escalation_id=escalation_id,
            status=STATUS_PROPOSED,
            policy_version=objective.policy_version,
            snapshot_hash=str(active["snapshot_hash"]) if active else "",
            horizon=HorizonView(
                start_ts=scope.horizon_start.isoformat(),
                end_ts=scope.horizon_end.isoformat(),
                end_reason=scope.horizon_end_reason,
            ),
            counts={},
            diff=ProposalDiff(),
            objective=ObjectiveValues(policy_version=objective.policy_version),
            explanation=(
                "This facility already has a proposal awaiting a planner. Review or apply it "
                "before requesting another (SOLUTION_DESIGN.md section 5.1: at most one active "
                "run per facility)."
            ),
            active_run=_run_summary(active) if active else None,
        )

    await session.commit()
    return _result_from_run(stored, diff=diff, objective=objective, facility=scope.facility)


def _run_summary(run: dict[str, Any]) -> dict[str, Any]:
    """The few fields a `RUN_ALREADY_ACTIVE` refusal needs about the incumbent."""
    return {
        "scheduling_run_id": str(run["scheduling_run_id"]),
        "status": str(run["status"]),
        "trigger_reason": str(run["trigger_reason"]),
        "escalation_id": run.get("escalation_id"),
        "snapshot_hash": str(run["snapshot_hash"]),
        "created_at": _iso(run.get("created_at")),
        "horizon_end": _iso(run.get("horizon_end")),
        "counts": (run.get("proposal_json") or {}).get("counts") or _counts_of(run),
    }


def _counts_of(run: dict[str, Any]) -> dict[str, int]:
    proposal = run.get("proposal_json") or {}
    return {
        bucket: len(proposal.get(bucket) or [])
        for bucket in ("unchanged", "moved", "newly_placed", "unplaceable")
    }


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _result_from_run(
    run: dict[str, Any],
    *,
    diff: ProposalDiff | None = None,
    objective: ObjectiveValues | None = None,
    facility: dict[str, Any] | None = None,
) -> SchedulingRunResult:
    """One stored row -> the response shape. Used by propose (fresh objects) and by
    `get_scheduling_run` (rehydrated from jsonb), which is what makes the two byte-identical."""
    proposal = run.get("proposal_json") or {}
    resolved_diff = diff if diff is not None else ProposalDiff.model_validate(proposal)
    resolved_objective = (
        objective
        if objective is not None
        else ObjectiveValues.model_validate(run.get("objective_json") or {"policy_version": ""})
    )
    return SchedulingRunResult(
        as_of=_as_of(),
        code=str(run["status"]),
        scheduling_run_id=str(run["scheduling_run_id"]),
        facility_id=str(run["facility_id"]),
        facility_name=(facility or {}).get("facility_name"),
        trigger_reason=str(run["trigger_reason"]),
        escalation_id=run.get("escalation_id"),
        status=str(run["status"]),
        policy_version=str(run["policy_version"]),
        snapshot_hash=str(run["snapshot_hash"]),
        horizon=HorizonView(
            start_ts=str(_iso(run["horizon_start"])),
            end_ts=str(_iso(run["horizon_end"])),
            end_reason=str(run["horizon_end_reason"]),
        ),
        counts=resolved_diff.counts,
        diff=resolved_diff,
        objective=resolved_objective,
        explanation=str(run["explanation"]),
        requested_by_user_id=run.get("requested_by_user_id"),
        created_at=_iso(run.get("created_at")),
        applied_at=_iso(run.get("applied_at")),
        applied_by_user_id=run.get("applied_by_user_id"),
        notifications_enqueued=run.get("notifications_enqueued"),
        superseded_at=_iso(run.get("superseded_at")),
        superseded_reason=run.get("superseded_reason"),
        input_snapshot=run.get("input_snapshot_json") or {},
    )


# ---------------------------------------------------------------------------------------------
# section 7.5.3 -- get_scheduling_run
# ---------------------------------------------------------------------------------------------


async def get_scheduling_run(
    session: AsyncSession, ctx: ExecutionContext, scheduling_run_id: str
) -> SchedulingRunResult:
    """Section 7.5.3's `get_scheduling_run`: *"The stored run: input snapshot, proposal, objective
    values, explanation -- replayable a month later, which is what makes section 8's 'how the
    business can trust the allocation' answerable."*

    A **read**, so it takes the read tier: section 7.5.3's own note says *"The agent may read a
    proposal to explain it; it may never apply one"*, and a global-read persona
    (REGIONAL_OPERATIONS_HEAD) auditing a facility's decisions is exactly what that tier is for.
    Scope is derived from the run's own `facility_id` -- the caller supplies a run id, never a
    facility -- so there is no argument here by which a caller could widen what they can see (M15).
    """
    run = await runs_repo.get_run(session, scheduling_run_id=scheduling_run_id)
    if run is None:
        raise AppError(
            f"Scheduling run '{scheduling_run_id}' not found.", code="NOT_FOUND", status_code=404
        )
    assert_facility_visible(ctx, str(run["facility_id"]))
    facility_name = await session.scalar(
        text("SELECT facility_name FROM public.facilities WHERE facility_id = :fid"),
        {"fid": run["facility_id"]},
    )
    return _result_from_run(run, facility={"facility_name": facility_name})


class SchedulingRunSummary(BaseModel):
    """One row of the pending-proposals list -- enough to render a count and open the right run.

    Deliberately **not** the whole proposal: `03-planner-dock-board/screens.md` section 3 needs a
    number on a button and the identity behind it, and shipping every run's full diff to build a
    badge would move kilobytes to render one integer.
    """

    model_config = ConfigDict(extra="forbid")

    scheduling_run_id: str
    facility_id: str
    status: str
    trigger_reason: str
    escalation_id: str | None = None
    policy_version: str
    snapshot_hash: str
    horizon: HorizonView
    counts: dict[str, int]
    explanation: str
    requested_by_user_id: str | None = None
    created_at: str | None = None
    applied_at: str | None = None
    superseded_reason: str | None = None
    #: The two figures section 5.1's headline puts in front of a planner, lifted out of
    #: `objective_json` so the list can be sorted or badged without parsing the whole objective.
    promises_moved: int = 0
    churn_count: int = 0


class SchedulingRunList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    facility_id: str | None = None
    status: str | None = None
    count: int = 0
    runs: list[SchedulingRunSummary] = Field(default_factory=list)


#: Bound on the list read. A facility produces single figures of runs per day (every one is a human
#: pressing a button), so this is a guard against a runaway query rather than a paging scheme --
#: `bulk_confirm`'s `MAX_BULK_CONFIRM_IDS` is sized the same way and for the same reason.
MAX_RUN_LIST = 50


async def list_scheduling_runs(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    facility_id: str | None = None,
    status: str | None = STATUS_PROPOSED,
    limit: int = MAX_RUN_LIST,
) -> SchedulingRunList:
    """Pending (or recent) proposals for a facility.

    **A deliberate addition to section 7.5.3's catalog, flagged rather than folded in** -- the same
    discipline `planner_service.get_dock_block_impact` and `admin_governance_service.
    get_active_policy_version` each state for themselves. Section 7.5.3 defines three tools and none
    of them is a list, but two shipped surfaces require one and neither can be built from
    `get_scheduling_run` alone, because both start without knowing a run id:

    * `03-planner-dock-board/screens.md` section 3's `[ Review proposal (N) ]` control needs **N**
      for this facility, and `flows-and-states.md` Flow 9 says that button "goes from
      Inactive-with-`(0)` to active the moment either origin produces a `scheduling_run_id`";
    * Flow 9's **ops-handoff** origin is the sharper case: the run is created on the ops console by
      `request_sequencer_proposal`, so the planner surface never saw its id and has no way to learn
      it except by asking.

    Section 8's "how the business can trust the allocation" wants the same read pointed at history
    rather than at the live set, which is why `status` is a filter and not a hardcoded `PROPOSED`.

    **Scope is derived, never argued (M15).** `facility_id` goes through
    `resolve_facility_scope_with_user_scopes`, so it can only narrow a global-read persona's view or
    name a facility the server itself grants this caller. `require_facility=False`, deliberately: an
    `ADMIN` or `REGIONAL_OPERATIONS_HEAD` legitimately asks "is any facility waiting on a planner",
    and that is a read their tier already permits -- unlike `propose`, which is a write-tier
    decision about one building.
    """
    scope_facility = await resolve_facility_scope_with_user_scopes(session, ctx, facility_id)
    rows = await runs_repo.list_runs(
        session,
        facility_id=scope_facility,
        status=status,
        limit=max(1, min(limit, MAX_RUN_LIST)),
    )
    runs = [
        SchedulingRunSummary(
            scheduling_run_id=str(row["scheduling_run_id"]),
            facility_id=str(row["facility_id"]),
            status=str(row["status"]),
            trigger_reason=str(row["trigger_reason"]),
            escalation_id=row.get("escalation_id"),
            policy_version=str(row["policy_version"]),
            snapshot_hash=str(row["snapshot_hash"]),
            horizon=HorizonView(
                start_ts=str(_iso(row["horizon_start"])),
                end_ts=str(_iso(row["horizon_end"])),
                end_reason=str(row["horizon_end_reason"]),
            ),
            counts=_counts_of(row),
            explanation=str(row["explanation"]),
            requested_by_user_id=row.get("requested_by_user_id"),
            created_at=_iso(row.get("created_at")),
            applied_at=_iso(row.get("applied_at")),
            superseded_reason=row.get("superseded_reason"),
            promises_moved=int((row.get("objective_json") or {}).get("promises_moved") or 0),
            churn_count=int((row.get("objective_json") or {}).get("churn_count") or 0),
        )
        for row in rows
    ]
    return SchedulingRunList(
        as_of=_as_of(),
        facility_id=scope_facility,
        status=status,
        count=len(runs),
        runs=runs,
    )


# ---------------------------------------------------------------------------------------------
# section 7.5.3 -- apply_schedule_proposal
# ---------------------------------------------------------------------------------------------


async def apply_schedule_proposal(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    scheduling_run_id: str,
    snapshot_hash: str,
    idempotency_key: str,
    now: datetime | None = None,
) -> ApplyResult:
    """Section 7.5.3's `apply_schedule_proposal`. One transaction, all-or-nothing.

    Outcomes, verbatim from the catalog: `APPLIED` (+ notification batch id) · `SNAPSHOT_DRIFT` ->
    re-run required · `PARTIALLY_INFEASIBLE` -> refuses entirely. *"There is deliberately no 'apply
    these three rows' argument -- cherry-picking produces a schedule nobody validated."* This
    function's signature is that sentence: there is no per-row argument to pass.

    ## The order of operations, and why each step is where it is

    1. **Idempotency lookup.** Section 7.5 principle 3. A retried apply returns the first apply's
       answer rather than re-running a schedule.
    2. **Lock the run `FOR UPDATE`**, then check its status. Two planners pressing Apply is the
       `confirm_request`-versus-sweeper race in a new place, and gets the same resolution: exactly
       one commits, the loser is told `ALREADY_APPLIED` rather than silently double-applying.
    3. **Rebuild the scope over the run's STORED horizon** and recompute the digest. Frozen window,
       so drift means the capacity moved and not that time passed.
    4. **Compare digests.** Mismatch -> `SNAPSHOT_DRIFT`, zero capacity writes, and the dead run is
       marked `SUPERSEDED` so the planner can request the fresh proposal Flow 9 step 4 tells them
       to.
    5. **Release every moved appointment's claim first, then revalidate, then re-claim.** Releasing
       first is not an optimisation: `reschedule_appointment` and `counter_offer` both document the
       hazard -- moving 11:00 to 11:30 on the same dock overlaps *itself*, so a proposal that held
       its old claims while validating its new ones would be refused by D1's exclusion constraint
       for conflicts it is itself about to remove. Doing it for the whole run at once is the same
       argument at facility scale: job A's new slot is frequently job B's old one.
    6. **Revalidate through Stage 1 with the same release semantics the proposal used.** Not
       through `explain_slot_eligibility`, deliberately -- that function keys on
       `v_latest_eta.effective_eta_ts`, so for an arrived truck it would evaluate a different
       `feasible_start` than the proposal did and could refuse a placement the proposal made on
       gate-in truth. That is precisely the two-definitions-of-one-predicate defect issues #84/#97
       are about, and the cost of avoiding it is one shared `build_scope` rather than N x 3 round
       trips.
    7. **Write through the real primitives.** `allocation._release_dock_occupancy` and
       `allocation._claim_dock_occupancy` -- the same pair `counter_offer` uses, so D1's exclusion
       constraint remains the single authority on who gets an interval and the audit trail records
       the window PostgreSQL actually accepted.
    8. **Enqueue notifications inside the same transaction.** Section 6.1's outbox guarantee: if the
       apply rolls back, so do its notifications, with no compensating logic.

    Any failure in 5-8 raises, the whole transaction rolls back, and the run is then marked
    `SUPERSEDED` in a **fresh** transaction -- so a refusal leaves zero rows changed in
    `appointments`, `dock_occupancy`, `audit_logs` and `notification_outbox`, and the only write is
    the retirement of an artifact that has just been proven inapplicable.
    """
    route = f"POST /api/v1/scheduling/runs/{scheduling_run_id}/apply"
    req_hash = payload_hash(
        {"scheduling_run_id": scheduling_run_id, "snapshot_hash": snapshot_hash}
    )
    replay = await lookup_idempotency(
        session, key=idempotency_key, user_id=ctx.user_id, route=route, request_hash=req_hash
    )
    if replay is not None:
        return ApplyResult.model_validate({**replay["response"], "idempotent_replay": True})

    moment = now or datetime.now(timezone.utc)
    run = await runs_repo.lock_run(session, scheduling_run_id=scheduling_run_id)
    if run is None:
        raise AppError(
            f"Scheduling run '{scheduling_run_id}' not found.", code="NOT_FOUND", status_code=404
        )
    facility_id = str(run["facility_id"])
    # D5's boundary, enforced here rather than only at the router: ops *requests*, a planner
    # *applies*. The router narrows the role set; this narrows the facility.
    assert_facility_write_scope(ctx, facility_id)

    if str(run["status"]) != STATUS_PROPOSED:
        await session.commit()
        return ApplyResult(
            as_of=_as_of(),
            code="ALREADY_APPLIED" if str(run["status"]) == STATUS_APPLIED else "RUN_NOT_ACTIVE",
            scheduling_run_id=scheduling_run_id,
            status=str(run["status"]),
            notification_batch_id=(
                scheduling_run_id if str(run["status"]) == STATUS_APPLIED else None
            ),
            notifications_enqueued=int(run.get("notifications_enqueued") or 0),
            idempotency_key=idempotency_key,
        )

    stored_hash = str(run["snapshot_hash"])
    frozen = (
        _coerce_dt(run["horizon_start"]),
        _coerce_dt(run["horizon_end"]),
        str(run["horizon_end_reason"]),
    )
    scope = await build_scope(
        session,
        facility_id=facility_id,
        now=moment,
        frozen_horizon=(frozen[0], frozen[1], frozen[2]),  # type: ignore[arg-type]
    )
    current_hash, _ = await compute_run_snapshot_hash(session, scope, actor_user_id=ctx.user_id)

    if snapshot_hash != stored_hash or current_hash != stored_hash:
        return await _refuse(
            session,
            ctx,
            run=run,
            code="SNAPSHOT_DRIFT",
            reason=SUPERSEDED_SNAPSHOT_DRIFT,
            moment=moment,
            idempotency_key=idempotency_key,
            route=route,
            req_hash=req_hash,
            drift={
                "expected_snapshot_hash": stored_hash,
                "current_snapshot_hash": current_hash,
                "supplied_snapshot_hash": snapshot_hash,
                "supplied_matches_run": snapshot_hash == stored_hash,
                "message": (
                    "The capacity this proposal was computed against has changed. Request a fresh "
                    "proposal (SOLUTION_DESIGN.md section 5.1: revalidate and re-run on drift)."
                ),
            },
        )

    proposal = ProposalDiff.model_validate(run.get("proposal_json") or {})
    jobs_by_shipment = {job.shipment_id: job for job in scope.jobs}
    to_write = [*proposal.moved, *proposal.newly_placed]

    # Local, and hoisted above the `try` because the IntegrityError handler needs it too:
    # `allocation` imports `scheduling.snapshot` and (lazily) `scheduling.holds`, and `holds`
    # imports `allocation` -- a module-level import here would sit inside that cycle. Same hook
    # shape `snapshot.load_appointment_snapshots` and `allocation._claim_dock_occupancy` both use.
    from app.scheduling import allocation

    infeasible: list[dict[str, Any]] = []
    try:
        # --- step 5: release every moved claim first -----------------------------------------
        for view in proposal.moved:
            if view.appointment_id:
                await allocation._release_dock_occupancy(session, view.appointment_id)

        # --- step 6: revalidate each placement through the shared Stage-1 guard ---------------
        candidates_by_slot = {str(row["slot_id"]): row for row in scope.candidates}
        releasable_slots = movable_slot_ids_of(scope)
        for view in to_write:
            job = jobs_by_shipment.get(view.shipment_id)
            candidate = candidates_by_slot.get(view.slot_id)
            if job is None or candidate is None:
                infeasible.append(
                    {
                        "shipment_id": view.shipment_id,
                        "slot_id": view.slot_id,
                        "failure_code": "SCOPE_CHANGED",
                        "message": (
                            "The shipment or the interval is no longer inside this run's horizon."
                        ),
                    }
                )
                continue
            probe = dict(candidate)
            # The identical nulling rule `_evaluate_jobs` applied at propose time -- see
            # `movable_slot_ids_of` for why the two must be one function and what broke when they
            # were two comprehensions.
            if probe.get("active_appointment_id") is not None and (
                view.slot_id in releasable_slots
                or str(probe["active_appointment_id"]) == str(view.appointment_id or "")
            ):
                probe["active_appointment_id"] = None
            option, reason = evaluate_candidate_slot(
                shipment=job.shipment,
                facility=scope.facility,
                eta_dt=job.release,
                candidate=probe,
                checked_constraints=sorted(load_scheduling_constraints().hard_constraint_ids()),
                facility_rules=scope.facility_rules,
                driver_window=job.driver_window,
            )
            if option is None:
                infeasible.append(
                    {
                        "shipment_id": view.shipment_id,
                        "slot_id": view.slot_id,
                        "failure_code": (reason.failure_code if reason else "SLOT_NOT_FEASIBLE"),
                        "message": (
                            reason.message if reason else "The proposed interval is not feasible."
                        ),
                    }
                )

        if infeasible:
            # Section 7.5.3: PARTIALLY_INFEASIBLE "refuses entirely". Raising rather than returning
            # is what discards the releases made above -- the router and `_refuse` both roll back.
            raise _PartiallyInfeasible(infeasible)

        # --- steps 7-8: the writes, through the real primitives -------------------------------
        moved_count = 0
        placed_count = 0
        notifications = 0
        # Tracked so the exclusion-constraint handler below can name the placement PostgreSQL
        # refused. Flow 9 step 5 requires the overlay to explain *which* constraint invalidated the
        # proposal; "a claim conflicted somewhere in this run" is not that.
        writing: PlacementView | None = None
        for view in proposal.moved:
            writing = view
            await _apply_move(session, ctx, view=view, run_id=scheduling_run_id, moment=moment)
            moved_count += 1
            if await _notify(session, view=view, run_id=scheduling_run_id):
                notifications += 1
        for view in proposal.newly_placed:
            writing = view
            await _apply_new_placement(
                session, ctx, view=view, run_id=scheduling_run_id, moment=moment
            )
            placed_count += 1
            if await _notify(session, view=view, run_id=scheduling_run_id):
                notifications += 1
        writing = None

        applied = await runs_repo.mark_applied(
            session,
            scheduling_run_id=scheduling_run_id,
            applied_by_user_id=ctx.user_id,
            applied_at=moment,
            notifications_enqueued=notifications,
        )
        if not applied:  # pragma: no cover - the FOR UPDATE lock above already serialises this
            raise AppError(
                "The proposal was actioned by someone else.",
                code="ALREADY_ACTIONED",
                status_code=409,
            )

        result = ApplyResult(
            as_of=_as_of(),
            code="APPLIED",
            scheduling_run_id=scheduling_run_id,
            status=STATUS_APPLIED,
            notification_batch_id=scheduling_run_id,
            notifications_enqueued=notifications,
            moved=moved_count,
            newly_placed=placed_count,
            unchanged=len(proposal.unchanged),
            idempotency_key=idempotency_key,
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
        return result

    except _PartiallyInfeasible as exc:
        return await _refuse(
            session,
            ctx,
            run=run,
            code="PARTIALLY_INFEASIBLE",
            reason=SUPERSEDED_PARTIALLY_INFEASIBLE,
            moment=moment,
            idempotency_key=idempotency_key,
            route=route,
            req_hash=req_hash,
            infeasible=exc.rows,
        )
    except IntegrityError as exc:
        # D1's exclusion constraint is the final authority, and it having the last word here is the
        # design working rather than failing: the proposal's own overlap model said these intervals
        # were free and PostgreSQL disagreed, so the whole run is refused rather than half-applied.
        constraint = allocation.allocation_unique_constraint_name(exc)
        if constraint is None:
            raise
        return await _refuse(
            session,
            ctx,
            run=run,
            code="PARTIALLY_INFEASIBLE",
            reason=SUPERSEDED_PARTIALLY_INFEASIBLE,
            moment=moment,
            idempotency_key=idempotency_key,
            route=route,
            req_hash=req_hash,
            infeasible=[
                {
                    "shipment_id": writing.shipment_id if writing else None,
                    "slot_id": writing.slot_id if writing else None,
                    "dock_id": writing.dock_id if writing else None,
                    "claim_start_ts": writing.claim_start_ts if writing else None,
                    "claim_end_ts": writing.claim_end_ts if writing else None,
                    "failure_code": "POSTGRES_ALLOCATION_CONFLICT",
                    "message": (
                        "PostgreSQL refused this placement because another active claim already "
                        f"holds that capacity (constraint {constraint}). The whole proposal is "
                        "refused."
                    ),
                }
            ],
        )


class _PartiallyInfeasible(Exception):
    """Internal control flow for section 7.5.3's `PARTIALLY_INFEASIBLE`.

    An exception rather than an early return on purpose: it unwinds past the claim releases made
    earlier in the same transaction, so the rollback in `_refuse` is what guarantees "refuses
    entirely" means zero capacity writes rather than "we tried to undo it".
    """

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        super().__init__("proposal is partially infeasible")
        self.rows = rows


async def _refuse(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    run: dict[str, Any],
    code: str,
    reason: str,
    moment: datetime,
    idempotency_key: str,
    route: str,
    req_hash: str,
    drift: dict[str, Any] | None = None,
    infeasible: list[dict[str, Any]] | None = None,
) -> ApplyResult:
    """Refuse an apply: roll back every capacity write, retire the run, record the refusal.

    The rollback comes **first** and is unconditional. Everything the apply attempted -- claim
    releases, appointment updates, audit rows, outbox rows -- is discarded, which is what makes
    section 5.1's *"All-or-nothing per run"* a property of the transaction rather than of the
    control flow above it.

    Then, in a fresh transaction, the run is marked `SUPERSEDED`. Both refusal codes mean the stored
    proposal is provably inapplicable, and leaving it `PROPOSED` would hold the facility's one
    active-run slot against the fresh proposal the planner is being told to request
    (Flow 9 step 4). This is a *run-lifecycle* write, not a capacity write -- the distinction the
    proof suite asserts on rather than a blanket "nothing was written".

    The refusal is stored under the idempotency key too, so a retried apply of a drifted run gets
    the same typed refusal instead of re-running the whole scope build.
    """
    await session.rollback()
    scheduling_run_id = str(run["scheduling_run_id"])
    await runs_repo.mark_superseded(
        session,
        scheduling_run_id=scheduling_run_id,
        reason=reason,
        superseded_at=moment,
    )
    result = ApplyResult(
        as_of=_as_of(),
        code=code,
        scheduling_run_id=scheduling_run_id,
        status=STATUS_SUPERSEDED,
        drift=drift,
        infeasible=infeasible or [],
        idempotency_key=idempotency_key,
    )
    await store_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
        response=result.model_dump(),
        status_code=409,
    )
    await session.commit()
    return result


async def _apply_move(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    view: PlacementView,
    run_id: str,
    moment: datetime,
) -> None:
    """Move one existing appointment onto its proposed interval.

    Byte-for-byte the same three writes `counter_offer` makes -- update `slot_id`, re-claim through
    `_claim_dock_occupancy`, write an `audit_logs` row -- because there is one capacity authority in
    this product and a second write path into `dock_occupancy` is how a system acquires two. The
    release already happened in the caller (see `apply_schedule_proposal` step 5).

    The appointment's **status is deliberately not touched.** A CONFIRMED promise that moves is
    still confirmed -- the facility changed where, not whether -- and demoting it to
    PENDING_CONFIRMATION would silently hand it back to the D9 expiry clock and re-open a decision
    the planner already made. A PENDING request that moves is still pending, and its `booked_at`
    (the anchor D9 measures its TTL from) is untouched for the same reason `counter_offer` leaves it
    alone: rewriting it would hand the warehouse an unbounded way to sit on capacity.
    """
    from app.scheduling import allocation

    appointment_id = str(view.appointment_id)
    await session.execute(
        text(
            """
            UPDATE public.appointments
               SET slot_id = :slot_id, updated_at = :updated_at
             WHERE appointment_id = :appointment_id
            """
        ),
        {"slot_id": view.slot_id, "updated_at": moment, "appointment_id": appointment_id},
    )
    claim = await allocation._claim_dock_occupancy(
        session,
        appointment_id=appointment_id,
        shipment_id=view.shipment_id,
        slot_id=view.slot_id,
        now=moment,
        actor_user_id=ctx.user_id,
    )
    if claim is None:
        raise AppError(
            "Could not claim dock capacity for a re-sequenced appointment.",
            code="DOCK_OCCUPANCY_CLAIM_FAILED",
            status_code=500,
        )
    await _write_audit(
        session,
        ctx,
        action_type=AUDIT_ACTION_MOVE,
        entity_id=appointment_id,
        moment=moment,
        old_value={
            "slot_id": view.previous_slot_id,
            "dock_id": view.previous_dock_id,
            "slot_start_ts": view.previous_start_ts,
        },
        new_value={
            "transition": AUDIT_TRANSITION_MOVED,
            "scheduling_run_id": run_id,
            "slot_id": view.slot_id,
            "dock_id": view.dock_id,
            "slot_start_ts": view.start_ts,
            "delta_minutes": view.delta_minutes,
            "communicated": view.communicated,
            "counted_as_churn": view.is_churn,
            "occupancy_window": claim["window"],
        },
    )


async def _apply_new_placement(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    view: PlacementView,
    run_id: str,
    moment: datetime,
) -> None:
    """Create the appointment a `newly placed` job never had.

    **`PENDING_CONFIRMATION`, not `CONFIRMED`, and that is D6 rather than caution.** *"Human planner
    always confirms PENDING -> CONFIRMED. No rules-based auto-confirm, no LLM confirm."* A planner
    applying a proposal has decided *where* this truck should go; the promise to the driver is still
    a separate, human confirmation. Writing CONFIRMED here would let one press of Apply auto-confirm
    N appointments, which is the exact violation section 7.5.1 warns about for `bulk_confirm`
    (*"A client-side-only predicate check would be auto-confirmation wearing a button"*), reached by
    a different door.

    `booking_source = 'SCHEDULING_TOOL'` is a value the shipped baseline CHECK already admits
    (20260805201923:175) -- not a new one -- and it is what makes "which of these bookings did the
    sequencer create" answerable by query rather than by joining the audit log.

    The claim goes in immediately after the appointment, in the same transaction, for the reason
    `request_slot` states: *"committing an appointment without its claim would leave the interval
    unprotected."*
    """
    from app.scheduling import allocation

    appointment_id = new_id("APT")
    await session.execute(
        text(
            """
            INSERT INTO public.appointments (
              appointment_id, shipment_id, slot_id, appointment_status, booking_source,
              is_current, booked_at, confirmed_at, cancelled_at, cancellation_reason,
              replaced_appointment_id, warehouse_confirmation_ref, updated_at
            ) VALUES (
              :appointment_id, :shipment_id, :slot_id, 'PENDING_CONFIRMATION', :booking_source,
              1, :booked_at, NULL, NULL, NULL, NULL, NULL, :updated_at
            )
            """
        ),
        {
            "appointment_id": appointment_id,
            "shipment_id": view.shipment_id,
            "slot_id": view.slot_id,
            "booking_source": BOOKING_SOURCE_SEQUENCER,
            "booked_at": moment,
            "updated_at": moment,
        },
    )
    claim = await allocation._claim_dock_occupancy(
        session,
        appointment_id=appointment_id,
        shipment_id=view.shipment_id,
        slot_id=view.slot_id,
        now=moment,
        actor_user_id=ctx.user_id,
    )
    if claim is None:  # pragma: no cover - unreachable for a freshly minted appointment id
        raise AppError(
            "Could not claim dock capacity for a newly placed appointment.",
            code="DOCK_OCCUPANCY_CLAIM_FAILED",
            status_code=500,
        )
    view.appointment_id = appointment_id
    await _write_audit(
        session,
        ctx,
        action_type=AUDIT_ACTION_PLACE,
        entity_id=appointment_id,
        moment=moment,
        old_value=None,
        new_value={
            "transition": AUDIT_TRANSITION_PLACED,
            "scheduling_run_id": run_id,
            "shipment_id": view.shipment_id,
            "slot_id": view.slot_id,
            "dock_id": view.dock_id,
            "status": "PENDING_CONFIRMATION",
            "booking_source": BOOKING_SOURCE_SEQUENCER,
            "occupancy_window": claim["window"],
        },
    )


async def _write_audit(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    action_type: str,
    entity_id: str,
    moment: datetime,
    old_value: dict[str, Any] | None,
    new_value: dict[str, Any],
) -> None:
    """One `audit_logs` row per placement, carrying the run id.

    FR-SYS-014 / section 8: *"who, what, when, which policy version, which tool call."* The run id
    in `new_value_json` is what makes "which proposal moved this truck" a query rather than a
    reconstruction -- and it is the join that lets `get_scheduling_run`'s replay be checked against
    what actually happened.
    """
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
            "action_type": action_type,
            "entity_id": entity_id,
            "old_value_json": json.dumps(old_value, default=str) if old_value else None,
            "new_value_json": json.dumps(new_value, default=str),
            "created_at": moment.isoformat(),
        },
    )


async def _notify(session: AsyncSession, *, view: PlacementView, run_id: str) -> bool:
    """One outbox row per affected driver, inside the applying transaction.

    Section 5.1's cascade path: *"capacity incident -> one run scoped to the affected docks and
    window -> one proposal -> planner applies -> **notifications batch out**. Not N independent
    escalations."* N notifications is right exactly where N escalations is wrong -- each affected
    driver is a different person who has to be told about their own slot -- which is the same split
    `notification_outbox.enqueue_option_withdrawn` already documents for a dock outage.

    `dedupe_scope = run_id` is what keeps the key an EVENT INSTANCE. Without it the key would be
    `APPOINTMENT_RESEQUENCED:<appointment>:<recipient>`, so the second time a facility re-sequenced
    the same truck the driver would silently not be told -- the day-bucket failure mode issue #96
    recorded, in a new place. With it, the key is one per (appointment, run, recipient): a replayed
    apply writes nothing, two different runs both notify.

    Returns whether a row was newly enqueued. `enqueue_notification` never raises and never commits,
    so a notification can never be the reason a schedule fails to apply.
    """
    if not view.appointment_id:
        return False
    written = await notification_outbox.enqueue_notification(
        session,
        event_type=notification_outbox.APPOINTMENT_RESEQUENCED,
        appointment_id=view.appointment_id,
        shipment_id=view.shipment_id,
        dedupe_scope=run_id,
    )
    return written is not None


# ---------------------------------------------------------------------------------------------
# section 7.5.5 -- request_sequencer_proposal (issue #54)
# ---------------------------------------------------------------------------------------------


async def request_sequencer_proposal(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    escalation_id: str,
    facility_id: str | None = None,
    now: datetime | None = None,
) -> SchedulingRunResult:
    """Section 7.5.5's eighth tool -- *"a thin delegate to section 7.5.3's
    `propose_facility_schedule`"*.

    The design's own words for what this is and is not: *"Delegates to section 7.5.3's
    `propose_facility_schedule` with `trigger_reason = 'CAPACITY_INCIDENT'` and the `escalation_id`
    attached to the resulting `scheduling_run_id`, rather than a parallel tool -- the incident and
    the run stay linkable. Returns the same shape section 7.5.3 already defines. **Ops triages and
    requests; a planner still applies** (`apply_schedule_proposal`, section 7.5.3) -- this tool
    cannot itself apply a proposal, preserving D5 across the two-surface handoff."*

    So it is deliberately thin: it resolves the incident, derives the facility from it, and calls
    the section 7.5.3 tool. Everything else -- the search, the objective, the debounce, the storage
    -- belongs to the one implementation above, because a second entry point that computed its own
    proposal would be exactly the "parallel tool" the design rules out.

    **The facility comes from the escalation's own row, never from the caller.** Section 7.5.5's
    table lists `facility_id` as an argument, and this signature keeps it -- but only as a value to
    *check*, never as the answer: a mismatch is refused rather than honoured, and omitting it is the
    normal case. That is section 7.5 principle 1 applied strictly (*"Where an id appears, it selects
    within the caller's scope and is validated against it"*), and it is stricter than the catalog's
    own wording because an escalation already knows which building it is about.

    Guarded like the other work-on-a-case tools, and the guards are mirrored exactly in
    `ops_copilot._classify_actions`, so the co-pilot can never recommend a button this refuses:
    non-terminal, acknowledged, and owned by the caller (or admin).
    """
    from app.services.escalation_service import STEPPER_POSITIONS, _escalation_queue_state

    state = await _escalation_queue_state(session, escalation_id)
    if state is None:
        raise AppError(
            f"Escalation '{escalation_id}' not found.", code="NOT_FOUND", status_code=404
        )
    incident_facility = str(state["facility_id"])
    assert_facility_write_scope(ctx, incident_facility)
    if facility_id is not None and facility_id != incident_facility:
        raise AppError(
            "facility_id does not match the escalation's own facility.",
            code="FORBIDDEN",
            status_code=403,
            detail=(
                "The facility a sequencer proposal covers is derived from the incident, never "
                "supplied by the caller (SOLUTION_DESIGN.md section 7.5 principle 1 / M15)."
            ),
        )

    status = str(state["escalation_status"])
    owner = state.get("owner_user_id")
    if status in {"RESOLVED", "CANCELLED"}:
        raise AppError(
            "This escalation is already closed.",
            code="ALREADY_ACTIONED",
            status_code=409,
            detail=f"escalation_status={status}",
        )
    if status not in {"ACKNOWLEDGED", "IN_PROGRESS"} or owner is None:
        raise AppError(
            "Acknowledge the escalation before requesting a proposal.",
            code="NOT_ACKNOWLEDGED",
            status_code=409,
            detail=f"escalation_status={status}, stepper={STEPPER_POSITIONS.get(status, 0)}",
        )
    if not ctx.is_admin and str(owner) != ctx.user_id:
        raise AppError(
            "Another coordinator owns this escalation.",
            code="NOT_OWNER",
            status_code=409,
            detail="Reassign it first if you need to work it.",
        )

    return await propose_facility_schedule(
        session,
        ctx,
        facility_id=incident_facility,
        trigger_reason=TRIGGER_CAPACITY_INCIDENT,
        escalation_id=escalation_id,
        now=now,
    )


__all__ = [
    "CHURN_EPSILON_MINUTES",
    "MAX_JOBS",
    "MAX_RUN_LIST",
    "TRIGGER_CAPACITY_INCIDENT",
    "TRIGGER_PLANNER_REQUESTED",
    "TRIGGER_REASONS",
    "WEIGHT_CHURN",
    "ApplyResult",
    "Coefficients",
    "Job",
    "ObjectiveValues",
    "Placement",
    "PlacementView",
    "ProposalDiff",
    "SchedulingRunList",
    "SchedulingRunResult",
    "SchedulingRunSummary",
    "Scope",
    "UnplaceableView",
    "apply_schedule_proposal",
    "build_diff",
    "build_explanation",
    "build_objective",
    "build_scope",
    "claim_window",
    "compute_run_snapshot_hash",
    "get_scheduling_run",
    "list_scheduling_runs",
    "movable_slot_ids_of",
    "placement_cost",
    "propose_facility_schedule",
    "request_sequencer_proposal",
]
