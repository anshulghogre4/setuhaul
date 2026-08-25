"""E4.2 (issue #32): the atomic deploy wrapper must not be able to reach `agentcore deploy`
without staging succeeding first, and must not silently accept an unchanged agentRuntimeVersion
as success on a real (non-dry-run) deploy."""

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
    monkeypatch.setattr(sys, "argv", ["agentcore_deploy.py", "--skip-local-verify"])

    exit_code = deploy_mod.main()

    assert exit_code == 0
    assert verify_called == []


def test_main_warns_when_runtime_version_is_unchanged_after_a_real_deploy(monkeypatch, capsys):
    monkeypatch.setattr(deploy_mod.stage, "main", lambda: 0)
    monkeypatch.setattr(deploy_mod, "local_verify", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "deploy", lambda **kw: True)
    monkeypatch.setattr(deploy_mod, "read_runtime_id", lambda **kw: "runtime-1")
    monkeypatch.setattr(deploy_mod, "read_runtime_version", lambda runtime_id: "9")
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
    monkeypatch.setattr(deploy_mod, "read_runtime_version", lambda runtime_id: next(versions))
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
