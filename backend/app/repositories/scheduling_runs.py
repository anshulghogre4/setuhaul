"""Persistence for `public.scheduling_runs` -- the D5 proposal artifact (issue #49).

Design citation: `SOLUTION_DESIGN.md` D5 (*"Sequencer output is a reviewable artifact
(`scheduling_runs`), never a silent write"*), section 5 Stage 4 (*"Persist every run in
`scheduling_runs` (input snapshot, proposal, objective values, explanation) so a proposal can be
reviewed and replayed"*), section 5.1's debounce rule (*"allow at most one active run per facility
(serialised)"*), section 7.5.3's three-tool table.
Requirements: `ARCHITECTURE/REQUIREMENTS.md` FR-SYS-016, FR-SYS-042, FR-PLN-009, FR-OPS-004.

A repository, not a service, per `AGENTS.md` (*"FastAPI routers stay thin. Business rules belong in
services; persistence belongs in repositories"*). Every function here is SQL and row-shaping only:
**nothing in this module decides scope, feasibility, or lifecycle legality.** `scheduling/
sequencer.py` owns all three, the same split `repositories/operations.py` and `services/
planner_service.py` already use.

## The two rules a caller cannot get wrong from here

1. **`insert_proposed_run` repeats the partial index's predicate** in its `ON CONFLICT`. PostgreSQL
   infers the arbiter index from the conflict target and *"index_predicate: used to allow inference
   of partial unique indexes"* (postgresql.org/docs/current/sql-insert.html, ON CONFLICT Clause --
   checked 2026-09-02 against PostgreSQL 18, the version the proof cluster runs). A bare
   `ON CONFLICT (facility_id)` against a partial unique index fails at runtime with 42P10, which is
   exactly the trap issue #96's migration had to warn three writers about. There is one writer here
   and this is it.
2. **Nothing commits.** Every function runs inside the caller's transaction, because the apply path
   writes `dock_occupancy`, `appointments`, `audit_logs`, `notification_outbox` and this table in
   one all-or-nothing unit (section 5.1: *"All-or-nothing per run. Partial application breaks the
   no-overlap and feasibility guarantees the run computed"*). A commit in here would tear that unit
   in half.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Every column `get_scheduling_run` replays, named once so the three readers below cannot drift into
# returning different shapes for the same row. section 7.5.3: the stored run is "input snapshot,
# proposal, objective values, explanation -- replayable a month later".
_RUN_COLUMNS = """
       scheduling_run_id, facility_id, trigger_reason, requested_by_user_id, escalation_id,
       status, horizon_start, horizon_end, horizon_end_reason, policy_version, snapshot_hash,
       input_snapshot_json, proposal_json, objective_json, explanation,
       created_at, applied_at, applied_by_user_id, notifications_enqueued,
       superseded_at, superseded_reason
