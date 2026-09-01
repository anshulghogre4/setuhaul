"""A local, in-process stand-in for the Upstash REST client, with a kill switch.

Design citation: `SOLUTION_DESIGN.md` section 10.6 -- "Kill Redis mid-conversation; the next turn
must still answer correctly from Postgres. Freshness comes from the database, never from cache."
GitHub issue #44.

## Why a fake rather than the real thing

Issue #44 is explicit: "use a local/fake Redis or monkeypatched transport -- never touch the shared
Upstash instance." That is not only a safety rule, it is the only way to get a *deterministic* kill:
`kill()` makes every subsequent operation raise on the very next call, with no network timeout to
wait out and no chance of the outage healing itself halfway through an assertion.

## What it has to be faithful about

`ConversationMemory` never calls a plain `redis` client -- it calls `upstash_redis.Redis`, and its
two hot-path methods (`load_turn_context`, `append_turn`) go through `client.pipeline()` /
`pipe.exec()`, not through individual commands. A fake that only implemented `get`/`set` would make
the chaos test exercise a code path production never takes. So this implements the pipeline object
too, with the same queue-then-`exec()` shape and the same return-a-list-of-results contract, and
`_lrange` reproduces Redis's inclusive negative-index slicing rather than Python's.

Nothing here is a general-purpose Redis: only the commands `redis_memory.py` actually issues are
implemented, and an unknown command raises rather than silently returning None -- so if the memory
layer grows a new command, this fake fails loudly instead of quietly degrading the chaos test into
a no-op.
"""

from __future__ import annotations

import json
from typing import Any


class RedisKilled(ConnectionError):
    """What every operation raises once `kill()` has been called.

    A `ConnectionError` subclass on purpose: `redis_memory.py` catches bare `Exception` and records
    `UPSTASH_*_FAILED:<type name>`, so the degrade reason the test asserts on carries this class's
    own name and the assertion cannot pass against some unrelated error.
    """


def _lrange(values: list[Any], start: int, stop: int) -> list[Any]:
    """Redis LRANGE semantics: inclusive `stop`, negative indices from the end, empty on inversion.

    Python slicing is exclusive on the upper bound, so `lst[-40:-1]` -- the naive translation of
    the `lrange(key, -HISTORY_LIMIT, -1)` call `load_turn_context` makes -- silently drops the most
    recent entry. Getting this wrong would make the chaos test's "memory held the turn" precondition
    fail for reasons that have nothing to do with the outage being simulated.
    """
    length = len(values)
    begin = start + length if start < 0 else start
    end = stop + length if stop < 0 else stop
    begin = max(begin, 0)
    end = min(end, length - 1)
    if begin > end or length == 0:
        return []
    return values[begin : end + 1]


class FakePipeline:
    def __init__(self, client: "FakeUpstashRedis") -> None:
        self._client = client
        self._queued: list[tuple[str, tuple[Any, ...]]] = []

    def _queue(self, command: str, *args: Any) -> "FakePipeline":
        self._client._assert_alive()
        self._queued.append((command, args))
        return self

    # Only the commands redis_memory.py issues inside a pipeline.
    def lrange(self, key: str, start: int, stop: int):
        return self._queue("lrange", key, start, stop)

    def get(self, key: str):
        return self._queue("get", key)

    def rpush(self, key: str, *values: str):
        return self._queue("rpush", key, values)

    def ltrim(self, key: str, start: int, stop: int):
        return self._queue("ltrim", key, start, stop)

    def expire(self, key: str, ttl: int):
        return self._queue("expire", key, ttl)

    def set(self, key: str, value: str, ex: int | None = None):
        return self._queue("set", key, value)

    def exec(self) -> list[Any]:
        self._client._assert_alive()
        results: list[Any] = []
        for command, args in self._queued:
            results.append(self._client._apply(command, args))
        self._queued.clear()
        return results


class FakeUpstashRedis:
    """The subset of `upstash_redis.Redis` that `ConversationMemory` actually uses."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.alive = True
        self.calls = 0
        self.calls_after_kill = 0

    # -- the kill switch ------------------------------------------------------------------

    def kill(self) -> None:
        self.alive = False

    def revive(self) -> None:
        self.alive = True

    def _assert_alive(self) -> None:
        self.calls += 1
        if not self.alive:
            self.calls_after_kill += 1
            raise RedisKilled("fake Upstash Redis is down (proof-suite chaos injection)")

    # -- command dispatch -----------------------------------------------------------------

    def _apply(self, command: str, args: tuple[Any, ...]) -> Any:
        if command == "lrange":
            key, start, stop = args
            return _lrange(list(self.store.get(key) or []), int(start), int(stop))
        if command == "get":
            (key,) = args
            return self.store.get(key)
        if command == "rpush":
            key, values = args
            bucket = self.store.setdefault(key, [])
            bucket.extend(values)
            return len(bucket)
        if command == "ltrim":
            key, start, stop = args
            self.store[key] = _lrange(list(self.store.get(key) or []), int(start), int(stop))
            return "OK"
        if command == "expire":
            # TTL is real behaviour in Upstash but irrelevant to this proof, and faking expiry
            # against a wall clock would reintroduce exactly the time dependency section 9.1
            # forbids. Accepted and ignored, stated rather than silently swallowed.
            return 1
        if command == "set":
            key, value = args
            self.store[key] = value
            return "OK"
        raise NotImplementedError(
            f"FakeUpstashRedis does not implement {command!r}. redis_memory.py issued a command "
            "this fake has never seen -- add it here rather than letting the chaos test pass "
            "against an incomplete simulation."
        )

    # -- direct (non-pipelined) calls -----------------------------------------------------

    def pipeline(self) -> FakePipeline:
        self._assert_alive()
        return FakePipeline(self)

    def get(self, key: str) -> Any:
        self._assert_alive()
        return self._apply("get", (key,))

    def set(self, key: str, value: str, ex: int | None = None) -> Any:
        self._assert_alive()
        return self._apply("set", (key, value))

    def lrange(self, key: str, start: int, stop: int) -> Any:
        self._assert_alive()
        return self._apply("lrange", (key, start, stop))

    # -- test conveniences ----------------------------------------------------------------

    def history_entries(self, key_fragment: str) -> list[dict[str, Any]]:
        for key, value in self.store.items():
            if key_fragment in key and isinstance(value, list):
                return [json.loads(item) if isinstance(item, str) else item for item in value]
        return []
