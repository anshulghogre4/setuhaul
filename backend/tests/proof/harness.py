"""Fixture seeding for the parts of section 10 that write.

Design citation: `SOLUTION_DESIGN.md` section 10.1 (the N=50 concurrency harness), section 9.1
("Every test must inject `now` rather than read the wall clock"), D1/D2. GitHub issue #44.

## Why the contested interval is in the year 2099

`find_feasible_slots` bounds its search from the *shipment's ETA*, not from wall-clock now
(`feasibility.py`: "bound the search to a rolling horizon measured from the effective ETA, not from
wall-clock now"). That is what makes every fixture here reproducible on any day: the harness picks
an ETA and a slot, and the engine's answer depends only on those two, never on the date the suite
happens to run.

2099 specifically, and a per-run unique id in every key, so that:

* nothing this module inserts can ever collide with the shipped seed's 2026-08-04 fixtures, which
  parts 2, 4 and 5 assert on to the row;
* two runs against the same cluster cannot collide with each other.

The interval also has to be *inside* FAC-JAI-01's operating window (06:00-22:00 local, seeded) and
below RULE005's 21:00 LAST_NEW_START_TIME, or Stage 1 would reject every candidate and the harness
would prove nothing about concurrency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.execution_context import ExecutionContext, RoleName

IST = timezone(timedelta(hours=5, minutes=30))

FACILITY_ID = "FAC-JAI-01"
# D1 and D2 are both STANDARD docks at FAC-JAI-01 in the shipped seed. D1 carries the contested
# interval; D2 carries the alternatives that make section 10.1's "with fresh options" clause
# testable rather than vacuous.
CONTESTED_DOCK = "DOCK-JAI-D1"
ALTERNATIVE_DOCK = "DOCK-JAI-D2"

CARRIER_ID = "CAR001"
VEHICLE_ID = "VEH001"
DRIVER_ROLE_ID = "ROL001"

# Comfortably inside the facility's 06:00-22:00 window and well before RULE005's 21:00 cutoff.
CONTESTED_START = datetime(2099, 3, 1, 10, 0, tzinfo=IST)
SLOT_MINUTES = 60
EXPECTED_UNLOAD_MIN = 45
LOAD_WEIGHT_KG = 10_000  # under DOCK-JAI-D1's 20,000 kg rating and RULE004's 25,000 kg heavy bar


@dataclass(frozen=True)
class Contender:
    """One competitor in the N=50 race: its own driver, its own user, its own shipment."""

    index: int
    user_id: str
    driver_id: str
    shipment_id: str

    def ctx(self) -> ExecutionContext:
        return ExecutionContext(
            request_id=f"proof-{self.shipment_id}",
            auth_subject=f"proof-{self.shipment_id}",
            user_id=self.user_id,
            email=f"{self.driver_id.lower()}@proof.invalid",
            full_name=f"Proof Driver {self.index}",
            role_id=DRIVER_ROLE_ID,
            role_name=RoleName.DRIVER,
            driver_id=self.driver_id,
            facility_id=FACILITY_ID,
        )


@dataclass(frozen=True)
class RaceFixture:
    run_id: str
    slot_id: str
    alternative_slot_ids: tuple[str, ...]
    contenders: tuple[Contender, ...]
    eta: datetime
    slot_start: datetime
    slot_end: datetime


async def seed_race(
    session: AsyncSession,
    *,
    run_id: str,
    contenders: int,
    start_offset_minutes: int = 0,
    alternatives: int = 3,
) -> RaceFixture:
    """Insert N drivers, N users, N shipments and one contested slot. Commits.

    `start_offset_minutes` shifts the whole fixture so several independent races can coexist in one
    database without sharing an interval -- part 1 uses it to give the TTL-orphan check its own
    slot rather than reusing the one 50 sessions just fought over.
    """
    slot_start = CONTESTED_START + timedelta(minutes=start_offset_minutes)
    slot_end = slot_start + timedelta(minutes=SLOT_MINUTES)
    # 30 minutes before the slot opens: the truck can be at the dock at slot start, so Stage 1's
    # "ETA + unload fits inside the interval" holds and the option is genuinely feasible.
    eta = slot_start - timedelta(minutes=30)

    slot_id = f"SLOT-PROOF-{run_id}"
    await session.execute(
        text(
            """
            INSERT INTO public.appointment_slots (
              slot_id, facility_id, dock_id, slot_start_ts, slot_end_ts,
              slot_status, block_reason, created_at
            ) VALUES (
              :slot_id, :facility_id, :dock_id, :slot_start, :slot_end, 'OPEN', NULL, :created_at
            )
            """
        ),
        {
            "slot_id": slot_id,
            "facility_id": FACILITY_ID,
            "dock_id": CONTESTED_DOCK,
            "slot_start": slot_start,
            "slot_end": slot_end,
            # appointment_slots.created_at became timestamptz in migration 20260823060000, and
            # asyncpg refuses to coerce a str into a timestamptz parameter -- the exact DataError
            # `expiry.py` and `holds.py` both document. Bind the datetime, not its ISO string.
            "created_at": slot_start,
        },
    )

    alternative_ids: list[str] = []
    for offset in range(1, alternatives + 1):
        alt_id = f"SLOT-PROOFALT-{run_id}-{offset}"
        alt_start = slot_start + timedelta(minutes=SLOT_MINUTES * offset)
        await session.execute(
            text(
                """
                INSERT INTO public.appointment_slots (
                  slot_id, facility_id, dock_id, slot_start_ts, slot_end_ts,
                  slot_status, block_reason, created_at
                ) VALUES (
                  :slot_id, :facility_id, :dock_id, :slot_start, :slot_end, 'OPEN', NULL, :created_at
                )
                """
            ),
            {
                "slot_id": alt_id,
                "facility_id": FACILITY_ID,
                "dock_id": ALTERNATIVE_DOCK,
                "slot_start": alt_start,
                "slot_end": alt_start + timedelta(minutes=SLOT_MINUTES),
                "created_at": slot_start,
            },
        )
        alternative_ids.append(alt_id)

    built: list[Contender] = []
    for index in range(contenders):
        suffix = f"{run_id}{index:03d}"
        contender = Contender(
            index=index,
            user_id=f"USR-PF-{suffix}",
            driver_id=f"DRV-PF-{suffix}",
            shipment_id=f"SHP-PF-{suffix}",
        )
        await session.execute(
            text(
                """
                INSERT INTO public.drivers (
                  driver_id, carrier_id, driver_name, phone, licence_number,
                  home_base_city, driver_status
                ) VALUES (
                  :driver_id, :carrier_id, :name, :phone, :licence, 'Jaipur', 'ACTIVE'
                )
                """
            ),
            {
                "driver_id": contender.driver_id,
                "carrier_id": CARRIER_ID,
                "name": f"Proof Driver {index}",
                "phone": f"+91-99{suffix}",
                "licence": f"LIC-{suffix}",
            },
        )
        # audit_logs.user_id is NOT NULL REFERENCES users(user_id), and every hold writes an audit
        # row -- so a real user row per contender is a hard requirement, not scaffolding.
        await session.execute(
            text(
                """
                INSERT INTO public.users (
                  user_id, role_id, employee_code, full_name, email, phone_number,
                  password_hash, driver_id, facility_id, is_active
                ) VALUES (
                  :user_id, :role_id, :employee_code, :full_name, :email, NULL,
                  'proof-suite-no-login', :driver_id, :facility_id, 1
                )
                """
            ),
            {
                "user_id": contender.user_id,
                "role_id": DRIVER_ROLE_ID,
                "employee_code": f"EMP-{suffix}",
                "full_name": f"Proof Driver {index}",
                "email": f"{contender.driver_id.lower()}@proof.invalid",
                "driver_id": contender.driver_id,
                "facility_id": FACILITY_ID,
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO public.shipments (
                  shipment_id, order_reference, carrier_id, driver_id, vehicle_id,
                  origin_name, origin_city, destination_facility_id, customer_name,
                  product_category, load_weight_kg, pallet_count, required_dock_type,
                  temperature_control_required, priority_code, planned_departure_ts,
                  actual_departure_ts, original_eta_ts, latest_eta_ts,
                  expected_unload_min, current_status, created_at, updated_at
                ) VALUES (
                  :shipment_id, :order_reference, :carrier_id, :driver_id, :vehicle_id,
                  'Proof Origin', 'Jaipur', :facility_id, 'Proof Customer',
                  'GENERAL', :load_weight_kg, 10, 'STANDARD',
                  0, 'NORMAL', :departure, :departure, :eta, :eta,
                  :unload_min, 'IN_TRANSIT', :created_at, :created_at
                )
                """
            ),
            {
                "shipment_id": contender.shipment_id,
                "order_reference": f"ORD-PF-{suffix}",
                "carrier_id": CARRIER_ID,
                "driver_id": contender.driver_id,
                "vehicle_id": VEHICLE_ID,
                "facility_id": FACILITY_ID,
                "load_weight_kg": LOAD_WEIGHT_KG,
                "departure": (eta - timedelta(hours=6)),
                "eta": eta,
                "unload_min": EXPECTED_UNLOAD_MIN,
                "created_at": (eta - timedelta(hours=6)),
            },
        )
        built.append(contender)

    await session.commit()
    return RaceFixture(
        run_id=run_id,
        slot_id=slot_id,
        alternative_slot_ids=tuple(alternative_ids),
        contenders=tuple(built),
        eta=eta,
        slot_start=slot_start,
        slot_end=slot_end,
    )
