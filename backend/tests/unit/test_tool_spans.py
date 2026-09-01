"""E7.3 / issue #51 — tool-level spans reach CloudWatch's OTEL pipeline.

## What was actually broken, and what these tests pin

The issue is titled "fix the ADOT `aws_auth_session` credential-recursion bug", and the premise
turned out to be two separate facts that had been fused into one:

1. **The crash was real, was upstream, and is already fixed.** `aws-opentelemetry-distro` 0.18.0's
   release note: *"avoid RecursionError when pip_system_certs replaces ssl.SSLContext (truststore
   injection) by rebinding stale botocore/urllib3 SSL context references and caching credentials in
   AwsAuthSession"*. This project triggers that exact condition — `app/core/tls.py` calls
   `truststore.inject_into_ssl()`. At the moment the crash was recorded (2026-08-16 21:05 IST) the
   pin was `aws-opentelemetry-distro>=0.10.0`; it was raised to `>=0.18.0` at 22:37 IST the same
   day, an hour and a half *after*. Nothing in this repository ever caused it and nothing here can
   fix it — the floor pin already did.

2. **There were no tool spans to export in the first place.** `from opentelemetry import metrics`
   was the only OpenTelemetry import anywhere in `backend/app/`. Even with a perfectly healthy
   exporter, a pipeline carrying zero spans emits zero spans. That is the half these tests cover.

So the assertions below are deliberately about *emission*, not about export: they install a real
`TracerProvider` with an in-memory exporter, which is the honest local stand-in for ADOT's provider
in the container, and check that a driver turn's tool calls produce spans a backend could read.
"""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from app.assistant.observability import TurnLatency

_EXPORTER = InMemorySpanExporter()


@pytest.fixture(scope="module", autouse=True)
def _real_tracer_provider():
    """Install one real SDK provider for this module.

    `set_tracer_provider` is deliberately once-per-process in OpenTelemetry (a second call logs a
    warning and is ignored), so this is module-scoped rather than per-test, and each test clears
    the exporter instead of rebuilding the pipeline.

    Installing it *after* `observability` was imported is not an accident either -- it reproduces
    the AgentCore ordering, where ADOT's auto-instrumentation sets the global provider and our
    module-level `get_tracer` call may have already run. That only works because `get_tracer`
    returns a `ProxyTracer` which re-resolves on first use; if that ever stopped being true, these
    tests would fail rather than silently pass against a no-op tracer.
    """
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
    trace.set_tracer_provider(provider)
    yield provider


@pytest.fixture(autouse=True)
def _clear_spans():
    _EXPORTER.clear()
    yield
    _EXPORTER.clear()


def _only_span():
    spans = _EXPORTER.get_finished_spans()
    assert len(spans) == 1, f"expected exactly one span, got {[s.name for s in spans]}"
    return spans[0]


def test_a_tool_call_emits_a_span_at_all():
    """The whole point of #51: before this, a turn produced metrics and no spans of its own."""
    TurnLatency().record_tool(tool="list_active_shipments", duration_ms=42.0, ok=True)

    span = _only_span()
    assert span.name == "execute_tool list_active_shipments"


def test_span_carries_the_genai_semantic_convention_attributes():
    """`gen_ai.*` is what a GenAI-aware backend groups on; `setuhaul.*` is what only we care about.

    They are kept as two namespaces on purpose. The GenAI conventions are still marked Development
    stability, so if `gen_ai.operation.name` is renamed upstream the SetuHaul numbers survive the
    rename untouched.
    """
    turn = TurnLatency()
    turn.note_hop()
    turn.note_hop()
    turn.record_tool(tool="find_feasible_slots", duration_ms=118.5, ok=True)

    attrs = dict(_only_span().attributes or {})
    assert attrs["gen_ai.operation.name"] == "execute_tool"
    assert attrs["gen_ai.tool.name"] == "find_feasible_slots"
    assert attrs["setuhaul.tool.duration_ms"] == 118.5
    assert attrs["setuhaul.tool.outcome"] == "ok"
    # The hop this tool ran in -- the number Appendix A calls the latency regression "no amount of
    # infrastructure tuning will fix", now attached to the tool rather than only to the turn.
    assert attrs["setuhaul.turn.hop"] == 2
    # COMMON_ATTRIBUTES still ride along, so a span and a histogram sample can be joined.
    assert attrs["environment"] == "poc"
    assert attrs["app_version"] == "sprint4"


def test_a_failed_tool_is_an_error_span_not_a_missing_one():
    """A tool that raised is the *most* interesting span, so it must not be dropped.

    `_execute_tool_round` catches every tool exception and turns it into a JSON result the model
    reads, so by the time this is recorded there is no live exception to attach -- the span carries
    ERROR status and the outcome attribute, and the stack trace lives in the LangSmith run where
    D-3 puts turn internals.
    """
    TurnLatency().record_tool(tool="request_slot", duration_ms=9.0, ok=False)

    span = _only_span()
    assert span.status.status_code is StatusCode.ERROR
    assert dict(span.attributes or {})["setuhaul.tool.outcome"] == "error"


