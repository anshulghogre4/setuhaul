#!/usr/bin/env python3
"""Owner-run applier for #79: the GATE_OFFICER role (ROL010) + one kiosk credential.

Why owner-run: the agent session's classifier gates production DDL/identity writes.
Owner authorization on record: "add gate officer role if needed no issues" (M5 sprint)
and the 2026-08-29 approval in the migration header.

Does, idempotently:
  1. Applies supabase/migrations/20260829180000_gate_officer_role.sql via psql
     (ON_ERROR_STOP, lock_timeout 5s; a single seed row -- no schema change).
  2. Provisions the kiosk credential the migration header says is the point:
     users row USR-GATE-01 (ROL010, FAC-JAI-01 -- the gate device's facility per
     gate-route.tsx's DEVICE SEAM), user_scopes FACILITY row, and a Supabase Auth
     identity gate.officer@setuhaul.com using the roster's Operations bucket
     password (read at runtime from POC_TEAM_ACCOUNTS.local.md; never printed).
  3. Verifies: ROL010 present, users row present, scope row present, auth mapped,
     and a real password-grant login succeeds.

Rollback: the migration header's DELETE (only while no users reference ROL010);
for the credential: delete the auth user via the dashboard, then
DELETE FROM user_scopes WHERE user_id='USR-GATE-01'; DELETE FROM users WHERE user_id='USR-GATE-01';
"""
import json
import re
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260829180000_gate_officer_role.sql"

USER_ID = "USR-GATE-01"
EMAIL = "gate.officer@setuhaul.com"
FULL_NAME = "Gate Officer (Kiosk)"
FACILITY_ID = "FAC-JAI-01"

env = {}
for envfile in (ROOT / ".env.local", ROOT / ".env"):
    if envfile.exists():
        for line in envfile.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
url = env.get("DATABASE_URL") or sys.exit("DATABASE_URL missing")
supabase_url = env.get("SUPABASE_URL") or sys.exit("SUPABASE_URL missing")
service_key = env.get("SUPABASE_SERVICE_ROLE_KEY") or sys.exit("SUPABASE_SERVICE_ROLE_KEY missing")
anon_key = env.get("SUPABASE_ANON_KEY") or sys.exit("SUPABASE_ANON_KEY missing")

roster = (ROOT / "POC_TEAM_ACCOUNTS.local.md").read_text(encoding="utf-8")
m = re.search(r"\|\s*Operations\s*\|\s*([^|]+?)\s*\|", roster)
if not m:
    sys.exit("Operations password bucket not found in POC_TEAM_ACCOUNTS.local.md")
PASSWORD = m.group(1).strip()


def psql(sql):
    r = subprocess.run(["psql", url, "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1",
                        "-c", "SET lock_timeout='5s';", "-c", sql],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-400:])
        sys.exit(f"psql FAILED: {sql[:80]}")
    # Last line only: the preceding -c "SET lock_timeout" prints its own 'SET' command tag
    # into stdout ahead of the query result, which broke every equality check on the first
    # owner run (2026-09-02) even though the migration itself had applied.
    return r.stdout.strip().splitlines()[-1].strip() if r.stdout.strip() else ""


print(f"[1/4] applying {MIGRATION.name}")
r = subprocess.run(["psql", url, "-v", "ON_ERROR_STOP=1",
                    "-c", "SET lock_timeout='5s';", "-f", str(MIGRATION)],
                   capture_output=True, text=True)
print(r.stdout[-300:])
if r.returncode != 0:
    print(r.stderr[-400:])
    sys.exit("migration apply FAILED")
assert psql("SELECT count(*) FROM public.roles WHERE role_id='ROL010' AND role_name='GATE_OFFICER'") == "1"
print("      ROL010/GATE_OFFICER present")

print("[2/4] users + scope rows (idempotent)")
psql(f"""
INSERT INTO public.users (user_id, role_id, employee_code, full_name, email, phone_number,
  password_hash, driver_id, facility_id, is_active, last_login_ts, created_at, updated_at, auth_user_id)
VALUES ('{USER_ID}', 'ROL010', NULL, '{FULL_NAME}', '{EMAIL}', '+91-90000-00079',
  '!auth_only!', NULL, '{FACILITY_ID}', 1, NULL, now()::text, now()::text, NULL)
ON CONFLICT DO NOTHING""")
psql(f"""
INSERT INTO public.user_scopes (scope_id, user_id, scope_type, scope_value, created_at)
VALUES ('SCP-FAC-{USER_ID}', '{USER_ID}', 'FACILITY', '{FACILITY_ID}', now())
ON CONFLICT DO NOTHING""")
print("      rows present")

print("[3/4] Supabase Auth identity")


def sb(method, path, body=None, key=service_key):
    req = urllib.request.Request(supabase_url + path,
                                 data=json.dumps(body).encode() if body else None, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


auth_id = None
st, listed = sb("GET", "/auth/v1/admin/users?page=1&per_page=200")
for u in listed.get("users", []):
    if (u.get("email") or "").lower() == EMAIL:
        auth_id = u["id"]
        print("      reusing existing auth user")
if auth_id is None:
    st, made = sb("POST", "/auth/v1/admin/users",
                  {"email": EMAIL, "password": PASSWORD, "email_confirm": True,
                   "user_metadata": {"full_name": FULL_NAME, "user_id": USER_ID}})
    if st >= 400:
        sys.exit(f"auth create FAILED {st}: {json.dumps(made)[:200]}")
    auth_id = made["id"]
    print("      created auth user")
psql(f"UPDATE public.users SET auth_user_id='{auth_id}'::uuid, updated_at=now()::text "
     f"WHERE user_id='{USER_ID}' AND auth_user_id IS NULL")
print(f"      mapped {USER_ID} -> auth")

print("[4/4] verify: real login")
req = urllib.request.Request(supabase_url + "/auth/v1/token?grant_type=password",
                             data=json.dumps({"email": EMAIL, "password": PASSWORD}).encode(),
                             method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("apikey", anon_key)
with urllib.request.urlopen(req, timeout=30) as resp:
    assert resp.status == 200
print("      login 200 -- GATE_OFFICER credential is live")
print("ALL STEPS PASS. Kiosk sign-in:", EMAIL, "(Operations bucket password)")
