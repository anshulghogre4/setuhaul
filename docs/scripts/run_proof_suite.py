#!/usr/bin/env python
"""Stand up a throwaway PostgreSQL cluster, replay this repo's own migration chain into it,
run `SOLUTION_DESIGN.md` section 10's six-part proof suite against it, then destroy it.

Design citation: `SOLUTION_DESIGN.md` section 10 ("Verification -- proving the system does not
double-book"), section 9.1 ("Deterministic clock"), section 9.3 (the migration replay order),
D1/D2/D12. GitHub issue #44 (E6.3, milestone M6).

## Why a script and not "just run pytest"

Section 10's assertions are about what **PostgreSQL** refuses, not about what Python believes. A
GiST exclusion constraint, a partial index predicate, a CHECK on `audit_logs.action_type` -- none
of these exist in a mocked session, which is exactly why the unit suite sat green through four
production-breaking defects during M5 (CHANGELOG, 2026-09-01). So the suite needs a real cluster,
and a real cluster needs an owner.

**Production is never an option here.** Not read-only, not "just the invariant queries". The
concurrency harness fires 50 competing writes, the idempotency replay writes exceptions, and the
scenario replay books appointments. This script therefore refuses to run against any database it
did not itself create (see `backend/tests/proof/conftest.py`, which re-checks independently).

## The recorded lesson this script's shape comes from

A data directory whose postmaster is bound to a killable shell leaks orphan postmasters: kill the
shell, and a `postgres.exe` keeps holding the data dir, so the next run's `initdb` or `rmtree`
fails against a directory nobody owns any more. Two concrete consequences for the code below:

1. **The whole lifetime lives in one process.** initdb, start, migrate, test, stop, delete are all
   steps of this one script, wrapped in one `try/finally`. There is no "start the cluster, then run
   pytest yourself" mode, because that is precisely the shape that leaks.
2. **The postmaster never inherits a pipe.** `pg_ctl -w start` was observed to hang indefinitely
   when launched from a shell that captured its stdout: the postmaster inherits the write end of
   the pipe, so the reader never sees EOF and waits forever even though the server came up fine
   (reproduced on this machine, 2026-09-01, PostgreSQL 18.3). Every subprocess below therefore
   redirects to a real file handle, never to a pipe the parent must drain.

A stale-run marker (`RUNS_DIR/*/marker.json`) is written before initdb and removed after teardown,
and a reaper at startup stops and deletes any cluster a previous crashed run left behind.

3. **The reaper asks who owns a directory before deleting it** (issue #105). Two agents ran this
   script concurrently on 2026-09-01 and each destroyed the other's cluster mid-bootstrap: a marker
   file records "a proof cluster lives here", which the reaper was reading as "nobody is using it".
   Every run now writes `owner.pid` into its directory the instant that directory exists, and the
   reaper skips any directory whose owning process is still alive. Concurrent runs in one shared
   RUNS_DIR are therefore safe, and `--runs-dir <own path>` is no longer needed to get isolation --
   it stays available for anyone who wants it anyway.

## Replay order, and why it is not simply "the migrations directory, sorted"

`supabase/migrations/` is **not** a standalone chain. The baseline creates the schema; `seed.sql`
is a separate file that populates it; and later migrations depend on seeded rows --
`20260823100000_e24_escalation_vocabulary.sql` needs `roles.ROL008`, which only `seed.sql` inserts,
and `20260823060000_d1_correctness_bedrock.sql`'s D1 backfill has nothing to backfill (and
therefore produces none of the D12 worklist rows section 10.2 asserts on) unless the seed is
already in place. The order is:

    baseline -> seed.sql -> every remaining migration in filename order

This is the same order the #53 dry run used (CHANGELOG, 2026-08-31) and it is asserted, not
assumed: the script fails loudly if the baseline file is missing or if any step's psql exits
non-zero under `ON_ERROR_STOP=1`.

## The three databases, and why the seed one is separate

* `setuhaul_proof_tpl` -- built once by the replay above, then never connected to again.
* `setuhaul_proof_seed` -- `CREATE DATABASE ... TEMPLATE tpl`. Section 10.2's invariant queries say
  "run against the shipped seed", so they need a database no other part of the suite has written
  to. Parts 4 and 5 read from here too.
* `setuhaul_proof_work` -- the same template, for the parts that mutate (concurrency, idempotency
  replay, chaos-lite).

A template copy rather than a second full replay because it is both faster and *provably* the same
bytes, which matters for part 5's determinism claim.

Usage:

    uv run --frozen python docs/scripts/run_proof_suite.py            # all six parts
    uv run --frozen python docs/scripts/run_proof_suite.py -k invariant
    uv run --frozen python docs/scripts/run_proof_suite.py --keep     # leave the cluster up

Any extra arguments are passed straight through to pytest.
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
SEED_FILE = REPO_ROOT / "supabase" / "seed.sql"
BASELINE_NAME = "20260805201923_setuhaul_baseline.sql"

TEMPLATE_DB = "setuhaul_proof_tpl"
SEED_DB = "setuhaul_proof_seed"
WORK_DB = "setuhaul_proof_work"

SUPERUSER = "postgres"
RUNS_DIR_NAME = "setuhaul-proof-clusters"

# Issue #105. Written into every run directory the instant it is created -- BEFORE initdb, before
# the marker, before anything slow -- so a concurrent run's reaper can tell "someone is using this"
# from "a crashed run left this behind". `marker.json` also carries a pid, but it is not written
# until `initdb()` starts, and the 2026-09-01 collision landed inside exactly that window.
OWNER_PIDFILE_NAME = "owner.pid"

# The safety valve for PID reuse. A dead run's pid can be handed to an unrelated long-lived process,
# which would make its directory look permanently live and leak forever -- so a directory older than
# this is reaped whatever its pid says. Hours, against a suite that takes minutes: it can only ever
# fire on a run that is no longer real.
MAX_CLUSTER_AGE_S = 12 * 60 * 60


class ProofSuiteError(RuntimeError):
    """Anything that means the cluster is not in a state the suite can trust."""


# ----------------------------------------------------------------------------------------------
# Locating the PostgreSQL binaries
# ----------------------------------------------------------------------------------------------


def _candidate_bin_dirs() -> list[Path]:
    explicit = os.environ.get("SETUHAUL_PG_BIN", "").strip()
    if explicit:
        return [Path(explicit)]
    found: list[Path] = []
    which = shutil.which("initdb")
    if which:
        found.append(Path(which).parent)
    # Windows installer layout, newest major first. Deliberately explicit rather than a glob over
    # every drive: this must never accidentally pick a *server* installation's bin dir that some
    # unrelated service is using -- it is only the client/server executables we need, and the
    # cluster itself is always created fresh in a temp dir.
    for base in (Path("C:/Program Files/PostgreSQL"), Path("/usr/lib/postgresql")):
        if base.is_dir():
            for child in sorted(base.iterdir(), reverse=True):
                candidate = child / "bin"
                if candidate.is_dir():
                    found.append(candidate)
    return found


def resolve_pg_bin() -> Path:
    exe = ".exe" if os.name == "nt" else ""
    for candidate in _candidate_bin_dirs():
        if all((candidate / f"{tool}{exe}").exists() for tool in ("initdb", "pg_ctl", "psql")):
            return candidate
    raise ProofSuiteError(
        "Could not find initdb/pg_ctl/psql. Set SETUHAUL_PG_BIN to a PostgreSQL bin directory."
    )


def _tool(pg_bin: Path, name: str) -> str:
    exe = ".exe" if os.name == "nt" else ""
    return str(pg_bin / f"{name}{exe}")


# ----------------------------------------------------------------------------------------------
# Cluster lifecycle
# ----------------------------------------------------------------------------------------------


def free_port() -> int:
    """A port nothing is listening on right now.

    Bind-to-0-then-close is inherently a small race, so the port is *also* re-checked by
    `pg_ctl -w start` refusing to come up, and the local machine's own PostgreSQL service (5432)
    can never be selected because the OS only hands out ephemeral ports.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ThrowawayCluster:
    """One disposable PostgreSQL cluster, owned start to finish by this process."""

    def __init__(self, pg_bin: Path, root: Path, *, keep: bool = False) -> None:
        self.pg_bin = pg_bin
        self.root = root
        self.data_dir = root / "data"
        self.log_file = root / "postgres.log"
        self.marker = root / "marker.json"
        self.port = free_port()
        self.keep = keep
        self.started = False

    # -- process plumbing -----------------------------------------------------------------

    def _run(self, argv: list[str], *, label: str, log_append: bool = True) -> None:
        """Run one PostgreSQL tool with its output going to a FILE, never a pipe.

        See the module docstring: a captured pipe makes `pg_ctl -w start` hang forever because the
        postmaster inherits the write end and the parent waits for an EOF that never comes.
        """
        mode = "ab" if log_append else "wb"
        with open(self.root / "tooling.log", mode) as handle:
            handle.write(f"\n=== {label} :: {' '.join(argv)} ===\n".encode())
            handle.flush()
            completed = subprocess.run(
                argv,
                stdout=handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=str(self.root),
                check=False,
            )
        if completed.returncode != 0:
            tail = (self.root / "tooling.log").read_text(errors="replace")[-4000:]
            raise ProofSuiteError(f"{label} failed (exit {completed.returncode}).\n{tail}")

    # -- lifecycle ------------------------------------------------------------------------

    def initdb(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.marker.write_text(
            json.dumps(
                {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "data_dir": str(self.data_dir),
                    "pg_bin": str(self.pg_bin),
                    "pid": os.getpid(),
                }
            )
        )
        self._run(
            [
                _tool(self.pg_bin, "initdb"),
                "-D", str(self.data_dir),
                "-U", SUPERUSER,
                "-A", "trust",
                "--encoding=UTF8",
                # C locale so ORDER BY text is byte order everywhere the suite runs. Part 5's
                # determinism claim is about byte-identical output; a collation that varies by
                # host would be a real source of drift and it costs nothing to pin it.
                "--locale=C",
            ],
            label="initdb",
            log_append=False,
        )

    def start(self) -> None:
        options = " ".join(
            [
                f"-p {self.port}",
                "-c listen_addresses=127.0.0.1",
                # Throwaway data: durability settings exist only to slow this down.
                "-c fsync=off",
                "-c full_page_writes=off",
                "-c synchronous_commit=off",
                # Part 1 opens 50 concurrent sessions plus the pool's spares.
                "-c max_connections=120",
                # A deadlock in the concurrency harness must surface as a test failure, not as a
                # suite that hangs in CI.
                "-c deadlock_timeout=1s",
                "-c log_min_messages=warning",
            ]
        )
        self._run(
            [
                _tool(self.pg_bin, "pg_ctl"),
                "-D", str(self.data_dir),
                "-l", str(self.log_file),
                "-o", options,
                "-w",
                "-t", "60",
                "start",
            ],
            label="pg_ctl start",
        )
        self.started = True
        self._await_ready()

    def _await_ready(self, timeout_s: float = 30.0) -> None:
        deadline = time.monotonic() + timeout_s
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=2):
                    return
            except OSError as exc:  # noqa: PERF203 - polling loop
                last = exc
                time.sleep(0.25)
        raise ProofSuiteError(f"Cluster never accepted connections on 127.0.0.1:{self.port}: {last}")

    def stop(self) -> None:
        if not self.started:
            return
        try:
            self._run(
                [
                    _tool(self.pg_bin, "pg_ctl"),
                    "-D", str(self.data_dir),
                    "-m", "immediate",
                    "-w",
                    "-t", "30",
                    "stop",
                ],
                label="pg_ctl stop",
            )
        except ProofSuiteError:
            # Report, never swallow: an unstoppable postmaster is the exact orphan condition this
            # script exists to avoid, and the operator needs the data dir path to clean it by hand.
            print(
                f"WARNING: pg_ctl stop failed for {self.data_dir}. "
                "Check for an orphan postmaster before the next run.",
                file=sys.stderr,
            )
            return
        finally:
            self.started = False

    def destroy(self) -> None:
        if self.keep:
            # `--keep` deliberately leaves the postmaster RUNNING, not merely the files on disk --
            # a stopped cluster cannot be inspected, which is the only reason to ask for one. That
            # is an orphan by request, so say so plainly and say how it goes away: the reaper at the
            # top of the next run stops and deletes any cluster carrying a marker file.
            print(
                f"--keep set: cluster LEFT RUNNING at 127.0.0.1:{self.port} ({self.root}).\n"
                f"  inspect : psql -h 127.0.0.1 -p {self.port} -U {SUPERUSER} -d {SEED_DB}\n"
                f"  destroy : pg_ctl -D {self.data_dir} -m immediate stop   (or just run this "
                "script again -- it reaps stale clusters on startup)"
            )
            return
        self.stop()
        for attempt in range(10):
            try:
                shutil.rmtree(self.root, ignore_errors=False)
                return
            except OSError:
                # Windows holds file handles briefly after the postmaster exits.
                time.sleep(0.5 * (attempt + 1))
        shutil.rmtree(self.root, ignore_errors=True)

    # -- SQL ------------------------------------------------------------------------------

    def url(self, dbname: str) -> str:
        return f"postgresql://{SUPERUSER}@127.0.0.1:{self.port}/{dbname}"

    def psql_file(self, dbname: str, path: Path) -> None:
        self._run(
            [
                _tool(self.pg_bin, "psql"),
                "-h", "127.0.0.1",
                "-p", str(self.port),
                "-U", SUPERUSER,
                "-d", dbname,
                "-v", "ON_ERROR_STOP=1",
                "--no-psqlrc",
                "-q",
                "-f", str(path),
            ],
            label=f"psql {dbname} < {path.name}",
        )

    def psql_command(self, dbname: str, sql: str, *, label: str | None = None) -> None:
        self._run(
            [
                _tool(self.pg_bin, "psql"),
                "-h", "127.0.0.1",
                "-p", str(self.port),
                "-U", SUPERUSER,
                "-d", dbname,
                "-v", "ON_ERROR_STOP=1",
                "--no-psqlrc",
                "-q",
                "-c", sql,
            ],
            label=label or f"psql {dbname} -c",
        )


