"""Write gitignored frontend/.env.production.local for the hosted Vite build.

Copies VITE_SUPABASE_* from frontend/.env.local and sets VITE_API_BASE_URL
to the Step 6 BFF URL. Never prints secret values.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / ".env.local"
DST = ROOT / "frontend" / ".env.production.local"
BFF = "https://se-e5cad5d30b1a4f22b9aeea032827f81b.ecs.us-east-1.on.aws"
WANTED = ("VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY")


def load_keys(path: Path) -> dict[str, str]:
    vals: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key in WANTED and value:
            vals[key] = value
    return vals


def main() -> int:
    if not SRC.exists():
        print("missing frontend/.env.local")
        return 1
    vals = load_keys(SRC)
    missing = [key for key in WANTED if key not in vals]
    if missing:
        print("missing_keys", ",".join(missing))
        return 1
    supabase_url = vals["VITE_SUPABASE_URL"]
    if not supabase_url.startswith("https://") or ".supabase.co" not in supabase_url:
        print("supabase_url_shape unexpected")
        return 1
    lines = [
        "# Generated for hosted Vite build. Gitignored. Do not commit.",
        f"VITE_SUPABASE_URL={vals['VITE_SUPABASE_URL']}",
        f"VITE_SUPABASE_ANON_KEY={vals['VITE_SUPABASE_ANON_KEY']}",
        f"VITE_API_BASE_URL={BFF}",
    ]
    DST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote frontend/.env.production.local")
    print("keys VITE_SUPABASE_URL,VITE_SUPABASE_ANON_KEY,VITE_API_BASE_URL")
    print("api_host", BFF.split("://", 1)[1])
    print("supabase_host_ok", True)
    print("anon_len", len(vals["VITE_SUPABASE_ANON_KEY"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
