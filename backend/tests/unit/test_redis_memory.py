import json

from app.core.settings import Settings
from app.services.redis_memory import TTL_SECONDS, ConversationMemory, normalize_memory_id


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


def test_conversation_memory_snapshot_degrades_without_upstash_config():
    memory = ConversationMemory(Settings(upstash_redis_rest_url="", upstash_redis_rest_token=""))

    snapshot = memory.snapshot(user_id="USR001", thread_id="THR-1")

    assert snapshot["code"] == "REDIS_MEMORY_UNAVAILABLE"
    assert snapshot["non_authoritative"] is True
    assert snapshot["ttl_seconds"] == TTL_SECONDS
    assert snapshot["degraded"] is True


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


def test_normalize_memory_id_sanitizes_and_bounds_key_parts():
    assert normalize_memory_id(" web:session / one ") == "web-session-one"
    assert normalize_memory_id(None, fallback="fallback") == "fallback"
    assert len(normalize_memory_id("x" * 200)) == 96
