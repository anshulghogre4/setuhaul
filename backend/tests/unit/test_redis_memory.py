import json
from types import SimpleNamespace

import pytest

from app.core.settings import Settings
from app.services.redis_memory import (
    RAW_MESSAGE_LIMIT,
    SUMMARY_CHUNK_SIZE,
    TTL_SECONDS,
    ConversationMemory,
    normalize_memory_id,
)


class _FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    def lrange(self, key: str, start: int, end: int):
        items = self.lists.get(key, [])
        if start < 0:
            start = max(len(items) + start, 0)
        if end < 0:
            end = len(items) + end
        return items[start : end + 1]

    def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    def get(self, key: str):
        return self.values.get(key)

    def rpush(self, key: str, *values: str) -> None:
        self.lists.setdefault(key, []).extend(values)

    def ltrim(self, key: str, start: int, end: int) -> None:
        items = self.lists.get(key, [])
        if start < 0:
            start = max(len(items) + start, 0)
        if end < 0:
            end = len(items) + end
        self.lists[key] = items[start : end + 1]

    def expire(self, key: str, seconds: int) -> None:
        self.expirations[key] = seconds

    def set(self, key: str, value: str, ex: int) -> None:
        self.values[key] = value
        self.expirations[key] = ex

    def pipeline(self) -> "_FakePipeline":
        return _FakePipeline(self)


class _FakePipeline:
    """Minimal stand-in for upstash_redis's Pipeline: queue calls, run them
    against the same fake client in order on exec(), matching the real
    pipeline's "batch of commands, list of results" contract closely enough
    for these tests."""

    def __init__(self, client: "_FakeRedis") -> None:
        self._client = client
        self._ops: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name: str):
        def queue(*args, **kwargs):
            self._ops.append((name, args, kwargs))
            return self

        return queue

    def exec(self) -> list:
        results = [getattr(self._client, name)(*args, **kwargs) for name, args, kwargs in self._ops]
        self._ops = []
        return results


class _FakeSummarizer:
    async def ainvoke(self, messages):  # noqa: ANN001
        human = messages[-1].content
        return SimpleNamespace(content=f"SUMMARY::{human[:80]}")


def test_conversation_memory_snapshot_degrades_without_upstash_config():
    memory = ConversationMemory(Settings(upstash_redis_rest_url="", upstash_redis_rest_token=""))

    snapshot = memory.snapshot(user_id="USR001", thread_id="THR-1")

    assert snapshot["code"] == "REDIS_MEMORY_UNAVAILABLE"
    assert snapshot["non_authoritative"] is True
    assert snapshot["ttl_seconds"] == TTL_SECONDS
    assert snapshot["degraded"] is True
    assert snapshot["summaries"] == []


def test_conversation_memory_snapshot_returns_bounded_ephemeral_context():
    memory = ConversationMemory(Settings())
    fake = _FakeRedis()
    memory._client = fake  # type: ignore[attr-defined]
    memory.degraded = False
    memory.degrade_reason = None
    fake.rpush(
        "setuhaul:chat:USR001:session:web-1:thread:THR-1:history",
        json.dumps({"role": "user", "content": "Where is my appointment?", "client_message_id": "m1"}),
        json.dumps({"role": "assistant", "content": "Let me check status."}),
    )
    fake.set(
        "setuhaul:chat:USR001:session:web-1:thread:THR-1:state",
        json.dumps({"last_intent": "get_appointment_request_status"}),
        ex=TTL_SECONDS,
    )

    snapshot = memory.snapshot(user_id="USR001", thread_id="THR-1", session_id="web-1")

    assert snapshot["code"] == "REDIS_MEMORY_LOADED"
    assert snapshot["freshness"] == "ephemeral_24h"
    assert snapshot["session_id"] == "web-1"
    assert snapshot["history_count"] == 2
    assert snapshot["summary_count"] == 0
    assert snapshot["session"]["last_intent"] == "get_appointment_request_status"
    assert snapshot["recent_messages"][0]["client_message_id"] == "m1"


def test_conversation_memory_isolates_same_thread_by_session_id():
    memory = ConversationMemory(Settings())
    fake = _FakeRedis()
    memory._client = fake  # type: ignore[attr-defined]

    memory.append_turn(
        user_id="USR001",
        thread_id="THR-1",
        session_id="web-alpha",
        user_message="Alpha message",
        assistant_message="Alpha reply",
        session={"last_intent": "alpha"},
        client_message_id="same-client-message-id",
    )
    memory.append_turn(
        user_id="USR001",
        thread_id="THR-1",
        session_id="web-beta",
        user_message="Beta message",
        assistant_message="Beta reply",
        session={"last_intent": "beta"},
        client_message_id="beta-message-id",
    )

    alpha = memory.snapshot(user_id="USR001", thread_id="THR-1", session_id="web-alpha")
    beta = memory.snapshot(user_id="USR001", thread_id="THR-1", session_id="web-beta")

    assert alpha["session"]["last_intent"] == "alpha"
    assert beta["session"]["last_intent"] == "beta"
    assert "Alpha message" in alpha["recent_messages"][0]["content"]
    assert "Beta message" in beta["recent_messages"][0]["content"]
    assert memory.seen_client_message(
        user_id="USR001",
        thread_id="THR-1",
        session_id="web-alpha",
        client_message_id="same-client-message-id",
    )
    assert not memory.seen_client_message(
        user_id="USR001",
        thread_id="THR-1",
        session_id="web-beta",
        client_message_id="same-client-message-id",
    )


