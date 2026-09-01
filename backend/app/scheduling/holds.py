"""D2's HELD promise-state: the soft, TTL-bounded hold and the tool that commits it.

Design citation: `SOLUTION_DESIGN.md` section 0.8 ("D2 in concrete terms"), section 4 (the promise
lifecycle), section 7.1 (`request_slot`'s two-phase contract and the missing `confirm_held_slot`),
section 7.5.4 (the 12-tool driver allowlist), D2, M5, M6, M10, M15. GitHub issue #53.

## Why this is its own module and not more lines in `allocation.py`

The same reason `expiry.py` is its own module, stated there and applying again here: `allocation.py`
owns the *appointment* lifecycle, and every one of its mutating paths starts from an appointment
row. A hold has no appointment row -- section 4 is explicit: *"Held != booked: no `appointments`
row exists yet."* A hold is a `dock_occupancy` row and nothing else. Threading a second, rowless
lifecycle through functions that all assume `appointment_id` would have meant either an optional
appointment id on every helper or a parallel set of near-copies. Neither is better than one module
that owns the hold from creation to either commitment or expiry.

The narrower, immediate reason: `allocation.py` is under concurrent edit by other tracks (issues
#62/#63 landed in it during this change). Keeping the hold path out of it means this work adds one
small hook there rather than ~250 lines competing for the same hunks.

## The state machine this file implements, and where each transition lives

    find_feasible_slots ──► SHOWN (reserves nothing, no row anywhere)
                              │  driver picks a slot_id
                              ▼
                       HELD  (dock_occupancy row, state='HELD', expires_at=now+90s,
                              appointment_id NULL)              ← `create_hold`, below
                              │  confirm within TTL
                              ▼
              PENDING_CONFIRMATION  (appointments row created; the SAME dock_occupancy
                                     row flips state and gains the appointment_id)
                                                                ← `confirm_held_slot`, below
                              │  TTL elapses instead
                              ▼
                           EXPIRED  (same row, state flipped in place)
                                                                ← `sweep_held_holds`, below

## The two things in here that are load-bearing rather than plumbing

**1. `confirm_held_slot` flips the existing row; it never deletes and re-inserts.**
That is the whole reason a hold is modelled as a `dock_occupancy` row in the first place (section 4:
*"not as a separate hold table, so there is one overlap truth and no drift between 'held' and
'booked' bookkeeping"*). A DELETE-then-INSERT would open a window -- however brief -- in which the
interval sits under no row at all and the exclusion constraint has nothing to exclude against, so a
competing `create_hold` committing in that window would win an interval that was already promised.
An UPDATE of the same row has no such window: the row is under the constraint continuously, and the
transition is atomic.

**2. Expiry is checked lazily on read, not merely swept.**
Section 0.8: *"Every read filters `state='HELD' AND expires_at > now()`; a sweeper transitions stale
rows to `EXPIRED`. **Never depend on the sweeper for correctness -- only for hygiene.**"* So
`confirm_held_slot`'s locking SELECT carries `expires_at > :now` itself. If the sweeper is down, a
lapsed hold still cannot be confirmed. The sweeper only stops lapsed rows from sitting in the table
looking like live capacity.

## The race, and why it needs no new machinery

`confirm_held_slot` and `sweep_held_holds` contend on exactly the same rows, which is section 9.2
#3's race one level down from the D9 one `expiry.py` already documents. It resolves identically and
for the same documented PostgreSQL reason (READ COMMITTED re-evaluates a `WHERE` clause against the
version a competing committed transaction left behind -- PostgreSQL "Transaction Isolation" 13.2.1):

* **Confirm commits first.** The sweeper's claim subquery carries `state = 'HELD'`. Postgres
  re-evaluates it against the committed version, which now says `PENDING_CONFIRMATION`, so the row
  is not returned and the sweeper does nothing. No compensating logic.
* **Sweeper commits first.** `confirm_held_slot`'s locking SELECT carries `state = 'HELD'` too, so
  it returns nothing, and the caller gets `HOLD_EXPIRED` -- naming what happened rather than a bare
  409.

`SKIP LOCKED` in the sweeper covers the third case (the driver's confirm transaction is still open):
the row is left for the next cycle, which at a 1-minute cadence against a 90-second TTL is free.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.services import notification_outbox
from app.core.execution_context import ExecutionContext
from app.core.settings import get_settings
from app.scheduling import allocation
from app.scheduling.constraints import load_scheduling_constraints
from app.scheduling.feasibility import evaluate_candidate_slot
from app.scheduling.occupancy import CAPACITY_CONSUMING_STATES, claim_window_sql
from app.services.idempotency import lookup_idempotency, payload_hash
from app.services.ids import new_id

logger = logging.getLogger(__name__)

AUDIT_ACTION_CREATE_HOLD = "CREATE_HOLD"
AUDIT_ACTION_CONFIRM_HOLD = "CONFIRM_HELD_SLOT"
AUDIT_ACTION_EXPIRE_HOLD = "EXPIRE_HOLD"

# `CAPACITY_CONSUMING_STATES` is imported above rather than defined here (issue #97). The literal
# now lives in `occupancy.py` beside the liveness predicate built from it, because this module,
# `snapshot.py` and the read paths all need the same tuple, and three hand-maintained copies of a
# value whose entire job is to mean the same thing everywhere was two too many. It stays a
# module-level name here because `planner_service` and the unit drift guard import it from this
# module.


class HoldResult(BaseModel):
    """Section 7.1's `HELD` outcome: "capacity is now blocked for this driver"."""

    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    status: str = "HELD"
    code: str = "SLOT_HELD"
    shipment_id: str
    slot_id: str
    hold_id: str
    dock_id: str
    # Section 0.8's driver-facing promise: "reserved for you for 90 seconds" -- wording the UI must
    # keep distinct from "requested" and from "confirmed" (section 4).
    hold_expires_at: str
    hold_ttl_seconds: int
    policy_version: str
    idempotency_key: str | None = None
    idempotent_replay: bool = False
    appointment_writes: int = 0


class ConfirmHeldSlotResult(BaseModel):
    """Section 7.1: `confirm_held_slot` "produces `PENDING_CONFIRMATION`"."""

    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    status: str
    code: str
    hold_id: str
    shipment_id: str | None = None
    slot_id: str | None = None
    appointment_id: str | None = None
    appointment: dict[str, Any] | None = None
    policy_version: str | None = None
    conflict: dict[str, Any] | None = None
    idempotency_key: str | None = None
    idempotent_replay: bool = False
    appointment_writes: int = 0