"""

# The status the partial unique index `scheduling_runs_active_per_facility_uidx` covers. Declared
# once here and interpolated into the `ON CONFLICT` predicate below so that the literal in the
# migration and the literal in the inference clause are the same string in the same place.
ACTIVE_STATUS = "PROPOSED"


def _row(row: Any) -> dict[str, Any]:
    """One `scheduling_runs` row as a plain dict, with its three jsonb columns decoded.

    asyncpg hands `jsonb` back as a **str**, not a dict, because SQLAlchemy's asyncpg dialect does
    not register a JSON codec for raw `text()` statements (the same reason
    `snapshot.py::_build_snapshot` calls `json.loads` on its own `::text`-cast aggregates). Decoding
    here rather than at each call site means `get_scheduling_run`'s response and the apply path's
    re-read of the proposal are the same objects, not two parses that could disagree.
    """
    data = dict(row)
    for key in ("input_snapshot_json", "proposal_json", "objective_json"):
        value = data.get(key)
        if isinstance(value, str):
            data[key] = json.loads(value)
        elif value is None:
            data[key] = {}
    return data


async def insert_proposed_run(
    session: AsyncSession,
    *,
    scheduling_run_id: str,
    facility_id: str,
    trigger_reason: str,
    requested_by_user_id: str,
    escalation_id: str | None,
    horizon_start: datetime,
    horizon_end: datetime,
    horizon_end_reason: str,
    policy_version: str,
    snapshot_hash: str,
    input_snapshot: dict[str, Any],
    proposal: dict[str, Any],
    objective: dict[str, Any],
    explanation: str,
) -> dict[str, Any] | None:
    """Write one PROPOSED run, or return `None` when this facility already has a live one.

    `None` is section 7.5.3's `RUN_ALREADY_ACTIVE`, and it is **the database's answer, not a
    pre-check's**: `DO NOTHING` on the partial unique index means two coordinators pressing "request
    a proposal" in the same second produce exactly one run, with no window between a SELECT and an
    INSERT for the second to slip through. Section 5.1's serialisation is only real if it is decided
    where the row is written.

    The caller is expected to have flipped genuinely expired proposals first
    (`supersede_expired_runs`) -- see that function for why a constraint cannot do it.
    """
    row = (
        await session.execute(
            text(
                f"""
                INSERT INTO public.scheduling_runs (
                  scheduling_run_id, facility_id, trigger_reason, requested_by_user_id,
                  escalation_id, status, horizon_start, horizon_end, horizon_end_reason,
                  policy_version, snapshot_hash, input_snapshot_json, proposal_json,
                  objective_json, explanation
                ) VALUES (
                  :scheduling_run_id, :facility_id, :trigger_reason, :requested_by_user_id,
                  :escalation_id, '{ACTIVE_STATUS}', :horizon_start, :horizon_end,
                  :horizon_end_reason, :policy_version, :snapshot_hash,
                  CAST(:input_snapshot_json AS jsonb), CAST(:proposal_json AS jsonb),
                  CAST(:objective_json AS jsonb), :explanation
                )
                -- The index_predicate is mandatory, not decorative -- see this module's docstring
                -- rule 1. Without it: SQLSTATE 42P10.
                ON CONFLICT (facility_id) WHERE status = '{ACTIVE_STATUS}' DO NOTHING
                RETURNING {_RUN_COLUMNS}
                """
            ),
            {
                "scheduling_run_id": scheduling_run_id,
                "facility_id": facility_id,
                "trigger_reason": trigger_reason,
                "requested_by_user_id": requested_by_user_id,
                "escalation_id": escalation_id,
                "horizon_start": horizon_start,
                "horizon_end": horizon_end,
                "horizon_end_reason": horizon_end_reason,
                "policy_version": policy_version,
                "snapshot_hash": snapshot_hash,
                "input_snapshot_json": json.dumps(input_snapshot, default=str),
                "proposal_json": json.dumps(proposal, default=str),
                "objective_json": json.dumps(objective, default=str),
                "explanation": explanation,
            },
        )
    ).mappings().first()
    return _row(row) if row is not None else None


async def supersede_expired_runs(
    session: AsyncSession, *, facility_id: str, now: datetime
) -> list[str]:
    """Retire PROPOSED runs whose horizon has already passed. Returns the ids flipped.

    ## Why this exists at all -- the constraint-versus-clock asymmetry, again

    `scheduling_runs_active_per_facility_uidx` is `WHERE status = 'PROPOSED'`, and **it cannot carry
    a time term**: a constraint is evaluated against rows, not against a clock. So a proposal whose
    4-hour horizon ended yesterday is, to PostgreSQL, still the facility's one active run and goes
    on refusing every new proposal until *something writes to it*.

    That is the identical shape `scheduling/occupancy.py` documents for lapsed D2 holds under the
    `dock_occupancy` exclusion constraint, and the fix is deliberately the identical one issue #97
    took: flip the dead rows lazily, inside the transaction that needs them gone, instead of
    teaching an index to know what time it is. Reusing the established pattern rather than inventing
    a second one is the point -- there is now one answer in this codebase to "a partial index whose
    predicate ought to have expired".

    A proposal past its horizon is dead in the strongest sense available: every placement in it
    starts before `now`, so applying it could only write intervals in the past. There is no
    judgement call to defer to a human here, which is why this is safe to do automatically where
    `SNAPSHOT_DRIFT` and `PARTIALLY_INFEASIBLE` (the other two supersede producers) are not
    automatic at all -- they happen only because a planner pressed Apply.

    `now` is a bound parameter and never SQL `now()`, per section 9.1's deterministic-clock rule and
    for the same reason every helper in `occupancy.py`/`expiry.py` takes its instant from the
    caller: a test that cannot pin the clock starts failing the day after it is written.
    """
    rows = (
        await session.execute(
            text(
                f"""
                UPDATE public.scheduling_runs
                   SET status = 'SUPERSEDED',
                       superseded_at = :now,
                       superseded_reason = 'HORIZON_PASSED'
                 WHERE facility_id = :facility_id
                   AND status = '{ACTIVE_STATUS}'
                   AND horizon_end <= :now
                RETURNING scheduling_run_id
                """
            ),
            {"facility_id": facility_id, "now": now},
        )
    ).scalars().all()
    return [str(run_id) for run_id in rows]


async def active_run_for_facility(
    session: AsyncSession, *, facility_id: str
) -> dict[str, Any] | None:
    """The facility's one live PROPOSED run, for naming it in a `RUN_ALREADY_ACTIVE` refusal.

    Read **after** the insert has already been refused, never before it as a pre-check: the insert
    is what decides, this is only what makes the refusal say *which* run is in the way. Section
    7.5.3's contract is a typed outcome, and "there is already one" without an id would send the
    planner hunting.
    """
    row = (
        await session.execute(
            text(
                f"""
                SELECT {_RUN_COLUMNS}
                  FROM public.scheduling_runs
                 WHERE facility_id = :facility_id AND status = '{ACTIVE_STATUS}'
                 ORDER BY created_at DESC
                 LIMIT 1
                """
            ),
            {"facility_id": facility_id},
        )
    ).mappings().first()
    return _row(row) if row is not None else None


async def get_run(session: AsyncSession, *, scheduling_run_id: str) -> dict[str, Any] | None:
    """Section 7.5.3's `get_scheduling_run` read. Pure -- no lock, no lifecycle check."""
    row = (
        await session.execute(
            text(
                f"""
                SELECT {_RUN_COLUMNS}
                  FROM public.scheduling_runs
                 WHERE scheduling_run_id = :scheduling_run_id
                """
            ),
            {"scheduling_run_id": scheduling_run_id},
        )
    ).mappings().first()
    return _row(row) if row is not None else None


