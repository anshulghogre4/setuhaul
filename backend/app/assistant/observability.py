"""CloudWatch histograms + tool spans (optional OTEL) + LangSmith run config + Sentry init.

Instruments TECH_STACK.md section 10's six named measurements (E0.3): TTFT p50/p95,
hop-count distribution per turn, per-tool DB latency, the LLM latency split, prompt-cache
hit rate and Redis RTT. Everything here is degrade-safe: with no OTEL distro installed
(local uvicorn) every instrument is None and every record call is a no-op, and a metric
failure is never allowed to break a turn.

Two later additions, both DEPLOYMENT.md section 8 (decision D-3), which splits observability
three ways -- CloudWatch owns infra/app signals, Sentry owns unhandled exceptions with stack
traces, LangSmith owns what happens inside a turn:

* **E7.3 / issue #51 -- tool-level spans.** Until this, CloudWatch saw only the platform-level
  `AgentCore.Runtime.Invoke` span: the process emitted metrics and no spans of its own at all
  (`from opentelemetry import metrics` was the only OTEL import in `backend/app/`). The spans
  below are created through `opentelemetry-api` only -- never the SDK, never an exporter -- so
  they attach to whatever provider is already installed in the process. On AgentCore that is
  ADOT's, so a tool span joins the platform span's trace instead of starting a rival one; with
  no SDK configured (local uvicorn, ECS) `get_tracer` hands back a proxy over the no-op provider
  and the whole path costs an attribute lookup.

* **E7.2 / issue #46 -- Sentry.** `init_sentry` is here rather than in `main.py` so the AgentCore
  entrypoint, which never runs the FastAPI lifespan, can call the same function.
"""

from __future__ import annotations

import logging
import re
import time
from contextlib import contextmanager
from typing import Any, Iterator

logger = logging.getLogger(__name__)

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

    # --- TECH_STACK.md section 10 "what to measure" (E0.3) ---------------------------
    # Histograms, not gauges: the document asks for p50/p95 and a hop-count
    # *distribution*, both of which are percentile queries over a distribution.
    turn_ttft_metric = _meter.create_histogram(
        name="setuhaul.turn.ttft",
        unit="ms",
        description="Time until the driver could see the first token of the answer",
    )
    turn_duration_metric = _meter.create_histogram(
        name="setuhaul.turn.duration",
        unit="ms",
        description="Whole-turn wall clock inside run_assistant (NFR-002 budget)",
    )
    turn_hops_metric = _meter.create_histogram(
        name="setuhaul.turn.hops",
        unit="hops",
        description="Tool-execution rounds per turn; one hop costs two LLM inferences",
    )
    tool_duration_metric = _meter.create_histogram(
        name="setuhaul.tool.duration",
        unit="ms",
        description="Per-tool latency; driver tools are DB reads, so this is tool DB latency",
    )
    llm_duration_metric = _meter.create_histogram(
        name="setuhaul.llm.duration",
        unit="ms",
        description="Per-inference latency, split by phase when a stream supplies TTFT",
    )
    llm_input_tokens_metric = _meter.create_histogram(
        name="setuhaul.llm.input_tokens",
        unit="tokens",
        description="Prompt tokens per inference (cache hit-rate denominator)",
    )
    llm_cached_input_tokens_metric = _meter.create_histogram(
        name="setuhaul.llm.cached_input_tokens",
        unit="tokens",
        description="Prompt tokens served from the provider prompt cache (numerator)",
    )
    llm_output_tokens_metric = _meter.create_histogram(
        name="setuhaul.llm.output_tokens",
        unit="tokens",
        description="Completion tokens per inference; separates slow network from long decode",
    )
    redis_duration_metric = _meter.create_histogram(
        name="setuhaul.redis.duration",
        unit="ms",
        description="Upstash round-trip time per command batch",
    )
