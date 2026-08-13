"""Shared Locust helpers. Never prints passwords, tokens, or SSM values."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BFF = "https://se-e5cad5d30b1a4f22b9aeea032827f81b.ecs.us-east-1.on.aws"
DEFAULT_ORIGIN = "https://setuhaul-roan.vercel.app"

# Verbatim from docs/DEMO_MANUAL_RUNBOOK.md — keep in sync (unit-tested).
RUNBOOK_PROMPTS = {
    "A2": "Show my current shipments.",
    "A3": "I will be late on SHP-D16-RAVI.",
    "A4": "Repair will take 90 minutes.",
    "A5": "My new ETA for SHP-D16-RAVI is 2026-08-16T18:45:00+05:30 due to traffic.",
    "B1": "I need help with shipment SHP-D16-RAVI.",
    "B2": "Show feasible slots after 6 PM.",
    "B5": "Has the warehouse confirmed my new slot?",
    "C1": "I need help with shipment SHP-D16-RACE-A.",
    "C2": "I need help with shipment SHP-D16-RACE-B.",
    "C3": "Show feasible slots after 6 PM.",
    "C4": "Show feasible slots after 6 PM.",
    "C5A": "Request slot D16-SLT-RACE for SHP-D16-RACE-A.",
    "C5B": "Request slot D16-SLT-RACE for SHP-D16-RACE-B.",
    "D1": "What are my active shipments?",
    "D2": "Find feasible slots for SHP-D16-NOSLOT.",
    "D3": "Escalate this no-slot case for SHP-D16-NOSLOT.",
    "D4": "Find slots for SHP-D16-MULTI-B.",
    "E1": "I need help with shipment SHP-D16-RAVI.",
    "E2": "Show feasible slots after 6 PM.",
    "E5": "Cancel my pending appointment request for SHP-D16-RAVI because plans changed.",
    "G2": "I need help with shipment SHP-D16-CONTEND-01.",
}

CONTEND_CAST = tuple(
    (f"driver.drv{index:03d}@setuhaul.com", f"SHP-D16-CONTEND-{n:02d}")
    for n, index in enumerate(range(4, 14), start=1)
)
RACE_SLOT_ID = "D16-SLT-RACE"


def bff_host() -> str:
    return (
        os.environ.get("SETUHAUL_BFF_URL")
        or os.environ.get("LOCUST_HOST")
        or DEFAULT_BFF
    ).rstrip("/")


def load_env_vals() -> dict[str, str]:
    vals: dict[str, str] = {}
    for name in (".env.local", ".env", "frontend/.env.local"):
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            vals[key.strip()] = value.strip().strip('"').strip("'")
    return vals


def load_driver_password() -> str:
    override = (os.environ.get("SETUHAUL_DRIVER_PASSWORD") or "").strip()
    if override:
        return override
    text = (ROOT / "POC_TEAM_ACCOUNTS.local.md").read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        if line.startswith("| Driver |") and "All DRIVER" in line:
            return line.split("|")[2].strip()
    raise RuntimeError("driver_password_missing")


def supabase_grant(email: str) -> str:
    vals = load_env_vals()
    url = (vals.get("VITE_SUPABASE_URL") or vals.get("SUPABASE_URL") or "").rstrip("/")
    anon = vals.get("VITE_SUPABASE_ANON_KEY") or vals.get("SUPABASE_ANON_KEY") or ""
    if not url or not anon:
        raise RuntimeError("supabase_vite_keys_missing")
    password = load_driver_password()
    request = urllib.request.Request(
        f"{url}/auth/v1/token?grant_type=password",
        data=json.dumps({"email": email, "password": password}).encode(),
        method="POST",
        headers={"apikey": anon, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"grant_failed_{exc.code}") from exc
    token = body.get("access_token")
    if not token:
        raise RuntimeError("grant_missing_access_token")
    return token


def auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Origin": os.environ.get("SETUHAUL_ORIGIN") or DEFAULT_ORIGIN,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def mutate_enabled() -> bool:
    return (os.environ.get("SETUHAUL_LOCUST_MUTATE") or "").strip() in {"1", "true", "yes"}