class ExpiredHold(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hold_id: str
    dock_id: str
    shipment_id: str


class HeldSweepResult(BaseModel):
    """One HELD sweep cycle.

    `supported` is retained from the pre-#53 stub deliberately rather than dropped: it is part of
    the `/internal/jobs/expiry-sweep` response contract, and it still has a real job to do -- it is
    now False when the two-phase hold path is switched off, which is the honest answer for a deploy
    where the migration has not been applied yet.
    """

    model_config = ConfigDict(extra="forbid")

    supported: bool
    expired: int = 0
    ttl_seconds: int
    candidates: int = 0
    deferred_or_lost: int = 0
    batch_limit_reached: bool = False
    holds: list[ExpiredHold] = Field(default_factory=list)
    unsupported_reason: str | None = None


HELD_SWEEP_DISABLED_REASON = (
    "D2 HELD expiry is switched off because the two-phase hold path is disabled "
    "(TWO_PHASE_HOLD_ENABLED=false). No dock_occupancy row can be in state 'HELD' while "
    "request_slot commits straight to PENDING_CONFIRMATION, so there is nothing to sweep. Apply "
    "supabase/migrations/20260829134929_d2_held_state_dock_occupancy.sql and set the flag to "
    "enable both halves together."
)


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_hold_id(hold_id: str) -> int | None:
    """`dock_occupancy.occupancy_id` is `bigint`; every caller hands us a string. Returns None if
    the string is not an integer at all.

    This is not defensive tidying, it is the same class of hard runtime failure `expiry.py`
    documents for `timestamptz` binds, in the other direction. asyncpg type-checks every parameter
    against the column's real type and refuses to coerce: binding the str `'22'` to a bigint
    parameter raises `asyncpg.exceptions.DataError: invalid input for query argument $1: '22'
    ('str' object cannot be interpreted as an integer)`. Verified against PostgreSQL 18.3 on
    2026-08-29 -- it is the exact error the first integration run produced.

    Ids stay `str` at the tool and HTTP boundary (every other id in this system is a text key like
    `APT-...`, and an LLM-supplied argument is a string whatever the schema says), so the
    conversion belongs here, once, rather than at each of the three call sites.

    None rather than an exception for a non-numeric id because the caller's answer is the same as
    for an id that simply does not exist -- `HOLD_NOT_FOUND`. A driver's model hallucinating
    `"hold-abc"` should get a clean refusal it can narrate, not a 500.
    """
    try:
        return int(str(hold_id).strip())
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------
# HELD creation -- called from `allocation.request_slot`, which owns the eligibility work
# ------------------------------------------------------------------------------------------


async def create_hold(
    session: AsyncSession,
    *,
    shipment_id: str,
    slot_id: str,
    policy_version: str,
    ttl_seconds: int,
    now: datetime,
    actor_user_id: str,
) -> dict[str, Any] | None:
    """Insert the D2 hold, inside the caller's transaction. Returns the row, or None.

    Called only from `allocation.request_slot`, after that function has already done the scope
    check, the staleness check and the Stage 1 feasibility evaluation. This function deliberately
    does *not* repeat any of that: duplicating the eligibility guard here would give the system two
    places where "may this shipment take this slot" is decided, which is precisely the drift D1's
    single-overlap-truth design exists to avoid.

    **This INSERT is the concurrency decision, not a pre-check.** Everything the caller did before
    it is advisory; the exclusion constraint is what actually admits exactly one holder of an
    overlapping interval (section 0.8, M6). An `IntegrityError` from here is therefore a *normal*
    outcome -- the loser of a genuine race -- and the caller translates it through
    `allocation.allocation_unique_constraint_name` into `SLOT_CONFLICT_REFRESH_REQUIRED`, exactly
    as it already does for the PENDING_CONFIRMATION claim.

    The window expression mirrors `allocation._claim_dock_occupancy` character for character --
    `slot_start_ts` plus `expected_unload_min` plus the flat 15-minute changeover buffer, half-open
    `'[)'` -- because a hold and the booking it becomes must mean the *same* interval. If they
    differed, `confirm_held_slot` would be converting a hold on one interval into an appointment on
    another, and the exclusion constraint would have been protecting the wrong range all along.

    `appointment_id` is left NULL: section 4, "Held != booked: no `appointments` row exists yet."
    The `dock_occupancy_held_shape_check` constraint added by this feature's migration enforces
    that from the database side, so a future caller cannot quietly attach one.

    Issue #97 added the `expire_lapsed_holds_on_interval` call below. It is not a pre-check and it
    does not weaken the INSERT's role as the concurrency decision: it only removes rows §0.8
    already considers dead from the set the constraint can refuse against. See that function and
    `occupancy.py` for why the write side has to *make* the predicate true rather than filter on
    it the way the read side does.
    """
    # Same transaction as the INSERT, and necessarily before it: a lapsed-but-unswept hold on this
    # dock interval would otherwise fire the exclusion constraint and refuse a hold that §0.8 says
    # nothing is holding. This is the write half of the shared liveness predicate.
    await expire_lapsed_holds_on_interval(
        session,
        slot_id=slot_id,
        shipment_id=shipment_id,
        now=now,
        actor_user_id=actor_user_id,
    )
    expires_at = now + timedelta(seconds=ttl_seconds)
    row = (
        await session.execute(
            text(
                """
                INSERT INTO public.dock_occupancy (
                  dock_id, appointment_id, shipment_id, "window", state, expires_at,
                  policy_version
                )
                SELECT sl.dock_id,
                       NULL,
                       :shipment_id,
                       tstzrange(
                           sl.slot_start_ts,
                           sl.slot_start_ts
                             + ((s.expected_unload_min + 15) || ' minutes')::interval,
                           '[)'
                       ),
                       'HELD',
                       :expires_at,
                       :policy_version
                FROM public.appointment_slots sl
                JOIN public.shipments s ON s.shipment_id = :shipment_id
                WHERE sl.slot_id = :slot_id
                RETURNING occupancy_id, dock_id, "window", expires_at
                """
            ),
            {
                "shipment_id": shipment_id,
                "slot_id": slot_id,
                # asyncpg encodes a timestamptz parameter with its datetime codec and raises
                # DataError on a str -- the same bind-type rule `expiry.py` documents. Both
                # dock_occupancy.expires_at and appointments.updated_at are timestamptz; only
                # audit_logs.created_at is still text.
                "expires_at": expires_at,
                "policy_version": policy_version,
            },
        )
    ).mappings().first()
    if row is None:
        return None

    hold = dict(row)
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id,
              old_value_json, new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :user_id, :action_type, 'dock_occupancy', :entity_id,
              NULL, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"),
            "user_id": actor_user_id,
            "action_type": AUDIT_ACTION_CREATE_HOLD,
            "entity_id": str(hold["occupancy_id"]),
            "new_value_json": json.dumps(
                {
                    "state": "HELD",
                    "shipment_id": shipment_id,
                    "slot_id": slot_id,
                    "dock_id": hold["dock_id"],
                    "occupancy_window": hold["window"],
                    "expires_at": expires_at.isoformat(),
                    "ttl_seconds": ttl_seconds,
                    "policy_version": policy_version,
                },
                default=str,
            ),
            # M14: every state change reconstructable. `audit_logs.created_at` is still `text`
            # (never converted by E1.1), so it takes the ISO string -- see the bind-type note above.
            "created_at": now.isoformat(),
        },
    )
    return hold


