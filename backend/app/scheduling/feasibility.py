from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.scheduling.constraints import load_scheduling_constraints

ACTIVE_APPOINTMENT_STATUSES = frozenset({"PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS"})
CANCELLED_SHIPMENT_STATUSES = frozenset({"COMPLETED", "CANCELLED"})
PRIORITY_RANK = {"CRITICAL": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3}


class FeasibleSlotOption(BaseModel):
    slot_id: str
    facility_id: str
    dock_id: str
    dock_code: str
    dock_type: str
    slot_start_ts: str
    slot_end_ts: str
    feasible_start_ts: str
    feasible_end_ts: str
    ranking_explanation: list[str]
    checked_constraints: list[str]
    option_status: str = "DISPLAYED_NOT_RESERVED"


class InfeasibleSlotReason(BaseModel):
    slot_id: str | None = None
    failure_code: str
    message: str


class FeasibleSlotsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_of: str
    source: str = "postgresql"
    freshness: str = "live"
    policy_version: str
    shipment_id: str
    facility_id: str
    effective_eta_ts: str
    eta_source: str
    expected_unload_min: int
    options_are_reserved: bool = False
    options: list[FeasibleSlotOption]
    rejected_reasons: list[InfeasibleSlotReason]
    escalation: dict[str, Any] | None = None
    current_active_appointment: dict[str, Any] | None = None
    note: str = (
        "Displayed options are not reserved. A later request/hold/confirm flow must "
        "transactionally revalidate the selected slot."
    )


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: str) -> datetime:
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        raise ValueError("Timestamp must include timezone offset.")
    return parsed


def _parse_local_time(value: str) -> time:
    return time.fromisoformat(value.strip())


def _facility_window_ok(start_dt: datetime, end_dt: datetime, *, tz_name: str, open_time: str, close_time: str) -> bool:
    tz = ZoneInfo(tz_name)
    local_start = start_dt.astimezone(tz)
    local_end = end_dt.astimezone(tz)
    if local_start.date() != local_end.date():
        return False
    return _parse_local_time(open_time) <= local_start.time() and local_end.time() <= _parse_local_time(close_time)


def _dock_type_ok(required: str, actual: str) -> bool:
    return required == "ANY" or required == actual


def _explain_option(*, shipment: dict[str, Any], eta_dt: datetime, option: dict[str, Any]) -> list[str]:
    return [
        f"Latest authoritative ETA {eta_dt.isoformat()} fits inside this slot with unload duration.",
        f"Dock {option['dock_code']} is compatible with required dock type {shipment['required_dock_type']}.",
        "No active appointment currently occupies the slot.",
        "Ranked by deterministic policy: earliest feasible fit, then stable slot id.",
    ]


def evaluate_candidate_slot(
    *,
    shipment: dict[str, Any],
    facility: dict[str, Any],
    eta_dt: datetime,
    candidate: dict[str, Any],
    checked_constraints: list[str],
) -> tuple[FeasibleSlotOption | None, InfeasibleSlotReason | None]:
    slot_id = str(candidate["slot_id"])
    slot_start = _parse_timestamp(str(candidate["slot_start_ts"]))
    slot_end = _parse_timestamp(str(candidate["slot_end_ts"]))
    unload_min = int(shipment["expected_unload_min"])
    feasible_start = max(eta_dt, slot_start)
    feasible_end = feasible_start.timestamp() + unload_min * 60
    feasible_end_dt = datetime.fromtimestamp(feasible_end, tz=feasible_start.tzinfo)

    if candidate["slot_status"] != "OPEN":
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="SLOT_NOT_OPEN",
            message=f"Slot status is {candidate['slot_status']}.",
        )
    if candidate.get("active_appointment_id"):
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="SLOT_CAPACITY_UNAVAILABLE",
            message="An active appointment already occupies this slot.",
        )
    if candidate.get("active_dock_event_id"):
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="DOCK_UNAVAILABLE",
            message="A dock event overlaps this slot.",
        )
    if candidate["dock_status"] != "ACTIVE":
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="DOCK_UNAVAILABLE",
            message=f"Dock status is {candidate['dock_status']}.",
        )
    if not _dock_type_ok(str(shipment["required_dock_type"]), str(candidate["dock_type"])):
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="DOCK_INCOMPATIBLE_VEHICLE",
            message=f"Shipment requires {shipment['required_dock_type']} dock, candidate is {candidate['dock_type']}.",
        )
    if int(shipment["temperature_control_required"]) and not int(candidate["supports_refrigerated"]):
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="DOCK_INCOMPATIBLE_LOAD",
            message="Temperature-controlled shipment requires refrigerated dock support.",
        )
    if int(shipment["load_weight_kg"]) > int(candidate["max_vehicle_weight_kg"]):
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="DOCK_INCOMPATIBLE_VEHICLE",
            message="Shipment load exceeds dock vehicle weight limit.",
        )
    if feasible_end_dt > slot_end:
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="ETA_AFTER_SLOT_WINDOW",
            message="ETA plus unload duration does not fit inside the slot window.",
        )
    if not _facility_window_ok(
        slot_start,
        slot_end,
        tz_name=str(facility["timezone"]),
        open_time=str(facility["open_time"]),
        close_time=str(facility["close_time"]),
    ):
        return None, InfeasibleSlotReason(
            slot_id=slot_id,
            failure_code="FACILITY_CLOSED",
            message="Slot falls outside facility operating hours.",
        )

    return (
        FeasibleSlotOption(
            slot_id=slot_id,
            facility_id=str(candidate["facility_id"]),
            dock_id=str(candidate["dock_id"]),
            dock_code=str(candidate["dock_code"]),
            dock_type=str(candidate["dock_type"]),
            slot_start_ts=slot_start.isoformat(),
            slot_end_ts=slot_end.isoformat(),
            feasible_start_ts=feasible_start.isoformat(),
            feasible_end_ts=feasible_end_dt.isoformat(),
            ranking_explanation=_explain_option(shipment=shipment, eta_dt=eta_dt, option=candidate),
            checked_constraints=checked_constraints,
        ),
        None,
    )


