"""Build a gitignored MCP file list for deploy_to_vercel. Never prints secrets."""

from __future__ import annotations

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
OUT = ROOT / "tmp" / "vercel-mcp-files.json"
ENV_SRC = FRONTEND / ".env.production.local"

TEXT_FILES = [
    "package.json",
    "index.html",
    "vite.config.ts",
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.node.json",
    "vercel.json",
    "src/main.tsx",
    "src/App.tsx",
    "src/App.css",
    "src/index.css",
    "src/core/http/api.ts",
    "src/core/auth/supabase.ts",
    "src/layouts/ProtectedLayout.tsx",
    "src/features/auth/LoginForm.tsx",
    "src/features/driver/DriverHome.tsx",
    "src/features/driver/DriverLayout.css",
    "src/features/operator/OpsHomes.tsx",
    "src/features/dispatch/DispatchHome.tsx",
    "public/favicon.svg",
    "public/icons.svg",
]

# 1x1 PNG so Vite can resolve the login hero imports without a 3.6MB MCP payload.
PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
PLACEHOLDER_PATHS = [
    "src/assets/setuhaul-driver-eta-hero.png",
    "src/assets/setuhaul-dock-command-hero.png",
]


def main() -> int:
    if not ENV_SRC.exists():
        print("missing frontend/.env.production.local")
        return 1
    files: list[dict[str, str]] = []
    for rel in TEXT_FILES:
        path = FRONTEND / rel
        if not path.exists():
            print("missing", rel)
            return 1
        files.append({"file": rel, "data": path.read_text(encoding="utf-8")})
    env_text = ENV_SRC.read_text(encoding="utf-8-sig")
    files.append({"file": ".env", "data": env_text})
    files.append({"file": ".env.production", "data": env_text})
    png_b64 = base64.b64encode(PLACEHOLDER_PNG).decode("ascii")
    for rel in PLACEHOLDER_PATHS:
        files.append({"file": rel, "data": png_b64, "encoding": "base64"})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"files": files}, ensure_ascii=False), encoding="utf-8")
    print("wrote", OUT.as_posix())
    print("file_count", len(files))
    print("payload_kb", round(OUT.stat().st_size / 1024, 1))
    print("has_env", any(item["file"] == ".env" for item in files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