# ------------------------------------------------------------------------------------------
# The consuming read (issue #83 / #85) -- "does this shipment have a live hold right now?"
# ------------------------------------------------------------------------------------------


HOLD_PROMISE_STATE = "HELD"
# Which authority named a shipment's promise state, in the same "never silently identical" spirit
# as `get_planner_queue`'s `interval_source` (issue #60). A surface that renders a HELD chip must be
# able to say *why* it is showing one.
PROMISE_STATE_SOURCE_APPOINTMENT = "appointments"
PROMISE_STATE_SOURCE_HOLD = "dock_occupancy_hold"


def hold_reads_enabled() -> bool:
    """Whether a read may reference the D2 hold columns at all.

    Not a stylistic gate on a feature: `dock_occupancy.state` / `.expires_at` do not exist until
    `20260829134929_d2_held_state_dock_occupancy.sql` is applied, and PostgreSQL resolves column
    references at *parse* time, so a statement naming them fails outright with `UndefinedColumn`
    on an unmigrated database rather than returning nothing. `TWO_PHASE_HOLD_ENABLED` is the flag
    `settings.py` already documents as "flip to true only after the migration is applied", which
    makes it the honest proxy for "these columns exist", and it is what `request_slot` itself
    branches on (`allocation.py`).

    Known limitation, stated rather than hidden: flipping the flag back off while holds are still
    live makes them invisible to these reads again for up to one TTL (90 s), during which they
    still consume capacity via the exclusion constraint. Correctness is unaffected -- no
    double-booking is possible either way -- but a preview could be optimistic for that window.
    The mitigation is the flag's own documented rollback note, not extra machinery here.
    """
    return get_settings().two_phase_hold_enabled


async def live_hold_for_shipment(
    session: AsyncSession, *, shipment_id: str, now: datetime
) -> dict[str, Any] | None:
    """The one live D2 hold on this shipment, or None. Safe to call with the flag off.

    Issues #83 and #85 are the same gap seen from two surfaces: every read that derives a promise
    state from `appointments.appointment_status` is blind to a hold, because §4 is explicit that
    *"Held is not booked: no `appointments` row exists yet"*. This is the missing half, written once
    here rather than as near-copies in `driver_reads`, `allocation` and the carrier repository.

    **`expires_at > :now` is applied here and is deliberately absent from the planner's
    displacement queries.** The two are answering different questions and §0.8 only mandates the
    filter for one of them: *"Every read filters `state='HELD' AND expires_at > now()`"* is about
    what promise a party actually holds -- a lapsed hold is not a promise, and telling a driver
    "reserved for you" about one would be a lie the sweeper has merely not caught up with yet. The
    planner's *displacement* read asks instead what PostgreSQL will refuse, and the exclusion
    constraint's predicate carries no time term at all, so a lapsed-but-unswept hold still blocks
    (verified empirically against PostgreSQL 18.3, 2026-08-29). Filtering there would re-introduce
    issue #84 in miniature.

    `now` is a parameter rather than SQL `now()` so §9.1's injected clock governs, the same reason
    `sweep_expired_appointments` and `get_planner_queue` take one.

    The slot join is LEFT, unlike `_locked_hold`'s: that function needs a slot because it is about
    to revalidate feasibility against it, whereas this one only needs the countdown, and a hold
    whose slot row cannot be resolved should still be *shown* rather than silently dropped.
    """
    if not hold_reads_enabled():
        return None
    row = (
        await session.execute(
            text(
                """
                SELECT o.occupancy_id, o.dock_id, o.shipment_id, o.state, o.expires_at,
                       lower(o."window") AS window_start,
                       upper(o."window") AS window_end,
                       sl.slot_id, sl.facility_id, sl.slot_start_ts, sl.slot_end_ts,
                       d.dock_code, d.dock_type
                FROM public.dock_occupancy o
                LEFT JOIN public.appointment_slots sl
                       ON sl.dock_id = o.dock_id
                      AND sl.slot_start_ts = lower(o."window")
                LEFT JOIN public.docks d ON d.dock_id = o.dock_id
                WHERE o.shipment_id = :shipment_id
                  AND o.state = 'HELD'
                  AND o.expires_at > :now
                ORDER BY o.expires_at DESC
                LIMIT 1
                """
            ),
            {"shipment_id": shipment_id, "now": now},
        )
    ).mappings().first()
    if row is None:
        return None
    hold = dict(row)
    expires_at = hold.get("expires_at")
    return {
        # `hold_id` is the name every caller of `confirm_held_slot` uses for this value, so the
        # read hands back the same key the write takes rather than making each surface rename it.
        "hold_id": str(hold["occupancy_id"]),
        "shipment_id": str(hold["shipment_id"]),
        "dock_id": str(hold["dock_id"]),
        "dock_code": hold.get("dock_code"),
        "dock_type": hold.get("dock_type"),
        "slot_id": hold.get("slot_id"),
        "facility_id": hold.get("facility_id"),
        "slot_start_ts": hold.get("slot_start_ts"),
        "slot_end_ts": hold.get("slot_end_ts"),
        "window_start": hold.get("window_start"),
        "window_end": hold.get("window_end"),
        "state": str(hold["state"]),
        "expires_at": expires_at,
        # The countdown the HELD screens render. Computed server-side against the same `now` the
        # row was filtered with, so the client never has to trust its own clock to decide whether
        # a hold is still live -- U48's "the interface renders receipts, it never computes them".
        "expires_in_seconds": (
            max(0, int((expires_at - now).total_seconds())) if expires_at is not None else None
        ),
    }


# ------------------------------------------------------------------------------------------
# `confirm_held_slot` -- section 7.5.4's twelfth driver tool
# ------------------------------------------------------------------------------------------