@pytest.mark.asyncio
async def test_maybe_summarize_history_rolls_oldest_chunk_into_summary():
    memory = ConversationMemory(Settings())
    fake = _FakeRedis()
    memory._client = fake  # type: ignore[attr-defined]
    memory.degraded = False

    hkey = "setuhaul:chat:USR001:session:web-1:thread:THR-1:history"
    skey = "setuhaul:chat:USR001:session:web-1:thread:THR-1:summaries"
    for i in range(RAW_MESSAGE_LIMIT):
        fake.rpush(
            hkey,
            json.dumps({"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"}),
        )

    summary = await memory.maybe_summarize_history(
        user_id="USR001",
        thread_id="THR-1",
        session_id="web-1",
        llm=_FakeSummarizer(),
    )

    assert summary is not None
    assert summary.startswith("SUMMARY::")
    assert fake.llen(hkey) == RAW_MESSAGE_LIMIT - SUMMARY_CHUNK_SIZE
    assert fake.llen(skey) == 1
    assert fake.expirations[skey] == TTL_SECONDS
    remaining = [json.loads(x)["content"] for x in fake.lists[hkey]]
    assert remaining[0] == f"msg-{SUMMARY_CHUNK_SIZE}"
    assert "msg-0" not in remaining

    loaded = memory.load_summaries(user_id="USR001", thread_id="THR-1", session_id="web-1")
    assert loaded == [summary]
    snap = memory.snapshot(user_id="USR001", thread_id="THR-1", session_id="web-1")
    assert snap["summary_count"] == 1
    assert snap["summaries"][0].startswith("SUMMARY::")


@pytest.mark.asyncio
async def test_maybe_summarize_history_skips_when_below_threshold():
    memory = ConversationMemory(Settings())
    fake = _FakeRedis()
    memory._client = fake  # type: ignore[attr-defined]
    fake.rpush(
        "setuhaul:chat:USR001:session:web-1:thread:THR-1:history",
        json.dumps({"role": "user", "content": "hi"}),
        json.dumps({"role": "assistant", "content": "hello"}),
    )

    summary = await memory.maybe_summarize_history(
        user_id="USR001",
        thread_id="THR-1",
        session_id="web-1",
        llm=_FakeSummarizer(),
    )
    assert summary is None
    assert fake.llen("setuhaul:chat:USR001:session:web-1:thread:THR-1:history") == 2


def test_normalize_memory_id_sanitizes_and_bounds_key_parts():
    assert normalize_memory_id(" web:session / one ") == "web-session-one"
    assert normalize_memory_id(None, fallback="fallback") == "fallback"
    assert len(normalize_memory_id("x" * 200)) == 96


def test_recommendation_stale_marker_is_ephemeral_and_scoped():
    memory = ConversationMemory(Settings())
    fake = _FakeRedis()
    memory._client = fake  # type: ignore[attr-defined]

    memory.store_active_recommendation(
        user_id="USR001", shipment_id="SHP1017", recommendation_id="REC-123"
    )
    assert memory.is_recommendation_stale(user_id="USR001", shipment_id="SHP1017") is False
    memory.mark_recommendation_stale(user_id="USR001", shipment_id="SHP1017")
    assert memory.is_recommendation_stale(user_id="USR001", shipment_id="SHP1017") is True
    memory.clear_recommendation_stale(user_id="USR001", shipment_id="SHP1017")
    assert memory.is_recommendation_stale(user_id="USR001", shipment_id="SHP1017") is False
    assert memory.get_active_recommendation(user_id="USR001", shipment_id="SHP1017") == "REC-123"
    assert all(seconds == TTL_SECONDS for seconds in fake.expirations.values())


def test_append_turn_sets_active_conversation_for_restore():
    memory = ConversationMemory(Settings())
    fake = _FakeRedis()
    memory._client = fake  # type: ignore[attr-defined]
    memory.degraded = False

    memory.append_turn(
        user_id="USR001",
        thread_id="THR-9",
        session_id="web-restore",
        user_message="hello",
        assistant_message="hi",
        session={"last_intent": "chat"},
        client_message_id="c1",
    )

    active = memory.get_active_conversation(user_id="USR001")
    assert active == {"session_id": "web-restore", "thread_id": "THR-9"}
    restored = memory.load_conversation_for_restore(user_id="USR001")
    assert restored["code"] == "CHAT_HISTORY_LOADED"
    assert restored["thread_id"] == "THR-9"
    assert restored["session_id"] == "web-restore"
    assert len(restored["messages"]) == 2
    assert restored["messages"][0]["content"] == "hello"
    assert restored["non_authoritative"] is True
