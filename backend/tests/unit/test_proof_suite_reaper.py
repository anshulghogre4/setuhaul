"""Issue #105: `run_proof_suite.py`'s startup reaper must not destroy a concurrent run's cluster.

The recorded incident (2026-09-01): two agents ran the proof suite at the same time against the
shared RUNS_DIR and each reaped the other's directory mid-`initdb`. The reaper deleted every
directory carrying `marker.json`, and a marker means "a proof cluster lives here" -- never "nobody
is using it".

These tests pin the *distinction*, not the deletion: a directory owned by a live process survives,
a directory owned by a dead one does not. The `pg_ctl stop` subprocess is stubbed throughout --
what is under test is which directories get chosen, and standing up real postmasters to prove a
predicate would make the suite slower and flakier for no extra signal.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "docs" / "scripts" / "run_proof_suite.py"

_spec = importlib.util.spec_from_file_location("run_proof_suite", SCRIPT_PATH)
proof = importlib.util.module_from_spec(_spec)
sys.modules["run_proof_suite"] = proof
_spec.loader.exec_module(proof)


# A pid that is essentially certain not to be running. 2**22 is above the default Linux
# `pid_max` (4194304 is the ceiling, 32768 the common default) and is not a live Windows pid on any
# machine this suite runs on. `_dead_pid` re-checks it rather than trusting the arithmetic, so a
# freak collision fails loudly here instead of silently weakening every assertion below.
_CANDIDATE_DEAD_PID = 2**22 - 1


@pytest.fixture(scope="module")
def dead_pid() -> int:
    if proof.process_is_alive(_CANDIDATE_DEAD_PID):
        pytest.skip(f"pid {_CANDIDATE_DEAD_PID} is unexpectedly live on this machine")
    return _CANDIDATE_DEAD_PID


@pytest.fixture()
def no_pg_ctl(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Stub `subprocess.run` inside the script module and record what it was asked to stop."""
    calls: list[list[str]] = []

    def _fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(proof.subprocess, "run", _fake_run)
    # `_tool` would otherwise need a real PostgreSQL bin directory on the machine running the suite.
    monkeypatch.setattr(proof, "_tool", lambda _bin, name: name)
    return calls


def _make_run_dir(runs_dir: Path, name: str, pid: int, *, with_marker: bool = True) -> Path:
    """A run directory shaped exactly like a real one: owner.pid, marker.json, and a data dir."""
    child = runs_dir / name
    (child / "data").mkdir(parents=True)
    (child / proof.OWNER_PIDFILE_NAME).write_text(str(pid), encoding="utf-8")
    if with_marker:
        (child / "marker.json").write_text(
            json.dumps({"created_at": "2026-09-01T00:00:00+00:00", "pid": pid})
        )
    return child


# ----------------------------------------------------------------------------------------------
# The incident, reproduced as a test
# ----------------------------------------------------------------------------------------------


def test_a_live_pid_directory_survives_and_a_dead_one_is_reaped(tmp_path, dead_pid, no_pg_ctl):
    """The exact 2026-09-01 collision: one live run, one crashed run, one reaper pass."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    # os.getpid() is genuinely alive -- this test process. No mocking of the liveness predicate
    # anywhere in this file, which is the point: the Windows implementation is what needs proving.
    live = _make_run_dir(runs_dir, "run-live", os.getpid())
    dead = _make_run_dir(runs_dir, "run-dead", dead_pid)

    reaped, skipped = proof.reap_stale_runs(runs_dir, Path("pgbin"))

    assert (reaped, skipped) == (1, 1)
    assert live.is_dir(), "a concurrent run's cluster must survive the reaper"
    assert not dead.exists(), "a crashed run's cluster must still be cleaned up"


def test_the_reaper_only_stops_the_postmaster_it_is_about_to_delete(tmp_path, dead_pid, no_pg_ctl):
    """`pg_ctl stop` against a live run's data dir IS the destruction, even without the rmtree."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    live = _make_run_dir(runs_dir, "run-live", os.getpid())
    dead = _make_run_dir(runs_dir, "run-dead", dead_pid)

    proof.reap_stale_runs(runs_dir, Path("pgbin"))

    stopped = [argv for argv in no_pg_ctl if "stop" in argv]
    assert len(stopped) == 1
    joined = " ".join(stopped[0])
    assert str(dead / "data") in joined
    assert str(live / "data") not in joined


# ----------------------------------------------------------------------------------------------
# Liveness predicate
# ----------------------------------------------------------------------------------------------


def test_process_is_alive_agrees_with_reality_for_this_process_and_a_dead_pid(dead_pid):
    assert proof.process_is_alive(os.getpid()) is True
    assert proof.process_is_alive(dead_pid) is False
    # 0 is the System Idle Process on Windows and "every process in the caller's group" for POSIX
    # kill(2) -- neither is an owner this script can ever have recorded.
    assert proof.process_is_alive(0) is False
    assert proof.process_is_alive(-1) is False


