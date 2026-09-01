"""The M8 expiry sweeper -- D2's HELD TTL and D9's PENDING_CONFIRMATION TTL.

Design citation: `SOLUTION_DESIGN.md` M8 / D2 / D9 / section 7.5.1 (the race resolution) / section
9.2 #3 (`pending_expiry_vs_planner_confirm`); `TECH-STACK/TECH_STACK.md` section 5.

Why this module exists rather than more lines in `allocation.py`: `allocation.py` owns transitions
driven by an *authenticated identity*, and every one of its paths starts from an `ExecutionContext`.
The sweeper has no identity -- it is a scheduled machine caller -- and it needs
`FOR UPDATE ... SKIP LOCKED` semantics that a user-facing path must never have (a driver whose
confirm silently no-ops because a row was locked would be a bug; a sweeper that defers a locked row
to the next minute is correct). Both facts make it a different shape of caller, not a variation on
the existing one. What it does *not* re-invent is the capacity release: it calls
`allocation._release_dock_occupancy` through the module object, so there is exactly one release
mechanism and E1.3's cancel/reject/expire paths and this one cannot drift apart.

## The race, and why the SQL below is the whole of the fix

section 9.2 #3 is "the nastiest race in the design" -- the D9 sweeper firing as a planner clicks
Confirm, both actors believing they acted. section 7.5.1's resolution: *"the sweeper's transition and
the confirm both take the row under the same transaction, exactly one commits, and the loser gets
`ALREADY_ACTIONED` with the winning transition named."*

That resolution is delivered by PostgreSQL, not by application bookkeeping, and it rests on a
specific documented behaviour of READ COMMITTED (PostgreSQL "Transaction Isolation", 13.2.1):

> "If the first updater commits, the second updater will ignore the row if the first updater deleted
> it, otherwise it will attempt to apply its operation to the updated version of the row. The search
> condition of the command (the WHERE clause) is re-evaluated to see if the updated version of the
> row still matches the search condition. If so, the second updater proceeds with its operation
> using the updated version of the row. In the case of SELECT FOR UPDATE and SELECT FOR SHARE, this
> means it is the updated version of the row that is locked and returned to the client."

So the two directions resolve as follows, with no extra machinery:

* **Planner commits first.** The sweeper's locking `SELECT` carries
  `appointment_status = 'PENDING_CONFIRMATION'` in its own `WHERE`. Postgres re-evaluates that
  predicate against the *committed* version, which now says `CONFIRMED`, so the row is not returned
  and the sweeper does nothing at all. No compensating logic, no "undo the expiry".
* **Sweeper commits first.** `allocation._locked_appointment` (used by `confirm_appointment`)
  deliberately has *no* status predicate, so it locks and returns the updated row -- now `EXPIRED`.
  `confirm_appointment`'s status check then refuses with `ALREADY_ACTIONED` and names the winning
  transition read back out of `audit_logs`, which is the loser-facing half of section 7.5.1.

`SKIP LOCKED` covers the third case: the planner's transaction is still *open* when the sweeper
arrives. Blocking there would be correct but would burn the sweeper's request budget on a lock wait
(EventBridge API destinations time an invocation out at 5 seconds -- AWS EventBridge "API
destinations as targets"), so the row is left for the next cycle instead. At a 1-minute cadence
against a 15-minute TTL that is free.

## Idempotency under retry

EventBridge retries a failed API-destination invocation. This endpoint needs no `Idempotency-Key`
for that: the `appointment_status = 'PENDING_CONFIRMATION'` predicate *is* the guard. A replayed
sweep finds the rows it already expired no longer matching and does nothing. Adding a key would be
ceremony over a condition the SQL already enforces.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, resolve_clock
from app.core.errors import AppError
from app.scheduling import allocation
from app.scheduling.holds import HeldSweepResult, sweep_held_holds

__all__ = [
    "DEFAULT_BATCH_LIMIT",
    "DEFAULT_HELD_TTL_SECONDS",
    "DEFAULT_PENDING_TTL_MINUTES",
    "EXPIRY_REASON",
    "ExpiredAppointment",
    "HeldSweepResult",
    "SweepResult",
    "sweep_expired_appointments",
    "sweep_held_holds",
]

logger = logging.getLogger(__name__)

# D9: "Pending TTL = 15 min, then release + escalate" (SOLUTION_DESIGN.md section 0 locked
# decisions). The deadline is ordinarily *derived* as `booked_at + ttl` rather than stored.
#
# Issue #64 changed half of that: `public.appointments` now has an `expires_at` column
# (20260829134929_d2_held_state_dock_occupancy.sql step 7) so that section 7.5.1's
# `hold_for_information` ("pauses the D9 clock exactly once", returning a `new_deadline`) has
# somewhere honest to record an extension -- previously there was nowhere, and faking it by
# touching `booked_at` would have corrupted the request's own history. The *tool* is still not
# built; the column and this sweeper's handling of it are, so that the first writer of it inherits
# correct expiry behaviour instead of a column the sweeper silently ignores.
#
# The precedence rule, stated once here because it is the whole semantics of the column:
# `expires_at IS NOT NULL` overrides the derived deadline; NULL means the derived deadline applies.
DEFAULT_PENDING_TTL_MINUTES = 15
# D2: "Default TTL 90 s, per-facility configurable."
DEFAULT_HELD_TTL_SECONDS = 90
DEFAULT_BATCH_LIMIT = 50

EXPIRY_REASON = "PENDING_CONFIRMATION expired unactioned (D9, 15-minute TTL)"

# The D2 HELD leg moved to `app/scheduling/holds.py` when issue #53 gave the state a schema to live
# in. It is re-exported here because `HeldSweepResult` is part of this module's public surface (the
# `/internal/jobs/expiry-sweep` response embeds it) and callers should not have to know which of
# the two modules currently owns the implementation.


class ExpiredAppointment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appointment_id: str
    shipment_id: str
    slot_id: str
    facility_id: str | None = None
    booked_at: str | None = None
    occupancy_released: bool


class SweepResult(BaseModel):
    """What one sweeper cycle actually did. Every count is observable, including the no-ops."""

    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    pending_ttl_minutes: int
    pending_deadline: str
    pending_candidates: int = 0
    pending_expired: int = 0
    # A candidate that was still PENDING at scan time but was not expired: either another
    # transaction held its row lock (SKIP LOCKED deferred it to the next cycle) or it stopped being
    # PENDING between the two statements -- the planner won the race. Both are benign and both
    # self-heal, so they share one counter rather than paying a round trip to tell them apart.
    pending_deferred_or_lost: int = 0
    batch_limit: int
    batch_limit_reached: bool = False
    expired: list[ExpiredAppointment] = Field(default_factory=list)
    held: HeldSweepResult


async def _assert_actor_exists(session: AsyncSession, actor_user_id: str) -> None:
    """Fail the whole sweep before it writes anything if the audit actor is not a real user.

    `audit_logs.user_id` is `NOT NULL REFERENCES users(user_id)` (verified live 2026-08-23), so a
    misconfigured actor would surface as an FK IntegrityError *after* the appointment UPDATE and the
    occupancy DELETE, aborting a transaction that had already done real work. Checking once up front
    turns that into one clear refusal. It is one extra query per minute.
    """
    exists = (
        await session.execute(
            text("SELECT 1 FROM public.users WHERE user_id = :user_id AND is_active = 1"),
            {"user_id": actor_user_id},
        )
    ).first()
    if exists is None:
        raise AppError(
            "Configured sweeper actor is not an active application user; refusing to sweep. "
            "JOB_ACTOR_USER_ID must name a row in public.users, because audit_logs.user_id is a "
            "NOT NULL foreign key and SOLUTION_DESIGN.md section 7.5.1 requires the audit trail to "
            "name who applied the expiring transition.",
            code="SWEEPER_ACTOR_INVALID",
            status_code=503,
        )


async def _pending_candidates(
    session: AsyncSession,
    *,
    deadline: datetime,
    now: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    """Unlocked scan for rows past the D9 deadline. Cheap, bounded, and only a hint.

    Nothing here is trusted: every id is re-checked under a row lock below. Reading candidates
    without a lock first keeps the locking statements short and lets the batch be bounded before any
    lock is taken, which is what keeps the whole cycle inside EventBridge's 5-second invocation
    timeout.

    Two deadlines, one predicate (issue #64). A request whose `expires_at` a planner extended
    through `hold_for_information` is due at *that* instant; every other request is due at
    `booked_at + ttl`. The CASE picks per row rather than the caller picking per sweep, because a
    single batch will routinely contain both kinds. Today no code writes `expires_at`, so the ELSE
    branch is taken for 100% of rows and this scan is behaviourally identical to the pre-#64 one --
    the column is wired up before its writer exists specifically so that it is not a trap for
    whoever builds that writer.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.shipment_id, a.slot_id, a.booked_at, a.expires_at,
                       sl.facility_id
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                WHERE a.appointment_status = 'PENDING_CONFIRMATION'
                  AND a.is_current = 1
                  AND CASE
                        WHEN a.expires_at IS NOT NULL THEN a.expires_at < :now
                        ELSE a.booked_at < :deadline
                      END
                ORDER BY COALESCE(a.expires_at, a.booked_at) ASC
                LIMIT :limit
                """
            ),
            {"deadline": deadline, "now": now, "limit": limit},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _expire_one_pending(
    session: AsyncSession,
    *,
    appointment_id: str,
    actor_user_id: str,
    now: datetime,
) -> bool | None:
    """Expire exactly one PENDING appointment, or return None without writing anything.

    Returns whether a `dock_occupancy` claim was actually released, or `None` when the row was not
    actioned at all (lock held, or no longer PENDING). Three-valued because "expired but held no
    claim" is a real and legitimate state -- see the caller's note on the E1.1 backfill.

    The whole race resolution of section 7.5.1 is the `WHERE` clause of the first statement. See this
    module's docstring for why: under READ COMMITTED, Postgres re-evaluates that predicate against
    the version a competing committed transaction left behind, so a planner who confirmed first
    makes this `SELECT` return nothing and this function a no-op. `SKIP LOCKED` handles the planner
    whose transaction is still open.

    Caller commits. One appointment per transaction, so a single problem row cannot roll back the
    rest of the batch.
    """
    locked = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.shipment_id, a.slot_id, a.appointment_status,
                       a.is_current, sl.facility_id
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                WHERE a.appointment_id = :appointment_id
                  AND a.appointment_status = 'PENDING_CONFIRMATION'
                  AND a.is_current = 1
                FOR UPDATE SKIP LOCKED
                """
            ),
            {"appointment_id": appointment_id},
        )
    ).mappings().first()
    if locked is None:
        return None

    # Bind types are not interchangeable here, and getting them wrong is a hard runtime failure
    # rather than a silent coercion. `appointments.updated_at` is `timestamptz` after E1.1's
    # conversion, and asyncpg 0.31.0 encodes a timestamptz parameter with its datetime codec:
    # handing it a `str` raises `asyncpg.exceptions.DataError: invalid input for query argument $1
    # ... (expected a datetime.date or datetime.datetime instance, got 'str')`. Verified live
    # 2026-08-23 against this database. `audit_logs.created_at` below is the opposite case -- still
    # `text`, never converted -- so it takes the ISO string. Same instant, two representations, on
    # purpose.
    now_iso = now.isoformat()
    await session.execute(
        text(
            """
            UPDATE public.appointments
            SET appointment_status = 'EXPIRED',
                is_current = 0,
                cancellation_reason = :reason,
                updated_at = :updated_at
            WHERE appointment_id = :appointment_id
            """
        ),
        {
            "appointment_id": appointment_id,
            "reason": EXPIRY_REASON,
            "updated_at": now,
        },
    )
    # Same transaction as the status change, and through the same function cancel/reject/the ops
    # expire path already use. D9's "release + escalate" is a release of *capacity*: the shipped
    # dock_occupancy has no state column, so deleting the claim is the only release there is, and
    # skipping it would leave an EXPIRED appointment blocking its dock interval forever while
    # find_feasible_slots kept offering the ghost slot (see allocation._release_dock_occupancy).
    released = await allocation._release_dock_occupancy(session, appointment_id)
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
            "audit_id": allocation.new_id("AUD"),
            "user_id": actor_user_id,
            "action_type": allocation.AUDIT_ACTION_EXPIRE_APPOINTMENT,
            "entity_id": appointment_id,
            "old_value_json": json.dumps({"status": "PENDING_CONFIRMATION", "is_current": 1}),
            # `actor` is what makes the audit trail answer section 7.5.1's "the audit log must show
            # which won and why" for a planner who clicked Confirm and saw the slot vanish: the row
            # says the sweeper did it, and why.
            "new_value_json": json.dumps(
                {
                    "status": "EXPIRED",
                    "is_current": 0,
                    "reason": EXPIRY_REASON,
                    "actor": "EXPIRY_SWEEPER",
                    "occupancy_released": released,
                }
            ),
            "created_at": now_iso,
        },
    )
    # M8's "escalates" leg (SOLUTION_DESIGN.md section 7.4, PENDING_EXPIRED_UNACTIONED): a
    # pending appointment nobody actioned before its TTL is an escalation-worthy event in its
    # own right, not just a status change nobody sees. Same table, same reasoning as E1.2's
    # REQUIRES_TIME_RESOLUTION/REQUIRES_DOCK_REASSIGNMENT reuse -- one durable, planner-facing
    # queue, not a second mechanism to keep in sync. The `DO NOTHING` upsert below
    # makes this safe under the same EventBridge-retry story as the rest of this function: a
    # replayed sweep finds the appointment no longer PENDING_CONFIRMATION and never reaches
    # this insert at all, so the dedupe key is a second, belt-and-braces guard, not the only one.
    await session.execute(
        text(
            """
            INSERT INTO public.escalation_queue (
              escalation_id, shipment_id, facility_id, escalation_type, escalation_status,
              severity_code, payload_json, dedupe_key, created_at, updated_at
            ) VALUES (
              :escalation_id, :shipment_id, :facility_id, 'PENDING_EXPIRED_UNACTIONED', 'OPEN',
              'HIGH', :payload_json, :dedupe_key, :created_at, :updated_at
            )
            -- Issue #96: the predicate is an ON CONFLICT index_predicate and must stay
            -- byte-identical to `escalation_queue_dedupe_key_active_uidx`'s (migration
            -- 20260901120000). Without it PostgreSQL cannot infer the now-partial unique index
            -- and every sweep raises 42P10 -- a silent, total break of the M8 escalate leg, not a
            -- degraded one. Behaviourally: if this appointment's earlier
            -- PENDING_EXPIRED_UNACTIONED case was already resolved, a later sweep opens a new one
            -- instead of being swallowed. That is the intended #96 semantics and is unreachable
            -- in practice anyway -- the guard above means a replayed sweep finds the appointment
            -- no longer PENDING_CONFIRMATION and never gets here.
            ON CONFLICT (dedupe_key) WHERE escalation_status NOT IN ('RESOLVED', 'CANCELLED')
            DO NOTHING
            """
        ),
        {
            "escalation_id": allocation.new_id("ESC"),
            "shipment_id": locked["shipment_id"],
            "facility_id": locked["facility_id"],
            "payload_json": json.dumps(
                {
                    "appointment_id": appointment_id,
                    "slot_id": locked["slot_id"],
                    "reason": EXPIRY_REASON,
                    "occupancy_released": released,
                }
            ),
            "dedupe_key": f"PENDING-EXPIRED-{appointment_id}",
            "created_at": now_iso,
            "updated_at": now_iso,
        },
    )
    return released