async def lock_run(session: AsyncSession, *, scheduling_run_id: str) -> dict[str, Any] | None:
    """The same read, `FOR UPDATE`, for the apply path.

    Two planners pressing Apply on one proposal is the same race section 7.5.1 names as "the
    nastiest race in the product" for `confirm_request`, and it gets the same resolution: both take
    the row under the same transaction, exactly one commits, the loser is told. The lock is taken
    **first**, before any capacity read, so that the snapshot recomputation below it is evaluated
    against committed state under READ COMMITTED -- the rule
    `scheduling/snapshot.py::load_appointment_snapshots` states for its own callers ("call this
    *after* the appointment rows are locked FOR UPDATE, never before").

    Lock ordering, traced rather than assumed: this row is taken before any `appointments` row, and
    nothing else in the codebase locks `scheduling_runs` at all, so this adds no cycle to the
    existing appointments -> `dock_occupancy` order every allocation path already uses.
    """
    row = (
        await session.execute(
            text(
                f"""
                SELECT {_RUN_COLUMNS}
                  FROM public.scheduling_runs
                 WHERE scheduling_run_id = :scheduling_run_id
                 FOR UPDATE
                """
            ),
            {"scheduling_run_id": scheduling_run_id},
        )
    ).mappings().first()
    return _row(row) if row is not None else None


async def mark_applied(
    session: AsyncSession,
    *,
    scheduling_run_id: str,
    applied_by_user_id: str,
    applied_at: datetime,
    notifications_enqueued: int,
) -> bool:
    """PROPOSED -> APPLIED. `False` means somebody else got there first.

    The `AND status = 'PROPOSED'` predicate is the guard, not a Python check above it -- the same
    "predicate is the guard" shape `expiry._expire_one_pending` and `escalation_service.
    start_escalation_work` both use. A second apply of the same run therefore writes nothing and is
    *told*, rather than double-applying a schedule.
    """
    row = (
        await session.execute(
            text(
                f"""
                UPDATE public.scheduling_runs
                   SET status = 'APPLIED',
                       applied_at = :applied_at,
                       applied_by_user_id = :applied_by_user_id,
                       notifications_enqueued = :notifications_enqueued
                 WHERE scheduling_run_id = :scheduling_run_id
                   AND status = '{ACTIVE_STATUS}'
                RETURNING scheduling_run_id
                """
            ),
            {
                "scheduling_run_id": scheduling_run_id,
                "applied_at": applied_at,
                "applied_by_user_id": applied_by_user_id,
                "notifications_enqueued": notifications_enqueued,
            },
        )
    ).first()
    return row is not None


