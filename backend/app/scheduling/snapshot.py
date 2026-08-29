"""`snapshot_hash` -- the optimistic-concurrency token for the planner throughput path.

Design citation: `SOLUTION_DESIGN.md` section 7.5 principle 3 (*"Anything that consumes capacity
takes an `Idempotency-Key` and a `snapshot_hash`, and refuses on drift"*), section 7.5.1
(`get_planner_queue` emits it; `confirm_request` / `counter_offer` / `bulk_confirm` consume it),
section 7.5.3 (`apply_schedule_proposal`), and `03-planner-dock-board/flows-and-states.md` Flow 1
step 5 -- *"never a silent retry with old context"*. Issue #61 (P-G2).

## Why this is its own module

Two halves of the product need the identical digest and neither may import the other. The producer
is `services/planner_service.py::get_planner_queue` (issue #60, shipped first, in the *service*
layer); the consumers are `scheduling/allocation.py`'s write paths (the *scheduling* layer, which
sits below services). Having `allocation` import `planner_service` would both invert that layering
and close a real import cycle -- `planner_service` imports `scheduling.expiry`, which imports
`scheduling.allocation`. A leaf module under `scheduling/` that both can depend on is the only
shape that avoids it.

## The contract, stated once so both halves match

**`planner_snapshot_hash` below is byte-identical to `planner_service._snapshot_hash`** and must
stay that way: `tests/unit/test_planner_snapshot_hash.py` asserts the two produce the same digest
for the same inputs, and fails the moment either drifts. The producer shipped first, so this is the
copy that conforms -- not the other way round. **The follow-up the coordinator should file: delete
`planner_service._snapshot_hash` and have it import this one.** Until then the drift guard is what
keeps them honest.

The digest is the SHA-256 hex of a canonical JSON object over:

| field | meaning |
|---|---|
| `v` | serialisation version, `1` |
| `appointment_id` | identity |
| `appointment_status` | lifecycle state |
| `is_current` | the "this is the live promise" flag, as an int |
| `dock_id` | the dock the slot resolves to |
| `interval_start` / `interval_end` | the **authoritative** interval: `dock_occupancy`'s claim when one exists, otherwise the same expression `allocation._claim_dock_occupancy` would compute (slot start + `expected_unload_min` + the flat 15-minute changeover buffer). D1 (section 0.9) makes `dock_occupancy` the authority, and `appointment_slots` cannot see a 75-minute unload booked into a 60-minute slot (section 6.2 #1) |
| `interval_source` | `dock_occupancy` or `appointment_slot_derived` -- which of the two the interval came from, so a claim appearing or being released is itself drift |
| `conflicts` | sorted appointment ids of other live claims overlapping that interval on that dock |

Deliberately **absent**: TTL remaining, ETA, and anything else that moves on a wall clock. A hash
that changed every second would make every confirm stale and turn `SNAPSHOT_STALE` into noise. The
guard means *"the capacity you looked at changed"*, not *"time passed"*.

Not a security boundary and not signed. The server recomputes the digest from its own rows under
the row lock, so a forged value can only ever make a comparison fail, never pass.

## Ordering of the two refusals, and why it is not arbitrary

`conflicts` is inside the hash, so a new overlapping claim changes the digest -- which would make
`SNAPSHOT_STALE` swallow the case section 7.5.1 gives its own code to. The write paths therefore
check displacement **first** and staleness second, so `DISPLACEMENT_DETECTED` keeps its meaning
("a conflict appeared since render") and `SNAPSHOT_STALE` keeps its own ("something else moved").
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Mirrors `planner_service.SNAPSHOT_ALGORITHM`, which the queue response already advertises.
SNAPSHOT_ALGORITHM = "sha256/planner-queue-v1"

ACTIVE_APPOINTMENT_STATUSES = ("PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS")

# `dock_status_events.event_type` values that mean "this dock is unavailable". Same tuple as
# `planner_service.BLOCKING_EVENT_TYPES`, read off the live CHECK constraint: MAINTENANCE,
# BREAKDOWN, CAPACITY_REDUCTION, REOPENED, MANUAL_BLOCK. REOPENED is excluded because it means the
# dock came *back*. Declared here rather than imported for the same import-cycle reason the module
# docstring gives.
BLOCKING_EVENT_TYPES = ("MAINTENANCE", "BREAKDOWN", "CAPACITY_REDUCTION", "MANUAL_BLOCK")

INTERVAL_SOURCE_OCCUPANCY = "dock_occupancy"
INTERVAL_SOURCE_SLOT_DERIVED = "appointment_slot_derived"

CONFLICT_INTERVAL = "INTERVAL_CONFLICT"
CONFLICT_DOCK_BLOCKED = "DOCK_BLOCKED"


def _coerce_ts(value: datetime) -> datetime:
    """UTC-pin a timestamp before it is rendered into the digest.

    Byte-identical to `planner_service._coerce_ts`. Without it a connection with a different
    TimeZone setting, or a driver handing back a fixed-offset tzinfo, would hash an unchanged row
    differently.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def planner_snapshot_hash(
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
    """The canonical `snapshot_hash`. Keep byte-identical to `planner_service._snapshot_hash`."""
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


def batch_snapshot_hash(row_hashes: dict[str, str]) -> str:
    """`bulk_confirm`'s single `snapshot_hash`, composed from the per-row ones (section 7.5.1).

    `bulk_confirm` takes `appointment_ids[]` and *one* `snapshot_hash`, so the batch token has to be
    derivable by the client from the per-row tokens `get_planner_queue` already handed it, and
    recomputable by the server from current state. Sorted by appointment id, so selection *order*
    never changes the token -- only membership and content do.
    """
    pairs = sorted(row_hashes.items())
    canonical = json.dumps(
        {"v": 1, "rows": [f"{appointment_id}:{row_hash}" for appointment_id, row_hash in pairs]},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# The write-side recomputation. Every COALESCE and every join below mirrors
# `repositories/operations.py::list_planner_queue_rows` -- the query the producer reads from -- so
# that the digest the planner was shown and the digest recomputed under the row lock can only
# differ because the data really changed. The two conflict sub-selects are what
# `DISPLACEMENT_DETECTED` is built from.
#
# `LEFT JOIN LATERAL ... ORDER BY occupancy_id ASC LIMIT 1` rather than a plain LEFT JOIN, again
# copied from the producer: the D1 EXCLUDE constraint is on (dock_id, window), so nothing stops one
# appointment holding claims on two different docks, and a plain join would fan the row out.
_SNAPSHOT_SQL = """
WITH target AS (
  SELECT a.appointment_id,
         a.shipment_id,
         a.slot_id,
         a.appointment_status,
         a.is_current,
         sl.facility_id,
         sl.dock_id,
         occ.window_start AS occupancy_start,
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
SELECT t.appointment_id,
       t.shipment_id,
       t.slot_id,
       t.appointment_status,
       t.is_current,
       t.facility_id,
       t.dock_id,
       t.occupancy_start,
       t.interval_start,
       t.interval_end,
       COALESCE((
           SELECT json_agg(json_build_object(
                      'conflict_type', 'INTERVAL_CONFLICT',
                      'appointment_id', oa.appointment_id,
                      'shipment_id', oa.shipment_id,
                      'appointment_status', oa.appointment_status,
                      'dock_id', o.dock_id
                  ) ORDER BY oa.appointment_id)
             FROM public.dock_occupancy o
             JOIN public.appointments oa ON oa.appointment_id = o.appointment_id
            WHERE o.dock_id = t.dock_id
              AND o.appointment_id <> t.appointment_id
              AND oa.appointment_status = ANY(:active_statuses)
              AND o."window" && tstzrange(t.interval_start, t.interval_end, '[)')
       ), '[]'::json)::text AS interval_conflicts_json,
       COALESCE((
           SELECT json_agg(json_build_object(
                      'conflict_type', 'DOCK_BLOCKED',
                      'dock_event_id', de.dock_event_id,
                      'dock_id', de.dock_id,
                      'event_type', de.event_type,
                      'reason', de.reason
                  ) ORDER BY de.dock_event_id)
             FROM public.dock_status_events de
            WHERE de.dock_id = t.dock_id
              AND de.event_type = ANY(:blocking_types)
              AND de.event_start_ts < t.interval_end
              AND (de.event_end_ts IS NULL OR de.event_end_ts > t.interval_start)
       ), '[]'::json)::text AS dock_block_conflicts_json
  FROM target t
"""


def _build_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    """Turn one `_SNAPSHOT_SQL` row into the snapshot record the write paths use."""
    interval_start = _coerce_ts(row["interval_start"])
    interval_end = _coerce_ts(row["interval_end"])
    interval_source = (
        INTERVAL_SOURCE_OCCUPANCY
        if row.get("occupancy_start") is not None
        else INTERVAL_SOURCE_SLOT_DERIVED
    )
    interval_conflicts: list[dict[str, Any]] = json.loads(row["interval_conflicts_json"] or "[]")
    dock_blocks: list[dict[str, Any]] = json.loads(row["dock_block_conflicts_json"] or "[]")
    return {
        "appointment_id": str(row["appointment_id"]),
        "shipment_id": str(row["shipment_id"]),
        "slot_id": str(row["slot_id"]),
        "appointment_status": str(row["appointment_status"]),
        "is_current": row.get("is_current"),
        "facility_id": str(row["facility_id"]),
        "dock_id": str(row["dock_id"]),
        "interval_start": interval_start,
        "interval_end": interval_end,
        "interval_source": interval_source,
        # Only the interval conflicts feed the hash -- that is exactly the set the producer puts in
        # `conflict_ids`, and adding the dock blocks here would silently fork the digest.
        "conflicts": interval_conflicts,
        "dock_blocks": dock_blocks,
        "snapshot_hash": planner_snapshot_hash(
            appointment_id=str(row["appointment_id"]),
            appointment_status=str(row["appointment_status"]),
            is_current=row.get("is_current"),
            dock_id=str(row["dock_id"]),
            interval_start=interval_start,
            interval_end=interval_end,
            interval_source=interval_source,
            conflict_ids=[str(c["appointment_id"]) for c in interval_conflicts],
        ),
    }


async def load_appointment_snapshots(
    session: AsyncSession, appointment_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """Recompute the snapshot (and its displacement set) for each id, in one round trip.

    Call this *after* the appointment rows are locked `FOR UPDATE`, never before: under READ
    COMMITTED the lock is what guarantees these are the committed values the write is about to act
    on (PostgreSQL "Transaction Isolation" 13.2.1, quoted at length in `expiry.py`).
    """
    if not appointment_ids:
        return {}
    rows = (
        await session.execute(
            text(_SNAPSHOT_SQL),
            {
                "appointment_ids": list(appointment_ids),
                "active_statuses": list(ACTIVE_APPOINTMENT_STATUSES),
                "blocking_types": list(BLOCKING_EVENT_TYPES),
            },
        )
    ).mappings().all()
    return {str(row["appointment_id"]): _build_snapshot(dict(row)) for row in rows}


async def load_appointment_snapshot(
    session: AsyncSession, appointment_id: str
) -> dict[str, Any] | None:
    """Single-appointment form, for `confirm_request` and `counter_offer`."""
    snapshots = await load_appointment_snapshots(session, [appointment_id])
    return snapshots.get(appointment_id)


def displacement_conflicts(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """The full `DISPLACEMENT_DETECTED` set: overlapping live claims **plus** dock blocks.

    Deliberately a *superset* of what `get_planner_queue` currently renders in its displacement
    column, which only carries the overlapping-claim half (`planner_service._conflicts_for`). A
    confirm can therefore be refused for a reason the row did not show -- a dock the planner (or a
    breakdown) took out from under it since render.

    That asymmetry is the safe direction and is stated rather than smuggled: refusing more than the
    row warned about is recoverable (Flow 1 step 6 re-renders with the conflict named), whereas
    confirming a truck onto a dock that `block_dock` took offline is not. `block_dock` deliberately
    does **not** delete the `dock_occupancy` rows it strands -- that is how a
    `CAPACITY_EVENT_CASCADE` begins (section 7.4) -- so nothing else in the confirm path would
    catch it. **Owner fork: `_conflicts_for` should grow the same leg so the row and the refusal
    agree.**
    """
    return [*snapshot.get("conflicts", []), *snapshot.get("dock_blocks", [])]


def describe_snapshot_drift(snapshot: dict[str, Any], *, expected_hash: str) -> dict[str, Any]:
    """The body of a `SNAPSHOT_STALE` refusal.

    Flow 1 step 5 requires the planner to *re-read before deciding again* rather than silently
    retry, and `edge-cases.md` #1 wants them told what changed. Current values are the honest thing
    to return: the server only ever held the client's hash, never its pre-image, so it can say what
    the row is now but not what the planner saw.
    """
    return {
        "reason_code": "SNAPSHOT_STALE",
        "algorithm": SNAPSHOT_ALGORITHM,
        "expected_snapshot_hash": expected_hash,
        "current_snapshot_hash": snapshot["snapshot_hash"],
        "current": {
            "appointment_status": snapshot["appointment_status"],
            "is_current": snapshot.get("is_current"),
            "dock_id": snapshot["dock_id"],
            "interval_start": snapshot["interval_start"].isoformat(),
            "interval_end": snapshot["interval_end"].isoformat(),
            "interval_source": snapshot["interval_source"],
            "conflict_appointment_ids": sorted(
                str(conflict["appointment_id"]) for conflict in snapshot.get("conflicts", [])
            ),
        },
    }
