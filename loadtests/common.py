"""Shared Locust helpers. Never prints passwords, tokens, or SSM values."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Issue #42's own sub-item: "Update `loadtests/common.py`'s default host once E7.1 lands, so these
# suites don't silently point at the pre-migration region."
#
# The retired default was `https://se-e5cad5d30b1a4f22b9aeea032827f81b.ecs.us-east-1.on.aws` -- the
# pre-migration `us-east-1` Express BFF. The live edge is the CloudFront distribution in front of
# the `ap-south-1` ALB (`E3B1GUEQF3U9U4` / `d382h70qmz3ife.cloudfront.net`, CHANGELOG 2026-08-30):
# `CachingDisabled` + `AllViewerExceptHostHeader`, so every method and the `Authorization` header
# pass through untouched, which is what makes it usable as a load-test target at all. The same
# origin serves `/api/v1/**` and `/internal/**`, because it fronts the FastAPI service directly --
# the frontend bundle was verified byte-exact against this URL on 2026-08-30.
DEFAULT_BFF = "https://d382h70qmz3ife.cloudfront.net"
# The local stack, for wiring checks that must not touch the hosted environment. Pass it with
# `-H http://127.0.0.1:8000` or `SETUHAUL_BFF_URL=http://127.0.0.1:8000`; `bff_host()` prefers both
# over the default.
LOCAL_BFF = "http://127.0.0.1:8000"
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

# ---------------------------------------------------------------------------
# Fixtures the four §9.2 race suites target, named here so the coordinator's mutating run needs
# zero improvisation and so two suites cannot silently pick the same row.
# ---------------------------------------------------------------------------
# `D16-SLT-RACE` is DOCK-JAI-D1 19:00-19:30 on the demo day, one of exactly four open evening slots
# at FAC-JAI-01 (`supabase/demo/generate_demo_day.py`: `race_window` + `open_evening_ids`). The
# other three are what makes `same_interval_race`'s "49 refusals **with fresh options**" assertion
# non-vacuous.
RACE_FACILITY_ID = "FAC-JAI-01"
RACE_DOCK_ID = "DOCK-JAI-D1"

# The isolated reschedule sandbox (`supabase/demo/seed_reschedule_driver.py`): driver DRV-RS-01 at
# FAC-GGN-01, outside the `D16-%` / `SHP-D16-%` namespace, which `reset_demo_day.py` never touches
# in either mode. Preferred over the cast wherever a scenario can self-provision, because a suite
# that runs here cannot disturb `docs/DEMO_MANUAL_RUNBOOK.md` Phases A-G.
SANDBOX_DRIVER_EMAIL = "driver.resched@setuhaul.com"
SANDBOX_OPEN_SHIPMENT = "SHP-RS-OPEN"  # no appointment, has feasible options
SANDBOX_FACILITY_ID = "FAC-GGN-01"

# `pending_expiry_vs_planner_confirm` needs a *planner*, and every seeded OPS_PORTAL role sits at
# FAC-JAI-01 (`supabase/seed.sql`: USR101-USR104). USR102 Rahul Verma is ROL003 WAREHOUSE_PLANNER
# there, so that scenario runs on the JAI cast rather than the GGN sandbox -- see the README for
# the sandbox variant and why it needs an ADMIN identity instead (`_assert_ops_scope` demands
# `is_admin` for the global tier; TRANSPORT_MANAGER / REGIONAL_OPERATIONS_HEAD are read-only).
PLANNER_EMAIL = "rahul.verma@setuhaul.com"
ADMIN_EMAIL = "admin@setuhaul.com"
PENDING_RACE_DRIVER_EMAIL = "amit.singh@setuhaul.com"
PENDING_RACE_SHIPMENT = "SHP-D16-RACE-B"

JOB_TOKEN_HEADER = "X-SetuHaul-Job-Token"


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


def load_bucket_password(bucket: str) -> str:
    """One of the three shared role-bucket passwords from the gitignored accounts file.

    `POC_TEAM_ACCOUNTS.local.md` opens with a three-row table (`| Driver |`, `| Operations |`,
    `| Admin |`); the password is the second cell. Generalised from `load_driver_password` because
    `pending_expiry_vs_planner_confirm` needs the Operations bucket for the planner half of the
    race, and a second copy of this parsing would be a second thing to keep in sync with the file's
    layout. Env overrides (`SETUHAUL_DRIVER_PASSWORD` / `SETUHAUL_OPERATIONS_PASSWORD` /
    `SETUHAUL_ADMIN_PASSWORD`) exist so a run can avoid the file entirely.

    Never logged, never returned in any suite's printed summary.
    """
    override = (os.environ.get(f"SETUHAUL_{bucket.upper()}_PASSWORD") or "").strip()
    if override:
        return override
    path = ROOT / "POC_TEAM_ACCOUNTS.local.md"
    if not path.exists():
        raise RuntimeError(f"{bucket.lower()}_password_missing_no_accounts_file")
    text = path.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        if line.startswith(f"| {bucket} |"):
            value = line.split("|")[2].strip()
            if value:
                return value
    raise RuntimeError(f"{bucket.lower()}_password_missing")


def load_driver_password() -> str:
    return load_bucket_password("Driver")


# Which bucket each seeded identity belongs to. Anything not listed is a driver -- the demo cast is
# overwhelmingly drivers, and an unknown ops email should fail loudly at grant time rather than be
# silently tried with the wrong password.
_OPERATIONS_EMAILS = frozenset(
    {
        "priya.mehta@setuhaul.com",
        "kavita.rao@setuhaul.com",
        "arvind.nair@setuhaul.com",
        "rahul.verma@setuhaul.com",
        "anjali.kapoor@setuhaul.com",
        "deepak.joshi@setuhaul.com",
    }
)
_ADMIN_EMAILS = frozenset(
    {
        "admin@setuhaul.com",
        "meera.iyer@setuhaul.com",
        "suresh.menon@setuhaul.com",
        "sanjay.gupta@setuhaul.com",
        "neha.bansal@setuhaul.com",
    }
)


def bucket_for(email: str) -> str:
    normalised = email.strip().lower()
    if normalised in _OPERATIONS_EMAILS:
        return "Operations"
    if normalised in _ADMIN_EMAILS:
        return "Admin"
    return "Driver"


# One token per identity per process, not one per virtual user.
#
# This is a correctness requirement at `same_interval_race`'s 50-way target, not an optimisation:
# Supabase's `/auth/v1/token` is rate limited to **1800 requests per hour with bursts up to 30**,
# by IP address, and that limit is explicitly *not* customizable (Supabase Auth, "Rate limits" --
# fetched 2026-09-02). Fifty virtual users each grabbing their own grant inside the spawn window
# would exceed the burst allowance and start the race with 429s instead of contention. Fifty users
# over the ten-strong contention cast collapse to ten grants here.
_TOKEN_CACHE: dict[str, str] = {}
_TOKEN_LOCK = threading.Lock()


def supabase_grant(email: str, *, refresh: bool = False) -> str:
    """A Supabase access token for `email`, cached per process. Never printed."""
    key = email.strip().lower()
    if not refresh:
        with _TOKEN_LOCK:
            cached = _TOKEN_CACHE.get(key)
        if cached:
            return cached
    token = _supabase_grant_uncached(email)
    with _TOKEN_LOCK:
        _TOKEN_CACHE[key] = token
    return token


def _supabase_grant_uncached(email: str) -> str:
    vals = load_env_vals()
    url = (vals.get("VITE_SUPABASE_URL") or vals.get("SUPABASE_URL") or "").rstrip("/")
    anon = vals.get("VITE_SUPABASE_ANON_KEY") or vals.get("SUPABASE_ANON_KEY") or ""
    if not url or not anon:
        raise RuntimeError("supabase_vite_keys_missing")
    password = load_bucket_password(bucket_for(email))
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


def env_flag(name: str, *, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes"}


def env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def idem_key(prefix: str) -> str:
    """A fresh Idempotency-Key. Fresh per attempt on purpose.

    Every mutating route on `routers/scheduling.py` 400s without this header
    (`IDEMPOTENCY_KEY_REQUIRED`), and a *reused* key would replay the stored response instead of
    re-entering the race -- `allocation.request_slot`'s replay branch returns the recorded outcome
    without touching the exclusion constraint. A race suite that reused keys would measure the
    idempotency store, not PostgreSQL.
    """
    return f"locust-{prefix}-{uuid.uuid4()}"


# ---------------------------------------------------------------------------
# Response-envelope readers (`app/core/envelope.py`)
# ---------------------------------------------------------------------------
# Success: {"success": true, "data": {...}, ...} -- the typed outcome's own `code` lives on `data`.
# Failure: {"success": false, "errors": [{"code": ..., "detail": ..., "field": ...}], ...}.
# `routers/scheduling.py` also emits a *third* shape for typed conflicts: an `ok()` envelope with
# `success` flipped to false and an `errors` list added, so `data.code` and `errors[0].code` are
# both present and agree. Reading `data.code` first is therefore right for every shape, and the
# `errors` fallback covers `AppError` responses (ALREADY_ACTIONED, HOLD_EXPIRED via a raise, 403,
# 422) that carry no `data` at all.


def envelope_data(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def envelope_code(payload: Any) -> str:
    data = envelope_data(payload)
    code = data.get("code")
    if code:
        return str(code)
    if isinstance(payload, dict):
        errors = payload.get("errors") or []
        if errors and isinstance(errors[0], dict) and errors[0].get("code"):
            return str(errors[0]["code"])
    return ""


def envelope_detail(payload: Any) -> str:
    if isinstance(payload, dict):
        errors = payload.get("errors") or []
        if errors and isinstance(errors[0], dict):
            return str(errors[0].get("detail") or "")
        message = payload.get("message")
        if message:
            return str(message)
    return ""


# ---------------------------------------------------------------------------
# The wall-clock release barrier
# ---------------------------------------------------------------------------
# `TESTING_STRATEGY.md` §11 risk #2 states the problem this solves in its own words: *"Ramping 50
# VUs is not the same as 50 requests landing together; the suite needs an explicit barrier/sync
# mechanism or it tests something weaker than it claims."*
#
# The barrier is an absolute wall-clock instant rather than a `threading.Barrier`, for two reasons.
# First, it does not depend on knowing how many users actually armed -- a user whose token grant or
# feasibility read failed simply never fires, and the other 49 still land together, where a counting
# barrier would deadlock until its timeout. Second, it is the only shape that also works if the run
# is ever split across worker processes, since those share no Python objects.
#
# `time.sleep` is cooperative here: importing `locust` runs `gevent.monkey.patch_all()`
# (`locust/__init__.py`, verified against the installed 2.46.3), so a sleeping user greenlet yields
# the hub instead of blocking it.


class ReleaseBarrier:
    """A shared "everyone fires at this instant" gate."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._release_at: float | None = None

    def arm(self, seconds_from_now: float) -> float:
        """Set the release instant once; later callers get the instant already chosen."""
        with self._lock:
            if self._release_at is None:
                self._release_at = time.time() + seconds_from_now
            return self._release_at

    def reset(self) -> None:
        with self._lock:
            self._release_at = None

    @property
    def release_at(self) -> float | None:
        with self._lock:
            return self._release_at

    def wait(self, *, poll: float = 0.05) -> float:
        """Block until the release instant. Returns the lateness in seconds (>= 0)."""
        target = self.release_at
        if target is None:
            return 0.0
        while True:
            remaining = target - time.time()
            if remaining <= 0:
                return -remaining
            time.sleep(min(poll, remaining))


