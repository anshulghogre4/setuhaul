"""E4.2 (issue #32): one command that cannot succeed without syncing first.

DEPLOYMENT.md section 2.2's first-choice fix -- the 2026-08-17 incident (and its 2026-08-25
recurrence, confirmed live) both happened because `agentcore.cmd deploy` was run without first
re-running `stage_agentcore_codezip.py`, and the CLI reports success either way since it only
knows about `agentcore/codezip/`, never `backend/app/` directly.

Usage: python docs/scripts/agentcore_deploy.py [--dry-run] [--skip-local-verify]
                                              [--skip-invoke-smoke]

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
  5. smoke   -- issue #92: actually INVOKE the runtime once and fail the run if the answer is an
               error. Step 4 proves new content shipped; it says nothing about whether the thing
               that shipped can serve a request. On 2026-09-01 a deploy passed steps 1-4 cleanly
               and chat was down for every user, because the deploy's own CloudFormation update
               had recreated the execution role and wiped its hand-attached SSM grant. This step
               is what would have caught that at deploy time instead of at click-through time.

STANDING RULE (issue #92, adopted 2026-09-02): the IAM grants this runtime and the ECS BFF need
are IaC/version-controlled artifacts now, and hand-patching them is FORBIDDEN.
  * runtime execution role's `/setuhaul/*` SSM read  -> agentcore/cdk/lib/cdk-stack.ts
  * BFF task role's InvokeAgentRuntime grant         -> deploy/bff-task-role-invoke-policy.json
                                                        (+ deploy/apply_bff_invoke_policy.{sh,ps1})
A policy applied by hand to an IaC-managed role survives exactly until the next deploy, then
disappears silently. That is not a hypothetical -- it is the recorded cause of #92. If a grant is
missing, add it to the artifact and redeploy; do not `aws iam put-role-policy` your way out.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_agentcore_codezip as stage  # noqa: E402

ROOT = stage.ROOT
DEPLOYED_STATE_PATH = ROOT / "agentcore" / ".cli" / "deployed-state.json"
RUNTIME_NAME = "SetuHaulAgent"

# The invoke-smoke payload. Reuses the checked-in Sprint-4 Step-8 payload rather than inventing a
# second one: it is a real DRIVER ExecutionContext for the seeded demo driver (Ravi/USR001), it has
# been proven end to end against a live runtime before, and it is read-only in effect -- the turn it
# provokes calls read tools (list_active_shipments and friends), never a booking or a mutation.
# A payload WITHOUT execution_context would be cheaper, but it would be useless here: the runtime
# rejects it in agentcore_main._run_turn BEFORE _ensure_db() runs, so it would never touch SSM
# hydration -- i.e. it would not have caught the 2026-09-01 incident, which is the entire point.
INVOKE_SMOKE_PAYLOAD_PATH = ROOT / "docs" / "scripts" / "agentcore_invoke_ravi.json"

# The ECS task role that the BFF actually invokes AgentCore with, and the inline policy name its
# grant lives under. Read-only here; the writable artifact is deploy/bff-task-role-invoke-policy.json.
BFF_TASK_ROLE_NAME = "setuhaul-bff-task-role"
BFF_INVOKE_POLICY_NAME = "SetuHaulInvokeAgentCore"

# Failure signatures worth naming explicitly, so the operator gets "this is #92 defect N again"
# instead of a raw error string they have to re-diagnose from scratch at 5am.
_ACCESS_DENIED_MARKERS = ("AccessDenied", "not authorized", "UnrecognizedClient")
_HYDRATION_MARKERS = (
    "Database is not configured",
    "ssm hydrate",
    "No LLM API key",
    "RegionMismatch",
)


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


def read_runtime_arn(*, target: str = "default", runtime: str = RUNTIME_NAME) -> str | None:
    """Read agentcore/.cli/deployed-state.json's runtimeArn, or None if absent.

    Sibling of read_runtime_id(): the version check needs the bare id (that is what
    `bedrock-agentcore-control get-agent-runtime --agent-runtime-id` takes), while the data-plane
    invoke needs the full ARN. Reading the ARN rather than rebuilding it from id+region matters --
    a rebuilt ARN would be a guess about the very region E7.1 has been migrating.
    """
    if not DEPLOYED_STATE_PATH.is_file():
        return None
    data = json.loads(DEPLOYED_STATE_PATH.read_text(encoding="utf-8"))
    try:
        return data["targets"][target]["resources"]["runtimes"][runtime]["runtimeArn"]
    except (KeyError, TypeError):
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


def _smoke_session_id() -> str:
    """A fresh runtimeSessionId per smoke, >= 33 chars.

    Two hard constraints, both real:
      * AWS requires 33-256 characters (verified against the current
        `aws bedrock-agentcore invoke-agent-runtime` CLI reference, not from memory). The BFF's own
        runtime_session_id() right-pads for the same reason.
      * It must be FRESH on every run. AgentCore hydrates SSM per cold start and a warm container
        keeps whatever environment it booted with -- #92's own operational note records a half-
        hydrated warm container still 502ing after the IAM fix had landed. Reusing a session id
        would let this smoke land on that stale container and report a fix that is not proven.
        A new id maximises the chance of a fresh worker; it does not guarantee one, which is why a
        PASS here means "a live worker answered", not "every warm worker has been recycled".
    """
    return f"setuhaul-deploy-smoke-{uuid.uuid4().hex}"


def _classify_runtime_error(text: str) -> str | None:
    """Name the incident class for a failure string, or None if it is not one we recognise."""
    if any(marker in text for marker in _ACCESS_DENIED_MARKERS):
        return (
            "ACCESS DENIED on InvokeAgentRuntime. This is #92 defect 1's shape: the caller's IAM "
            "policy does not cover this runtime ARN. For the BFF's own role the checked-in grant "
            "is deploy/bff-task-role-invoke-policy.json -- apply it with "
            "deploy/apply_bff_invoke_policy.sh (or .ps1) and re-point it if the runtime moved."
        )
    if any(marker in text for marker in _HYDRATION_MARKERS):
        return (
            "The runtime answered, but could not hydrate its own environment from SSM. This is #92 "
            "defect 2 verbatim: the execution role cannot read /setuhaul/*. The grant now lives in "
            "agentcore/cdk/lib/cdk-stack.ts (SetuHaulSsmHydrateRead) -- confirm this deploy carried "
            "it rather than re-attaching a policy by hand, which is what caused the incident."
        )
    return None


def invoke_smoke(*, runtime_arn: str, region: str | None, payload_path: Path) -> bool:
    """Invoke the deployed runtime once, with the DEPLOYER's credentials, and judge the answer.

    Deliberately does not go through the BFF: this must be runnable at deploy time, from the deploy
    machine, with nothing else running. The tradeoff is stated honestly rather than glossed -- a
    PASS here proves the RUNTIME is healthy (it booted, hydrated SSM, reached Postgres and the LLM,
    and served a turn), which is #92 defect 2. It does NOT prove the BFF's task role may invoke it,
    because the deployer's credentials are not the BFF's; defect 1 is covered separately by
    check_bff_invoke_grant() below.

    Uses the `aws` CLI rather than boto3 for the same reason read_runtime_version() does: this
    machine's AWS login flow needs `botocore[crt]` for boto3's credential provider, which the CLI
    does not require. Keeping both on the CLI keeps the wrapper working on the machine that
    actually runs deploys.
    """
    if not payload_path.is_file():
        print(f"[smoke] payload not found at {payload_path} -- cannot smoke-test.")
        return False

    # Prefer the region encoded in the ARN over the deploy target's, mirroring the BFF's own
    # _region_from_arn(). They agree in normal operation, but "queried the wrong region and got a
    # useless answer" is a bug this exact file has already shipped once (see read_runtime_version's
    # docstring), and during a partial region migration a stale deployed-state.json is precisely
    # how they come apart. The ARN is the more specific fact, so it wins.
    arn_parts = runtime_arn.split(":")
    arn_region = arn_parts[3] if len(arn_parts) >= 4 and arn_parts[3] else None
    if arn_region and region and arn_region != region:
        print(
            f"[smoke] NOTE: deploy target region is {region!r} but the runtime ARN is in "
            f"{arn_region!r}; invoking in {arn_region!r} (the ARN wins). Worth investigating -- "
            "these should not disagree outside a region migration."
        )
    region = arn_region or region

    with tempfile.TemporaryDirectory() as tmp:
        outfile = Path(tmp) / "invoke-response.json"
        args = [
            "aws",
            "bedrock-agentcore",
            "invoke-agent-runtime",
            "--agent-runtime-arn",
            runtime_arn,
            "--runtime-session-id",
            _smoke_session_id(),
            "--qualifier",
            # The BFF invokes with qualifier=DEFAULT (agentcore_runtime.py). Smoking a different
            # endpoint than production uses would prove the wrong thing.
            "DEFAULT",
            "--content-type",
            "application/json",
            "--accept",
            "application/json",
            # fileb:// sends the file's bytes verbatim, matching the BFF's
            # json.dumps(payload).encode("utf-8"). Plain file:// would be subject to the CLI's
            # base64 blob handling and arrive mangled.
            "--payload",
            f"fileb://{payload_path}",
        ]
        if region:
            args += ["--region", region]
        args.append(str(outfile))

        print(f"[smoke] invoking the deployed runtime once ({runtime_arn}) ...")
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            print(f"[smoke] invoke FAILED: {stderr[:800]}")
            classified = _classify_runtime_error(stderr)
            if classified:
                print(f"[smoke] {classified}")
            return False

        try:
            body = json.loads(outfile.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[smoke] invoke returned an unreadable body: {exc}")
            return False

    if not isinstance(body, dict):
        print(f"[smoke] FAILED -- expected a JSON object, got {type(body).__name__}.")
        return False

    if body.get("error"):
        message = str(body["error"])
        print(f"[smoke] the runtime answered with an ERROR: {message[:500]}")
        classified = _classify_runtime_error(message)
        if classified:
            print(f"[smoke] {classified}")
        return False

    tools = [t.get("name") for t in body.get("tool_calls") or [] if isinstance(t, dict)]
    response = str(body.get("response") or "")
    print(f"[smoke] OK -- runtime served a turn. tools={tools or '[]'}")
    print(f"[smoke] response (truncated): {response[:160]!r}")

    # A loud warning, not a failure. `memory_degraded` means the Redis half of hydration did not
    # land -- if the reason names a missing credential, that IS #92 defect 2 partially recurring
    # (the incident's own signature was a HALF-hydrated container). It is not a hard failure
    # because Redis can also degrade for reasons that have nothing to do with IAM, and failing a
    # deploy on a transient upstream blip would train people to pass --skip-invoke-smoke.
    if body.get("memory_degraded"):
        print(
            f"[smoke] WARNING: memory_degraded=True reason={body.get('memory_degrade_reason')!r}. "
            "If that names a missing/blank Redis credential, treat it as a partial SSM-hydration "
            "failure (#92 defect 2), not as normal degradation."
        )
    return True


def check_bff_invoke_grant(*, runtime_arn: str, role_name: str = BFF_TASK_ROLE_NAME) -> bool:
    """Read-only: does the ECS BFF task role still allow invoking THIS runtime ARN?

    This is the half invoke_smoke() structurally cannot cover. #92 defect 1 was not an unhealthy
    runtime -- the runtime was fine -- it was a grant still pointing at the retired us-east-1 ARN
    after E7.1 moved the runtime to ap-south-1. Nothing about deploying a healthy runtime detects
    that; only comparing the live grant against the ARN just deployed does.

    Three outcomes, deliberately distinct:
      * grant readable and names this ARN  -> pass
      * grant readable and does NOT        -> FAIL loudly (the exact 503 that was shipped once)
      * grant not readable at all          -> UNKNOWN, warn but do not fail. The deployer may
        legitimately lack iam:GetRolePolicy, or the session may have expired mid-run (#92's own
        note: `aws login` grants expired three times in one session). Reporting "unknown" honestly
        beats failing a good deploy or, worse, passing on an unread policy.
    """
    print(f"[smoke] checking {role_name}'s {BFF_INVOKE_POLICY_NAME} grant covers the deployed ARN ...")
    result = subprocess.run(
        [
            "aws", "iam", "get-role-policy",
            "--role-name", role_name,
            "--policy-name", BFF_INVOKE_POLICY_NAME,
            "--output", "json",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(
            "[smoke] BFF grant UNKNOWN -- could not read the role policy "
            f"({(result.stderr or '').strip()[:200]}). Nothing proven either way; verify by hand "
            "with deploy/README.md's verification command before trusting chat."
        )
        return True

    # Substring match on the whole document is intentional. The grant may list several ARNs (the
    # ap-south-1 runtime plus the us-east-1 rollback, plus optional /runtime-endpoint/DEFAULT
    # suffixes), and a structural walk would have to re-implement IAM policy evaluation to do
    # better. "Is the ARN we just deployed mentioned at all?" is the question that actually
    # separates the incident state from the healthy state.
    if runtime_arn not in result.stdout:
        print(
            f"[smoke] FAILED -- {role_name}'s {BFF_INVOKE_POLICY_NAME} does not mention "
            f"{runtime_arn}. This is #92 defect 1 recurring: the BFF will get AccessDeniedException "
            "on every invoke and chat will 503. Fix the checked-in artifact "
            "deploy/bff-task-role-invoke-policy.json and apply it with "
            "deploy/apply_bff_invoke_policy.sh -- do not hand-edit the policy in the console."
        )
        return False

    print("[smoke] OK -- the BFF task role's grant covers the deployed runtime ARN.")
    return True


def post_deploy_smoke(*, runtime_arn: str | None, region: str | None) -> bool:
    """Both post-deploy checks, in the order that gives the most useful failure first."""
    if not runtime_arn:
        print(
            "[smoke] SKIPPED -- no runtimeArn in agentcore/.cli/deployed-state.json, so there is "
            "nothing to invoke. Treated as UNKNOWN, not as a pass; run `agentcore status`."
        )
        return True
    runtime_ok = invoke_smoke(
        runtime_arn=runtime_arn, region=region, payload_path=INVOKE_SMOKE_PAYLOAD_PATH
    )
    # Run the grant check even when the invoke failed: if both are broken (which is exactly what
    # 2026-09-01 looked like), one run should report both, not make the operator deploy twice.
    grant_ok = check_bff_invoke_grant(runtime_arn=runtime_arn)
    return runtime_ok and grant_ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Pass --dry-run through to agentcore deploy.")
    parser.add_argument(
        "--skip-local-verify", action="store_true",
        help="Skip `agentcore package` before deploying. Not recommended.",
    )
    parser.add_argument(
        "--skip-invoke-smoke", action="store_true",
        help=(
            "Skip the post-deploy InvokeAgentRuntime smoke (issue #92). NEVER acceptable as a "
            "routine habit -- this check is the only thing in the pipeline that proves the thing "
            "you just deployed can actually serve a request. Legitimate uses are narrow: the "
            "deploy machine has no data-plane invoke permission; the runtime is deliberately "
            "being deployed ahead of a database/secret it does not have yet; or you are "
            "re-running only to re-stage an artifact and will smoke it separately. If you skip "
            "it, you own verifying chat by hand before calling the deploy done."
        ),
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

    if args.skip_invoke_smoke:
        print(
            "[smoke] SKIPPED (--skip-invoke-smoke). Nothing has proven this deploy can serve a "
            "request -- verify chat by hand before calling it done."
        )
        return 0

    if not post_deploy_smoke(runtime_arn=read_runtime_arn(), region=region):
        # The deploy already happened; this exit code is a post-deploy verdict, not a rollback.
        # Say so plainly, because the natural reading of "DEPLOY ... FAILED" is "nothing shipped".
        print(
            "\nPOST-DEPLOY SMOKE FAILED. The new version IS deployed -- this is not a rollback and "
            "nothing was undone. It is the check that 2026-09-01 did not have: the runtime shipped "
            "fine and could not serve a single request. Fix the grant in its checked-in artifact "
            "(agentcore/cdk/lib/cdk-stack.ts for the runtime's SSM read, "
            "deploy/bff-task-role-invoke-policy.json for the BFF's invoke) and re-run this wrapper. "
            "Do not hand-patch the live role -- that is what created #92."
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
