from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

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
        self.degraded = False
        self.degrade_reason: str | None = None
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

    def append_turn(
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
        if self._client is None:
            return
        try:
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
            self._client.rpush(hkey, json.dumps(user_payload), json.dumps(asst_payload))
            self._client.ltrim(hkey, -HISTORY_LIMIT, -1)
            self._client.expire(hkey, TTL_SECONDS)
            if session is not None:
                skey = self._session_key(user_id, thread_id, session_id)
                self._client.set(skey, json.dumps(session), ex=TTL_SECONDS)
            self.set_active_conversation(
                user_id=user_id, thread_id=thread_id, session_id=session_id
            )
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
            "messages": [
                {
                    "role": item.get("role"),
                    "content": str(item.get("content") or ""),
                    "client_message_id": item.get("client_message_id"),
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
    ) -> str | None:
        """When raw history is long enough, summarize the oldest chunk (ERICA-style).

        Summaries are ephemeral and non-authoritative. Operational facts must still
        be verified with PostgreSQL-backed tools.
        """
        if self._client is None:
            return None
        hkey = self._history_key(user_id, thread_id, session_id)
        skey = self._summaries_key(user_id, thread_id, session_id)
        try:
            message_count = int(self._client.llen(hkey) or 0)
            if message_count < RAW_MESSAGE_LIMIT:
                return None

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

    def snapshot(
        self,
        *,
        user_id: str,
        thread_id: str,
        session_id: str | None = None,
        include_recent_messages: bool = True,
        recent_limit: int = 8,
    ) -> dict[str, Any]:
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

        history = self.load_history(user_id=user_id, thread_id=thread_id, session_id=safe_session_id)
        summaries = self.load_summaries(
            user_id=user_id, thread_id=thread_id, session_id=safe_session_id
        )
        session = self.load_session(user_id=user_id, thread_id=thread_id, session_id=safe_session_id)
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
