"""Put Sprint 4 /setuhaul/* SecureString parameters from gitignored env files.

Never prints secret values. Run from repo root after `aws login` / `aws configure`.

  python docs/scripts/put_hosting_ssm.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]

MAP = (
    ("GOOGLE_API_KEY", "/setuhaul/google-api-key"),
    ("OPENAI_API_KEY", "/setuhaul/openai-api-key"),
    ("UPSTASH_REDIS_REST_URL", "/setuhaul/upstash-redis-rest-url"),
    ("UPSTASH_REDIS_REST_TOKEN", "/setuhaul/upstash-redis-rest-token"),
    ("LANGSMITH_API_KEY", "/setuhaul/langsmith-api-key"),
    # #46: shipped dark until the owner provisions a Sentry project; the row exists so a
    # rotation through this script does not silently drop the DSN once it is set.
    ("SENTRY_DSN", "/setuhaul/sentry-dsn"),
    ("SUPABASE_URL", "/setuhaul/supabase-url"),
    ("SUPABASE_URL", "/setuhaul/supabase-jwks-issuer-base"),
)


def load_env() -> None:
    for env_name in (".env", ".env.local"):
        path = ROOT / env_name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            val = value.strip().strip('"').strip("'")
            if not val:
                continue
            os.environ[key.strip()] = val


def database_url_kind(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if "pooler.supabase.com" in host and port == 6543:
        return "pooler_6543"
    if host.startswith("db.") and host.endswith(".supabase.co") and port in (5432, None):
        return "direct_5432"
    if "pooler.supabase.com" in host:
        return "pooler_other"
    return "other"


# The runtime resolves its hydration region to ap-south-1 on every code path (issue #92's
# verification); us-east-1 is written too, purely as the recorded rollback target until
# issue #45's decommission ruling retires it. A rotation must reach the region that is READ.
PUT_REGIONS = ("ap-south-1", "us-east-1")


def put(name: str, value: str, region: str = "ap-south-1") -> str:
    completed = subprocess.run(
        [
            "aws",
            "ssm",
            "put-parameter",
            "--name",
            name,
            "--type",
            "SecureString",
            "--value",
            value,
            "--overwrite",
            "--region",
            region,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode == 0:
        return "ok"
    err = (completed.stderr or completed.stdout or "aws_error").strip().splitlines()
    last = err[-1] if err else "aws_error"
    if "ExpiredToken" in last or "expired" in last.lower():
        return "fail:expired_session"
    return f"fail:{last[:80]}"


def main() -> int:
    load_env()
    results: list[tuple[str, str]] = []

    for env_key, name in MAP:
        value = (os.environ.get(env_key) or "").strip()
        if not value:
            results.append((name, f"skip:empty:{env_key}"))
            continue
        for region in PUT_REGIONS:
            results.append((f"{name}@{region}", put(name, value, region)))

    db = (os.environ.get("DATABASE_URL") or "").strip()
    db_name = "/setuhaul/database-url"
    if not db:
        results.append((db_name, "skip:empty:DATABASE_URL"))
    else:
        kind = database_url_kind(db)
        if kind == "direct_5432":
            results.append((db_name, "skip:direct_5432_use_pooler"))
        else:
            for region in PUT_REGIONS:
                results.append((f"{db_name}@{region}", f"{put(db_name, db, region)}:{kind}"))

    for name, status in results:
        print(f"{name} {status}")
    return 0 if all(status.startswith("ok") or status.startswith("skip") for _, status in results) else 1


if __name__ == "__main__":
    sys.exit(main())
