"""Stage backend/app into agentcore/codezip without .venv. Never copies secrets."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC_APP = ROOT / "backend" / "app"
DST = ROOT / "agentcore" / "codezip"
SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def main() -> int:
    if not SRC_APP.is_dir():
        print("missing backend/app")
        return 1
    if DST.exists():
        shutil.rmtree(DST)
    dst_app = DST / "app"

    def ignore(directory: str, names: list[str]) -> list[str]:
        dropped = [name for name in names if name in SKIP_DIRS or name.endswith(".pyc")]
        return dropped

    shutil.copytree(SRC_APP, dst_app, ignore=ignore)
    req = (ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")
    extra = "bedrock-agentcore>=0.1.0\naws-opentelemetry-distro>=0.10.0\nopentelemetry-instrumentation-langchain>=0.40.0\n"
    (DST / "requirements.txt").write_text(req + extra, encoding="utf-8")
    # AgentCore CDK CodeZip requires pyproject.toml at the codeLocation root (ERICA layout).
    pyproject = ROOT / "backend" / "pyproject.agentcore.toml"
    if not pyproject.is_file():
        print("missing backend/pyproject.agentcore.toml")
        return 1
    shutil.copy2(pyproject, DST / "pyproject.toml")
    print(
        "staged",
        DST.as_posix(),
        "app_files",
        sum(1 for _ in dst_app.rglob("*") if _.is_file()),
        "pyproject",
        True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
