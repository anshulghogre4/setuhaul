"""M0 latency work (GitHub epics E0.2 / E0.3).

Covers the four highest-payoff fixes from `COMPARISON-latency.md` §6 and the six
measurements `TECH_STACK.md` §10 names. Each test names the issue it guards so a
future regression is traceable to the reason the code looks this way.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from app.core.settings import (
    DESIGNED_AWS_REGION,
    RegionMismatchError,
    Settings,
    assert_region_alignment,
)


# --------------------------------------------------------------------------- #
# Issue #12 — region default + startup assertion
# --------------------------------------------------------------------------- #


def test_aws_region_default_is_designed_region():
    """Read the field default, not a constructed instance: a developer .env must not
    be able to make this test pass or fail for the wrong reason."""
    assert DESIGNED_AWS_REGION == "ap-south-1"
    assert Settings.model_fields["aws_region"].default == "ap-south-1"


def test_resolved_region_is_this_process_region_not_a_remote_resource():
    s = Settings(
        aws_region="ap-south-1",
        agentcore_runtime_arn="arn:aws:bedrock-agentcore:us-east-1:1:runtime/x",
    )
    assert s.resolved_aws_region == "ap-south-1"
    assert s.agentcore_arn_region == "us-east-1"
    assert Settings(agentcore_runtime_arn="").agentcore_arn_region is None


def test_resolved_region_falls_back_to_aws_region_without_arn():
    assert Settings(aws_region="ap-south-1", agentcore_runtime_arn="").resolved_aws_region == "ap-south-1"


def test_region_guard_passes_when_co_located():
    s = Settings(aws_region="ap-south-1", agentcore_runtime_arn="")
    assert assert_region_alignment(s) == "ap-south-1"


def test_region_guard_fails_loudly_on_mismatch():
    s = Settings(aws_region="us-east-1", agentcore_runtime_arn="")
    with pytest.raises(RegionMismatchError) as exc:
        assert_region_alignment(s)
    assert "us-east-1" in str(exc.value)
    assert "ap-south-1" in str(exc.value)


def test_out_of_region_agentcore_runtime_is_critical_but_not_fatal(caplog):
    """A remote runtime in the wrong region is a real co-location violation, but it is
    fixed by redeploying that runtime - failing startup on it would make the BFF
    unbootable for a defect it cannot correct."""
    s = Settings(
        aws_region="ap-south-1",
        agentcore_runtime_arn="arn:aws:bedrock-agentcore:us-east-1:1:runtime/x",
    )
    with caplog.at_level("CRITICAL"):
        assert assert_region_alignment(s) == "ap-south-1"
    assert any("AgentCore runtime is in us-east-1" in r.getMessage() for r in caplog.records)


def test_region_guard_escape_hatch_is_explicit_and_does_not_raise():
    s = Settings(aws_region="us-east-1", agentcore_runtime_arn="", allow_region_mismatch=True)
    assert assert_region_alignment(s) == "us-east-1"


# --------------------------------------------------------------------------- #
# Issue #13 — no telemetry flush on the response path
# --------------------------------------------------------------------------- #


def test_observe_output_records_without_flushing(monkeypatch):
    """The response path must not touch the meter provider at all: reaching it is how
    the old blocking force_flush() got in."""
    from app.assistant import observability as obs

    provider = MagicMock()
    fake_metrics = MagicMock()
    fake_metrics.get_meter_provider.return_value = provider
    histogram = MagicMock()
    monkeypatch.setattr(obs, "metrics", fake_metrics)
    monkeypatch.setattr(obs, "response_length_metric", histogram)

    obs.observe_output("driver-visible answer")

    histogram.record.assert_called_once()
    fake_metrics.get_meter_provider.assert_not_called()
    provider.force_flush.assert_not_called()


def test_shutdown_telemetry_flushes_off_the_request_path(monkeypatch):
    from app.assistant import observability as obs

    provider = MagicMock()
    fake_metrics = MagicMock()
    fake_metrics.get_meter_provider.return_value = provider
    monkeypatch.setattr(obs, "metrics", fake_metrics)

    assert obs.shutdown_telemetry() is True
    provider.force_flush.assert_called_once()
    provider.shutdown.assert_called_once()


def test_shutdown_telemetry_is_a_noop_without_a_distro(monkeypatch):
    from app.assistant import observability as obs

    monkeypatch.setattr(obs, "metrics", None)
    assert obs.shutdown_telemetry() is False


# --------------------------------------------------------------------------- #
# Issue #14 — process-scoped JwtVerifier / JWKS client
# --------------------------------------------------------------------------- #


def test_jwt_verifier_is_process_scoped_per_auth_config():
    from app.core import deps

    deps._JWT_VERIFIERS.clear()
    settings = Settings(supabase_url="https://proj-a.supabase.co")
    first = deps.get_jwt_verifier(settings)
    second = deps.get_jwt_verifier(Settings(supabase_url="https://proj-a.supabase.co"))
    other = deps.get_jwt_verifier(Settings(supabase_url="https://proj-b.supabase.co"))

    assert first is second, "a second request must reuse the verifier, not refetch JWKS"
    assert other is not first, "a different Supabase project must not share a JWKS cache"
    assert deps.get_jwt_verifier(settings) is first


def test_jwks_client_is_built_once_and_keeps_rotation_refresh_enabled():
    """PyJWKClient.__init__ performs no network I/O, so this is safe offline. The
    lifespan assertion is the real guard: rotation only works because the cached JWK set
    expires (300 s) and an unknown `kid` forces a refetch."""
    from app.core.security import JwtVerifier

    verifier = JwtVerifier(Settings(supabase_url="https://proj-a.supabase.co"))
    client = verifier._client()

    assert verifier._client() is client, "second verify must not rebuild the JWKS client"
    assert client.jwk_set_cache is not None
    assert client.jwk_set_cache.lifespan == 300


def test_jwks_client_refresh_window_is_now_live_code():
    """Before process-scoping, this hourly guard could never fire — the instance holding
    the timestamp did not survive one request."""
    from app.core.security import JwtVerifier

    verifier = JwtVerifier(Settings(supabase_url="https://proj-a.supabase.co"))
    first = verifier._client()
    verifier._jwks_fetched_at = time.time() - 3601
    assert verifier._client() is not first


# --------------------------------------------------------------------------- #
# Issue #15 — summarisation off the request path
# --------------------------------------------------------------------------- #


def _driver_ctx():
    from app.core.execution_context import ExecutionContext, RoleName

    return ExecutionContext(
        request_id="req-1",
        auth_subject="auth-1",
        user_id="USR001",
        email="ravi.kumar@setuhaul.com",
        full_name="Ravi Kumar",
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id="DRV001",
        facility_id="FAC-JAI-01",
        permissions=["chat:own"],
    )


class _FakeMemory:
    """Stand-in for ConversationMemory. Records what the turn asked it to do and how
    long the (deliberately slow) summariser took relative to the response."""

    def __init__(self, *_args, **_kwargs):
        self.degraded = False
        self.degrade_reason = None
        self.redis_ops = 2
        self.redis_ms = 31.5
        self.summary_started = asyncio.Event()
        self.summary_finished = asyncio.Event()
        self.summary_delay = 0.05
        self.summaries: list[str] = []

    def load_turn_context(self, **_kwargs):
        return {"history": [], "summaries": [], "session": {}}

    def append_turn(self, **_kwargs):
        return None

    async def maybe_summarize_history(self, **_kwargs):
        self.summary_started.set()
        await asyncio.sleep(self.summary_delay)
        self.summaries.append("summary-of-oldest-chunk")
        self.summary_finished.set()
        return "summary-of-oldest-chunk"


class _FakeAI:
    def __init__(self, content="Your shipment is on track.", usage=None, tool_calls=None):
        self.content = content
        self.tool_calls: list[dict] = list(tool_calls or [])
        self.usage_metadata = usage
        self.response_metadata: dict = {}


class _FakeTool:
    """Minimal stand-in for a bound LangChain tool (tools.py is out of scope here)."""

    def __init__(self, name="get_my_shipment", result=None, delay=0.0, raises=None):
        self.name = name
        self.args_schema = None
        self._result = result if result is not None else '{"code": "OK"}'
        self._delay = delay
        self._raises = raises

    async def ainvoke(self, _args, config=None):
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raises is not None:
            raise self._raises
        return self._result


def _patch_turn(monkeypatch, memory, ai=None, tool_rounds=None, tools=None):
    """Wire run_assistant to fakes: no Redis, no LLM, no real tools, no DB."""
    from app.assistant import run_assistant as ra

    replies = list(tool_rounds or []) + [ai or _FakeAI()]

    class _LLM:
        def __init__(self):
            self.calls = 0

        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, _messages, config=None):
            reply = replies[min(self.calls, len(replies) - 1)]
            self.calls += 1
            return reply

    llm = _LLM()
    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: memory)
    monkeypatch.setattr(ra, "build_chat_model", lambda _settings: llm)
    monkeypatch.setattr(ra, "build_driver_tools", lambda **_kwargs: list(tools or []))
    return llm


async def _run_turn(monkeypatch, memory, **kwargs):
    """Run one driver turn against the fakes. Returns (result, llm, elapsed_seconds).

    ``elapsed`` times only the awaited turn — module import of langchain costs seconds on
    a cold interpreter and would swamp any per-turn assertion.
    """
    from app.assistant.run_assistant import run_assistant

    llm = _patch_turn(monkeypatch, memory, **kwargs)
    started = time.perf_counter()
    result = await run_assistant(
        session=MagicMock(),
        ctx=_driver_ctx(),
        settings=Settings(google_api_key="AIzaTestKeyNotReal", langsmith_tracing=False),
        message="Where is my shipment?",
        thread_id="THR-TEST-1",
        session_id="web-1",
    )
    return result, llm, time.perf_counter() - started


async def test_turn_returns_before_summarisation_completes(monkeypatch):
    memory = _FakeMemory()
    result, _, elapsed = await _run_turn(monkeypatch, memory)

    assert result["response"] == "Your shipment is on track."
    assert result["summary_scheduled"] is True
    # The fake summariser sleeps 50 ms. Returning in materially less than that proves the
    # response did not wait for it — the point of the fix.
    assert elapsed < memory.summary_delay, f"turn waited for the summariser ({elapsed:.3f}s)"
    assert not memory.summary_finished.is_set()


async def test_scheduled_summary_still_lands_after_the_response(monkeypatch):
    """Acceptance for #15: fire-and-forget must not mean fire-and-lose."""
    memory = _FakeMemory()
    await _run_turn(monkeypatch, memory)

    await asyncio.wait_for(memory.summary_finished.wait(), timeout=2.0)
    assert memory.summaries == ["summary-of-oldest-chunk"]


