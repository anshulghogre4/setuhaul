"""E4.3 (issue #33, M4) tests: lever 1 (operational-context prefetch) and lever 3
(`stream_assistant_turn` SSE generator), plus a dedicated regression guard for the `turn`-variable
shadowing bug found and fixed while building this epic (see `run_assistant.py`'s `hist_turn`
comment) -- every prior test used an empty `history` fixture, so nothing had ever exercised the
code path where the bug actually fired.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from app.core.execution_context import ExecutionContext, RoleName
from app.core.settings import Settings

FACILITY = "FAC-JAI-01"


def _driver_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="req-1", auth_subject="auth-1", user_id="USR001", email="ravi.kumar@setuhaul.com",
        full_name="Ravi Kumar", role_id="ROL001", role_name=RoleName.DRIVER, driver_id="DRV001",
        facility_id=FACILITY, permissions=["chat:own"],
    )


class _FakeMemory:
    def __init__(self, *_a, history=None, **_k):
        self.degraded = False
        self.degrade_reason = None
        self.redis_ops = 1
        self.redis_ms = 5.0
        self._history = history or []
        self.appended: list[dict] = []

    async def load_turn_context(self, **_kwargs):
        return {"history": self._history, "summaries": [], "session": {}}

    async def append_turn(self, **kwargs):
        self.appended.append(kwargs)

    async def maybe_summarize_history(self, **_kwargs):
        return None


def _no_op_session() -> AsyncMock:
    """No `chat_threads` row for this thread -- not escalated, proceed normally."""
    session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = None
    session.execute = AsyncMock(return_value=result)
    return session


def _settings() -> Settings:
    return Settings(google_api_key="AIzaTestKeyNotReal", langsmith_tracing=False)


class _FakeNoToolLLM:
    """A single round, no tool calls -- exercises the common (post-prefetch) no-hop path.

    Implements both `ainvoke` (the blocking `run_assistant` path) and `astream` (the SSE path),
    so the same fake backs the parity test between the two entrypoints.
    """

    def bind_tools(self, _tools):
        return self

    async def astream(self, _messages, config=None):
        for piece in ("Your ", "shipment ", "is on track."):
            yield AIMessageChunk(content=piece)

    async def ainvoke(self, _messages, config=None):
        return AIMessage(content="Your shipment is on track.")


class _FakeOneToolLLM:
    """Round 1 calls a tool; round 2 (post tool-result) streams the final answer."""

    def __init__(self):
        self.round = 0

    def bind_tools(self, _tools):
        return self

    async def astream(self, _messages, config=None):
        self.round += 1
        if self.round == 1:
            yield AIMessageChunk(
                content="",
                tool_call_chunks=[{"name": "get_my_tool", "args": "{}", "id": "call1", "index": 0}],
            )
        else:
            for piece in ("Found ", "1 option."):
                yield AIMessageChunk(content=piece)


class _FakeTool:
    def __init__(self, name="get_my_tool"):
        self.name = name
        self.args_schema = None

    async def ainvoke(self, _args, config=None):
        return '{"code": "OK"}'


def _patch_prefetch(monkeypatch, *, raises: bool = False):
    from app.assistant import run_assistant as ra

    async def _fake_prefetch(_session, _ctx):
        if raises:
            raise RuntimeError("prefetch boom")
        return {"active_shipments": [{"shipment_id": "SHP1017"}], "current_appointment": None}

    monkeypatch.setattr(ra.driver_reads, "get_driver_operational_context", _fake_prefetch)


# ---------------------------------------------------------------------------------------------
# Lever 1 -- prefetch
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_assistant_injects_the_prefetched_context_as_a_system_message(monkeypatch):
    from app.assistant import run_assistant as ra

    _patch_prefetch(monkeypatch)
    memory = _FakeMemory()
    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: memory)
    monkeypatch.setattr(ra, "build_chat_model", lambda _s: _FakeNoToolLLM())
    monkeypatch.setattr(ra, "build_driver_tools", lambda **_kwargs: [])

    result = await ra.run_assistant(
        session=_no_op_session(), ctx=_driver_ctx(), settings=_settings(),
        message="Where is my shipment?", thread_id="THR-1", session_id="web-1",
    )

    assert result["response"] == "Your shipment is on track."


@pytest.mark.asyncio
async def test_run_assistant_degrades_gracefully_when_the_prefetch_fails(monkeypatch):
    from app.assistant import run_assistant as ra

    _patch_prefetch(monkeypatch, raises=True)
    memory = _FakeMemory()
    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: memory)
    monkeypatch.setattr(ra, "build_chat_model", lambda _s: _FakeNoToolLLM())
    monkeypatch.setattr(ra, "build_driver_tools", lambda **_kwargs: [])

    result = await ra.run_assistant(
        session=_no_op_session(), ctx=_driver_ctx(), settings=_settings(),
        message="Where is my shipment?", thread_id="THR-1", session_id="web-1",
    )

    # The turn still completes -- a prefetch failure is not a hard dependency.
    assert result["response"] == "Your shipment is on track."


# ---------------------------------------------------------------------------------------------
# The turn-variable shadowing regression -- the bug this epic's work uncovered independently.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_assistant_does_not_crash_on_a_threads_second_message(monkeypatch):
    """Regression guard: `for turn in history:` used to silently overwrite the `TurnLatency`
    tracker (`turn = TurnLatency()`), since Python `for` targets are not block-scoped. Every prior
    test used an empty `history` fixture, so this fired on literally every real second message in
    a thread without ever being caught. Confirmed present in the last-pushed commit before this
    fix; this test would have failed with AttributeError against that code."""
    from app.assistant import run_assistant as ra

    _patch_prefetch(monkeypatch)
    memory = _FakeMemory(history=[
        {"role": "user", "content": "Where is my shipment?", "client_message_id": "cm-1"},
        {"role": "assistant", "content": "Your shipment is on track."},
    ])
    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: memory)
    monkeypatch.setattr(ra, "build_chat_model", lambda _s: _FakeNoToolLLM())
    monkeypatch.setattr(ra, "build_driver_tools", lambda **_kwargs: [])

    result = await ra.run_assistant(
        session=_no_op_session(), ctx=_driver_ctx(), settings=_settings(),
        message="What about now?", thread_id="THR-1", session_id="web-1", client_message_id="cm-2",
    )

    assert result["response"] == "Your shipment is on track."
    assert result["duplicate"] is False


# ---------------------------------------------------------------------------------------------
# Lever 3 -- stream_assistant_turn
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_assistant_turn_yields_start_tokens_then_done(monkeypatch):
    from app.assistant import run_assistant as ra

    _patch_prefetch(monkeypatch)
    memory = _FakeMemory()
    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: memory)
    monkeypatch.setattr(ra, "build_chat_model", lambda _s: _FakeNoToolLLM())
    monkeypatch.setattr(ra, "build_driver_tools", lambda **_kwargs: [])

    events = [
        e async for e in ra.stream_assistant_turn(
            session=_no_op_session(), ctx=_driver_ctx(), settings=_settings(),
            message="Where is my shipment?", thread_id="THR-1", session_id="web-1",
        )
    ]

    assert events[0]["event"] == "start"
    token_events = [e for e in events if e["event"] == "token"]
    assert [e["data"]["content"] for e in token_events] == ["Your ", "shipment ", "is on track."]
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["response"] == "Your shipment is on track."


@pytest.mark.asyncio
async def test_stream_assistant_turn_emits_a_status_event_for_a_tool_call(monkeypatch):
    from app.assistant import run_assistant as ra

    _patch_prefetch(monkeypatch)
    memory = _FakeMemory()
    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: memory)
    monkeypatch.setattr(ra, "build_chat_model", lambda _s: _FakeOneToolLLM())
    monkeypatch.setattr(ra, "build_driver_tools", lambda **_kwargs: [_FakeTool()])

    events = [
        e async for e in ra.stream_assistant_turn(
            session=_no_op_session(), ctx=_driver_ctx(), settings=_settings(),
            message="Find me a slot", thread_id="THR-1", session_id="web-1",
        )
    ]

    status_events = [e for e in events if e["event"] == "status"]
    assert status_events == [{"event": "status", "data": {"tool": "get_my_tool"}}]
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["response"] == "Found 1 option."
    assert events[-1]["data"]["tool_calls"][0]["name"] == "get_my_tool"


@pytest.mark.asyncio
async def test_stream_assistant_turn_matches_run_assistant_for_the_same_conversation(monkeypatch):
    """Parity: the two entrypoints must reach the same final answer for the same inputs, since
    both now go through the same `_prepare_turn`/`_execute_tool_round`/`_finalize_content`."""
    from app.assistant import run_assistant as ra

    _patch_prefetch(monkeypatch)
    monkeypatch.setattr(ra, "build_driver_tools", lambda **_kwargs: [])

    memory_a = _FakeMemory()
    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: memory_a)
    monkeypatch.setattr(ra, "build_chat_model", lambda _s: _FakeNoToolLLM())
    blocking_result = await ra.run_assistant(
        session=_no_op_session(), ctx=_driver_ctx(), settings=_settings(),
        message="Where is my shipment?", thread_id="THR-1", session_id="web-1",
    )

    memory_b = _FakeMemory()
    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: memory_b)
    monkeypatch.setattr(ra, "build_chat_model", lambda _s: _FakeNoToolLLM())
    streamed_events = [
        e async for e in ra.stream_assistant_turn(
            session=_no_op_session(), ctx=_driver_ctx(), settings=_settings(),
            message="Where is my shipment?", thread_id="THR-1", session_id="web-1",
        )
    ]
    streamed_result = streamed_events[-1]["data"]

    assert streamed_result["response"] == blocking_result["response"]
    assert streamed_result["ux_state"] == blocking_result["ux_state"]


@pytest.mark.asyncio
async def test_stream_assistant_turn_reports_llm_failure_as_an_error_event_not_an_exception(monkeypatch):
    from app.assistant import run_assistant as ra

    class _FailingLLM:
        def bind_tools(self, _tools):
            return self

        async def astream(self, _messages, config=None):
            raise RuntimeError("provider is down")
            yield  # pragma: no cover -- makes this an async generator

    _patch_prefetch(monkeypatch)
    memory = _FakeMemory()
    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: memory)
    monkeypatch.setattr(ra, "build_chat_model", lambda _s: _FailingLLM())
    monkeypatch.setattr(ra, "build_driver_tools", lambda **_kwargs: [])

    events = [
        e async for e in ra.stream_assistant_turn(
            session=_no_op_session(), ctx=_driver_ctx(), settings=_settings(),
            message="Where is my shipment?", thread_id="THR-1", session_id="web-1",
        )
    ]

    assert events[-1]["event"] == "error"
    assert events[-1]["data"]["code"] == "LLM_UNAVAILABLE"


@pytest.mark.asyncio
async def test_stream_assistant_turn_ends_immediately_on_a_duplicate_message(monkeypatch):
    from app.assistant import run_assistant as ra

    memory = _FakeMemory(history=[
        {"role": "user", "content": "hi", "client_message_id": "cm-1"},
        {"role": "assistant", "content": "earlier answer"},
    ])
    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: memory)

    events = [
        e async for e in ra.stream_assistant_turn(
            session=_no_op_session(), ctx=_driver_ctx(), settings=_settings(),
            message="hi", thread_id="THR-1", session_id="web-1", client_message_id="cm-1",
        )
    ]

    assert [e["event"] for e in events] == ["start", "done"]
    assert events[-1]["data"]["duplicate"] is True