except Exception:  # noqa: BLE001 — tracing-off / missing distro must not crash local uvicorn
    metrics = None  # type: ignore[assignment]
    messages_loaded_metric = None
    response_length_metric = None
    turn_ttft_metric = None
    turn_duration_metric = None
    turn_hops_metric = None
    tool_duration_metric = None
    llm_duration_metric = None
    llm_input_tokens_metric = None
    llm_cached_input_tokens_metric = None
    llm_output_tokens_metric = None
    redis_duration_metric = None


# --- E7.3 (issue #51): tool-level spans -------------------------------------------------
#
# `opentelemetry-api` only, deliberately. The historical blocker on this issue was a
# `RecursionError` raised deep inside ADOT's *exporter* (`aws_auth_session.py`) -- an SDK-side
# fault, fixed upstream in `aws-opentelemetry-distro` 0.18.0. Nothing here can reintroduce it,
# because nothing here configures a provider, a processor or an exporter: `get_tracer` returns a
# `ProxyTracer` that resolves lazily against whatever global provider exists at first use. In the
# AgentCore container ADOT's auto-instrumentation has already installed one, so these spans join
# the live trace; everywhere else the proxy resolves to the no-op provider and every call below is
# free. The import is still guarded because `opentelemetry-api` is a runtime dependency that a
# stripped install could lack, and telemetry must never be the reason a driver turn fails.
try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.trace import SpanKind, Status, StatusCode

    _tool_tracer = _otel_trace.get_tracer("setuhaul.agent")
except Exception:  # noqa: BLE001 — no OTEL API installed must not crash local uvicorn
    _otel_trace = None  # type: ignore[assignment]
    SpanKind = None  # type: ignore[assignment]
    Status = None  # type: ignore[assignment]
    StatusCode = None  # type: ignore[assignment]
    _tool_tracer = None


def _emit_tool_span(*, tool: str, duration_ms: float, ok: bool, hop: int) -> None:
    """One span per tool call, parented to the ambient turn trace.

    The span is created *after* the tool returned, with explicit `start_time`/`end_time`, rather
    than by wrapping the call in `start_as_current_span`. That is a scope decision, not a
    preference: the wrapping seam is `run_assistant._execute_tool_round`, and this change is
    deliberately confined to the observability module. The consequence is worth stating plainly --
    name, duration, attributes, status and *parent* are all exactly what a wrapping span would
    produce, but any auto-instrumented span raised inside the tool (an asyncpg query, say) parents
    to the turn rather than nesting under its tool. Issue #51 asks for tool-level visibility, which
    this delivers; nesting the tool's own children is the follow-up, and it is one line at the
    seam once someone owns that file.

    Attribute names follow OpenTelemetry's GenAI semantic conventions (`gen_ai.operation.name` =
    `execute_tool`, `gen_ai.tool.name`, span name `execute_tool {name}`), which are still marked
    Development stability -- so the SetuHaul-specific numbers are carried under a `setuhaul.*`
    prefix that cannot be invalidated by a convention change.
    """
    if _tool_tracer is None:
        return
    try:
        end_ns = time.time_ns()
        # Wall-clock start reconstructed from the measurement the caller already made. Clamped at
        # zero so a negative duration (a clock adjustment mid-call) can never emit a span that
        # ends before it starts, which some backends reject outright.
        start_ns = end_ns - max(0, int(duration_ms * 1_000_000))
        span = _tool_tracer.start_span(
            f"execute_tool {tool}",
            kind=SpanKind.INTERNAL,
            start_time=start_ns,
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": tool,
                "setuhaul.tool.duration_ms": duration_ms,
                "setuhaul.tool.outcome": "ok" if ok else "error",
                "setuhaul.turn.hop": hop,
                **COMMON_ATTRIBUTES,
            },
        )
        # No exception is recorded: `_execute_tool_round` has already caught it and turned it into
        # a JSON result the model reads, so there is no live exception to attach. ERROR status
        # without a message is the honest encoding of "this tool call failed" -- the *why* is in
        # the LangSmith run, which is where D-3 says turn internals live.
        span.set_status(Status(StatusCode.ERROR) if not ok else Status(StatusCode.OK))
        span.end(end_time=end_ns)
    except Exception:  # noqa: BLE001 — a span must never break a turn, same rule as _record
        pass


