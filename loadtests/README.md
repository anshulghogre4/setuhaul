# SetuHaul Locust (runbook-aligned)

Maps [`docs/DEMO_MANUAL_RUNBOOK.md`](../docs/DEMO_MANUAL_RUNBOOK.md) to two files. Locust runs on the **laptop** and hits the hosted BFF. Passwords come from gitignored `POC_TEAM_ACCOUNTS.local.md`.

| File | Runbook / design | LLM? |
|---|---|---|
| `locust_runbook_chat.py` | Phases A–D exact prompts; E5/C5 writes only if `SETUHAUL_LOCUST_MUTATE=1` | Yes |
| `locust_slot_contention.py` | Phase G + §9.2 race 1 `same_interval_race` (50-way) | No (REST) |
| `locust_hold_expiry_confirm.py` | §9.2 race 2 `hold_expiry_vs_confirm` | No (REST) |
| `locust_pending_expiry_confirm.py` | §9.2 race 3 `pending_expiry_vs_planner_confirm` | No (REST) |
| `locust_ordinal_staleness.py` | §9.2 race 4 `ordinal_staleness` | No (REST) |

Phase F (Ops UI) is not Locust. Reset the cast before a mutating run:

```powershell
python supabase/demo/reset_demo_day.py --mode cast --include-shp1017 --confirm
```

