"""E4.2 (issue #32): one command that cannot succeed without syncing first.

DEPLOYMENT.md section 2.2's first-choice fix -- the 2026-08-17 incident (and its 2026-08-25
recurrence, confirmed live) both happened because `agentcore.cmd deploy` was run without first
re-running `stage_agentcore_codezip.py`, and the CLI reports success either way since it only
knows about `agentcore/codezip/`, never `backend/app/` directly.

Usage: python docs/scripts/agentcore_deploy.py [--dry-run] [--skip-local-verify]

Pipeline, each step gating the next:
  1. stage   -- regenerate agentcore/codezip/ from backend/app/ + backend/pyproject.toml
  2. verify  -- `agentcore package`, the vendor tool's own artifact build, run locally
               (no AWS credentials required; catches a broken/unresolvable dependency set
               before anything is shipped, not after)
  3. deploy  -- `agentcore deploy --yes` (or --dry-run), only if 1 and 2 both succeeded
  4. confirm -- compare AWS's own agentRuntimeVersion (via `aws bedrock-agentcore-control
               get-agent-runtime`) before and after; unchanged after a real (non-dry-run) deploy
               is flagged, not silently accepted -- that is the exact signature of the 2026-08-17
               incident reproduced structurally (CLI exit 0, content unchanged)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_agentcore_codezip as stage  # noqa: E402

ROOT = stage.ROOT
DEPLOYED_STATE_PATH = ROOT / "agentcore" / ".cli" / "deployed-state.json"
RUNTIME_NAME = "SetuHaulAgent"


def _run(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(args)}")
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def read_runtime_id(*, target: str = "default", runtime: str = RUNTIME_NAME) -> str | None:
    """Read agentcore/.cli/deployed-state.json's runtimeId, or None if absent."""
    if not DEPLOYED_STATE_PATH.is_file():
        return None
    data = json.loads(DEPLOYED_STATE_PATH.read_text(encoding="utf-8"))
    try:
        return data["targets"][target]["resources"]["runtimes"][runtime]["runtimeId"]
    except (KeyError, TypeError):
        return None


AWS_TARGETS_PATH = ROOT / "agentcore" / "aws-targets.json"


def read_target_region(*, target: str = "default") -> str | None:
    """Read agentcore/aws-targets.json's region for one deploy target, or None if absent."""
    if not AWS_TARGETS_PATH.is_file():
        return None
    data = json.loads(AWS_TARGETS_PATH.read_text(encoding="utf-8"))
    for entry in data:
        if entry.get("name") == target:
            return entry.get("region")
    return None


def read_runtime_version(runtime_id: str, *, region: str | None = None) -> str | None:
    """The live AWS-reported agentRuntimeVersion for one runtime, or None if unreachable.

    Tried `deployHash` from deployed-state.json first (E4.2/issue #32's first attempt) -- it
    turned out identical before and after a real, AWS-confirmed new deployment (agentRuntimeVersion
    9 -> 10), so it is not the content signal its name suggests and was not safe to rely on.
    `agentRuntimeVersion`, queried directly from AWS rather than a local cached file, is the
    real signal -- verified live: it changes exactly when a new deployment actually lands.
    Uses the `aws` CLI via subprocess, not boto3 -- this machine's current AWS login flow needs
    `botocore[crt]` for boto3's credential provider, which the CLI itself does not require.

    `region` must be passed explicitly (from `read_target_region()`) once a runtime lives outside
    the CLI's default region -- E7.1's ap-south-1 deploy hit exactly this: the deploy itself
    succeeded (independently confirmed live) but this function silently returned None because it
    queried the wrong region, and the caller had no way to tell "verification failed" apart from
    "nothing to verify." Fixed here rather than left as a known gap.
    """
    args = ["aws", "bedrock-agentcore-control", "get-agent-runtime", "--agent-runtime-id", runtime_id]
    if region:
        args += ["--region", region]
    args += ["--output", "json"]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout).get("agentRuntimeVersion")
    except json.JSONDecodeError:
        return None


