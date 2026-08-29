from __future__ import annotations

import json
import logging
import re
import time
from contextlib import contextmanager
from typing import Any, Iterator, Protocol

from app.assistant.observability import record_redis_op
from app.core.settings import Settings
from app.core.tls import use_system_trust_store

logger = logging.getLogger(__name__)

TTL_SECONDS = 24 * 60 * 60
HISTORY_LIMIT = 40
DEFAULT_SESSION_ID = "default"

# Rolling-summary policy (ERICA-style, adapted to RPUSH + auth-scoped Upstash keys).
RAW_MESSAGE_LIMIT = 10
RAW_CONTEXT_SIZE = 5
SUMMARY_CHUNK_SIZE = 5
SUMMARY_CONTEXT_SIZE = 5

_SAFE_KEY_PART = re.compile(r"[^A-Za-z0-9_.-]+")

_SUMMARY_SYSTEM = (
    "Summarize this SetuHaul driver chat chunk briefly. "
    "Preserve important user facts, decisions, requests, and unresolved work. "
    "Do not invent shipment, ETA, appointment, dock, or facility facts. "
    "Label uncertain items as unresolved."
)


class _SummarizerLLM(Protocol):
    async def ainvoke(self, messages: list[Any]) -> Any: ...


def normalize_memory_id(value: str | None, *, fallback: str = DEFAULT_SESSION_ID) -> str:
    """Return a Redis-safe bounded key segment.

    The value is only a namespace for ephemeral memory. It never grants access.
    """
    raw = (value or "").strip()
    if not raw:
        raw = fallback
    safe = _SAFE_KEY_PART.sub("-", raw)[:96].strip(".-")
    return safe or fallback