async def _locked_hold(
    session: AsyncSession, *, hold_id: int, now: datetime
) -> dict[str, Any] | None:
    """Lock one live hold, or return None.

    The three predicates are each doing separate work and none is redundant:

    * `state = 'HELD'` is the race resolution against the sweeper (see the module docstring).
    * `expires_at > :now` is section 0.8's mandatory lazy expiry check -- *"Never depend on the
      sweeper for correctness"*. A hold whose TTL elapsed thirty seconds ago is not confirmable
      even if the sweeper has not run since.
    * `FOR UPDATE` (no `SKIP LOCKED`) because this is a user-facing path. A driver whose confirm
      silently no-ops because a row was momentarily locked would be a bug; blocking briefly and
      then getting a true answer is correct. This is the inverse of the sweeper's choice, and
      `expiry.py`'s docstring explains the same asymmetry for the D9 pair.

    `shipment_id` comes off this row and is never accepted from the caller -- see
    `confirm_held_slot` for the M15 argument.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT o.occupancy_id, o.dock_id, o.shipment_id, o.state, o.expires_at,
                       o.policy_version, o."window",
                       lower(o."window") AS window_start,
                       sl.slot_id, sl.facility_id, sl.slot_start_ts, sl.slot_end_ts,
                       sl.slot_status, sl.block_reason,
                       d.dock_code, d.dock_type, d.supports_refrigerated,
                       d.max_vehicle_weight_kg, d.dock_status
                FROM public.dock_occupancy o
                JOIN public.appointment_slots sl
                  ON sl.dock_id = o.dock_id
                 AND sl.slot_start_ts = lower(o."window")
                JOIN public.docks d ON d.dock_id = o.dock_id
                WHERE o.occupancy_id = :hold_id
                  AND o.state = 'HELD'
                  AND o.expires_at > :now
                FOR UPDATE OF o
                """
            ),
            {"hold_id": hold_id, "now": now},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _hold_epitaph(session: AsyncSession, hold_id: int) -> dict[str, Any] | None:
    """Read back a hold that `_locked_hold` refused, so the caller can say *why* rather than 404.

    Costs one extra query only on the failure path. Section 7.5.1's principle for the D9 race --
    *"the loser gets ALREADY_ACTIONED with the winning transition named"* -- applies just as much
    to a driver who tapped Confirm two seconds after their hold lapsed: "that hold lapsed, here are
    current options" (section 0.8) is only possible if we know it lapsed rather than never existed.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT occupancy_id, state, expires_at, shipment_id, appointment_id
                FROM public.dock_occupancy
                WHERE occupancy_id = :hold_id
                """
            ),
            {"hold_id": hold_id},
        )
    ).mappings().first()
    return dict(row) if row else None


