"""The one definition of "this `dock_occupancy` row is blocking capacity right now".

Design citation: `SOLUTION_DESIGN.md` §0.8 ("D2 in concrete terms" -- *"Expiry is lazy plus swept.
Every read filters `state='HELD' AND expires_at > now()`; a sweeper transitions stale rows to
`EXPIRED`. Never depend on the sweeper for correctness -- only for hygiene."*), §5 Stage 3, D1, D2,
M6, FR-SYS-006. GitHub issue #97.

## Why this module exists -- the constraint-versus-clock asymmetry

`dock_occupancy` is guarded by a **partial** exclusion constraint
(`20260829134929_d2_held_state_dock_occupancy.sql` step 5)::

    EXCLUDE USING gist (dock_id WITH =, "window" WITH &&)
    WHERE (state IN ('HELD','PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS'))

**That predicate contains no time term, and it cannot: a constraint is evaluated against rows, not
against a clock.** A `HELD` row whose `expires_at` passed an hour ago is, to PostgreSQL, still a
member of the excluded set -- it goes on refusing every overlapping insert until *something writes
to it*. §0.8's TTL is therefore not enforced by the database at all; it is enforced by application
reads filtering on it, and by the sweeper eventually flipping the row.

Issue #97 is what happens when the two halves of the system disagree about which of those two
definitions they mean:

* `find_feasible_slots` consulted **neither** -- it derived availability from `appointment_slots`
  joined to `appointments`, and a `HELD` row has no `appointments` row at all (§4: *"Held != booked:
  no `appointments` row exists yet"*). So a live hold by another shipment was invisible to it and it
  offered the interval anyway.
* `request_slot` consulted the **constraint**, which sees lapsed holds as live. So a dead,
  never-swept hold refused an interval that feasibility had just offered.

Two failures, opposite directions, one root cause: no shared definition of "blocking". Live
evidence, 2026-09-01: `dock_occupancy` rows 758/759 at `DOCK-GGN-D1`, `state='HELD'`, `expires_at`
~11:33 IST and long past, unswept -- there is no sweeper running (the EventBridge wiring is still
open on issue #20). Feasibility offered those windows; `request_slot` refused them.

## The predicate, and why *both* sides need the *same* one

    state IN ('PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS')
    OR (state = 'HELD' AND expires_at > now)

i.e. **the exclusion constraint's set, minus lapsed holds**. `PENDING_CONFIRMATION` / `CONFIRMED` /
`IN_PROGRESS` carry no `expires_at` at all (`dock_occupancy_held_shape_check` forbids it: *"state
<> 'HELD' AND expires_at IS NULL"*), so the time term applies only to the `HELD` leg -- which is
exactly §0.8's sentence, expressed as SQL.

The two consumers are not symmetric and neither is sufficient alone:

* **The read side** (`feasibility.find_feasible_slots`, `feasibility.explain_slot_eligibility`)
  applies it as a *filter*: an interval already blocked by a live claim is not offered.
* **The write side** (`allocation._claim_dock_occupancy`, `holds.create_hold`) cannot filter --
  PostgreSQL will apply the constraint's own, wider predicate no matter what the application
  believes. So it makes the predicate *true of the table* instead, by lazily flipping colliding
  lapsed holds to `EXPIRED` inside the claiming transaction before it inserts
  (`holds.expire_lapsed_holds_on_interval`).

That is the whole of the fix and it only works as a pair. If the read side filtered lapsed holds
out but the write side did not expire them, feasibility would go straight back to offering
intervals the constraint refuses -- issue #97 unchanged, with a longer explanation.

## `now` is always a bound parameter, never SQL `now()`

§9.1's deterministic clock: *"Every test must inject `now` rather than read the wall clock, or the
entire suite starts failing the day after it is written."* Every helper here takes the instant from
its caller for the same reason `sweep_expired_appointments`, `sweep_held_holds` and
`live_hold_for_shipment` already do.
"""

from __future__ import annotations

__all__ = [
    "CAPACITY_CONSUMING_STATES",
    "CHANGEOVER_BUFFER_MINUTES",
    "TIMED_CAPACITY_STATES",
    "UNTIMED_CAPACITY_STATES",
    "claim_window_sql",
    "live_blocking_occupancy_sql",
]

