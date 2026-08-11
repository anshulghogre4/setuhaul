"""Reset demo-day cast / Redis residue for shared Ravi demos.

Modes:
  cast (default) — wipe hero-cast runtime mutations and restore golden fields
  full           — namespaced D16 wipe, then re-apply demo_day_YYYY-MM-DD.sql

Safety:
  Requires --confirm or SETUHAUL_DEMO_RESET=1.
  Use --dry-run to print counts without writing.

Does not touch Auth passwords or Auth users.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEMO_DAY = "2026-08-16"
RACE_SLOT_ID = "D16-SLT-RACE"
RAVI_OLD_APPOINTMENT_ID = "D16-APT-RAVI-OLD"

CAST_SHIPMENT_IDS: tuple[str, ...] = (
    "SHP-D16-RAVI",
    "SHP-D16-RACE-A",
    "SHP-D16-RACE-B",
    "SHP-D16-NOSLOT",
    "SHP-D16-MULTI-B",
    *(f"SHP-D16-CONTEND-{i:02d}" for i in range(1, 11)),
)

REDIS_USER_IDS: tuple[str, ...] = (
    "USR001",
    "USR002",
    "USR003",
    *(f"USR{i}" for i in range(201, 211)),
)

# Golden shipment fields from generate_demo_day.py (authoritative for cast reset).
GOLDEN_SHIPMENTS: dict[str, dict[str, Any]] = {
    "SHP-D16-RAVI": {
        "latest_eta_ts": "2026-08-16T18:30:00+05:30",
        "expected_unload_min": 25,
        "current_status": "IN_TRANSIT",
    },
    "SHP-D16-RACE-A": {
        "latest_eta_ts": "2026-08-16T18:35:00+05:30",
        "expected_unload_min": 25,
        "current_status": "IN_TRANSIT",
    },
    "SHP-D16-RACE-B": {
        "latest_eta_ts": "2026-08-16T18:40:00+05:30",
        "expected_unload_min": 25,
        "current_status": "IN_TRANSIT",
    },
    "SHP-D16-NOSLOT": {
        "latest_eta_ts": "2026-08-16T21:30:00+05:30",
        "expected_unload_min": 90,
        "current_status": "IN_TRANSIT",
    },
    "SHP-D16-MULTI-B": {
        "latest_eta_ts": "2026-08-16T19:15:00+05:30",
        "expected_unload_min": 25,
        "current_status": "IN_TRANSIT",
    },
    **{
        f"SHP-D16-CONTEND-{i:02d}": {
            "latest_eta_ts": (
                f"2026-08-16T{17 + ((30 + (i - 1) * 10) // 60):02d}:"
                f"{(30 + (i - 1) * 10) % 60:02d}:00+05:30"
            ),
            "expected_unload_min": 25,
            "current_status": "IN_TRANSIT",
        }
        for i in range(1, 11)
    },
    "SHP1017": {
        "latest_eta_ts": "2026-08-04T12:45:00+05:30",
        "expected_unload_min": 50,
        "current_status": "IN_TRANSIT",
    },
}


@dataclass
class PlanSummary:
    actions: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, label: str, count: int) -> None:
        self.counts[label] = count
        self.actions.append(f"{label}={count}")


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def confirm_allowed(args: argparse.Namespace) -> bool:
    if args.dry_run:
        return True
    if args.confirm:
        return True
    return (os.environ.get("SETUHAUL_DEMO_RESET") or "").strip() == "1"


def cast_ids(*, include_shp1017: bool) -> list[str]:
    ids = list(CAST_SHIPMENT_IDS)
    if include_shp1017:
        ids.append("SHP1017")
    return ids


async def _count(conn: Any, sql: str, *args: Any) -> int:
    value = await conn.fetchval(sql, *args)
    return int(value or 0)


async def plan_cast(conn: Any, shipment_ids: Sequence[str]) -> PlanSummary:
    summary = PlanSummary()
    ids = list(shipment_ids)

    summary.add(
        "escalation_queue",
        await _count(
            conn,
            "SELECT count(*) FROM public.escalation_queue WHERE shipment_id = ANY($1::text[])",
            ids,
        ),
    )
    summary.add(
        "runtime_chat_messages",
        await _count(
            conn,
            """
            SELECT count(*)
            FROM public.chat_messages m
            JOIN public.chat_threads t ON t.thread_id = m.thread_id
            WHERE t.shipment_id = ANY($1::text[])
              AND t.thread_id NOT LIKE 'D16-%'
              AND t.thread_id NOT LIKE 'THR%'
            """,
            ids,
        ),
    )
    summary.add(
        "runtime_chat_threads",
        await _count(
            conn,
            """
            SELECT count(*)
            FROM public.chat_threads
            WHERE shipment_id = ANY($1::text[])
              AND thread_id NOT LIKE 'D16-%'
              AND thread_id NOT LIKE 'THR%'
            """,
            ids,
        ),
    )
    summary.add(
        "runtime_driver_exceptions",
        await _count(
            conn,
            """
            SELECT count(*)
            FROM public.driver_exceptions
            WHERE shipment_id = ANY($1::text[])
              AND exception_id NOT LIKE 'D16-%'
              AND exception_id NOT LIKE 'EXC%'
            """,
            ids,
        ),
    )
    summary.add(
        "runtime_appointments",
        await _count(
            conn,
            """
            SELECT count(*)
            FROM public.appointments
            WHERE (
                shipment_id = ANY($1::text[])
                OR slot_id = $2
              )
              AND appointment_id NOT IN ('D16-APT-RAVI-OLD', 'APT1017')
              AND (
                booking_source = 'DRIVER_CHAT'
                OR appointment_id LIKE 'APT-%'
                OR appointment_id NOT LIKE 'D16-APT-%'
              )
            """,
            ids,
            RACE_SLOT_ID,
        ),
    )
    summary.add(
        "ops_msgs_linked_to_runtime_apts",
        await _count(
            conn,
            """
            SELECT count(*)
            FROM public.operational_messages om
            WHERE om.appointment_id IN (
              SELECT appointment_id
              FROM public.appointments
              WHERE (
                  shipment_id = ANY($1::text[])
                  OR slot_id = $2
                )
                AND appointment_id NOT IN ('D16-APT-RAVI-OLD', 'APT1017')
                AND (
                  booking_source = 'DRIVER_CHAT'
                  OR appointment_id LIKE 'APT-%'
                  OR appointment_id NOT LIKE 'D16-APT-%'
                )
            )
            """,
            ids,
            RACE_SLOT_ID,
        ),
    )
    summary.add(
        "extra_eta_updates",
        await _count(
            conn,
            """
            SELECT count(*)
            FROM public.eta_updates
            WHERE shipment_id = ANY($1::text[])
              AND (
                (
                  shipment_id LIKE 'SHP-D16-%'
                  AND source_type <> 'ORIGINAL_PLAN'
                )
                OR (
                  shipment_id = 'SHP1017'
                  AND eta_update_id <> 'ETA012'
                )
              )
            """,
            ids,
        ),
    )
    summary.add(
        "active_race_claims",
        await _count(
            conn,
            """
            SELECT count(*)
            FROM public.appointments
            WHERE slot_id = $1
              AND appointment_status IN
                ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')
              AND is_current = 1
            """,
            RACE_SLOT_ID,
        ),
    )
    summary.add(
        "idempotency_cast_routes",
        await _count(
            conn,
            """
            SELECT count(*)
            FROM public.idempotency_requests
            WHERE route LIKE ANY($1::text[])
               OR user_id = ANY($2::text[])
            """,
            [f"%{sid}%" for sid in ids],
            list(REDIS_USER_IDS),
        ),
    )
    summary.add(
        "shipments_to_restore",
        await _count(
            conn,
            "SELECT count(*) FROM public.shipments WHERE shipment_id = ANY($1::text[])",
            ids,
        ),
    )
    summary.add(
        "ravi_old_appointment",
        await _count(
            conn,
            "SELECT count(*) FROM public.appointments WHERE appointment_id = $1",
            RAVI_OLD_APPOINTMENT_ID,
        ),
    )
    if "SHP1017" in ids:
        summary.add(
            "apt1017",
            await _count(
                conn,
                "SELECT count(*) FROM public.appointments WHERE appointment_id = 'APT1017'",
            ),
        )
    return summary


async def execute_cast(conn: Any, shipment_ids: Sequence[str], *, dry_run: bool) -> PlanSummary:
    summary = await plan_cast(conn, shipment_ids)
    if dry_run:
        return summary

    ids = list(shipment_ids)
    async with conn.transaction():
        await conn.execute(
            "DELETE FROM public.escalation_queue WHERE shipment_id = ANY($1::text[])",
            ids,
        )
        await conn.execute(
            """
            DELETE FROM public.chat_messages m
            USING public.chat_threads t
            WHERE m.thread_id = t.thread_id
              AND t.shipment_id = ANY($1::text[])
              AND t.thread_id NOT LIKE 'D16-%'
              AND t.thread_id NOT LIKE 'THR%'
            """,
            ids,
        )
        await conn.execute(
            """
            DELETE FROM public.chat_threads
            WHERE shipment_id = ANY($1::text[])
              AND thread_id NOT LIKE 'D16-%'
              AND thread_id NOT LIKE 'THR%'
            """,
            ids,
        )
        await conn.execute(
            """
            DELETE FROM public.driver_exceptions
            WHERE shipment_id = ANY($1::text[])
              AND exception_id NOT LIKE 'D16-%'
              AND exception_id NOT LIKE 'EXC%'
            """,
            ids,
        )
        # Free demo claims on race + cast shipments (keep planner seed rows).
        # Clear self-FK / ops-message links first so DELETE cannot trip NO ACTION.
        await conn.execute(
            """
            WITH delete_candidates AS (
              SELECT appointment_id
              FROM public.appointments
              WHERE (
                  shipment_id = ANY($1::text[])
                  OR slot_id = $2
                )
                AND appointment_id NOT IN ('D16-APT-RAVI-OLD', 'APT1017')
                AND (
                  booking_source = 'DRIVER_CHAT'
                  OR appointment_id LIKE 'APT-%'
                  OR appointment_id NOT LIKE 'D16-APT-%'
                )
            )
            UPDATE public.operational_messages om
            SET appointment_id = NULL
            WHERE om.appointment_id IN (SELECT appointment_id FROM delete_candidates)
            """,
            ids,
            RACE_SLOT_ID,
        )
        await conn.execute(
            """
            WITH delete_candidates AS (
              SELECT appointment_id
              FROM public.appointments
              WHERE (
                  shipment_id = ANY($1::text[])
                  OR slot_id = $2
                )
                AND appointment_id NOT IN ('D16-APT-RAVI-OLD', 'APT1017')
                AND (
                  booking_source = 'DRIVER_CHAT'
                  OR appointment_id LIKE 'APT-%'
                  OR appointment_id NOT LIKE 'D16-APT-%'
                )
            )
            UPDATE public.appointments
            SET replaced_appointment_id = NULL
            WHERE appointment_id IN (SELECT appointment_id FROM delete_candidates)
               OR replaced_appointment_id IN (SELECT appointment_id FROM delete_candidates)
            """,
            ids,
            RACE_SLOT_ID,
        )
        await conn.execute(
            """
            DELETE FROM public.appointments
            WHERE (
                shipment_id = ANY($1::text[])
                OR slot_id = $2
              )
              AND appointment_id NOT IN ('D16-APT-RAVI-OLD', 'APT1017')
              AND (
                booking_source = 'DRIVER_CHAT'
                OR appointment_id LIKE 'APT-%'
                OR appointment_id NOT LIKE 'D16-APT-%'
              )
            """,
            ids,
            RACE_SLOT_ID,
        )
        await conn.execute(
            """
            DELETE FROM public.eta_updates
            WHERE shipment_id = ANY($1::text[])
              AND (
                (
                  shipment_id LIKE 'SHP-D16-%'
                  AND source_type <> 'ORIGINAL_PLAN'
                )
                OR (
                  shipment_id = 'SHP1017'
                  AND eta_update_id <> 'ETA012'
                )
              )
            """,
            ids,
        )
        await conn.execute(
            """
            DELETE FROM public.idempotency_requests
            WHERE route LIKE ANY($1::text[])
               OR user_id = ANY($2::text[])
            """,
            [f"%{sid}%" for sid in ids],
            list(REDIS_USER_IDS),
        )

        for shipment_id in ids:
            golden = GOLDEN_SHIPMENTS.get(shipment_id)
            if not golden:
                continue
            await conn.execute(
                """
                UPDATE public.shipments
                SET latest_eta_ts = $2,
                    expected_unload_min = $3,
                    current_status = $4,
                    updated_at = $5
                WHERE shipment_id = $1
                """,
                shipment_id,
                golden["latest_eta_ts"],
                golden["expected_unload_min"],
                golden["current_status"],
                "2026-08-16T16:00:00+05:30",
            )

        await conn.execute(
            """
            UPDATE public.appointments
            SET appointment_status = 'CONFIRMED',
                is_current = 1,
                booking_source = 'PLANNER',
                confirmed_at = COALESCE(confirmed_at, '2026-08-15T09:00:00+05:30'),
                cancelled_at = NULL,
                cancellation_reason = NULL,
                warehouse_confirmation_ref = COALESCE(
                  warehouse_confirmation_ref, 'WH-D16-APT-RAVI-OLD'
                ),
                updated_at = '2026-08-15T09:00:00+05:30'
            WHERE appointment_id = $1
            """,
            RAVI_OLD_APPOINTMENT_ID,
        )

        if "SHP1017" in ids:
            await conn.execute(
                """
                UPDATE public.appointments
                SET appointment_status = 'CONFIRMED',
                    is_current = 1,
                    booking_source = 'PLANNER',
                    confirmed_at = COALESCE(confirmed_at, '2026-08-01T12:25:00+05:30'),
                    cancelled_at = NULL,
                    cancellation_reason = NULL,
                    warehouse_confirmation_ref = COALESCE(
                      warehouse_confirmation_ref, 'WH-JAI-9017'
                    ),
                    updated_at = '2026-08-04T10:00:00+05:30'
                WHERE appointment_id = 'APT1017'
                """
            )

        # Ensure race slot has no leftover active claim (belt-and-suspenders).
        await conn.execute(
            """
            UPDATE public.appointments
            SET appointment_status = 'CANCELLED',
                is_current = 0,
                cancelled_at = COALESCE(cancelled_at, '2026-08-16T16:00:00+05:30'),
                cancellation_reason = COALESCE(
                  cancellation_reason, 'demo_day_cast_reset'
                ),
                updated_at = '2026-08-16T16:00:00+05:30'
            WHERE slot_id = $1
              AND appointment_status IN
                ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS', 'EXPIRED')
              AND is_current = 1
            """,
            RACE_SLOT_ID,
        )

    return summary


async def plan_full(conn: Any) -> PlanSummary:
    summary = PlanSummary()
    checks = [
        ("chat_messages_D16", "SELECT count(*) FROM public.chat_messages WHERE chat_message_id LIKE 'D16-%'"),
        ("driver_exceptions_D16", "SELECT count(*) FROM public.driver_exceptions WHERE exception_id LIKE 'D16-%'"),
        ("chat_threads_D16", "SELECT count(*) FROM public.chat_threads WHERE thread_id LIKE 'D16-%'"),
        ("facility_checkins_D16", "SELECT count(*) FROM public.facility_checkins WHERE checkin_id LIKE 'D16-%'"),
        ("appointments_D16", "SELECT count(*) FROM public.appointments WHERE appointment_id LIKE 'D16-%'"),
        ("eta_updates_D16", "SELECT count(*) FROM public.eta_updates WHERE eta_update_id LIKE 'D16-%'"),
        ("shipments_SHP_D16", "SELECT count(*) FROM public.shipments WHERE shipment_id LIKE 'SHP-D16-%'"),
        ("slots_D16", "SELECT count(*) FROM public.appointment_slots WHERE slot_id LIKE 'D16-%'"),
        ("vehicles_D16", "SELECT count(*) FROM public.vehicles WHERE vehicle_id LIKE 'D16-%'"),
        ("drivers_D16", "SELECT count(*) FROM public.drivers WHERE driver_id LIKE 'D16-%'"),
        ("facility_rules_D16", "SELECT count(*) FROM public.facility_rules WHERE rule_id LIKE 'D16-%'"),
        ("docks_D16", "SELECT count(*) FROM public.docks WHERE dock_id LIKE 'D16-%'"),
        (
            "demo_facilities",
            """
            SELECT count(*) FROM public.facilities
            WHERE facility_id IN ('FAC-DEL-01','FAC-AMD-01','FAC-PNQ-01','FAC-BLR-01')
            """,
        ),
        (
            "escalation_SHP_D16",
            "SELECT count(*) FROM public.escalation_queue WHERE shipment_id LIKE 'SHP-D16-%'",
        ),
    ]
    for label, sql in checks:
        summary.add(label, await _count(conn, sql))
    return summary


async def execute_full_wipe(conn: Any, *, dry_run: bool) -> PlanSummary:
    summary = await plan_full(conn)
    if dry_run:
        return summary

    async with conn.transaction():
        # FK-safe order: children first, then D16 inventory, then optional demo facilities.
        await conn.execute(
            "DELETE FROM public.escalation_queue WHERE shipment_id LIKE 'SHP-D16-%'"
        )
        await conn.execute(
            "DELETE FROM public.chat_messages WHERE chat_message_id LIKE 'D16-%'"
        )
        await conn.execute(
            "DELETE FROM public.driver_exceptions WHERE exception_id LIKE 'D16-%'"
        )
        await conn.execute(
            "DELETE FROM public.chat_threads WHERE thread_id LIKE 'D16-%'"
        )
        await conn.execute(
            "DELETE FROM public.facility_checkins WHERE checkin_id LIKE 'D16-%'"
        )
        await conn.execute(
            "DELETE FROM public.appointments WHERE appointment_id LIKE 'D16-%'"
        )
        await conn.execute(
            "DELETE FROM public.eta_updates WHERE eta_update_id LIKE 'D16-%'"
        )
        await conn.execute(
            "DELETE FROM public.shipments WHERE shipment_id LIKE 'SHP-D16-%'"
        )
        await conn.execute(
            "DELETE FROM public.appointment_slots WHERE slot_id LIKE 'D16-%'"
        )
        # Do not delete USR2% Auth-mapped users (Auth identities stay).
        await conn.execute(
            "DELETE FROM public.vehicles WHERE vehicle_id LIKE 'D16-%'"
        )
        await conn.execute(
            "DELETE FROM public.drivers WHERE driver_id LIKE 'D16-%'"
        )
        await conn.execute(
            "DELETE FROM public.facility_rules WHERE rule_id LIKE 'D16-%'"
        )
        await conn.execute(
            "DELETE FROM public.docks WHERE dock_id LIKE 'D16-%'"
        )
        await conn.execute(
            """
            DELETE FROM public.facilities
            WHERE facility_id IN ('FAC-DEL-01','FAC-AMD-01','FAC-PNQ-01','FAC-BLR-01')
            """
        )
        await conn.execute(
            """
            DELETE FROM public.idempotency_requests
            WHERE route LIKE '%SHP-D16-%'
               OR route LIKE '%D16-%'
               OR user_id = ANY($1::text[])
            """,
            list(REDIS_USER_IDS),
        )
    return summary


async def apply_sql(conn: Any, sql_path: Path) -> None:
    sql = sql_path.read_text(encoding="utf-8")
    print(f"Re-applying {sql_path.name} ({len(sql)} chars)...")
    await conn.execute(sql)
    print("APPLY_OK")


def clear_redis(*, dry_run: bool) -> PlanSummary:
    summary = PlanSummary()
    url = (os.environ.get("UPSTASH_REDIS_REST_URL") or "").strip()
    token = (os.environ.get("UPSTASH_REDIS_REST_TOKEN") or "").strip()
    if not url or not token:
        summary.add("redis_keys_skipped_unset", 0)
        print("Redis: UPSTASH_REDIS_REST_* unset — skipping chat memory clear.")
        return summary

    try:
        from upstash_redis import Redis

        client = Redis(url=url, token=token)
    except Exception as exc:  # noqa: BLE001
        summary.add("redis_keys_skipped_init_failed", 0)
        print(f"Redis: init failed ({type(exc).__name__}) — skipping.")
        return summary

    matched: list[str] = []
    for user_id in REDIS_USER_IDS:
        pattern = f"setuhaul:chat:{user_id}:*"
        try:
            keys = client.keys(pattern) or []
        except Exception as exc:  # noqa: BLE001
            print(f"Redis: keys({pattern}) failed ({type(exc).__name__})")
            continue
        if isinstance(keys, list):
            matched.extend(str(k) for k in keys)

    # De-dupe while preserving order
    seen: set[str] = set()
    unique_keys: list[str] = []
    for key in matched:
        if key in seen:
            continue
        seen.add(key)
        unique_keys.append(key)

    summary.add("redis_keys", len(unique_keys))
    if dry_run:
        return summary

    deleted = 0
    for key in unique_keys:
        try:
            client.delete(key)
            deleted += 1
        except Exception as exc:  # noqa: BLE001
            print(f"Redis: delete failed for one key ({type(exc).__name__})")
    summary.counts["redis_keys_deleted"] = deleted
    return summary


def print_summary(title: str, summary: PlanSummary) -> None:
    print(title)
    if not summary.actions:
        print("  (nothing matched)")
        return
    for action in summary.actions:
        print(f"  {action}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("cast", "full"),
        default="cast",
        help="cast = hero cast + Redis (default); full = D16 wipe + re-apply SQL",
    )
    parser.add_argument(
        "--demo-day",
        default=DEFAULT_DEMO_DAY,
        help=f"Demo day used for full re-apply SQL (default {DEFAULT_DEMO_DAY})",
    )
    parser.add_argument(
        "--include-shp1017",
        action="store_true",
        help="Also reset baseline SHP1017 / APT1017 (cast mode)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts only; no Postgres/Redis writes",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required for non-dry-run writes (or set SETUHAUL_DEMO_RESET=1)",
    )
    parser.add_argument(
        "--skip-redis",
        action="store_true",
        help="Skip Upstash chat-memory clear",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    import asyncpg

    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("DATABASE_URL missing (load .env.local / .env)")

    if not confirm_allowed(args):
        raise SystemExit(
            "Refusing to run: pass --confirm or set SETUHAUL_DEMO_RESET=1 "
            "(or use --dry-run)."
        )

    mode = "DRY-RUN " if args.dry_run else ""
    print(f"{mode}mode={args.mode} demo_day={args.demo_day}")

    conn = await asyncpg.connect(url, statement_cache_size=0, timeout=180)
    try:
        if args.mode == "cast":
            ids = cast_ids(include_shp1017=args.include_shp1017)
            print(f"cast_shipments={len(ids)}")
            summary = await execute_cast(conn, ids, dry_run=args.dry_run)
            print_summary("Postgres cast plan:", summary)
        else:
            wipe = await execute_full_wipe(conn, dry_run=args.dry_run)
            print_summary("Postgres full wipe plan:", wipe)
            if not args.dry_run:
                sql_path = (
                    ROOT / "supabase" / "demo" / "out" / f"demo_day_{args.demo_day}.sql"
                )
                if not sql_path.exists():
                    raise SystemExit(f"Missing {sql_path}")
                await apply_sql(conn, sql_path)
    finally:
        await conn.close()

    if args.skip_redis:
        print("Redis: skipped (--skip-redis)")
    else:
        redis_summary = clear_redis(dry_run=args.dry_run)
        print_summary("Redis plan:", redis_summary)

    print("RESET_OK" if not args.dry_run else "DRY_RUN_OK")
    return 0


def main() -> None:
    load_env(ROOT / ".env.local")
    load_env(ROOT / ".env")
    args = parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
