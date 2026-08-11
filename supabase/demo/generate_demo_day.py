#!/usr/bin/env python3
"""Generate deterministic, additive SetuHaul demo-day SQL."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Facility:
    facility_id: str
    code: str
    name: str
    city: str
    state: str
    opens: time
    closes: time
    docks: tuple[tuple[str, str, int, int], ...]
    slot_dock_count: int


FACILITIES = (
    Facility(
        "FAC-JAI-01",
        "JAI",
        "SetuHaul Jaipur Distribution Centre",
        "Jaipur",
        "Rajasthan",
        time(6),
        time(22),
        (
            ("DOCK-JAI-D1", "STANDARD", 0, 20_000),
            ("DOCK-JAI-D2", "STANDARD", 0, 25_000),
            ("DOCK-JAI-D3", "STANDARD", 0, 20_000),
            ("DOCK-JAI-D4", "STANDARD", 0, 25_000),
            ("DOCK-JAI-D5", "REEFER", 1, 22_000),
            ("DOCK-JAI-D6", "HEAVY", 0, 35_000),
        ),
        6,
    ),
    Facility(
        "FAC-GGN-01",
        "GGN",
        "SetuHaul Gurugram Cross-Dock",
        "Gurugram",
        "Haryana",
        time(7),
        time(21),
        (
            ("DOCK-GGN-D1", "STANDARD", 0, 22_000),
            ("DOCK-GGN-D2", "STANDARD", 0, 22_000),
            ("DOCK-GGN-D3", "REEFER", 1, 20_000),
        ),
        3,
    ),
    Facility(
        "FAC-DEL-01",
        "DEL",
        "SetuHaul Delhi Consolidation Hub",
        "Delhi",
        "Delhi",
        time(8),
        time(16),
        (
            ("D16-DOCK-DEL-D1", "STANDARD", 0, 22_000),
            ("D16-DOCK-DEL-D2", "REEFER", 1, 20_000),
            ("D16-DOCK-DEL-D3", "STANDARD", 0, 24_000),
            ("D16-DOCK-DEL-D4", "HEAVY", 0, 36_000),
        ),
        2,
    ),
    Facility(
        "FAC-AMD-01",
        "AMD",
        "SetuHaul Ahmedabad Freight Centre",
        "Ahmedabad",
        "Gujarat",
        time(8),
        time(16),
        (
            ("D16-DOCK-AMD-D1", "STANDARD", 0, 22_000),
            ("D16-DOCK-AMD-D2", "HEAVY", 0, 36_000),
            ("D16-DOCK-AMD-D3", "STANDARD", 0, 24_000),
            ("D16-DOCK-AMD-D4", "REEFER", 1, 20_000),
        ),
        2,
    ),
    Facility(
        "FAC-PNQ-01",
        "PNQ",
        "SetuHaul Pune Logistics Park",
        "Pune",
        "Maharashtra",
        time(8),
        time(16),
        (
            ("D16-DOCK-PNQ-D1", "STANDARD", 0, 22_000),
            ("D16-DOCK-PNQ-D2", "REEFER", 1, 20_000),
            ("D16-DOCK-PNQ-D3", "STANDARD", 0, 24_000),
            ("D16-DOCK-PNQ-D4", "HEAVY", 0, 36_000),
        ),
        2,
    ),
    Facility(
        "FAC-BLR-01",
        "BLR",
        "SetuHaul Bengaluru Distribution Campus",
        "Bengaluru",
        "Karnataka",
        time(8),
        time(16),
        (
            ("D16-DOCK-BLR-D1", "STANDARD", 0, 22_000),
            ("D16-DOCK-BLR-D2", "HEAVY", 0, 36_000),
            ("D16-DOCK-BLR-D3", "STANDARD", 0, 24_000),
            ("D16-DOCK-BLR-D4", "REEFER", 1, 20_000),
        ),
        2,
    ),
)


class DemoData:
    """Small table-shaped accumulator with deterministic SQL rendering."""

    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = {}

    def add(self, table: str, **values: Any) -> None:
        self.rows.setdefault(table, []).append(values)

    def count(self, table: str) -> int:
        return len(self.rows.get(table, ()))


def ts(day: date, hour: int, minute: int = 0) -> str:
    return datetime.combine(day, time(hour, minute), IST).isoformat(timespec="seconds")


def iso(value: datetime) -> str:
    return value.astimezone(IST).isoformat(timespec="seconds")


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def chunks(values: list[dict[str, Any]], size: int = 400) -> Iterable[list[dict[str, Any]]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def render_table(table: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    columns = tuple(rows[0])
    statements: list[str] = []
    for batch in chunks(rows):
        values = ",\n".join(
            "  (" + ", ".join(sql_literal(row[column]) for column in columns) + ")"
            for row in batch
        )
        statements.append(
            f"INSERT INTO public.{table} ({', '.join(columns)})\n"
            f"VALUES\n{values}\nON CONFLICT DO NOTHING;"
        )
    return "\n\n".join(statements)


def build_demo_data(demo_day: date) -> tuple[DemoData, dict[str, Any]]:
    data = DemoData()
    day_code = f"D{demo_day.day:02d}"
    period_start = demo_day - timedelta(days=6)
    created_at = ts(period_start, 0)

    # Four additive facilities. The two hero facilities remain untouched.
    for facility in FACILITIES[2:]:
        data.add(
            "facilities",
            facility_id=facility.facility_id,
            facility_name=facility.name,
            city=facility.city,
            state=facility.state,
            timezone="Asia/Kolkata",
            open_time=facility.opens.strftime("%H:%M"),
            close_time=facility.closes.strftime("%H:%M"),
            checkin_grace_min=30,
            default_unload_min=60,
            active_flag=1,
        )
        data.add(
            "facility_rules",
            rule_id=f"{day_code}-RULE-{facility.code}-01",
            facility_id=facility.facility_id,
            rule_type="NO_SHOW_GRACE_MIN",
            rule_value="30",
            description="Demo-day no-show grace period.",
            effective_from=ts(period_start, 0),
            effective_to=None,
            active_flag=1,
        )
        data.add(
            "facility_rules",
            rule_id=f"{day_code}-RULE-{facility.code}-02",
            facility_id=facility.facility_id,
            rule_type="LAST_NEW_START_TIME",
            rule_value=facility.closes.strftime("%H:%M"),
            description="Demo-day last start follows facility closing time.",
            effective_from=ts(period_start, 0),
            effective_to=None,
            active_flag=1,
        )
        for dock_id, dock_type, refrigerated, max_weight in facility.docks:
            data.add(
                "docks",
                dock_id=dock_id,
                facility_id=facility.facility_id,
                dock_code=dock_id.rsplit("-", 1)[-1],
                dock_type=dock_type,
                supports_refrigerated=refrigerated,
                max_vehicle_weight_kg=max_weight,
                dock_status="ACTIVE",
            )

    # Ninety additional drivers and matching vehicles.
    new_driver_ids: list[str] = []
    new_vehicle_ids: list[str] = []
    vehicle_types = ("20FT", "32FT_SXL", "32FT_MXL", "REEFER_32", "HEAVY_40")
    capacities = (9_000, 15_000, 22_000, 18_000, 32_000)
    for index in range(1, 91):
        driver_id = f"{day_code}-DRV-{index:03d}"
        vehicle_id = f"{day_code}-VEH-{index:03d}"
        carrier_id = f"CAR{((index - 1) % 4) + 1:03d}"
        type_index = (index - 1) % len(vehicle_types)
        new_driver_ids.append(driver_id)
        new_vehicle_ids.append(vehicle_id)
        data.add(
            "drivers",
            driver_id=driver_id,
            carrier_id=carrier_id,
            driver_name=f"Demo Driver {index:03d}",
            phone=f"+91-91616{index:05d}",
            licence_number=f"D16DL{index:06d}",
            home_base_city=FACILITIES[index % len(FACILITIES)].city,
            driver_status="ACTIVE",
        )
        data.add(
            "vehicles",
            vehicle_id=vehicle_id,
            carrier_id=carrier_id,
            vehicle_type_code=vehicle_types[type_index],
            registration_number=f"DD16GT{index:04d}",
            capacity_kg=capacities[type_index],
            refrigeration_capable=1 if vehicle_types[type_index] == "REEFER_32" else 0,
            active_flag=1,
        )

    # App users intentionally do not create Supabase Auth identities.
    for offset, driver_number in enumerate(range(4, 16), start=201):
        driver_id = f"DRV{driver_number:03d}"
        data.add(
            "users",
            user_id=f"USR{offset}",
            role_id="ROL001",
            employee_code=None,
            full_name=f"Demo Contention Driver {driver_number:03d}",
            email=f"driver.drv{driver_number:03d}@setuhaul.com",
            phone_number=f"+91-91717{driver_number:05d}",
            password_hash="!auth_only!",
            driver_id=driver_id,
            facility_id="FAC-JAI-01",
            is_active=1,
            last_login_ts=None,
            created_at=created_at,
            updated_at=created_at,
            auth_user_id=None,
        )

    # Roughly 30-minute capacity. Existing hero docks are all represented.
    # New sites use two representative slot-enabled docks each to keep the
    # full seven-day inventory in the requested 2,000-3,000 row range.
    slots: list[dict[str, Any]] = []
    slot_index = 0
    race_window = (demo_day, "DOCK-JAI-D1", time(19), time(19, 30))
    for day_offset in range(7):
        current_day = period_start + timedelta(days=day_offset)
        for facility in FACILITIES:
            for dock_id, _dock_type, _refrigerated, _max_weight in facility.docks[
                : facility.slot_dock_count
            ]:
                cursor = datetime.combine(current_day, facility.opens, IST)
                close = datetime.combine(current_day, facility.closes, IST)
                while cursor < close:
                    end = cursor + timedelta(minutes=30)
                    slot_index += 1
                    slot_id = f"{day_code}-SLT-{slot_index:05d}"
                    if (
                        current_day,
                        dock_id,
                        cursor.time(),
                        end.time(),
                    ) == race_window:
                        slot_id = f"{day_code}-SLT-RACE"
                    row = {
                        "slot_id": slot_id,
                        "facility_id": facility.facility_id,
                        "dock_id": dock_id,
                        "slot_start_ts": iso(cursor),
                        "slot_end_ts": iso(end),
                        "slot_status": "OPEN",
                        "block_reason": None,
                        "created_at": created_at,
                    }
                    slots.append(row)
                    data.add("appointment_slots", **row)
                    cursor = end

    slot_by_key = {
        (row["dock_id"], row["slot_start_ts"]): row for row in slots
    }

    hero_specs: list[dict[str, Any]] = []
    baseline_vehicles = {index: f"VEH{index:03d}" for index in range(1, 16)}
    for index, driver_number in enumerate(range(4, 14), start=1):
        eta_minutes = 17 * 60 + 30 + (index - 1) * 10
        hero_specs.append(
            {
                "shipment_id": f"SHP-{day_code}-CONTEND-{index:02d}",
                "driver_id": f"DRV{driver_number:03d}",
                "vehicle_id": baseline_vehicles[driver_number],
                "eta": ts(demo_day, eta_minutes // 60, eta_minutes % 60),
                "dock_type": "STANDARD",
                "temperature": 0,
                "weight": 12_000 + index * 300,
                "status": "IN_TRANSIT",
                "priority": ("NORMAL", "HIGH", "NORMAL", "CRITICAL")[index % 4],
                "unload": 25,
            }
        )
    hero_specs.extend(
        [
            {
                "shipment_id": f"SHP-{day_code}-RACE-A",
                "driver_id": "DRV001",
                "vehicle_id": "VEH001",
                "eta": ts(demo_day, 18, 35),
                "dock_type": "STANDARD",
                "temperature": 0,
                "weight": 12_000,
                "status": "IN_TRANSIT",
                "priority": "HIGH",
                "unload": 25,
                "scenario": "same_slot_race",
            },
            {
                "shipment_id": f"SHP-{day_code}-RACE-B",
                "driver_id": "DRV002",
                "vehicle_id": "VEH002",
                "eta": ts(demo_day, 18, 40),
                "dock_type": "STANDARD",
                "temperature": 0,
                "weight": 16_000,
                "status": "IN_TRANSIT",
                "priority": "HIGH",
                "unload": 25,
                "scenario": "same_slot_race",
            },
            {
                "shipment_id": f"SHP-{day_code}-RAVI",
                "driver_id": "DRV001",
                "vehicle_id": "VEH001",
                "eta": ts(demo_day, 18, 30),
                "dock_type": "STANDARD",
                "temperature": 0,
                "weight": 11_500,
                "status": "IN_TRANSIT",
                "priority": "HIGH",
                "unload": 25,
                "scenario": "single_driver_happy_path",
            },
            {
                "shipment_id": f"SHP-{day_code}-NOSLOT",
                "driver_id": "DRV003",
                "vehicle_id": "VEH003",
                "eta": ts(demo_day, 21, 30),
                "dock_type": "HEAVY",
                "temperature": 1,
                "weight": 31_000,
                "status": "IN_TRANSIT",
                "priority": "CRITICAL",
                "unload": 90,
                "scenario": "no_feasible_slot",
            },
            {
                "shipment_id": f"SHP-{day_code}-MULTI-B",
                "driver_id": "DRV003",
                "vehicle_id": "VEH003",
                "eta": ts(demo_day, 19, 15),
                "dock_type": "STANDARD",
                "temperature": 0,
                "weight": 7_000,
                "status": "IN_TRANSIT",
                "priority": "NORMAL",
                "unload": 25,
                "scenario": "multi_shipment_driver",
            },
            {
                "shipment_id": f"SHP-{day_code}-EARLY",
                "driver_id": f"{day_code}-DRV-001",
                "vehicle_id": f"{day_code}-VEH-001",
                "eta": ts(demo_day, 17, 0),
                "dock_type": "STANDARD",
                "temperature": 0,
                "weight": 8_000,
                "status": "WAITING",
                "priority": "LOW",
                "unload": 45,
                "scenario": "facility_snapshot_early",
            },
            {
                "shipment_id": f"SHP-{day_code}-LATE",
                "driver_id": f"{day_code}-DRV-002",
                "vehicle_id": f"{day_code}-VEH-002",
                "eta": ts(demo_day, 17, 20),
                "dock_type": "STANDARD",
                "temperature": 0,
                "weight": 10_000,
                "status": "WAITING",
                "priority": "NORMAL",
                "unload": 60,
                "scenario": "facility_snapshot_late",
            },
            {
                "shipment_id": f"SHP-{day_code}-UNDOCK",
                "driver_id": f"{day_code}-DRV-003",
                "vehicle_id": f"{day_code}-VEH-003",
                "eta": ts(demo_day, 16, 30),
                "dock_type": "STANDARD",
                "temperature": 0,
                "weight": 14_000,
                "status": "IN_DOCK",
                "priority": "HIGH",
                "unload": 75,
                "scenario": "facility_snapshot_unloading",
            },
            {
                "shipment_id": f"SHP-{day_code}-FUTURE",
                "driver_id": f"{day_code}-DRV-004",
                "vehicle_id": f"{day_code}-VEH-004",
                "eta": ts(demo_day, 20, 45),
                "dock_type": "STANDARD",
                "temperature": 0,
                "weight": 9_000,
                "status": "IN_TRANSIT",
                "priority": "NORMAL",
                "unload": 45,
                "scenario": "facility_snapshot_future",
            },
        ]
    )

    shipment_rows: list[dict[str, Any]] = []

    def add_shipment(spec: dict[str, Any], ordinal: int, destination: str) -> None:
        eta_value = spec["eta"]
        driver_id = spec["driver_id"]
        carrier_id = (
            f"CAR{((int(driver_id.split('-')[-1]) - 1) % 4) + 1:03d}"
            if driver_id.startswith(day_code)
            else f"CAR{((int(driver_id[-3:]) - 1) % 4) + 1:03d}"
        )
        shipment = {
            "shipment_id": spec["shipment_id"],
            "order_reference": f"ORD-{day_code}-{ordinal:05d}",
            "carrier_id": carrier_id,
            "driver_id": driver_id,
            "vehicle_id": spec["vehicle_id"],
            "origin_name": f"Demo Origin {ordinal:03d}",
            "origin_city": FACILITIES[(ordinal + 1) % len(FACILITIES)].city,
            "destination_facility_id": destination,
            "customer_name": f"Demo Customer {(ordinal % 20) + 1:02d}",
            "product_category": (
                "Temperature controlled freight"
                if spec["temperature"]
                else "General freight"
            ),
            "load_weight_kg": spec["weight"],
            "pallet_count": 8 + ordinal % 28,
            "required_dock_type": spec["dock_type"],
            "temperature_control_required": spec["temperature"],
            "priority_code": spec["priority"],
            "planned_departure_ts": ts(period_start, 2 + ordinal % 8),
            "actual_departure_ts": ts(period_start, 2 + ordinal % 8, 15),
            "original_eta_ts": eta_value,
            "latest_eta_ts": eta_value,
            "expected_unload_min": spec["unload"],
            "current_status": spec["status"],
            "created_at": created_at,
            "updated_at": ts(demo_day, 16),
        }
        shipment_rows.append(shipment)
        data.add("shipments", **shipment)

    for ordinal, spec in enumerate(hero_specs, start=1):
        add_shipment(spec, ordinal, "FAC-JAI-01")

    # Bring the total to 640 shipments. Most are completed historical traffic.
    background_specs: list[dict[str, Any]] = []
    for background_index in range(1, 640 - len(hero_specs) + 1):
        shipment_day = period_start + timedelta(days=(background_index - 1) % 7)
        facility = FACILITIES[(background_index - 1) % len(FACILITIES)]
        driver_index = ((background_index - 1) % len(new_driver_ids))
        dock_cycle = ("STANDARD", "STANDARD", "REEFER", "HEAVY")
        dock_type = dock_cycle[background_index % len(dock_cycle)]
        temperature = 1 if dock_type == "REEFER" else 0
        status = "COMPLETED" if background_index <= 560 else (
            "ASSIGNED" if background_index % 3 == 0 else "IN_TRANSIT"
        )
        eta_hour = 9 + background_index % 7
        spec = {
            "shipment_id": f"SHP-{day_code}-BG-{background_index:04d}",
            "driver_id": new_driver_ids[driver_index],
            "vehicle_id": new_vehicle_ids[driver_index],
            "eta": ts(shipment_day, eta_hour, (background_index % 2) * 30),
            "dock_type": dock_type,
            "temperature": temperature,
            "weight": 30_000 if dock_type == "HEAVY" else 8_000 + background_index % 11_000,
            "status": status,
            "priority": ("LOW", "NORMAL", "NORMAL", "HIGH")[background_index % 4],
            "unload": 90 if dock_type == "HEAVY" else 60,
            "scenario": "background_volume",
        }
        background_specs.append(spec)
        add_shipment(spec, len(hero_specs) + background_index, facility.facility_id)

    shipment_by_id = {row["shipment_id"]: row for row in shipment_rows}

    # Every shipment has an original update; 160 have one later update.
    for index, shipment in enumerate(shipment_rows, start=1):
        data.add(
            "eta_updates",
            eta_update_id=f"{day_code}-ETA-{index:05d}",
            shipment_id=shipment["shipment_id"],
            source_type="ORIGINAL_PLAN",
            reported_by_driver_id=None,
            declared_eta_ts=shipment["original_eta_ts"],
            confidence_code="HIGH",
            delay_reason_code=None,
            note="Deterministic demo baseline ETA.",
            created_at=shipment["created_at"],
        )
    for index, shipment in enumerate(shipment_rows[:160], start=641):
        declared = datetime.fromisoformat(shipment["latest_eta_ts"]) + timedelta(minutes=15)
        data.add(
            "eta_updates",
            eta_update_id=f"{day_code}-ETA-{index:05d}",
            shipment_id=shipment["shipment_id"],
            source_type="DRIVER_DECLARED",
            reported_by_driver_id=shipment["driver_id"],
            declared_eta_ts=iso(declared),
            confidence_code="MEDIUM",
            delay_reason_code="TRAFFIC",
            note="Deterministic second ETA update for demo volume.",
            created_at=iso(declared - timedelta(minutes=45)),
        )

    # Explicit Jaipur scarcity: exactly four unoccupied standard slots remain
    # between 18:00 and 20:00, including D16-SLT-RACE.
    evening_slots = [
        row
        for row in slots
        if row["facility_id"] == "FAC-JAI-01"
        and row["dock_id"] in {"DOCK-JAI-D1", "DOCK-JAI-D2", "DOCK-JAI-D3", "DOCK-JAI-D4"}
        and ts(demo_day, 18) <= row["slot_start_ts"] < ts(demo_day, 20)
    ]
    open_evening_ids = {
        f"{day_code}-SLT-RACE",
        slot_by_key[("DOCK-JAI-D2", ts(demo_day, 18, 30))]["slot_id"],
        slot_by_key[("DOCK-JAI-D3", ts(demo_day, 19, 30))]["slot_id"],
        slot_by_key[("DOCK-JAI-D4", ts(demo_day, 18, 0))]["slot_id"],
    }
    occupied_evening = [row for row in evening_slots if row["slot_id"] not in open_evening_ids]

    appointment_rows: list[dict[str, Any]] = []

    def add_appointment(
        appointment_id: str,
        shipment_id: str,
        slot_id: str,
        status: str,
        is_current: int,
        booked_at: str,
    ) -> None:
        row = {
            "appointment_id": appointment_id,
            "shipment_id": shipment_id,
            "slot_id": slot_id,
            "appointment_status": status,
            "booking_source": "PLANNER",
            "is_current": is_current,
            "booked_at": booked_at,
            "confirmed_at": booked_at if status in {"CONFIRMED", "IN_PROGRESS", "COMPLETED"} else None,
            "cancelled_at": None,
            "cancellation_reason": None,
            "replaced_appointment_id": None,
            "warehouse_confirmation_ref": f"WH-{appointment_id}" if status == "CONFIRMED" else None,
            "updated_at": booked_at,
        }
        appointment_rows.append(row)
        data.add("appointments", **row)

    active_background = [
        row for row in shipment_rows if row["shipment_id"].startswith(f"SHP-{day_code}-BG")
        and row["current_status"] != "COMPLETED"
    ]
    for index, slot in enumerate(occupied_evening):
        shipment = active_background[index]
        add_appointment(
            f"{day_code}-APT-SCARCE-{index + 1:02d}",
            shipment["shipment_id"],
            slot["slot_id"],
            "CONFIRMED",
            1,
            ts(demo_day - timedelta(days=1), 10),
        )

    ravi_slot = slot_by_key[("DOCK-JAI-D1", ts(demo_day, 17, 0))]
    add_appointment(
        f"{day_code}-APT-RAVI-OLD",
        f"SHP-{day_code}-RAVI",
        ravi_slot["slot_id"],
        "CONFIRMED",
        1,
        ts(demo_day - timedelta(days=1), 9),
    )
    undock_slot = slot_by_key[("DOCK-JAI-D2", ts(demo_day, 16, 30))]
    add_appointment(
        f"{day_code}-APT-UNDOCK",
        f"SHP-{day_code}-UNDOCK",
        undock_slot["slot_id"],
        "IN_PROGRESS",
        1,
        ts(demo_day - timedelta(days=1), 9),
    )

    # Historical volume is non-active and therefore cannot violate either
    # partial unique allocation index.
    historical_shipments = [
        row for row in shipment_rows if row["current_status"] == "COMPLETED"
    ]
    historical_slots = [
        row for row in slots
        if row["slot_start_ts"] < ts(demo_day, 17)
        and row["slot_id"] not in {ravi_slot["slot_id"], undock_slot["slot_id"]}
    ]
    history_index = 1
    while len(appointment_rows) < 900:
        shipment = historical_shipments[(history_index - 1) % len(historical_shipments)]
        slot = historical_slots[(history_index - 1) % len(historical_slots)]
        add_appointment(
            f"{day_code}-APT-HIST-{history_index:04d}",
            shipment["shipment_id"],
            slot["slot_id"],
            "COMPLETED",
            0,
            slot["slot_start_ts"],
        )
        history_index += 1

    # Four explicit Jaipur facility-snapshot states.
    snapshot_checkins = (
        (
            f"SHP-{day_code}-EARLY",
            "EARLY",
            "WAITING_EARLY",
            1,
            None,
            ts(demo_day, 16, 45),
        ),
        (
            f"SHP-{day_code}-LATE",
            "LATE",
            "WAITING_LATE",
            2,
            None,
            ts(demo_day, 17, 40),
        ),
        (
            f"SHP-{day_code}-UNDOCK",
            "ON_TIME",
            "IN_DOCK",
            None,
            "DOCK-JAI-D2",
            ts(demo_day, 16, 25),
        ),
        (
            f"SHP-{day_code}-FUTURE",
            None,
            "NOT_QUEUED",
            None,
            None,
            None,
        ),
    )
    for index, (shipment_id, arrival, queue, position, dock, gate_in) in enumerate(
        snapshot_checkins, start=1
    ):
        in_dock = queue == "IN_DOCK"
        data.add(
            "facility_checkins",
            checkin_id=f"{day_code}-CHK-SNAPSHOT-{index}",
            shipment_id=shipment_id,
            facility_id="FAC-JAI-01",
            gate_in_ts=gate_in,
            yard_queue_enter_ts=gate_in,
            dock_in_ts=ts(demo_day, 16, 35) if in_dock else None,
            unload_start_ts=ts(demo_day, 16, 40) if in_dock else None,
            unload_end_ts=None,
            gate_out_ts=None,
            arrival_state=arrival,
            queue_state=queue,
            queue_position=position,
            actual_dock_id=dock,
            notes="Demo-day facility snapshot state.",
            updated_at=ts(demo_day, 17, 45),
        )
    for index, shipment in enumerate(historical_shipments[:396], start=5):
        facility_id = shipment["destination_facility_id"]
        gate_in = datetime.fromisoformat(shipment["original_eta_ts"])
        data.add(
            "facility_checkins",
            checkin_id=f"{day_code}-CHK-{index:04d}",
            shipment_id=shipment["shipment_id"],
            facility_id=facility_id,
            gate_in_ts=iso(gate_in),
            yard_queue_enter_ts=iso(gate_in),
            dock_in_ts=iso(gate_in + timedelta(minutes=15)),
            unload_start_ts=iso(gate_in + timedelta(minutes=20)),
            unload_end_ts=iso(gate_in + timedelta(minutes=80)),
            gate_out_ts=iso(gate_in + timedelta(minutes=90)),
            arrival_state="ON_TIME",
            queue_state="COMPLETED",
            queue_position=None,
            actual_dock_id=None,
            notes="Completed background demo check-in.",
            updated_at=iso(gate_in + timedelta(minutes=90)),
        )

    # 250 structured exception threads with six messages each.
    exception_shipments = hero_specs[:15] + background_specs[:235]
    for index, spec in enumerate(exception_shipments, start=1):
        shipment_id = spec["shipment_id"]
        driver_id = spec["driver_id"]
        thread_id = f"{day_code}-THR-{index:04d}"
        exception_id = f"{day_code}-EXC-{index:04d}"
        opened_at = ts(demo_day, 15, index % 60)
        data.add(
            "chat_threads",
            thread_id=thread_id,
            driver_id=driver_id,
            shipment_id=shipment_id,
            opened_at=opened_at,
            closed_at=None if index <= 20 else ts(demo_day, 16, index % 60),
            thread_status="OPEN" if index <= 20 else "RESOLVED",
            thread_intent="ASK_SLOT_OPTIONS" if index <= 15 else "REPORT_DELAY",
        )
        data.add(
            "driver_exceptions",
            exception_id=exception_id,
            shipment_id=shipment_id,
            driver_id=driver_id,
            thread_id=thread_id,
            exception_type="DOCK_UNAVAILABLE" if "NOSLOT" in shipment_id else "DELAY",
            reported_at=opened_at,
            reported_delay_min=45,
            declared_eta_ts=spec["eta"],
            earliest_acceptable_ts=spec["eta"],
            latest_acceptable_ts=iso(
                datetime.fromisoformat(spec["eta"]) + timedelta(hours=2)
            ),
            severity_code=spec["priority"] if spec["priority"] in {"HIGH", "CRITICAL"} else "MEDIUM",
            exception_status="OPEN" if index <= 20 else "RESOLVED",
            description=f"Deterministic demo exception for {shipment_id}.",
            dedupe_key=f"{day_code}:exception:{index:04d}",
        )
        for message_number in range(1, 7):
            sender = ("DRIVER", "AGENT", "DRIVER", "AGENT", "OPERATIONS", "AGENT")[
                message_number - 1
            ]
            message_time = datetime.fromisoformat(opened_at) + timedelta(
                minutes=message_number - 1
            )
            data.add(
                "chat_messages",
                chat_message_id=f"{day_code}-MSG-{index:04d}-{message_number}",
                thread_id=thread_id,
                sender_type=sender,
                sender_reference=driver_id if sender == "DRIVER" else "DEMO",
                message_text=(
                    f"Demo conversation turn {message_number} for {shipment_id}; "
                    "operational facts remain database-backed."
                ),
                message_ts=iso(message_time),
                external_message_id=f"{day_code}-EXT-{index:04d}-{message_number}",
                is_duplicate=0,
                parsed_intent="ASK_SLOT_OPTIONS" if index <= 15 else "REPORT_DELAY",
                extracted_eta_ts=spec["eta"] if message_number in {1, 3} else None,
                requires_human_review=1 if "NOSLOT" in shipment_id else 0,
            )

    metadata = {
        "day_code": day_code,
        "period_start": period_start.isoformat(),
        "period_end": demo_day.isoformat(),
        "race_slot_id": f"{day_code}-SLT-RACE",
        "open_evening_slot_ids": sorted(open_evening_ids),
        "hero_scenarios": {
            spec["shipment_id"]: spec["scenario"] for spec in hero_specs
        },
    }
    validate(data, metadata)
    return data, metadata


def validate(data: DemoData, metadata: dict[str, Any]) -> None:
    for table, rows in data.rows.items():
        if not rows:
            continue
        first_column = next(iter(rows[0]))
        identifiers = [row[first_column] for row in rows]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError(f"Duplicate generated identifier in {table}")

    slots = data.rows["appointment_slots"]
    slot_windows = [
        (row["dock_id"], row["slot_start_ts"], row["slot_end_ts"]) for row in slots
    ]
    if len(slot_windows) != len(set(slot_windows)):
        raise ValueError("Duplicate dock/start/end slot window")

    active_statuses = {"PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS"}
    active = [
        row for row in data.rows["appointments"]
        if row["appointment_status"] in active_statuses
    ]
    for field in ("slot_id", "shipment_id"):
        values = [row[field] for row in active]
        if len(values) != len(set(values)):
            raise ValueError(f"Multiple active appointments share {field}")

    race_slot = metadata["race_slot_id"]
    if any(row["slot_id"] == race_slot for row in data.rows["appointments"]):
        raise ValueError("Race slot must have no appointment")

    if len(metadata["open_evening_slot_ids"]) != 4:
        raise ValueError("Jaipur contention window must leave exactly four options")

    expected = {
        "facilities": 4,
        "docks": 16,
        "drivers": 90,
        "vehicles": 90,
        "users": 12,
        "appointment_slots": 2828,
        "shipments": 640,
        "appointments": 900,
        "eta_updates": 800,
        "facility_checkins": 400,
        "driver_exceptions": 250,
        "chat_threads": 250,
        "chat_messages": 1500,
    }
    actual = {table: data.count(table) for table in expected}
    if actual != expected:
        raise ValueError(f"Count contract mismatch: expected {expected}, got {actual}")

    for table, rows in data.rows.items():
        for row in rows:
            for column, value in row.items():
                if (
                    value is not None
                    and (column.endswith("_ts") or column.endswith("_at"))
                    and column not in {"open_time", "close_time"}
                    and isinstance(value, str)
                    and not value.endswith("+05:30")
                ):
                    raise ValueError(f"{table}.{column} lacks +05:30: {value}")


TABLE_ORDER = (
    "facilities",
    "facility_rules",
    "docks",
    "drivers",
    "vehicles",
    "users",
    "appointment_slots",
    "shipments",
    "eta_updates",
    "appointments",
    "facility_checkins",
    "chat_threads",
    "driver_exceptions",
    "chat_messages",
)


def render_sql(data: DemoData, demo_day: date, metadata: dict[str, Any]) -> str:
    counts = Counter({table: data.count(table) for table in TABLE_ORDER})
    header_counts = ", ".join(f"{table}={counts[table]}" for table in TABLE_ORDER)
    sections = [
        f"""-- SetuHaul deterministic demo-day data
