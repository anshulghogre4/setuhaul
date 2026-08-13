"""List recent LangSmith run names only. Never prints keys."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    vals: dict[str, str] = {}
    for name in (".env.local", ".env"):
        path = ROOT / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            vals[key.strip()] = value.strip().strip('"').strip("'")
    key = vals.get("LANGSMITH_API_KEY") or ""
    print("key_present", bool(key))
    if not key:
        return 0
    import os

    os.environ["LANGSMITH_API_KEY"] = key
    try:
        from langsmith import Client
    except Exception as exc:  # noqa: BLE001
        print("langsmith_import", type(exc).__name__)
        return 0
    client = Client()
    runs = list(client.list_runs(project_name="setuhaul-agentcore", limit=8))
    print("run_count", len(runs))
    for run in runs:
        print("run", getattr(run, "name", None), getattr(run, "status", None), str(getattr(run, "start_time", ""))[:19])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
