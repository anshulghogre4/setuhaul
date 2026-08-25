"""E4.4 (issue #34, M4) tests: the opt-in native async Redis client for `ConversationMemory`'s
two chat-turn hot-path methods, `load_turn_context`/`append_turn`. See `redis_memory.py`'s module
docstring on `__init__` for the exact scope boundary -- every other method stays REST-only.
"""

from __future__ import annotations

import json

import pytest

from app.core.settings import Settings
from app.services.redis_memory import ConversationMemory


class _FakeAsyncPipeline:
    """Minimal stand-in for `redis.asyncio`'s Pipeline: queue calls, return canned results on
    `execute()` in call order -- the same fake-pipeline shape `test_redis_memory.py`'s
    `_FakePipeline` already uses for the REST client, mirrored for the native one."""

    def __init__(self, client: "_FakeAsyncRedis") -> None:
        self._client = client
        self._calls: list[tuple[str, tuple, dict]] = []

    def lrange(self, key, start, end):
        self._calls.append(("lrange", (key, start, end), {}))
        return self

    def get(self, key):
        self._calls.append(("get", (key,), {}))
        return self

    def rpush(self, key, *values):
        self._calls.append(("rpush", (key, *values), {}))
        return self

    def ltrim(self, key, start, end):
        self._calls.append(("ltrim", (key, start, end), {}))
        return self

    def expire(self, key, seconds):
        self._calls.append(("expire", (key, seconds), {}))
        return self

    def set(self, key, value, ex=None):
        self._calls.append(("set", (key, value), {"ex": ex}))
        return self

    async def execute(self):
        results = []
        for name, args, _kwargs in self._calls:
            method = getattr(self._client, f"_do_{name}")
            results.append(method(*args))
        self._client.pipeline_call_count += 1
        return results


class _FakeAsyncRedis:
    """Minimal stand-in for `redis.asyncio.Redis`."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.values: dict[str, str] = {}
        self.pipeline_call_count = 0
        self.raise_on_execute: Exception | None = None

    def pipeline(self):
        if self.raise_on_execute:
            class _Raising:
                def __getattr__(_self, _name):
                    def _fn(*_a, **_k):
                        return _self
                    return _fn

                async def execute(_self):
                    raise self.raise_on_execute

            return _Raising()
        return _FakeAsyncPipeline(self)

    def _do_lrange(self, key, start, end):
        items = self.lists.get(key, [])
        if start < 0:
            start = max(len(items) + start, 0)
        if end < 0:
            end = len(items) + end
        return items[start : end + 1]

    def _do_get(self, key):
        return self.values.get(key)

    def _do_rpush(self, key, *values):
        self.lists.setdefault(key, []).extend(values)
        return len(self.lists[key])

    def _do_ltrim(self, key, start, end):
        items = self.lists.get(key, [])
        if start < 0:
            start = max(len(items) + start, 0)
        if end < 0:
            end = len(items) + end
        self.lists[key] = items[start : end + 1]
        return True

    def _do_expire(self, key, seconds):
        return True

    def _do_set(self, key, value):
        self.values[key] = value
        return True


def _memory_with_native_client() -> tuple[ConversationMemory, _FakeAsyncRedis]:
    memory = ConversationMemory(Settings())
    fake = _FakeAsyncRedis()
    memory._async_client = fake  # type: ignore[attr-defined]
    memory.degraded = False
    return memory, fake


@pytest.mark.asyncio
async def test_append_turn_uses_the_native_client_when_configured():
    memory, fake = _memory_with_native_client()

    await memory.append_turn(
        user_id="USR001", thread_id="THR-1", session_id="web-1",
        user_message="hello", assistant_message="hi", session={"last_intent": "chat"},
    )

    assert fake.pipeline_call_count == 1
    hkey = "setuhaul:chat:USR001:session:web-1:thread:THR-1:history"
    assert len(fake.lists[hkey]) == 2
    assert json.loads(fake.lists[hkey][0])["content"] == "hello"


@pytest.mark.asyncio
async def test_load_turn_context_uses_the_native_client_when_configured():
    memory, fake = _memory_with_native_client()
    await memory.append_turn(
        user_id="USR001", thread_id="THR-1", session_id="web-1",
        user_message="hello", assistant_message="hi",
    )

    result = await memory.load_turn_context(user_id="USR001", thread_id="THR-1", session_id="web-1")

    assert [m["content"] for m in result["history"]] == ["hello", "hi"]


@pytest.mark.asyncio
async def test_load_turn_context_falls_back_to_rest_when_native_is_not_configured():
    """No `UPSTASH_REDIS_NATIVE_URL` -- `_async_client` is never constructed, and the method
    still works via the pre-existing REST path (`upstash_redis_rest_url` also unset here, so it
    degrades exactly as it always has -- no regression from this epic's own opt-in change)."""
    memory = ConversationMemory(Settings(upstash_redis_rest_url="", upstash_redis_rest_token=""))
    assert memory._async_client is None

    result = await memory.load_turn_context(user_id="USR001", thread_id="THR-1")

    assert result == {"history": [], "summaries": [], "session": {}}


@pytest.mark.asyncio
async def test_append_turn_degrades_gracefully_on_a_native_client_failure():
    memory, fake = _memory_with_native_client()
    fake.raise_on_execute = ConnectionError("native redis unreachable")

    await memory.append_turn(
        user_id="USR001", thread_id="THR-1", session_id="web-1",
        user_message="hello", assistant_message="hi",
    )

    assert memory.degraded is True
    assert memory.degrade_reason is not None
    assert memory.degrade_reason.startswith("NATIVE_REDIS_WRITE_FAILED")


@pytest.mark.asyncio
async def test_native_client_construction_failure_falls_back_to_rest(monkeypatch):
    """A bad native URL (unreachable host, malformed scheme) must not take down the whole
    memory layer -- construction failure degrades to the REST client silently, per
    `ConversationMemory.__init__`'s own docstring."""
    import redis.asyncio as aioredis

    def _raise(*_a, **_k):
        raise ValueError("malformed URL")

    monkeypatch.setattr(aioredis, "from_url", _raise)
    memory = ConversationMemory(
        Settings(upstash_redis_native_url="not-a-real-url", upstash_redis_rest_url="", upstash_redis_rest_token="")
    )
    assert memory._async_client is None
