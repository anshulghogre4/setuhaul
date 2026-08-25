"""Planner dock-blocking writes -- SOLUTION_DESIGN.md section 7.5.1, FR-PLN-007 / FR-PLN-008.

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

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.repositories.scope import assert_facility_write_scope
from app.services.idempotency import lookup_idempotency, payload_hash, store_idempotency
from app.services.ids import new_id

# `dock_status_events.event_type` values that mean "this dock is unavailable". Read live from the
# CHECK constraint 2026-08-23: MAINTENANCE, BREAKDOWN, CAPACITY_REDUCTION, REOPENED, MANUAL_BLOCK.
# A planner-initiated block is MANUAL_BLOCK; the others are recorded by other actors or the seed.
MANUAL_BLOCK_EVENT_TYPE = "MANUAL_BLOCK"
BLOCKING_EVENT_TYPES = ("MAINTENANCE", "BREAKDOWN", "CAPACITY_REDUCTION", "MANUAL_BLOCK")

ACTIVE_APPOINTMENT_STATUSES = ("PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS")


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
    "DockBlockImpact",
    "DockBlockResult",
    "MANUAL_BLOCK_EVENT_TYPE",
    "block_dock",
    "end_dock_block",
    "get_dock_block_impact",
]
