#!/usr/bin/env python3
"""Owner-run applier for migration 20260901120000_escalation_dedupe_nonterminal_only.sql (#96).

Why this script exists: the agent session's permission classifier gates direct
production DDL, so the owner runs this one command instead. It does exactly what
the migration's own live-apply plan specifies -- one psql session, ON_ERROR_STOP,
lock_timeout 5s, the file's own BEGIN/COMMIT (deliberately NOT -1: wrapping the
SET into the file's transaction would revert it on the rollback path it protects).
Then it runs the read-only verification queries and prints PASS/FAIL per check.

Safe to re-run: the migration is idempotent (create-then-drop, shape-matched).
Rollback: see the migration header. Table backup taken 2026-09-01 12:21 IST at
C:/Users/ANSHUL/setuhaul-db-backups/pre_esc_dedupe_20260901_122115.dump
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260901120000_escalation_dedupe_nonterminal_only.sql"

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
    sys.exit("DATABASE_URL not found in .env.local/.env")

print(f"Applying {MIGRATION.name} ...")
r = subprocess.run(
    ["psql", url, "-v", "ON_ERROR_STOP=1",
     "-c", "SET lock_timeout='5s';", "-f", str(MIGRATION)],
    capture_output=True, text=True,
)
print(r.stdout[-800:])
if r.returncode != 0:
    print(r.stderr[-800:])
    sys.exit(f"APPLY FAILED rc={r.returncode} -- lock_timeout abort is safe; just re-run.")
print("APPLY OK. Verifying...")

CHECKS = [
    ("new partial unique index present with correct predicate",
     "SELECT count(*) FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid "
     "WHERE i.indrelid='public.escalation_queue'::regclass "
     "AND ic.relname='escalation_queue_dedupe_key_active_uidx' AND i.indisunique "
     "AND pg_get_expr(i.indpred,i.indrelid) LIKE '%RESOLVED%CANCELLED%'", "1"),
    ("old global UNIQUE constraint gone",
     "SELECT count(*) FROM pg_constraint WHERE conrelid='public.escalation_queue'::regclass "
     "AND contype='u'", "0"),
    ("no full-table unique index on dedupe_key remains",
     "SELECT count(*) FROM pg_index i JOIN pg_class ic ON ic.oid=i.indexrelid "
     "WHERE i.indrelid='public.escalation_queue'::regclass AND i.indisunique "
     "AND i.indpred IS NULL AND ic.relname <> 'escalation_queue_pkey'", "0"),
    ("live-row uniqueness holds (no live duplicates)",
     "SELECT count(*) FROM (SELECT dedupe_key FROM public.escalation_queue "
     "WHERE escalation_status NOT IN ('RESOLVED','CANCELLED') "
     "GROUP BY dedupe_key HAVING count(*)>1) d", "0"),
]
ok = True
for name, q, expect in CHECKS:
    res = subprocess.run(["psql", url, "-X", "-A", "-t", "-c", q],
                         capture_output=True, text=True)
    got = res.stdout.strip()
    status = "PASS" if got == expect else "FAIL"
    ok = ok and got == expect
    print(f"  [{status}] {name} (got {got!r}, expected {expect!r})")
print("ALL VERIFICATIONS PASS" if ok else "VERIFICATION FAILURE -- do not deploy; report back")
sys.exit(0 if ok else 1)