async def sweep_expired_appointments(
    session: AsyncSession,
    *,
    actor_user_id: str,
    clock: Clock | None = None,
    pending_ttl_minutes: int = DEFAULT_PENDING_TTL_MINUTES,
    held_ttl_seconds: int = DEFAULT_HELD_TTL_SECONDS,
    batch_limit: int = DEFAULT_BATCH_LIMIT,
    held_enabled: bool = False,
) -> SweepResult:
    """One sweeper cycle. M8's "pending expiry releases capacity", D9's 15-minute TTL.

    `clock` is the section 9.1 injected clock and is the only source of `now` in here -- pass a
    `FrozenClock` to make section 9.2 #3 reproducible instead of relying on timing luck. It is a
    keyword argument rather than a module global on purpose (see `app/core/clock.py`).

    Commits per appointment. That is deliberate: the sweeper is a batch of independent decisions, and
    one row that cannot be expired must not undo the releases that already succeeded.
    """
    resolved_clock = resolve_clock(clock)
    now = resolved_clock.now()
    deadline = now - timedelta(minutes=pending_ttl_minutes)
    limit = max(1, batch_limit)

    await _assert_actor_exists(session, actor_user_id)

    candidates = await _pending_candidates(session, deadline=deadline, now=now, limit=limit)
    expired: list[ExpiredAppointment] = []
    deferred_or_lost = 0
    for candidate in candidates:
        appointment_id = str(candidate["appointment_id"])
        released = await _expire_one_pending(
            session,
            appointment_id=appointment_id,
            actor_user_id=actor_user_id,
            now=now,
        )
        if released is None:
            # Nothing was written, but the lock this transaction may still hold has to go before the
            # next candidate opens a new one.
            await session.rollback()
            deferred_or_lost += 1
            continue
        await session.commit()
        expired.append(
            ExpiredAppointment(
                appointment_id=appointment_id,
                shipment_id=str(candidate["shipment_id"]),
                slot_id=str(candidate["slot_id"]),
                facility_id=(
                    str(candidate["facility_id"]) if candidate.get("facility_id") else None
                ),
                booked_at=(
                    candidate["booked_at"].isoformat()
                    if isinstance(candidate.get("booked_at"), datetime)
                    else (str(candidate["booked_at"]) if candidate.get("booked_at") else None)
                ),
                # `_release_dock_occupancy` returns False for an appointment that never held a
                # claim -- the E1.1 backfill escalated 42 genuinely overlapping appointments to the
                # D12 worklist instead of claiming for them, so this is legitimately False
                # sometimes and is recorded rather than assumed.
                occupancy_released=released,
            )
        )

    result = SweepResult(
        as_of=now.isoformat(),
        pending_ttl_minutes=pending_ttl_minutes,
        pending_deadline=deadline.isoformat(),
        pending_candidates=len(candidates),
        pending_expired=len(expired),
        pending_deferred_or_lost=deferred_or_lost,
        batch_limit=limit,
        # A full batch means there is very likely more work waiting. At a 1-minute cadence the next
        # cycle picks it up; surfacing the flag is what makes a persistent backlog visible instead
        # of looking like a healthy sweep.
        batch_limit_reached=len(candidates) >= limit,
        expired=expired,
        # D2's HELD leg, after the D9 work rather than before it. Ordering is not arbitrary: a
        # lapsed hold blocks strictly less capacity than a sterilised PENDING row (90 seconds
        # against 15 minutes), so if a cycle runs out of EventBridge's 5-second budget it should
        # run out on the cheaper half. Its own transaction commits below, separately from the
        # per-appointment commits above.
        held=await sweep_held_holds(
            session,
            actor_user_id=actor_user_id,
            now=now,
            ttl_seconds=held_ttl_seconds,
            batch_limit=limit,
            enabled=held_enabled,
        ),
    )
    if result.held.expired:
        await session.commit()
    logger.info(
        "expiry sweep: candidates=%d expired=%d deferred_or_lost=%d batch_limit_reached=%s "
        "held_supported=%s held_expired=%d",
        result.pending_candidates,
        result.pending_expired,
        result.pending_deferred_or_lost,
        result.batch_limit_reached,
        result.held.supported,
        result.held.expired,
    )
    return result