# ----------------------------------------------------------------------------------------------
# Migration replay
# ----------------------------------------------------------------------------------------------


# Supabase provisions these three roles on every project; the migrations REVOKE/GRANT against them
# by name, so a bare PostgreSQL cluster fails at the baseline's first `revoke ... from anon`
# (reproduced 2026-09-01: `ERROR: role "anon" does not exist`). Created NOLOGIN and with no
# privileges: the point is only that the GRANT statements in the shipped migrations execute exactly
# as written, so the replayed schema is the schema production has -- not to emulate Supabase's Data
# API, which nothing in this suite goes through.
SUPABASE_ROLE_BOOTSTRAP = """
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon','authenticated','service_role'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN NOINHERIT', r);
    END IF;
  END LOOP;
END $$;
"""


def replay_chain(cluster: ThrowawayCluster) -> list[str]:
    """baseline -> seed.sql -> remaining migrations. Returns the applied file names, in order."""
    baseline = MIGRATIONS_DIR / BASELINE_NAME
    if not baseline.is_file():
        raise ProofSuiteError(f"Baseline migration missing: {baseline}")
    if not SEED_FILE.is_file():
        raise ProofSuiteError(f"Seed missing: {SEED_FILE}")

    rest = sorted(p for p in MIGRATIONS_DIR.glob("*.sql") if p.name != BASELINE_NAME)

    cluster.psql_command("postgres", SUPABASE_ROLE_BOOTSTRAP, label="bootstrap supabase roles")
    cluster.psql_command("postgres", f'CREATE DATABASE "{TEMPLATE_DB}"', label="create template db")

    applied: list[str] = []
    for path in [baseline, SEED_FILE, *rest]:
        cluster.psql_file(TEMPLATE_DB, path)
        applied.append(path.name)
    return applied