def test_a_real_child_process_is_alive_then_dead():
    """End to end through the actual OS, not a pid arithmetic argument.

    This is the test that would have caught `os.kill(pid, 0)` on Windows -- there, signal 0 is
    `CTRL_C_EVENT`/`TerminateProcess`, so the "probe" kills the child and the second assertion
    would still pass while the first had already destroyed what it measured.
    """
    child = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert proof.process_is_alive(child.pid) is True
        # Probing must not have disturbed it: still running after the check.
        assert child.poll() is None
    finally:
        child.stdin.close()
        child.wait(timeout=30)

    # Windows keeps the process object addressable while `child` holds a handle, so this is also
    # the assertion that proves GetExitCodeProcess is consulted rather than OpenProcess alone.
    assert proof.process_is_alive(child.pid) is False


# ----------------------------------------------------------------------------------------------
# Ownership bookkeeping
# ----------------------------------------------------------------------------------------------


def test_write_owner_pidfile_claims_the_directory_for_this_process(tmp_path):
    proof.write_owner_pidfile(tmp_path)
    assert (tmp_path / proof.OWNER_PIDFILE_NAME).read_text(encoding="utf-8") == str(os.getpid())
    assert proof._owner_pid(tmp_path) == os.getpid()


def test_a_pre_105_directory_is_respected_through_its_marker_pid(tmp_path, no_pg_ctl):
    """A run started by an older copy of this script has no owner.pid -- only marker.json's pid.

    Without this fallback, upgrading the script mid-flight would make the first new-format run
    reap a live old-format one, which is the very incident being fixed.
    """
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    child = runs_dir / "run-old"
    (child / "data").mkdir(parents=True)
    (child / "marker.json").write_text(json.dumps({"pid": os.getpid()}))

    reaped, skipped = proof.reap_stale_runs(runs_dir, Path("pgbin"))

    assert (reaped, skipped) == (0, 1)
    assert child.is_dir()


def test_a_directory_with_no_ownership_files_is_left_untouched(tmp_path, no_pg_ctl):
    """The `mkdtemp`-to-`write_owner_pidfile` window, and anything else that is not ours."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    fresh = runs_dir / "run-just-created"
    fresh.mkdir()
    stray = runs_dir / "notes.txt"
    stray.write_text("not a cluster")

    reaped, skipped = proof.reap_stale_runs(runs_dir, Path("pgbin"))

    assert (reaped, skipped) == (0, 0)
    assert fresh.is_dir()
    assert stray.is_file()


def test_an_unreadable_pidfile_falls_back_rather_than_crashing(tmp_path, no_pg_ctl):
    """A truncated owner.pid must not take the whole suite down before it starts."""
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    child = runs_dir / "run-corrupt"
    (child / "data").mkdir(parents=True)
    (child / proof.OWNER_PIDFILE_NAME).write_text("", encoding="utf-8")
    (child / "marker.json").write_text("{not json")

    assert proof._owner_pid(child) is None
    reaped, _ = proof.reap_stale_runs(runs_dir, Path("pgbin"))
    # Unknown owner falls back to the pre-#105 contract: reap, preserving leak prevention.
    assert reaped == 1


# ----------------------------------------------------------------------------------------------
# Age ceiling -- the PID-reuse safety valve, and what makes `--keep` still work
# ----------------------------------------------------------------------------------------------


def test_a_live_pid_directory_older_than_the_ceiling_is_still_reaped(tmp_path, no_pg_ctl):
    """PID reuse must not create an immortal directory.

    Uses this process's own (definitely live) pid with a backdated mtime, so the ceiling is the
    only thing that can decide the outcome.
    """
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    child = _make_run_dir(runs_dir, "run-ancient", os.getpid())
    old = time.time() - (proof.MAX_CLUSTER_AGE_S + 60)
    for path in (child / proof.OWNER_PIDFILE_NAME, child / "marker.json", child):
        os.utime(path, (old, old))

    reaped, skipped = proof.reap_stale_runs(runs_dir, Path("pgbin"))

    assert (reaped, skipped) == (1, 0)
    assert not child.exists()


def test_the_ceiling_cannot_fire_on_a_run_of_realistic_length():
    """A guard on the constant itself: the suite takes minutes, the ceiling is hours."""
    assert proof.MAX_CLUSTER_AGE_S >= 6 * 60 * 60


def test_a_keep_left_cluster_is_reaped_because_its_owner_exited(tmp_path, dead_pid, no_pg_ctl):
    """`--keep` leaves the postmaster running and lets its owning process exit.

    That is a dead pid by design, and `destroy()`'s own message promises the next run cleans it up
    ("just run this script again"). Age-based cleanup for dead owners is what keeps that promise.
    """
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    kept = _make_run_dir(runs_dir, "run-kept", dead_pid)

    reaped, skipped = proof.reap_stale_runs(runs_dir, Path("pgbin"))

    assert (reaped, skipped) == (1, 0)
    assert not kept.exists()