async def test_background_task_failure_does_not_surface_to_the_driver(monkeypatch):
    from app.assistant import run_assistant as ra

    class _FailingMemory(_FakeMemory):
        async def maybe_summarize_history(self, **_kwargs):
            self.summary_started.set()
            raise RuntimeError("upstash down")

    memory = _FailingMemory()
    result, _, _ = await _run_turn(monkeypatch, memory)
    assert result["response"] == "Your shipment is on track."
    await asyncio.sleep(0.05)
    assert not ra._BACKGROUND_TASKS, "failed task must be released, not leaked"


# --------------------------------------------------------------------------- #
# Issue #8 (E0.3) — TECH_STACK.md §10's six measurements
# --------------------------------------------------------------------------- #

_GEMINI_USAGE = {
    "input_tokens": 2000,
    "output_tokens": 40,
    "total_tokens": 2040,
    "input_token_details": {"cache_read": 1500},
}


def test_cache_tokens_read_the_shape_langchain_actually_emits():
    """Field names verified against the installed packages: langchain_core 0.3.86
    defines input_token_details["cache_read"]; langchain_openai maps OpenAI's
    prompt_tokens_details.cached_tokens and langchain_google_genai maps Gemini's
    cached_content_token_count into it."""
    from app.assistant.observability import cache_tokens_from_usage

    assert cache_tokens_from_usage(_GEMINI_USAGE) == (2000, 1500, 40)
    assert cache_tokens_from_usage({"input_tokens": 10, "output_tokens": 2}) == (10, 0, 2)
    assert cache_tokens_from_usage({"input_tokens": "bad"}) == (0, 0, 0)
    assert cache_tokens_from_usage(None) == (0, 0, 0)
    assert cache_tokens_from_usage("nonsense") == (0, 0, 0)


