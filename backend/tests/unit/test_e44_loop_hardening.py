"""E4.4 (issue #34, M4) tests: LLM call timeout wiring and the turn-deadline ceiling.

Session-hold and Redis-protocol (this epic's other two sub-issues) are covered separately -- see
`test_db_session_hold.py` and `test_redis_native_protocol.py`.
"""

from __future__ import annotations

import asyncio

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
    def __init__(self, *_a, **_k):
        self.degraded = False
        self.degrade_reason = None
        self.redis_ops = 1
        self.redis_ms = 5.0

    async def load_turn_context(self, **_kwargs):
        return {"history": [], "summaries": [], "session": {}}

    async def append_turn(self, **_kwargs):
        return None

    async def maybe_summarize_history(self, **_kwargs):
        return None


def _no_op_session():
    from unittest.mock import AsyncMock, MagicMock

    session = AsyncMock()
    result = MagicMock()
    result.mappings.return_value.first.return_value = None
    session.execute = AsyncMock(return_value=result)
    return session


def _patch_prefetch(monkeypatch):
    from app.assistant import run_assistant as ra

    async def _fake_prefetch(_session, _ctx):
        return {"active_shipments": []}

    monkeypatch.setattr(ra.driver_reads, "get_driver_operational_context", _fake_prefetch)


# ---------------------------------------------------------------------------------------------
# build_chat_model -- timeout actually reaches the client.
# ---------------------------------------------------------------------------------------------


def test_build_chat_model_passes_the_configured_timeout_to_openai():
    from app.assistant.llm import build_chat_model

    # llm_provider forced explicitly, same reasoning as the gemini test below: this process's
    # real environment may have GCP_PROJECT set (from .env/.env.local), which would otherwise
    # win under "auto" mode (gemini-first per issue #31) regardless of the openai_api_key here.
    settings = Settings(
        openai_api_key="sk-test-not-real", llm_call_timeout_seconds=12.5, llm_provider="openai",
    )
    model = build_chat_model(settings)
    assert model.request_timeout == 12.5


def test_build_chat_model_passes_the_configured_timeout_to_gemini(tmp_path, monkeypatch):
    from app.assistant.llm import build_chat_model

    # llm_provider forced explicitly: this process's real environment may have OPENAI_API_KEY set
    # (from .env/.env.local), which would otherwise win under "auto" mode regardless of the
    # gcp_project set here -- exactly the ordering issue #31 flags.
    #
    # GOOGLE_APPLICATION_CREDENTIALS is pointed at a throwaway file because issue #103 made a
    # project id alone insufficient for Gemini readiness. Pointing at an existing file (rather
    # than passing GCP_SA_KEY_JSON) keeps this timeout test from materializing a key file as a
    # side effect -- the ADC path itself is covered in test_llm_factory.py. Nothing here
    # authenticates: google-genai resolves credentials lazily, on the first request.
    adc = tmp_path / "adc.json"
    adc.write_text('{"type": "service_account"}', encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(adc))
    settings = Settings(
        gcp_project="proj-x", llm_call_timeout_seconds=8.0, llm_provider="gemini",
    )
    model = build_chat_model(settings)
    assert model.timeout == 8.0


def test_build_chat_model_timeout_defaults_to_thirty_seconds():
    assert Settings().llm_call_timeout_seconds == 30.0


# ---------------------------------------------------------------------------------------------
# run_assistant -- the turn-deadline ceiling.
# ---------------------------------------------------------------------------------------------


class _HangingLLM:
    """Never completes within the test's deadline -- exercises the ceiling itself, not any one
    provider's own timeout (which is orthogonal and mocked away here)."""

    def bind_tools(self, _tools):
        return self

    async def ainvoke(self, _messages, config=None):
        await asyncio.sleep(10)
        return AIMessage(content="too late")

    async def astream(self, _messages, config=None):
        await asyncio.sleep(10)
        yield AIMessageChunk(content="too late")


@pytest.mark.asyncio
async def test_run_assistant_raises_turn_deadline_exceeded_when_the_loop_runs_long(monkeypatch):
    from app.assistant import run_assistant as ra
    from app.core.errors import AppError

    _patch_prefetch(monkeypatch)
    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: _FakeMemory())
    monkeypatch.setattr(ra, "build_chat_model", lambda _s: _HangingLLM())
    monkeypatch.setattr(ra, "build_driver_tools", lambda **_kwargs: [])

    settings = Settings(google_api_key="AIzaTestKeyNotReal", langsmith_tracing=False, turn_deadline_seconds=0.05)

    with pytest.raises(AppError) as exc:
        await ra.run_assistant(
            session=_no_op_session(), ctx=_driver_ctx(), settings=settings,
            message="Where is my shipment?", thread_id="THR-1", session_id="web-1",
        )
    assert exc.value.code == "TURN_DEADLINE_EXCEEDED"
    assert exc.value.status_code == 504


@pytest.mark.asyncio
async def test_stream_assistant_turn_yields_a_deadline_error_event_between_rounds(monkeypatch):
    """The streamed path can't use `asyncio.wait_for` around a whole async-generator
    consumption, so the deadline is checked between tool rounds instead -- this drives that path
    by making every round need another tool call, forcing at least one between-round check."""
    from app.assistant import run_assistant as ra

    class _AlwaysToolCallLLM:
        def bind_tools(self, _tools):
            return self

        async def astream(self, _messages, config=None):
            yield AIMessageChunk(
                content="", tool_call_chunks=[{"name": "get_my_tool", "args": "{}", "id": "call1", "index": 0}]
            )

    class _FakeTool:
        name = "get_my_tool"
        args_schema = None

        async def ainvoke(self, _args, config=None):
            return '{"code": "OK"}'

    _patch_prefetch(monkeypatch)
    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: _FakeMemory())
    monkeypatch.setattr(ra, "build_chat_model", lambda _s: _AlwaysToolCallLLM())
    monkeypatch.setattr(ra, "build_driver_tools", lambda **_kwargs: [_FakeTool()])

    settings = Settings(google_api_key="AIzaTestKeyNotReal", langsmith_tracing=False, turn_deadline_seconds=0.0)

    events = [
        e async for e in ra.stream_assistant_turn(
            session=_no_op_session(), ctx=_driver_ctx(), settings=settings,
            message="Find me a slot", thread_id="THR-1", session_id="web-1",
        )
    ]

    error_events = [e for e in events if e["event"] == "error"]
    assert error_events, "expected a deadline error event once the 0-second budget elapsed"
    assert error_events[-1]["data"]["code"] == "TURN_DEADLINE_EXCEEDED"