async def confirm_held_slot(
    session: AsyncSession,
    ctx: ExecutionContext,
    *,
    hold_id: str,
    idempotency_key: str,
    note: str | None = None,
    persist: bool = True,
) -> ConfirmHeldSlotResult:
    """Convert a live hold into a `PENDING_CONFIRMATION` appointment. Section 7.1's missing tool.

    Section 7.1 states the contract in one sentence: *"Needed: takes the hold id, revalidates inside
    the transaction, and produces `PENDING_CONFIRMATION`."* All three clauses are load-bearing and
    all three are implemented literally.

    **"Takes the hold id" -- and nothing else that decides scope (M15).** `hold_id` is the only
    client-supplied identifier. `shipment_id`, `slot_id`, `dock_id` and `facility_id` are all read
    off the held row server-side, and the caller's authority over that shipment is then checked
    against the identity on the `ExecutionContext`. Section 7.5's first principle: *"Scope is
    derived from the authenticated identity, never from an argument. No tool accepts a `facility_id`
    or `carrier_id` that decides what the caller may see."* Accepting a `shipment_id` here would
    have been the classic hole -- pass someone else's hold id together with your own shipment id and
    the scope check passes while the capacity moves.

    **"Revalidates inside the transaction."** Stage 1 is re-run against the locked row, not against
    what was true 90 seconds ago when the hold was taken. A dock can go down, a slot can be blocked,
    an ETA can move past the interval inside a 90-second window; committing a hold that is no longer
    feasible would launder a stale decision into a real appointment. On failure the hold is released
    rather than left to rot -- the driver cannot use it, so nobody else should be blocked by it.

    **"Produces PENDING_CONFIRMATION."** The appointment row is created here, at confirm time --
    never at hold time (section 4: *"Held != booked: no `appointments` row exists yet"*) -- and the
    *same* `dock_occupancy` row is flipped to carry it. See the module docstring for why flipping
    rather than re-inserting is the whole point.

    D6 is untouched by this: `PENDING_CONFIRMATION` is still a request awaiting a human. This tool
    cannot and must not reach `CONFIRMED` (M7).
    """
    route = "POST /api/v1/holds/{hold_id}/confirm"
    req_hash = payload_hash({"hold_id": hold_id, "note": note})
    replay = await lookup_idempotency(
        session,
        key=idempotency_key,
        user_id=ctx.user_id,
        route=route,
        request_hash=req_hash,
    )
    if replay is not None:
        # M9: a retried confirm must not produce a second appointment. Unlike `request_slot`'s
        # replay branch there is no "was the claim since released" re-check to do here, because a
        # hold is single-use by construction: the row it confirmed is no longer in state 'HELD', so
        # a genuine re-run could not succeed anyway.
        return ConfirmHeldSlotResult.model_validate({**replay["response"], "idempotent_replay": True})

    now = datetime.now(timezone.utc)
    constraints = load_scheduling_constraints()

    numeric_hold_id = _coerce_hold_id(hold_id)
    if numeric_hold_id is None:
        raise AppError(
            "No such hold.",
            code="HOLD_NOT_FOUND",
            status_code=404,
        )

    hold = await _locked_hold(session, hold_id=numeric_hold_id, now=now)
    if hold is None:
        epitaph = await _hold_epitaph(session, numeric_hold_id)
        if epitaph is None:
            raise AppError(
                "No such hold.",
                code="HOLD_NOT_FOUND",
                status_code=404,
            )
        # Deliberately not scope-checked before answering: `occupancy_id` is a server-minted
        # sequence value the caller cannot enumerate meaningfully, and the response says only that
        # *a* hold is no longer live -- no shipment, dock, facility or carrier is disclosed. The
        # alternative (looking up the shipment to scope-check a row we are refusing anyway) would
        # cost a query to leak strictly more.
        state = str(epitaph.get("state") or "UNKNOWN")
        if state == "HELD":
            message = (
                "That hold lapsed before it was confirmed. Its 90-second reservation window has "
                "closed; ask for current options and choose again."
            )
            code = "HOLD_EXPIRED"
        else:
            message = f"That hold is no longer live: it is already {state}."
            code = "HOLD_ALREADY_ACTIONED"
        return ConfirmHeldSlotResult(
            as_of=_as_of(),
            status="CONFLICTED",
            code=code,
            hold_id=hold_id,
            conflict={"reason_code": code, "message": message, "hold_state": state},
            idempotency_key=idempotency_key,
            appointment_writes=0,
        )

    shipment_id = str(hold["shipment_id"])
    slot_id = str(hold["slot_id"])

    # ---- M15: scope derived from the held row, checked against the authenticated identity ----
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
        allocation._assert_driver_scope(ctx, shipment_data)
    else:
        allocation._assert_ops_scope(ctx, shipment_data)

    # ---- "revalidates inside the transaction" ----
    candidate = {
        "slot_id": slot_id,
        "facility_id": hold["facility_id"],
        "dock_id": hold["dock_id"],
        "slot_start_ts": hold["slot_start_ts"],
        "slot_end_ts": hold["slot_end_ts"],
        "slot_status": hold["slot_status"],
        "block_reason": hold["block_reason"],
        "dock_code": hold["dock_code"],
        "dock_type": hold["dock_type"],
        "supports_refrigerated": hold["supports_refrigerated"],
        "max_vehicle_weight_kg": hold["max_vehicle_weight_kg"],
        "dock_status": hold["dock_status"],
        # The hold itself is the only capacity claim on this interval, and it belongs to this
        # caller -- so there is no competing active appointment to declare. Passing the hold's own
        # dock event would make Stage 1 refuse the very interval it just reserved.
        "active_appointment_id": None,
        "active_dock_event_id": None,
    }
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
                "dock_id": hold["dock_id"],
                "slot_start_ts": hold["slot_start_ts"],
                "slot_end_ts": hold["slot_end_ts"],
            },
        )
    ).mappings().first()
    candidate["active_dock_event_id"] = dock_event["dock_event_id"] if dock_event else None

    option, reason = evaluate_candidate_slot(
        shipment=shipment_data,
        facility=shipment_data,
        eta_dt=datetime.fromisoformat(str(shipment_data["effective_eta_ts"])),
        candidate=candidate,
        checked_constraints=sorted(constraints.hard_constraint_ids()),
    )
    if option is None:
        # The hold is dead either way; release the interval instead of leaving 90 seconds of
        # capacity sterilised by a reservation nobody can now use.
        await _expire_hold_row(
            session,
            hold_id=int(hold["occupancy_id"]),
            actor_user_id=ctx.user_id,
            now=now,
            reason=(reason.failure_code if reason else "SLOT_NOT_FEASIBLE"),
        )
        result = ConfirmHeldSlotResult(
            as_of=_as_of(),
            status="CONFLICTED",
            code="SLOT_CONFLICT_REFRESH_REQUIRED",
            hold_id=hold_id,
            shipment_id=shipment_id,
            slot_id=slot_id,
            policy_version=constraints.policy_version,
            conflict={
                "reason_code": reason.failure_code if reason else "SLOT_NOT_FEASIBLE",
                "message": (
                    reason.message
                    if reason
                    else "The held slot stopped being feasible before it was confirmed."
                ),
            },
            idempotency_key=idempotency_key,
            appointment_writes=0,
        )
        if persist:
            await session.commit()
        return result

    # ---- "produces PENDING_CONFIRMATION" ----
    appointment_id = new_id("APT")
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
                # `booked_at` anchors D9's 15-minute TTL, which starts now -- at the point the
                # request reaches a planner -- not 90 seconds ago when the hold was taken. The
                # driver's deliberation time is not deducted from the planner's clock.
                "booked_at": now,
                "updated_at": now,
            },
        )
        # The hold becomes the booking: same row, same interval, no gap. `state = 'HELD'` in the
        # WHERE is the second half of the race guard -- if the sweeper committed between the
        # locking SELECT and here (it cannot, we hold the lock, but the predicate costs nothing and
        # documents the invariant), this updates zero rows and the check below refuses.
        flipped = (
            await session.execute(
                text(
                    """
                    UPDATE public.dock_occupancy
                    SET state = 'PENDING_CONFIRMATION',
                        appointment_id = :appointment_id,
                        expires_at = NULL
                    WHERE occupancy_id = :hold_id
                      AND state = 'HELD'
                    RETURNING occupancy_id
                    """
                ),
                {"appointment_id": appointment_id, "hold_id": hold["occupancy_id"]},
            )
        ).first()
        if flipped is None:
            # Deliberately loud, exactly as `request_slot` is when its claim insert returns
            # nothing: committing an appointment whose interval is not actually claimed is the one
            # failure mode `dock_occupancy` exists to prevent.
            raise AppError(
                "Could not convert the hold into a capacity claim.",
                code="HOLD_CONVERSION_FAILED",
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
                "action_type": AUDIT_ACTION_CONFIRM_HOLD,
                "entity_id": appointment_id,
                "old_value_json": json.dumps(
                    {"state": "HELD", "hold_id": str(hold["occupancy_id"])}
                ),
                "new_value_json": json.dumps(
                    {
                        "status": "PENDING_CONFIRMATION",
                        "hold_id": str(hold["occupancy_id"]),
                        "shipment_id": shipment_id,
                        "slot_id": slot_id,
                        "dock_id": hold["dock_id"],
                        "policy_version": constraints.policy_version,
                        "held_policy_version": hold["policy_version"],
                        "note": note,
                    },
                    default=str,
                ),
                "created_at": now.isoformat(),
            },
        )
        await session.flush()
    except IntegrityError as exc:
        constraint_name = allocation.allocation_unique_constraint_name(exc)
        if constraint_name is None:
            raise
        await session.rollback()
        # Reachable through `ux_current_active_appointment_per_shipment`: the driver acquired a
        # hold and then, inside the TTL, got an appointment for the same shipment by another route.
        # The hold is not released here -- the rollback already undid this transaction, and the
        # sweeper will retire the row on its TTL.
        return ConfirmHeldSlotResult(
            as_of=_as_of(),
            status="CONFLICTED",
            code="SLOT_CONFLICT_REFRESH_REQUIRED",
            hold_id=hold_id,
            shipment_id=shipment_id,
            slot_id=slot_id,
            policy_version=constraints.policy_version,
            conflict={
                "reason_code": "POSTGRES_UNIQUE_ALLOCATION_CONFLICT",
                "message": (
                    "PostgreSQL rejected the appointment because another active claim already "
                    f"holds this capacity (constraint {constraint_name})."
                ),
            },
            idempotency_key=idempotency_key,
            appointment_writes=0,
        )

    appointment = await allocation._reread_appointment(session, appointment_id)
    result = ConfirmHeldSlotResult(
        as_of=_as_of(),
        status="PENDING_CONFIRMATION",
        code="SLOT_REQUESTED",
        hold_id=hold_id,
        shipment_id=shipment_id,
        slot_id=slot_id,
        appointment_id=appointment_id,
        appointment=appointment,
        policy_version=constraints.policy_version,
        idempotency_key=idempotency_key,
        appointment_writes=1,
    )
    await allocation._store_request_idempotency(
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
        result.appointment = await allocation._reread_appointment(session, appointment_id)
    result.idempotent_replay = False
    return result


# ------------------------------------------------------------------------------------------
# The M8 sweeper's HELD leg -- D2's 90-second TTL
# ------------------------------------------------------------------------------------------


async def _expire_hold_row(
    session: AsyncSession,
    *,
    hold_id: int,
    actor_user_id: str,
    now: datetime,
    reason: str,
) -> bool:
    """Flip one hold to EXPIRED in place, with an audit row. Caller commits.

    In place rather than DELETE, which is what section 0.8's partial exclusion predicate buys: an
    `EXPIRED` row drops out of `WHERE (state IN (...))` and so stops blocking capacity, while
    remaining readable as evidence that the hold existed and lapsed. Deleting it would release the
    capacity just as effectively and leave nothing behind -- and M14 wants every state change
    reconstructable.
    """
    flipped = (
        await session.execute(
            text(
                """
                UPDATE public.dock_occupancy
                SET state = 'EXPIRED', expires_at = NULL
                WHERE occupancy_id = :hold_id
                  AND state = 'HELD'
                RETURNING occupancy_id, dock_id, shipment_id
                """
            ),
            {"hold_id": hold_id},
        )
    ).mappings().first()
    if flipped is None:
        return False
    await session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id,
              old_value_json, new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :user_id, :action_type, 'dock_occupancy', :entity_id,
              :old_value_json, :new_value_json, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": new_id("AUD"),
            "user_id": actor_user_id,
            "action_type": AUDIT_ACTION_EXPIRE_HOLD,
            "entity_id": str(hold_id),
            "old_value_json": json.dumps({"state": "HELD"}),
            "new_value_json": json.dumps(
                {
                    "state": "EXPIRED",
                    "reason": reason,
                    "dock_id": flipped["dock_id"],
                    "shipment_id": flipped["shipment_id"],
                }
            ),
            "created_at": now.isoformat(),
        },
    )
    return True


