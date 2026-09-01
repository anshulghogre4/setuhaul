"""§7.3's composite queue ordering, in one place, for every queue-shaped read.

Design citation: `SOLUTION_DESIGN.md` §7.3 ("Queue ordering -- not FIFO"), §13.1 ("average driver
waiting"), FR-PLN-010. GitHub issues #60 (which first implemented this) and #82 (which is why it
now lives here rather than inside `services/planner_service.py`).

## Why this is its own module

§7.3 rejects **both** pure FIFO and pure TTL ordering by name, for the same reason: either one
buries the seeded SHP1014 case (CRITICAL, entered the queue *after* lower-priority requests).
The replacement it specifies is a composite of three terms -- TTL remaining, priority code, and
whether the driver is physically waiting at the gate.

Two different reads answer that same question for the same facility: `planner_service
.get_planner_queue` (the §7.5.1 planner queue) and `escalation_service.get_pending_confirmations`
(the ops console's pending list). The second shipped ordering `booked_at ASC` -- exactly the FIFO
§7.3 names -- and issue #82's assessment was explicit that the fix is for it to *adopt* the first
one's ordering rather than for a second implementation of a scheduling policy to appear in a
different service, because two implementations of one policy is how they drift.

So the policy lives here, in `scheduling/` (where scheduling policy belongs) and as a leaf that
imports nothing from the application: both services can depend on it and neither depends on the
other. `planner_service` re-binds these names on import, so `planner_service.TTL_PRESSURE_MAX`
and friends keep resolving exactly as they did.

## The weights, restated rather than re-derived

§7.3 names the three terms and their intent but assigns no weights, so the two numbers below are an
implementation choice and are stated as one rather than buried. They are unchanged from issue #60's
original calibration -- moving a policy must not silently retune it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = [
    "PHYSICALLY_WAITING_QUEUE_STATES",
    "TTL_PRESSURE_MAX",
    "WAITING_BONUS",
    "QueueUrgency",
    "composite_urgency",
    "urgency_sort_key",
]

# `facility_checkins.queue_state` values that mean "this driver is physically waiting at the gate"
# -- §7.3's third ordering term, "queue_state in WAITING_*". Read off the live CHECK constraint
# (baseline migration line 220): NOT_QUEUED / WAITING_EARLY / WAITING_LATE /
# WAITING_DOCK_UNAVAILABLE / CALLED_TO_DOCK / IN_DOCK / COMPLETED. CALLED_TO_DOCK and IN_DOCK are
# deliberately excluded: that truck is being served, not burning detention in the yard, which is
# the metric §13.1 asks this term to express.
PHYSICALLY_WAITING_QUEUE_STATES = ("WAITING_EARLY", "WAITING_LATE", "WAITING_DOCK_UNAVAILABLE")

# TTL_PRESSURE_MAX = 1000 -- exactly one priority step in the shipped `ranking_policy`
# (CRITICAL 4000 / HIGH 3000 / NORMAL 2000 / LOW 1000). A request that has burnt its whole D9 clock
# is therefore promoted by one band and no further: an expiring NORMAL ties a fresh HIGH and can
# never outrank a fresh CRITICAL. That is what stops this being "pure TTL ordering", which §7.3
# rejects for the same reason it rejects FIFO.
#
# WAITING_BONUS = 500 -- half a band. A driver physically waiting outranks a comparable one still
# in transit, but never inverts a priority step on its own.
#
# Owner-reviewable: the calibration is defensible but it is not in any design document. The score
# and every term are returned per row so the sort is inspectable instead of magic.
TTL_PRESSURE_MAX = 1000
WAITING_BONUS = 500


class QueueUrgency(BaseModel):
    """One row's composite urgency, with every term it was built from.

    Returned in full, not just as `score`, because §7.3's ordering is a policy decision a planner
    (and an auditor) must be able to check. A bare number would be unfalsifiable.
    """

    model_config = ConfigDict(extra="forbid")

    score: int
    priority_score: int
    ttl_pressure: int
    waiting_bonus: int


def composite_urgency(
    *,
    priority_code: str,
    priority_scores: dict[str, int],
    ttl_remaining_seconds: int,
    ttl_total_seconds: int,
    physically_waiting: bool,
) -> QueueUrgency:
    """§7.3's composite urgency as one inspectable number.

    A *score*, not a lexicographic sort, because §7.3 rejects both pure FIFO and pure TTL ordering
    by name -- either one buries the seeded SHP1014 case. See the module docstring for the
    calibration and why those two numbers are stated rather than tuned in silence.
    """
    priority_score = priority_scores.get(priority_code, priority_scores.get("UNKNOWN", 500))
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


def urgency_sort_key(score: int, appointment_id: str) -> tuple[int, str]:
    """Highest urgency first, `appointment_id` ascending as the stable tiebreaker.

    Extracted alongside the score for issue #82 so the two consumers cannot agree on the metric and
    then disagree on how to sort by it. A stable order matters more than it looks: U19 freezes the
    sort while a row has focus, and a sort that could reorder equal-scoring rows between two polls
    would move a row out from under whoever was mid-decision on it. It is also the same
    "no randomness, deterministic tiebreaker" posture `ranking_policy.ordered_factors` ends on.
    """
    return (-score, appointment_id)