def wait_until(target_epoch: float, *, poll: float = 0.05) -> float:
    """Sleep until an absolute epoch instant; returns lateness in seconds."""
    while True:
        remaining = target_epoch - time.time()
        if remaining <= 0:
            return -remaining
        time.sleep(min(poll, remaining))


def parse_iso_epoch(value: Any) -> float | None:
    """ISO-8601 (as every SetuHaul timestamp field is returned) -> epoch seconds."""
    if not value:
        return None
    raw = str(value).strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.timestamp()


# ---------------------------------------------------------------------------
# The internal job endpoint (`/internal/jobs/expiry-sweep`)
# ---------------------------------------------------------------------------


def job_token() -> str:
    """The shared secret `routers/internal.require_job_token` compares, or "" if unavailable.

    Env first, then `JOB_AUTH_TOKEN` out of the root `.env.local` / `.env` the rest of this module
    already reads. Empty means the sweeper leg of a scenario must be skipped **with a stated
    reason**, never quietly dropped: the endpoint fails closed on the server side too (503
    `JOB_AUTH_UNCONFIGURED` when the service itself has no token configured), so a silent skip and a
    real misconfiguration would look identical in the output.
    """
    from_env = (os.environ.get("JOB_AUTH_TOKEN") or "").strip()
    if from_env:
        return from_env
    return (load_env_vals().get("JOB_AUTH_TOKEN") or "").strip()


def job_headers(token: str) -> dict[str, str]:
    return {
        JOB_TOKEN_HEADER: token,
        "Origin": os.environ.get("SETUHAUL_ORIGIN") or DEFAULT_ORIGIN,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def post_json(
    url: str, *, headers: dict[str, str], payload: dict[str, Any] | None = None, timeout: int = 30
) -> tuple[int, dict[str, Any]]:
    """A minimal POST that is *not* recorded in Locust's request statistics.

    Used only for `/internal/jobs/expiry-sweep`. That call is a scheduled machine caller standing in
    for EventBridge, not a user-facing request, and folding its latency into the same percentiles as
    a driver's confirm would make the SLO numbers in `TESTING_STRATEGY.md` §3c mean two different
    things at once. Its outcome is asserted and printed by the suite instead.

    `urllib` rather than `requests` because it is already imported here for the Supabase grant, and
    because gevent's monkey patch makes it cooperative either way.
    """
    body = json.dumps(payload or {}).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except Exception:  # noqa: BLE001
            return exc.code, {}
    except Exception as exc:  # noqa: BLE001
        return 0, {"errors": [{"code": "TRANSPORT_ERROR", "detail": str(exc)[:200]}]}
