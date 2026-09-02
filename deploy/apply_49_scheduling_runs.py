#!/usr/bin/env python3
"""Owner-run applier for 20260902160000_scheduling_runs.sql (#49, the §7.5.3 Sequencer).

Why owner-run: the agent session's classifier gates production DDL (same as #96/#94).
ORDER: this migration ALTERs notification_outbox (adds APPOINTMENT_RESEQUENCED to its
event CHECK), so deploy/apply_94_outbox_migration.py MUST run first -- this script
refuses to proceed if that table is absent.

Does: table backup of notification_outbox -> psql apply (ON_ERROR_STOP, lock_timeout 5s,
the file's own BEGIN/COMMIT -- deliberately no -1) -> the migration footer's verification
queries, printed PASS/FAIL. Idempotent; a lock_timeout abort is safe, just re-run.
Rollback: see the migration footer (two halves; the outbox CHECK half only after
confirming zero APPOINTMENT_RESEQUENCED rows).
"""
import datetime
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260902160000_scheduling_runs.sql"
BACKUP_DIR = Path.home() / "setuhaul-db-backups"

url = None
for envfile in (ROOT / ".env.local", ROOT / ".env"):
    if envfile.exists():
        for line in envfile.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
    if url:
        break
if not url:
    sys.exit("DATABASE_URL not found")


def q(sql):
    r = subprocess.run(["psql", url, "-X", "-A", "-t", "-c", sql], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-300:])
        sys.exit(f"query FAILED: {sql[:70]}")
    return r.stdout.strip()


if q("SELECT to_regclass('public.notification_outbox') IS NOT NULL") != "t":
    sys.exit("PRECONDITION FAILED: notification_outbox absent -- run deploy/apply_94_outbox_migration.py first")
if q("SELECT to_regclass('public.scheduling_runs') IS NOT NULL") == "t":
    print("scheduling_runs already exists -- migration is idempotent, continuing to verification")

BACKUP_DIR.mkdir(exist_ok=True)
b = BACKUP_DIR / f"pre_scheduling_runs_{datetime.datetime.now():%Y%m%d_%H%M%S}.dump"
r = subprocess.run(["pg_dump", "-Fc", "-t", "public.notification_outbox", "-f", str(b), url],
                   capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr[-300:])
    sys.exit("backup FAILED -- not applying")
print(f"backup: {b} ({os.path.getsize(b)} bytes)")

print(f"applying {MIGRATION.name} ...")
r = subprocess.run(["psql", url, "-v", "ON_ERROR_STOP=1", "-c", "SET lock_timeout='5s';",
                    "-f", str(MIGRATION)], capture_output=True, text=True)
print(r.stdout[-500:])
if r.returncode != 0:
    print(r.stderr[-500:])
    sys.exit("APPLY FAILED -- a lock_timeout abort is safe; re-run")
print("APPLY OK. Verifying ...")

CHECKS = [
    ("scheduling_runs table present",
     "SELECT to_regclass('public.scheduling_runs') IS NOT NULL", "t"),
    ("one-active-run-per-facility partial unique index",
     "SELECT count(*) FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid "
     "WHERE i.indrelid='public.scheduling_runs'::regclass AND i.indisunique "
     "AND pg_get_expr(i.indpred,i.indrelid) LIKE '%PROPOSED%'", "1"),
    ("RLS enabled on scheduling_runs",
     "SELECT relrowsecurity::text FROM pg_class WHERE oid='public.scheduling_runs'::regclass", "true"),
    ("no anon/authenticated grants on scheduling_runs",
     "SELECT count(*) FROM information_schema.role_table_grants "
     "WHERE table_schema='public' AND table_name='scheduling_runs' "
     "AND grantee IN ('anon','authenticated')", "0"),
    ("outbox CHECK admits APPOINTMENT_RESEQUENCED",
     "SELECT count(*) FROM pg_constraint WHERE conrelid='public.notification_outbox'::regclass "
     "AND contype='c' AND pg_get_constraintdef(oid) LIKE '%APPOINTMENT_RESEQUENCED%'", "1"),
    ("table starts empty", "SELECT count(*) FROM public.scheduling_runs", "0"),
]
ok = True
for name, sql, expect in CHECKS:
    got = q(sql)
    status = "PASS" if got == expect else "FAIL"
    ok = ok and got == expect
    print(f"  [{status}] {name} (got {got!r}, expected {expect!r})")
print("ALL VERIFICATIONS PASS" if ok else "VERIFICATION FAILURE -- report back before deploying")
sys.exit(0 if ok else 1)