def test_cache_hit_rate_is_none_when_no_provider_reported_tokens():
    """An unmeasured cache and a cold cache are different facts and must not share a
    value — a hard zero here would look like a broken prefix (§10 lever 5)."""
    from app.assistant.observability import TurnLatency

    turn = TurnLatency()
    assert turn.cache_hit_rate is None
    turn.record_llm(duration_ms=10.0, provider="P", model="m", hop=0, usage=_GEMINI_USAGE)
    assert turn.cache_hit_rate == 0.75


def test_llm_split_records_total_only_without_a_stream(monkeypatch):
    from app.assistant import observability as obs

    instrument = MagicMock()
    monkeypatch.setattr(obs, "llm_duration_metric", instrument)
    obs.TurnLatency().record_llm(duration_ms=1860.0, provider="P", model="m", hop=0)

    phases = [call.args[1]["phase"] for call in instrument.record.call_args_list]
    assert phases == ["total_no_stream"]


def test_llm_split_emits_ttft_and_generation_once_a_stream_supplies_first_token(monkeypatch):
    """Wired now so the split starts working the moment SSE lands (§10 lever 3), with no
    further instrumentation change."""
    from app.assistant import observability as obs

    instrument = MagicMock()
    monkeypatch.setattr(obs, "llm_duration_metric", instrument)
    turn = obs.TurnLatency(streaming=True)
    turn.record_llm(
        duration_ms=1860.0, provider="P", model="m", hop=0, first_token_ms=420.0
    )

    recorded = {call.args[1]["phase"]: call.args[0] for call in instrument.record.call_args_list}
    assert recorded == {"total": 1860.0, "ttft": 420.0, "generation": 1440.0}
    assert turn.ttft_ms == 420.0
    assert turn.finish(ux_state="answered")["llm_split"] == "measured"


