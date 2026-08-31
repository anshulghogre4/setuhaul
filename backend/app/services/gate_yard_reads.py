"""Gate and yard *reads* -- `SOLUTION_DESIGN.md` section 7.5.2, `GY-G1` (issue #67).

The read side of the gate/yard kiosk. `gate_yard_service.py` shipped all five section 7.5.2
*writes*; nothing shipped the lookup that reaches them, so an officer could type a shipment id or a
plate number into the surface's single most-used field
(`UI-UX/04-gate-yard-kiosk/components.md` section 2) and no tool anywhere in the product could
answer. This module is that one tool.

Filed as its own module rather than appended to `gate_yard_service.py` to match the codebase's
existing read/write file split (`driver_reads.py`, `operations_reads.py`, `carrier_reads.py` are
reads; `gate_yard_service.py`, `planner_service.py`, `escalation_service.py` are writes) -- and
because `gate_yard_service.py`'s own docstring scopes it to writes by name.

Four structural notes for anyone editing this file:

1. **Scope is derived, never accepted** (`M15` / `NFR-019`). `search_gate_yard_trucks` takes no
   `facility_id` argument. `UI-UX/04-gate-yard-kiosk/implementation-spec.md` section 6 Fork E
   sketches the tool as `search_gate_yard_truck(query, facility_id)`; that literal signature is
   deliberately **not** implemented, because a client-supplied scope id is exactly the shape M15
   forbids. The facility comes from `repositories.scope.resolve_facility_scope`, the same resolver
   `search_records` uses, so a `GATE_OFFICER` (issue #79), `WAREHOUSE_PLANNER` or
   `FACILITY_MANAGER` sees only their own facility and an `ADMIN` (the one `has_global_read_scope`
   role that also passes the router's role gate) sees every facility -- which is exactly the reach
   `assert_gate_write_scope` already grants each of them on the five writes. Read reach and write
   reach agree by construction; a search cannot surface a truck the caller could not then act on.
   `GATE_OFFICER` needed no change here: it is facility-scoped through the ordinary `facility_id`
   column and is not `has_global_read_scope`, so `resolve_facility_scope` already returns its own
   facility (or refuses an unmapped identity) with no branch of its own.

2. **Exact match on a normalised identifier, never fuzzy.** `search_records` (section 7.5.8) uses
   pg_trgm `similarity` because a desk operator scanning a palette benefits from near-misses. A
   gate officer does not: acting on the wrong truck writes a false arrival fact into
   `facility_checkins`, which is the sequencer's only source of *actual* arrival truth. So the
   three identifier columns are compared for equality after both sides are stripped of
   non-alphanumerics and upper-cased. That normalisation is not cosmetic -- plates are stored
   unspaced (`RJ14GT4101`, seeded `vehicles` rows) but rendered spaced in this surface's own
   mockup (`RJ14 GH 2211`), and `order_reference` is stored hyphenated (`ORD-260804-001`), so an
   officer typing what they can physically see would otherwise miss every time.
   `flows-and-states.md` Flow 1's "multiple matches" branch still occurs naturally -- one plate can
   carry more than one live shipment -- without any fuzziness being introduced to produce it.

3. **Out of scope is indistinguishable from non-existent.** A truck at another facility does not
   produce a "wrong facility" message; it produces `NO_MATCH`, the same as a plate that matches
   nothing. Same discipline `repositories.scope.assert_shipment_in_carrier_fleet` documents for
   the carrier portal -- a distinguishable refusal leaks existence by response shape alone.

4. **This is a read; it opens no transaction of its own and writes no audit row.** The five writes
   each leave an `audit_logs` trace because each records a fact about the world. A lookup does not.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.repositories.scope import resolve_facility_scope
from app.services.gate_yard_service import WAITING_STATES

# Shortest query worth running. Matches `search_service.search_records`'s own floor so the two
# search surfaces refuse the same inputs the same way. Measured against the *normalised* needle,
# not the raw string: "a-b" is a two-character identifier, "!!" is not an identifier at all.
MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 64

# Disambiguation-list cap (`flows-and-states.md` Flow 1.4 -- "a short disambiguation list").
# Fetching one more than this is what makes `truncated` an honest field rather than a guess.
MAX_MATCHES = 10

# How long a gated-out truck stays findable.
#
# **Calibrated, not documented -- flagged as an owner decision in this tool's own report.** Without
# a recency bound, an exact plate match returns every trip that vehicle ever made (a plate is
# UNIQUE per `vehicles` row, and one vehicle accumulates many `shipments` over time), which would
# turn Flow 1's "short disambiguation list" into a scroll of finished history. A bound is therefore
# structurally required, and its value has no source in the design docs. 12 hours is one gate
# shift: this surface's unit of work is explicitly a shift (`flows-and-states.md` Flow 0/Flow 9 --
# identity is set once per shift and cleared at its end), a truck gated out during the officer's
# own shift is still their concern (`edge-cases.md` #6's re-search case), and one gated out a week
# ago is not -- `flows-and-states.md` Flow 8 states the surface has no history view at all.
RECENT_GATE_OUT_HOURS = 12

# The one valid next action per `screens.md` section 3's state -> action table, as a code rather
# than a label (the kiosk owns copy). `None` is the terminal case `edge-cases.md` #6 requires:
# a gated-out truck renders its identity card with no button at all, not a disabled one.
NEXT_ACTIONS = (
    "GATE_IN",
    "CALL_TO_DOCK",
    "DOCK_IN",
    "START_UNLOAD",
    "END_UNLOAD",
    "GATE_OUT",
)

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")


class GateTruckMatch(BaseModel):
    """One truck the officer could be standing in front of.

    Carries everything `components.md` section 3's truck-identity card renders **and** the two
    arguments the follow-on write needs (`shipment_id` for all five tools, `appointment_dock_id`
    for `record_dock_in`, which `flows-and-states.md` Flow 5 requires the kiosk to read off the
    appointment rather than let the officer choose) -- so Flow 1 -> Flow 2 -> Flow 3..7 never needs
    a second round trip.
    """

    model_config = ConfigDict(extra="forbid")

    shipment_id: str
    order_reference: str
    facility_id: str
    current_status: str
    registration_number: str
    driver_name: str
    carrier_name: str

    checkin_id: str | None = None
    queue_state: str = "NOT_QUEUED"
    queue_position: int | None = None
    arrival_state: str | None = None
    actual_dock_id: str | None = None
    gate_in_ts: datetime | None = None
    dock_in_ts: datetime | None = None
    unload_start_ts: datetime | None = None
    unload_end_ts: datetime | None = None
    gate_out_ts: datetime | None = None
    # Only set once the cycle is terminal. Same subtraction `record_gate_out` returns, computed
    # here so `edge-cases.md` #6's terminal card ("dwell 1h 22m") does not require the kiosk to
    # redo date arithmetic the server already owns.
    dwell_min: float | None = None

    appointment_id: str | None = None
    appointment_status: str | None = None
    appointment_dock_id: str | None = None
    appointment_dock_code: str | None = None
    slot_start_ts: datetime | None = None
    slot_end_ts: datetime | None = None

    next_action: str | None = None


class GateTruckSearchResult(BaseModel):
    """Typed outcome for Flow 1, one code per branch (section 7.5's principle 2: never prose)."""

    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    # MATCH (Flow 1.2) · NO_MATCH (Flow 1.3) · MULTIPLE_MATCHES (Flow 1.4).
    code: str
    query: str
    # The scope actually searched, echoed back for the kiosk to display. Derived from the verified
    # token (note 1); never read from the request.
    facility_id: str | None = None
    match_count: int = 0
    truncated: bool = False
    matches: list[GateTruckMatch] = []


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalise_identifier(value: str) -> str:
    """Strip every non-alphanumeric character and upper-case what remains.

    Pure and exported so the exact match semantics are unit-testable directly against the real
    stored formats (`RJ14GT4101`, `ORD-260804-001`, `SHP1015`) rather than only through SQL. The
    SQL side applies the byte-identical transformation via `regexp_replace(..., '[^A-Za-z0-9]',
    '', 'g')`; if one side changes, the other must change with it.
    """
    return _NON_ALNUM.sub("", value).upper()


def derive_next_action(
    *,
    queue_state: str | None,
    gate_in_ts: datetime | None,
    unload_start_ts: datetime | None,
    unload_end_ts: datetime | None,
    gate_out_ts: datetime | None,
) -> str | None:
    """`screens.md` section 3's state -> action table, evaluated server-side.

    Pure and exported for the same reason `gate_yard_service.classify_arrival` is: it is a business
    rule, not plumbing. It lives here rather than in the kiosk because section 7.5.2 states the
    state machine is "enforced server-side, not by the kiosk" -- a kiosk that derived its own next
    action would be a second copy of `QUEUE_TRANSITIONS` free to drift from the one the writes
    actually enforce. The kiosk may still render its own label; this only says which action is the
    one valid one.

    Ordering matters. `gate_out_ts` is checked before anything else because it is terminal
    regardless of `queue_state` (`edge-cases.md` #6), and `gate_in_ts` is checked before the state
    because every write except `record_gate_in` refuses a truck with a null `gate_in_ts` outright
    (`NOT_CHECKED_IN`) -- so the state column alone is not a safe discriminator.
    """
    if gate_out_ts is not None:
        return None
    if gate_in_ts is None:
        return "GATE_IN"

    state = (queue_state or "NOT_QUEUED").upper()
    if state == "NOT_QUEUED":
        return "GATE_IN"
    if state in WAITING_STATES:
        return "CALL_TO_DOCK"
    if state == "CALLED_TO_DOCK":
        return "DOCK_IN"
    if state == "IN_DOCK":
        if unload_start_ts is None:
            return "START_UNLOAD"
        if unload_end_ts is None:
            return "END_UNLOAD"
        # Not reachable through the shipped writes -- `record_unload_start_end` moves the row to
        # COMPLETED in the same statement that sets `unload_end_ts`. Handled rather than left to
        # fall through, so a row repaired by hand still offers the officer the correct last step.
        return "GATE_OUT"
    if state == "COMPLETED":
        return "GATE_OUT"
    return None


def _dwell_min(gate_in_ts: datetime | None, gate_out_ts: datetime | None) -> float | None:
    if gate_in_ts is None or gate_out_ts is None:
        return None
    return round((gate_out_ts - gate_in_ts).total_seconds() / 60.0, 2)


def _to_match(row: dict[str, Any]) -> GateTruckMatch:
    queue_state = str(row["queue_state"] or "NOT_QUEUED")
    return GateTruckMatch(
        shipment_id=str(row["shipment_id"]),
        order_reference=str(row["order_reference"]),
        facility_id=str(row["facility_id"]),
        current_status=str(row["current_status"]),
        registration_number=str(row["registration_number"]),
        driver_name=str(row["driver_name"]),
        carrier_name=str(row["carrier_name"]),
        checkin_id=str(row["checkin_id"]) if row["checkin_id"] else None,
        queue_state=queue_state,
        queue_position=row["queue_position"],
        arrival_state=row["arrival_state"],
        actual_dock_id=row["actual_dock_id"],
        gate_in_ts=row["gate_in_ts"],
        dock_in_ts=row["dock_in_ts"],
        unload_start_ts=row["unload_start_ts"],
        unload_end_ts=row["unload_end_ts"],
        gate_out_ts=row["gate_out_ts"],
        dwell_min=_dwell_min(row["gate_in_ts"], row["gate_out_ts"]),
        appointment_id=row["appointment_id"],
        appointment_status=row["appointment_status"],
        appointment_dock_id=row["appointment_dock_id"],
        appointment_dock_code=row["appointment_dock_code"],
        slot_start_ts=row["slot_start_ts"],
        slot_end_ts=row["slot_end_ts"],
        next_action=derive_next_action(
            queue_state=queue_state,
            gate_in_ts=row["gate_in_ts"],
            unload_start_ts=row["unload_start_ts"],
            unload_end_ts=row["unload_end_ts"],
            gate_out_ts=row["gate_out_ts"],
        ),
    )


# One statement, deliberately. The identity card needs the shipment, its vehicle (the plate), its
# driver, its carrier, its current check-in and its current appointment's dock and interval; issuing
# five reads to assemble one card would put four extra round trips inside the officer's single
# most-frequent interaction. The LATERAL sub-select reproduces `gate_yard_service._active_appointment`
# exactly (same `is_current`/status filter, same `slot_start_ts ASC LIMIT 1` tie-break), so the dock
# this read hands the kiosk is the same dock `record_dock_in` will compare against.
_SEARCH_SQL = """
SELECT s.shipment_id,
       s.order_reference,
       s.destination_facility_id AS facility_id,
       s.current_status,
       v.registration_number,
       d.driver_name,
       c.carrier_name,
       fc.checkin_id,
       fc.queue_state,
       fc.queue_position,
       fc.arrival_state,
       fc.actual_dock_id,
       fc.gate_in_ts,
       fc.dock_in_ts,
       fc.unload_start_ts,
       fc.unload_end_ts,
       fc.gate_out_ts,
       apt.appointment_id,
       apt.appointment_status,
       apt.dock_id AS appointment_dock_id,
       apt.dock_code AS appointment_dock_code,
       apt.slot_start_ts,
       apt.slot_end_ts
FROM public.shipments s
JOIN public.vehicles v ON v.vehicle_id = s.vehicle_id
JOIN public.drivers d ON d.driver_id = s.driver_id
JOIN public.carriers c ON c.carrier_id = s.carrier_id
LEFT JOIN public.facility_checkins fc ON fc.shipment_id = s.shipment_id
LEFT JOIN LATERAL (
    SELECT a.appointment_id, a.appointment_status, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts,
           dk.dock_code
    FROM public.appointments a
    JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
    JOIN public.docks dk ON dk.dock_id = sl.dock_id
    WHERE a.shipment_id = s.shipment_id
      AND a.is_current = 1
      AND a.appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
    ORDER BY sl.slot_start_ts ASC
    LIMIT 1
) apt ON TRUE
WHERE (
        UPPER(REGEXP_REPLACE(s.shipment_id, '[^A-Za-z0-9]', '', 'g')) = :needle
     OR UPPER(REGEXP_REPLACE(s.order_reference, '[^A-Za-z0-9]', '', 'g')) = :needle
     OR UPPER(REGEXP_REPLACE(v.registration_number, '[^A-Za-z0-9]', '', 'g')) = :needle
      )
  AND (fc.gate_out_ts IS NULL OR fc.gate_out_ts >= :recent_cutoff)
  {facility_filter}
ORDER BY (fc.gate_out_ts IS NULL) DESC,
         fc.gate_in_ts DESC NULLS LAST,
         apt.slot_start_ts ASC NULLS LAST,
         s.shipment_id ASC
LIMIT :limit
"""


async def search_gate_yard_trucks(
    session: AsyncSession, ctx: ExecutionContext, *, query: str
) -> GateTruckSearchResult:
    """`GY-G1` / `UI-UX/04-gate-yard-kiosk/flows-and-states.md` Flow 1, section 7.5.2.

    Returns `MATCH` (one truck -- Flow 2 renders directly), `MULTIPLE_MATCHES` (the short
    disambiguation list of Flow 1.4) or `NO_MATCH` (Flow 1.3's named cause). `NO_MATCH` is a 200
    carrying an empty list, not a 404: a search that found nothing is an answer, not a failure, and
    Flow 1.3 needs the officer to stay on the search screen with the field still focused.

    Takes no facility argument by design -- see this module's docstring, note 1.
    """
    trimmed = query.strip()[:MAX_QUERY_LENGTH]
    needle = normalise_identifier(trimmed)
    if len(needle) < MIN_QUERY_LENGTH:
        raise AppError(
            f"Enter at least {MIN_QUERY_LENGTH} characters of a shipment ID or plate number.",
            code="QUERY_TOO_SHORT",
            status_code=422,
        )

    # `require_facility=False`: ADMIN legitimately resolves to None ("no facility filter"), which
    # is the same reach `assert_facility_write_scope` already grants them on the five writes. A
    # facility-bound operator with no mapped facility raises FORBIDDEN inside the resolver.
    scope = resolve_facility_scope(ctx, None)

    # Only the facility predicate is interpolated, and only from a server-derived value's
    # *presence* -- never its content. Same shape `search_service._search_shipments` uses.
    sql = _SEARCH_SQL.format(
        facility_filter="AND s.destination_facility_id = :facility_id" if scope else ""
    )
    params: dict[str, Any] = {
        "needle": needle,
        "recent_cutoff": datetime.now(timezone.utc) - timedelta(hours=RECENT_GATE_OUT_HOURS),
        # One more than the cap, so `truncated` reports a real overflow rather than guessing from
        # a full page.
        "limit": MAX_MATCHES + 1,
    }
    if scope:
        params["facility_id"] = scope

    rows = (await session.execute(text(sql), params)).mappings().all()
    truncated = len(rows) > MAX_MATCHES
    matches = [_to_match(dict(r)) for r in rows[:MAX_MATCHES]]

    if not matches:
        code = "NO_MATCH"
    elif len(matches) == 1:
        code = "MATCH"
    else:
        code = "MULTIPLE_MATCHES"

    return GateTruckSearchResult(
        as_of=_as_of(),
        code=code,
        query=trimmed,
        facility_id=scope,
        match_count=len(matches),
        truncated=truncated,
        matches=matches,
    )


__all__ = [
    "MAX_MATCHES",
    "MAX_QUERY_LENGTH",
    "MIN_QUERY_LENGTH",
    "NEXT_ACTIONS",
    "RECENT_GATE_OUT_HOURS",
    "GateTruckMatch",
    "GateTruckSearchResult",
    "derive_next_action",
    "normalise_identifier",
    "search_gate_yard_trucks",
]