HELD_EXPIRY_REASON = "HELD reservation lapsed unconfirmed (D2, 90-second TTL)"

# Issue #97's lazy leg. Same transition, different discoverer: the sweeper finds a lapsed hold on a
# schedule, this finds one because it is standing in the way of a claim right now.
LAZY_EXPIRY_REASON = (
    "HELD reservation lapsed unconfirmed (D2, 90-second TTL); expired lazily by a competing claim "
    "on the same dock interval because the sweeper had not reached it"
)
# Issue #98's leg. Third discoverer of the same transition: a planner displacement read found the
# dead hold standing in the way of an appointment it was about to be refused for. Recorded
# separately from `LAZY_EXPIRY_REASON` because "who noticed" is genuinely different -- a reader,
# not a claimant -- and M14 wants a state change reconstructable from the audit row alone.
LAZY_EXPIRY_ON_READ_REASON = (
    "HELD reservation lapsed unconfirmed (D2, 90-second TTL); expired lazily by a planner "
    "displacement read over the same dock interval because the sweeper had not reached it"
)
ACTOR_EXPIRY_SWEEPER = "EXPIRY_SWEEPER"
ACTOR_LAZY_CLAIM = "LAZY_EXPIRY_ON_CLAIM"
ACTOR_LAZY_DISPLACEMENT_READ = "LAZY_EXPIRY_ON_DISPLACEMENT_READ"


async def _audit_hold_expiries(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    *,
    actor_user_id: str,
    now: datetime,
    reason: str,
    actor: str,
) -> None:
    """One `EXPIRE_HOLD` audit row per hold flipped, for whichever path did the flipping.

    Extracted from `sweep_held_holds` so the sweeper and `expire_lapsed_holds_on_interval` cannot
    drift in what they record. M14 wants every state change reconstructable, and "who noticed the
    hold was dead" is part of reconstructing it -- hence `actor`, which is the only field that
    differs between the two callers.

    `EXPIRE_HOLD` deliberately serves both. It is already in `audit_logs_action_type_check` (that
    CHECK admitted only thirteen non-hold action types until the D2 migration extended it, and a
    fourteenth value invented here would need a migration this change does not have); and the
    transition really is the same one, so giving it a second name would make an audit reader
    reconcile two vocabularies for one event.
    """
    for row in rows:
        await session.execute(
            text(
                """
                INSERT INTO public.audit_logs (
                  audit_id, user_id, action_type, entity_name, entity_id,
                  old_value_json, new_value_json, ip_address, user_agent, created_at
                ) VALUES (
                  :audit_id, :user_id, :action_type, 'dock_occupancy', :entity_id,
                  :old_value_json, :new_value_json, NULL, NULL, :created_at
                )
                """
            ),
            {
                "audit_id": new_id("AUD"),
                "user_id": actor_user_id,
                "action_type": AUDIT_ACTION_EXPIRE_HOLD,
                "entity_id": str(row["occupancy_id"]),
                "old_value_json": json.dumps({"state": "HELD"}),
                "new_value_json": json.dumps(
                    {
                        "state": "EXPIRED",
                        "reason": reason,
                        "actor": actor,
                        "dock_id": row["dock_id"],
                        "shipment_id": row["shipment_id"],
                    }
                ),
                # `audit_logs.created_at` is still `text` (never converted by E1.1), so it takes the
                # ISO string -- see `create_hold`'s bind-type note.
                "created_at": now.isoformat(),
            },
        )


async def _flip_lapsed_holds(
    session: AsyncSession,
    *,
    statement: str,
    params: dict[str, Any],
    now: datetime,
    actor_user_id: str,
    reason: str,
    actor: str,
    log_subject: str,
) -> list[int]:
    """Run one lapsed-hold UPDATE and audit whatever it flipped. Caller commits.

    **The shared core of every lazy-expiry variant** (issues #97 and #98). Only the `WHERE` that
    selects *which* dead holds are in the way differs between callers -- the flip itself, the audit
    row, the CHECK-satisfying `expires_at = NULL`, and the log line are identical, and issue #98's
    whole premise is that a second copy of this transition is how two paths drift apart. Every
    caller's `statement` must therefore end in
    `RETURNING o.occupancy_id, o.dock_id, o.shipment_id` and must carry
    `state = 'HELD' AND expires_at <= :now`; nothing here re-checks that, because a variant that
    dropped either predicate would be expiring holds somebody could still use.

    `UPDATE ... FROM` is used by both variants and can join a target row to more than one driving
    row. PostgreSQL's own wording (`SQL-UPDATE`, "FROM clause"): *"If it does, then only one of the
    join rows will be used to update the target row, but which one will be used is not readily
    predictable."* That ambiguity is harmless here and deliberately so -- no `SET` expression reads
    a column from the driving side, so every candidate join row would produce the identical update.
    Each target row is still updated at most once, so `RETURNING` yields one row per flipped hold
    and `_audit_hold_expiries` writes exactly one audit row per hold.
    """
    rows = (await session.execute(text(statement), params)).mappings().all()
    if not rows:
        return []
    flipped = [dict(row) for row in rows]
    await _audit_hold_expiries(
        session, flipped, actor_user_id=actor_user_id, now=now, reason=reason, actor=actor
    )
    logger.info(
        "lazily expired %d lapsed hold(s) blocking %s: %s",
        len(flipped),
        log_subject,
        [row["occupancy_id"] for row in flipped],
    )
    return [int(row["occupancy_id"]) for row in flipped]


