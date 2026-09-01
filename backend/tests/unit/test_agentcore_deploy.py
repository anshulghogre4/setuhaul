"""E4.2 (issue #32): the atomic deploy wrapper must not be able to reach `agentcore deploy`
without staging succeeding first, and must not silently accept an unchanged agentRuntimeVersion
as success on a real (non-dry-run) deploy.

Issue #92 adds the post-deploy smoke to the same file: the wrapper must actually invoke what it
just deployed and FAIL on an AccessDenied/hydration answer, because on 2026-09-01 every check
above passed while chat was down for every user.

Every `main()` test below stubs `post_deploy_smoke` -- not for convenience, but because leaving it
unstubbed would make the unit suite shell out to `aws bedrock-agentcore invoke-agent-runtime`
against the real deployed runtime. That would be a live network call inside a unit test, and
(worse) a real assistant turn against production. The smoke's own behaviour is tested directly,
with subprocess stubbed, further down.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "docs" / "scripts" / "agentcore_deploy.py"

_spec = importlib.util.spec_from_file_location("agentcore_deploy", SCRIPT_PATH)
deploy_mod = importlib.util.module_from_spec(_spec)
sys.modules["agentcore_deploy"] = deploy_mod
_spec.loader.exec_module(deploy_mod)


# Real shape confirmed directly against `agentcore/.cli/deployed-state.json` and
# `agentcore status --json` output (not guessed): runtimeId is nested inside
# targets.<target>.resources.runtimes.<runtime>; a deployHash field also exists as a *sibling*
# of `runtimes` under `resources` -- see read_runtime_version's own docstring for why that field
# turned out unreliable and is not used here.
_REAL_SHAPE = {
    "targets": {
        "default": {
            "resources": {
                "runtimes": {
                    "SetuHaulAgent": {
                        "runtimeId": "SetuHaulAgent_SetuHaulAgent-18B4pX4XF1",
                        "runtimeArn": "arn:aws:bedrock-agentcore:us-east-1:118490268011:runtime/SetuHaulAgent_SetuHaulAgent-18B4pX4XF1",
                        "roleArn": "arn:aws:iam::118490268011:role/example",
                    }
                },
                "stackName": "AgentCore-SetuHaulAgent-default",
                "deployHash": "b65fea3b9abe341b",
            }
        }
    }
}


def test_read_runtime_id_parses_the_real_shape(tmp_path, monkeypatch):
    path = tmp_path / "deployed-state.json"
    path.write_text(json.dumps(_REAL_SHAPE), encoding="utf-8")
    monkeypatch.setattr(deploy_mod, "DEPLOYED_STATE_PATH", path)

    assert deploy_mod.read_runtime_id() == "SetuHaulAgent_SetuHaulAgent-18B4pX4XF1"


def test_read_runtime_id_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_mod, "DEPLOYED_STATE_PATH", tmp_path / "missing.json")
    assert deploy_mod.read_runtime_id() is None


def test_read_runtime_id_returns_none_on_unexpected_shape(tmp_path, monkeypatch):
    path = tmp_path / "deployed-state.json"
    path.write_text(json.dumps({"targets": {}}), encoding="utf-8")
    monkeypatch.setattr(deploy_mod, "DEPLOYED_STATE_PATH", path)
    assert deploy_mod.read_runtime_id() is None


def test_read_runtime_version_parses_aws_cli_json(monkeypatch):
    monkeypatch.setattr(
        deploy_mod.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps({"agentRuntimeVersion": "10"})),
    )
    assert deploy_mod.read_runtime_version("some-id") == "10"


def test_read_runtime_version_passes_region_when_given(monkeypatch):
    captured = {}

    def fake_run(args, **kw):
        captured["args"] = args
        return SimpleNamespace(returncode=0, stdout=json.dumps({"agentRuntimeVersion": "1"}))

    monkeypatch.setattr(deploy_mod.subprocess, "run", fake_run)
    deploy_mod.read_runtime_version("some-id", region="ap-south-1")

    assert "--region" in captured["args"]
    assert "ap-south-1" in captured["args"]


def test_read_runtime_version_omits_region_when_not_given(monkeypatch):
    captured = {}

    def fake_run(args, **kw):
        captured["args"] = args
        return SimpleNamespace(returncode=0, stdout=json.dumps({"agentRuntimeVersion": "1"}))

    monkeypatch.setattr(deploy_mod.subprocess, "run", fake_run)
    deploy_mod.read_runtime_version("some-id")

    assert "--region" not in captured["args"]


def test_read_target_region_parses_the_real_shape(tmp_path, monkeypatch):
    path = tmp_path / "aws-targets.json"
    path.write_text(json.dumps([{"name": "default", "account": "123", "region": "ap-south-1"}]), encoding="utf-8")
    monkeypatch.setattr(deploy_mod, "AWS_TARGETS_PATH", path)

    assert deploy_mod.read_target_region() == "ap-south-1"


def test_read_target_region_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_mod, "AWS_TARGETS_PATH", tmp_path / "missing.json")
    assert deploy_mod.read_target_region() is None


def test_read_target_region_returns_none_when_target_not_found(tmp_path, monkeypatch):
    path = tmp_path / "aws-targets.json"
    path.write_text(json.dumps([{"name": "other", "region": "us-east-1"}]), encoding="utf-8")
    monkeypatch.setattr(deploy_mod, "AWS_TARGETS_PATH", path)

    assert deploy_mod.read_target_region(target="default") is None


def test_read_runtime_version_returns_none_on_cli_failure(monkeypatch):
    monkeypatch.setattr(
        deploy_mod.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=1, stdout=""),
    )
    assert deploy_mod.read_runtime_version("some-id") is None


def test_local_verify_runs_tests_before_packaging_and_short_circuits_on_test_failure(monkeypatch):
    package_called = []
    monkeypatch.setattr(deploy_mod, "run_backend_tests", lambda: False)
    monkeypatch.setattr(
        deploy_mod, "_run", lambda *a, **kw: package_called.append(1) or SimpleNamespace(returncode=0, stdout="", stderr="")
    )

    ok = deploy_mod.local_verify(agentcore_cmd="agentcore")

    assert ok is False
    assert package_called == []


def test_local_verify_packages_only_after_tests_pass(monkeypatch):
    monkeypatch.setattr(deploy_mod, "run_backend_tests", lambda: True)
    monkeypatch.setattr(
        deploy_mod, "_run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout="", stderr="")
    )

    ok = deploy_mod.local_verify(agentcore_cmd="agentcore")

    assert ok is True


def test_main_aborts_before_any_agentcore_call_when_staging_fails(monkeypatch, capsys):
    monkeypatch.setattr(deploy_mod.stage, "main", lambda: 1)
    called = []
    monkeypatch.setattr(deploy_mod, "local_verify", lambda **kw: called.append("verify") or True)
    monkeypatch.setattr(deploy_mod, "deploy", lambda **kw: called.append("deploy") or True)
    monkeypatch.setattr(sys, "argv", ["agentcore_deploy.py"])

    exit_code = deploy_mod.main()

    assert exit_code == 1
    assert called == []
    assert "STAGING FAILED" in capsys.readouterr().out


def test_main_aborts_before_deploy_when_local_verify_fails(monkeypatch, capsys):
    monkeypatch.setattr(deploy_mod.stage, "main", lambda: 0)
    monkeypatch.setattr(deploy_mod, "local_verify", lambda **kw: False)
    deploy_called = []
    monkeypatch.setattr(deploy_mod, "deploy", lambda **kw: deploy_called.append(1) or True)
    monkeypatch.setattr(sys, "argv", ["agentcore_deploy.py"])

    exit_code = deploy_mod.main()

    assert exit_code == 1
    assert deploy_called == []
    assert "LOCAL VERIFY FAILED" in capsys.readouterr().out


def test_main_skips_local_verify_only_when_explicitly_flagged(monkeypatch):
    monkeypatch.setattr(deploy_mod.stage, "main", lambda: 0)
    verify_called = []
    monkeypatch.setattr(deploy_mod, "local_verify", lambda **kw: verify_called.append(1) or True)
    monkeypatch.setattr(deploy_mod, "deploy", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "read_runtime_id", lambda **kw: None)
    monkeypatch.setattr(deploy_mod, "post_deploy_smoke", lambda **kw: True)
    monkeypatch.setattr(sys, "argv", ["agentcore_deploy.py", "--skip-local-verify"])

    exit_code = deploy_mod.main()

    assert exit_code == 0
    assert verify_called == []


def test_main_warns_when_runtime_version_is_unchanged_after_a_real_deploy(monkeypatch, capsys):
    monkeypatch.setattr(deploy_mod.stage, "main", lambda: 0)
    monkeypatch.setattr(deploy_mod, "local_verify", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "deploy", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "read_runtime_id", lambda **kw: "runtime-1")
    monkeypatch.setattr(deploy_mod, "read_runtime_version", lambda runtime_id, **kw: "9")
    monkeypatch.setattr(deploy_mod, "post_deploy_smoke", lambda **kw: True)
    monkeypatch.setattr(sys, "argv", ["agentcore_deploy.py"])

    exit_code = deploy_mod.main()

    assert exit_code == 0
    assert "WARNING: agentRuntimeVersion did not change" in capsys.readouterr().out


def test_main_does_not_warn_when_runtime_version_changes(monkeypatch, capsys):
    monkeypatch.setattr(deploy_mod.stage, "main", lambda: 0)
    monkeypatch.setattr(deploy_mod, "local_verify", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "deploy", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "read_runtime_id", lambda **kw: "runtime-1")
    versions = iter(["9", "10"])
    monkeypatch.setattr(deploy_mod, "read_runtime_version", lambda runtime_id, **kw: next(versions))
    monkeypatch.setattr(deploy_mod, "post_deploy_smoke", lambda **kw: True)
    monkeypatch.setattr(sys, "argv", ["agentcore_deploy.py"])

    exit_code = deploy_mod.main()

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "WARNING: agentRuntimeVersion did not change" not in out
    assert "agentRuntimeVersion changed (9 -> 10)" in out


def test_main_reports_unknown_when_version_cannot_be_read(monkeypatch, capsys):
    monkeypatch.setattr(deploy_mod.stage, "main", lambda: 0)
    monkeypatch.setattr(deploy_mod, "local_verify", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "deploy", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "read_runtime_id", lambda **kw: None)
    monkeypatch.setattr(deploy_mod, "post_deploy_smoke", lambda **kw: True)
    monkeypatch.setattr(sys, "argv", ["agentcore_deploy.py"])

    exit_code = deploy_mod.main()

    assert exit_code == 0
    assert "[confirm] UNKNOWN" in capsys.readouterr().out


def test_main_skips_version_check_on_dry_run(monkeypatch, capsys):
    monkeypatch.setattr(deploy_mod.stage, "main", lambda: 0)
    monkeypatch.setattr(deploy_mod, "local_verify", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "deploy", lambda **kw: True)
    id_calls = []
    monkeypatch.setattr(deploy_mod, "read_runtime_id", lambda **kw: id_calls.append(1) or "x")
    monkeypatch.setattr(sys, "argv", ["agentcore_deploy.py", "--dry-run"])

    exit_code = deploy_mod.main()

    assert exit_code == 0
    assert id_calls == []
    assert "Dry run complete" in capsys.readouterr().out


def test_main_returns_failure_when_deploy_itself_fails(monkeypatch, capsys):
    monkeypatch.setattr(deploy_mod.stage, "main", lambda: 0)
    monkeypatch.setattr(deploy_mod, "local_verify", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "deploy", lambda **kw: False)
    monkeypatch.setattr(sys, "argv", ["agentcore_deploy.py"])

    exit_code = deploy_mod.main()

    assert exit_code == 1
    assert "DEPLOY FAILED" in capsys.readouterr().out


# ---------------------------------------------------------------------------------------------
# Issue #92: the post-deploy invoke smoke.
#
# What these lock down is narrow and deliberate: the wrapper must (a) build an invoke call that
# actually matches how the BFF invokes the same runtime, (b) refuse to call an error answer a
# success, and (c) name the incident class rather than dumping a raw string. The 2026-09-01
# outage was two IAM defects that every existing check above sailed past.
# ---------------------------------------------------------------------------------------------

_LIVE_ARN = "arn:aws:bedrock-agentcore:ap-south-1:118490268011:runtime/SetuHaulAgent_SetuHaulAgent-E9mrbf5VGD"
_RETIRED_ARN = "arn:aws:bedrock-agentcore:us-east-1:118490268011:runtime/SetuHaulAgent_SetuHaulAgent-18B4pX4XF1"


def test_read_runtime_arn_parses_the_real_shape(tmp_path, monkeypatch):
    path = tmp_path / "deployed-state.json"
    path.write_text(json.dumps(_REAL_SHAPE), encoding="utf-8")
    monkeypatch.setattr(deploy_mod, "DEPLOYED_STATE_PATH", path)

    assert deploy_mod.read_runtime_arn() == _RETIRED_ARN


def test_read_runtime_arn_returns_none_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(deploy_mod, "DEPLOYED_STATE_PATH", tmp_path / "missing.json")
    assert deploy_mod.read_runtime_arn() is None


def test_smoke_session_id_meets_the_aws_minimum_and_is_unique():
    # AWS constrains runtimeSessionId to 33-256 chars; a warm-container reuse would also make the
    # smoke prove nothing, so uniqueness is part of the contract, not incidental.
    first, second = deploy_mod._smoke_session_id(), deploy_mod._smoke_session_id()
    assert 33 <= len(first) <= 256
    assert first != second


def _fake_invoke(*, returncode=0, stderr="", body=None):
    """Stand in for `aws bedrock-agentcore invoke-agent-runtime`, writing the outfile it is asked
    to write -- the response goes to a positional outfile, not to stdout."""
    captured = {}

    def fake_run(args, **kw):
        captured["args"] = args
        if body is not None:
            Path(args[-1]).write_text(json.dumps(body), encoding="utf-8")
        return SimpleNamespace(returncode=returncode, stdout="", stderr=stderr)

    return fake_run, captured


def test_invoke_smoke_mirrors_the_bff_call_shape(monkeypatch, tmp_path):
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"message": "hi"}), encoding="utf-8")
    fake_run, captured = _fake_invoke(body={"response": "ok", "tool_calls": []})
    monkeypatch.setattr(deploy_mod.subprocess, "run", fake_run)

    assert deploy_mod.invoke_smoke(runtime_arn=_LIVE_ARN, region="ap-south-1", payload_path=payload) is True

    args = captured["args"]
    assert args[:3] == ["aws", "bedrock-agentcore", "invoke-agent-runtime"]
    assert _LIVE_ARN in args
    # qualifier DEFAULT: smoking a different endpoint than production uses would prove the wrong
    # thing -- agentcore_runtime.py invokes with qualifier="DEFAULT".
    assert args[args.index("--qualifier") + 1] == "DEFAULT"
    # fileb:// sends bytes verbatim, matching the BFF's json.dumps(...).encode("utf-8").
    assert args[args.index("--payload") + 1].startswith("fileb://")
    assert args[args.index("--region") + 1] == "ap-south-1"
    assert len(args[args.index("--runtime-session-id") + 1]) >= 33


def test_invoke_smoke_fails_and_names_the_hydration_defect(monkeypatch, tmp_path, capsys):
    payload = tmp_path / "payload.json"
    payload.write_text("{}", encoding="utf-8")
    fake_run, _ = _fake_invoke(body={"error": "Database is not configured on the Runtime."})
    monkeypatch.setattr(deploy_mod.subprocess, "run", fake_run)

    assert deploy_mod.invoke_smoke(runtime_arn=_LIVE_ARN, region=None, payload_path=payload) is False

    out = capsys.readouterr().out
    assert "defect 2" in out
    assert "cdk-stack.ts" in out


def test_invoke_smoke_fails_and_names_the_access_denied_defect(monkeypatch, tmp_path, capsys):
    payload = tmp_path / "payload.json"
    payload.write_text("{}", encoding="utf-8")
    fake_run, _ = _fake_invoke(returncode=255, stderr="AccessDeniedException when calling InvokeAgentRuntime")
    monkeypatch.setattr(deploy_mod.subprocess, "run", fake_run)

    assert deploy_mod.invoke_smoke(runtime_arn=_LIVE_ARN, region=None, payload_path=payload) is False

    out = capsys.readouterr().out
    assert "defect 1" in out
    assert "bff-task-role-invoke-policy.json" in out


def test_invoke_smoke_warns_but_passes_on_degraded_memory(monkeypatch, tmp_path, capsys):
    # A half-hydrated container is the incident's own signature, so it must be visible -- but Redis
    # also degrades for reasons unrelated to IAM, and a false deploy failure trains people to skip.
    payload = tmp_path / "payload.json"
    payload.write_text("{}", encoding="utf-8")
    fake_run, _ = _fake_invoke(
        body={
            "response": "ok",
            "tool_calls": [],
            "memory_degraded": True,
            "memory_degrade_reason": "no token",
        }
    )
    monkeypatch.setattr(deploy_mod.subprocess, "run", fake_run)

    assert deploy_mod.invoke_smoke(runtime_arn=_LIVE_ARN, region=None, payload_path=payload) is True
    assert "memory_degraded=True" in capsys.readouterr().out


def test_invoke_smoke_fails_when_the_payload_is_missing(tmp_path, capsys):
    missing = tmp_path / "nope.json"
    assert deploy_mod.invoke_smoke(runtime_arn=_LIVE_ARN, region=None, payload_path=missing) is False
    assert "payload not found" in capsys.readouterr().out


def test_bff_grant_check_fails_when_the_deployed_arn_is_absent(monkeypatch, capsys):
    # The literal 2026-09-01 defect 1: a healthy runtime, and a grant still naming the retired one.
    stale = json.dumps({"PolicyDocument": {"Statement": [{"Resource": _RETIRED_ARN}]}})
    monkeypatch.setattr(
        deploy_mod.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=stale, stderr=""),
    )

    assert deploy_mod.check_bff_invoke_grant(runtime_arn=_LIVE_ARN) is False
    assert "defect 1 recurring" in capsys.readouterr().out


def test_bff_grant_check_passes_when_the_deployed_arn_is_present(monkeypatch):
    current = json.dumps({"PolicyDocument": {"Statement": [{"Resource": [_LIVE_ARN, _RETIRED_ARN]}]}})
    monkeypatch.setattr(
        deploy_mod.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=current, stderr=""),
    )

    assert deploy_mod.check_bff_invoke_grant(runtime_arn=_LIVE_ARN) is True


def test_bff_grant_check_reports_unknown_rather_than_failing_when_unreadable(monkeypatch, capsys):
    # The deployer may lack iam:GetRolePolicy, or the login may have expired mid-run (#92's own
    # operational note: three expiries in one session). "Unknown" is the honest answer; failing an
    # otherwise good deploy on a permissions gap in the CHECKER is not.
    monkeypatch.setattr(
        deploy_mod.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=254, stdout="", stderr="ExpiredToken"),
    )

    assert deploy_mod.check_bff_invoke_grant(runtime_arn=_LIVE_ARN) is True
    assert "UNKNOWN" in capsys.readouterr().out


def test_post_deploy_smoke_reports_both_halves_even_when_the_invoke_fails(monkeypatch):
    # One run should surface both defects; 2026-09-01 had both at once and took two round trips.
    calls = []
    monkeypatch.setattr(deploy_mod, "invoke_smoke", lambda **kw: calls.append("invoke") or False)
    monkeypatch.setattr(deploy_mod, "check_bff_invoke_grant", lambda **kw: calls.append("grant") or True)

    assert deploy_mod.post_deploy_smoke(runtime_arn=_LIVE_ARN, region="ap-south-1") is False
    assert calls == ["invoke", "grant"]


def test_main_fails_the_run_when_the_smoke_fails_and_says_nothing_was_rolled_back(monkeypatch, capsys):
    monkeypatch.setattr(deploy_mod.stage, "main", lambda: 0)
    monkeypatch.setattr(deploy_mod, "local_verify", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "deploy", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "read_runtime_id", lambda **kw: "runtime-1")
    versions = iter(["9", "10"])
    monkeypatch.setattr(deploy_mod, "read_runtime_version", lambda runtime_id, **kw: next(versions))
    monkeypatch.setattr(deploy_mod, "read_runtime_arn", lambda **kw: _LIVE_ARN)
    monkeypatch.setattr(deploy_mod, "post_deploy_smoke", lambda **kw: False)
    monkeypatch.setattr(sys, "argv", ["agentcore_deploy.py"])

    exit_code = deploy_mod.main()

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "POST-DEPLOY SMOKE FAILED" in out
    assert "not a rollback" in out


def test_main_runs_the_smoke_by_default_after_a_real_deploy(monkeypatch):
    seen = {}
    monkeypatch.setattr(deploy_mod.stage, "main", lambda: 0)
    monkeypatch.setattr(deploy_mod, "local_verify", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "deploy", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "read_runtime_id", lambda **kw: "runtime-1")
    monkeypatch.setattr(deploy_mod, "read_runtime_version", lambda runtime_id, **kw: "9")
    monkeypatch.setattr(deploy_mod, "read_target_region", lambda **kw: "ap-south-1")
    monkeypatch.setattr(deploy_mod, "read_runtime_arn", lambda **kw: _LIVE_ARN)
    monkeypatch.setattr(deploy_mod, "post_deploy_smoke", lambda **kw: seen.update(kw) or True)
    monkeypatch.setattr(sys, "argv", ["agentcore_deploy.py"])

    assert deploy_mod.main() == 0
    assert seen == {"runtime_arn": _LIVE_ARN, "region": "ap-south-1"}


def test_main_skips_the_smoke_only_when_explicitly_flagged(monkeypatch, capsys):
    smoke_called = []
    monkeypatch.setattr(deploy_mod.stage, "main", lambda: 0)
    monkeypatch.setattr(deploy_mod, "local_verify", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "deploy", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "read_runtime_id", lambda **kw: "runtime-1")
    monkeypatch.setattr(deploy_mod, "read_runtime_version", lambda runtime_id, **kw: "9")
    monkeypatch.setattr(deploy_mod, "post_deploy_smoke", lambda **kw: smoke_called.append(1) or True)
    monkeypatch.setattr(sys, "argv", ["agentcore_deploy.py", "--skip-invoke-smoke"])

    assert deploy_mod.main() == 0
    assert smoke_called == []
    assert "[smoke] SKIPPED" in capsys.readouterr().out


def test_main_does_not_smoke_on_a_dry_run(monkeypatch):
    smoke_called = []
    monkeypatch.setattr(deploy_mod.stage, "main", lambda: 0)
    monkeypatch.setattr(deploy_mod, "local_verify", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "deploy", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "post_deploy_smoke", lambda **kw: smoke_called.append(1) or True)
    monkeypatch.setattr(sys, "argv", ["agentcore_deploy.py", "--dry-run"])

    assert deploy_mod.main() == 0
    assert smoke_called == []


def test_invoke_smoke_prefers_the_arn_region_over_the_deploy_target_region(monkeypatch, tmp_path, capsys):
    """The wrapper has already shipped a 'queried the wrong region' bug once (read_runtime_version).
    A stale deployed-state.json during a region migration is exactly how the two disagree."""
    payload = tmp_path / "payload.json"
    payload.write_text("{}", encoding="utf-8")
    fake_run, captured = _fake_invoke(body={"response": "ok", "tool_calls": []})
    monkeypatch.setattr(deploy_mod.subprocess, "run", fake_run)

    assert deploy_mod.invoke_smoke(runtime_arn=_RETIRED_ARN, region="ap-south-1", payload_path=payload) is True

    args = captured["args"]
    assert args[args.index("--region") + 1] == "us-east-1"
    assert "the ARN wins" in capsys.readouterr().out
