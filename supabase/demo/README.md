# SetuHaul demo-day data

`generate_demo_day.py` creates deterministic, additive PostgreSQL data for a
seven-day window ending on the requested demo day. It does not delete or
rewrite the baseline 4 August seed.

## Generate

From the repository root:

```powershell
python supabase/demo/generate_demo_day.py --demo-day 2026-08-16 --emit counts
python supabase/demo/generate_demo_day.py --demo-day 2026-08-16 --emit sql
```

The SQL command writes:

```text
supabase/demo/out/demo_day_2026-08-16.sql
```

Run `--emit counts` first when reviewing a change. It validates identifier,
slot-window, active-appointment, race-slot, timestamp-offset, and target-count
invariants without writing a file.

## Apply

Review the generated SQL and use a PostgreSQL connection with the required
permissions:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f "supabase/demo/out/demo_day_2026-08-16.sql"
```

Alternatively, paste the reviewed SQL into an authorized Supabase SQL workflow
or apply it through the Supabase MCP SQL execution tool. The file is wrapped in
one transaction and uses `ON CONFLICT DO NOTHING` so a repeat run is additive
and does not erase baseline data.

The cleanup block at the bottom is commented out intentionally. Prefer the
reset script below instead of hand-editing that block.

## Reset between demos

Re-applying the demo SQL is **additive** (`ON CONFLICT DO NOTHING`). It does
**not** undo ETA confirms, `request_slot` / cancel / confirm mutations,
`escalation_queue` rows, or Upstash chat memory. Use
`reset_demo_day.py` before a fresh shared Ravi show.

```powershell
# Preview (no writes)
python supabase/demo/reset_demo_day.py --mode cast --include-shp1017 --dry-run

# Between team demos (hero cast + optional SHP1017 + Redis chat clear)
python supabase/demo/reset_demo_day.py --mode cast --include-shp1017 --confirm

# Rare deep refresh: wipe D16-% / SHP-D16-% inventory, then re-apply SQL
python supabase/demo/reset_demo_day.py --mode full --confirm
```

Safety:

- Non-dry-run requires `--confirm` or `SETUHAUL_DEMO_RESET=1`.
- Loads `DATABASE_URL` / Upstash from root `.env.local` / `.env` (never logs secrets).
- Does **not** reset Auth passwords or delete Auth users.
- `--mode cast` restores golden cast fields (e.g. `SHP-D16-RAVI` ETA 18:30 /
  unload 25, `D16-APT-RAVI-OLD` historical CANCELLED / not current so Phase B
  `request_slot` can run, race slot free) and clears Redis keys
  for `USR001`–`USR003` and `USR201`–`USR210`. `APT1017` stays CONFIRMED.

## Authentication boundary

The generator creates `public.users` rows for the 12 contention drivers with
`password_hash = '!auth_only!'`. This value is a non-secret placeholder and is
not a usable password. Supabase Auth identities and passwords must be created
separately through an approved secure workflow. Never put real passwords,
service-role keys, access tokens, or database credentials in generated SQL.

## Capacity note

All nine docks at the two hero facilities receive 30-minute slots across their
full open hours. Each added facility has four physical docks and two
representative slot-enabled docks in this bounded demo inventory. This yields
2,828 slots while preserving all three dock types across the six-facility
network and keeping the requested full-brief-ish scale practical.
