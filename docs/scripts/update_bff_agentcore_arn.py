"""Step 9: merge AGENTCORE_RUNTIME_ARN into Express primary-container JSON. Never prints values."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESCRIBE = Path.home() / "AppData" / "Local" / "Temp" / "setuhaul-express-describe.json"
OUT = Path.home() / "AppData" / "Local" / "Temp" / "setuhaul-express-step9.json"
RUNTIME_ID = "SetuHaulAgent_SetuHaulAgent-18B4pX4XF1"


def _read_json(path: Path) -> dict:
    raw = path.read_bytes()
    text = raw.decode("utf-16") if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff") else raw.decode("utf-8-sig")
    return json.loads(text)


def _arn_from_env() -> str:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("AGENTCORE_RUNTIME_ARN="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    return f"arn:aws:bedrock-agentcore:us-east-1:118490268011:runtime/{RUNTIME_ID}"


def main() -> int:
    data = _read_json(DESCRIBE)
    container = data["service"]["activeConfigurations"][0]["primaryContainer"]
    arn = _arn_from_env()
    if RUNTIME_ID not in arn:
        print("arn_mismatch")
        return 1
    env = list(container.get("environment") or [])
    found = False
    for item in env:
        if item.get("name") == "AGENTCORE_RUNTIME_ARN":
            item["value"] = arn
            found = True
    if not found:
        env.append({"name": "AGENTCORE_RUNTIME_ARN", "value": arn})
    out = {
        "image": container["image"],
        "containerPort": container.get("containerPort") or 8000,
        "environment": env,
        "secrets": container.get("secrets") or [],
    }
    OUT.write_text(json.dumps(out), encoding="utf-8")
    names = [i.get("name") for i in env]
    secret_names = [i.get("name") for i in out["secrets"]]
    print("wrote", OUT.as_posix())
    print("env_names", names)
    print("secret_names", secret_names)
    print("arn_set", True)
    print("arn_len", len(arn))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