def run_backend_tests() -> bool:
    """The owner's 2026-08-22 rule: 'it deployed successfully is not evidence it works.' A
    package that builds cleanly can still be behaviorally wrong -- the test suite is this
    project's actual standard for 'it works', so it gates a deploy the same way it gates every
    other change."""
    print("[local-verify] backend unit test suite ...")
    result = _run(
        ["uv", "run", "--no-sync", "python", "-m", "pytest", "tests/unit", "-q"],
        cwd=ROOT / "backend",
    )
    print(result.stdout[-3000:])
    if result.returncode != 0:
        print(result.stderr[-2000:])
        print("[local-verify] backend tests FAILED")
        return False
    print("[local-verify] backend tests OK")
    return True


def local_verify(*, agentcore_cmd: str) -> bool:
    """Behavior (the test suite) plus packaging (the vendor CLI's own artifact build, run
    locally) -- confirms both that the code works and that the staged codezip's dependency set
    actually resolves and packages, before anything is shipped."""
    if not run_backend_tests():
        return False
    print("[local-verify] agentcore package -- building the artifact locally (no AWS needed) ...")
    result = _run([agentcore_cmd, "package", "-r", RUNTIME_NAME], cwd=ROOT)
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        print("[local-verify] agentcore package FAILED")
        return False
    print("[local-verify] OK")
    return True


def deploy(*, agentcore_cmd: str, dry_run: bool) -> bool:
    args = [agentcore_cmd, "deploy", "--yes"]
    if dry_run:
        args.append("--dry-run")
    print(f"[deploy] {'dry-run ' if dry_run else ''}deploying ...")
    result = subprocess.run(args, cwd=ROOT)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Pass --dry-run through to agentcore deploy.")
    parser.add_argument(
        "--skip-local-verify", action="store_true",
        help="Skip `agentcore package` before deploying. Not recommended.",
    )
    parser.add_argument(
        "--agentcore-cmd", default="agentcore",
        help="Path to the agentcore CLI executable (default: 'agentcore' on PATH).",
    )
    args = parser.parse_args()

    print("[stage] regenerating agentcore/codezip/ from backend/app/ + backend/pyproject.toml ...")
    if stage.main() != 0:
        print("STAGING FAILED -- deploy aborted. No agentcore command was run.")
        return 1

    if args.skip_local_verify:
        print("[local-verify] SKIPPED (--skip-local-verify) -- not recommended.")
    elif not local_verify(agentcore_cmd=args.agentcore_cmd):
        print("LOCAL VERIFY FAILED -- deploy aborted. Fix the artifact before deploying.")
        return 1

    region = read_target_region()
    pre_runtime_id = None if args.dry_run else read_runtime_id()
    pre_version = read_runtime_version(pre_runtime_id, region=region) if pre_runtime_id else None

    if not deploy(agentcore_cmd=args.agentcore_cmd, dry_run=args.dry_run):
        print("DEPLOY FAILED.")
        return 1

    if args.dry_run:
        print("Dry run complete -- nothing was actually deployed, runtime version not checked.")
        return 0

    post_runtime_id = read_runtime_id()
    post_version = read_runtime_version(post_runtime_id, region=region) if post_runtime_id else None
    print(f"[confirm] agentRuntimeVersion before={pre_version!r} after={post_version!r}")
    if pre_version is None or post_version is None:
        print(
            "[confirm] UNKNOWN -- could not read agentRuntimeVersion before and/or after; "
            "nothing proven either way. Run `agentcore status` and check manually."
        )
    elif pre_version == post_version:
        print(
            "WARNING: agentRuntimeVersion did not change. If you expected new code to ship, "
            "this is the exact 2026-08-17 incident signature (CLI reported success, content "
            "unchanged) -- do not assume the deploy actually shipped anything new without "
            "investigating."
        )
    else:
        print(
            f"[confirm] agentRuntimeVersion changed ({pre_version} -> {post_version}) -- "
            "deployed content is provably different from before."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