def test_failed_inference_is_not_counted_as_a_successful_one(monkeypatch):
    from app.assistant import observability as obs

    instrument = MagicMock()
    monkeypatch.setattr(obs, "llm_duration_metric", instrument)
    obs.TurnLatency().record_llm(duration_ms=30_000.0, provider="P", model="m", hop=0, ok=False)

    assert instrument.record.call_args_list[0].args[1]["outcome"] == "error"


def test_redis_rtt_is_recorded_per_command_batch(monkeypatch):
    """Un-pipelined groups are counted as the number of round trips they really make."""
    from app.services import redis_memory as rm

    recorded: list[tuple[str, float]] = []
    monkeypatch.setattr(rm, "record_redis_op", lambda op, ms: recorded.append((op, ms)))
    memory = rm.ConversationMemory(
        Settings(upstash_redis_rest_url="", upstash_redis_rest_token="")
    )

    with memory._timed("pipeline_turn_context"):
        pass
    with memory._timed("summary_write_unpipelined", ops=5):
        pass

    assert [op for op, _ in recorded] == ["pipeline_turn_context", "summary_write_unpipelined"]
    assert memory.redis_ops == 6
    assert memory.redis_ms > 0


def test_redis_timer_records_even_when_the_batch_raises(monkeypatch):
    from app.services import redis_memory as rm

    recorded: list[tuple[str, float]] = []
    monkeypatch.setattr(rm, "record_redis_op", lambda op, ms: recorded.append((op, ms)))
    memory = rm.ConversationMemory(
        Settings(upstash_redis_rest_url="", upstash_redis_rest_token="")
    )

    with pytest.raises(RuntimeError):
        with memory._timed("pipeline_append_turn"):
            raise RuntimeError("upstash 500")

    assert recorded and recorded[0][0] == "pipeline_append_turn"
    assert memory.redis_ops == 1


