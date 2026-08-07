"""Scripted Sprint 2 team demo path (no secrets printed).

Usage (from repo root, with servers running and .env loaded):
  python docs/scripts/sprint2_demo_path.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]
for env_name in (".env", ".env.local"):
    path = ROOT / env_name
    if not path.exists():
        continue
    # utf-8-sig strips a BOM that PowerShell Set-Content may introduce
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

API = os.environ.get("VITE_API_BASE_URL", "http://127.0.0.1:8000")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
ANON = os.environ.get("SUPABASE_ANON_KEY", "")


async def password_token(email: str, password: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        res = await client.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={"apikey": ANON, "Content-Type": "application/json"},
            json={"email": email, "password": password},
        )
        res.raise_for_status()
        # Allow local clock skew vs Supabase iat before first API call
        await asyncio.sleep(1.5)
        return res.json()["access_token"]


async def main() -> int:
    driver_email = os.environ["SETUHAUL_POC_DRIVER_EMAIL"]
    driver_password = os.environ["SETUHAUL_POC_DRIVER_PASSWORD"]
    ops_email = os.environ["SETUHAUL_POC_OPERATOR_EMAIL"]
    ops_password = os.environ["SETUHAUL_POC_OPERATOR_PASSWORD"]

    print("1) Driver token")
    driver_token = await password_token(driver_email, driver_password)
    headers = {"Authorization": f"Bearer {driver_token}", "Accept": "application/json"}

    async with httpx.AsyncClient(base_url=API, timeout=90) as client:
        print("2) Driver context")
        ctx = (await client.get("/api/v1/driver/context", headers=headers)).json()
        assert ctx["success"], ctx
        shipment_id = ctx["data"]["primary_shipment"]["shipment_id"]
        print(f"   primary={shipment_id}")

        print("3) Chat observational")
        chat = (
            await client.post(
                "/api/v1/chat",
                headers=headers,
                json={
                    "message": "What is my current shipment and appointment?",
                    "client_message_id": str(uuid4()),
                },
            )
        ).json()
        assert chat["success"], chat
        tools = [t["name"] for t in chat["data"].get("tool_calls") or []]
        print(f"   tools={tools} ux={chat['data'].get('ux_state')}")
        thread_id = chat["data"]["thread_id"]

        print("4) Repair-duration clarification (via REST confirmation gate)")
        eta_ts = "2026-08-07T21:45:00+05:30"
        preview = (
            await client.post(
                f"/api/v1/shipments/{shipment_id}/eta-updates",
                headers={**headers, "Idempotency-Key": str(uuid4())},
                json={
                    "declared_eta_ts": eta_ts,
                    "repair_duration_min": 40,
                    "confirmed": False,
                },
            )
        ).json()
        assert preview["data"]["status"] == "CONFIRMATION_REQUIRED", preview
        print(f"   display={preview['data'].get('display_eta')}")

        print("5) Confirmed atomic ETA write")
        key = str(uuid4())
        written_res = await client.post(
                f"/api/v1/shipments/{shipment_id}/eta-updates",
                headers={**headers, "Idempotency-Key": key},
                json={
                    "declared_eta_ts": eta_ts,
                    "confirmation_eta_ts": eta_ts,
                    "confirmed": True,
                    "confidence_code": "HIGH",
                    "delay_reason_code": "TRAFFIC",
                    "repair_duration_min": 40,
                    "exception_type": "DELAY",
                    "note": "sprint2 demo",
                    "thread_id": thread_id,
                    "client_message_id": key,
                },
            )
        written = written_res.json()
        if not written.get("success"):
            print("   write_failed", written_res.status_code, written)
            raise SystemExit(1)
        assert written["data"]["status"] == "PERSISTED", written
        print(f"   persisted display={written['data'].get('display_eta')}")

        print("6) Duplicate idempotency replay")
        replay_res = await client.post(
            f"/api/v1/shipments/{shipment_id}/eta-updates",
            headers={**headers, "Idempotency-Key": key},
            json={
                "declared_eta_ts": eta_ts,
                "confirmation_eta_ts": eta_ts,
                "confirmed": True,
                "confidence_code": "HIGH",
                "delay_reason_code": "TRAFFIC",
                "repair_duration_min": 40,
                "exception_type": "DELAY",
                "note": "sprint2 demo",
                "thread_id": thread_id,
                "client_message_id": key,
            },
        )
        replay = replay_res.json()
        assert replay.get("success") and replay["data"].get("idempotent_replay") is True, replay
        print("   replay ok")

        print("7) Scheduling capability denied via chat")
        denied = (
            await client.post(
                "/api/v1/chat",
                headers=headers,
                json={
                    "message": "Book me an earlier dock slot for tomorrow morning.",
                    "thread_id": thread_id,
                    "client_message_id": str(uuid4()),
                },
            )
        ).json()
        assert denied["success"], denied
        print(f"   ux={denied['data'].get('ux_state')} tools={[t['name'] for t in denied['data'].get('tool_calls') or []]}")

        print("8) Ops refresh")
        ops_token = await password_token(ops_email, ops_password)
        ops_headers = {"Authorization": f"Bearer {ops_token}", "Accept": "application/json"}
        exc = (await client.get("/api/v1/operations/exceptions", headers=ops_headers)).json()
        assert exc["success"], exc
        match = [i for i in exc["data"]["items"] if i.get("shipment_id") == shipment_id]
        print(f"   matching_exceptions={len(match)} open_sample_eta={match[0].get('declared_eta_ts') if match else None}")

    print("DEMO_PATH_PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyError as exc:
        print(f"Missing env: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