Run every command from the **repo root**. Needs `POC_TEAM_ACCOUNTS.local.md` + `.env.local` (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`).

**Default host (changed 2026-09-02, issue #42):** `https://d382h70qmz3ife.cloudfront.net` — the live CloudFront distribution in front of the `ap-south-1` ALB. The previous default was the retired `us-east-1` Express BFF (`https://se-…ecs.us-east-1.on.aws`), which every run since the E7.1 region migration had to override by hand. Override with `-H` or `SETUHAUL_BFF_URL`; for a local stack use `-H http://127.0.0.1:8000` (`common.LOCAL_BFF`).

## Suite A — short chat (keep small)

Web UI (open http://127.0.0.1:8089, Start with 5 users / 1 per second):

```powershell
uv run --with locust locust -f loadtests/locust_runbook_chat.py --web-host 127.0.0.1 --web-port 8089
```

Headless:

```powershell
uv run --with locust locust -f loadtests/locust_runbook_chat.py --headless -u 5 -r 1 -t 3m
```

## Pass / fail vs the runbook

Locust **200** means the host answered. It does **not** tick Phase A–G in `docs/DEMO_MANUAL_RUNBOOK.md` (those need the reply text / one active claim). Suite A fail = `http_5xx` or `success_false` (2026-08-14: one C2 503).

---

# The four §9.2 race suites (issue #42)

`SOLUTION_DESIGN.md` §9.2 names four concurrency races; `TESTING_STRATEGY.md` §3a states what each must produce. One suite per race. All four are REST-only (no LLM, no cost) and all four run **read-only** unless `SETUHAUL_LOCUST_MUTATE=1` is set.

| Suite | §9.2 | Must produce |
|---|---|---|
| `locust_slot_contention.py` | 1 `same_interval_race` | Exactly **1** `SLOT_HELD` · **N−1** `SLOT_CONFLICT_REFRESH_REQUIRED` **with fresh options** · **zero 5xx** |
| `locust_hold_expiry_confirm.py` | 2 `hold_expiry_vs_confirm` | Exactly one outcome — never both a lapse notice and a pending appointment · interval re-acquirable after the lapse |
| `locust_pending_expiry_confirm.py` | 3 `pending_expiry_vs_planner_confirm` | Exactly one of {CONFIRMED, EXPIRED} wins · loser gets `ALREADY_ACTIONED` · **the audit log names the winner** |
| `locust_ordinal_staleness.py` | 4 `ordinal_staleness` | Stale `recommendation_id` **rejected and re-presented** · never applied to the new list · zero writes |

Each file's module docstring carries its own design citations, its full target set, and the reasoning behind every assertion. Read it before running the suite.

## Before any mutating run

1. **Reset the cast** — required for suites 1 and 3, which use `SHP-D16-*` rows:

   ```powershell
   python supabase/demo/reset_demo_day.py --mode cast --include-shp1017 --confirm
   ```

   Verified 2026-09-02 against the local stack: on an **un-reset** cast, `D16-SLT-RACE` is offered to nobody and six of the ten `SHP-D16-CONTEND-*` shipments return `NO_FEASIBLE_SLOT`. Suite 1 detects this during arming and refuses to write, printing `FAIL_fixture_not_raceable` rather than a misleading "no winner".

2. **Confirm the sandbox exists** — suites 2 and 4 self-provision on `SHP-RS-OPEN`, which `reset_demo_day.py` never touches in either mode:

   ```powershell
   python supabase/demo/seed_reschedule_driver.py --dry-run
   ```

3. **`JOB_AUTH_TOKEN`** must be readable (env or root `.env.local`) for the sweeper leg of suites 2 and 3. Suite 2 skips that leg with a stated reason without it; **suite 3 fails** without it, because the sweeper *is* half of race 3. Probe the guard without sweeping anything by sending a deliberately wrong token — a healthy route answers `401 JOB_AUTH_INVALID`.

## 1 · `same_interval_race`

```powershell
$env:SETUHAUL_LOCUST_MUTATE="1"
uv run --with locust locust -f loadtests/locust_slot_contention.py --headless -u 50 -r 50 -t 90s
```

| | |
|---|---|
| Identities | `driver.drv004@` – `driver.drv013@` (10 cast drivers, 50 users round-robin) |
| Shipments | `SHP-D16-CONTEND-01` .. `-10` |
| Contested interval | `D16-SLT-RACE` — DOCK-JAI-D1 19:00–19:30, FAC-JAI-01 |
| Env | `SETUHAUL_RACE_SLOT_ID` (override interval) · `SETUHAUL_RACE_ARM_SECONDS` (default 20) · `SETUHAUL_RACE_TARGET_MODE=leader` (race the cast's own top interval when the named one is unavailable) |
| Leaves behind | one `HELD` `dock_occupancy` row, self-expiring in 90 s. No appointment |
| Exit 1 on | `FAIL_5xx` · `FAIL_winner_count` · `FAIL_refusal_count` · `FAIL_unexpected_codes` · `FAIL_refusal_without_options` · `FAIL_no_db_level_contention` · `FAIL_double_book` · `FAIL_fixture_not_raceable` |

`FAIL_no_db_level_contention` is the one that stops a green run from being hollow: at least one refusal must carry `POSTGRES_UNIQUE_ALLOCATION_CONFLICT`, i.e. D1's exclusion constraint actually decided the race rather than a pre-check filtering everyone out first.

## 2 · `hold_expiry_vs_confirm`

```powershell
$env:SETUHAUL_LOCUST_MUTATE="1"
uv run --with locust locust -f loadtests/locust_hold_expiry_confirm.py --headless -u 1 -r 1 -t 5m
```

| | |
|---|---|
| Identity / shipment | `driver.resched@setuhaul.com` / `SHP-RS-OPEN` (sandbox, FAC-GGN-01) |
| Interval | the shipment's own top feasible option — never invented |
| Env | `SETUHAUL_HOLD_LAPSE_MARGIN_S` (3) · `SETUHAUL_HOLD_RACE_LEAD_MS` (150) · `SETUHAUL_LOCUST_CLEANUP=0` to leave a won appointment in place |
| Runtime | ~3.5 min — two 90-second TTLs run end to end. Do not shorten `-t` below `5m` |
| Leaves behind | nothing needing cleanup: a won race is cancelled by the suite, lapsed holds self-expire |

Three legs: lapse → typed `HOLD_EXPIRED` 409 and no appointment; re-acquire the same interval (proves a lapsed hold stopped blocking — issue #97); then confirm at `hold_expires_at − 150 ms` with the sweeper firing at the same instant.

## 3 · `pending_expiry_vs_planner_confirm`

```powershell
$env:SETUHAUL_LOCUST_MUTATE="1"
$env:JOB_AUTH_TOKEN="<from .env.local / SSM>"   # required
uv run --with locust locust -f loadtests/locust_pending_expiry_confirm.py --headless -u 1 -r 1 -t 25m
```

| | |
|---|---|
| Driver / shipment | `amit.singh@setuhaul.com` / `SHP-D16-RACE-B` (FAC-JAI-01) |
| Planner | `rahul.verma@setuhaul.com` — USR102, ROL003 `WAREHOUSE_PLANNER` at FAC-JAI-01 |
| Auditor (read-only) | `admin@setuhaul.com` — set `SETUHAUL_PENDING_AUDIT_CHECK=0` to skip |
| Env | `SETUHAUL_PENDING_SHIPMENT` · `SETUHAUL_PENDING_DRIVER_EMAIL` · `SETUHAUL_PLANNER_EMAIL` · `SETUHAUL_PENDING_FACILITY` · `SETUHAUL_PENDING_RELEASE_MARGIN_S` (5) · `SETUHAUL_PENDING_MAX_WAIT_S` (1200) |
| Runtime | up to ~17 min: it books a request and waits out D9's 15-minute TTL, unless a pending row already exists to adopt |

> ⚠️ **The sweep is global.** `POST /internal/jobs/expiry-sweep` expires **every** `PENDING_CONFIRMATION` row in the database past its D9 deadline and raises a `PENDING_EXPIRED_UNACTIONED` escalation for each — there is no facility or shipment filter. Confirmed 2026-09-02: `SHP-RS-PENDING` (the reschedule sandbox's pending fixture) is currently past its deadline, so this run **will** expire it and the reschedule demo's "reschedule a pending request" case needs re-seeding afterwards (`rollback_reschedule_driver.py --confirm` then `seed_reschedule_driver.py --confirm`). Never run this against a database someone else is demoing on.

Issue #64 guard: the suite refuses any row whose queue `ttl.hold_used` is true — a `hold_for_information` extension makes `appointments.expires_at` the deadline instead of `booked_at + 15 min`, and racing that would be racing a deadline the suite has mis-modelled.

## 4 · `ordinal_staleness`

```powershell
$env:SETUHAUL_LOCUST_MUTATE="1"
uv run --with locust locust -f loadtests/locust_ordinal_staleness.py --headless -u 1 -r 1 -t 90s
```

| | |
|---|---|
| Identity / shipment | `driver.resched@setuhaul.com` / `SHP-RS-OPEN` (sandbox) |
| Re-rank trigger | the driver declares a new ETA on their own shipment, shifted from its *current* ETA by `SETUHAUL_ORDINAL_ETA_SHIFT_MIN` (default 20) |
| Env | `SETUHAUL_ORDINAL_ETA_SHIFT_MIN` · `SETUHAUL_ORDINAL_POSITIVE_CONTROL=0` · `SETUHAUL_ORDINAL_TRIGGER` (only `eta` is wired) |
| Writes | one `eta_updates` row + `shipments.latest_eta_ts` + one `chat_messages` row; plus a 90-second hold if the positive control runs |
| Leaves behind | no appointment. To restore the sandbox ETA exactly, re-seed the sandbox |

The positive control (same slot, *fresh* `recommendation_id` → `SLOT_HELD`) is what stops a refusal-only test from passing while the endpoint is simply broken.

> 🔴 **Expect suite 4 to go red on this build, with `positive_control_blocked_by_sticky_stale_flag`.** Traced 2026-09-02: `clear_recommendation_stale` is called only at `allocation.py:1976`, which sits *after* the `TWO_PHASE_HOLD_ENABLED` early return at `allocation.py:1819` — and that is its only call site in `backend/app`. `_validate_displayed_recommendation` refuses on the Redis stale flag alone, so with the flag on (its default) a driver who declares a new ETA is refused `SLOT_OPTIONS_STALE` on **every** subsequent `request_slot` for that shipment — fresh recommendation id or none at all — until the 24-hour Redis key expires. That is the §9.2 race-4 promise ("rejected and re-presented") failing on the second half. Needs its own tracker issue; the suite names it rather than papering over it.

## Do not

- Spawn 20+ chat users (LLM cost).
- Set `SETUHAUL_LOCUST_MUTATE=1` on Suite A with more than 2 users (Phase C race only).
- Run any mutating race suite against a database in use for a demo, or without the reset step above.
- Run suite 3 in distributed mode: its two actors coordinate through in-process state.
- Treat Suite A HTTP stats as Phase A–G sign-off.
- Commit passwords or tokens.
