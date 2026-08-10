from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.services.ids import new_id
from app.services.scheduling.schemas import (
    FeasibilitySearchCommand,
    FeasibilitySearchResultDTO,
    FeasibleSlotDTO,
)


def _parse_ts(ts_str: str | None) -> datetime | None:
    if not ts_str:
        return None
    try:
        # Handle trailing Z or offsets
        clean = ts_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def check_dock_compatibility(
    dock: dict[str, Any],
    shipment: dict[str, Any],
    vehicle: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    notes = []
    dock_type = dock.get("dock_type", "STANDARD")
    req_type = shipment.get("required_dock_type", "ANY")

    if req_type != "ANY" and dock_type != req_type:
        return False, [f"Dock type {dock_type} does not match required {req_type}"]

    if shipment.get("temperature_control_required") == 1:
        if dock.get("supports_refrigerated") != 1:
            return False, ["Dock does not support refrigeration"]

    load_weight = shipment.get("load_weight_kg", 0)
    max_weight = dock.get("max_vehicle_weight_kg", 999999)
    if load_weight > max_weight:
        return False, [f"Shipment weight {load_weight}kg exceeds dock max {max_weight}kg"]

    if dock.get("dock_status") != "ACTIVE":
        return False, [f"Dock status is {dock.get('dock_status')}"]

    notes.append(f"Compatible {dock_type} bay")
    return True, notes


def check_arrival_feasibility(
    slot_start_ts: str,
    driver_eta_ts: str,
    buffer_minutes: int = 15,
) -> tuple[bool, float]:
    slot_dt = _parse_ts(slot_start_ts)
    eta_dt = _parse_ts(driver_eta_ts)

    if not slot_dt or not eta_dt:
        return False, 0.0

    earliest_usable_start = eta_dt + timedelta(minutes=buffer_minutes)
    if slot_dt < earliest_usable_start:
        return False, 0.0

    wait_minutes = max(0.0, (slot_dt - eta_dt).total_seconds() / 60.0)
    return True, wait_minutes


def score_and_rank_slots(
    candidate_slots: list[dict[str, Any]],
    priority_code: str,
    driver_eta_ts: str,
) -> list[FeasibleSlotDTO]:
    scored_dtos: list[FeasibleSlotDTO] = []

    priority_bonus = {
        "CRITICAL": 25.0,
        "HIGH": 15.0,
        "NORMAL": 0.0,
        "LOW": -10.0,
    }.get(priority_code, 0.0)

    for cand in candidate_slots:
        slot = cand["slot"]
        dock = cand["dock"]
        wait_min = cand["wait_minutes"]
        notes = cand["notes"]

        # Base score 100, penalize long wait times, add priority bonus
        wait_penalty = min(60.0, wait_min * 0.25)
        score = max(1.0, round(100.0 - wait_penalty + priority_bonus, 2))

        dto = FeasibleSlotDTO(
            slot_id=slot["slot_id"],
            facility_id=slot["facility_id"],
            dock_id=dock["dock_id"],
            dock_code=dock["dock_code"],
            dock_type=dock["dock_type"],
            slot_start_ts=slot["slot_start_ts"],
            slot_end_ts=slot["slot_end_ts"],
            score=score,
            wait_minutes_from_eta=round(wait_min, 1),
            state="SHOWING_ONLY",
            is_reserved=False,
            feasibility_notes=notes,
        )
        scored_dtos.append(dto)

    # Sort deterministically: score DESC, slot_start_ts ASC, dock_id ASC
    scored_dtos.sort(key=lambda s: (-s.score, s.slot_start_ts, s.dock_id))
    return scored_dtos


async def find_feasible_slots_service(
    session: AsyncSession,
    ctx: ExecutionContext,
    command: FeasibilitySearchCommand,
) -> FeasibilitySearchResultDTO:
    # 1. Fetch Shipment
    shipment_row = (
        await session.execute(
            text(
                """
                SELECT shipment_id, driver_id, vehicle_id, destination_facility_id,
                       product_category, load_weight_kg, required_dock_type,
                       temperature_control_required, priority_code, original_eta_ts,
                       latest_eta_ts, expected_unload_min, current_status
                FROM public.shipments
                WHERE shipment_id = :shipment_id
                """
            ),
            {"shipment_id": command.shipment_id},
        )
    ).mappings().first()

    if not shipment_row:
        raise AppError("Shipment not found.", code="NOT_FOUND", status_code=404)

    shipment = dict(shipment_row)

    # Authorization Check
    if ctx.is_driver:
        if shipment["driver_id"] != ctx.driver_id:
            raise AppError("Access denied to requested shipment.", code="FORBIDDEN", status_code=403)

    if ctx.is_operator and ctx.facility_id:
        if shipment["destination_facility_id"] != ctx.facility_id:
            raise AppError("Facility out of role scope.", code="FORBIDDEN", status_code=403)

    # 2. Determine Effective ETA
    effective_eta = (
        command.revised_eta_ts
        or shipment.get("latest_eta_ts")
        or shipment.get("original_eta_ts")
    )

    facility_id = shipment["destination_facility_id"]

    # 3. Fetch Vehicle
    vehicle_row = (
        await session.execute(
            text(
                """
                SELECT vehicle_id, vehicle_type_code, capacity_kg, refrigeration_capable
                FROM public.vehicles WHERE vehicle_id = :vehicle_id
                """
            ),
            {"vehicle_id": shipment["vehicle_id"]},
        )
    ).mappings().first()
    vehicle = dict(vehicle_row) if vehicle_row else None

    # 4. Fetch Active Docks for Facility
    dock_rows = (
        await session.execute(
            text(
                """
                SELECT dock_id, facility_id, dock_code, dock_type,
                       supports_refrigerated, max_vehicle_weight_kg, dock_status
                FROM public.docks
                WHERE facility_id = :facility_id AND dock_status = 'ACTIVE'
                """
            ),
            {"facility_id": facility_id},
        )
    ).mappings().all()

    compatible_docks: dict[str, tuple[dict[str, Any], list[str]]] = {}
    for d_row in dock_rows:
        d_dict = dict(d_row)
        is_comp, notes = check_dock_compatibility(d_dict, shipment, vehicle)
        if is_comp:
            compatible_docks[d_dict["dock_id"]] = (d_dict, notes)

    if not compatible_docks:
        now_iso = datetime.now(timezone.utc).isoformat()
        return FeasibilitySearchResultDTO(
            recommendation_id=new_id("REC"),
            version_hash=hashlib.md5(f"{command.shipment_id}-{now_iso}".encode()).hexdigest()[:10],
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
            shipment_id=command.shipment_id,
            destination_facility_id=facility_id,
            effective_arrival_ts=effective_eta,
            feasible_slots=[],
            total_found=0,
        )

    # 5. Fetch Open Slots for Facility
    dock_id_list = list(compatible_docks.keys())
    slots_rows = (
        await session.execute(
            text(
                """
                SELECT slot_id, facility_id, dock_id, slot_start_ts, slot_end_ts, slot_status
                FROM public.appointment_slots
                WHERE facility_id = :facility_id AND slot_status = 'OPEN'
                  AND dock_id = ANY(:dock_ids)
                ORDER BY slot_start_ts ASC
                """
            ),
            {"facility_id": facility_id, "dock_ids": dock_id_list},
        )
    ).mappings().all()

    # 6. Fetch Occupied Slot IDs
    occupied_rows = (
        await session.execute(
            text(
                """
                SELECT slot_id FROM public.appointments
                WHERE appointment_status IN ('CONFIRMED', 'PENDING_CONFIRMATION', 'IN_PROGRESS')
                  AND is_current = 1
                """
            )
        )
    ).mappings().all()
    occupied_slot_ids = {r["slot_id"] for r in occupied_rows}

    # 7. Evaluate Candidates
    candidate_slots = []
    for s_row in slots_rows:
        s_dict = dict(s_row)
        slot_id = s_dict["slot_id"]
        dock_id = s_dict["dock_id"]

        if slot_id in occupied_slot_ids:
            continue

        dock_dict, dock_notes = compatible_docks[dock_id]
        is_feasible, wait_min = check_arrival_feasibility(
            slot_start_ts=s_dict["slot_start_ts"],
            driver_eta_ts=effective_eta,
        )

        if not is_feasible:
            continue

        # Filter by command after_time_ts if provided
        if command.after_time_ts:
            cmd_after_dt = _parse_ts(command.after_time_ts)
            slot_start_dt = _parse_ts(s_dict["slot_start_ts"])
            if cmd_after_dt and slot_start_dt and slot_start_dt < cmd_after_dt:
                continue

        candidate_slots.append(
            {
                "slot": s_dict,
                "dock": dock_dict,
                "wait_minutes": wait_min,
                "notes": dock_notes,
            }
        )

    # 8. Score and Rank
    ranked_dtos = score_and_rank_slots(
        candidate_slots,
        priority_code=shipment.get("priority_code", "NORMAL"),
        driver_eta_ts=effective_eta,
    )

    now_dt = datetime.now(timezone.utc)
    rec_id = new_id("REC")
    version_raw = f"{command.shipment_id}:{effective_eta}:{len(ranked_dtos)}:{now_dt.isoformat()}"
    v_hash = hashlib.md5(version_raw.encode()).hexdigest()[:10]

    return FeasibilitySearchResultDTO(
        recommendation_id=rec_id,
        version_hash=v_hash,
        expires_at=(now_dt + timedelta(minutes=15)).isoformat(),
        shipment_id=command.shipment_id,
        destination_facility_id=facility_id,
        effective_arrival_ts=effective_eta,
        feasible_slots=ranked_dtos,
        total_found=len(ranked_dtos),
    )