async def mark_superseded(
    session: AsyncSession, *, scheduling_run_id: str, reason: str, superseded_at: datetime
) -> bool:
    """PROPOSED -> SUPERSEDED with a stated reason. `False` if it was no longer PROPOSED.

    Called on the two refusal paths section 7.5.3 defines -- `SNAPSHOT_DRIFT` ("re-run required")
    and `PARTIALLY_INFEASIBLE` ("refuses entirely"). Both mean the stored proposal is provably not
    applicable, and leaving it PROPOSED would hold the facility's one active-run slot against the
    fresh proposal the planner has just been told to request
    (`03-planner-dock-board/flows-and-states.md` Flow 9 step 4: the overlay "offers 'Request a fresh
    proposal' rather than a bare error").

    This is a **run-lifecycle** write, not a capacity write, and the distinction is the whole
    all-or-nothing story: on both refusal paths zero rows change in `appointments`,
    `dock_occupancy`, `audit_logs` or `notification_outbox`, and the only thing that moves is the
    status of the dead artifact. `tests/proof/test_part12_sequencer.py` asserts exactly that split
    rather than a blanket "nothing was written".
    """
    row = (
        await session.execute(
            text(
                f"""
                UPDATE public.scheduling_runs
                   SET status = 'SUPERSEDED',
                       superseded_at = :superseded_at,
                       superseded_reason = :reason
                 WHERE scheduling_run_id = :scheduling_run_id
                   AND status = '{ACTIVE_STATUS}'
                RETURNING scheduling_run_id
                """
            ),
            {
                "scheduling_run_id": scheduling_run_id,
                "superseded_at": superseded_at,
                "reason": reason,
            },
        )
    ).first()
    return row is not None


async def list_runs(
    session: AsyncSession,
    *,
    facility_id: str | None,
    status: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Runs at a facility, newest first. `facility_id=None` means "every facility in scope".

    Rides `ix_scheduling_runs_facility_created` (facility_id, created_at DESC) -- the index that
    exists for exactly this read. The unscoped form is reachable only by a global-read persona; the
    **service** decides that, not this function, per this module's docstring.

    `status` is an optional equality filter rather than a hardcoded `'PROPOSED'` so the same read
    answers both questions the planner board asks: "is there a proposal waiting" (the
    `[ Review proposal (N) ]` count) and "what happened here recently" (the audit view section 8's
    trust question needs). A `PROPOSED` filter additionally rides the partial unique index.
    """
    where = ["1 = 1"]
    params: dict[str, Any] = {"limit": limit}
    if facility_id is not None:
        where.append("facility_id = :facility_id")
        params["facility_id"] = facility_id
    if status is not None:
        where.append("status = :status")
        params["status"] = status
    rows = (
        await session.execute(
            text(
                f"""
                SELECT {_RUN_COLUMNS}
                  FROM public.scheduling_runs
                 WHERE {' AND '.join(where)}
                 ORDER BY created_at DESC, scheduling_run_id DESC
                 LIMIT :limit
                """
            ),
            params,
        )
    ).mappings().all()
    return [_row(row) for row in rows]


async def latest_run_for_escalation(
    session: AsyncSession, *, escalation_id: str
) -> dict[str, Any] | None:
    """The newest run this capacity incident produced (issue #54's link, read back).

    Ops Flow 4 step 4 keeps the incident row in the queue in a handoff state -- *"Proposal
    requested - routed to Planner queue - N shipments awaiting a planner's review"* -- which is only
    renderable if the console can find the run its own request created. Rides the partial index
    `ix_scheduling_runs_escalation`.
    """
    row = (
        await session.execute(
            text(
                f"""
                SELECT {_RUN_COLUMNS}
                  FROM public.scheduling_runs
                 WHERE escalation_id = :escalation_id
                 ORDER BY created_at DESC
                 LIMIT 1
                """
            ),
            {"escalation_id": escalation_id},
        )
    ).mappings().first()
    return _row(row) if row is not None else None