def _assert_scope(ctx: ExecutionContext, shipment: dict[str, Any]) -> None:
    if ctx.is_driver:
        if shipment["driver_id"] != ctx.driver_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
        return
    if ctx.is_operator:
        if shipment["destination_facility_id"] != ctx.facility_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
        return
    if ctx.is_admin:
        return
    raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)


async def find_feasible_slots(
    session: AsyncSession,
    ctx: ExecutionContext,
    shipment_id: str,
    *,
    limit: int = 5,
) -> FeasibleSlotsResult:
    constraints = load_scheduling_constraints()
    checked_constraints = sorted(constraints.hard_constraint_ids())

    shipment = (
        await session.execute(
            text(
                """
                SELECT s.shipment_id, s.driver_id, s.vehicle_id, s.destination_facility_id,
                       s.priority_code, s.required_dock_type, s.temperature_control_required,
                       s.load_weight_kg, s.expected_unload_min, s.current_status,
                       le.effective_eta_ts, le.eta_source, le.eta_confidence
                FROM public.shipments s
                JOIN public.v_latest_eta le ON le.shipment_id = s.shipment_id
                WHERE s.shipment_id = :shipment_id
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()
    if shipment is None:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)
    shipment_data = dict(shipment)
    _assert_scope(ctx, shipment_data)

    if shipment_data["current_status"] in CANCELLED_SHIPMENT_STATUSES:
        raise AppError(
            "Shipment is not eligible for slot search.",
            code="SHIPMENT_NOT_ACTIVE",
            status_code=409,
        )

    facility = (
        await session.execute(
            text(
                """
                SELECT facility_id, facility_name, timezone, open_time, close_time, active_flag
                FROM public.facilities
                WHERE facility_id = :facility_id
                """
            ),
            {"facility_id": shipment_data["destination_facility_id"]},
        )
    ).mappings().first()
    if facility is None or not int(facility["active_flag"]):
        raise AppError("Destination facility is not active.", code="FACILITY_UNAVAILABLE", status_code=409)
    facility_data = dict(facility)

    active_appt = (
        await session.execute(
            text(
                """
                SELECT a.appointment_id, a.shipment_id, a.slot_id, a.appointment_status,
                       a.is_current, sl.facility_id, sl.dock_id, sl.slot_start_ts, sl.slot_end_ts
                FROM public.appointments a
                JOIN public.appointment_slots sl ON sl.slot_id = a.slot_id
                WHERE a.shipment_id = :shipment_id
                  AND a.is_current = 1
                  AND a.appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                ORDER BY a.updated_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"shipment_id": shipment_id},
        )
    ).mappings().first()

    eta_dt = _parse_timestamp(str(shipment_data["effective_eta_ts"]))
    candidates = (
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
                 AND de.event_start_ts < sl.slot_end_ts
                 AND (de.event_end_ts IS NULL OR de.event_end_ts > sl.slot_start_ts)
                WHERE sl.facility_id = :facility_id
                  AND sl.slot_end_ts > :eta_ts
                ORDER BY sl.slot_start_ts, sl.slot_id
                LIMIT 200
                """
            ),
            {"facility_id": shipment_data["destination_facility_id"], "eta_ts": eta_dt.isoformat()},
        )
    ).mappings().all()

    options: list[FeasibleSlotOption] = []
    rejected: list[InfeasibleSlotReason] = []
    for row in candidates:
        option, reason = evaluate_candidate_slot(
            shipment=shipment_data,
            facility=facility_data,
            eta_dt=eta_dt,
            candidate=dict(row),
            checked_constraints=checked_constraints,
        )
        if option:
            options.append(option)
        elif reason and len(rejected) < 20:
            rejected.append(reason)
        if len(options) >= limit:
            break

    options.sort(
        key=lambda option: (
            _parse_timestamp(option.slot_start_ts),
            PRIORITY_RANK.get(str(shipment_data["priority_code"]), 9),
            option.slot_id,
        )
    )

    escalation = None
    if not options:
        escalation = {
            "required": True,
            "shipment_id": shipment_id,
            "facility_id": shipment_data["destination_facility_id"],
            "as_of": _as_of(),
            "policy_version": constraints.policy_version,
            "checked_constraints": checked_constraints,
            "blocking_reasons": [reason.model_dump() for reason in rejected[:10]]
            or [{"failure_code": "NO_CANDIDATE_SLOTS", "message": "No candidate slots were found."}],
            "recommended_human_queue": "OPERATIONS_EXCEPTION_QUEUE",
        }

    return FeasibleSlotsResult(
        as_of=_as_of(),
        policy_version=constraints.policy_version,
        shipment_id=shipment_id,
        facility_id=str(shipment_data["destination_facility_id"]),
        effective_eta_ts=eta_dt.isoformat(),
        eta_source=str(shipment_data["eta_source"]),
        expected_unload_min=int(shipment_data["expected_unload_min"]),
        options=options[:limit],
        rejected_reasons=rejected,
        escalation=escalation,
        current_active_appointment=dict(active_appt) if active_appt else None,
    )

