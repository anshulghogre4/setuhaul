"""E4.2 (issue #32): the AgentCore codezip artifact's dependency manifests must be generated
from backend/pyproject.toml, not hand-maintained duplicates -- that duplication is exactly what
let the deployed artifact silently drift from the real dependency set (issue #31's
langchain-google-genai pin never reaching agentcore/codezip/requirements.txt is the concrete
incident this guards against)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "docs" / "scripts" / "stage_agentcore_codezip.py"

_spec = importlib.util.spec_from_file_location("stage_agentcore_codezip", SCRIPT_PATH)
stage = importlib.util.module_from_spec(_spec)
sys.modules["stage_agentcore_codezip"] = stage
_spec.loader.exec_module(stage)


def test_agentcore_dependencies_reflects_the_real_pyproject_toml():
    deps = stage.agentcore_dependencies()
    joined = "\n".join(deps)
    # The exact regression this guards: the old hand-maintained files kept the pre-E4.1 pin.
    assert "langchain-google-genai>=4.0.0,<5.0.0" in deps
    assert "langchain-google-genai>=2.0.0,<3.0.0" not in joined
    assert "redis>=5.0.0,<6.0.0" in deps


def test_agentcore_dependencies_excludes_test_only_packages():
    deps = stage.agentcore_dependencies()
    assert not any(stage._package_name(d) == "pytest-asyncio" for d in deps)


def test_agentcore_dependencies_includes_agentcore_only_extras():
    deps = stage.agentcore_dependencies()
    for extra in stage.AGENTCORE_ONLY_EXTRA_DEPS:
        assert extra in deps


def test_requirements_txt_and_pyproject_toml_share_one_dependency_list():
    """The two generated files can no longer drift from each other -- same input, same order."""
    deps = stage.agentcore_dependencies()
    req_txt = stage.render_requirements_txt(deps)
    pyproject = stage.render_pyproject_toml(deps)
    for dep in deps:
        assert dep in req_txt
        assert f'"{dep}",' in pyproject


def test_main_stages_a_fresh_codezip_with_correct_deps(tmp_path, monkeypatch):
    fake_dst = tmp_path / "codezip"
    monkeypatch.setattr(stage, "DST", fake_dst)

    exit_code = stage.main()

    assert exit_code == 0
    assert (fake_dst / "app").is_dir()
    assert (fake_dst / "app" / "main.py").is_file()
    req_txt = (fake_dst / "requirements.txt").read_text(encoding="utf-8")
    assert "langchain-google-genai>=4.0.0,<5.0.0" in req_txt
    pyproject_toml = (fake_dst / "pyproject.toml").read_text(encoding="utf-8")
    assert "langchain-google-genai>=4.0.0,<5.0.0" in pyproject_toml
    assert "bedrock-agentcore>=0.1.0" in pyproject_toml


def test_main_excludes_pycache_and_venv_dirs(tmp_path, monkeypatch):
    fake_dst = tmp_path / "codezip"
    monkeypatch.setattr(stage, "DST", fake_dst)

    stage.main()

    staged_dir_names = {p.name for p in fake_dst.rglob("*") if p.is_dir()}
    assert "__pycache__" not in staged_dir_names
    assert ".venv" not in staged_dir_names