async def expire_lapsed_holds_for_appointments(
    session: AsyncSession,
    *,
    appointment_ids: list[str],
    now: datetime,
    actor_user_id: str,
) -> list[int]:
    """Flip every lapsed HELD row overlapping these appointments' own intervals. Caller commits.

    **Issue #98 -- the displacement-read half of the same problem `expire_lapsed_holds_on_interval`
    solves for the claim path.** `snapshot.load_appointment_snapshots` and
    `planner_service.get_planner_queue` both answer *"what would PostgreSQL refuse?"*, so both
    deliberately omit the `expires_at > now()` term (`repositories/operations.py
    ::list_live_dock_occupancy` argues that at length, and #84 is why). After issue #97 gave the
    claim path a lazy-expiry leg, that reasoning was only half-true: the constraint still has no
    time term, but the write path effectively acquired one -- so a planner could be refused with
    `DISPLACEMENT_DETECTED` by a hold the very next claim would silently expire, and with no
    sweeper running (issue #20) the refusal never cleared.

    Owner decision (b) on #98: rather than teaching the reads to *ignore* lapsed holds -- which
    would reopen the gap between what the reads see and what the constraint sees that #84 exists to
    close -- make the table tell the truth first. After this runs the constraint genuinely does not
    count those rows, so "the recomputation sees exactly what the exclusion constraint sees" stays
    literally true rather than becoming an approximation.

    ## The interval, and why it is not the published slot window

    The `target` CTE below is `snapshot._SNAPSHOT_SQL`'s own `target` CTE, minus the columns this
    statement does not need. It must stay that way: `dock_occupancy`'s claim when the appointment
    has one, otherwise slot start + `expected_unload_min` + the flat changeover buffer -- D1 (§0.9)
    makes `dock_occupancy` the authority and `appointment_slots` cannot see a 75-minute unload
    booked into a 60-minute slot (§6.2 #1). `repositories/operations.list_planner_queue_rows`
    computes the same expression for the same reason, which is what lets one statement serve both
    the write-path recomputation and the queue read.

    `LEFT JOIN LATERAL ... LIMIT 1` rather than a plain join, copied from the same place: the D1
    EXCLUDE constraint is on `(dock_id, window)`, so nothing stops one appointment holding claims
    on two docks and a plain join would fan the target row out.

    Returns the `occupancy_id`s flipped; an empty list is the overwhelmingly common case and costs
    one statement.
    """
    if not appointment_ids:
        return []
    return await _flip_lapsed_holds(
        session,
        statement="""
            WITH target AS (
              SELECT sl.dock_id,
                     COALESCE(occ.window_start, sl.slot_start_ts) AS interval_start,
                     COALESCE(
                         occ.window_end,
                         sl.slot_start_ts + ((s.expected_unload_min + 15) || ' minutes')::interval
                     ) AS interval_end
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                JOIN public.shipments s ON s.shipment_id = a.shipment_id
                LEFT JOIN LATERAL (
                    SELECT lower(o."window") AS window_start, upper(o."window") AS window_end
                      FROM public.dock_occupancy o
                     WHERE o.appointment_id = a.appointment_id
                     ORDER BY o.occupancy_id ASC
                     LIMIT 1
                ) occ ON true
               WHERE a.appointment_id = ANY(:appointment_ids)
            )
            UPDATE public.dock_occupancy o
            SET state = 'EXPIRED', expires_at = NULL
            FROM target t
            WHERE o.dock_id = t.dock_id
              AND o.state = 'HELD'
              AND o.expires_at <= :now
              AND o."window" && tstzrange(t.interval_start, t.interval_end, '[)')
            RETURNING o.occupancy_id, o.dock_id, o.shipment_id
        """,
        params={"appointment_ids": list(appointment_ids), "now": now},
        now=now,
        actor_user_id=actor_user_id,
        reason=LAZY_EXPIRY_ON_READ_REASON,
        actor=ACTOR_LAZY_DISPLACEMENT_READ,
        log_subject=f"{len(appointment_ids)} appointment interval(s)",
    )


