"""Step 9 hosted smoke: Ravi JWT + BFF chat after ARN is set. Never prints secrets."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BFF = "https://se-e5cad5d30b1a4f22b9aeea032827f81b.ecs.us-east-1.on.aws"
ORIGIN = "https://setuhaul-roan.vercel.app"
EMAIL = "ravi.kumar@setuhaul.com"
SESSION = "step9-hosted-smoke-0000000000001"


def load_driver_password() -> str:
    text = (ROOT / "POC_TEAM_ACCOUNTS.local.md").read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        if line.startswith("| Driver |") and "All DRIVER" in line:
            return line.split("|")[2].strip()
    raise SystemExit("driver_password_missing")


def load_supabase() -> tuple[str, str]:
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
    url = vals.get("VITE_SUPABASE_URL") or vals.get("SUPABASE_URL")
    anon = vals.get("VITE_SUPABASE_ANON_KEY") or vals.get("SUPABASE_ANON_KEY")
    if not url or not anon:
        raise SystemExit("supabase_vite_keys_missing")
    return url.rstrip("/"), anon


def req(url: str, *, method: str = "GET", headers: dict[str, str] | None = None, data: bytes | None = None):
    request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = response.read()
            return response.status, dict(response.headers), body
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def main() -> int:
    password = load_driver_password()
    supabase, anon = load_supabase()
    grant_status, _, grant_body = req(
        f"{supabase}/auth/v1/token?grant_type=password",
        method="POST",
        headers={"apikey": anon, "Content-Type": "application/json"},
        data=json.dumps({"email": EMAIL, "password": password}).encode(),
    )
    print("ravi_grant", grant_status)
    if grant_status != 200:
        return 1
    token = json.loads(grant_body)["access_token"]
    me_status, _, me_body = req(
        f"{BFF}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}", "Origin": ORIGIN, "Accept": "application/json"},
    )
    me = json.loads(me_body)
    data = me.get("data") or {}
    print("auth_me", me_status, data.get("user_id"), data.get("role_name"), data.get("driver_id"))
    chat_status, _, chat_body = req(
        f"{BFF}/api/v1/chat/message",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Origin": ORIGIN,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps(
            {
                "message": "Step 9 hosted smoke: do I have a current appointment?",
                "session_id": SESSION,
                "thread_id": "default",
            }
        ).encode(),
    )
    try:
        chat = json.loads(chat_body)
    except json.JSONDecodeError:
        print("chat_raw", chat_status, chat_body[:200])
        return 1
    payload = chat.get("data") or {}
    tools = []
    if isinstance(payload, dict):
        tools = payload.get("tools_used") or payload.get("tool_calls") or []
    names = []
    for item in tools:
        if isinstance(item, dict):
            names.append(item.get("name") or item.get("tool"))
        else:
            names.append(str(item))
    print(
        "chat",
        chat_status,
        "success",
        chat.get("success"),
        "code",
        chat.get("error", {}).get("code") if isinstance(chat.get("error"), dict) else chat.get("code"),
        "ux",
        payload.get("ux") if isinstance(payload, dict) else None,
        "tools",
        names,
    )
    return 0 if me_status == 200 and chat_status == 200 and chat.get("success") else 1


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    raise SystemExit(main())
