#!/usr/bin/env python3
"""Roll back the isolated reschedule-demo driver seeded by
``seed_reschedule_driver.py``.

Reverses every RS-prefixed row created for the sandbox: cancels any active
appointment through the production ``cancel_appointment`` service (so the
slot claim is released and audited correctly, not just deleted), then
deletes escalation/audit/idempotency rows and finally the shipments, user,
and driver rows themselves, in FK-safe order.

Modernized 2026-09-01 (#95): eight tables now hold FKs onto shipments, and
this script must clear ALL of them before the shipments delete or it dies
partway on an FK violation -- which is exactly how it rotted. The newer legs
it predated: dock_occupancy (D2's shipment_id FK; note cancel_appointment
flips claims to CANCELLED and the sweeper expires holds IN PLACE, so rows
persist and must be deleted here), chat_threads/chat_messages (#55's
coordinator-reply work), plus driver_exceptions, eta_updates,
facility_checkins, and operational_messages rows the race suites create.

Never touches FAC-JAI-01, the demo cast (SHP-D16-*/CONTEND-*/RACE-*), or
the reused vehicle ``D16-VEH-002``.

Safety:
  Requires --confirm for any write. Use --dry-run to preview (default).
  --with-auth additionally deletes the Supabase Auth identity created by
  ``seed_reschedule_driver.py --with-auth``, if one was mapped.
"""

from __future__ import annotations