def test_span_duration_matches_the_measurement_the_histogram_got():
    """The span is created after the call returns, with explicit start/end times.

    That reconstruction is the one thing a retroactive span can get wrong, so it is asserted
    directly rather than trusted: a span whose duration disagreed with the histogram would make the
    two telemetry channels tell different stories about the same call.
    """
    TurnLatency().record_tool(tool="get_shipment_detail", duration_ms=250.0, ok=True)

    span = _only_span()
    assert span.end_time is not None and span.start_time is not None
    assert (span.end_time - span.start_time) == 250_000_000  # ns


def test_a_negative_duration_cannot_produce_a_span_that_ends_before_it_starts():
    """Clamp guard. A clock adjustment mid-call is rare; a span rejected by the backend for
    ending before it started is a silent, total loss of that turn's tool visibility."""
    TurnLatency().record_tool(tool="weird_clock", duration_ms=-5.0, ok=True)

    span = _only_span()
    assert span.end_time >= span.start_time


def test_the_tool_span_joins_the_ambient_trace_rather_than_starting_a_rival_one():
    """The load-bearing assertion for #51's actual ask.

    On AgentCore there is already a live platform span (`AgentCore.Runtime.Invoke`) when our code
    runs. A tool span that started its own trace would be invisible next to it in Transaction
    Search -- present, but unjoinable. `start_span` with no explicit context takes the *current*
    context as parent, which is what makes these spans nest under the platform span instead.
    """
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("AgentCore.Runtime.Invoke") as parent:
        TurnLatency().record_tool(tool="list_active_shipments", duration_ms=5.0, ok=True)
        parent_ctx = parent.get_span_context()

    tool_spans = [s for s in _EXPORTER.get_finished_spans() if s.name.startswith("execute_tool")]
    assert len(tool_spans) == 1
    child = tool_spans[0]
    assert child.parent is not None
    assert child.parent.span_id == parent_ctx.span_id
    assert child.context.trace_id == parent_ctx.trace_id


def test_the_histogram_still_records_exactly_as_before(monkeypatch):
    """#51 is additive. The section-10 per-tool latency measurement must be untouched by it."""
    from app.assistant import observability as obs

    recorded: list[tuple] = []

    class _Histogram:
        def record(self, value, attributes):
            recorded.append((value, attributes))

    monkeypatch.setattr(obs, "tool_duration_metric", _Histogram())
    turn = TurnLatency()
    turn.record_tool(tool="list_active_shipments", duration_ms=42.0, ok=True)

    assert recorded == [(42.0, {"environment": "poc", "app_version": "sprint4",
                               "tool": "list_active_shipments", "outcome": "ok"})]
    assert turn.tool_calls == 1
    assert turn.tool_ms == 42.0


def test_no_tracer_installed_is_a_silent_no_op(monkeypatch):
    """Local uvicorn and ECS have no OTEL provider at all. Emission must cost nothing and,
    crucially, must not raise -- telemetry is never allowed to be why a driver turn fails."""
    from app.assistant import observability as obs

    monkeypatch.setattr(obs, "_tool_tracer", None)
    obs.TurnLatency().record_tool(tool="list_active_shipments", duration_ms=1.0, ok=True)

    assert _EXPORTER.get_finished_spans() == ()


def test_a_broken_tracer_never_breaks_the_turn(monkeypatch):
    """Same rule `_record` follows for metrics, asserted for spans: a provider that throws is a
    lost span, not a lost answer to the driver."""
    from app.assistant import observability as obs

    class _ExplodingTracer:
        def start_span(self, *_args, **_kwargs):
            raise RuntimeError("provider is on fire")

    monkeypatch.setattr(obs, "_tool_tracer", _ExplodingTracer())
    turn = obs.TurnLatency()
    turn.record_tool(tool="list_active_shipments", duration_ms=1.0, ok=True)

    # The measurement the turn depends on still happened.
    assert turn.tool_calls == 1


def test_the_adot_floor_pin_is_not_lowered_below_the_recursion_fix():
    """A regression guard on the dependency, because that is where #51's real fix lives.

    0.18.0 is the release that fixed the `RecursionError` in ADOT's OTLP exporter. Lowering this
    floor would silently reopen the original bug on the next lock refresh, and the failure mode is
    "no in-app spans export at all", which no application test could ever catch.
    """
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    extras = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"][
        "optional-dependencies"
    ]["agentcore"]
    pin = next(d for d in extras if d.startswith("aws-opentelemetry-distro"))
    floor = pin.split(">=")[1].split(",")[0]
    assert tuple(int(p) for p in floor.split(".")) >= (0, 18, 0), pin
