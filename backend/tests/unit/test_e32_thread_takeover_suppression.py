"""E3.2 (issue #26, M3): `run_assistant` must suppress LLM auto-reply once a coordinator has
taken over a thread (`chat_threads.thread_status = 'ESCALATED'`). Before this epic nothing in the
turn path ever read `thread_status` at all -- verified by grep before this was built. This is a
narrow, dedicated regression guard for that one check, independent of `test_latency_levers.py`'s
broader turn-shape coverage.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.execution_context import ExecutionContext, RoleName
from app.core.settings import Settings


def _driver_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="req-1", auth_subject="auth-1", user_id="USR001",
        email="ravi.kumar@setuhaul.com", full_name="Ravi Kumar", role_id="ROL001",
        role_name=RoleName.DRIVER, driver_id="DRV001", facility_id="FAC-JAI-01",
        permissions=["chat:own"],
    )


class _FakeMemory:
    def __init__(self, *_a, **_k):
        self.degraded = False
        self.degrade_reason = None
        self.redis_ops = 1
        self.redis_ms = 5.0
        self.appended: list[dict] = []

    def load_turn_context(self, **_kwargs):
        return {"history": [], "summaries": [], "session": {}}

    def append_turn(self, **kwargs):
        self.appended.append(kwargs)

    async def maybe_summarize_history(self, **_kwargs):
        return None


def _session_returning(thread_status: str | None) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    row = {"thread_status": thread_status} if thread_status is not None else None
    result.mappings.return_value.first.return_value = row
    session.execute = AsyncMock(return_value=result)
    return session


def _patch_llm_should_not_be_called(monkeypatch):
    from app.assistant import run_assistant as ra

    class _LLM:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, *_a, **_k):
            raise AssertionError("LLM must not be invoked on an ESCALATED thread")

    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: memory)
    monkeypatch.setattr(ra, "build_chat_model", lambda _settings: _LLM())
    monkeypatch.setattr(ra, "build_driver_tools", lambda **_kwargs: [])


memory = _FakeMemory()


@pytest.mark.asyncio
async def test_run_assistant_suppresses_auto_reply_on_an_escalated_thread(monkeypatch):
    from app.assistant.run_assistant import run_assistant

    global memory
    memory = _FakeMemory()
    _patch_llm_should_not_be_called(monkeypatch)

    result = await run_assistant(
        session=_session_returning("ESCALATED"),
        ctx=_driver_ctx(),
        settings=Settings(google_api_key="AIzaTestKeyNotReal", langsmith_tracing=False),
        message="Where is my shipment?",
        thread_id="THR-TAKEN-OVER",
        session_id="web-1",
    )

    assert result["ux_state"] == "escalated_takeover"
    assert result["tool_calls"] == []
    assert "operations coordinator" in result["response"].lower()
    # The driver's real message is still preserved in Redis history, paired with the notice.
    assert memory.appended
    assert memory.appended[0]["user_message"] == "Where is my shipment?"


@pytest.mark.asyncio
async def test_run_assistant_proceeds_normally_when_the_thread_is_not_escalated(monkeypatch):
    from app.assistant import run_assistant as ra
    from app.assistant.run_assistant import run_assistant

    global memory
    memory = _FakeMemory()

    class _LLM:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, *_a, **_k):
            class _AI:
                content = "Your shipment is on track."
                tool_calls: list = []
                usage_metadata = None
                response_metadata: dict = {}

            return _AI()

    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: memory)
    monkeypatch.setattr(ra, "build_chat_model", lambda _settings: _LLM())
    monkeypatch.setattr(ra, "build_driver_tools", lambda **_kwargs: [])

    result = await run_assistant(
        session=_session_returning("OPEN"),
        ctx=_driver_ctx(),
        settings=Settings(google_api_key="AIzaTestKeyNotReal", langsmith_tracing=False),
        message="Where is my shipment?",
        thread_id="THR-NORMAL",
        session_id="web-1",
    )

    assert result["ux_state"] != "escalated_takeover"
    assert result["response"] == "Your shipment is on track."


@pytest.mark.asyncio
async def test_run_assistant_proceeds_normally_when_the_thread_has_no_row_yet(monkeypatch):
    """A brand-new thread (no chat_threads row written yet) is not escalated by default."""
    from app.assistant import run_assistant as ra
    from app.assistant.run_assistant import run_assistant

    global memory
    memory = _FakeMemory()

    class _LLM:
        def bind_tools(self, _tools):
            return self

        async def ainvoke(self, *_a, **_k):
            class _AI:
                content = "Your shipment is on track."
                tool_calls: list = []
                usage_metadata = None
                response_metadata: dict = {}

            return _AI()

    monkeypatch.setattr(ra, "ConversationMemory", lambda *_a, **_k: memory)
    monkeypatch.setattr(ra, "build_chat_model", lambda _settings: _LLM())
    monkeypatch.setattr(ra, "build_driver_tools", lambda **_kwargs: [])

    result = await run_assistant(
        session=_session_returning(None),
        ctx=_driver_ctx(),
        settings=Settings(google_api_key="AIzaTestKeyNotReal", langsmith_tracing=False),
        message="Where is my shipment?",
        thread_id="THR-BRAND-NEW",
        session_id="web-1",
    )

    assert result["ux_state"] != "escalated_takeover"
