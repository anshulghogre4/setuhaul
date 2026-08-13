"""CloudWatch histograms (optional OTEL) + LangSmith run config. Safe when tracing is off."""

from __future__ import annotations

import re
from typing import Any

ENVIRONMENT = "poc"
APP_VERSION = "sprint4"

COMMON_ATTRIBUTES = {
    "environment": ENVIRONMENT,
    "app_version": APP_VERSION,
}

_SECRET_KEY = re.compile(
    r"(api[_-]?key|token|password|secret|authorization|service[_-]?role)",
    re.IGNORECASE,
)

try:
    from opentelemetry import metrics

    _meter = metrics.get_meter("setuhaul-agent")
    messages_loaded_metric = _meter.create_histogram(
        name="setuhaul.memory.messages_loaded",
        unit="messages",
        description="Messages loaded from Redis for each assistant turn",
    )
    response_length_metric = _meter.create_histogram(
        name="setuhaul.response.length",
        unit="characters",
        description="Characters returned by the assistant",
    )
except Exception:  # noqa: BLE001 — tracing-off / missing distro must not crash local uvicorn
    metrics = None  # type: ignore[assignment]
    messages_loaded_metric = None
    response_length_metric = None


def get_history_size_bucket(message_count: int) -> str:
    if message_count <= 0:
        return "0"
    if message_count <= 4:
        return "1-4"
    if message_count <= 8:
        return "5-8"
    return "9+"


def sanitize_for_trace(value: Any) -> Any:
    """Redact secret-shaped keys so LangSmith/CloudWatch never store credentials."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _SECRET_KEY.search(str(key)):
                out[str(key)] = "[redacted]"
            else:
                out[str(key)] = sanitize_for_trace(item)
        return out
    if isinstance(value, list):
        return [sanitize_for_trace(item) for item in value]
    return value


def tool_outcome_metadata(tool_calls: list[dict[str, Any]], ux_state: str) -> dict[str, Any]:
    """Per-turn FDE story fields — not warehouse totals."""
    last_code = ""
    eta_persisted = False
    exception_touched = False
    names: list[str] = []
    for call in tool_calls:
        names.append(str(call.get("name") or ""))
        parsed = call.get("result")
        if not isinstance(parsed, dict):
            continue
        code = str(parsed.get("code") or parsed.get("status") or "")
        if code:
            last_code = code
        if parsed.get("status") == "PERSISTED" or code in {"ETA_UPDATED", "ETA_PERSISTED"}:
            eta_persisted = True
        if "exception" in names[-1].lower() or code in {"NO_FEASIBLE_SLOTS", "ESCALATED"}:
            exception_touched = True
    if ux_state == "persisted_success":
        eta_persisted = True
    return {
        "last_result_code": last_code or ux_state,
        "eta_persisted": eta_persisted,
        "exception_touched": exception_touched,
        "tool_names": ",".join(n for n in names if n)[:500],
    }


def observe_input(message_count: int, extra_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    if messages_loaded_metric is not None:
        messages_loaded_metric.record(message_count, COMMON_ATTRIBUTES)
    metadata = {
        "history_size": message_count,
        "history_size_bucket": get_history_size_bucket(message_count),
        **COMMON_ATTRIBUTES,
    }
    if extra_metadata:
        metadata.update(sanitize_for_trace(extra_metadata))
    return {
        "run_name": "setuhaul.chat",
        "metadata": metadata,
        "tags": ["setuhaul", "agentcore", "driver-chat"],
    }


def observe_output(response_text: str) -> None:
    if response_length_metric is None:
        return
    response_length_metric.record(len(str(response_text)), COMMON_ATTRIBUTES)
    if metrics is not None:
        provider = metrics.get_meter_provider()
        if hasattr(provider, "force_flush"):
            try:
                provider.force_flush()
            except Exception:  # noqa: BLE001
                pass
