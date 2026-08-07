#!/usr/bin/env python3
"""Create three POC Supabase Auth users and map auth_user_id on public.users.

Requires env:
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
  SETUHAUL_POC_DRIVER_PASSWORD
  SETUHAUL_POC_OPERATOR_PASSWORD
  SETUHAUL_POC_ADMIN_PASSWORD

Never commit passwords or the service-role key. Run locally only.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx


def _load_dotenv_local() -> None:
    """Load gitignored `.env.local` from repo root if present (does not override existing env)."""
    root = Path(__file__).resolve().parents[2]
    path = root / ".env.local"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


POC_USERS = [
    {
        "email": "ravi.kumar@setuhaul.com",
        "user_id": "USR001",
        "password_env": "SETUHAUL_POC_DRIVER_PASSWORD",
        "app_metadata": {"portal": "driver", "seed_user_id": "USR001"},
    },
    {
        "email": "priya.mehta@setuhaul.com",
        "user_id": "USR101",
        "password_env": "SETUHAUL_POC_OPERATOR_PASSWORD",
        "app_metadata": {"portal": "operator", "seed_user_id": "USR101"},
    },
    {
        "email": "admin@setuhaul.com",
        "user_id": "USR999",
        "password_env": "SETUHAUL_POC_ADMIN_PASSWORD",
        "app_metadata": {"portal": "admin", "seed_user_id": "USR999"},
    },
]


def main() -> int:
    _load_dotenv_local()
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not service_key:
        print(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required "
            "(set in environment or gitignored .env.local).",
            file=sys.stderr,
        )
        return 1

    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=30.0) as client:
        for spec in POC_USERS:
            password = os.environ.get(spec["password_env"], "")
            if not password:
                print(f"Missing {spec['password_env']}", file=sys.stderr)
                return 1

            # Look up existing auth user by email
            listed = client.get(
                f"{base}/auth/v1/admin/users",
                headers=headers,
                params={"page": 1, "per_page": 200},
            )
            listed.raise_for_status()
            users = listed.json().get("users", [])
            existing = next((u for u in users if u.get("email") == spec["email"]), None)

            if existing:
                auth_id = existing["id"]
                print(f"Auth user exists for {spec['email']} -> {auth_id}")
            else:
                created = client.post(
                    f"{base}/auth/v1/admin/users",
                    headers=headers,
                    json={
                        "email": spec["email"],
                        "password": password,
                        "email_confirm": True,
                        "app_metadata": spec["app_metadata"],
                    },
                )
                if created.status_code >= 400:
                    print(created.text, file=sys.stderr)
                    created.raise_for_status()
                auth_id = created.json()["id"]
                print(f"Created Auth user for {spec['email']} -> {auth_id}")

            # Map via PostgREST (service role bypasses RLS)
            mapped = client.patch(
                f"{base}/rest/v1/users",
                headers={
                    **headers,
                    "Prefer": "return=representation",
                },
                params={"user_id": f"eq.{spec['user_id']}"},
                json={"auth_user_id": auth_id},
            )
            if mapped.status_code >= 400:
                print(mapped.text, file=sys.stderr)
                mapped.raise_for_status()
            print(f"Mapped {spec['user_id']} auth_user_id={auth_id}")

    print("Done. Passwords were not printed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