async def expire_lapsed_holds_on_interval(
    session: AsyncSession,
    *,
    slot_id: str,
    shipment_id: str,
    now: datetime,
    actor_user_id: str,
) -> list[int]:
    """Flip every lapsed HELD row that would collide with a claim on this slot. Caller commits.

    **This is the write half of issue #97's shared predicate** -- see `occupancy.py` for the whole
    argument. In one sentence: the exclusion constraint's predicate has no time term and cannot
    have one, so a `HELD` row whose TTL passed goes on refusing overlapping inserts until something
    writes to it. §0.8 says a lapsed hold is not a live promise; the constraint says it is. This
    makes the table agree with §0.8 immediately before the claim, inside the claiming transaction,
    instead of waiting for a sweeper that may be hours away or (as of 2026-09-01) not running at
    all -- the EventBridge wiring is still open on issue #20.

    ## Why this cannot steal a hold somebody could still have used

    The `expires_at <= :now` predicate is the same line `confirm_held_slot` already draws.
    `_locked_hold` requires `expires_at > :now`, so any row this function is able to touch was
    *already* unconfirmable by its owner before this ran -- §0.8's lazy-expiry rule, which this
    module's docstring calls the first line of defence. Expiring it changes what PostgreSQL will
    admit; it does not change any promise anybody still held.

    ## Why the minimal flip is the complete flip

    Checked against `sweep_held_holds` below rather than assumed. The sweeper's HELD leg does
    exactly three things: `state='EXPIRED'`, `expires_at=NULL`, and one `EXPIRE_HOLD` audit row per
    row. It deliberately raises **no** escalation (a hold lapsing is the designed outcome of a
    driver not choosing in time, not an operational failure -- see its own closing comment) and
    releases nothing else, because under §4 a hold *is* a `dock_occupancy` row and nothing else:
    no appointment, no slot mutation, no notification. So there is no fourth thing for this path to
    mirror, and it reuses `_flip_lapsed_holds` (which reuses `_audit_hold_expiries`) for the third
    rather than re-writing it.

    `expires_at = NULL` is not tidiness: `dock_occupancy_held_shape_check` is
    `(state='HELD' AND expires_at IS NOT NULL AND appointment_id IS NULL) OR (state<>'HELD' AND
    expires_at IS NULL)`, so flipping the state while leaving the deadline behind violates the
    CHECK and aborts the claiming transaction.

    The sweeper stays correct after this runs, and idempotently so: its inner SELECT carries
    `state = 'HELD'`, so a row this function already expired no longer matches, is not returned,
    and produces no second audit row. Same guard that makes an EventBridge retry a no-op.

    ## Concurrency

    No `SKIP LOCKED`, unlike the sweeper -- this is a user-facing path and the asymmetry is the one
    `expiry.py` documents for the D9 pair. Two claimants racing for the same dead hold both try to
    lock it; the loser blocks, then re-evaluates `state = 'HELD'` against the committed version
    (READ COMMITTED, PostgreSQL "Transaction Isolation" 13.2.1) and updates zero rows. Both then
    reach the INSERT and the exclusion constraint admits exactly one, which is M6's guarantee
    unchanged -- this function widens what may be claimed, never who wins.

    Since issue #98 a *reader* can be the other party in that race
    (`expire_lapsed_holds_for_appointments`, called from the displacement paths). It resolves the
    same way and adds no new lock-ordering risk: both variants take appointment-row locks first
    (their callers' `SELECT ... FOR UPDATE`) and `dock_occupancy` row locks second, so every path
    that touches both tables acquires them in the same order. `confirm_held_slot` is the one path
    that locks `dock_occupancy` first, and it goes on to *insert* an appointment rather than lock
    an existing one, so it closes no cycle.

    Returns the `occupancy_id`s flipped, so the caller can log or assert on them. An empty list is
    the overwhelmingly common case and costs one indexed statement.
    """
    return await _flip_lapsed_holds(
        session,
        statement=f"""
            UPDATE public.dock_occupancy o
            SET state = 'EXPIRED', expires_at = NULL
            FROM public.appointment_slots sl
            JOIN public.shipments s ON s.shipment_id = :shipment_id
            WHERE sl.slot_id = :slot_id
              AND o.dock_id = sl.dock_id
              AND o.state = 'HELD'
              AND o.expires_at <= :now
              AND o."window" && {claim_window_sql(
                  start_expr="sl.slot_start_ts",
                  unload_min_expr="s.expected_unload_min",
              )}
            RETURNING o.occupancy_id, o.dock_id, o.shipment_id
        """,
        params={"slot_id": slot_id, "shipment_id": shipment_id, "now": now},
        now=now,
        actor_user_id=actor_user_id,
        reason=LAZY_EXPIRY_REASON,
        actor=ACTOR_LAZY_CLAIM,
        log_subject=f"slot {slot_id}",
    )


async def sweep_held_holds(
    session: AsyncSession,
    *,
    actor_user_id: str,
    now: datetime,
    ttl_seconds: int,
    batch_limit: int = 50,
    enabled: bool = True,
) -> HeldSweepResult:
    """D2's 90-second HELD sweep. Hygiene, never correctness.

    Section 0.8 is explicit that this is the *second* line of defence: *"Every read filters
    `state='HELD' AND expires_at > now()`; a sweeper transitions stale rows to `EXPIRED`. Never
    depend on the sweeper for correctness -- only for hygiene."* `_locked_hold` implements the
    first line. If this function never ran, no lapsed hold could ever be confirmed; the table would
    merely accumulate rows that look like live capacity to anything reading `state` alone.

    `ttl_seconds` is *not* used to compute the deadline -- `expires_at` was stamped at hold time
    and is the authority, so a config change cannot retroactively lengthen or shorten a hold a
    driver was already promised. It is carried in the result for observability only.

    Commits are the caller's. Unlike the D9 leg (one appointment per transaction, because each is
    an independent decision that must not be undone by a neighbour), the whole HELD batch is one
    statement: it is a single set-based UPDATE, so there is no partial-batch state to protect.
    """
    if not enabled:
        return HeldSweepResult(
            supported=False,
            expired=0,
            ttl_seconds=ttl_seconds,
            unsupported_reason=HELD_SWEEP_DISABLED_REASON,
        )

    limit = max(1, batch_limit)
    # The claim-and-update-in-one-statement queue pattern: the inner SELECT takes the row locks
    # with SKIP LOCKED and the outer UPDATE flips exactly those rows, so two sweeper invocations
    # overlapping in time cannot fight over the same hold. `state = 'HELD'` in the inner WHERE is
    # the race guard against a driver's in-flight `confirm_held_slot` (module docstring).
    rows = (
        await session.execute(
            text(
                """
                UPDATE public.dock_occupancy
                SET state = 'EXPIRED', expires_at = NULL
                WHERE occupancy_id IN (
                    SELECT occupancy_id
                    FROM public.dock_occupancy
                    WHERE state = 'HELD'
                      AND expires_at <= :now
                    ORDER BY expires_at ASC
                    LIMIT :limit
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING occupancy_id, dock_id, shipment_id
                """
            ),
            {"now": now, "limit": limit},
        )
    ).mappings().all()

    expired = [
        ExpiredHold(
            hold_id=str(row["occupancy_id"]),
            dock_id=str(row["dock_id"]),
            shipment_id=str(row["shipment_id"]),
        )
        for row in rows
    ]
    # Shared with `expire_lapsed_holds_on_interval` (issue #97) so the scheduled and the lazy
    # discoverer of a lapsed hold record the identical transition, differing only in `actor`.
    await _audit_hold_expiries(
        session,
        [dict(row) for row in rows],
        actor_user_id=actor_user_id,
        now=now,
        reason=HELD_EXPIRY_REASON,
        actor=ACTOR_EXPIRY_SWEEPER,
    )

    # #94: the "that hold lapsed, here are current options" message section 0.8 promises --
    # one outbox row per lapsed hold, same transaction as the flip. A HELD row has no
    # appointment (section 4), so the shipment is the routing key.
    for row in rows:
        await notification_outbox.enqueue_notification(
            session,
            event_type=notification_outbox.HOLD_LAPSED,
            shipment_id=str(row["shipment_id"]) if row.get("shipment_id") else None,
        )

    # Deliberately no escalation_queue row per lapsed hold, unlike the D9 leg's
    # PENDING_EXPIRED_UNACTIONED. A hold lapsing is the *designed* outcome of a driver not choosing
    # within 90 seconds (section 0.8: "a driver on a bad connection who misses the window gets a
    # clear 'that hold lapsed, here are current options' message"), not an operational failure
    # anyone must action. Raising an escalation for each would bury the D9 escalations that do
    # need a human.
    return HeldSweepResult(
        supported=True,
        expired=len(expired),
        ttl_seconds=ttl_seconds,
        candidates=len(expired),
        deferred_or_lost=0,
        batch_limit_reached=len(expired) >= limit,
        holds=expired,
    )
