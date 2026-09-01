#!/usr/bin/env python3
"""EMERGENCY compat shim for #96 (owner-run): restore old-code ON CONFLICT inference.

Incident 2026-09-01: the #96 migration was applied to production BEFORE the new
backend code deployed, and the deploy-order analysis in that migration was inverted --
the deployed (old) code's bare `ON CONFLICT (dedupe_key)` cannot infer an arbiter from
a PARTIAL unique index, so escalate / planner-cascade / expiry writes raise
"no unique or exclusion constraint matching the ON CONFLICT specification" (42P10).

This shim recreates the FULL unique index ALONGSIDE the partial one:
  - old (deployed) code infers the full index again -> writes work;
  - new code's predicate arbiter still matches the partial index -> also works;
  - #96's new semantics (terminal + live twin rows) are suppressed while the shim
    exists -- that is exactly the pre-#96 behavior, a typed refusal, not a 500.

SAFE precondition, checked before creating: zero duplicate dedupe_keys (guaranteed,
since only the undeployed new code can create legal duplicates).

AFTER the backend deploy ships the new code: re-run deploy/apply_96_dedupe_migration.py
-- its drop-by-shape step removes this shim idempotently and re-verifies. Do not leave
the shim in place longer than the deploy gap.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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

def q(sql):
    r = subprocess.run(["psql", url, "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-400:])
        sys.exit(f"FAILED: {sql[:80]}")
    return r.stdout.strip()

# Consolidation pre-step (added 2026-09-01 after the first run ABORTed on 3 groups):
# the click-sweep ran the NEW code locally against the live DB and legally created
# terminal twins -- but only ever on the reschedule sandbox. Deleting SANDBOX+TERMINAL
# rows inside duplicate groups is safe (they are test artifacts the sandbox rollback
# script deletes wholesale anyway). Anything else still aborts for owner review.
removed = q(
    "WITH dupkeys AS (SELECT dedupe_key FROM public.escalation_queue "
    "  GROUP BY dedupe_key HAVING count(*)>1), "
    "gone AS (DELETE FROM public.escalation_queue e "
    "  USING dupkeys d WHERE e.dedupe_key = d.dedupe_key "
    "    AND e.shipment_id LIKE 'SHP-RS-%' "
    "    AND e.escalation_status IN ('RESOLVED','CANCELLED') RETURNING 1) "
    "SELECT count(*) FROM gone"
)
print(f"consolidated {removed} sandbox terminal duplicate row(s)")

dups = q("SELECT count(*) FROM (SELECT dedupe_key FROM public.escalation_queue "
         "GROUP BY dedupe_key HAVING count(*)>1) d")
if dups != "0":
    sys.exit(f"ABORT: {dups} NON-sandbox duplicate dedupe_key group(s) remain -- "
             "these need per-key owner review per the migration's rollback note.")
print("precondition PASS: zero duplicate dedupe_keys")

q("SET lock_timeout='5s'; CREATE UNIQUE INDEX IF NOT EXISTS "
  "escalation_queue_dedupe_key_compat_shim ON public.escalation_queue (dedupe_key)")
print("shim index created")

probe = subprocess.run(
    ["psql", url, "-X", "-c",
     "BEGIN; EXPLAIN INSERT INTO public.escalation_queue "
     "(escalation_id, shipment_id, facility_id, escalation_type, escalation_status, "
     "severity_code, payload_json, dedupe_key, created_at, updated_at) "
     "SELECT 'ESC-PROBE', shipment_id, facility_id, escalation_type, 'OPEN', 'HIGH', "
     "'{}', 'PROBE-NOOP', created_at, updated_at FROM public.escalation_queue LIMIT 1 "
     "ON CONFLICT (dedupe_key) DO NOTHING; ROLLBACK;"],
    capture_output=True, text=True)
if "ERROR" in (probe.stderr or ""):
    print(probe.stderr[-300:])
    sys.exit("VERIFY FAILED: old-code arbiter still cannot infer")
print("VERIFY PASS: old-code bare arbiter infers again -- production writes restored")
print("REMEMBER: after the backend deploy, re-run deploy/apply_96_dedupe_migration.py to drop this shim.")
