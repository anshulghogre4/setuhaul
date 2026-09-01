#!/usr/bin/env python3
"""Owner-run applier for 20260902093000_notification_outbox.sql (#94).

Why owner-run: the agent session's classifier gates production DDL. Same shape as
deploy/apply_96_dedupe_migration.py, which ran clean twice.

Does: (1) pg_dump backup of the two existing notification tables (the new one has no
data to lose; the RLS lockdown touches these two), (2) applies the migration (one psql
session, ON_ERROR_STOP, lock_timeout 5s, the file's own transaction), (3) runs the
migration footer's verification queries and prints PASS/FAIL.

NOTE this migration also enables RLS + revokes anon/authenticated grants on
notifications/notification_preferences -- closing a real PostgREST exposure (#94's
security finding). Rollback for the outbox table is a plain DROP (footer); do NOT roll
back the RLS lockdown with it.

Safe to re-run: idempotent DO-block style throughout.
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260902093000_notification_outbox.sql"

url = None
for envfile in (ROOT / ".env.local", ROOT / ".env"):
    if not envfile.exists():
        continue
    for line in envfile.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip('"').strip("'")
    if url:
        break
if not url:
    sys.exit("DATABASE_URL not found")

backup = (Path.home() / "setuhaul-db-backups" /
          f"pre_outbox_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dump")
backup.parent.mkdir(exist_ok=True)
r = subprocess.run(["pg_dump", "-Fc", "-t", "public.notifications",
                    "-t", "public.notification_preferences", "-f", str(backup), url],
                   capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr[-300:])
    sys.exit("backup FAILED -- not applying")
print(f"backup OK: {backup} ({backup.stat().st_size} bytes)")

r = subprocess.run(["psql", url, "-v", "ON_ERROR_STOP=1",
                    "-c", "SET lock_timeout='5s';", "-f", str(MIGRATION)],
                   capture_output=True, text=True)
print(r.stdout[-400:])
if r.returncode != 0:
    print(r.stderr[-400:])
    sys.exit("APPLY FAILED -- lock_timeout abort is safe; re-run.")
print("APPLY OK. Verifying...")


def q(sql):
    rr = subprocess.run(["psql", url, "-X", "-A", "-t", "-c", sql],
                        capture_output=True, text=True)
    return rr.stdout.strip()


CHECKS = [
    ("outbox table has 18 columns",
     "SELECT count(*) FROM information_schema.columns "
     "WHERE table_schema='public' AND table_name='notification_outbox'", "18"),
    ("dedupe_key globally unique (NFR-009)",
     "SELECT count(*) FROM pg_indexes WHERE schemaname='public' "
     "AND indexname='notification_outbox_dedupe_key_uidx' AND indexdef LIKE '%UNIQUE%'", "1"),
    ("six CHECK constraints present",
     "SELECT count(*) FROM pg_constraint WHERE conrelid='public.notification_outbox'::regclass "
     "AND contype='c'", "6"),
    ("RLS enabled on all three notification tables",
     "SELECT count(*) FROM pg_class WHERE relname IN "
     "('notification_outbox','notifications','notification_preferences') AND relrowsecurity", "3"),
    ("zero anon/authenticated grants remain on the three tables",
     "SELECT count(*) FROM information_schema.role_table_grants "
     "WHERE table_schema='public' AND table_name IN "
     "('notification_outbox','notifications','notification_preferences') "
     "AND grantee IN ('anon','authenticated')", "0"),
    ("outbox starts empty (no backfill, by design)",
     "SELECT count(*) FROM public.notification_outbox", "0"),
]
ok = True
for name, sql, expect in CHECKS:
    got = q(sql)
    status = "PASS" if got == expect else "FAIL"
    ok = ok and got == expect
    print(f"  [{status}] {name} (got {got!r}, expected {expect!r})")
print("ALL VERIFICATIONS PASS" if ok else "VERIFICATION FAILURE -- report back before deploying")
sys.exit(0 if ok else 1)
