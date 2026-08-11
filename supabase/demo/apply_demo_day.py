"""Apply supabase/demo/out/demo_day_*.sql using DATABASE_URL from .env.local."""

from __future__ import annotations

import asyncio
import os
import sys
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
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


async def apply(sql_path: Path) -> None:
    import asyncpg

    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise SystemExit("DATABASE_URL missing")
    sql = sql_path.read_text(encoding="utf-8")
    print(f"Applying {sql_path.name} ({len(sql)} chars)...")
    conn = await asyncpg.connect(url, statement_cache_size=0, timeout=180)
    try:
        await conn.execute(sql)
        print("APPLY_OK")
    finally:
        await conn.close()


def main() -> None:
    load_env(ROOT / ".env.local")
    load_env(ROOT / ".env")
    day = sys.argv[1] if len(sys.argv) > 1 else "2026-08-16"
    sql_path = ROOT / "supabase" / "demo" / "out" / f"demo_day_{day}.sql"
    if not sql_path.exists():
        raise SystemExit(f"Missing {sql_path}")
    asyncio.run(apply(sql_path))


if __name__ == "__main__":
    main()
