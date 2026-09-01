#!/usr/bin/env python3
"""Seed one isolated reschedule-demo driver at FAC-GGN-01.

Creates driver ``DRV-RS-01``, users row ``USR-RS-01`` (DRIVER role,
FAC-GGN-01), and four shipments:

  SHP-RS-PENDING   -> booked via request_slot()      -> PENDING_CONFIRMATION
  SHP-RS-CONFIRMED -> booked, then confirm_appointment() -> CONFIRMED
  SHP-RS-OPEN      -> no appointment; has feasible options
  SHP-RS-NOSLOT    -> no appointment; HEAVY dock type, GGN has none -> escalation

All appointment/audit writes go through the production services
(``app.scheduling.allocation.request_slot`` / ``confirm_appointment``,
``app.scheduling.feasibility.find_feasible_slots``,
``app.services.escalation_service.escalate_exception``) with real
ExecutionContext scope checks -- the same path the driver chat assistant
uses. Nothing is inserted into ``public.appointments`` directly.

Isolation: every new row uses the ``RS`` id prefix and destination
FAC-GGN-01, which the demo cast (SHP-D16-*, CONTEND-*, RACE-*) never
touches. ``reset_demo_day.py`` (cast or full mode) cannot see or delete
these rows.

Safety:
  Requires --confirm for any Postgres write. Use --dry-run to preview
  (default). --with-auth additionally creates a Supabase Auth identity
  for the new driver using the existing shared Driver password (never
  resets an existing account, never prints the password); it is gated
  separately from --confirm so the DB seed can be inspected first.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DRIVER_ID = "DRV-RS-01"
USER_ID = "USR-RS-01"
DRIVER_EMAIL = "driver.resched@setuhaul.com"
DRIVER_NAME = "Resched Demo Driver"
FACILITY_ID = "FAC-GGN-01"
VEHICLE_ID = "D16-VEH-002"  # existing 32FT_SXL / 15,000 kg / CAR002 — reused, not created
CARRIER_ID = "CAR002"
ETA_TS = "2026-08-16T09:00:00+05:30"
CREATED_AT = "2026-08-16T08:00:00+05:30"

SHP_PENDING = "SHP-RS-PENDING"
SHP_CONFIRMED = "SHP-RS-CONFIRMED"
SHP_OPEN = "SHP-RS-OPEN"
SHP_NOSLOT = "SHP-RS-NOSLOT"

SHIPMENT_SPECS: list[dict[str, Any]] = [
    {
        "shipment_id": SHP_PENDING,
        "required_dock_type": "STANDARD",
        "load_weight_kg": 12000,
        "priority_code": "NORMAL",
        "book": True,
        "confirm": False,
    },
    {
        "shipment_id": SHP_CONFIRMED,
        "required_dock_type": "STANDARD",
        "load_weight_kg": 12000,
        "priority_code": "NORMAL",
        "book": True,
        "confirm": True,
    },
    {
        "shipment_id": SHP_OPEN,
        "required_dock_type": "STANDARD",
        "load_weight_kg": 12000,
        "priority_code": "NORMAL",
        "book": False,
        "confirm": False,
    },
    {
        "shipment_id": SHP_NOSLOT,
        "required_dock_type": "HEAVY",  # FAC-GGN-01 has no HEAVY dock -> guaranteed escalation
        "load_weight_kg": 30000,
        "priority_code": "HIGH",
        "book": False,
        "confirm": False,
    },
]

RS_ID_PATTERNS = ("DRV-RS-%", "USR-RS-%", "SHP-RS-%")


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def _collision_counts(conn: Any) -> dict[str, int]:
    counts = {
        "drivers": await conn.fetchval(
            "SELECT count(*) FROM public.drivers WHERE driver_id = $1", DRIVER_ID
        ),
        "users": await conn.fetchval(
            "SELECT count(*) FROM public.users WHERE user_id = $1", USER_ID
        ),
        "shipments": await conn.fetchval(
            "SELECT count(*) FROM public.shipments WHERE shipment_id LIKE 'SHP-RS-%'"
        ),
    }
    return {key: int(value or 0) for key, value in counts.items()}


async def seed_rows(conn: Any, *, dry_run: bool) -> None:
    """Insert driver/user/shipment rows. Idempotent via ON CONFLICT DO NOTHING."""
    if dry_run:
        return
    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO public.drivers (
              driver_id, carrier_id, driver_name, phone, licence_number,
              home_base_city, driver_status
            ) VALUES ($1, $2, $3, $4, $5, $6, 'ACTIVE')
            ON CONFLICT DO NOTHING
            """,
            DRIVER_ID,
            CARRIER_ID,
            DRIVER_NAME,
            "+91-90000-00001",
            "RSDL000001",
            "Gurugram",
        )
        await conn.execute(
            """
            INSERT INTO public.users (
              user_id, role_id, employee_code, full_name, email, phone_number,
              password_hash, driver_id, facility_id, is_active, last_login_ts,
              created_at, updated_at, auth_user_id
            ) VALUES (
              $1, 'ROL001', NULL, $2, $3, '+91-90000-00002',
              '!auth_only!', $4, $5, 1, NULL,
              $6, $6, NULL
            )
            ON CONFLICT DO NOTHING
            """,
            USER_ID,
            DRIVER_NAME,
            DRIVER_EMAIL,
            DRIVER_ID,
            FACILITY_ID,
            CREATED_AT,
        )
        for ordinal, spec in enumerate(SHIPMENT_SPECS, start=1):
            await conn.execute(
                """
                INSERT INTO public.shipments (
                  shipment_id, order_reference, carrier_id, driver_id, vehicle_id,
                  origin_name, origin_city, destination_facility_id, customer_name,
                  product_category, load_weight_kg, pallet_count, required_dock_type,
                  temperature_control_required, priority_code, planned_departure_ts,
                  actual_departure_ts, original_eta_ts, latest_eta_ts,
                  expected_unload_min, current_status, created_at, updated_at
                ) VALUES (
                  $1, $2, $3, $4, $5,
                  'Reschedule Sandbox Origin', 'Delhi', $6, 'Reschedule Sandbox Customer',
                  'GENERAL', $7, 10, $8,
                  0, $9, $10,
                  $10, $11, $11,
                  25, 'IN_TRANSIT', $12, $12
                )
                ON CONFLICT DO NOTHING
                """,
                spec["shipment_id"],
                f"ORD-RS-{ordinal:03d}",
                CARRIER_ID,
                DRIVER_ID,
                VEHICLE_ID,
                FACILITY_ID,
                spec["load_weight_kg"],
                spec["required_dock_type"],
                spec["priority_code"],
                # Parsed to datetime (2026-09-01): the D1 migration 20260823060000 converted these
                # columns from TEXT to timestamptz, and asyncpg refuses a str bind against
                # timestamptz -- same bind-type class the D2 work documented for bigint/str.
                # This script predates the conversion and rotted silently until the next reseed.
                datetime.fromisoformat("2026-08-16T04:00:00+05:30"),
                datetime.fromisoformat(ETA_TS) if isinstance(ETA_TS, str) else ETA_TS,
                datetime.fromisoformat(CREATED_AT) if isinstance(CREATED_AT, str) else CREATED_AT,
            )