import argparse
import asyncio
import os
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


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def cancel_active_appointments(*, dry_run: bool) -> list[dict[str, Any]]:
    """Release any active appointment through the production cancel service."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.execution_context import ExecutionContext, RoleName
    from app.db.session import _normalize_async_url
    from app.scheduling.allocation import CancelAppointmentCommand, cancel_appointment

    admin_ctx = ExecutionContext(
        request_id="rollback-rs-admin",
        auth_subject="rollback-rs-admin",
        user_id="USR997",
        email="meera.iyer@setuhaul.com",
        full_name="Rollback Script Admin",
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
        async with session_factory() as session:
            rows = (
                await session.execute(
                    text(
                        """
                        SELECT appointment_id, shipment_id
                        FROM public.appointments
                        WHERE shipment_id LIKE 'SHP-RS-%'
                          AND is_current = 1
                          AND appointment_status IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
                        """
                    )
                )
            ).mappings().all()
        for row in rows:
            outcomes.append(
                {
                    "shipment_id": row["shipment_id"],
                    "appointment_id": row["appointment_id"],
                    "action": "would_cancel" if dry_run else "cancelling",
                }
            )
            if dry_run:
                continue
            async with session_factory() as session:
                result = await cancel_appointment(
                    session,
                    admin_ctx,
                    shipment_id=row["shipment_id"],
                    command=CancelAppointmentCommand(
                        appointment_id=row["appointment_id"],
                        cancellation_reason="Reschedule-sandbox rollback",
                    ),
                    idempotency_key=f"rollback-rs-{row['appointment_id']}-cancel",
                )
                outcomes[-1]["code"] = result.code
    finally:
        await engine.dispose()
    return outcomes


async def delete_rows(conn: Any, *, dry_run: bool) -> dict[str, int]:
    counts = {
        "escalation_queue": await conn.fetchval(
            "SELECT count(*) FROM public.escalation_queue WHERE shipment_id LIKE 'SHP-RS-%'"
        ),
        "audit_logs": await conn.fetchval(
            "SELECT count(*) FROM public.audit_logs WHERE user_id = $1", USER_ID
        ),
        "appointments": await conn.fetchval(
            "SELECT count(*) FROM public.appointments WHERE shipment_id LIKE 'SHP-RS-%'"
        ),
        "idempotency_requests": await conn.fetchval(
            "SELECT count(*) FROM public.idempotency_requests WHERE idempotency_key LIKE 'seed-rs-%' OR idempotency_key LIKE 'rollback-rs-%'"
        ),
        "dock_occupancy": await conn.fetchval(
            "SELECT count(*) FROM public.dock_occupancy WHERE shipment_id LIKE 'SHP-RS-%'"
        ),
        "chat_threads": await conn.fetchval(
            "SELECT count(*) FROM public.chat_threads WHERE shipment_id LIKE 'SHP-RS-%'"
        ),
        "driver_exceptions": await conn.fetchval(
            "SELECT count(*) FROM public.driver_exceptions WHERE shipment_id LIKE 'SHP-RS-%'"
        ),
        "eta_updates": await conn.fetchval(
            "SELECT count(*) FROM public.eta_updates WHERE shipment_id LIKE 'SHP-RS-%'"
        ),
        "facility_checkins": await conn.fetchval(
            "SELECT count(*) FROM public.facility_checkins WHERE shipment_id LIKE 'SHP-RS-%'"
        ),
        "operational_messages": await conn.fetchval(
            "SELECT count(*) FROM public.operational_messages WHERE shipment_id LIKE 'SHP-RS-%'"
        ),
        "shipments": await conn.fetchval(
            "SELECT count(*) FROM public.shipments WHERE shipment_id LIKE 'SHP-RS-%'"
        ),
        "users": await conn.fetchval(
            "SELECT count(*) FROM public.users WHERE user_id = $1", USER_ID
        ),
        "drivers": await conn.fetchval(
            "SELECT count(*) FROM public.drivers WHERE driver_id = $1", DRIVER_ID
        ),
    }
    counts = {key: int(value or 0) for key, value in counts.items()}
    if dry_run:
        return counts

    async with conn.transaction():
        await conn.execute(
            "DELETE FROM public.escalation_queue WHERE shipment_id LIKE 'SHP-RS-%'"
        )
        # driver_exceptions before chat_threads: exceptions carry a thread_id link.
        # Keyed by shipment OR driver: assistant flows can create rows against the
        # driver without an RS shipment id on them.
        await conn.execute(
            "DELETE FROM public.driver_exceptions WHERE shipment_id LIKE 'SHP-RS-%' OR driver_id = $1",
            DRIVER_ID,
        )
        # chat_messages before chat_threads (message->thread FK), threads before shipments.
        # Threads matched by shipment OR driver: a general chat turn opens a thread
        # keyed to the driver alone.
        await conn.execute(
            """
            DELETE FROM public.chat_messages
            WHERE thread_id IN (
              SELECT thread_id FROM public.chat_threads
              WHERE shipment_id LIKE 'SHP-RS-%' OR driver_id = $1
            )
            """,
            DRIVER_ID,
        )
        # api_logs FKs both chat_threads and users (found 2026-09-01 via pg_constraint,
        # not assumed). Sandbox request logs go with the sandbox, same as audit_logs.
        await conn.execute(
            """
            DELETE FROM public.api_logs
            WHERE user_id = $1 OR thread_id IN (
              SELECT thread_id FROM public.chat_threads
              WHERE shipment_id LIKE 'SHP-RS-%' OR driver_id = $2
            )
            """,
            USER_ID,
            DRIVER_ID,
        )
        await conn.execute(
            "DELETE FROM public.chat_threads WHERE shipment_id LIKE 'SHP-RS-%' OR driver_id = $1",
            DRIVER_ID,
        )
        await conn.execute(
            "DELETE FROM public.eta_updates WHERE shipment_id LIKE 'SHP-RS-%' OR reported_by_driver_id = $1",
            DRIVER_ID,
        )
        await conn.execute(
            "DELETE FROM public.facility_checkins WHERE shipment_id LIKE 'SHP-RS-%'"
        )
        await conn.execute(
            "DELETE FROM public.operational_messages WHERE shipment_id LIKE 'SHP-RS-%'"
        )
        # dock_occupancy before appointments AND shipments: it FKs both. Includes
        # EXPIRED/CANCELLED rows the sweeper/cancel path leaves in place for audit.
        await conn.execute(
            "DELETE FROM public.dock_occupancy WHERE shipment_id LIKE 'SHP-RS-%'"
        )
        # Clear self-FK links before deleting appointments (matches reset_demo_day.py pattern).
        await conn.execute(
            """
            UPDATE public.operational_messages om
            SET appointment_id = NULL
            WHERE om.appointment_id IN (
              SELECT appointment_id FROM public.appointments WHERE shipment_id LIKE 'SHP-RS-%'
            )
            """
        )
        await conn.execute(
            """
            UPDATE public.appointments
            SET replaced_appointment_id = NULL
            WHERE shipment_id LIKE 'SHP-RS-%'
               OR replaced_appointment_id IN (
                 SELECT appointment_id FROM public.appointments WHERE shipment_id LIKE 'SHP-RS-%'
               )
            """
        )
        await conn.execute(
            "DELETE FROM public.appointments WHERE shipment_id LIKE 'SHP-RS-%'"
        )
        await conn.execute(
            "DELETE FROM public.audit_logs WHERE user_id = $1", USER_ID
        )
        await conn.execute(
            """
            DELETE FROM public.idempotency_requests
            WHERE idempotency_key LIKE 'seed-rs-%' OR idempotency_key LIKE 'rollback-rs-%'
            """
        )
        await conn.execute(
            "DELETE FROM public.shipments WHERE shipment_id LIKE 'SHP-RS-%'"
        )
        # users has more referencing tables than it did when this script was written
        # (user_scopes, notifications, notification_preferences -- pg_constraint-verified
        # 2026-09-01). Clear them before the users row or the delete dies on an FK.
        await conn.execute("DELETE FROM public.user_scopes WHERE user_id = $1", USER_ID)
        await conn.execute("DELETE FROM public.notifications WHERE user_id = $1", USER_ID)
        await conn.execute(
            "DELETE FROM public.notification_preferences WHERE user_id = $1", USER_ID
        )
        await conn.execute("DELETE FROM public.users WHERE user_id = $1", USER_ID)
        await conn.execute("DELETE FROM public.drivers WHERE driver_id = $1", DRIVER_ID)
    return counts


async def delete_auth_identity() -> None:
    import asyncpg
    import httpx

    base = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    service = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not base or not service or not db_url:
        print("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / DATABASE_URL missing — skipping Auth cleanup.")
        return

    conn = await asyncpg.connect(db_url, statement_cache_size=0)
    try:
        row = await conn.fetchrow(
            "SELECT auth_user_id FROM public.users WHERE user_id = $1", USER_ID
        )
        auth_id = row["auth_user_id"] if row else None
    finally:
        await conn.close()

    if not auth_id:
        print("No mapped Auth identity found — nothing to delete.")
        return

    headers = {"apikey": service, "Authorization": f"Bearer {service}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.delete(f"{base}/auth/v1/admin/users/{auth_id}", headers=headers)
        if resp.status_code >= 400:
            print(f"AUTH_DELETE_FAIL {resp.status_code} {resp.text[:200]}")
        else:
            print(f"AUTH_DELETED {auth_id}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print counts only; no writes (default)")
    parser.add_argument("--confirm", action="store_true", help="Required for writes")
    parser.add_argument(
        "--with-auth",
        action="store_true",
        help="Also delete the mapped Supabase Auth identity, if any",
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

    cancel_outcomes = await cancel_active_appointments(dry_run=dry_run)
    for outcome in cancel_outcomes:
        print(outcome)

    conn = await asyncpg.connect(url, statement_cache_size=0, timeout=180)
    try:
        counts = await delete_rows(conn, dry_run=dry_run)
        print(f"{'DRY-RUN ' if dry_run else ''}rows={counts}")
    finally:
        await conn.close()

    if args.with_auth and not dry_run:
        await delete_auth_identity()
    elif args.with_auth and dry_run:
        print("Skipping --with-auth delete in dry-run.")

    print("ROLLBACK_DRY_RUN_OK" if dry_run else "ROLLBACK_OK")
    return 0


def main() -> None:
    load_env(ROOT / ".env.local")
    load_env(ROOT / ".env")
    args = parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
