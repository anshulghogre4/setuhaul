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

The cleanup block at the bottom is commented out intentionally. If cleanup is
needed, review dependency order and the namespace predicates before manually
uncommenting it.

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
