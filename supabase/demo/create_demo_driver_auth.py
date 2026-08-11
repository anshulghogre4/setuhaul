"""Create Supabase Auth for demo drivers using the existing shared Driver password.

Never resets existing users. Never prints passwords.
Reads Driver password from POC_TEAM_ACCOUNTS.local.md or SETUHAUL_POC_DRIVER_PASSWORD.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]

# DRV004-DRV015 mapped to USR201-USR212 by the demo generator.
DEMO_DRIVERS = [
    ("USR201", "DRV004", "Sandeep Meena", "driver.drv004@setuhaul.com"),
    ("USR202", "DRV005", "Gurpreet Singh", "driver.drv005@setuhaul.com"),
    ("USR203", "DRV006", "Manoj Sharma", "driver.drv006@setuhaul.com"),
    ("USR204", "DRV007", "Nitin Patil", "driver.drv007@setuhaul.com"),
    ("USR205", "DRV008", "Ashok Prajapat", "driver.drv008@setuhaul.com"),
    ("USR206", "DRV009", "Vikram Solanki", "driver.drv009@setuhaul.com"),
    ("USR207", "DRV010", "Deepak Saini", "driver.drv010@setuhaul.com"),
    ("USR208", "DRV011", "Ramesh Choudhary", "driver.drv011@setuhaul.com"),
    ("USR209", "DRV012", "Arjun Das", "driver.drv012@setuhaul.com"),
    ("USR210", "DRV013", "Kailash Gurjar", "driver.drv013@setuhaul.com"),
    ("USR211", "DRV014", "Pradeep Jat", "driver.drv014@setuhaul.com"),
    ("USR212", "DRV015", "Mohammed Salim", "driver.drv015@setuhaul.com"),
]


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def driver_password() -> str:
    env_pw = (os.environ.get("SETUHAUL_POC_DRIVER_PASSWORD") or "").strip()
    if env_pw:
        return env_pw
    roster = ROOT / "POC_TEAM_ACCOUNTS.local.md"
    text = roster.read_text(encoding="utf-8")
    m = re.search(r"\|\s*Driver\s*\|\s*([^|]+)\|", text)
    if not m:
        raise SystemExit("Driver password not found in POC_TEAM_ACCOUNTS.local.md")
    return m.group(1).strip()


def main() -> None:
    load_env(ROOT / ".env.local")
    load_env(ROOT / ".env")
    base = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    service = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    db_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not base or not service or not db_url:
        raise SystemExit("SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, DATABASE_URL required")

    password = driver_password()
    headers = {
        "apikey": service,
        "Authorization": f"Bearer {service}",
        "Content-Type": "application/json",
    }

    import asyncio
    import asyncpg

    async def run() -> None:
        conn = await asyncpg.connect(db_url, statement_cache_size=0)
        created = 0
        mapped = 0
        skipped = 0
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for user_id, driver_id, full_name, email in DEMO_DRIVERS:
                    row = await conn.fetchrow(
                        "select auth_user_id from public.users where user_id=$1",
                        user_id,
                    )
                    if row is None:
                        print(f"MISSING_USER {user_id}")
                        continue
                    if row["auth_user_id"] is not None:
                        skipped += 1
                        print(f"SKIP_ALREADY_MAPPED {user_id}")
                        continue

                    # Look up existing auth user by email first (no password reset).
                    listed = await client.get(
                        f"{base}/auth/v1/admin/users",
                        headers=headers,
                        params={"page": 1, "per_page": 200},
                    )
                    listed.raise_for_status()
                    auth_id = None
                    for u in listed.json().get("users", []):
                        if (u.get("email") or "").lower() == email.lower():
                            auth_id = u.get("id")
                            break

                    if auth_id is None:
                        resp = await client.post(
                            f"{base}/auth/v1/admin/users",
                            headers=headers,
                            json={
                                "email": email,
                                "password": password,
                                "email_confirm": True,
                                "user_metadata": {
                                    "full_name": full_name,
                                    "driver_id": driver_id,
                                    "user_id": user_id,
                                },
                            },
                        )
                        if resp.status_code >= 400:
                            print(f"CREATE_FAIL {user_id} {resp.status_code} {resp.text[:200]}")
                            continue
                        auth_id = resp.json().get("id")
                        created += 1
                        print(f"CREATED_AUTH {user_id} {email}")
                    else:
                        print(f"REUSE_AUTH {user_id} {email}")

                    await conn.execute(
                        "update public.users set auth_user_id=$1::uuid, updated_at=now()::text where user_id=$2",
                        auth_id,
                        user_id,
                    )
                    mapped += 1
                    print(f"MAPPED {user_id} -> {auth_id}")
        finally:
            await conn.close()
        print(f"DONE created={created} mapped={mapped} skipped={skipped}")

    asyncio.run(run())


if __name__ == "__main__":
    main()