# §0.8: "one truck per dock per instant, across every state that occupies capacity." Mirrors the
# migration's exclusion-constraint predicate exactly (20260829134929 step 5). Defined HERE and
# re-exported by `holds.py` and `snapshot.py`, which each carried their own identical copy before
# issue #97 -- three literals that had to be kept in step by hand were two too many for a value
# whose whole job is to mean the same thing everywhere.
CAPACITY_CONSUMING_STATES = ("HELD", "PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS")

# The split the liveness predicate turns on. `dock_occupancy_held_shape_check` guarantees it:
# only 'HELD' may carry an `expires_at`, and it must carry one. So only the HELD leg has a clock.
UNTIMED_CAPACITY_STATES = ("PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS")
TIMED_CAPACITY_STATES = ("HELD",)

# D1's flat changeover buffer between trucks on the same dock. Still flat rather than per-facility
# because that is what the E1.1 backfill used and making it configurable is an open D1 decision
# (§0.8, "Three things D1 forces us to decide"); there is no column to read it from yet.
CHANGEOVER_BUFFER_MINUTES = 15


def _quoted_states(states: tuple[str, ...]) -> str:
    return ", ".join(f"'{state}'" for state in states)


def live_blocking_occupancy_sql(*, alias: str = "o", now_param: str = "now") -> str:
    """The §0.8 liveness predicate as a SQL fragment, for `alias` bound to `dock_occupancy`.

    `alias` and `now_param` are interpolated, not bound. They are always module-level literals
    supplied by this repository's own call sites -- never a request value, never anything an LLM
    argument reaches -- because a bind parameter cannot stand in for an identifier in PostgreSQL.
    `now_param` names a real bind parameter the caller must supply (`:now`), so the *instant* is
    still parameterised even though its name is not.

    The first clause looks redundant against the second and is not. It is written to be
    **textually identical to the exclusion constraint's own partial-index predicate**, and what it
    buys was measured on PostgreSQL 18.3 rather than assumed (proof cluster, 2026-09-01, both forms
    EXPLAINed under `enable_seqscan = off`):

    * **Without it**, the planner rewrites the bare OR into a `BitmapOr` of *two* index scans --
      `dock_occupancy_dock_id_window_excl` for the dock+window arm, and
      `ix_dock_occupancy_held_expiry` for the `expires_at > now` arm. The second arm carries no
      `dock_id` and no `"window"` condition at all: it reads **every live hold in the system** and
      rechecks them. Cheap on a proof cluster, linear in total outstanding holds in production, and
      paid once per candidate slot.
    * **With it**, the plan is a single `Index Scan using dock_occupancy_dock_id_window_excl` whose
      `Index Cond` is exactly the dock and the window, with the liveness test demoted to a Filter
      over the handful of rows that survive.

    So this is not defensive redundancy against a hypothetically weak implication prover -- it is
    the difference between a bounded probe and an unbounded one, and NFR-003's <50 ms budget for
    `find_feasible_slots` is what it protects. `tests/proof/test_part7_read_write_agreement.py`
    pins the resulting plan.
    """
    return (
        f"({alias}.state IN ({_quoted_states(CAPACITY_CONSUMING_STATES)})\n"
        f"                       AND ({alias}.state IN ({_quoted_states(UNTIMED_CAPACITY_STATES)})\n"
        f"                            OR ({alias}.state = 'HELD' AND {alias}.expires_at > :{now_param})))"
    )


def claim_window_sql(*, start_expr: str, unload_min_expr: str) -> str:
    """The `tstzrange` a claim on this slot would occupy: start, plus unload, plus the buffer.

    This expression is the definition of "occupied" for D1, and three places must agree on it or
    the system means different things by the word in each: the E1.1 backfill
    (`20260823060000_d1_correctness_bedrock.sql`), `allocation._claim_dock_occupancy` and
    `holds.create_hold` (which write it), and the read/lazy-expiry paths added for issue #97
    (which must ask about *the interval the write would take*, not about the published slot
    window -- a 75-minute unload booked into a 60-minute slot is precisely the case
    `appointment_slots` cannot see, §6.2 #1).

    Parameterised on its two operand expressions rather than fixed, because the callers name them
    differently: the writers read `expected_unload_min` off a joined `shipments` row, while
    `find_feasible_slots` already has the value in Python and binds it. Same expression, same
    result, one source. `tests/unit/test_scheduling_allocation.py` pins it against both inline
    copies and against the migration.
    """
    return (
        f"tstzrange({start_expr}, {start_expr} "
        f"+ (({unload_min_expr} + {CHANGEOVER_BUFFER_MINUTES}) || ' minutes')::interval, '[)')"
    )
