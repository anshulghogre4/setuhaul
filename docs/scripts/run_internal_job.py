"""Run one internal job cycle by hand, until the EventBridge schedule (#111) is live.

    python docs/scripts/run_internal_job.py expiry-sweep
    python docs/scripts/run_internal_job.py notification-drain --base http://127.0.0.1:8000

WHY THIS EXISTS
Issue #111: the ECS task definition carried no `JOB_AUTH_TOKEN`, so both internal job routes
answered 503 JOB_AUTH_UNCONFIGURED on production and no scheduler ever called them (the #20
EventBridge leg was never built). Producers wrote `notification_outbox` rows and nothing
drained them; PENDING_CONFIRMATION rows past their TTL were only retired lazily by the
claim/read paths, leaving `PENDING_EXPIRED_UNACTIONED` escalations unproduced. This script is
the owner's manual crank for that gap, and stays useful afterwards for forcing a cycle.

PATH NOTE (verified live 2026-09-02): these routes are mounted at `/internal/jobs/<name>` with
NO `/api/v1` prefix -- `internal.router` carries `prefix="/internal"` and is included without
the versioned prefix the business routers get. Hitting `/api/v1/internal/jobs/...` 404s.

The token is read from the environment or the gitignored `.env.local`, and is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JOBS = ("expiry-sweep", "notification-drain")
DEFAULT_BASE = "https://d382h70qmz3ife.cloudfront.net"
TOKEN_HEADER = "X-SetuHaul-Job-Token"  # must match JOB_TOKEN_HEADER in routers/internal.py


def load_token() -> str:
    """Environment first, then .env.local -- same precedence as the other docs/scripts helpers."""
    token = (os.environ.get("JOB_AUTH_TOKEN") or "").strip()
    if token:
        return token
    for env_name in (".env.local", ".env"):
        path = ROOT / env_name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "JOB_AUTH_TOKEN":
                candidate = value.strip().strip('"').strip("'")
                if candidate:
                    return candidate
    raise SystemExit(
        "JOB_AUTH_TOKEN not found in the environment or .env.local.\n"
        "It must be the same value as SSM /setuhaul/job-auth-token in ap-south-1 -- see the\n"
        "'#111 runbook' section of deploy/README.md."
    )


def post(url: str, token: str, timeout: float) -> tuple[int, dict | str]:
    request = urllib.request.Request(
        url,
        data=b"",  # both routes take no body; an empty one keeps Content-Length honest
        method="POST",
        headers={TOKEN_HEADER: token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return exc.code, raw.decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise SystemExit(f"could not reach {url}: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("job", choices=JOBS, help="which internal job to run once")
    parser.add_argument("--base", default=DEFAULT_BASE, help=f"base URL (default: {DEFAULT_BASE})")
    parser.add_argument("--timeout", type=float, default=60.0, help="client timeout in seconds")
    args = parser.parse_args()

    token = load_token()
    url = f"{args.base.rstrip('/')}/internal/jobs/{args.job}"
    print(f"POST {url}")

    started = time.perf_counter()
    status, body = post(url, token, args.timeout)
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"status {status} in {elapsed_ms:.0f} ms")

    if isinstance(body, str):
        print(body)
        return 1

    # The envelope is app.core.envelope.ok(): success/message/data/timestamp/request_id.
    if status == 200 and body.get("success"):
        if body.get("message"):
            print(body["message"])
        print(json.dumps(body.get("data"), indent=2, sort_keys=True))
        print(f"request_id {body.get('request_id')}")
        return 0

    print(json.dumps(body, indent=2, sort_keys=True))
    codes = {e.get("code") for e in body.get("errors") or []}
    if "JOB_AUTH_UNCONFIGURED" in codes:
        print(
            "\nThis is issue #111's exact failure: the SERVER has no JOB_AUTH_TOKEN.\n"
            "Apply deploy/ecs-task-definition.json (deploy/apply_ecs_task_definition.sh|.ps1).",
            file=sys.stderr,
        )
    elif "JOB_AUTH_INVALID" in codes:
        print(
            "\nThe server is configured but rejected this token: your local JOB_AUTH_TOKEN and\n"
            "SSM /setuhaul/job-auth-token have drifted. Re-sync them (deploy/README.md).",
            file=sys.stderr,
        )
    elif "SWEEPER_ACTOR_UNCONFIGURED" in codes:
        print(
            "\nJOB_ACTOR_USER_ID is unset on the server. The sweeper refuses to write audit rows\n"
            "it cannot attribute (SOLUTION_DESIGN.md 7.5.1). Add it to the task definition.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