-- Demo day: {demo_day.isoformat()} (Asia/Kolkata, UTC+05:30)
-- Coverage: {metadata['period_start']} through {metadata['period_end']}
-- Additive: preserves the baseline 2026-08-04 seed; no DELETE is executed.
-- Generated counts: {header_counts}
-- Auth note: public.users.password_hash is '!auth_only!'; create Auth users separately.

BEGIN;
SET LOCAL search_path = public;
""".rstrip()
    ]
    for table in TABLE_ORDER:
        sections.append(f"-- {table}\n{render_table(table, data.rows.get(table, []))}")
    sections.append(
        """COMMIT;

-- OPTIONAL CLEANUP (commented out intentionally; review before use).
-- DELETE FROM public.chat_messages WHERE chat_message_id LIKE 'D16-%';
-- DELETE FROM public.driver_exceptions WHERE exception_id LIKE 'D16-%';
-- DELETE FROM public.chat_threads WHERE thread_id LIKE 'D16-%';
-- DELETE FROM public.facility_checkins WHERE checkin_id LIKE 'D16-%';
-- DELETE FROM public.appointments WHERE appointment_id LIKE 'D16-%';
-- DELETE FROM public.eta_updates WHERE eta_update_id LIKE 'D16-%';
-- DELETE FROM public.shipments WHERE shipment_id LIKE 'SHP-D16-%';
-- DELETE FROM public.appointment_slots WHERE slot_id LIKE 'D16-%';
-- DELETE FROM public.users WHERE user_id LIKE 'USR2%';
-- DELETE FROM public.vehicles WHERE vehicle_id LIKE 'D16-%';
-- DELETE FROM public.drivers WHERE driver_id LIKE 'D16-%';
-- DELETE FROM public.facility_rules WHERE rule_id LIKE 'D16-%';
-- DELETE FROM public.docks WHERE dock_id LIKE 'D16-%';
-- DELETE FROM public.facilities WHERE facility_id IN ('FAC-DEL-01','FAC-AMD-01','FAC-PNQ-01','FAC-BLR-01');
"""
    )
    return "\n\n".join(sections) + "\n"


def print_counts(data: DemoData, demo_day: date, metadata: dict[str, Any]) -> None:
    payload = {
        "demo_day": demo_day.isoformat(),
        "timezone": "Asia/Kolkata",
        "period": [metadata["period_start"], metadata["period_end"]],
        "race_slot_id": metadata["race_slot_id"],
        "open_jaipur_standard_slots_18_20": len(metadata["open_evening_slot_ids"]),
        "counts": {table: data.count(table) for table in TABLE_ORDER},
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo-day",
        required=True,
        type=date.fromisoformat,
        help="Demo day in YYYY-MM-DD format.",
    )
    parser.add_argument("--emit", required=True, choices=("sql", "counts"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data, metadata = build_demo_data(args.demo_day)
    if args.emit == "counts":
        print_counts(data, args.demo_day, metadata)
        return 0

    output_dir = ROOT / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"demo_day_{args.demo_day.isoformat()}.sql"
    output_path.write_text(
        render_sql(data, args.demo_day, metadata),
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