def clone_databases(cluster: ThrowawayCluster) -> None:
    for target in (SEED_DB, WORK_DB):
        cluster.psql_command(
            "postgres",
            f'CREATE DATABASE "{target}" TEMPLATE "{TEMPLATE_DB}"',
            label=f"clone {target}",
        )


# ----------------------------------------------------------------------------------------------
# Stale-run reaper
# ----------------------------------------------------------------------------------------------


def process_is_alive(pid: int) -> bool:
    """Is a process with this pid running right now? Query only -- never signals anything.

    ## Windows: NOT `os.kill(pid, 0)`

    `os.kill(pid, 0)` is the POSIX idiom and it is actively dangerous on Windows. CPython's Windows
    branch has no null-signal concept: `signal.CTRL_C_EVENT` **is** the integer 0, so 0 is either
    dispatched as a console control event or passed to `TerminateProcess` as the victim's exit
    code. bpo-14480 ("os.kill on Windows should accept zero as signal") asked for the POSIX
    behaviour and was **rejected** -- "0 has no special meaning on Windows". So on this platform the
    idiomatic liveness probe is a kill, which in this script would mean the reaper terminating the
    very run it was asked to leave alone.

    The real query is `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION=0x1000)` +
    `GetExitCodeProcess`, both verified against Microsoft's current reference (2026-09-01):

      * `OpenProcess` "returns NULL" if the function fails; a non-existent pid fails with
        `ERROR_INVALID_PARAMETER`, and a process that exists but is protected fails with
        `ERROR_ACCESS_DENIED` -- so access-denied is treated as ALIVE, not as absent.
      * `GetExitCodeProcess` is why opening a handle is not by itself enough: a terminated process
        object outlives its exit while handles remain, and the docs state the status is
        `STILL_ACTIVE` (259) only "if the process has not terminated".

    `psutil` would do this in one line and is deliberately not added -- it is not in
    `backend/pyproject.toml` and this is one helper in one dev script.

    ## POSIX: `os.kill(pid, 0)` is exactly right

    POSIX.1 `kill()`: "If sig is 0 (the null signal), error checking is performed but no signal is
    actually sent. The null signal can be used to check the validity of pid." `ESRCH` means no such
    process; `EPERM` means it exists but is not ours to signal -- alive either way.
    """
    if pid <= 0:
        return False

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        ERROR_ACCESS_DENIED = 5

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            # Existing-but-unopenable counts as alive: refusing to reap something we cannot inspect
            # is the safe direction for a function whose "false" answer deletes a data directory.
            return ctypes.get_last_error() == ERROR_ACCESS_DENIED
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True
    return True


