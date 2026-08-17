"""Free stuck/leaked Supabase Supavisor session-mode connections.

DATABASE_URL points at Supavisor's SESSION-mode pooler (port 5432), which caps
the whole project at a small fixed global connection budget (currently 15 —
see backend/app/db/session.py). A leaked connection sitting `idle in
transaction` (or just idle) never gets released back to that budget on its
own, and once enough pile up, every new connection attempt — including the
app itself — starts failing with `EMAXCONNSESSION: max clients reached in
session mode`. Live-reproduced and fixed manually 2026-08-17; this script is
the repeatable version of that fix.

This connects through Supavisor's TRANSACTION-mode pooler (port 6543) — a
separate pool from the saturated session-mode one — so it can still get in
and query/terminate backends even when session mode itself is fully stuck.
It only ever touches `usename='postgres' AND application_name='Supavisor'`
backends (i.e. app connections proxied through the session-mode pooler),
never Supabase's own internal services (pg_cron, pg_net, PostgREST,
postgres_exporter, Supavisor's own auth_query connections), and never its
own current connection.

Usage:
  python docs/scripts/free_stuck_db_connections.py           # dry run (list only)
  python docs/scripts/free_stuck_db_connections.py --confirm  # actually terminate
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def run(confirm: bool) -> int:
    import asyncpg

    pooled = (os.environ.get("DATABASE_URL") or "").strip()
    if not pooled:
        raise SystemExit("DATABASE_URL missing (load .env.local / .env)")
    txn_url = pooled.replace(":5432/", ":6543/")

    conn = await asyncpg.connect(txn_url, statement_cache_size=0, timeout=20)
    try:
        rows = await conn.fetch(
            """
            SELECT pid, state, query, backend_start
            FROM pg_stat_activity
            WHERE datname = current_database()
              AND usename = 'postgres'
              AND application_name = 'Supavisor'
              AND pid <> pg_backend_pid()
            ORDER BY backend_start
            """
        )
        print(f"CANDIDATES={len(rows)}")
        for r in rows:
            print(f"  pid={r['pid']} state={r['state']!r} query={r['query']!r} since={r['backend_start']}")
        if not confirm:
            print("Dry run only (pass --confirm to terminate). No connections touched.")
            return 0

        killed = 0
        for r in rows:
            ok = await conn.fetchval("SELECT pg_terminate_backend($1)", r["pid"])
            if ok:
                killed += 1
        print(f"KILLED={killed}/{len(rows)}")
        return 0
    finally:
        await conn.close()


def main() -> None:
    load_env(ROOT / ".env.local")
    load_env(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--confirm", action="store_true", help="Actually terminate the listed connections")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.confirm)))


if __name__ == "__main__":
    main()
