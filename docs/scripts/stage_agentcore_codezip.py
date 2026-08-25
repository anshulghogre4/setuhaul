"""Stage backend/app into agentcore/codezip without .venv. Never copies secrets.

E4.2 (issue #32): requirements.txt and pyproject.toml for the codezip artifact used to be
hand-maintained duplicates of backend/pyproject.toml's dependency list -- they had already
drifted from each other and from the source of truth before this fix (different langchain/redis
pins). Both are now generated here from backend/pyproject.toml directly, so a dependency bump in
one place can no longer silently fail to reach the deployed artifact.
"""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_APP = ROOT / "backend" / "app"
BACKEND_PYPROJECT = ROOT / "backend" / "pyproject.toml"
DST = ROOT / "agentcore" / "codezip"
SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}

# Present in backend/pyproject.toml's runtime dependencies but not wanted in the deployed
# AgentCore artifact (test-only).
EXCLUDE_FROM_AGENTCORE = {"pytest-asyncio"}

# AgentCore needs these; the ECS/local backend does not (tracing/runtime SDK specific to the
# AgentCore Runtime host itself, not the application code both targets share).
AGENTCORE_ONLY_EXTRA_DEPS = [
    "bedrock-agentcore>=0.1.0",
    "langsmith",
    "aws-opentelemetry-distro>=0.18.0",
    "opentelemetry-instrumentation-langchain>=0.40.0",
]

# Static AgentCore packaging metadata (CodeZip/ERICA layout requires pyproject.toml at the
# codeLocation root). Rarely changes, unlike dependency pins, so it stays a template here rather
# than a fourth file to keep in sync.
_PYPROJECT_TEMPLATE = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "setuhaul-agentcore"
version = "0.1.0"
description = "SetuHaul AgentCore CodeZip -- same run_assistant, no second agent tree"
requires-python = ">=3.12,<3.13"
dependencies = [
{deps}
]

[tool.uv]
package = false

[tool.hatch.build.targets.wheel]
packages = ["app"]
"""


def _package_name(spec: str) -> str:
    for sep in ("[", ">=", "==", "<", ">", "~="):
        idx = spec.find(sep)
        if idx != -1:
            return spec[:idx].strip()
    return spec.strip()


def agentcore_dependencies() -> list[str]:
    """The single source of truth for what the deployed AgentCore artifact requires."""
    data = tomllib.loads(BACKEND_PYPROJECT.read_text(encoding="utf-8"))
    main_deps: list[str] = data["project"]["dependencies"]
    filtered = [d for d in main_deps if _package_name(d) not in EXCLUDE_FROM_AGENTCORE]
    return filtered + AGENTCORE_ONLY_EXTRA_DEPS


def render_requirements_txt(deps: list[str]) -> str:
    return "\n".join(deps) + "\n"


def render_pyproject_toml(deps: list[str]) -> str:
    deps_block = "\n".join(f'  "{d}",' for d in deps)
    return _PYPROJECT_TEMPLATE.format(deps=deps_block)


def main() -> int:
    if not SRC_APP.is_dir():
        print("missing backend/app")
        return 1
    if not BACKEND_PYPROJECT.is_file():
        print("missing backend/pyproject.toml")
        return 1
    if DST.exists():
        shutil.rmtree(DST)
    dst_app = DST / "app"

    def ignore(directory: str, names: list[str]) -> list[str]:
        dropped = [name for name in names if name in SKIP_DIRS or name.endswith(".pyc")]
        return dropped

    shutil.copytree(SRC_APP, dst_app, ignore=ignore)

    deps = agentcore_dependencies()
    (DST / "requirements.txt").write_text(render_requirements_txt(deps), encoding="utf-8")
    (DST / "pyproject.toml").write_text(render_pyproject_toml(deps), encoding="utf-8")

    print(
        "staged",
        DST.as_posix(),
        "app_files",
        sum(1 for _ in dst_app.rglob("*") if _.is_file()),
        "deps",
        len(deps),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