def write_owner_pidfile(root: Path) -> None:
    """Claim a run directory for this process. Must run before anything else touches `root`."""
    (root / OWNER_PIDFILE_NAME).write_text(str(os.getpid()), encoding="utf-8")


def _owner_pid(child: Path) -> int | None:
    """This run directory's owning pid, or None if it never recorded one."""
    pidfile = child / OWNER_PIDFILE_NAME
    if pidfile.is_file():
        try:
            return int(pidfile.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
    # Directories created before issue #105 carry the pid inside marker.json instead. Read it so an
    # in-flight run started by an older copy of this script is still respected.
    marker = child / "marker.json"
    if marker.is_file():
        try:
            value = json.loads(marker.read_text(encoding="utf-8")).get("pid")
        except (OSError, ValueError):
            return None
        if isinstance(value, int):
            return value
    return None


def _age_seconds(child: Path) -> float:
    """How long ago this run directory was created, best effort."""
    for candidate in (child / OWNER_PIDFILE_NAME, child / "marker.json", child):
        try:
            return max(0.0, time.time() - candidate.stat().st_mtime)
        except OSError:
            continue
    return 0.0


def reap_stale_runs(runs_dir: Path, pg_bin: Path) -> tuple[int, int]:
    """Stop and delete clusters a previous crashed run left behind.

    Returns `(reaped, skipped_live)`.

    **Issue #105 -- this used to delete every directory carrying a marker, full stop.** Correct for
    the single-user design it was written for, destructive the moment two agents ran the suite at
    once on 2026-09-01: one run's "stale" sweep caught the other's live `initdb`, because a marker
    file says "a proof cluster lives here", not "nobody is using it". The liveness question needed
    an owner, so every run now writes `owner.pid` before it does anything else and a directory whose
    owner is still running is left alone.

    Age-based cleanup is retained for the dead ones -- and it is load-bearing rather than belt and
    braces, because `--keep` deliberately leaves a postmaster running after its owning process
    exits. That is a dead pid by design, and it must still be reaped, which is exactly what
    `--keep`'s own message promises ("just run this script again").
    """
    if not runs_dir.is_dir():
        return 0, 0
    reaped = 0
    skipped = 0
    for child in sorted(runs_dir.iterdir()):
        if not child.is_dir():
            continue
        # A directory with neither file is not this script's to touch -- and it is also the
        # sub-millisecond window between `mkdtemp` and `write_owner_pidfile`, so skipping is the
        # safe reading either way.
        if not (child / "marker.json").is_file() and not (child / OWNER_PIDFILE_NAME).is_file():
            continue

        pid = _owner_pid(child)
        if pid is not None and process_is_alive(pid) and _age_seconds(child) < MAX_CLUSTER_AGE_S:
            skipped += 1
            continue

        data_dir = child / "data"
        if data_dir.is_dir():
            subprocess.run(
                [_tool(pg_bin, "pg_ctl"), "-D", str(data_dir), "-m", "immediate", "-w", "-t", "20", "stop"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        shutil.rmtree(child, ignore_errors=True)
        reaped += 1
    return reaped, skipped


# ----------------------------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------------------------


def build_child_env(cluster: ThrowawayCluster) -> dict[str, str]:
    """The environment pytest runs under.

    Every value that could reach production is overwritten, not merely left unset: pydantic-settings
    reads OS environment variables at a HIGHER priority than a dotenv file ("environment variables
    will always take priority over values loaded from a dotenv file" -- pydantic-settings docs,
    checked 2026-09-01 against the pinned 2.15.0), and this repo has a real `.env.local` at its root
    carrying the production `DATABASE_URL` and Supabase keys. Setting them to the throwaway values
    here is what makes it impossible for `get_settings()` to resolve production inside the suite.
    """
    env = dict(os.environ)
    env["SETUHAUL_PROOF_SEED_URL"] = cluster.url(SEED_DB)
    env["SETUHAUL_PROOF_WORK_URL"] = cluster.url(WORK_DB)
    env["SETUHAUL_PROOF_PORT"] = str(cluster.port)
    env["DATABASE_URL"] = cluster.url(WORK_DB)
    # Blank rather than absent, for the same priority reason as above.
    for key in (
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
        "UPSTASH_REDIS_NATIVE_URL",
        "LANGSMITH_API_KEY",
    ):
        env[key] = ""
    env["LANGSMITH_TRACING"] = "false"
    # Section 10.1's expected 1-HELD/49-conflict split is the two-phase contract, which is also the
    # shipped default (settings.py, flipped 2026-08-31). Pinned explicitly so the harness cannot be
    # silently retargeted at the legacy single-phase path by a stray environment.
    # `Settings` declares no env_prefix, so the field `two_phase_hold_enabled` reads exactly this
    # name -- not a SETUHAUL_-prefixed one.
    env["TWO_PHASE_HOLD_ENABLED"] = "true"
    env["ALLOW_REGION_MISMATCH"] = "true"
    env["PYTHONPATH"] = str(BACKEND_DIR)
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep", action="store_true", help="leave the cluster running after the suite")
    parser.add_argument("--runs-dir", default=None, help="where throwaway clusters are created")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    pg_bin = resolve_pg_bin()
    runs_dir = Path(args.runs_dir) if args.runs_dir else Path(tempfile.gettempdir()) / RUNS_DIR_NAME
    runs_dir.mkdir(parents=True, exist_ok=True)

    reaped, skipped = reap_stale_runs(runs_dir, pg_bin)
    if reaped:
        print(f"Reaped {reaped} stale throwaway cluster(s) from a previous run.")
    if skipped:
        # Say so rather than staying silent: "another run is using this directory" is the single
        # most useful thing to know when two suites are in flight (issue #105).
        print(f"Left {skipped} cluster(s) alone -- still owned by a live process.")

    root = Path(tempfile.mkdtemp(prefix="run-", dir=str(runs_dir)))
    # Issue #105: claim the directory immediately. `mkdtemp` has already created it, so any gap
    # between these two lines is a gap in which a concurrent reaper sees an unclaimed directory.
    write_owner_pidfile(root)
    cluster = ThrowawayCluster(pg_bin, root, keep=args.keep)

    # Belt and braces on top of the try/finally below: a SIGINT during the pytest run must still
    # take the postmaster down with it rather than leaving it holding the data dir.
    atexit.register(cluster.destroy)

    def _signal_handler(signum, _frame):  # type: ignore[no-untyped-def]
        cluster.destroy()
        sys.exit(128 + signum)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _signal_handler)
        except (ValueError, OSError):  # not all signals exist on all platforms
            pass

    started = time.monotonic()
    try:
        print(f"PostgreSQL bin : {pg_bin}")
        print(f"Cluster root   : {root}")
        cluster.initdb()
        cluster.start()
        print(f"Cluster up     : 127.0.0.1:{cluster.port}")

        applied = replay_chain(cluster)
        print(f"Replayed       : {len(applied)} files (baseline -> seed.sql -> {len(applied) - 2} migrations)")
        clone_databases(cluster)
        print(f"Databases      : {SEED_DB} (pristine) + {WORK_DB} (mutable)")

        pytest_args = [a for a in (args.pytest_args or []) if a != "--"]
        cmd = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "tests/proof", *pytest_args]
        print(f"Running        : {' '.join(cmd)}\n")
        completed = subprocess.run(cmd, cwd=str(BACKEND_DIR), env=build_child_env(cluster), check=False)
        return completed.returncode
    finally:
        elapsed = time.monotonic() - started
        cluster.destroy()
        atexit.unregister(cluster.destroy)
        print(f"\nCluster torn down after {elapsed:.1f}s.")


if __name__ == "__main__":
    raise SystemExit(main())