async def test_turn_reports_all_six_measurements(monkeypatch):
    """One traced driver turn: one hop, two inferences, one tool, Redis accounted for."""
    tool = _FakeTool(name="get_my_shipment", delay=0.01)
    first = _FakeAI(
        content="",
        usage=_GEMINI_USAGE,
        tool_calls=[{"name": "get_my_shipment", "id": "call-1", "args": {}}],
    )
    final = _FakeAI(content="Your shipment is on track.", usage=_GEMINI_USAGE)
    memory = _FakeMemory()

    result, llm, elapsed = await _run_turn(
        monkeypatch, memory, ai=final, tool_rounds=[first], tools=[tool]
    )
    latency = result["latency"]

    assert llm.calls == 2, "one hop must cost two inferences"
    assert latency["hops"] == 1                      # hop-count distribution
    assert latency["llm_calls"] == 2
    assert latency["tool_calls"] == 1                # per-tool DB latency
    assert latency["tool_ms"] >= 10.0                # the fake tool slept 10 ms
    assert latency["redis_ops"] == 2                 # Redis RTT
    assert latency["redis_ms"] == 31.5
    assert latency["input_tokens"] == 4000
    assert latency["cached_input_tokens"] == 3000
    assert latency["cache_hit_rate"] == 0.75         # prompt-cache hit rate
    assert latency["llm_split"] == "unavailable_no_stream"
    # TTFT: with no streaming path the driver sees nothing until the turn ends, so TTFT is
    # the turn. Recorded with streaming=False so it never shares a percentile with a
    # future streamed turn.
    assert latency["streaming"] is False
    assert latency["ttft_ms"] == latency["turn_ms"]
    assert 0 < latency["turn_ms"] <= elapsed * 1000 + 1


async def test_tool_error_is_recorded_as_an_error_not_a_fast_success(monkeypatch):
    from app.assistant import observability as obs

    instrument = MagicMock()
    monkeypatch.setattr(obs, "tool_duration_metric", instrument)
    tool = _FakeTool(name="get_my_shipment", raises=RuntimeError("db down"))
    first = _FakeAI(
        content="", tool_calls=[{"name": "get_my_shipment", "id": "call-1", "args": {}}]
    )
    result, _, _ = await _run_turn(
        monkeypatch, _FakeMemory(), ai=_FakeAI(), tool_rounds=[first], tools=[tool]
    )

    assert result["latency"]["tool_calls"] == 1
    assert instrument.record.call_args_list[0].args[1] == {
        **obs.COMMON_ATTRIBUTES,
        "tool": "get_my_shipment",
        "outcome": "error",
    }


async def test_duplicate_turn_is_measured_too(monkeypatch):
    from app.assistant.run_assistant import run_assistant

    class _DupMemory(_FakeMemory):
        def load_turn_context(self, **_kwargs):
            return {
                "history": [
                    {"role": "user", "content": "hi", "client_message_id": "cm-1"},
                    {"role": "assistant", "content": "earlier answer"},
                ],
                "summaries": [],
                "session": {},
            }

    memory = _DupMemory()
    _patch_turn(monkeypatch, memory)
    result = await run_assistant(
        session=MagicMock(),
        ctx=_driver_ctx(),
        settings=Settings(google_api_key="AIzaTestKeyNotReal", langsmith_tracing=False),
        message="hi",
        thread_id="THR-TEST-1",
        session_id="web-1",
        client_message_id="cm-1",
    )

    assert result["duplicate"] is True
    assert result["latency"]["llm_calls"] == 0, "a deduped turn must not reach the model"
    assert result["latency"]["hops"] == 0


def test_attach_run_metrics_is_a_noop_without_a_run():
    from app.assistant.observability import attach_run_metrics

    attach_run_metrics(None, {"turn_ms": 1.0})

    run = MagicMock()
    attach_run_metrics(run, {"turn_ms": 1.0}, outputs={"response": "hi"})
    run.add_metadata.assert_called_once_with({"latency": {"turn_ms": 1.0}})
    run.add_outputs.assert_called_once_with({"response": "hi"})