def _parse_list_items(raw: list[Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw or []:
        if isinstance(item, str):
            out.append(json.loads(item))
        elif isinstance(item, dict):
            out.append(item)
    return out


class ConversationMemory:
    """Upstash Redis 24h non-authoritative conversation/session memory."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None
        self._async_client = None
        self.degraded = False
        self.degrade_reason: str | None = None
        # Redis RTT for this turn. Upstash is reached over its REST API, so every batch
        # below is a full HTTPS request - this is the number the native-protocol decision
        # (section 10 lever 9) will be measured against.
        self.redis_ops = 0
        self.redis_ms = 0.0
        url = (settings.upstash_redis_rest_url or "").strip()
        token = (settings.upstash_redis_rest_token or "").strip()
        if not url or not token:
            self.degraded = True
            self.degrade_reason = "UPSTASH_NOT_CONFIGURED"
            return
        try:
            use_system_trust_store()
            from upstash_redis import Redis

            self._client = Redis(url=url, token=token)
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_INIT_FAILED:{type(exc).__name__}"
            logger.warning("Upstash init failed: %s", type(exc).__name__)

        # E4.4 (issue #34): opt-in native-protocol client for the chat turn's two hot-path calls
        # (`load_turn_context`/`append_turn`) only -- every other method here still uses the REST
        # client above unconditionally, a deliberate scope boundary (see those two methods'
        # docstrings). Construction failure degrades to the REST fallback silently; it is not a
        # fatal error, since the REST client above is already a fully working memory layer.
        native_url = (settings.upstash_redis_native_url or "").strip()
        if native_url:
            try:
                import redis.asyncio as aioredis

                self._async_client = aioredis.from_url(native_url, decode_responses=True)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Native Redis client init failed, falling back to REST: %s", type(exc).__name__)

    @contextmanager
    def _timed(self, op: str, *, ops: int = 1) -> Iterator[None]:
        """Time one Upstash command batch and record it as Redis RTT.

        ``ops`` is the number of HTTP requests inside the block: the summariser's trailing
        writes are un-pipelined, so counting them as one would hide five round trips.
        """
        started = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
            self.redis_ops += ops
            self.redis_ms += duration_ms
            record_redis_op(op, duration_ms)

    def _scope(self, *, user_id: str, thread_id: str, session_id: str | None = None) -> tuple[str, str, str]:
        return (
            normalize_memory_id(user_id, fallback="unknown-user"),
            normalize_memory_id(session_id),
            normalize_memory_id(thread_id, fallback="unknown-thread"),
        )

    def _history_key(self, user_id: str, thread_id: str, session_id: str | None = None) -> str:
        uid, sid, tid = self._scope(user_id=user_id, session_id=session_id, thread_id=thread_id)
        return f"setuhaul:chat:{uid}:session:{sid}:thread:{tid}:history"

    def _summaries_key(self, user_id: str, thread_id: str, session_id: str | None = None) -> str:
        uid, sid, tid = self._scope(user_id=user_id, session_id=session_id, thread_id=thread_id)
        return f"setuhaul:chat:{uid}:session:{sid}:thread:{tid}:summaries"

    def _session_key(self, user_id: str, thread_id: str, session_id: str | None = None) -> str:
        uid, sid, tid = self._scope(user_id=user_id, session_id=session_id, thread_id=thread_id)
        return f"setuhaul:chat:{uid}:session:{sid}:thread:{tid}:state"

    def _active_key(self, user_id: str) -> str:
        uid = normalize_memory_id(user_id, fallback="unknown-user")
        return f"setuhaul:chat:{uid}:active"

    def _thread_pointer_key(self, user_id: str, thread_id: str) -> str:
        """Which session a given thread's history lives under (E5.2, issue #58).

        The history key is namespaced by user **and session and thread**. An ops coordinator taking
        over a thread knows the thread id (it is `chat_threads.thread_id`) and can derive the
        driver's `user_id` from Postgres, but has no way to know which chat *session* the driver's
        bubbles were appended under -- and without it the history key cannot be reconstructed at
        all. `_active_key` only answers this for the driver's single most recent thread; this
        answers it per thread. Written inside `append_turn`'s existing pipeline, so it costs one
        extra queued command and zero extra round trips.
        """
        uid = normalize_memory_id(user_id, fallback="unknown-user")
        tid = normalize_memory_id(thread_id, fallback="unknown-thread")
        return f"setuhaul:chat:{uid}:thread:{tid}:session"

    def _recommendation_key(self, *, user_id: str, shipment_id: str) -> str:
        uid = normalize_memory_id(user_id, fallback="unknown-user")
        shipment = normalize_memory_id(shipment_id, fallback="unknown-shipment")
        return f"setuhaul:chat:{uid}:recommendation:{shipment}"

    def store_active_recommendation(
        self, *, user_id: str, shipment_id: str, recommendation_id: str
    ) -> None:
        """Store an ephemeral display pointer; PostgreSQL remains authoritative."""
        if self._client is None:
            return
        try:
            self._client.set(
                self._recommendation_key(user_id=user_id, shipment_id=shipment_id),
                json.dumps({"recommendation_id": recommendation_id, "stale": False}),
                ex=TTL_SECONDS,
            )
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_RECOMMENDATION_WRITE_FAILED:{type(exc).__name__}"
            logger.warning("Upstash recommendation write failed: %s", type(exc).__name__)

    def mark_recommendation_stale(self, *, user_id: str, shipment_id: str) -> None:
        if self._client is None:
            return
        try:
            key = self._recommendation_key(user_id=user_id, shipment_id=shipment_id)
            raw = self._client.get(key)
            data = raw if isinstance(raw, dict) else (json.loads(raw) if raw else {})
            data["stale"] = True
            self._client.set(key, json.dumps(data), ex=TTL_SECONDS)
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_RECOMMENDATION_STALE_FAILED:{type(exc).__name__}"
            logger.warning("Upstash recommendation stale mark failed: %s", type(exc).__name__)

    def is_recommendation_stale(self, *, user_id: str, shipment_id: str) -> bool:
        if self._client is None:
            return False
        try:
            raw = self._client.get(self._recommendation_key(user_id=user_id, shipment_id=shipment_id))
            data = raw if isinstance(raw, dict) else (json.loads(raw) if raw else {})
            return bool(data.get("stale"))
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_RECOMMENDATION_READ_FAILED:{type(exc).__name__}"
            logger.warning("Upstash recommendation stale read failed: %s", type(exc).__name__)
            return False

    def clear_recommendation_stale(self, *, user_id: str, shipment_id: str) -> None:
        if self._client is None:
            return
        try:
            key = self._recommendation_key(user_id=user_id, shipment_id=shipment_id)
            raw = self._client.get(key)
            data = raw if isinstance(raw, dict) else (json.loads(raw) if raw else {})
            data["stale"] = False
            self._client.set(key, json.dumps(data), ex=TTL_SECONDS)
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_RECOMMENDATION_CLEAR_FAILED:{type(exc).__name__}"
            logger.warning("Upstash recommendation stale clear failed: %s", type(exc).__name__)

    def get_active_recommendation(self, *, user_id: str, shipment_id: str) -> str | None:
        """Return the last displayed REC id for this user/shipment, if Redis still has it."""
        if self._client is None:
            return None
        try:
            raw = self._client.get(self._recommendation_key(user_id=user_id, shipment_id=shipment_id))
            data = raw if isinstance(raw, dict) else (json.loads(raw) if raw else {})
            rec = data.get("recommendation_id")
            return str(rec) if rec else None
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_RECOMMENDATION_GET_FAILED:{type(exc).__name__}"
            logger.warning("Upstash recommendation get failed: %s", type(exc).__name__)
            return None

    def load_history(
        self,
        *,
        user_id: str,
        thread_id: str,
        session_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if self._client is None:
            return []
        try:
            take = HISTORY_LIMIT if limit is None else max(1, min(limit, HISTORY_LIMIT))
            with self._timed("lrange_history"):
                raw = self._client.lrange(
                    self._history_key(user_id, thread_id, session_id), -take, -1
                )
            out = _parse_list_items(raw)
            self.degraded = False
            self.degrade_reason = None
            return out
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_READ_FAILED:{type(exc).__name__}"
            logger.warning("Upstash read failed: %s", type(exc).__name__)
            return []

    def load_summaries(
        self,
        *,
        user_id: str,
        thread_id: str,
        session_id: str | None = None,
        limit: int = SUMMARY_CONTEXT_SIZE,
    ) -> list[str]:
        if self._client is None:
            return []
        try:
            take = max(1, min(limit, SUMMARY_CONTEXT_SIZE))
            with self._timed("lrange_summaries"):
                raw = self._client.lrange(
                    self._summaries_key(user_id, thread_id, session_id), -take, -1
                )
            out: list[str] = []
            for item in raw or []:
                if isinstance(item, str):
                    out.append(item)
                elif isinstance(item, dict):
                    out.append(str(item.get("content") or item))
                else:
                    out.append(str(item))
            return out
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_SUMMARY_READ_FAILED:{type(exc).__name__}"
            logger.warning("Upstash summary read failed: %s", type(exc).__name__)
            return []

    def load_session(
        self, *, user_id: str, thread_id: str, session_id: str | None = None
    ) -> dict[str, Any]:
        if self._client is None:
            return {}
        try:
            with self._timed("get_session"):
                raw = self._client.get(self._session_key(user_id, thread_id, session_id))
            if not raw:
                return {}
            if isinstance(raw, dict):
                return raw
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_SESSION_READ_FAILED:{type(exc).__name__}"
            return {}

    async def load_turn_context(
        self, *, user_id: str, thread_id: str, session_id: str | None = None
    ) -> dict[str, Any]:
        """Full history + summaries + session state in one pipelined round trip.

        Callers should dedupe/slice the returned ``history`` locally instead of
        issuing a second ``load_history()`` call — this replaces what used to be
        three-to-four separate Upstash HTTP requests per turn with one.

        E4.4 (issue #34): uses the native async client when configured (a real non-blocking
        round trip); otherwise falls back to the existing synchronous REST pipeline below,
        unchanged from before this epic. `async def` either way, so callers don't need to know
        which transport actually ran.
        """
        empty: dict[str, Any] = {"history": [], "summaries": [], "session": {}}
        hkey = self._history_key(user_id, thread_id, session_id)
        skey = self._summaries_key(user_id, thread_id, session_id)
        sekey = self._session_key(user_id, thread_id, session_id)

        if self._async_client is not None:
            try:
                pipe = self._async_client.pipeline()
                pipe.lrange(hkey, -HISTORY_LIMIT, -1)
                pipe.lrange(skey, -SUMMARY_CONTEXT_SIZE, -1)
                pipe.get(sekey)
                with self._timed("native_pipeline_turn_context"):
                    history_raw, summaries_raw, session_raw = await pipe.execute()
                summaries = [str(item) for item in (summaries_raw or [])]
                session = json.loads(session_raw) if session_raw else {}
                self.degraded = False
                self.degrade_reason = None
                return {"history": _parse_list_items(history_raw), "summaries": summaries, "session": session}
            except Exception as exc:  # noqa: BLE001
                self.degraded = True
                self.degrade_reason = f"NATIVE_REDIS_PIPELINE_READ_FAILED:{type(exc).__name__}"
                logger.warning("Native Redis pipelined read failed: %s", type(exc).__name__)
                return empty

        if self._client is None:
            return empty
        try:
            pipe = self._client.pipeline()
            pipe.lrange(hkey, -HISTORY_LIMIT, -1)
            pipe.lrange(skey, -SUMMARY_CONTEXT_SIZE, -1)
            pipe.get(sekey)
            with self._timed("pipeline_turn_context"):
                history_raw, summaries_raw, session_raw = pipe.exec()

            summaries: list[str] = []
            for item in summaries_raw or []:
                if isinstance(item, str):
                    summaries.append(item)
                elif isinstance(item, dict):
                    summaries.append(str(item.get("content") or item))
                else:
                    summaries.append(str(item))

            if not session_raw:
                session: dict[str, Any] = {}
            elif isinstance(session_raw, dict):
                session = session_raw
            else:
                session = json.loads(session_raw)

            self.degraded = False
            self.degrade_reason = None
            return {"history": _parse_list_items(history_raw), "summaries": summaries, "session": session}
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_PIPELINE_READ_FAILED:{type(exc).__name__}"
            logger.warning("Upstash pipelined read failed: %s", type(exc).__name__)
            return empty

    async def append_turn(
        self,
        *,
        user_id: str,
        thread_id: str,
        session_id: str | None = None,
        user_message: str,
        assistant_message: str,
        session: dict[str, Any] | None = None,
        client_message_id: str | None = None,
    ) -> None:
        """E4.4 (issue #34): native async client when configured, else the existing synchronous
        REST pipeline unchanged from before this epic -- see `load_turn_context`'s docstring for
        the same shape of fallback."""
        hkey = self._history_key(user_id, thread_id, session_id)
        user_payload = {
            "role": "user",
            "content": user_message,
            "client_message_id": client_message_id,
            "session_id": normalize_memory_id(session_id),
        }
        asst_payload = {
            "role": "assistant",
            "content": assistant_message,
            "session_id": normalize_memory_id(session_id),
        }
        active_payload = {
            "user_id": normalize_memory_id(user_id, fallback="unknown-user"),
            "session_id": normalize_memory_id(session_id),
            "thread_id": normalize_memory_id(thread_id, fallback="unknown-thread"),
        }

        # E5.2 (issue #58): one extra queued command inside the pipeline that already runs, not a
        # new round trip -- see `_thread_pointer_key`. This is what makes an ops coordinator's
        # `OPERATIONS` message able to find the driver's own history key later.
        pointer_key = self._thread_pointer_key(user_id, thread_id)
        pointer_payload = {"session_id": normalize_memory_id(session_id)}

        if self._async_client is not None:
            try:
                pipe = self._async_client.pipeline()
                pipe.rpush(hkey, json.dumps(user_payload), json.dumps(asst_payload))
                pipe.ltrim(hkey, -HISTORY_LIMIT, -1)
                pipe.expire(hkey, TTL_SECONDS)
                if session is not None:
                    skey = self._session_key(user_id, thread_id, session_id)
                    pipe.set(skey, json.dumps(session), ex=TTL_SECONDS)
                pipe.set(self._active_key(user_id), json.dumps(active_payload), ex=TTL_SECONDS)
                pipe.set(pointer_key, json.dumps(pointer_payload), ex=TTL_SECONDS)
                with self._timed("native_pipeline_append_turn"):
                    await pipe.execute()
                self.degraded = False
                self.degrade_reason = None
                return
            except Exception as exc:  # noqa: BLE001
                self.degraded = True
                self.degrade_reason = f"NATIVE_REDIS_WRITE_FAILED:{type(exc).__name__}"
                logger.warning("Native Redis write failed: %s", type(exc).__name__)
                return

        if self._client is None:
            return
        try:
            # One pipelined round trip instead of up to five separate requests.
            pipe = self._client.pipeline()
            pipe.rpush(hkey, json.dumps(user_payload), json.dumps(asst_payload))
            pipe.ltrim(hkey, -HISTORY_LIMIT, -1)
            pipe.expire(hkey, TTL_SECONDS)
            if session is not None:
                skey = self._session_key(user_id, thread_id, session_id)
                pipe.set(skey, json.dumps(session), ex=TTL_SECONDS)
            pipe.set(self._active_key(user_id), json.dumps(active_payload), ex=TTL_SECONDS)
            pipe.set(pointer_key, json.dumps(pointer_payload), ex=TTL_SECONDS)
            with self._timed("pipeline_append_turn"):
                pipe.exec()

            self.degraded = False
            self.degrade_reason = None
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_WRITE_FAILED:{type(exc).__name__}"
            logger.warning("Upstash write failed: %s", type(exc).__name__)

    def set_active_conversation(
        self, *, user_id: str, thread_id: str, session_id: str | None = None
    ) -> None:
        """Remember the latest chat namespace for UI restore after re-login (24h TTL)."""
        if self._client is None:
            return
        try:
            payload = {
                "user_id": normalize_memory_id(user_id, fallback="unknown-user"),
                "session_id": normalize_memory_id(session_id),
                "thread_id": normalize_memory_id(thread_id, fallback="unknown-thread"),
            }
            self._client.set(self._active_key(user_id), json.dumps(payload), ex=TTL_SECONDS)
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_ACTIVE_WRITE_FAILED:{type(exc).__name__}"
            logger.warning("Upstash active write failed: %s", type(exc).__name__)

    def get_active_conversation(self, *, user_id: str) -> dict[str, str] | None:
        if self._client is None:
            return None
        try:
            raw = self._client.get(self._active_key(user_id))
            if not raw:
                return None
            data = raw if isinstance(raw, dict) else json.loads(raw)
            session_id = str(data.get("session_id") or "").strip()
            thread_id = str(data.get("thread_id") or "").strip()
            if not session_id or not thread_id:
                return None
            return {"session_id": session_id, "thread_id": thread_id}
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_ACTIVE_READ_FAILED:{type(exc).__name__}"
            return None

    def resolve_thread_session_id(self, *, user_id: str, thread_id: str) -> str | None:
        """Which Redis session namespace this user's `thread_id` history lives under.

        Tries the per-thread pointer `append_turn` writes, then falls back to the user's single
        `active` pointer when it happens to name the same thread (covers a thread whose last turn
        predates this pointer existing but is still the driver's current conversation). Returns
        `None` when neither answers -- which the caller must treat as "cannot deliver", never as
        "deliver to the default session", since guessing would append a coordinator's message into
        a conversation the driver is not reading.
        """
        if self._client is None:
            return None
        target = normalize_memory_id(thread_id, fallback="unknown-thread")
        try:
            raw = self._client.get(self._thread_pointer_key(user_id, thread_id))
            if raw:
                data = raw if isinstance(raw, dict) else json.loads(raw)
                session_id = str(data.get("session_id") or "").strip()
                if session_id:
                    return session_id
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_THREAD_POINTER_READ_FAILED:{type(exc).__name__}"
            logger.warning("Upstash thread pointer read failed: %s", type(exc).__name__)
            return None

        active = self.get_active_conversation(user_id=user_id)
        if active and active["thread_id"] == target:
            return active["session_id"]
        return None

    async def append_agent_side_message(
        self,
        *,
        user_id: str,
        thread_id: str,
        session_id: str,
        content: str,
        sender: str,
        sender_name: str | None = None,
        message_id: str | None = None,
        message_ts: str | None = None,
    ) -> bool:
        """Project one already-committed non-driver message into the driver's live feed (issue #58).

        **This is a projection, not a write of record.** The authoritative row is the
        `chat_messages` row the caller has already committed to PostgreSQL; this only makes it
        visible in the bounded 24h Redis feed the driver's chat surface actually renders
        (`chat.py`'s `/chat/history` and `run_assistant`'s per-turn history both read Redis, and
        neither has ever read `chat_messages`). Returning `False` therefore means "durably
        recorded but not shown live", which is a different and much weaker failure than a lost
        message -- callers surface it rather than swallowing it.

        `role` stays `"assistant"` deliberately, rather than a new `"operations"`/`"system"` role:
        every existing consumer of this list (`load_conversation_for_restore`'s role filter,
        `run_assistant._prepare_turn`'s history→LangChain mapping, the driver chat UI's bubble
        renderer) understands exactly two roles, and a third would be silently dropped by all
        three. Provenance rides on `sender`/`sender_name` instead, which are additive and cannot
        break a consumer that ignores them. It also means the assistant, after hand-back, sees
        what the coordinator actually promised the driver instead of a hole in the transcript.
        """
        hkey = self._history_key(user_id, thread_id, session_id)
        payload = {
            "role": "assistant",
            "content": content,
            "session_id": normalize_memory_id(session_id),
            "sender": sender,
            "sender_name": sender_name,
            "message_id": message_id,
            "ts": message_ts,
        }

        if self._async_client is not None:
            try:
                pipe = self._async_client.pipeline()
                pipe.rpush(hkey, json.dumps(payload))
                pipe.ltrim(hkey, -HISTORY_LIMIT, -1)
                pipe.expire(hkey, TTL_SECONDS)
                with self._timed("native_append_agent_side_message"):
                    await pipe.execute()
                return True
            except Exception as exc:  # noqa: BLE001
                self.degraded = True
                self.degrade_reason = f"NATIVE_REDIS_PROJECTION_FAILED:{type(exc).__name__}"
                logger.warning("Native Redis projection failed: %s", type(exc).__name__)
                return False

        if self._client is None:
            return False
        try:
            pipe = self._client.pipeline()
            pipe.rpush(hkey, json.dumps(payload))
            pipe.ltrim(hkey, -HISTORY_LIMIT, -1)
            pipe.expire(hkey, TTL_SECONDS)
            with self._timed("append_agent_side_message"):
                pipe.exec()
            return True
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_PROJECTION_FAILED:{type(exc).__name__}"
            logger.warning("Upstash projection failed: %s", type(exc).__name__)
            return False

    def load_conversation_for_restore(
        self,
        *,
        user_id: str,
        thread_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Load Redis history for an explicit thread/session or the user's active pointer."""
        resolved_session = session_id
        resolved_thread = thread_id
        if not resolved_thread or not resolved_session:
            active = self.get_active_conversation(user_id=user_id)
            if active:
                resolved_session = resolved_session or active["session_id"]
                resolved_thread = resolved_thread or active["thread_id"]

        if not resolved_thread or not resolved_session:
            return {
                "code": "NO_ACTIVE_CONVERSATION",
                "source": "upstash_redis",
                "thread_id": None,
                "session_id": None,
                "messages": [],
                "ttl_seconds": TTL_SECONDS,
                "non_authoritative": True,
                "degraded": self.degraded,
                "degrade_reason": self.degrade_reason,
            }

        history = self.load_history(
            user_id=user_id, thread_id=resolved_thread, session_id=resolved_session
        )
        return {
            "code": "CHAT_HISTORY_LOADED" if history else "CHAT_HISTORY_EMPTY",
            "source": "upstash_redis",
            "thread_id": normalize_memory_id(resolved_thread, fallback="unknown-thread"),
            "session_id": normalize_memory_id(resolved_session),
            # E5.2 (issue #58): `sender`/`sender_name` are additive and always present, so a driver
            # client can tell an ops coordinator's message and the takeover divider apart from an
            # ordinary assistant reply. Defaulted for every message written before this existed,
            # rather than emitted as `null` only sometimes -- a consumer branching on this field
            # should never have to handle a third "unknown" case.
            "messages": [
                {
                    "role": item.get("role"),
                    "content": str(item.get("content") or ""),
                    "client_message_id": item.get("client_message_id"),
                    "sender": item.get("sender")
                    or ("DRIVER" if item.get("role") == "user" else "AGENT"),
                    "sender_name": item.get("sender_name"),
                }
                for item in history
                if item.get("role") in {"user", "assistant"}
            ],
            "ttl_seconds": TTL_SECONDS,
            "non_authoritative": True,
            "degraded": self.degraded,
            "degrade_reason": self.degrade_reason,
        }

    async def maybe_summarize_history(
        self,
        *,
        user_id: str,
        thread_id: str,
        session_id: str | None = None,
        llm: _SummarizerLLM,
        known_message_count: int | None = None,
    ) -> str | None:
        """When raw history is long enough, summarize the oldest chunk (ERICA-style).

        Summaries are ephemeral and non-authoritative. Operational facts must still
        be verified with PostgreSQL-backed tools.

        ``known_message_count`` lets a caller that just appended to this thread
        pass the already-known post-append count instead of paying for another
        Upstash round trip (``LLEN``) purely to re-derive it.
        """
        if self._client is None:
            return None
        hkey = self._history_key(user_id, thread_id, session_id)
        skey = self._summaries_key(user_id, thread_id, session_id)
        try:
            message_count = (
                known_message_count
                if known_message_count is not None
                else int(self._client.llen(hkey) or 0)
            )
            if message_count < RAW_MESSAGE_LIMIT:
                return None

            with self._timed("lrange_summary_chunk"):
                oldest = _parse_list_items(self._client.lrange(hkey, 0, SUMMARY_CHUNK_SIZE - 1))
            if not oldest:
                return None

            chunk_text = "\n".join(
                f"{item.get('role', 'unknown')}: {item.get('content', '')}" for item in oldest
            )
            from langchain_core.messages import HumanMessage, SystemMessage

            response = await llm.ainvoke(
                [
                    SystemMessage(content=_SUMMARY_SYSTEM),
                    HumanMessage(content=chunk_text[:4000]),
                ]
            )
            summary = response.content if isinstance(response.content, str) else str(response.content)
            summary = (summary or "").strip()
            if not summary:
                return None

            # Five separate HTTPS requests, unlike append_turn's single pipeline. Left
            # un-pipelined deliberately for now: this whole block runs off the request
            # path since the summariser became fire-and-forget, so pipelining it would
            # optimise a path no driver waits on. Measured as a five-op group so the cost
            # stays visible if it ever moves back onto the turn.
            with self._timed("summary_write_unpipelined", ops=5):
                self._client.rpush(skey, summary)
                self._client.ltrim(skey, -SUMMARY_CONTEXT_SIZE, -1)
                self._client.expire(skey, TTL_SECONDS)
                # Drop the summarized oldest raw messages; keep newer turns.
                self._client.ltrim(hkey, SUMMARY_CHUNK_SIZE, -1)
                self._client.expire(hkey, TTL_SECONDS)
            self.degraded = False
            self.degrade_reason = None
            return summary
        except Exception as exc:  # noqa: BLE001
            self.degraded = True
            self.degrade_reason = f"UPSTASH_SUMMARY_FAILED:{type(exc).__name__}"
            logger.warning("Upstash summarize failed: %s", type(exc).__name__)
            return None

    def seen_client_message(
        self,
        *,
        user_id: str,
        thread_id: str,
        client_message_id: str,
        session_id: str | None = None,
    ) -> bool:
        history = self.load_history(user_id=user_id, thread_id=thread_id, session_id=session_id)
        return any(m.get("client_message_id") == client_message_id for m in history)

    async def snapshot(
        self,
        *,
        user_id: str,
        thread_id: str,
        session_id: str | None = None,
        include_recent_messages: bool = True,
        recent_limit: int = 8,
    ) -> dict[str, Any]:
        """`async def` because it calls `load_turn_context`, which is (E4.4, issue #34). Not
        called from production code today -- only `load_turn_context`/`append_turn` are the
        actual chat-turn hot path this epic targets -- but a method depending on an async one
        cannot itself stay sync."""
        safe_session_id = normalize_memory_id(session_id)
        if self._client is None:
            return {
                "code": "REDIS_MEMORY_UNAVAILABLE",
                "source": "upstash_redis",
                "freshness": "unavailable",
                "thread_id": thread_id,
                "session_id": safe_session_id,
                "history_count": 0,
                "summary_count": 0,
                "summaries": [],
                "recent_messages": [],
                "session": {},
                "ttl_seconds": TTL_SECONDS,
                "non_authoritative": True,
                "degraded": True,
                "degrade_reason": self.degrade_reason or "UPSTASH_NOT_CONFIGURED",
            }

        turn_context = await self.load_turn_context(user_id=user_id, thread_id=thread_id, session_id=safe_session_id)
        history = turn_context["history"]
        summaries = turn_context["summaries"]
        session = turn_context["session"]
        recent = history[-max(1, min(recent_limit, HISTORY_LIMIT)) :] if include_recent_messages else []
        return {
            "code": "REDIS_MEMORY_LOADED",
            "source": "upstash_redis",
            "freshness": "ephemeral_24h",
            "thread_id": thread_id,
            "session_id": safe_session_id,
            "history_count": len(history),
            "summary_count": len(summaries),
            "summaries": [s[:500] for s in summaries],
            "recent_messages": [
                {
                    "role": item.get("role"),
                    "content": str(item.get("content") or "")[:500],
                    "client_message_id": item.get("client_message_id"),
                }
                for item in recent
            ],
            "session": session,
            "ttl_seconds": TTL_SECONDS,
            "non_authoritative": True,
            "degraded": self.degraded,
            "degrade_reason": self.degrade_reason,
        }