def _record(instrument: Any, value: float, attributes: dict[str, Any] | None = None) -> None:
    """Record on a possibly-absent instrument. Measurement never breaks a turn."""
    if instrument is None:
        return
    try:
        instrument.record(value, {**COMMON_ATTRIBUTES, **(attributes or {})})
    except Exception:  # noqa: BLE001
        pass


def elapsed_ms(started: float) -> float:
    """Milliseconds since a time.perf_counter() reading, rounded for readability."""
    return round((time.perf_counter() - started) * 1000.0, 1)


def model_labels(llm: Any) -> tuple[str, str]:
    """(provider, model) for metric attributes, without importing any provider package.

    ChatOpenAI exposes model_name; ChatGoogleGenerativeAI exposes model. Attributes stay
    low-cardinality: class name plus model id, never a per-request value.
    """
    provider = type(llm).__name__
    model = getattr(llm, "model_name", None) or getattr(llm, "model", None) or "unknown"
    return provider, str(model)


def cache_tokens_from_usage(usage: Any) -> tuple[int, int, int]:
    """(input_tokens, cached_input_tokens, output_tokens) from LangChain usage_metadata.

    Verified against the installed packages rather than assumed: langchain_core 0.3.86
    defines input_token_details["cache_read"], langchain_openai 0.3.35 maps OpenAI's
    prompt_tokens_details.cached_tokens into it, and langchain_google_genai 2.1.12 maps
    Gemini's cached_content_token_count. Missing or partial usage yields zeros; a provider
    that never reports tokens contributes a zero denominator and so cannot silently
    inflate the cache hit rate.
    """
    if not isinstance(usage, dict):
        return 0, 0, 0

    def _int(source: dict[str, Any], key: str) -> int:
        try:
            return int(source.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    details = usage.get("input_token_details")
    cached = _int(details, "cache_read") if isinstance(details, dict) else 0
    return _int(usage, "input_tokens"), cached, _int(usage, "output_tokens")


def attach_run_metrics(
    run: Any,
    latency: dict[str, Any],
    outputs: dict[str, Any] | None = None,
) -> None:
    """Attach a turn's latency numbers to its LangSmith parent run.

    No-op when tracing is off (run is None) or when the SDK version lacks the setters.
    Verified against langsmith 0.10.17: RunTree.add_metadata / add_outputs.
    """
    if run is None:
        return
    try:
        add_metadata = getattr(run, "add_metadata", None)
        if callable(add_metadata):
            add_metadata({"latency": latency})
        if outputs:
            add_outputs = getattr(run, "add_outputs", None)
            if callable(add_outputs):
                add_outputs(sanitize_for_trace(outputs))
    except Exception:  # noqa: BLE001 - tracing must never break a turn
        pass


def record_redis_op(op: str, duration_ms: float) -> None:
    """Redis RTT (lever 9). Called from redis_memory around each command batch."""
    _record(redis_duration_metric, duration_ms, {"op": op})


class TurnLatency:
    """Per-turn accumulator for the six measurements.

    One instance per driver turn, owned by run_assistant. Each measurement goes to its
    histogram as it happens, and finish() returns a compact metadata dict so the same
    numbers land on the LangSmith parent run - which is where they can actually be read
    today, since the OTEL distro only exists on AgentCore.
    """

    __slots__ = (
        "_started",
        "streaming",
        "ttft_ms",
        "hops",
        "llm_calls",
        "llm_ms",
        "tool_calls",
        "tool_ms",
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
    )

    def __init__(self, *, streaming: bool = False) -> None:
        self._started = time.perf_counter()
        # No streaming path exists yet (lever 3 is a separate epic). Until one does, the
        # driver's first visible token arrives with the whole response, so TTFT is the
        # whole turn - recorded with streaming="false" so the two eras never mix in one
        # percentile.
        self.streaming = streaming
        self.ttft_ms: float | None = None
        self.hops = 0
        self.llm_calls = 0
        self.llm_ms = 0.0
        self.tool_calls = 0
        self.tool_ms = 0.0
        self.input_tokens = 0
        self.cached_input_tokens = 0
        self.output_tokens = 0

    def note_hop(self) -> None:
        """One tool-execution round. Hop count is lever #1, so it is counted rather than
        inferred from a list of tool names."""
        self.hops += 1

    def record_llm(
        self,
        *,
        duration_ms: float,
        provider: str,
        model: str,
        hop: int,
        usage: Any = None,
        first_token_ms: float | None = None,
        ok: bool = True,
    ) -> None:
        """One inference.

        first_token_ms is the only honest way to split network from inference: neither
        langchain_openai 0.3.35 nor langchain_google_genai 2.1.12 surfaces server-side
        timing (their response_metadata carries finish_reason / safety_ratings /
        system_fingerprint and nothing temporal), so the split needs a first-token
        timestamp, which needs streaming. The parameter is wired now, so the
        ttft/generation phases start emitting the moment a streaming caller passes it.
        Until then the total is recorded with phase="total_no_stream" alongside token
        counts, which still separates "slow network / long prefill" from "long decode".
        """
        self.llm_calls += 1
        self.llm_ms += duration_ms
        attrs = {
            "provider": provider,
            "model": model,
            "hop": str(hop),
            "outcome": "ok" if ok else "error",
        }
        if first_token_ms is None:
            _record(llm_duration_metric, duration_ms, {**attrs, "phase": "total_no_stream"})
        else:
            _record(llm_duration_metric, duration_ms, {**attrs, "phase": "total"})
            _record(llm_duration_metric, first_token_ms, {**attrs, "phase": "ttft"})
            _record(
                llm_duration_metric,
                max(0.0, duration_ms - first_token_ms),
                {**attrs, "phase": "generation"},
            )
            if self.ttft_ms is None:
                self.ttft_ms = first_token_ms

        tokens_in, cached_in, tokens_out = cache_tokens_from_usage(usage)
        self.input_tokens += tokens_in
        self.cached_input_tokens += cached_in
        self.output_tokens += tokens_out
        token_attrs = {"provider": provider, "model": model}
        if tokens_in:
            _record(llm_input_tokens_metric, tokens_in, token_attrs)
            # Recorded even at zero: a zero cache read against a non-zero prompt is the
            # signal that something volatile leaked into the cacheable prefix (lever 5).
            _record(llm_cached_input_tokens_metric, cached_in, token_attrs)
        if tokens_out:
            _record(llm_output_tokens_metric, tokens_out, token_attrs)

    def record_tool(self, *, tool: str, duration_ms: float, ok: bool) -> None:
        """Per-tool latency. Driver tools are typed PostgreSQL reads, so measuring at the
        call site is per-tool DB latency without touching the tool layer.

        E7.3 (issue #51) also emits a span here. The histogram answers "how slow are tools in
        aggregate"; the span answers "what did *this* turn actually do", which is the question
        CloudWatch could not answer while only the platform-level `AgentCore.Runtime.Invoke` span
        existed. `self.hops` is the current round index -- already tracked for the hop-count
        distribution, so the span costs no new plumbing through the caller.
        """
        self.tool_calls += 1
        self.tool_ms += duration_ms
        resolved = tool or "unknown"
        _record(
            tool_duration_metric,
            duration_ms,
            {"tool": resolved, "outcome": "ok" if ok else "error"},
        )
        _emit_tool_span(tool=resolved, duration_ms=duration_ms, ok=ok, hop=self.hops)

    @property
    def cache_hit_rate(self) -> float | None:
        """None, not zero, when no provider reported prompt tokens - an unmeasured cache
        and a cold cache are different facts."""
        if self.input_tokens <= 0:
            return None
        return round(self.cached_input_tokens / self.input_tokens, 4)

    def finish(
        self,
        *,
        ux_state: str,
        redis_ms: float = 0.0,
        redis_ops: int = 0,
    ) -> dict[str, Any]:
        """Record the turn-level histograms and return metadata for the LangSmith run."""
        turn_ms = elapsed_ms(self._started)
        if self.ttft_ms is None:
            self.ttft_ms = turn_ms
        _record(turn_duration_metric, turn_ms, {"ux_state": ux_state})
        _record(
            turn_ttft_metric,
            self.ttft_ms,
            {"ux_state": ux_state, "streaming": "true" if self.streaming else "false"},
        )
        _record(turn_hops_metric, self.hops, {"ux_state": ux_state})
        return {
            "turn_ms": turn_ms,
            "ttft_ms": self.ttft_ms,
            "streaming": self.streaming,
            "hops": self.hops,
            "llm_calls": self.llm_calls,
            "llm_ms": round(self.llm_ms, 1),
            "tool_calls": self.tool_calls,
            "tool_ms": round(self.tool_ms, 1),
            "redis_ms": round(redis_ms, 1),
            "redis_ops": redis_ops,
            "input_tokens": self.input_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "output_tokens": self.output_tokens,
            "cache_hit_rate": self.cache_hit_rate,
            "llm_split": "measured" if self.streaming else "unavailable_no_stream",
        }


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


def observe_input(
    message_count: int,
    extra_metadata: dict[str, Any] | None = None,
    *,
    thread_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    if messages_loaded_metric is not None:
        messages_loaded_metric.record(message_count, COMMON_ATTRIBUTES)
    metadata = {
        "history_size": message_count,
        "history_size_bucket": get_history_size_bucket(message_count),
        **COMMON_ATTRIBUTES,
    }
    if thread_id:
        metadata["thread_id"] = thread_id
    if session_id:
        metadata["session_id"] = session_id
    if extra_metadata:
        metadata.update(sanitize_for_trace(extra_metadata))
    return {
        "run_name": "setuhaul.chat",
        "metadata": metadata,
        "tags": ["setuhaul", "agentcore", "driver-chat"],
    }


def child_invoke_config(
    parent_config: dict[str, Any],
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Nested LLM/tool config. No run_name so children keep their own span names."""
    metadata = dict(parent_config.get("metadata") or {})
    if extra_metadata:
        metadata.update(sanitize_for_trace(extra_metadata))
    return {
        "metadata": metadata,
        "tags": list(parent_config.get("tags") or []),
    }


@contextmanager
def chat_turn_trace(
    config: dict[str, Any],
    inputs: dict[str, Any] | None = None,
) -> Iterator[Any]:
    """One parent LangSmith run per user turn. No-op if langsmith is unavailable."""
    try:
        from langsmith import trace
    except Exception:  # noqa: BLE001
        yield None
        return
    with trace(
        name=str(config.get("run_name") or "setuhaul.chat"),
        run_type="chain",
        metadata=dict(config.get("metadata") or {}),
        tags=list(config.get("tags") or []),
        inputs=sanitize_for_trace(inputs or {}),
    ) as run:
        yield run


def observe_output(response_text: str) -> None:
    """Record the turn's output. Never flushes.

    A per-turn ``MeterProvider.force_flush()`` used to run here. It is a synchronous
    per-reader collect-and-export with a 10-second default deadline, on the event loop,
    between composing the answer and returning it — a no-op locally (no OTEL distro) and
    live on AgentCore. TECH_STACK.md §10 lever 8: telemetry never blocks the request
    path. Export now happens on PeriodicExportingMetricReader's own interval, plus
    shutdown_telemetry() below at process exit.
    """
    if response_length_metric is None:
        return
    response_length_metric.record(len(str(response_text)), COMMON_ATTRIBUTES)


def shutdown_telemetry(timeout_millis: float = 5_000) -> bool:
    """Flush and shut down metrics at process exit — off the request path.

    Called from the FastAPI lifespan's shutdown half. The SDK also registers its own
    atexit handler (``shutdown_on_exit=True``), so this is the graceful-shutdown path
    rather than the only one; calling it twice is a logged no-op. Returns False when
    there is nothing to flush (no distro installed, or shutdown already ran).
    """
    if metrics is None:
        return False
    try:
        provider = metrics.get_meter_provider()
        flush = getattr(provider, "force_flush", None)
        if callable(flush):
            flush(timeout_millis=timeout_millis)
        shutdown = getattr(provider, "shutdown", None)
        if callable(shutdown):
            shutdown()
        return True
    except Exception:  # noqa: BLE001 — shutdown must never mask a real shutdown error
        return False


# --- E7.2 (issue #46): Sentry ------------------------------------------------------------


def sentry_before_send(event: Any, _hint: Any = None) -> Any:
    """Run every outgoing Sentry event through this project's own redaction rule.

    `send_default_pii=False` already stops the SDK attaching headers, cookies and bodies, but it
    says nothing about *stack-frame locals*, which Sentry sends by default and which on this
    codebase can hold a Supabase service-role key, a JWT or an Upstash token -- exactly the values
    `AGENTS.md` forbids putting anywhere durable. `sanitize_for_trace` is the redaction rule
    LangSmith traces already use, reused rather than reinvented so the two channels cannot drift.

    Fails **closed**: if scrubbing itself raises, the event is dropped rather than sent unscrubbed.
    Losing one crash report is recoverable; publishing a service-role key to a third party is not.
    """
    try:
        return sanitize_for_trace(event)
    except Exception:  # noqa: BLE001
        logger.warning("sentry event dropped: redaction failed")
        return None


def init_sentry(settings: Any) -> bool:
    """Initialise Sentry, but only when a DSN is actually configured. Returns whether it ran.

    DEPLOYMENT.md section 8 (D-3) gives Sentry one job: unhandled exceptions with stack traces,
    frontend and backend. Called from `main.create_app` before the FastAPI app is constructed
    (Sentry's own FastAPI guide: "configuration should happen as early as possible", and the
    Starlette/FastAPI integrations are auto-enabled by the presence of the packages, so there is
    nothing to pass explicitly) and from the AgentCore entrypoint, which never runs that lifespan.

    The empty-DSN branch does not merely skip `init` -- it never imports `sentry_sdk` at all, so an
    unconfigured deployment carries no import cost, installs no `sys.excepthook`, patches no ASGI
    app and opens no background transport thread. That is what "ships dark" has to mean for this
    to be a safe no-op rather than a dormant feature.

    Every failure path returns False instead of raising: an observability tool must not be able to
    stop the API from booting.
    """
    dsn = (getattr(settings, "sentry_dsn", "") or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
    except Exception:  # noqa: BLE001
        # A configured DSN with no SDK installed is a real deployment mistake, so it is a warning
        # rather than a silent skip -- but still not fatal.
        logger.warning("SENTRY_DSN is set but sentry-sdk is not installed; error tracking is off")
        return False

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=(getattr(settings, "environment", "") or "unknown").strip(),
            # `or None` rather than `or ""`, and the difference is not cosmetic: `None` hands the
            # decision to Sentry's own `get_default_release()`, which reads `SENTRY_RELEASE` and
            # then falls back to the git HEAD SHA. Verified rather than assumed -- initialising
            # with a blank setting in this repo produces the current commit SHA as the release, so
            # leaving `sentry_release` unset already gives correctly-versioned events locally and
            # anywhere the deploy exports `SENTRY_RELEASE`. An empty string would instead be taken
            # as a real release name and group every event ever sent under it.
            release=(getattr(settings, "sentry_release", "") or "").strip() or None,
            traces_sample_rate=float(getattr(settings, "sentry_traces_sample_rate", 0.1) or 0.0),
            # Explicit, not inherited. Sentry's own FastAPI quickstart sets this True; this
            # project must not. Driver names, phone numbers and shipment references are the
            # payloads these endpoints carry, and SOLUTION_DESIGN's data-residency posture does
            # not survive shipping them to a third-party region by default.
            send_default_pii=False,
            # Same reasoning one layer down: without this, a 500 on a booking write would carry
            # the request body -- driver identity and appointment detail -- into the event.
            max_request_body_size="never",
            before_send=sentry_before_send,
        )
    except Exception:  # noqa: BLE001 — a malformed DSN must not stop the API from starting
        logger.warning("sentry init failed; continuing without error tracking")
        return False
    return True