async def book_and_confirm(*, dry_run: bool) -> list[dict[str, Any]]:
    """Run request_slot / confirm_appointment through the production services."""
    if dry_run:
        return []

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.execution_context import ExecutionContext, RoleName
    from app.db.session import _normalize_async_url
    from app.scheduling.allocation import (
        ConfirmAppointmentCommand,
        RequestSlotCommand,
        confirm_appointment,
        request_slot,
    )
    from app.scheduling.feasibility import find_feasible_slots

    driver_ctx = ExecutionContext(
        request_id="seed-rs-driver",
        auth_subject=f"seed-{DRIVER_ID}",
        user_id=USER_ID,
        email=DRIVER_EMAIL,
        full_name=DRIVER_NAME,
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id=DRIVER_ID,
        facility_id=FACILITY_ID,
    )
    admin_ctx = ExecutionContext(
        request_id="seed-rs-admin",
        auth_subject="seed-rs-admin",
        user_id="USR997",
        email="meera.iyer@setuhaul.com",
        full_name="Seed Script Admin",
        role_id="ROL008",
        role_name=RoleName.ADMIN,
    )

    engine = create_async_engine(
        _normalize_async_url(os.environ["DATABASE_URL"]),
        pool_pre_ping=True,
        connect_args={"statement_cache_size": 0},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    outcomes: list[dict[str, Any]] = []
    try:
        for spec in SHIPMENT_SPECS:
            shipment_id = spec["shipment_id"]
            async with session_factory() as session:
                options = await find_feasible_slots(session, driver_ctx, shipment_id, limit=5)
                if not spec["book"]:
                    outcomes.append(
                        {
                            "shipment_id": shipment_id,
                            "action": "left_open" if options.options else "left_noslot",
                            "options": len(options.options),
                            "escalation": options.escalation is not None,
                        }
                    )
                    continue
                if options.current_active_appointment:
                    # Re-run safety: a prior run (or a live reschedule smoke test)
                    # already booked this shipment. Re-issuing request_slot here
                    # would either violate ACTIVE_APPOINTMENT_EXISTS or replay a
                    # stale idempotency response for a slot that has since moved.
                    outcomes.append(
                        {
                            "shipment_id": shipment_id,
                            "action": "already_active",
                            "appointment_id": options.current_active_appointment["appointment_id"],
                            "slot_id": options.current_active_appointment["slot_id"],
                        }
                    )
                    continue
                if not options.options:
                    outcomes.append(
                        {"shipment_id": shipment_id, "action": "book_failed_no_options"}
                    )
                    continue
                slot_id = options.options[0].slot_id
                booked = await request_slot(
                    session,
                    driver_ctx,
                    shipment_id=shipment_id,
                    slot_id=slot_id,
                    command=RequestSlotCommand(
                        note="Reschedule-sandbox seed booking",
                        displayed_policy_version=options.policy_version,
                        displayed_recommendation_id=options.recommendation_id,
                    ),
                    idempotency_key=f"seed-rs-{shipment_id}-book",
                )
                outcomes.append(
                    {
                        "shipment_id": shipment_id,
                        "action": "booked",
                        "code": booked.code,
                        "appointment_id": booked.appointment_id,
                        "slot_id": slot_id,
                    }
                )
                if spec["confirm"] and booked.code == "SLOT_REQUESTED" and booked.appointment_id:
                    confirmed = await confirm_appointment(
                        session,
                        admin_ctx,
                        shipment_id=shipment_id,
                        command=ConfirmAppointmentCommand(
                            appointment_id=booked.appointment_id,
                            warehouse_confirmation_ref=f"WH-RS-{shipment_id}",
                        ),
                        idempotency_key=f"seed-rs-{shipment_id}-confirm",
                    )
                    outcomes.append(
                        {
                            "shipment_id": shipment_id,
                            "action": "confirmed",
                            "code": confirmed.code,
                        }
                    )
    finally:
        await engine.dispose()
    return outcomes


def driver_password() -> str:
    env_pw = (os.environ.get("SETUHAUL_POC_DRIVER_PASSWORD") or "").strip()
    if env_pw:
        return env_pw
    roster = ROOT / "POC_TEAM_ACCOUNTS.local.md"
    text = roster.read_text(encoding="utf-8")
    m = re.search(r"\|\s*Driver\s*\|\s*([^|]+)\|", text)
    if not m:
        raise SystemExit("Driver password not found in POC_TEAM_ACCOUNTS.local.md")
    return m.group(1).strip()


async def create_auth_identity() -> None:
    import httpx
    import asyncpg

    base = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    service = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not base or not service or not db_url:
        raise SystemExit("SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, DATABASE_URL required for --with-auth")

    password = driver_password()
    headers = {
        "apikey": service,
        "Authorization": f"Bearer {service}",
        "Content-Type": "application/json",
    }
    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        row = await conn.fetchrow(
            "SELECT auth_user_id FROM public.users WHERE user_id = $1", USER_ID
        )
        if row is None:
            print(f"MISSING_USER {USER_ID} (run the DB seed with --confirm first)")
            return
        if row["auth_user_id"] is not None:
            print(f"SKIP_ALREADY_MAPPED {USER_ID}")
            return

        async with httpx.AsyncClient(timeout=30.0) as client:
            listed = await client.get(
                f"{base}/auth/v1/admin/users",
                headers=headers,
                params={"page": 1, "per_page": 200},
            )
            listed.raise_for_status()
            auth_id = None
            for u in listed.json().get("users", []):
                if (u.get("email") or "").lower() == DRIVER_EMAIL.lower():
                    auth_id = u.get("id")
                    break

            if auth_id is None:
                resp = await client.post(
                    f"{base}/auth/v1/admin/users",
                    headers=headers,
                    json={
                        "email": DRIVER_EMAIL,
                        "password": password,
                        "email_confirm": True,
                        "user_metadata": {
                            "full_name": DRIVER_NAME,
                            "driver_id": DRIVER_ID,
                            "user_id": USER_ID,
                        },
                    },
                )
                if resp.status_code >= 400:
                    print(f"CREATE_FAIL {USER_ID} {resp.status_code} {resp.text[:200]}")
                    return
                auth_id = resp.json().get("id")
                print(f"CREATED_AUTH {USER_ID} {DRIVER_EMAIL}")
            else:
                print(f"REUSE_AUTH {USER_ID} {DRIVER_EMAIL}")

        await conn.execute(
            "UPDATE public.users SET auth_user_id = $1::uuid, updated_at = now()::text WHERE user_id = $2",
            auth_id,
            USER_ID,
        )
        print(f"MAPPED {USER_ID} -> {auth_id}")
    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print plan only; no writes (default)")
    parser.add_argument("--confirm", action="store_true", help="Required for Postgres writes")
    parser.add_argument(
        "--with-auth",
        action="store_true",
        help="Also create the Supabase Auth identity (requires --confirm to have run first)",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    import asyncpg

    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("DATABASE_URL missing (load .env.local / .env)")

    dry_run = not args.confirm
    if dry_run and not args.dry_run:
        print("No --confirm passed; running as --dry-run.")

    conn = await asyncpg.connect(url, statement_cache_size=0, timeout=180)
    try:
        collisions = await _collision_counts(conn)
        print(f"{'DRY-RUN ' if dry_run else ''}existing_rows={collisions}")
        if collisions["drivers"] or collisions["users"]:
            print(f"{DRIVER_ID} / {USER_ID} already exist — seed is idempotent, continuing.")
        await seed_rows(conn, dry_run=dry_run)
    finally:
        await conn.close()

    outcomes = await book_and_confirm(dry_run=dry_run)
    for outcome in outcomes:
        print(outcome)

    if args.with_auth:
        if dry_run:
            print("Skipping --with-auth: pass --confirm first so the users row exists.")
        else:
            await create_auth_identity()

    print("SEED_DRY_RUN_OK" if dry_run else "SEED_OK")
    return 0


def main() -> None:
    load_env(ROOT / ".env.local")
    load_env(ROOT / ".env")
    args = parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
