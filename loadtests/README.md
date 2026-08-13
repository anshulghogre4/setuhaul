# SetuHaul Locust (runbook-aligned)

Maps [`docs/DEMO_MANUAL_RUNBOOK.md`](../docs/DEMO_MANUAL_RUNBOOK.md) to two files. Locust runs on the **laptop** and hits the hosted BFF. Passwords come from gitignored `POC_TEAM_ACCOUNTS.local.md`.

| File | Runbook | LLM? |
|---|---|---|
| `locust_runbook_chat.py` | Phases A–D exact prompts; E5/C5 writes only if `SETUHAUL_LOCUST_MUTATE=1` | Yes |
| `locust_slot_contention.py` | Phase G / PDF 10 Drivers on `SHP-D16-CONTEND-01..10` | No (REST) |

Phase F (Ops UI) is not Locust. Reset the cast before a mutating run:

```powershell
python supabase/demo/reset_demo_day.py --mode cast --include-shp1017 --confirm
```

Run every command from the **repo root**. Needs `POC_TEAM_ACCOUNTS.local.md` + `.env.local` (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`). Default host is the Express BFF (`https://se-e5cad5d30b1a4f22b9aeea032827f81b.ecs.us-east-1.on.aws`). Override with `-H` or `SETUHAUL_BFF_URL`.

## Suite A — short chat (keep small)

Web UI (open http://127.0.0.1:8089, Start with 5 users / 1 per second):

```powershell
uv run --with locust locust -f loadtests/locust_runbook_chat.py --web-host 127.0.0.1 --web-port 8089
```

Headless:

```powershell
uv run --with locust locust -f loadtests/locust_runbook_chat.py --headless -u 5 -r 1 -t 3m
```

## Suite B — scarce slots, zero double-books

```powershell
uv run --with locust locust -f loadtests/locust_slot_contention.py --headless -u 10 -r 10 -t 90s
```

Uses GET feasible (never invents a `slot_id`), then POST request. 409 conflict is a **pass**. Two `SLOT_REQUESTED` on one slot → exit 1.

## Pass / fail vs the runbook

Locust **200** means the hosted BFF answered. It does **not** tick Phase A–G in `docs/DEMO_MANUAL_RUNBOOK.md` (those need the reply text / one active claim). Suite A fail = `http_5xx` or `success_false` (2026-08-14: one C2 503). Suite B fail = `FAIL_double_book`.

## Do not

- Spawn 20+ chat users (LLM cost).
- Set `SETUHAUL_LOCUST_MUTATE=1` with more than 2 users (Phase C race only).
- Treat Suite A HTTP stats as Phase A–G sign-off.
- Commit passwords or tokens.
